import atexit
import itertools
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

        # Guild starts unset, and is populated in on_ready().
        self._guild: Optional[discord.Guild] = None
        self._config = config

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

        # Need to find the guild so that we can restrict operations therein. If it cannot be found,
        # the bot will not operate at all.
        self._guild = None
        for guild in self.guilds:
            if guild.name == self._config.discord_server:
                self._guild = guild
                break
        else:
            _log.error("Could not find Discord server '%s'; bot will not operate", self._config.discord_server)
            return

        # Validate that the configured channels and roles exist in the guild.
        config_roles = set(itertools.chain(*self._config.discord_command_role_restrictions.values()))
        config_channels = set(itertools.chain(*self._config.discord_command_channel_restrictions.values()))
        config_channels.update(self._config.discord_command_channels)

        if missing_roles := config_roles - set(role.name for role in self._guild.roles):
            _log.warning(
                "Could not find configured roles %s in server '%s'", missing_roles, self._config.discord_server
            )
        if missing_channels := config_channels - set(channel.name for channel in self._guild.text_channels):
            _log.warning(
                "Could not find configured channels %s in server '%s'", missing_channels, self._config.discord_server
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
            channel_name = message.channel.name
            if isinstance(message.channel, discord.Thread):
                parent_channel = self._guild.get_channel(message.channel.parent_id)
                if parent_channel is not None:
                    channel_name = parent_channel.name
            if channel_name not in self._config.discord_command_channels:
                return

        await super().on_message(message)  # type: ignore[no-untyped-call]

    async def invoke(self, ctx: BotContext) -> None:
        assert self._guild is not None
        if ctx.invoked_with is None:
            return
        _log.info("Processing user command '%s'", ctx.message.content)

        member = ctx.author if isinstance(ctx.author, discord.Member) else self._guild.get_member(ctx.author.id)
        for command, roles in self._config.discord_command_role_restrictions.items():
            command = f"{self._config.discord_command_prefix}{command}"
            if ctx.message.content.startswith(command):
                if member is None or not roles.intersection(role.name for role in member.roles):
                    _log.info("User attempted use of command '%s' without sufficient roles", command)
                    await send_failure(ctx, f"You do not have permission to run `{command}`")
                    return

        for command, channels in self._config.discord_command_channel_restrictions.items():
            command = f"{self._config.discord_command_prefix}{command}"
            if ctx.message.content.startswith(command):
                if not isinstance(ctx.channel, discord.TextChannel) or ctx.channel.name not in channels:
                    _log.info("User attempted use of command '%s' in unsupported channel", command)
                    await send_failure(ctx, f"Command `{command}` cannot be used in the current channel")
                    return

        await super().invoke(ctx)

    # Handles different classes of errors raised during command processing.
    #   - Case #1: User syntax mistakes
    #   - Case #2: User using a disabled command
    #   - Case #3: Expected failure conditions, likely user mistakes
    #   - Case #4: Unexpected errors, potentially bugs
    async def on_command_error(self, context: BotContext, exception: CommandError) -> None:
        if isinstance(exception, (CommandNotFound, ConversionError, UserInputError)):
            _log.info("Invalid user command '%s': %s", context.message.content, exception)
            await send_failure(context, f"Invalid command: {exception}")
        elif isinstance(exception, DisabledCommand):
            _log.info("User attempted use of a disabled command: %s", context.message.content)
            await send_failure(context, f"Invalid operation: {exception}")
        elif isinstance(exception, CommandInvokeError) and isinstance(exception.original, ADOSError):
            _log.info("Error running user command '%s': %s", context.message.content, exception.original)
            await send_failure(context, f"Error running command: {exception.original}")
        else:
            _log.error("Unexpected error processing user command '%s': %s", context.message.content, exception)
            await send_failure(context, "Something went wrong while processing your command.")

    # When the bot is shut down, we flush the current playtimes since each slot last joined.
    def _on_program_exit(self) -> None:
        try:
            self._room_manager.active_room.state.flush_playtime()
        except ADOSError:
            pass
