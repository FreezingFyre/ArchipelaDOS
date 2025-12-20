import logging
import random
from typing import Literal, Optional

import discord
from discord.ext import commands
from discord.ext.commands.errors import (
    CommandError,
    CommandNotFound,
    ConversionError,
    UserInputError,
)

from ados.config import ADOSConfig

type BotContext = commands.context.Context[commands.Bot]

_log = logging.getLogger(__name__)


async def _send_embed(ctx: BotContext, embed: discord.Embed) -> None:
    await ctx.send(embed=embed)


async def _send_success(ctx: BotContext, message: str) -> None:
    await _send_embed(ctx, discord.Embed(description=f"*{message}*", color=discord.Color.dark_green()))


async def _send_info(ctx: BotContext, message: str) -> None:
    await _send_embed(ctx, discord.Embed(description=f"*{message}*", color=discord.Color.light_grey()))


async def _send_failure(ctx: BotContext, message: str) -> None:
    await _send_embed(ctx, discord.Embed(description=f"*{message}*", color=discord.Color.dark_red()))


class ADOSCommands(commands.Cog, name="ArchipelaDOS"):  # pyright: ignore - pylance hates this pattern

    ################################################
    ################ BASIC COMMANDS ################
    ################################################

    HELLO_RESPONSES = [
        "Hello!",
        "Hallo!",
        "Bonjour!",
        "Guten Tag!",
        "Yassas!",
        "Shalom!",
        "Marhaba!",
        "Namaste!",
        "Dia duit!",
        "Salve!",
        "Ciao!",
        "Kon'nichiwa!",
        "Annyeonghaseyo!",
        "Nǐ hǎo!",
        "Dzień dobry!",
        "Olá!",
        "¡Hola!",
        "Zdravstvuyte!",
        "Hej!",
        "Xin chào!",
    ]

    @commands.command(name="hello", help="Greet the bot (and it might greet you back)")
    async def hello(self, ctx: BotContext) -> None:
        await _send_info(ctx, random.choice(ADOSCommands.HELLO_RESPONSES))

    ################################################
    ########### SLOT MANAGEMENT COMMANDS ###########
    ################################################

    @commands.group(name="slot", help="Manage slot registrations", invoke_without_command=True)  # type: ignore[arg-type]
    async def slot(self, ctx: BotContext) -> None:
        raise CommandNotFound("Must specify a sub-command for !slot")

    @slot.command(name="add", help="Registers you for the given slot")  # type: ignore[arg-type]
    async def slot_add(self, ctx: BotContext, slot: str) -> None:
        pass

    @slot.command(name="remove", help="Unregisters you from the given slot")  # type: ignore[arg-type]
    async def slot_remove(self, ctx: BotContext, slot: str) -> None:
        pass

    @slot.command(name="list", help="Lists all slots for which you are registered")  # type: ignore[arg-type]
    async def slot_list(self, ctx: BotContext) -> None:
        pass

    @slot.command(name="clear", help="Unregisters you from all slots")  # type: ignore[arg-type]
    async def slot_clear(self, ctx: BotContext) -> None:
        pass

    ################################################
    ######### NOTIFICATION REPLAY COMMANDS #########
    ################################################

    @commands.group(name="replay", help="View previously received items for your registered slots", invoke_without_command=True)  # type: ignore[arg-type]
    async def replay(self, ctx: BotContext) -> None:
        raise CommandNotFound("Must specify a sub-command for !replay")

    @replay.command(name="recent", help="Replay items received since last call (for the given slot if specified)")  # type: ignore[arg-type]
    async def replay_recent(self, ctx: BotContext, slot: Optional[str] = None) -> None:
        pass

    @replay.command(name="all", help="Replay all items recieved since game start (for the given slot if specified)")  # type: ignore[arg-type]
    async def replay_all(self, ctx: BotContext, slot: Optional[str] = None) -> None:
        pass

    @commands.command(name="ketchmeup", help="Alias of '!replay recent'")
    async def ketchmeup(self, ctx: BotContext, slot: Optional[str] = None) -> None:
        await self.replay_recent(ctx, slot)  # type: ignore[arg-type]

    ################################################
    ################ HINT COMMANDS #################
    ################################################

    @commands.group(name="hint", help="View and use hints for your registered slots", invoke_without_command=True)  # type: ignore[arg-type]
    async def hint(self, ctx: BotContext) -> None:
        raise CommandNotFound("Must specify a sub-command for !hint")

    @hint.command(name="points", help="Show hint points (for the given slot if specified)")  # type: ignore[arg-type]
    async def hint_points(self, ctx: BotContext, slot: Optional[str] = None) -> None:
        pass

    @hint.command(name="use", help="Use a hint for the given item; must specify slot if multi-registered")  # type: ignore[arg-type]
    async def hint_use(self, ctx: BotContext, item: str, slot: Optional[str] = None) -> None:
        pass

    @hint.command(name="list", help="List unfound hints (for the given slot if specified)")  # type: ignore[arg-type]
    async def hint_list(self, ctx: BotContext, slot: Optional[str] = None) -> None:
        pass

    @hint.command(name="listall", help="List all hints (for the given slot if specified)")  # type: ignore[arg-type]
    async def hint_listall(self, ctx: BotContext, slot: Optional[str] = None) -> None:
        pass

    ################################################
    ############ SUBSCRIPTION COMMANDS #############
    ################################################

    @commands.group(name="subscribe", help="Manage item subscriptions, which will notify you on item send", invoke_without_command=True)  # type: ignore[arg-type]
    async def subscribe(self, ctx: BotContext) -> None:
        raise CommandNotFound("Must specify a sub-command for !subscribe")

    @subscribe.command(name="add", help="Subscribes you for the given item; must specify slot if multi-registered")  # type: ignore[arg-type]
    async def subscribe_add(self, ctx: BotContext, item: str, slot: Optional[str] = None) -> None:
        pass

    @subscribe.command(name="remove", help="Unsubscribes you from the given item (for the given slot if specified)")  # type: ignore[arg-type]
    async def subscribe_remove(self, ctx: BotContext, item: str, slot: Optional[str] = None) -> None:
        pass

    @subscribe.command(name="list", help="Lists your active item subscriptions (for the given slot if specified)")  # type: ignore[arg-type]
    async def subscribe_list(self, ctx: BotContext, slot: Optional[str] = None) -> None:
        pass

    @subscribe.command(name="clear", help="Unsubscribes you from all items (for the given slot if specified)")  # type: ignore[arg-type]
    async def subscribe_clear(self, ctx: BotContext, slot: Optional[str] = None) -> None:
        pass

    ################################################
    ################ STATS COMMANDS ################
    ################################################

    @commands.command(name="checks", help="Outputs data on completed/total checks per slot")
    async def checks(self, ctx: BotContext, mode: Literal["list", "graph"]) -> None:
        pass

    @commands.command(name="deaths", help="Outputs data on death links triggered per slot")
    async def deaths(self, ctx: BotContext, mode: Literal["list", "graph"]) -> None:
        pass


class HelpCommand(commands.DefaultHelpCommand):
    pass


class ADOSBot(commands.Bot):

    def __init__(self, config: ADOSConfig):
        intents = discord.Intents.default()
        intents.message_content = True
        help_command = HelpCommand()  # type: ignore[no-untyped-call]
        super().__init__(command_prefix="!", intents=intents, help_command=help_command)

        bot_commands = ADOSCommands()
        help_command.cog = bot_commands  # Need to set the cog so "help" is grouped with other commands
        self.add_cog(bot_commands)

        self._config = config

    def run(self) -> None:
        _log.info("Starting ArchipelaDOS bot with configuration: %s", self._config.model_dump_json())
        super().run(self._config.discord_token)
        _log.info("Stopping ArchipelaDOS bot")

    async def on_command_error(self, context: BotContext, exception: CommandError) -> None:
        if isinstance(exception, (CommandNotFound, ConversionError, UserInputError)):
            _log.info("Invalid user command '%s': %s", context.message.content, exception)
            await _send_failure(context, f"I didn't understand that command: {exception}")
        else:
            _log.warning("Error processing user command '%s': %s", context.message.content, exception)
            await _send_failure(context, f"An error occurred while processing your command: {exception}")
