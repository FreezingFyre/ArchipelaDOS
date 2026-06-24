import asyncio
import random
import re
from datetime import timedelta
from enum import Enum
from typing import Optional, cast

from discord.ext import commands
from discord.ext.commands.errors import UserInputError

from ados.arch.messages import (
    HintPointsMessage,
    HintsMessage,
    StatusMessage,
    get_hint_item_message,
    get_hint_location_message,
    get_hint_message,
    get_status_message,
)
from ados.common import (
    ADOSError,
    HintInfo,
    HintStatusFilter,
    ItemCategoryFilter,
    ItemInfo,
    LocationInfo,
    SentItemInfo,
    SlotFullStatus,
    SlotInfo,
    SubscriptionType,
    join_objects,
)
from ados.config import ADOSConfig
from ados.discord.common import (
    BotContext,
    highlight,
    send_message,
    send_success,
    send_table,
)
from ados.discord.plotting import GraphPlotter, TablePlotter
from ados.room import ActiveRoomManager
from ados.state import RoomState


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
            return ctx.cog.state.resolve_slot(_strip_quotes(argument))
        except ADOSError as ex:
            raise UserInputError(str(ex)) from ex


class StringArg(commands.Converter[str]):
    async def convert(self, ctx: BotContext, argument: str) -> str:  # pylint: disable = unused-argument
        argument = _strip_quotes(argument)
        if not argument:
            raise UserInputError("Argument cannot be empty")
        return argument


class TimeDeltaArg(commands.Converter[timedelta]):
    async def convert(self, ctx: BotContext, argument: str) -> timedelta:  # pylint: disable = unused-argument
        argument = argument.lower()

        def _extract_count(unit: str) -> float:
            match = re.search(rf"([\d\.]+)\s*{unit}", argument)
            return float(match.group(1)) if match else 0

        delta_days = _extract_count("d")
        delta_hours = _extract_count("h")
        delta_minutes = _extract_count("m")
        delta_seconds = _extract_count("s")
        return timedelta(days=delta_days, hours=delta_hours, minutes=delta_minutes, seconds=delta_seconds)


class Commands(commands.Cog):  # pyright: ignore - pylance hates this pattern

    def __init__(self, config: ADOSConfig, room_manager: ActiveRoomManager):
        super().__init__()
        self._config = config
        self._room_manager = room_manager

    @property
    def state(self) -> RoomState:
        return self._room_manager.active_room.state

    def _resolve_slots(self, ctx: BotContext, flag_slot: Optional[SlotInfoArg]) -> list[SlotInfo]:
        if flag_slot is not None:
            return [cast(SlotInfo, flag_slot)]

        slots = self.state.get_user_slots(ctx.author.id)
        if len(slots) == 0:
            raise ADOSError("You are not registered for any slots; either register or specify a slot")
        return slots

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

    ################################################
    ########### ROOM MANAGEMENT COMMANDS ###########
    ################################################

    class RoomFlags(commands.FlagConverter):
        id_or_url: str = commands.flag(positional=True)
        slot: str = "ArchipelaDOS"  # We don't resolve this with SlotInfoArg since the bot will not be connected yet.
        game: str = "Archipelago"
        password: Optional[StringArg] = None

    @commands.group(name="room", help="Set and interact with the active room", invoke_without_command=True)  # type: ignore[arg-type]
    async def room(self, ctx: BotContext) -> None:
        raise UserInputError(f"Must specify a sub-command for `{self._config.discord_command_prefix}room`")

    @room.command(name="connect", help="Connect to a new Archipelago room via room ID or socket URL", ignore_extra=False, extras={"ord": 1})  # type: ignore[arg-type]
    async def room_connect(self, ctx: BotContext, *, flags: RoomFlags) -> None:
        await self._room_manager.connect(flags.id_or_url, flags.slot, flags.game, cast(Optional[str], flags.password))
        await send_success(ctx, f"Connected to new room at <{self._room_manager.active_room.location}>")

    @room.command(name="finalize", help="Disconnect from the current Archipelago room, allowing a new connection", ignore_extra=False, extras={"ord": 2})  # type: ignore[arg-type]
    async def room_finalize(self, ctx: BotContext) -> None:
        location = self._room_manager.active_room.location
        await self._room_manager.disconnect()
        await send_success(ctx, f"Disconnected from room at <{location}>")

    @room.command(name="info", help="Get information about the Archipelago room", ignore_extra=False, extras={"ord": 3})  # type: ignore[arg-type]
    async def room_info(self, ctx: BotContext) -> None:
        slot_names_joined = join_objects(self.state.all_slots())
        message = ["Room information"]
        message.extend(f"- {key}: {value}" for key, value in self._room_manager.active_room.get_info().items())
        message.append(f"- Available slots: {slot_names_joined}")
        await send_message(ctx, "\n".join(message))

    @room.command(name="refresh", help="Refresh the room on archipelago.gg, reconnecting the bot if it got disconnected", ignore_extra=False, extras={"ord": 4})  # type: ignore[arg-type]
    async def room_refresh(self, ctx: BotContext) -> None:
        await self._room_manager.active_room.refresh()
        await send_success(ctx, f"Refreshed room at <{self._room_manager.active_room.location}>")

    ################################################
    ########### SLOT MANAGEMENT COMMANDS ###########
    ################################################

    class SlotFlags(commands.FlagConverter):
        slot: SlotInfoArg = commands.flag(positional=True)

    class SlotFlagsOptional(commands.FlagConverter):
        slot: Optional[SlotInfoArg] = commands.flag(positional=True, default=None)

    class SlotFlagsValue(commands.FlagConverter):
        value: StringArg = commands.flag(positional=True)
        slot: Optional[SlotInfoArg] = None

    @commands.group(name="slot", help="Manage slot registrations and info", invoke_without_command=True)  # type: ignore[arg-type]
    async def slot(self, ctx: BotContext) -> None:
        raise UserInputError(f"Must specify a sub-command for `{self._config.discord_command_prefix}slot`")

    @slot.command(name="add", help="Registers you for the given slot", ignore_extra=False, extras={"ord": 1})  # type: ignore[arg-type]
    async def slot_add(self, ctx: BotContext, *, flags: SlotFlags) -> None:
        self.state.add_user_slot(ctx.author.id, flags.slot)
        await send_success(ctx, f"You have been registered for slot `{flags.slot}`")

    @slot.command(name="remove", help="Unregisters you from the given slot", ignore_extra=False, extras={"ord": 2})  # type: ignore[arg-type]
    async def slot_remove(self, ctx: BotContext, *, flags: SlotFlags) -> None:
        self.state.remove_user_slot(ctx.author.id, flags.slot)
        await send_success(ctx, f"You have been unregistered from slot `{flags.slot}`")

    @slot.command(name="list", help="Lists all slots for which you are registered", ignore_extra=False, extras={"ord": 3})  # type: ignore[arg-type]
    async def slot_list(self, ctx: BotContext) -> None:
        slots = self.state.get_user_slots(ctx.author.id)
        if not slots:
            await send_message(ctx, "You are not registered for any slots")
        else:
            slot_names_joined = join_objects(slots)
            await send_message(ctx, f"You are registered for the following slots: {slot_names_joined}")

    @slot.command(name="clear", help="Clears your registration for all slots", ignore_extra=False, extras={"ord": 4})  # type: ignore[arg-type]
    async def slot_clear(self, ctx: BotContext) -> None:
        self.state.clear_user_slots(ctx.author.id)
        await send_success(ctx, "You have been unregistered from all slots")

    @slot.command(name="info", help="Get information about your registered slots (can filter by slot)", ignore_extra=False, extras={"ord": 5})  # type: ignore[arg-type]
    async def slot_info(self, ctx: BotContext, *, flags: SlotFlagsOptional) -> None:
        slots = self._resolve_slots(ctx, flags.slot)
        message = []
        for slot in slots:
            groups_joined = join_objects(self.state.all_groups(slot.game))
            message.append(
                "\n".join(
                    [
                        f"Slot information for `{slot}`:",
                        f"- Game: `{slot.game}`",
                        f"- Item groups: {groups_joined}",
                    ]
                )
            )
        await send_message(ctx, "\n\n".join(message))

    @slot.command(name="search", help="Search for items/locations in your registered slots containing the given text (can filter by slot)", ignore_extra=False, extras={"ord": 6})  # type: ignore[arg-type]
    async def slot_search(self, ctx: BotContext, *, flags: SlotFlagsValue) -> None:
        slots = self._resolve_slots(ctx, flags.slot)
        slot_items = {slot: self.state.search_items(slot.game, cast(str, flags.value)) for slot in slots}
        slot_items = {slot: items for slot, items in slot_items.items() if items}
        slot_locations = {slot: self.state.search_locations(slot.game, cast(str, flags.value)) for slot in slots}
        slot_locations = {slot: locations for slot, locations in slot_locations.items() if locations}

        if not slot_items and not slot_locations:
            await send_message(ctx, f"No items or locations found matching `{flags.value}`")
            return
        if slot_items:
            table_items: dict[str, list[str]] = {"Slot": [], "Item": []}
            for slot, items in slot_items.items():
                for item in sorted(items, key=lambda x: x.name):
                    table_items["Slot"].append(str(slot))
                    table_items["Item"].append(item.name)
            await send_table(ctx, table_items, reply=True)
        if slot_locations:
            table_locations: dict[str, list[str]] = {"Slot": [], "Location": []}
            for slot, locations in slot_locations.items():
                for location in sorted(locations, key=lambda x: x.name):
                    table_locations["Slot"].append(str(slot))
                    table_locations["Location"].append(location.name)
            await send_table(ctx, table_locations, reply=True)

    ################################################
    ######### NOTIFICATION REPLAY COMMANDS #########
    ################################################

    class ReplayFlags(commands.FlagConverter):
        filter: ItemCategoryFilter = commands.flag(positional=True, default=ItemCategoryFilter.USEFUL)
        slot: Optional[SlotInfoArg] = None
        since: Optional[TimeDeltaArg] = None

    @commands.group(name="replay", help="View previously received items for your registered slots", invoke_without_command=True)  # type: ignore[arg-type]
    async def replay(self, ctx: BotContext) -> None:
        raise UserInputError(f"Must specify a sub-command for `{self._config.discord_command_prefix}replay`")

    @replay.command(name="new", help="Replay items received since last call (can filter by rarity/slot/relative time delta)", ignore_extra=False, extras={"ord": 1})  # type: ignore[arg-type]
    async def replay_new(self, ctx: BotContext, *, flags: ReplayFlags) -> None:
        slots = self._resolve_slots(ctx, flags.slot)
        slot_items: dict[SlotInfo, list[SentItemInfo]] = {}
        for slot in slots:
            # We always call get_new_items() to trigger the saving of replay position, but we disregard the
            # resulting list if the "since" flag was set.
            items = self.state.get_new_items(ctx.author.id, slot)
            if flags.since is not None:
                items = self.state.get_all_items(slot, since=cast(Optional[timedelta], flags.since))
            slot_items[slot] = self._filter_items(items, flags)
        await self._send_replay_items(ctx, slot_items)

    @replay.command(name="full", help="Replay all items received since game start (can filter by rarity/slot/relative time delta)", ignore_extra=False, extras={"ord": 2})  # type: ignore[arg-type]
    async def replay_full(self, ctx: BotContext, *, flags: ReplayFlags) -> None:
        slots = self._resolve_slots(ctx, flags.slot)
        slot_items: dict[SlotInfo, list[SentItemInfo]] = {}
        for slot in slots:
            items = self.state.get_all_items(slot, since=cast(Optional[timedelta], flags.since))
            slot_items[slot] = self._filter_items(items, flags)
        await self._send_replay_items(ctx, slot_items)

    @commands.command(name="ketchmeup", help="Alias of 'replay new'", ignore_extra=False)
    async def ketchmeup(self, ctx: BotContext, *, flags: ReplayFlags) -> None:
        await self.replay_new(ctx, flags=flags)  # type: ignore[arg-type]

    def _filter_items(self, items: list[SentItemInfo], flags: ReplayFlags) -> list[SentItemInfo]:
        return [item for item in items if flags.filter.check(item.category)]

    async def _send_replay_items(self, ctx: BotContext, slot_items: dict[SlotInfo, list[SentItemInfo]]) -> None:
        for slot, items in slot_items.items():
            if not items:
                await send_message(ctx, f"No items to replay for slot `{slot}`", reply=True)
                continue

            table: dict[str, list[str]] = {"You": [], "Item": [], "Sender": [], "Location": []}
            for item in items:
                table["You"].append(str(slot))
                table["Item"].append(item.item_name)
                table["Sender"].append(self.state.resolve_slot(item.from_slot_id).name)
                table["Location"].append(item.location_name)
            await send_table(ctx, table, reply=True)

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
    async def subscribe(self, ctx: BotContext, *, flags: SubscribeFlagsItem) -> None:
        await self.subscribe_item(ctx, flags=flags)  # type: ignore[arg-type]

    @subscribe.command(name="item", help="Subscribes you for the given item (can filter by slot if needed)", ignore_extra=False, extras={"ord": 1})  # type: ignore[arg-type]
    async def subscribe_item(self, ctx: BotContext, *, flags: SubscribeFlagsItem) -> None:
        item: Optional[ItemInfo] = None
        matching_slots: list[SlotInfo] = []
        slots = self._resolve_slots(ctx, flags.slot)
        for slot in slots:
            try:
                item = self.state.resolve_item(slot.game, cast(str, flags.item))
                self.state.add_user_subscription(ctx.author.id, slot, SubscriptionType.ITEM, item.name)
                matching_slots.append(slot)
            except ADOSError:
                continue
        if not matching_slots or item is None:
            raise ADOSError(f"Item `{flags.item}` does not exist in the searched slots")

        slot_names_joined = join_objects(matching_slots)
        await send_success(ctx, f"You have subscribed to item `{item.name}` in: {slot_names_joined}")

    @subscribe.command(name="group", help="Subscribes you for the given group (can filter by slot if needed)", ignore_extra=False, extras={"ord": 2})  # type: ignore[arg-type]
    async def subscribe_group(self, ctx: BotContext, *, flags: SubscribeFlagsGroup) -> None:
        group: Optional[str] = None
        matching_slots: list[SlotInfo] = []
        slots = self._resolve_slots(ctx, flags.slot)
        for slot in slots:
            try:
                group = self.state.resolve_group(slot.game, cast(str, flags.group))
                self.state.add_user_subscription(ctx.author.id, slot, SubscriptionType.GROUP, group)
                matching_slots.append(slot)
            except ADOSError:
                continue
        if not matching_slots or group is None:
            raise ADOSError(f"Group `{flags.group}` does not exist in the searched slots")

        slot_names_joined = join_objects(matching_slots)
        await send_success(ctx, f"You have subscribed to item group `{group}` in: {slot_names_joined}")

    @subscribe.command(name="remove", help="Unsubscribes you from items/groups containing the given text (can filter by slot)", ignore_extra=False, extras={"ord": 3})  # type: ignore[arg-type]
    async def subscribe_remove(self, ctx: BotContext, *, flags: SubscribeFlagsValue) -> None:
        self.state.remove_user_subscriptions(ctx.author.id, flags.slot, flags.value)
        await send_success(ctx, f"You have removed items/group subscriptions matching `{flags.value}`")

    @subscribe.command(name="list", help="Lists your active item/group subscriptions (can filter by slot)", ignore_extra=False)  # type: ignore[arg-type]
    async def subscribe_list(self, ctx: BotContext, *, flags: SubscribeFlags) -> None:
        slot_subscriptions = self.state.get_user_subscriptions(ctx.author.id, cast(Optional[SlotInfo], flags.slot))
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

    @subscribe.command(name="clear", help="Clears all your item/group subscriptions (can filter by slot)", ignore_extra=False, extras={"ord": 4})  # type: ignore[arg-type]
    async def subscribe_clear(self, ctx: BotContext, *, flags: SubscribeFlags) -> None:
        self.state.remove_user_subscriptions(ctx.author.id, flags.slot, None)
        await send_success(ctx, "You have cleared your item/group subscriptions")

    ################################################
    ################ HINT COMMANDS #################
    ################################################

    class HintFlagsItem(commands.FlagConverter):
        item: StringArg = commands.flag(positional=True)
        slot: Optional[SlotInfoArg] = None

    class HintFlagsLocation(commands.FlagConverter):
        location: StringArg = commands.flag(positional=True)
        slot: Optional[SlotInfoArg] = None

    class HintFlagsList(commands.FlagConverter):
        filter: HintStatusFilter = commands.flag(positional=True, default=HintStatusFilter.UNFOUND)
        slot: Optional[SlotInfoArg] = None

    class HintFlagsPoints(commands.FlagConverter):
        slot: Optional[SlotInfoArg] = None

    @commands.group(name="hint", help="View and use hints for your registered slots", invoke_without_command=True)  # type: ignore[arg-type]
    async def hint(self, ctx: BotContext, *, flags: HintFlagsItem) -> None:
        await self.hint_item(ctx, flags=flags)  # type: ignore[arg-type]

    @hint.command(name="item", help="Use a hint for the given item (can filter by slot if needed)", ignore_extra=False, extras={"ord": 1})  # type: ignore[arg-type]
    async def hint_item(self, ctx: BotContext, *, flags: HintFlagsItem) -> None:
        item: Optional[ItemInfo] = None
        matching_slots: list[SlotInfo] = []
        slots = self._resolve_slots(ctx, flags.slot)
        for slot in slots:
            try:
                item = self.state.resolve_item(slot.game, cast(str, flags.item))
                matching_slots.append(slot)
            except ADOSError:
                continue
        if not matching_slots or item is None:
            raise ADOSError(f"Item `{flags.item}` does not exist in the searched slots")
        if len(matching_slots) != 1:
            raise ADOSError(f"Item `{flags.item}` exists in multiple slots; please specify one to hint")

        socket = await self._room_manager.active_room.get_slot_socket(matching_slots[0])
        response = await socket.perform_request(HintsMessage, get_hint_item_message(item.name))
        points = await socket.perform_request(HintPointsMessage, get_hint_message())
        await self._send_hint_response(ctx, matching_slots[0], response, points)

    @hint.command(name="location", help="Use a hint to see what is at the given location (can filter by slot if needed)", ignore_extra=False, extras={"ord": 2})  # type: ignore[arg-type]
    async def hint_location(self, ctx: BotContext, *, flags: HintFlagsLocation) -> None:
        location: Optional[LocationInfo] = None
        matching_slots: list[SlotInfo] = []
        slots = self._resolve_slots(ctx, flags.slot)
        for slot in slots:
            try:
                location = self.state.resolve_location(slot.game, cast(str, flags.location))
                matching_slots.append(slot)
            except ADOSError:
                continue
        if not matching_slots or location is None:
            raise ADOSError(f"Location `{flags.location}` does not exist in the searched slots")
        if len(matching_slots) != 1:
            raise ADOSError(f"Location `{flags.location}` exists in multiple slots; please specify one to hint")

        socket = await self._room_manager.active_room.get_slot_socket(matching_slots[0])
        response = await socket.perform_request(HintsMessage, get_hint_location_message(location.name))
        points = await socket.perform_request(HintPointsMessage, get_hint_message())
        await self._send_hint_response(ctx, matching_slots[0], response, points)

    @hint.command(name="list", help="List available hints (can filter by slot/status)", ignore_extra=False, extras={"ord": 3})  # type: ignore[arg-type]
    async def hint_list(self, ctx: BotContext, *, flags: HintFlagsList) -> None:
        async def _fetch_hints_for_slot(slot: SlotInfo) -> HintsMessage:
            socket = await self._room_manager.active_room.get_slot_socket(slot)
            return await socket.perform_request(HintsMessage, get_hint_message())

        slots = self._resolve_slots(ctx, flags.slot)
        results = await asyncio.gather(*(_fetch_hints_for_slot(slot) for slot in slots))

        sent_hints = False
        for slot, result in zip(slots, results):
            hints = [hint for hint in result.hints if flags.filter.check(hint.status)]
            if hints:
                sent_hints = True
                await self._send_hints(ctx, slot, hints)
        if not sent_hints:
            await send_message(ctx, "There are no hints available for the selected slots and filter level")

    @hint.command(name="points", help="Show hint points held and needed (can filter by slot)", ignore_extra=False, extras={"ord": 4})  # type: ignore[arg-type]
    async def hint_points(self, ctx: BotContext, *, flags: HintFlagsPoints) -> None:
        async def _fetch_points_for_slot(slot: SlotInfo) -> HintPointsMessage:
            socket = await self._room_manager.active_room.get_slot_socket(slot)
            return await socket.perform_request(HintPointsMessage, get_hint_message())

        slots = self._resolve_slots(ctx, flags.slot)
        results = await asyncio.gather(*(_fetch_points_for_slot(slot) for slot in slots))

        message: list[str] = []
        for slot, result in zip(slots, results):
            message.append(
                f"- `{slot}`: {result.points_available} points available ({result.points_required} required)"
            )
        await send_message(ctx, "\n".join(message))

    async def _send_hint_response(
        self, ctx: BotContext, slot: SlotInfo, response: HintsMessage, points: HintPointsMessage
    ) -> None:
        if response.result == HintsMessage.Result.SUCCESS:
            await self._send_hints(ctx, slot, response.hints)
            await send_message(
                ctx,
                f"You have {points.points_available} points remaining ({points.points_required} required)",
                reply=True,
            )
        elif response.result == HintsMessage.Result.NOT_FOUND:
            raise ADOSError("Nothing found for recognized object name; object appears to not exist in the multiworld")
        elif response.result == HintsMessage.Result.NO_POINTS:
            raise ADOSError(
                f"You cannot afford a hint; you have {points.points_available} points available and need at least {points.points_required}"
            )

    async def _send_hints(self, ctx: BotContext, hinter: SlotInfo, hints: list[HintInfo]) -> None:
        hints.sort(key=lambda hint: (hint.to_slot_id != hinter.id, -hint.status.value, hint.item_id))

        table: dict[str, list[str]] = {"Hinter": [], "Item": [], "Holder": [], "Location": [], "Status": []}
        for hint in hints:
            to_slot = self.state.resolve_slot(hint.to_slot_id)
            from_slot = self.state.resolve_slot(hint.from_slot_id)
            table["Hinter"].append(str(to_slot))
            table["Item"].append(str(self.state.resolve_item(to_slot.game, hint.item_id)))
            table["Holder"].append(str(from_slot))
            table["Location"].append(str(self.state.resolve_location(from_slot.game, hint.location_id)))
            table["Status"].append(hint.status.name.lower())

        if len(hints) == 1:
            self_slot, item, other_slot, location, status = (column[0] for column in table.values())
            await send_message(
                ctx,
                f"{highlight(self_slot)}'s `{item}` is at `{location}` in {highlight(other_slot)}'s world ({status})",
                reply=True,
            )
        else:
            await send_table(ctx, table, reply=True)

    ################################################
    ################ STATS COMMANDS ################
    ################################################

    class StatsFlags(commands.FlagConverter):
        mode: StatsOutputMode = commands.flag(positional=True)

    @commands.command(name="checks", help="Outputs data on completed/total checks per slot", ignore_extra=False)
    async def checks(self, ctx: BotContext, *, flags: StatsFlags) -> None:
        server_statuses = (
            await self._room_manager.active_room.socket.perform_request(StatusMessage, get_status_message())
        ).statuses
        local_statuses = self.state.slot_checks_statuses()

        full_statuses: dict[SlotInfo, SlotFullStatus] = {}
        for slot_name, server_status in server_statuses.items():
            slot = self.state.resolve_slot(slot_name)
            local_status = local_statuses[slot]
            full_statuses[slot] = SlotFullStatus(
                found_checks=server_status.found_checks,
                total_checks=server_status.total_checks,
                self_freed_checks=local_status.self_freed,
                other_freed_checks=local_status.other_freed,
                goal_completed=server_status.goal_completed,
                has_released=local_status.has_released,
            )

        full_statuses = dict(sorted(full_statuses.items(), key=lambda pair: pair[0].name))
        await self._get_plotter(flags.mode).send_checks(ctx, full_statuses)

    @commands.command(name="items", help="Outputs data on types of items sent/received per slot", ignore_extra=False)
    async def items(self, ctx: BotContext, *, flags: StatsFlags) -> None:
        item_counts = dict(sorted(self.state.slot_item_counts().items(), key=lambda pair: pair[0].name))
        if not item_counts:
            await send_message(ctx, "No items have been sent yet")
            return
        await self._get_plotter(flags.mode).send_items(ctx, item_counts)

    @commands.command(name="deaths", help="Outputs data on death links triggered per slot", ignore_extra=False)
    async def deaths(self, ctx: BotContext, *, flags: StatsFlags) -> None:
        death_counts = dict(sorted(self.state.death_counts().items(), key=lambda pair: pair[0].name))
        if not death_counts:
            await send_message(ctx, "No death links have been triggered yet")
            return
        await self._get_plotter(flags.mode).send_deaths(ctx, death_counts)

    def _get_plotter(self, mode: StatsOutputMode) -> type[GraphPlotter] | type[TablePlotter]:
        return GraphPlotter if mode == StatsOutputMode.GRAPH else TablePlotter
