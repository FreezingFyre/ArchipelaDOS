import logging

import discord
from discord.ext import commands

from ados.config import ADOSConfig

_log = logging.getLogger(__name__)


class _CustomHelp(commands.MinimalHelpCommand):

    def __init__(self) -> None:
        super().__init__(no_category="Commands")  # type: ignore

    async def send_pages(self) -> None:

        dest = self.get_destination()  # type: ignore
        if dest is self.context.channel and not isinstance(self.context.channel, discord.Thread):
            print(repr(self.context.message))
            dest = await self.context.message.create_thread(name="ArchipelaDOS")

        for page in self.paginator.pages:
            await dest.send(embed=discord.Embed(description=page))

        if isinstance(dest, discord.Thread):
            await dest.archive()


class ADOSBot(commands.Bot):

    def __init__(self, config: ADOSConfig):
        self._config = config
        intents = discord.Intents.default()
        intents.message_content = True
        _log.info("Initializing ADOSBot with provided configuration.")
        super().__init__(command_prefix="!", intents=intents, help_command=_CustomHelp())
