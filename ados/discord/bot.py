import atexit
import logging
from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands.errors import (
    CommandError,
    CommandInvokeError,
    CommandNotFound,
    ConversionError,
    DisabledCommand,
    UserInputError,
)

from ados.common import ADOSError
from ados.config import ADOSConfig
from ados.discord.commands import Commands
from ados.discord.common import BotContext, EmojiType, send_failure
from ados.discord.deathpoll import DeathPollManager
from ados.discord.help import HelpCommand
from ados.room import ActiveRoomManager

_log = logging.getLogger(__name__)


# Discord will warn about PyNaCl not being installed if this is not set.
discord.VoiceClient.warn_nacl = False


# The main ArchipelaDOS Discord bot class. Handles processing of user commands, sending
# messages based on Archipelago events, and storage of bot state.
class ADOSBot(commands.Bot):

    def __init__(self, config: ADOSConfig):
        intents = discord.Intents.default()
        intents.message_content = True
        help_command = HelpCommand(config.discord_command_prefix)
        super().__init__(command_prefix=config.discord_command_prefix, intents=intents, help_command=help_command)

        # Guild and channel IDs start unset, and are populated in on_ready().
        self._config = config
        self._guild: Optional[discord.Guild] = None
        self._command_channel_ids: set[int] = set()

        self._room_manager = ActiveRoomManager(config, self)
        self._death_poll_manager = DeathPollManager()
        atexit.register(self._on_program_exit)

        bot_commands = Commands(config, self._room_manager, self._death_poll_manager)
        self.add_cog(bot_commands)

    async def execute(self) -> None:
        _log.info("Starting ArchipelaDOS bot with configuration: %s", self._config.model_dump_json())
        await self._room_manager.initialize()
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

        # Guild emojis are only populated after the bot has connected, so custom emojis for death poll
        # commands need to be set now.
        def _resolve_emoji(value: Optional[str]) -> Optional[EmojiType]:
            if value is None:
                return value
            for emoji in self.emojis:
                if emoji.name == value:
                    return emoji
            return value

        self._death_poll_manager.override_emojis(
            _resolve_emoji(self._config.deathpoll_yes_emoji_override),
            _resolve_emoji(self._config.deathpoll_no_emoji_override),
        )

        self._room_manager.start_broadcasting(self._guild)

    async def on_disconnect(self) -> None:
        _log.warning("Disconnected from Discord, reconnect will be attempted automatically")
        self._room_manager.stop_broadcasting()

    async def on_resumed(self) -> None:
        assert self._guild is not None
        _log.info("Reconnected to Discord with ID: %d", self.application_id)
        self._room_manager.start_broadcasting(self._guild)

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
        elif isinstance(exception, DisabledCommand):
            _log.info("User attempted use of a disabled command: %s", context.message.content)
            await send_failure(context, f"Invalid operation: {exception}")
        else:
            _log.error("Unexpected error processing user command '%s': %s", context.message.content, exception)
            await send_failure(context, "Something went wrong while processing your command.")

    # When the bot is shut down, we flush the current playtimes since each slot last joined.
    def _on_program_exit(self) -> None:
        try:
            self._room_manager.active_room.state.flush_playtime()
        except ADOSError:
            pass
