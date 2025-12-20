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

from ados.common import ADOSError
from ados.config import ADOSConfig
from ados.discord.commands import Commands
from ados.discord.help import HelpCommand
from ados.discord.utils import MessageType, send_message

type BotContext = commands.context.Context[commands.Bot]

_log = logging.getLogger(__name__)


class ADOSBot(commands.Bot):

    def __init__(self, config: ADOSConfig):
        intents = discord.Intents.default()
        intents.message_content = True
        help_command = HelpCommand()  # type: ignore[no-untyped-call]
        super().__init__(command_prefix="!", intents=intents, help_command=help_command)

        bot_commands = Commands()
        # Need to set the help_command's cog so "help" is grouped with other commands
        help_command.cog = bot_commands
        self.add_cog(bot_commands)

        self._config = config
        self._guild_id: Optional[int] = None
        self._channel_ids: set[int] = set()

    def execute(self) -> None:
        _log.info("Starting ArchipelaDOS bot with configuration: %s", self._config.model_dump_json())
        super().run(self._config.discord_token)
        _log.info("Stopping ArchipelaDOS bot")

    async def on_ready(self) -> None:
        _log.info("Connected to Discord with ID: %d", self.application_id)

        self._guild_id = None
        self._channel_ids = set()
        guild_ref: discord.Guild

        for guild in self.guilds:
            if guild.name == self._config.discord_server:
                self._guild_id = guild.id
                guild_ref = guild
                break
        else:
            _log.error("Could not find Discord server '%s'; bot will not operate", self._config.discord_server)
            return

        config_channels = set(self._config.discord_channels)
        for channel in guild_ref.text_channels:
            if channel.name in config_channels:
                self._channel_ids.add(channel.id)
                config_channels.remove(channel.name)
        if config_channels:
            _log.warning(
                "Could not find Discord channels %s in server '%s'; bot will not operate in those channels",
                config_channels,
                self._config.discord_server,
            )

    async def on_message(self, message: discord.Message) -> None:
        if self._guild_id is None or message.guild is None or message.guild.id != self._guild_id:
            return
        if message.channel.id not in self._channel_ids:
            return
        await super().on_message(message)  # type: ignore[no-untyped-call]

    async def on_command_error(self, context: BotContext, exception: CommandError) -> None:
        if isinstance(exception, (CommandNotFound, ConversionError, UserInputError)):
            _log.info("Invalid user command '%s': %s", context.message.content, exception)
            await send_message(
                context, f"Invalid command: {exception}\nUse `!help` to see what's available.", MessageType.FAILURE
            )
        elif isinstance(exception, CommandInvokeError) and isinstance(exception.original, ADOSError):
            _log.info("Could not process user command '%s': %s", context.message.content, exception.original)
            await send_message(context, f"Could not process command: {exception.original}", MessageType.FAILURE)
        else:
            _log.warning("Unexpected error processing user command '%s': %s", context.message.content, exception)
            await send_message(
                context, "Something went wrong while processing your command. Try again later.", MessageType.FAILURE
            )
