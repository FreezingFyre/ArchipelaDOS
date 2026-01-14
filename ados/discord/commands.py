import random
from typing import Literal, Optional

from discord.ext import commands
from discord.ext.commands.errors import UserInputError

from ados.arch.socket import SocketClient
from ados.arch.web import WebClient
from ados.common import (
    ADOSError,
    ItemCategoryFilter,
    SentItemInfo,
    SlotInfo,
)
from ados.discord.common import (
    COMMAND_PREFIX,
    BotContext,
    send_message,
    send_success,
    send_table,
)
from ados.state import GlobalState


def _strip_quotes(value: str) -> str:
    return value.strip("'\"")


class SlotInfoArg(commands.Converter[SlotInfo]):
    async def convert(self, ctx: BotContext, argument: str) -> SlotInfo:
        try:
            assert isinstance(ctx.cog, Commands)
            return ctx.cog._state.resolve_slot(_strip_quotes(argument))  # pylint: disable = protected-access
        except ADOSError as ex:
            raise UserInputError(str(ex)) from ex


class StringArg(commands.Converter[str]):
    async def convert(self, ctx: BotContext, argument: str) -> str:  # pylint: disable = unused-argument
        return _strip_quotes(argument)


class Commands(commands.Cog):  # pyright: ignore - pylance hates this pattern

    def __init__(self, web: WebClient, socket: SocketClient, state: GlobalState):
        super().__init__()
        self._web = web
        self._socket = socket
        self._state = state

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

    @commands.command(name="hello", help="Greet the bot (it might greet you back)", ignore_extra=False)
    async def hello(self, ctx: BotContext) -> None:
        await send_message(ctx, random.choice(Commands.GREETINGS))

    @commands.command(name="dmme", help="Trigger the bot to send you a direct message", ignore_extra=False)
    async def dmme(self, ctx: BotContext) -> None:
        await ctx.message.author.send(random.choice(Commands.GREETINGS))
        await send_success(ctx, "Direct message sent")

    @commands.command(name="threadme", help="Trigger the bot to send you a message in a new thread", ignore_extra=False)
    async def threadme(self, ctx: BotContext) -> None:
        await send_message(ctx, random.choice(Commands.GREETINGS), reply=True)

    @commands.command(name="refresh", help="Refresh the room on archipelago.gg", ignore_extra=False)
    async def refresh(self, ctx: BotContext) -> None:
        await self._web.refresh()
        await self._socket.connect(self._web.server_url)
        await send_success(ctx, f"Refreshed room data from <{self._web.room_url}>")

    @commands.command(name="info", help="Get information about the Archipelago room", ignore_extra=False)
    async def info(self, ctx: BotContext) -> None:
        port = self._web.server_url.split(":")[-1]
        slot_names = [f"`{slot}`" for slot in self._state.all_slots()]
        slot_list = ", ".join(slot_name for slot_name in slot_names)
        message = (
            f"Room Information:\n"
            f"- Port: {port}\n"
            f"- Room URL: <{self._web.room_url}>\n"
            f"- Tracker URL: <{self._web.tracker_url}>\n"
            f"- Available Slots: {slot_list}"
        )
        await send_message(ctx, message)

    ################################################
    ########### SLOT MANAGEMENT COMMANDS ###########
    ################################################

    class SlotFlags(commands.FlagConverter):
        slot: SlotInfoArg = commands.flag(positional=True)

    @commands.group(name="slot", help="Manage slot registrations", invoke_without_command=True)  # type: ignore[arg-type]
    async def slot(self, ctx: BotContext) -> None:
        raise UserInputError(f"Must specify a sub-command for `{COMMAND_PREFIX}slot`")

    @slot.command(name="add", help="Registers you for the given slot", ignore_extra=False)  # type: ignore[arg-type]
    async def slot_add(self, ctx: BotContext, *, flags: SlotFlags) -> None:
        self._state.add_user_slot(ctx.author.id, flags.slot)
        await send_success(ctx, f"You have been registered for slot `{flags.slot}`")

    @slot.command(name="remove", help="Unregisters you from the given slot", ignore_extra=False)  # type: ignore[arg-type]
    async def slot_remove(self, ctx: BotContext, *, flags: SlotFlags) -> None:
        self._state.remove_user_slot(ctx.author.id, flags.slot)
        await send_success(ctx, f"You have been unregistered from slot `{flags.slot}`")

    @slot.command(name="list", help="Lists all slots for which you are registered", ignore_extra=False)  # type: ignore[arg-type]
    async def slot_list(self, ctx: BotContext) -> None:
        slots = self._state.get_user_slots(ctx.author.id)
        if not slots:
            await send_message(ctx, "You are not registered for any slots")
        else:
            slot_names = [str(slot) for slot in slots]
            slot_list = ", ".join(f"`{slot_name}`" for slot_name in sorted(slot_names))
            await send_message(ctx, f"You are registered for the following slots: {slot_list}")

    @slot.command(name="clear", help="Unregisters you from all slots", ignore_extra=False)  # type: ignore[arg-type]
    async def slot_clear(self, ctx: BotContext) -> None:
        self._state.clear_user_slots(ctx.author.id)
        await send_success(ctx, "You have been unregistered from all slots")

    ################################################
    ######### NOTIFICATION REPLAY COMMANDS #########
    ################################################

    class ReplayFlags(commands.FlagConverter):
        slot: Optional[SlotInfoArg] = None
        filter: ItemCategoryFilter = ItemCategoryFilter.USEFUL

    @commands.group(name="replay", help="View previously received items for your registered slots", invoke_without_command=True)  # type: ignore[arg-type]
    async def replay(self, ctx: BotContext) -> None:
        raise UserInputError(f"Must specify a sub-command for `{COMMAND_PREFIX}replay`")

    @replay.command(name="new", help="Replay items received since last call (can filter by slot/item level)", ignore_extra=False)  # type: ignore[arg-type]
    async def replay_new(self, ctx: BotContext, *, flags: ReplayFlags) -> None:
        slots = await self._resolve_replay_slots(ctx, flags.slot)
        slot_items: dict[SlotInfo, list[SentItemInfo]] = {}
        for slot in slots:
            items = self._state.get_new_items(ctx.author.id, slot)
            slot_items[slot] = self._filter_items(items, flags)
        await self._send_replay_items(ctx, slot_items)

    @replay.command(name="all", help="Replay all items recieved since game start (can filter by slot/item level)", ignore_extra=False)  # type: ignore[arg-type]
    async def replay_all(self, ctx: BotContext, *, flags: ReplayFlags) -> None:
        slots = await self._resolve_replay_slots(ctx, flags.slot)
        slot_items: dict[SlotInfo, list[SentItemInfo]] = {}
        for slot in slots:
            items = self._state.get_all_items(slot)
            slot_items[slot] = self._filter_items(items, flags)
        await self._send_replay_items(ctx, slot_items)

    @commands.command(name="ketchmeup", help=f"Alias of '{COMMAND_PREFIX}replay new'", ignore_extra=False)
    async def ketchmeup(self, ctx: BotContext, *, flags: ReplayFlags) -> None:
        await self.replay_new(ctx, flags=flags)  # type: ignore[arg-type]

    def _filter_items(self, items: list[SentItemInfo], flags: ReplayFlags) -> list[SentItemInfo]:
        return [item for item in items if flags.filter.check(item.category)]

    async def _resolve_replay_slots(self, ctx: BotContext, flag_slot: Optional[SlotInfoArg]) -> list[SlotInfo]:
        if flag_slot is not None:
            assert isinstance(flag_slot, SlotInfo)
            slots: list[SlotInfo] = [flag_slot]
        else:
            slots = self._state.get_user_slots(ctx.author.id)
        if not slots:
            await send_message(ctx, "You are not registered for any slots", reply=True)
        return slots

    async def _send_replay_items(self, ctx: BotContext, slot_items: dict[SlotInfo, list[SentItemInfo]]) -> None:
        for slot, items in slot_items.items():
            if not items:
                await send_message(ctx, f"No items to replay for slot `{slot}`", reply=True)
                continue

            table: dict[str, list[str]] = {"You": [], "Item": [], "Sender": [], "Location": []}
            for item in items:
                table["You"].append(str(slot))
                table["Item"].append(item.item_name)
                table["Sender"].append(self._state.resolve_slot(item.from_slot_id).name)
                table["Location"].append(item.location_name)
            await send_table(ctx, table, reply=True)

    ################################################
    ################ HINT COMMANDS #################
    ################################################

    class HintFlagsItem(commands.FlagConverter):
        item: StringArg = commands.flag(positional=True)
        slot: Optional[SlotInfoArg] = None

    class HintFlagsNoItem(commands.FlagConverter):
        slot: Optional[SlotInfoArg] = None

    @commands.group(name="hint", help="View and use hints for your registered slots", invoke_without_command=True)  # type: ignore[arg-type]
    async def hint(self, ctx: BotContext) -> None:
        raise UserInputError(f"Must specify a sub-command for `{COMMAND_PREFIX}hint`")

    @hint.command(name="points", help="Show hint points (can filter by slot)", ignore_extra=False)  # type: ignore[arg-type]
    async def hint_points(self, ctx: BotContext, *, flags: HintFlagsNoItem) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement

    @hint.command(name="use", help="Use a hint for the given item (can filter by slot, and must if multi-registered)", ignore_extra=False)  # type: ignore[arg-type]
    async def hint_use(self, ctx: BotContext, *, flags: HintFlagsItem) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement

    @hint.command(name="list", help="List unfound hints (can filter by slot)", ignore_extra=False)  # type: ignore[arg-type]
    async def hint_list(self, ctx: BotContext, *, flags: HintFlagsNoItem) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement

    @hint.command(name="listall", help="List all hints (can filter by slot)", ignore_extra=False)  # type: ignore[arg-type]
    async def hint_listall(self, ctx: BotContext, *, flags: HintFlagsNoItem) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement

    ################################################
    ############ SUBSCRIPTION COMMANDS #############
    ################################################

    class SubscribeFlagsItem(commands.FlagConverter):
        item: StringArg = commands.flag(positional=True)
        slot: Optional[SlotInfoArg] = None

    class SubscribeFlagsNoItem(commands.FlagConverter):
        slot: Optional[SlotInfoArg] = None

    @commands.group(name="subscribe", help="Manage item subscriptions, which will notify you on item send", invoke_without_command=True)  # type: ignore[arg-type]
    async def subscribe(self, ctx: BotContext) -> None:
        raise UserInputError(f"Must specify a sub-command for `{COMMAND_PREFIX}subscribe`")

    @subscribe.command(name="add", help="Subscribes you for the given item (can filter by slot, and must if multi-registered)", ignore_extra=False)  # type: ignore[arg-type]
    async def subscribe_add(self, ctx: BotContext, *, flags: SubscribeFlagsItem) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement

    @subscribe.command(name="remove", help="Unsubscribes you from the given item (can filter by slot)", ignore_extra=False)  # type: ignore[arg-type]
    async def subscribe_remove(self, ctx: BotContext, *, flags: SubscribeFlagsItem) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement

    @subscribe.command(name="list", help="Lists your active item subscriptions (can filter by slot)", ignore_extra=False)  # type: ignore[arg-type]
    async def subscribe_list(self, ctx: BotContext, *, flags: SubscribeFlagsNoItem) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement

    @subscribe.command(name="clear", help="Unsubscribes you from all items (can filter by slot)", ignore_extra=False)  # type: ignore[arg-type]
    async def subscribe_clear(self, ctx: BotContext, *, flags: SubscribeFlagsNoItem) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement

    ################################################
    ################ STATS COMMANDS ################
    ################################################

    @commands.command(name="checks", help="Outputs data on completed/total checks per slot", ignore_extra=False)
    async def checks(self, ctx: BotContext, mode: Literal["list", "graph"]) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement

    @commands.command(name="deaths", help="Outputs data on death links triggered per slot", ignore_extra=False)
    async def deaths(self, ctx: BotContext, mode: Literal["list", "graph"]) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement
