import asyncio
import logging
import random
from typing import Callable, NamedTuple, Optional

import discord

from ados.arch.messages import (
    DeathLinkMessage,
    GoalReachedMessage,
    ItemSendMessage,
    JoinLeaveMessage,
    JoinLeaveType,
    PlayerChatMessage,
    ServerChatMessage,
    SlotReleaseMessage,
)
from ados.arch.socket import SocketClient
from ados.common import DeathLinkSource, FinishState, ItemCategory, ItemCategoryFilter
from ados.config import ADOSConfig, BroadcastCategory
from ados.discord.common import highlight
from ados.state import RoomState

_log = logging.getLogger(__name__)

DEFAULT_DEATH_LINK_MESSAGES = [
    "{player} has triggered a death link",
]


# Items placed on the broadcast queue for sending to channels.
class BroadcastItem(NamedTuple):
    channel_ids: list[int]
    content: str
    mention_user_ids: set[int] = set()


# Configuration for which types of broadcasts to send to a particular channel.
class BroadcastConfig:
    def __init__(self, categories: set[BroadcastCategory]) -> None:

        everything = BroadcastCategory.EVERYTHING in categories

        self.item_filter = ItemCategoryFilter.ALL if everything else ItemCategoryFilter.NONE
        self.send_traps = everything
        self.send_death_links = everything
        self.send_join_leave = everything
        self.send_player_chat = everything
        self.send_server_chat = everything
        self.send_goal_reached = everything
        self.send_slot_released = everything
        self.send_room_completed = everything
        self.send_admin_alerts = everything

        for category in categories:
            if category == BroadcastCategory.PROGRESSION_ITEMS:
                self.item_filter = ItemCategoryFilter.PROGRESSION
            elif category == BroadcastCategory.USEFUL_ITEMS:
                self.item_filter = ItemCategoryFilter.USEFUL
            elif category == BroadcastCategory.ALL_ITEMS:
                self.item_filter = ItemCategoryFilter.ALL
            elif category == BroadcastCategory.TRAP_ITEMS:
                self.send_traps = True
            elif category == BroadcastCategory.DEATH_LINKS:
                self.send_death_links = True
            elif category == BroadcastCategory.JOIN_LEAVE:
                self.send_join_leave = True
            elif category == BroadcastCategory.PLAYER_CHAT:
                self.send_player_chat = True
            elif category == BroadcastCategory.SERVER_CHAT:
                self.send_server_chat = True
            elif category == BroadcastCategory.GOAL_REACHED:
                self.send_goal_reached = True
            elif category == BroadcastCategory.SLOT_RELEASED:
                self.send_slot_released = True
            elif category == BroadcastCategory.ROOM_COMPLETED:
                self.send_room_completed = True
            elif category == BroadcastCategory.ADMIN_ALERTS:
                self.send_admin_alerts = True


# Broadcasts messages sent from the Archipelago socket connection to the various
# Discord channels, as specified by the configuration.
class MessageBroadcaster:

    def __init__(self, config: ADOSConfig, socket: SocketClient, state: RoomState, client: discord.Client):
        self._config = config
        self._socket = socket
        self._state = state
        self._client = client

        self._channels: dict[int, discord.TextChannel | discord.Thread] = {}
        self._channel_configs: dict[int, BroadcastConfig] = {}
        self._no_mention_channels: set[int] = set()

        self._death_link_messages = self._load_death_link_messages(config.death_link_messages_path)

        self._broadcast_queue: asyncio.Queue[BroadcastItem] = asyncio.Queue()
        self._broadcast_task: Optional[asyncio.Task[None]] = None

        self._socket.add_message_handler(ItemSendMessage, self._handle_item_send)
        self._socket.add_message_handler(DeathLinkMessage, self._handle_death_link)
        self._socket.add_message_handler(JoinLeaveMessage, self._handle_join_leave)
        self._socket.add_message_handler(PlayerChatMessage, self._handle_player_chat)
        self._socket.add_message_handler(ServerChatMessage, self._handle_server_chat)
        self._socket.add_message_handler(GoalReachedMessage, self._handle_goal_reached)
        self._socket.add_message_handler(SlotReleaseMessage, self._handle_slot_release)

    # Called by the bot when it is properly connected to Discord and ready to send. Must populate the lists
    # of configured channels/threads at this point.
    def start(self, guild: discord.Guild, connect_id: Optional[int]) -> None:
        _log.info("Starting message broadcaster in server '%s'", guild.name)

        channel_categories = {
            identifier: categories.copy() for identifier, categories in self._config.discord_broadcast_channels.items()
        }
        mention_blacklist = self._config.discord_mention_channel_blacklist.copy()
        if connect_id is not None:
            if None in channel_categories:
                if connect_id not in channel_categories:
                    channel_categories[connect_id] = set()
                channel_categories[connect_id].update(channel_categories.pop(None))
            if None in mention_blacklist:
                mention_blacklist.add(connect_id)

        def _consider_channel(channel: discord.TextChannel | discord.Thread) -> None:
            if isinstance(channel, discord.Thread):
                assert isinstance(channel.parent, discord.TextChannel)
                channel_name = f"{channel.parent.name}@{channel.name}"
            else:
                channel_name = channel.name
            categories = channel_categories.pop(channel_name, set())
            categories.update(channel_categories.pop(channel.id, set()))
            if categories:
                self._channels[channel.id] = channel
                self._channel_configs[channel.id] = BroadcastConfig(categories)
            if mention_blacklist.intersection({channel.id, channel_name}):
                self._no_mention_channels.add(channel.id)

        for channel in guild.text_channels:
            _consider_channel(channel)
            for thread in channel.threads:
                _consider_channel(thread)

        channel_categories.pop(None, None)
        if channel_categories:
            _log.warning(
                "Could not find Discord channels/threads %s in server '%s'; bot will not broadcast there",
                set(channel_categories.keys()),
                guild.name,
            )

        self._broadcast_task = asyncio.create_task(self._broadcast_loop())

    # Called in the event the bot disconnects from Discord.
    def stop(self) -> None:
        _log.info("Stopping message broadcaster")
        if self._broadcast_task:
            self._broadcast_task.cancel()
            self._broadcast_task = None
        self._channels.clear()
        self._channel_configs.clear()
        self._no_mention_channels.clear()

    def admin_alert(self, message: str) -> None:
        channel_ids = self._filter_channels(lambda config: config.send_admin_alerts)
        content = f":loudspeaker: *{message}*"

        _log.info("Sending admin alert message: '%s'", message)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_ids, content))

    def _load_death_link_messages(self, path: Optional[str]) -> dict[DeathLinkSource, list[str]]:
        on_error_messages = {source: DEFAULT_DEATH_LINK_MESSAGES for source in DeathLinkSource}
        if not path:
            return on_error_messages

        messages: dict[DeathLinkSource, list[str]] = {source: [] for source in DeathLinkSource}
        bad_messages: list[str] = []
        try:
            with open(path, mode="r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("BOT_DEATHLINK:"):
                        messages[DeathLinkSource.BOT_DEATHLINK].append(line.removeprefix("BOT_DEATHLINK:").strip())
                    elif line.startswith("BOT_DEATHPOLL:"):
                        messages[DeathLinkSource.BOT_DEATHPOLL].append(line.removeprefix("BOT_DEATHPOLL:").strip())
                    elif "{player}" in line:
                        messages[DeathLinkSource.OTHER].append(line)
                    else:
                        bad_messages.append(line)
        except Exception as ex:
            _log.error("Error loading death link messages from '%s': %s", path, ex)
            return on_error_messages

        _log.info("Loaded %d death link messages from '%s'", sum(len(lines) for lines in messages.values()), path)
        if bad_messages:
            _log.warning(
                "Ignored %d death link messages from '%s' missing {player} token: %s",
                len(bad_messages),
                path,
                bad_messages,
            )
        if not messages[DeathLinkSource.OTHER]:
            messages[DeathLinkSource.OTHER] = DEFAULT_DEATH_LINK_MESSAGES
        for source, lines in messages.items():
            if not lines:
                messages[source] = messages[DeathLinkSource.OTHER]
        return messages

    async def _broadcast_loop(self) -> None:
        while True:
            item = await self._broadcast_queue.get()
            content = item.content

            try:
                mentions = ""
                for user_id in item.mention_user_ids:
                    user = await self._client.get_or_fetch(discord.User, user_id)
                    if user is not None:
                        mentions += f" {user.mention}"

                for channel_id in item.channel_ids:
                    channel = self._channels.get(channel_id)
                    channel_mentions = mentions if channel_id not in self._no_mention_channels else ""
                    if not channel:
                        continue
                    await channel.send(content.format(mentions=channel_mentions))

            except Exception as ex:
                _log.error(
                    "Error broadcasting message to channels %s: %s",
                    [self._channels[channel_id].name for channel_id in item.channel_ids],
                    ex,
                )

    # This is the core functionality of the broadcaster: handling an item being sent in the
    # multiworld. These are subject to a variety of filters based on channel configuration,
    # and may notify users who have subscribed to certain items.
    def _handle_item_send(self, message: ItemSendMessage) -> None:
        channel_ids: list[int] = []
        for channel_id, config in self._channel_configs.items():
            if message.category == ItemCategory.TRAP and config.send_traps:
                channel_ids.append(channel_id)
            elif config.item_filter.check(message.category):
                channel_ids.append(channel_id)
        if not channel_ids:
            return

        to_slot = self._state.resolve_slot(message.to_slot_id)
        from_slot = self._state.resolve_slot(message.from_slot_id)
        item = self._state.resolve_item(to_slot.game, message.item_id)
        location = self._state.resolve_location(from_slot.game, message.location_id)

        self_send = message.to_slot_id == message.from_slot_id
        if message.category == ItemCategory.TRAP:
            if self_send:
                content = f":broken_heart: {highlight(from_slot)} subjected themselves to `{item}`"
            else:
                content = f":broken_heart: {highlight(from_slot)} subjected {highlight(to_slot)} to `{item}`"
        else:
            # pylint: disable-next = else-if-used
            if self_send:
                content = f"{highlight(from_slot)} found their own `{item}`"
            else:
                content = f"{highlight(from_slot)} sent {highlight(to_slot)} their `{item}`"
        content += f"{{mentions}}\n-# via check {location}"

        _log.info("Handling item '%s' sent from '%s' to '%s'", item, from_slot, to_slot)
        mention_user_ids = self._state.get_subscribed_users(to_slot, message.category, item)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_ids, content, mention_user_ids))

    def _handle_death_link(self, message: DeathLinkMessage) -> None:
        if not (channel_ids := self._filter_channels(lambda config: config.send_death_links)):
            return

        content = highlight(message.slot_name)
        content = random.choice(self._death_link_messages[message.source]).format(player=content)
        content = f":headstone: {content}"

        _log.info("Handling death link from '%s'", message.slot_name)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_ids, content))

    def _handle_join_leave(self, message: JoinLeaveMessage) -> None:
        if not (channel_ids := self._filter_channels(lambda config: config.send_join_leave)):
            return

        slot = self._state.resolve_slot(message.slot_id)
        if message.join_or_leave == JoinLeaveType.JOIN:
            content = f":arrow_right: {highlight(slot)} has joined the game"
        else:
            content = f":arrow_left: {highlight(slot)} has left the game"

        _log.info("Handling %s from '%s'", message.join_or_leave.value, slot)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_ids, content))

    def _handle_player_chat(self, message: PlayerChatMessage) -> None:
        if not (channel_ids := self._filter_channels(lambda config: config.send_player_chat)):
            return

        slot = self._state.resolve_slot(message.slot_id)
        content = f"{highlight(slot)} says: {message.message}"

        _log.info("Handling chat from '%s': '%s'", slot, message.message)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_ids, content))

    def _handle_server_chat(self, message: ServerChatMessage) -> None:
        if not (channel_ids := self._filter_channels(lambda config: config.send_server_chat)):
            return

        content = f"Server says: {message.message}"

        _log.info("Handling server chat: '%s'", message.message)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_ids, content))

    def _handle_goal_reached(self, message: GoalReachedMessage) -> None:
        if not (channel_ids := self._filter_channels(lambda config: config.send_goal_reached)):
            return

        slot = self._state.resolve_slot(message.slot_id)
        content = f":trophy: {highlight(slot)} has reached their goal!"

        _log.info("Handling goal reached for '%s'", slot)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_ids, content))
        self._check_room_complete()

    def _handle_slot_release(self, message: SlotReleaseMessage) -> None:
        if not (channel_ids := self._filter_channels(lambda config: config.send_slot_released)):
            return
        if self._state.get_finish_state(message.slot_id) == FinishState.GOAL:
            return

        slot = self._state.resolve_slot(message.slot_id)
        content = f":broken_chain: {highlight(slot)} has released their remaining items"

        _log.info("Handling items released for '%s'", slot)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_ids, content))
        self._check_room_complete()

    def _check_room_complete(self) -> None:
        if not self._state.all_slots_finished():
            return
        if not (channel_ids := self._filter_channels(lambda config: config.send_room_completed)):
            return

        content = ":100: All players have completed their games!"

        _log.info("Handling room completion")
        self._broadcast_queue.put_nowait(BroadcastItem(channel_ids, content))

    def _filter_channels(self, predicate: Callable[[BroadcastConfig], bool]) -> list[int]:
        return [channel_id for channel_id, config in self._channel_configs.items() if predicate(config)]
