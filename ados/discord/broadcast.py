import asyncio
import logging
from typing import NamedTuple, Optional

import discord

from ados.arch.messages import DeathLinkMessage, ItemSendMessage
from ados.arch.socket import SocketClient
from ados.common import ItemCategory, ItemCategoryFilter
from ados.config import ADOSConfig, BroadcastCategory
from ados.discord.common import highlight
from ados.state import GlobalState

_log = logging.getLogger(__name__)


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
        else:
            self.item_filter = ItemCategoryFilter.ALL
            self.send_traps = True
            self.send_death_links = True

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


# Broadcasts messages sent from the Archipelago socket connection to the various
# Discord channels, as specified by the configuration.
class MessageBroadcaster:

    def __init__(self, config: ADOSConfig, socket: SocketClient, state: GlobalState, client: discord.Client):
        self._socket = socket
        self._state = state
        self._client = client

        self._channel_configs = {
            channel_name: BroadcastConfig(categories)
            for channel_name, categories in config.discord_broadcast_channels.items()
        }
        self._channels: dict[str, discord.TextChannel] = {}

        self._broadcast_queue: asyncio.Queue[BroadcastItem] = asyncio.Queue()
        self._broadcast_task: Optional[asyncio.Task[None]] = None

        self._socket.add_message_handler(ItemSendMessage, self._handle_item_send)
        self._socket.add_message_handler(DeathLinkMessage, self._handle_death_link)

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

    async def _broadcast_loop(self) -> None:
        while True:
            item = await self._broadcast_queue.get()
            content = item.content

            mentions: list[str] = []
            for user_id in item.mention_user_ids:
                user = await self._client.get_or_fetch(discord.User, user_id)
                if user is not None:
                    mentions.append(user.mention)
            if mentions:
                content += "\n" + " ".join(mentions)

            for channel_name in item.channel_names:
                channel = self._channels.get(channel_name)
                if not channel:
                    continue
                await channel.send(content)

    def _handle_item_send(self, message: ItemSendMessage) -> None:
        channel_names: list[str] = []
        for channel_name, config in self._channel_configs.items():
            if message.category == ItemCategory.TRAP and config.send_traps:
                channel_names.append(channel_name)
            elif config.item_filter.check(message.category):
                channel_names.append(channel_name)
        if not channel_names:
            return

        _log.debug(
            "Queueing %s item send message for delivery to channels: %s",
            message.category.value,
            channel_names,
        )

        to_slot = self._state.resolve_slot(message.to_slot_id)
        from_slot = self._state.resolve_slot(message.from_slot_id)
        item = self._state.resolve_item(to_slot.game, message.item_id)
        location = self._state.resolve_location(from_slot.game, message.location_id)

        self_send = message.to_slot_id == message.from_slot_id
        if message.category == ItemCategory.TRAP:
            if self_send:
                content = f"`{from_slot}` subjected themsevles to {highlight(item)}"
            else:
                content = f"`{from_slot}` subjected {to_slot} to {highlight(item)}"
        else:
            # pylint: disable-next = else-if-used
            if self_send:
                content = f"`{from_slot}` found their own {highlight(item)}"
            else:
                content = f"`{from_slot}` sent {highlight(item)} to {to_slot}"
        content += f"  —  from check `{location}`"

        mention_user_ids = self._state.get_subscribed_users(to_slot, item)
        self._broadcast_queue.put_nowait(BroadcastItem(channel_names, content, mention_user_ids))

    def _handle_death_link(self, message: DeathLinkMessage) -> None:
        channel_names = [
            channel_name for channel_name, config in self._channel_configs.items() if config.send_death_links
        ]
        if not channel_names:
            return

        _log.debug(
            "Queueing death link message for delivery to channels: %s",
            channel_names,
        )

        content = f":headstone: `{message.slot_name}` has triggered a death link"
        self._broadcast_queue.put_nowait(BroadcastItem(channel_names, content))
