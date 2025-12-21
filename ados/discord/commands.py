import random
from typing import Literal, Optional

from discord.ext import commands
from discord.ext.commands.errors import UserInputError

from ados.discord.utils import send_info

type BotContext = commands.context.Context[commands.Bot]


def _strip_quotes(value: Optional[str]) -> Optional[str]:
    return value.strip("'\"") if value else None


class Commands(commands.Cog, name="ArchipelaDOS"):  # pyright: ignore - pylance hates this pattern

    class _SlotFlags(commands.FlagConverter):
        slot: Optional[str] = None

        def __init__(self) -> None:
            super().__init__()
            self.slot = _strip_quotes(self.slot)

    class _SlotLevelFlags(commands.FlagConverter):
        slot: Optional[str] = None
        level: Optional[str] = None

        def __init__(self) -> None:
            super().__init__()
            self.slot = _strip_quotes(self.slot)
            self.level = _strip_quotes(self.level)

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

    @commands.command(name="hello", help="Greet the bot (it might greet you back)")
    async def hello(self, ctx: BotContext) -> None:
        await send_info(ctx, random.choice(Commands.HELLO_RESPONSES))

    ################################################
    ########### SLOT MANAGEMENT COMMANDS ###########
    ################################################

    @commands.group(name="slot", help="Manage slot registrations", invoke_without_command=True)  # type: ignore[arg-type]
    async def slot(self, ctx: BotContext) -> None:
        raise UserInputError("Must specify a sub-command for `!slot`")

    @slot.command(name="add", help="Registers you for the given slot")  # type: ignore[arg-type]
    async def slot_add(self, ctx: BotContext, slot: str) -> None:
        await send_info(ctx, f"Registered for slot '{slot}'")

    @slot.command(name="remove", help="Unregisters you from the given slot")  # type: ignore[arg-type]
    async def slot_remove(self, ctx: BotContext, slot: str) -> None:
        await send_info(ctx, f"Unregistered from slot '{slot}'")

    @slot.command(name="list", help="Lists all slots for which you are registered")  # type: ignore[arg-type]
    async def slot_list(self, ctx: BotContext) -> None:
        await send_info(ctx, "Listing all registered slots")

    @slot.command(name="clear", help="Unregisters you from all slots")  # type: ignore[arg-type]
    async def slot_clear(self, ctx: BotContext) -> None:
        await send_info(ctx, "Unregistered from all slots")

    ################################################
    ######### NOTIFICATION REPLAY COMMANDS #########
    ################################################

    @commands.group(name="replay", help="View previously received items for your registered slots", invoke_without_command=True)  # type: ignore[arg-type]
    async def replay(self, ctx: BotContext) -> None:
        raise UserInputError("Must specify a sub-command for `!replay`")

    @replay.command(name="recent", help="Replay items received since last call (can filter by slot/item level)")  # type: ignore[arg-type]
    async def replay_recent(self, ctx: BotContext, *, flags: _SlotLevelFlags) -> None:
        await send_info(ctx, f"Replaying recent items; {flags}")

    @replay.command(name="all", help="Replay all items recieved since game start (can filter by slot/item level)")  # type: ignore[arg-type]
    async def replay_all(self, ctx: BotContext, *, flags: _SlotLevelFlags) -> None:
        await send_info(ctx, f"Replaying all items; {flags}")

    @commands.command(name="ketchmeup", help="Alias of '!replay recent'")
    async def ketchmeup(self, ctx: BotContext, *, flags: _SlotLevelFlags) -> None:
        await self.replay_recent(ctx, flags=flags)  # type: ignore[arg-type]

    ################################################
    ################ HINT COMMANDS #################
    ################################################

    @commands.group(name="hint", help="View and use hints for your registered slots", invoke_without_command=True)  # type: ignore[arg-type]
    async def hint(self, ctx: BotContext) -> None:
        raise UserInputError("Must specify a sub-command for `!hint`")

    @hint.command(name="points", help="Show hint points (can filter by slot)")  # type: ignore[arg-type]
    async def hint_points(self, ctx: BotContext, *, flags: _SlotFlags) -> None:
        await send_info(ctx, f"Showing hint points; {flags}")

    @hint.command(name="use", help="Use a hint for the given item (can filter by slot, and must if multi-registered)")  # type: ignore[arg-type]
    async def hint_use(self, ctx: BotContext, item: str, *, flags: _SlotFlags) -> None:
        await send_info(ctx, f"Using hint for item '{item}'; {flags}")

    @hint.command(name="list", help="List unfound hints (can filter by slot)")  # type: ignore[arg-type]
    async def hint_list(self, ctx: BotContext, *, flags: _SlotFlags) -> None:
        await send_info(ctx, f"Listing unfound hints; {flags}")

    @hint.command(name="listall", help="List all hints (can filter by slot)")  # type: ignore[arg-type]
    async def hint_listall(self, ctx: BotContext, *, flags: _SlotFlags) -> None:
        await send_info(ctx, f"Listing all hints; {flags}")

    ################################################
    ############ SUBSCRIPTION COMMANDS #############
    ################################################

    @commands.group(name="subscribe", help="Manage item subscriptions, which will notify you on item send", invoke_without_command=True)  # type: ignore[arg-type]
    async def subscribe(self, ctx: BotContext) -> None:
        raise UserInputError("Must specify a sub-command for `!subscribe`")

    @subscribe.command(name="add", help="Subscribes you for the given item (can filter by slot, and must if multi-registered)")  # type: ignore[arg-type]
    async def subscribe_add(self, ctx: BotContext, item: str, *, flags: _SlotFlags) -> None:
        await send_info(ctx, f"Subscribed to item '{item}'; {flags}")

    @subscribe.command(name="remove", help="Unsubscribes you from the given item (can filter by slot)")  # type: ignore[arg-type]
    async def subscribe_remove(self, ctx: BotContext, item: str, *, flags: _SlotFlags) -> None:
        await send_info(ctx, f"Unsubscribed from item '{item}'; {flags}")

    @subscribe.command(name="list", help="Lists your active item subscriptions (can filter by slot)")  # type: ignore[arg-type]
    async def subscribe_list(self, ctx: BotContext, *, flags: _SlotFlags) -> None:
        await send_info(ctx, f"Listing subscriptions; {flags}")

    @subscribe.command(name="clear", help="Unsubscribes you from all items (can filter by slot)")  # type: ignore[arg-type]
    async def subscribe_clear(self, ctx: BotContext, *, flags: _SlotFlags) -> None:
        await send_info(ctx, f"Clearing all subscriptions; {flags}")

    ################################################
    ################ STATS COMMANDS ################
    ################################################

    @commands.command(name="checks", help="Outputs data on completed/total checks per slot")
    async def checks(self, ctx: BotContext, mode: Literal["list", "graph"]) -> None:
        await send_info(ctx, f"Generating checks data in mode '{mode}'")

    @commands.command(name="deaths", help="Outputs data on death links triggered per slot")
    async def deaths(self, ctx: BotContext, mode: Literal["list", "graph"]) -> None:
        await send_info(ctx, f"Generating deaths data in mode '{mode}'")
