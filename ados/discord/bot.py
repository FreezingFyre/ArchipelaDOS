import asyncio
import logging
from datetime import datetime, timedelta
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

from ados.arch.socket import SocketClient
from ados.arch.web import WebClient
from ados.common import ADOSError
from ados.config import ADOSConfig
from ados.discord.broadcast import MessageBroadcaster
from ados.discord.commands import Commands
from ados.discord.common import COMMAND_PREFIX, THREAD_NAME, BotContext, send_failure
from ados.discord.help import HelpCommand
from ados.state import GlobalState

_log = logging.getLogger(__name__)

# On each cleanup interval, ArchipelaDOS threads with no activity within the inactivity
# threshold will be archived.
CLEANUP_INTERVAL = timedelta(minutes=1)
CLEANUP_INACTIVITY_THRESHOLD = timedelta(minutes=5)


# The main ArchipelaDOS Discord bot class. Handles processing of user commands, sending
# messages based on Archipelago events, and storage of bot state.
class ADOSBot(commands.Bot):

    def __init__(self, config: ADOSConfig):
        intents = discord.Intents.default()
        intents.message_content = True
        help_command = HelpCommand()  # type: ignore[no-untyped-call]
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents, help_command=help_command)

        # Guild and channel IDs start unset, and are populated in on_ready()
        self._config = config
        self._guild: Optional[discord.Guild] = None
        self._command_channel_ids: set[int] = set()

        self._web = WebClient(config)
        self._socket = SocketClient(config, slot_name=config.archipelago_slot, game="Archipelago", fetch_data=True)
        self._state = GlobalState(config, self._socket)
        self._broadcaster = MessageBroadcaster(config, self._socket, self._state, self)

        self._cleanup_task: Optional[asyncio.Task[None]] = None

        bot_commands = Commands(self._web, self._socket, self._state)
        self.add_cog(bot_commands)

    async def execute(self) -> None:
        _log.info("Starting ArchipelaDOS bot with configuration: %s", self._config.model_dump_json())
        await self._web.refresh()
        await self._socket.connect(self._web.server_url)
        await super().start(self._config.discord_token)
        _log.info("Stopping ArchipelaDOS bot")

    async def on_ready(self) -> None:
        _log.info("Connected to Discord with ID: %d", self.application_id)

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
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def on_disconnect(self) -> None:
        _log.error("Disconnected from Discord, reconnect will be attempted automatically")
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        self._broadcaster.stop()
        self._guild = None
        self._command_channel_ids.clear()

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

    # Periodically cleans up old threads in the command channels. Threads that have had no new
    # activity within the inactivity threshold are archived.
    async def _cleanup_loop(self) -> None:

        async def _cleanup_job() -> None:
            if not self._guild:
                return

            archived_count = 0
            bot_thread_count = 0
            archive_cutoff = datetime.now() - CLEANUP_INACTIVITY_THRESHOLD
            _log.debug("Checking for inactive threads to archive")

            threads = await self._guild.active_threads()
            for thread in threads:
                if thread.name != THREAD_NAME or thread.archived or thread.parent_id not in self._command_channel_ids:
                    continue
                bot_thread_count += 1
                new_messages = await thread.history(limit=1, after=archive_cutoff).flatten()
                if not new_messages:
                    archived_count += 1
                    await thread.edit(archived=True)

            _log.debug(
                "Archived %d inactive threads out of %d bot threads; checked %d total threads",
                archived_count,
                bot_thread_count,
                len(threads),
            )

        # Use asyncio.gather to run the cleanup job and the sleep concurrently, so whichever
        # takes longer determines the interval.
        while True:
            await asyncio.gather(
                _cleanup_job(),
                asyncio.sleep(CLEANUP_INTERVAL.total_seconds()),
            )
