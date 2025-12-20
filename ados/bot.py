import logging

from discord import Intents
from discord.commands.context import ApplicationContext
from discord.ext import commands

from ados.config import ADOSConfig

_log = logging.getLogger(__name__)


class HelpCommand(commands.DefaultHelpCommand):
    pass


class ADOSCommands(commands.Cog, name="ArchipelaDOS"):  # pyright: ignore - pylance hates this pattern

    @commands.command(name="ping")
    async def ping(self, ctx: ApplicationContext) -> None:
        await ctx.send("Pong!")


class ADOSBot(commands.Bot):

    def __init__(self, config: ADOSConfig):
        intents = Intents.default()
        intents.message_content = True
        help_command = HelpCommand()  # type: ignore[no-untyped-call]
        super().__init__(command_prefix="!", intents=intents, help_command=help_command)

        bot_commands = ADOSCommands()
        help_command.cog = bot_commands  # Need to set the cog so 'help' is grouped with other commands
        self.add_cog(bot_commands)

        self._config = config

    def run(self) -> None:
        _log.info("Starting ArchipelaDOS bot with configuration: %s", self._config.model_dump_json())
        super().run(self._config.discord_token)
        _log.info("Stopping ArchipelaDOS bot")
