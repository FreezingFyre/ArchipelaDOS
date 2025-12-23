import random
from typing import Literal, Optional

from discord.ext import commands
from discord.ext.commands.context import Context
from discord.ext.commands.errors import UserInputError

from ados.discord.utils import send_message, send_success
from ados.state import ADOSState

type BotContext = Context[commands.Bot]


def _strip_quotes(value: Optional[str]) -> Optional[str]:
    return value.strip("'\"") if value else None


class Commands(commands.Cog):  # pyright: ignore - pylance hates this pattern

    def __init__(self, state: ADOSState):
        super().__init__()
        self._state = state

    class SlotFlags(commands.FlagConverter):
        slot: Optional[str] = None

        def __init__(self) -> None:
            super().__init__()
            self.slot = _strip_quotes(self.slot)

    class SlotLevelFlags(commands.FlagConverter):
        slot: Optional[str] = None
        level: Optional[str] = None

        def __init__(self) -> None:
            super().__init__()
            self.slot = _strip_quotes(self.slot)
            self.level = _strip_quotes(self.level)

    ################################################
    ################ BASIC COMMANDS ################
    ################################################

    GREETINGS = [
        "Annyeonghaseyo",
        "Bonjour",
        "Ciao",
        "Dia duit",
        "Dzień dobry",
        "Guten Tag",
        "Hallo",
        "Hej",
        "Hello",
        "Hola",
        "Kon'nichiwa",
        "Marhaba",
        "Namaste",
        "Nǐ hǎo",
        "Olá",
        "Salve",
        "Shalom",
        "Xin chào",
        "Yassas",
        "Zdravstvuyte",
    ]

    @commands.command(name="hello", help="Greet the bot (it might greet you back)")
    async def hello(self, ctx: BotContext) -> None:
        await send_message(ctx, random.choice(Commands.GREETINGS))

    @commands.command(name="dmme", help="Trigger the bot to send you a direct message")
    async def dmme(self, ctx: BotContext) -> None:
        await ctx.message.author.send(random.choice(Commands.GREETINGS))
        await send_success(ctx, "Direct message sent")

    @commands.command(name="threadme", help="Trigger the bot to send you a message in a new thread")
    async def threadme(self, ctx: BotContext) -> None:
        await send_message(ctx, random.choice(Commands.GREETINGS), reply=True)

    @commands.command(name="refresh", help="Refresh the room on archipelago.gg")
    async def refresh(self, ctx: BotContext) -> None:
        pass  # TODO: Implement

    ################################################
    ########### SLOT MANAGEMENT COMMANDS ###########
    ################################################

    @commands.group(name="slot", help="Manage slot registrations", invoke_without_command=True)  # type: ignore[arg-type]
    async def slot(self, ctx: BotContext) -> None:
        raise UserInputError("Must specify a sub-command for `!slot`")

    @slot.command(name="add", help="Registers you for the given slot")  # type: ignore[arg-type]
    async def slot_add(self, ctx: BotContext, slot: str) -> None:
        await self._state.add_user_slot(ctx.author.id, slot)
        await send_success(ctx, f"You have been registered for slot `{slot}`")

    @slot.command(name="remove", help="Unregisters you from the given slot")  # type: ignore[arg-type]
    async def slot_remove(self, ctx: BotContext, slot: str) -> None:
        await self._state.remove_user_slot(ctx.author.id, slot)
        await send_success(ctx, f"You have been unregistered from slot `{slot}`")

    @slot.command(name="list", help="Lists all slots for which you are registered")  # type: ignore[arg-type]
    async def slot_list(self, ctx: BotContext) -> None:
        user_slots = await self._state.user_slots(ctx.author.id)
        if not user_slots:
            await send_message(ctx, "You are not registered for any slots")
        else:
            slot_list = ", ".join(f"`{slot}`" for slot in sorted(user_slots))
            await send_message(ctx, f"You are registered for the following slots: {slot_list}")

    @slot.command(name="clear", help="Unregisters you from all slots")  # type: ignore[arg-type]
    async def slot_clear(self, ctx: BotContext) -> None:
        await self._state.clear_user_slots(ctx.author.id)
        await send_success(ctx, "You have been unregistered from all slots")

    ################################################
    ######### NOTIFICATION REPLAY COMMANDS #########
    ################################################

    @commands.group(name="replay", help="View previously received items for your registered slots", invoke_without_command=True)  # type: ignore[arg-type]
    async def replay(self, ctx: BotContext) -> None:
        raise UserInputError("Must specify a sub-command for `!replay`")

    @replay.command(name="recent", help="Replay items received since last call (can filter by slot/item level)")  # type: ignore[arg-type]
    async def replay_recent(self, ctx: BotContext, *, flags: SlotLevelFlags) -> None:
        pass  # TODO: Implement

    @replay.command(name="all", help="Replay all items recieved since game start (can filter by slot/item level)")  # type: ignore[arg-type]
    async def replay_all(self, ctx: BotContext, *, flags: SlotLevelFlags) -> None:
        pass  # TODO: Implement

    @commands.command(name="ketchmeup", help="Alias of '!replay recent'")
    async def ketchmeup(self, ctx: BotContext, *, flags: SlotLevelFlags) -> None:
        await self.replay_recent(ctx, flags=flags)  # type: ignore[arg-type]

    ################################################
    ################ HINT COMMANDS #################
    ################################################

    @commands.group(name="hint", help="View and use hints for your registered slots", invoke_without_command=True)  # type: ignore[arg-type]
    async def hint(self, ctx: BotContext) -> None:
        raise UserInputError("Must specify a sub-command for `!hint`")

    @hint.command(name="points", help="Show hint points (can filter by slot)")  # type: ignore[arg-type]
    async def hint_points(self, ctx: BotContext, *, flags: SlotFlags) -> None:
        pass  # TODO: Implement

    @hint.command(name="use", help="Use a hint for the given item (can filter by slot, and must if multi-registered)")  # type: ignore[arg-type]
    async def hint_use(self, ctx: BotContext, item: str, *, flags: SlotFlags) -> None:
        pass  # TODO: Implement

    @hint.command(name="list", help="List unfound hints (can filter by slot)")  # type: ignore[arg-type]
    async def hint_list(self, ctx: BotContext, *, flags: SlotFlags) -> None:
        pass  # TODO: Implement

    @hint.command(name="listall", help="List all hints (can filter by slot)")  # type: ignore[arg-type]
    async def hint_listall(self, ctx: BotContext, *, flags: SlotFlags) -> None:
        pass  # TODO: Implement

    ################################################
    ############ SUBSCRIPTION COMMANDS #############
    ################################################

    @commands.group(name="subscribe", help="Manage item subscriptions, which will notify you on item send", invoke_without_command=True)  # type: ignore[arg-type]
    async def subscribe(self, ctx: BotContext) -> None:
        raise UserInputError("Must specify a sub-command for `!subscribe`")

    @subscribe.command(name="add", help="Subscribes you for the given item (can filter by slot, and must if multi-registered)")  # type: ignore[arg-type]
    async def subscribe_add(self, ctx: BotContext, item: str, *, flags: SlotFlags) -> None:
        pass  # TODO: Implement

    @subscribe.command(name="remove", help="Unsubscribes you from the given item (can filter by slot)")  # type: ignore[arg-type]
    async def subscribe_remove(self, ctx: BotContext, item: str, *, flags: SlotFlags) -> None:
        pass  # TODO: Implement

    @subscribe.command(name="list", help="Lists your active item subscriptions (can filter by slot)")  # type: ignore[arg-type]
    async def subscribe_list(self, ctx: BotContext, *, flags: SlotFlags) -> None:
        pass  # TODO: Implement

    @subscribe.command(name="clear", help="Unsubscribes you from all items (can filter by slot)")  # type: ignore[arg-type]
    async def subscribe_clear(self, ctx: BotContext, *, flags: SlotFlags) -> None:
        pass  # TODO: Implement

    ################################################
    ################ STATS COMMANDS ################
    ################################################

    @commands.command(name="checks", help="Outputs data on completed/total checks per slot")
    async def checks(self, ctx: BotContext, mode: Literal["list", "graph"]) -> None:
        pass  # TODO: Implement

    @commands.command(name="deaths", help="Outputs data on death links triggered per slot")
    async def deaths(self, ctx: BotContext, mode: Literal["list", "graph"]) -> None:
        pass  # TODO: Implement
