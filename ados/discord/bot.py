import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands.errors import (
    CommandError,
    CommandInvokeError,
    CommandNotFound,
    ConversionError,
    UserInputError,
)

from ados.arch.messages import ConnectionClosedMessage
from ados.arch.socket import SocketClient
from ados.arch.web import WebClient
from ados.common import ADOSError
from ados.config import ADOSConfig
from ados.discord.broadcast import MessageBroadcaster
from ados.discord.commands import Commands
from ados.discord.common import COMMAND_PREFIX, BotContext, send_failure
from ados.discord.help import HelpCommand
from ados.state import GlobalState

_log = logging.getLogger(__name__)


# The main ArchipelaDOS Discord bot class. Handles processing of user commands, sending
# messages based on Archipelago events, and storage of bot state.
class ADOSBot(commands.Bot):

    def __init__(self, config: ADOSConfig):
        intents = discord.Intents.default()
        intents.message_content = True
        help_command = HelpCommand()  # type: ignore[no-untyped-call]
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents, help_command=help_command)

        # Guild and channel IDs start unset, and are populated in on_ready()
        self._connected = False
        self._config = config
        self._guild: Optional[discord.Guild] = None
        self._command_channel_ids: set[int] = set()

        self._web = WebClient(config)
        self._socket = SocketClient(config, slot_name=config.archipelago_slot, game=config.archipelago_game)
        self._state = GlobalState(config, self._socket)
        self._broadcaster = MessageBroadcaster(config, self._socket, self._state, self)

        self._cleanup_task: Optional[asyncio.Task[None]] = None

        bot_commands = Commands(config, self._web, self._socket, self._state)
        self.add_cog(bot_commands)

        self._socket.add_message_handler(ConnectionClosedMessage, self._on_socket_disconnected)

    async def execute(self) -> None:
        _log.info("Starting ArchipelaDOS bot with configuration: %s", self._config.model_dump_json())
        await self._web.refresh()
        await self._socket.connect(self._web.server_url, fetch_data=True)
        await super().start(self._config.discord_token)
        _log.info("Stopping ArchipelaDOS bot")

    async def on_ready(self) -> None:
        _log.info("Connected to Discord with ID: %d", self.application_id)

        self._connected = True
        self._guild = None
        self._command_channel_ids.clear()

        # Need to find the guild and channel IDs so that we can restrict operations therein.
        # If they cannot be found, the bot will not operate at all.
        for guild in self.guilds:
            if guild.name == self._config.discord_server:
                self._guild = guild
                break
        else:
            _log.error("Could not find Discord server '%s'; bot will not operate", self._config.discord_server)
            return

        command_channels = self._config.discord_command_channels.copy()
        for channel in self._guild.text_channels:
            if channel.name in command_channels:
                self._command_channel_ids.add(channel.id)
                command_channels.remove(channel.name)
        if command_channels:
            _log.warning(
                "Could not find Discord channels %s in server '%s'; bot will not operate in those channels",
                command_channels,
                self._config.discord_server,
            )

        self._broadcaster.start(self._guild)

    async def on_disconnect(self) -> None:
        _log.warning("Disconnected from Discord, reconnect will be attempted automatically")
        self._connected = False
        self._broadcaster.stop()

    async def on_resumed(self) -> None:
        assert self._guild is not None
        _log.info("Reconnected to Discord with ID: %d", self.application_id)
        self._broadcaster.start(self._guild)

    async def on_message(self, message: discord.Message) -> None:

        # Only process commands sent in the configured server and channels.
        if self._guild is None:
            return
        if message.guild is not None and message.guild.id != self._guild.id:
            return
        if not isinstance(message.channel, (discord.DMChannel, discord.TextChannel, discord.Thread)):
            return

        if not isinstance(message.channel, discord.DMChannel):
            channel_id = message.channel.id
            if isinstance(message.channel, discord.Thread):
                channel_id = message.channel.parent_id
            if channel_id not in self._command_channel_ids:
                return

        await super().on_message(message)  # type: ignore[no-untyped-call]

    async def on_command(self, context: BotContext) -> None:
        _log.info("Processing user command '%s'", context.message.content)

    # Handles different classes of errors raised during command processing.
    #   - Case #1: User syntax mistakes
    #   - Case #2: Expected failure conditions, likely user mistakes
    #   - Case #3: Unexpected errors, potentially bugs
    async def on_command_error(self, context: BotContext, exception: CommandError) -> None:
        if isinstance(exception, (CommandNotFound, ConversionError, UserInputError)):
            _log.info("Invalid user command '%s': %s", context.message.content, exception)
            await send_failure(context, f"Invalid command: {exception}")
        elif isinstance(exception, CommandInvokeError) and isinstance(exception.original, ADOSError):
            _log.info("Error running user command '%s': %s", context.message.content, exception.original)
            await send_failure(context, f"Error running command: {exception.original}")
        else:
            _log.error("Unexpected error processing user command '%s': %s", context.message.content, exception)
            await send_failure(context, "Something went wrong while processing your command.")

    # If the socket disconnects, we want to refresh the room and attempt a reconnect before
    # erroring out.
    def _on_socket_disconnected(self, _: ConnectionClosedMessage) -> None:

        async def _reconnect_task() -> None:
            _log.warning("Socket disconnected; attempting to refresh room and reconnect")
            try:
                await self._web.refresh()
                await self._socket.connect(self._web.server_url, fetch_data=False)
                _log.info("Socket successfully reconnected after disconnect")
            except Exception as ex:
                _log.error("Failed to reconnect socket after disconnect: %s", ex)
                assert self._guild is not None
                for channel in self._guild.text_channels:
                    if channel.name in self._config.discord_broadcast_channels:
                        await channel.send(
                            f":red_circle:  *Lost connection to Archipelago server. Use {COMMAND_PREFIX}refresh to attempt a reconnect.*"
                        )

        asyncio.create_task(_reconnect_task())
