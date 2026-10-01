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
        self._command_role_restrictions: dict[str, set[int]] = {}
        self._command_channel_restrictions: dict[str, set[int]] = {}

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
        self._command_role_restrictions.clear()
        self._command_channel_restrictions.clear()

        # Need to find the guild and channel IDs so that we can restrict operations therein.
        # If they cannot be found, the bot will not operate at all.
        for guild in self.guilds:
            if guild.name == self._config.discord_server:
                self._guild = guild
                break
        else:
            _log.error("Could not find Discord server '%s'; bot will not operate", self._config.discord_server)
            return

        self._handle_channel_role_configs()
        self._handle_emoji_configs()
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

    async def invoke(self, ctx: BotContext) -> None:
        assert self._guild is not None
        _log.info("Processing user command '%s'", ctx.message.content)

        member = ctx.author if isinstance(ctx.author, discord.Member) else self._guild.get_member(ctx.author.id)
        for command, role_ids in self._command_role_restrictions.items():
            command = f"{self._config.discord_command_prefix}{command}"
            if ctx.message.content.startswith(command):
                if member is None or not role_ids.intersection(role.id for role in member.roles):
                    _log.info("User attempted use of command '%s' without sufficient roles", command)
                    await send_failure(ctx, f"You do not have permission to run `{command}`")
                    return

        for command, channel_ids in self._command_channel_restrictions.items():
            command = f"{self._config.discord_command_prefix}{command}"
            if ctx.message.content.startswith(command):
                if not isinstance(ctx.channel, discord.TextChannel) or ctx.channel.id not in channel_ids:
                    _log.info("User attempted use of command '%s' in unsupported channel", command)
                    await send_failure(ctx, f"Command `{command}` cannot be used in the current channel")
                    return

        await super().invoke(ctx)

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

    # Called to populate the local configuration of channel IDs and command restrictions once the bot
    # is connected to Discord.
    def _handle_channel_role_configs(self) -> None:
        assert self._guild is not None
        guild_channels = {channel.name: channel.id for channel in self._guild.text_channels}
        guild_roles = {role.name: role.id for role in self._guild.roles}
        unfound_channels: set[str] = set()
        unfound_roles: set[str] = set()

        def _resolve_channel_ids(channel_names: set[str]) -> set[int]:
            channel_ids: set[int] = set()
            for channel_name in channel_names:
                if (channel_id := guild_channels.get(channel_name)) is not None:
                    channel_ids.add(channel_id)
                else:
                    unfound_channels.add(channel_name)
            return channel_ids

        def _resolve_role_ids(role_names: set[str]) -> set[int]:
            role_ids: set[int] = set()
            for role_name in role_names:
                if (role_id := guild_roles.get(role_name)) is not None:
                    role_ids.add(role_id)
                else:
                    unfound_roles.add(role_name)
            return role_ids

        self._command_channel_ids = _resolve_channel_ids(self._config.discord_command_channels)
        self._command_channel_restrictions = {
            command: _resolve_channel_ids(channel_names)
            for command, channel_names in self._config.discord_command_channel_restrictions.items()
        }
        self._command_role_restrictions = {
            command: _resolve_role_ids(role_names)
            for command, role_names in self._config.discord_command_role_restrictions.items()
        }

        if unfound_channels:
            _log.warning(
                "Could not find configured Discord channels %s in server '%s'",
                unfound_channels,
                self._config.discord_server,
            )
        if unfound_roles:
            _log.warning(
                "Could not find configured Discord roles %s in server '%s'", unfound_roles, self._config.discord_server
            )

    # Called to handle custom death poll emoji configuration once the bot is connected to Discord, since
    # guild emojis are only populated at that point.
    def _handle_emoji_configs(self) -> None:
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

    # When the bot is shut down, we flush the current playtimes since each slot last joined.
    def _on_program_exit(self) -> None:
        try:
            self._room_manager.active_room.state.flush_playtime()
        except ADOSError:
            pass
