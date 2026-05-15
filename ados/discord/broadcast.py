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
)
from ados.arch.socket import SocketClient
from ados.common import ItemCategory, ItemCategoryFilter
from ados.config import ADOSConfig, BroadcastCategory
from ados.discord.common import highlight
from ados.state import RoomState

_log = logging.getLogger(__name__)

DEFAULT_DEATH_LINK_MESSAGES = [
    "{player} has triggered a death link",
]


# Items placed on the broadcast queue for sending to channels.
class BroadcastItem(NamedTuple):
    channel_names: list[str]
    content: str
    mention_user_ids: set[int] = set()


# Configuration for which types of broadcasts to send to a particular channel.
class BroadcastConfig:
    def __init__(self, categories: set[BroadcastCategory]) -> None:
        if categories:
            self.item_filter = ItemCategoryFilter.NONE
            self.send_traps = False
            self.send_death_links = False
            self.send_join_leave = False
            self.send_player_chat = False
            self.send_server_chat = False
            self.send_goal_reached = False
            self.send_admin_alerts = False
        else:
            self.item_filter = ItemCategoryFilter.ALL
            self.send_traps = True
            self.send_death_links = True
            self.send_join_leave = True
            self.send_player_chat = True
            self.send_server_chat = True
            self.send_goal_reached = True
            self.send_admin_alerts = True

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
            elif category == BroadcastCategory.ADMIN_ALERTS:
                self.send_admin_alerts = True


# Broadcasts messages sent from the Archipelago socket connection to the various
# Discord channels, as specified by the configuration.
class MessageBroadcaster:

    def __init__(self, config: ADOSConfig, socket: SocketClient, state: RoomState, client: discord.Client):
        self._socket = socket
        self._state = state
        self._client = client

        self._channel_configs = {
            channel_name: BroadcastConfig(categories)
            for channel_name, categories in config.discord_broadcast_channels.items()
        }
        self._channels: dict[str, discord.TextChannel] = {}

        self._death_link_messages = self._load_death_link_messages(config.death_link_messages_path)

        self._broadcast_queue: asyncio.Queue[BroadcastItem] = asyncio.Queue()
        self._broadcast_task: Optional[asyncio.Task[None]] = None

        self._socket.add_message_handler(ItemSendMessage, self._handle_item_send)
        self._socket.add_message_handler(DeathLinkMessage, self._handle_death_link)
        self._socket.add_message_handler(JoinLeaveMessage, self._handle_join_leave)
        self._socket.add_message_handler(PlayerChatMessage, self._handle_player_chat)
        self._socket.add_message_handler(ServerChatMessage, self._handle_server_chat)
        self._socket.add_message_handler(GoalReachedMessage, self._handle_goal_reached)

    # Called by the bot when it is properly connected to Discord and ready to send.
    def start(self, guild: discord.Guild) -> None:
        _log.info("Starting message broadcaster in server '%s'", guild.name)

        channel_names = set(self._channel_configs.keys())
        for channel in guild.text_channels:
            if channel.name in channel_names:
                self._channels[channel.name] = channel
                channel_names.remove(channel.name)
        if channel_names:
            _log.warning(
                "Could not find Discord channels %s in server '%s'; bot will not broadcast there",
                channel_names,
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

    def admin_alert(self, message: str) -> None:
        channel_names = self._filter_channels(lambda config: config.send_admin_alerts)
        content = f":loud_sound: *{message}*"

        _log.info("Sending admin alert message: '%s'", message)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_names, content))

    def _load_death_link_messages(self, path: Optional[str]) -> list[str]:

        if not path:
            return DEFAULT_DEATH_LINK_MESSAGES

        try:
            messages: list[str] = []
            bad_messages: list[str] = []
            with open(path, "r") as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    if "{player}" in line:
                        messages.append(line)
                    else:
                        bad_messages.append(line)
        except Exception as ex:
            _log.error("Error loading death link messages from '%s': %s", path, ex)
            return DEFAULT_DEATH_LINK_MESSAGES

        _log.info("Loaded %d death link messages from '%s'", len(messages), path)
        if bad_messages:
            _log.warning(
                "Ignored %d death link messages from '%s' missing {player} token: %s",
                len(bad_messages),
                path,
                bad_messages,
            )
        return messages if messages else DEFAULT_DEATH_LINK_MESSAGES

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
                content = content.format(mentions=mentions)

                for channel_name in item.channel_names:
                    channel = self._channels.get(channel_name)
                    if not channel:
                        continue
                    await channel.send(content)
            except Exception as ex:
                _log.error("Error broadcasting message to channels %s: %s", item.channel_names, ex)

    # This is the core functionality of the broadcaster: handling an item being sent in the
    # multiworld. These are subject to a variety of filters based on channel configuration,
    # and may notify users who have subscribed to certain items.
    def _handle_item_send(self, message: ItemSendMessage) -> None:
        channel_names: list[str] = []
        for channel_name, config in self._channel_configs.items():
            if message.category == ItemCategory.TRAP and config.send_traps:
                channel_names.append(channel_name)
            elif config.item_filter.check(message.category):
                channel_names.append(channel_name)
        if not channel_names:
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
        mention_user_ids = self._state.get_subscribed_users(to_slot, item)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_names, content, mention_user_ids))

    def _handle_death_link(self, message: DeathLinkMessage) -> None:
        if not (channel_names := self._filter_channels(lambda config: config.send_death_links)):
            return

        content = highlight(message.slot_name)
        content = random.choice(self._death_link_messages).format(player=content)
        content = f":headstone: {content}"

        _log.info("Handling death link from '%s'", message.slot_name)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_names, content))

    def _handle_join_leave(self, message: JoinLeaveMessage) -> None:
        if not (channel_names := self._filter_channels(lambda config: config.send_join_leave)):
            return

        slot = self._state.resolve_slot(message.slot_id)
        if message.join_or_leave == JoinLeaveType.JOIN:
            content = f":arrow_right: {highlight(slot)} has joined the game"
        else:
            content = f":arrow_left: {highlight(slot)} has left the game"

        _log.info("Handling %s from '%s'", message.join_or_leave.value, slot)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_names, content))

    def _handle_player_chat(self, message: PlayerChatMessage) -> None:
        if not (channel_names := self._filter_channels(lambda config: config.send_player_chat)):
            return

        slot = self._state.resolve_slot(message.slot_id)
        content = f"{highlight(slot)} says: {message.message}"

        _log.info("Handling chat from '%s': '%s'", slot, message.message)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_names, content))

    def _handle_server_chat(self, message: ServerChatMessage) -> None:
        if not (channel_names := self._filter_channels(lambda config: config.send_server_chat)):
            return

        content = f"Server says: {message.message}"

        _log.info("Handling server chat: '%s'", message.message)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_names, content))

    def _handle_goal_reached(self, message: GoalReachedMessage) -> None:
        if not (channel_names := self._filter_channels(lambda config: config.send_goal_reached)):
            return

        slot = self._state.resolve_slot(message.slot_id)
        content = f":trophy: {highlight(slot)} has reached their goal!"

        _log.info("Handling goal reached for '%s'", slot)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_names, content))

    def _filter_channels(self, predicate: Callable[[BroadcastConfig], bool]) -> list[str]:
        return [channel_name for channel_name, config in self._channel_configs.items() if predicate(config)]
