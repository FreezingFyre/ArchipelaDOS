import io
import random
from enum import Enum
from typing import Optional, cast

import discord
import matplotlib.pyplot as plt
from discord.ext import commands
from discord.ext.commands.errors import UserInputError

from ados.arch.socket import SocketClient
from ados.arch.web import WebClient
from ados.common import (
    ADOSError,
    ItemCategoryFilter,
    SentItemInfo,
    SlotInfo,
    join_objects,
)
from ados.discord.common import (
    COMMAND_PREFIX,
    BotContext,
    send_message,
    send_success,
    send_table,
)
from ados.state import GlobalState, SubscriptionType


def _strip_quotes(value: str) -> str:
    return value.strip("'\"")


class StatsOutputMode(str, Enum):
    LIST = "list"
    TABLE = "table"
    GRAPH = "graph"


class SlotInfoArg(commands.Converter[SlotInfo]):
    async def convert(self, ctx: BotContext, argument: str) -> SlotInfo:
        try:
            assert isinstance(ctx.cog, Commands)
            return ctx.cog._state.resolve_slot(_strip_quotes(argument))  # pylint: disable = protected-access
        except ADOSError as ex:
            raise UserInputError(str(ex)) from ex


class StringArg(commands.Converter[str]):
    async def convert(self, ctx: BotContext, argument: str) -> str:  # pylint: disable = unused-argument
        argument = _strip_quotes(argument)
        if not argument:
            raise UserInputError("Argument cannot be empty")
        return argument


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
        await self._socket.connect(self._web.server_url, fetch_data=False)
        await send_success(ctx, f"Refreshed room data from <{self._web.room_url}>")

    @commands.command(name="info", help="Get information about the Archipelago room", ignore_extra=False)
    async def info(self, ctx: BotContext) -> None:
        port = self._web.server_url.split(":")[-1]
        slot_names_joined = join_objects(self._state.all_slots())
        message = [
            "Room information:",
            f"- Port: {port}",
            f"- Room URL: <{self._web.room_url}>",
            f"- Tracker URL: <{self._web.tracker_url}>",
            f"- Available slots: {slot_names_joined}",
        ]
        await send_message(ctx, "\n".join(message))

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
            slot_names_joined = join_objects(slots)
            await send_message(ctx, f"You are registered for the following slots: {slot_names_joined}")

    @slot.command(name="clear", help="Clears your registration for all slots", ignore_extra=False)  # type: ignore[arg-type]
    async def slot_clear(self, ctx: BotContext) -> None:
        self._state.clear_user_slots(ctx.author.id)
        await send_success(ctx, "You have been unregistered from all slots")

    @slot.command(name="info", help="Get information about a specific slot", ignore_extra=False)  # type: ignore[arg-type]
    async def slot_info(self, ctx: BotContext, *, flags: SlotFlags) -> None:
        game = cast(SlotInfo, flags.slot).game
        groups_joined = join_objects(self._state.all_groups(game))
        message = [
            f"Slot information for `{flags.slot}`:",
            f"- Game: `{game}`",
            f"- Item groups: {groups_joined}",
        ]
        await send_message(ctx, "\n".join(message))

    ################################################
    ######### NOTIFICATION REPLAY COMMANDS #########
    ################################################

    class ReplayFlags(commands.FlagConverter):
        filter: ItemCategoryFilter = commands.flag(positional=True, default=ItemCategoryFilter.USEFUL)
        slot: Optional[SlotInfoArg] = None

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

    @replay.command(name="full", help="Replay all items recieved since game start (can filter by slot/item level)", ignore_extra=False)  # type: ignore[arg-type]
    async def replay_full(self, ctx: BotContext, *, flags: ReplayFlags) -> None:
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

    class HintFlags(commands.FlagConverter):
        slot: Optional[SlotInfoArg] = None

    class HintFlagsItem(commands.FlagConverter):
        item: StringArg = commands.flag(positional=True)
        slot: Optional[SlotInfoArg] = None

    @commands.group(name="hint", help="View and use hints for your registered slots", invoke_without_command=True)  # type: ignore[arg-type]
    async def hint(self, ctx: BotContext) -> None:
        raise UserInputError(f"Must specify a sub-command for `{COMMAND_PREFIX}hint`")

    @hint.command(name="points", help="Show hint points (can filter by slot)", ignore_extra=False)  # type: ignore[arg-type]
    async def hint_points(self, ctx: BotContext, *, flags: HintFlags) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement

    @hint.command(name="use", help="Use a hint for the given item (can filter by slot, and must if multi-registered)", ignore_extra=False)  # type: ignore[arg-type]
    async def hint_use(self, ctx: BotContext, *, flags: HintFlagsItem) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement

    @hint.command(name="list", help="List hints (can filter by slot/found status)", ignore_extra=False)  # type: ignore[arg-type]
    async def hint_list(self, ctx: BotContext, *, flags: HintFlags) -> None:
        raise ADOSError("Not yet implemented")  # TODO: Implement

    ################################################
    ############ SUBSCRIPTION COMMANDS #############
    ################################################

    class SubscribeFlags(commands.FlagConverter):
        slot: Optional[SlotInfoArg] = None

    class SubscribeFlagsItem(commands.FlagConverter):
        item: StringArg = commands.flag(positional=True)
        slot: Optional[SlotInfoArg] = None

    class SubscribeFlagsGroup(commands.FlagConverter):
        group: StringArg = commands.flag(positional=True)
        slot: Optional[SlotInfoArg] = None

    class SubscribeFlagsValue(commands.FlagConverter):
        value: StringArg = commands.flag(positional=True)
        slot: Optional[SlotInfoArg] = None

    @commands.group(name="subscribe", help="Manage item subscriptions, which will notify you on item send", invoke_without_command=True)  # type: ignore[arg-type]
    async def subscribe(self, ctx: BotContext) -> None:
        raise UserInputError(f"Must specify a sub-command for `{COMMAND_PREFIX}subscribe`")

    @subscribe.command(name="item", help="Subscribes you for the given item (can filter by slot, and must if multi-registered)", ignore_extra=False)  # type: ignore[arg-type]
    async def subscribe_item(self, ctx: BotContext, *, flags: SubscribeFlagsItem) -> None:
        slot = self._resolve_subscribe_slot(ctx, flags.slot)
        item = self._state.resolve_item(slot.game, cast(str, flags.item))
        self._state.add_user_subscription(ctx.author.id, slot, SubscriptionType.ITEM, item.name)
        await send_success(ctx, f"You have subscribed to item `{item.name}` in slot `{slot}`")

    @subscribe.command(name="group", help="Subscribes you for the given item group (can filter by slot, and must if multi-registered)", ignore_extra=False)  # type: ignore[arg-type]
    async def subscribe_group(self, ctx: BotContext, *, flags: SubscribeFlagsGroup) -> None:
        slot = self._resolve_subscribe_slot(ctx, flags.slot)
        group = self._state.resolve_group(slot.game, cast(str, flags.group))
        self._state.add_user_subscription(ctx.author.id, slot, SubscriptionType.GROUP, group)
        await send_success(ctx, f"You have subscribed to item group `{group}` in slot `{slot}`")

    @subscribe.command(name="remove", help="Unsubscribes you from items/groups containing the given text (can filter by slot)", ignore_extra=False)  # type: ignore[arg-type]
    async def subscribe_remove(self, ctx: BotContext, *, flags: SubscribeFlagsValue) -> None:
        self._state.remove_user_subscription(ctx.author.id, flags.slot, flags.value)
        await send_success(ctx, f"You have removed items/group subscriptions matching `{flags.value}`")

    @subscribe.command(name="list", help="Lists your active item/group subscriptions (can filter by slot)", ignore_extra=False)  # type: ignore[arg-type]
    async def subscribe_list(self, ctx: BotContext, *, flags: SubscribeFlags) -> None:
        slot_subscriptions = self._state.get_user_subscriptions(ctx.author.id, cast(Optional[SlotInfo], flags.slot))
        if not slot_subscriptions:
            await send_message(ctx, "You have no active item/group subscriptions")
        else:
            table: dict[str, list[str]] = {"Slot": [], "Type": [], "Value": []}
            for slot, subscriptions in sorted(slot_subscriptions.items(), key=lambda pair: pair[0].name):
                for subscription in subscriptions:
                    table["Slot"].append(str(slot))
                    table["Type"].append(subscription.type.value)
                    table["Value"].append(subscription.value)
            await send_table(ctx, table)

    @subscribe.command(name="clear", help="Clears all your subscriptions (can filter by slot)", ignore_extra=False)  # type: ignore[arg-type]
    async def subscribe_clear(self, ctx: BotContext, *, flags: SubscribeFlags) -> None:
        self._state.remove_user_subscription(ctx.author.id, flags.slot, "")
        await send_success(ctx, "You have cleared your item/group subscriptions")

    def _resolve_subscribe_slot(self, ctx: BotContext, flag_slot: Optional[SlotInfoArg]) -> SlotInfo:
        if flag_slot is not None:
            assert isinstance(flag_slot, SlotInfo)
            return flag_slot

        slots = self._state.get_user_slots(ctx.author.id)
        if len(slots) == 0:
            raise ADOSError("You are not registered for any slots; either register or specify a slot")
        if len(slots) > 1:
            raise ADOSError("You are registered for multiple slots; please specify a slot")
        return slots[0]

    ################################################
    ################ STATS COMMANDS ################
    ################################################

    @commands.command(name="checks", help="Outputs data on completed/total checks per slot", ignore_extra=False)
    async def checks(self, ctx: BotContext, mode: StatsOutputMode) -> None:
        check_counts = {
            self._state.resolve_slot(slot_id): counts
            for slot_id, counts in (await self._web.fetch_slot_check_counts()).items()
        }
        check_counts = dict(sorted(check_counts.items(), key=lambda pair: pair[0].name))

        if mode == StatsOutputMode.GRAPH:
            await self._send_graph(
                ctx, {slot: counts.percent for slot, counts in check_counts.items()}, "Completion Percentage"
            )
        else:
            table: dict[str, list[str]] = {"Slot": [], "Found": [], "Total": [], "Percent": []}
            for slot, counts in check_counts.items():
                table["Slot"].append(str(slot))
                table["Found"].append(str(counts.found))
                table["Total"].append(str(counts.total))
                table["Percent"].append(f"{counts.percent}%")
            await send_table(ctx, table, right_just=True)

    @commands.command(name="deaths", help="Outputs data on death links triggered per slot", ignore_extra=False)
    async def deaths(self, ctx: BotContext, mode: StatsOutputMode) -> None:
        death_counts = dict(sorted(self._state.death_counts().items(), key=lambda pair: pair[0].name))
        if not death_counts:
            await send_message(ctx, "No death links have been triggered yet")
            return

        if mode == StatsOutputMode.GRAPH:
            await self._send_graph(ctx, death_counts, "Death Counts")
        else:
            table: dict[str, list[str]] = {"Slot": [], "Deaths": []}
            for slot, count in death_counts.items():
                table["Slot"].append(str(slot))
                table["Deaths"].append(str(count))
            await send_table(ctx, table, right_just=True)

    async def _send_graph(self, ctx: BotContext, data: dict[SlotInfo, int], title: str) -> None:
        plt.figure(figsize=(max(8, len(data) * 0.5), 6))
        bars = plt.bar([str(slot) for slot in data.keys()], list(data.values()))
        plt.bar_label(bars)
        plt.title(title)
        plt.xlabel("Slot")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        image_buffer = io.BytesIO()
        plt.savefig(image_buffer, dpi=200, format="png")
        image_buffer.seek(0)
        plt.close()

        await ctx.send(file=discord.File(fp=image_buffer, filename="stats.png"))
