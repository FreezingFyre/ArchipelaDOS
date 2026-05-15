import json
import logging
import os
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timedelta
from typing import DefaultDict, NamedTuple, Optional

from pydantic import BaseModel

from ados.arch.messages import (
    ConnectedMessage,
    DataPackageMessage,
    DeathLinkMessage,
    GoalReachedMessage,
    ItemGroupsMessage,
    ItemSendMessage,
    RoomUpdateMessage,
    SlotReleaseMessage,
)
from ados.arch.socket import SocketClient
from ados.common import (
    ADOSError,
    ItemInfo,
    LocationInfo,
    Persisted,
    SentItemInfo,
    SlotInfo,
    SlotItemCounts,
    SubscriptionType,
    normalize,
)

_log = logging.getLogger(__name__)

REPLAY_MARKER = "REPLAY: "


class UserSlot(NamedTuple):
    user_id: int
    slot_id: int


class SlotSubscription(NamedTuple):
    type: SubscriptionType
    value: str
    user_id: int


class SlotChecksStatus(NamedTuple):
    self_freed: int
    other_freed: int
    has_released: bool


# The data stored in the state file.
class RoomStateData(BaseModel):
    user_slot_ids: DefaultDict[int, set[int]] = defaultdict(set)
    slot_subscriptions: DefaultDict[int, set[SlotSubscription]] = defaultdict(set)
    slot_deaths: DefaultDict[int, int] = defaultdict(int)
    slot_self_freed: DefaultDict[int, int] = defaultdict(int)
    slot_other_freed: DefaultDict[int, int] = defaultdict(int)
    slots_released: set[int] = set()


# The data stored in the item log file.
class ItemLogData:
    def __init__(self) -> None:
        self.slot_items: dict[int, list[SentItemInfo]] = defaultdict(list)
        self.user_slot_replay_index: dict[UserSlot, int] = defaultdict(int)


# The main ArchipelaDOS state management class. Handles information related to user state,
# like registered slots and item subscriptions, and ensures this information is persisted
# where necessary so that it is not lost on bot restarts. Also handles information fetched
# from the server, such as slot details and item mappings.
class RoomState(Persisted[RoomStateData]):

    def __init__(self, data_path: str, socket: SocketClient):

        super().__init__(os.path.join(data_path, "state.json"))
        self._item_log_file = os.path.join(data_path, "itemlog.txt")

        self._slots: dict[int, SlotInfo] = {}
        self._slot_ids_by_name: dict[str, int] = {}

        self._game_items: dict[str, dict[int, ItemInfo]] = {}
        self._game_item_ids_by_name: dict[str, dict[str, int]] = {}
        self._game_locations: dict[str, dict[int, LocationInfo]] = {}
        self._game_location_ids_by_name: dict[str, dict[str, int]] = {}
        self._game_groups: dict[str, set[str]] = {}

        # This is the information about slot item sends.
        self._item_counts: dict[int, SlotItemCounts] = defaultdict(SlotItemCounts)
        self._item_log = self._load_item_log()

        socket.add_message_handler(ConnectedMessage, self._handle_slot_update)
        socket.add_message_handler(RoomUpdateMessage, self._handle_slot_update)
        socket.add_message_handler(DataPackageMessage, self._handle_data_package)
        socket.add_message_handler(ItemGroupsMessage, self._handle_item_groups)
        socket.add_message_handler(ItemSendMessage, self._handle_item_send)
        socket.add_message_handler(DeathLinkMessage, self._handle_death_link)
        socket.add_message_handler(GoalReachedMessage, self._handle_slot_completed)
        socket.add_message_handler(SlotReleaseMessage, self._handle_slot_completed)

    # The list of slots can change on either a ConnectedMessage or a RoomUpdateMessage. This
    # will only affect aliases, so all IDs remain valid.
    def _handle_slot_update(self, message: ConnectedMessage | RoomUpdateMessage) -> None:
        self._slots = {slot.id: slot for slot in message.slots}
        self._slot_ids_by_name = {normalize(slot.name): slot.id for slot in message.slots}
        self._slot_ids_by_name.update({normalize(slot.alias): slot.id for slot in message.slots})
        self._slot_ids_by_name.update({normalize(str(slot)): slot.id for slot in message.slots})
        _log.info("Populated slot information for %d slots", len(message.slots))

    # The DataPackageMessage is sent once on startup, to populate item and location mappings
    # for each game.
    def _handle_data_package(self, message: DataPackageMessage) -> None:
        for game, items in message.game_items.items():
            self._game_items[game] = {item.id: item for item in items}
            self._game_item_ids_by_name[game] = {normalize(item.name): item.id for item in items}
        for game, locations in message.game_locations.items():
            self._game_locations[game] = {location.id: location for location in locations}
            self._game_location_ids_by_name[game] = {normalize(location.name): location.id for location in locations}
        _log.info("Populated packaged data for %d games", len(message.game_items))

    # The ItemGroupsMessage is sent once on startup, to populate item group mappings for
    # each game.
    def _handle_item_groups(self, message: ItemGroupsMessage) -> None:
        self._game_groups = {game: set(groups) for game, groups in message.game_groups.items()}
        for game, items in self._game_items.items():
            if not game in message.game_item_groups:
                continue
            new_items: dict[int, ItemInfo] = {}
            for item_id, item in items.items():
                groups = message.game_item_groups[game].get(item.name, [])
                new_items[item_id] = item._replace(groups=groups)  # pylint: disable = protected-access
            items.update(new_items)
        _log.info("Populated item groups for %d games", len(message.game_item_groups))

    # Whenever an item is sent, append it to the item log both on disk and in memory.
    def _handle_item_send(self, message: ItemSendMessage) -> None:
        item = self.resolve_item(self._slots[message.to_slot_id].game, message.item_id)
        location = self.resolve_location(self._slots[message.from_slot_id].game, message.location_id)

        sent_item = SentItemInfo(
            timestamp=datetime.now().timestamp(),
            item_name=item.name,
            location_name=location.name,
            to_slot_id=message.to_slot_id,
            from_slot_id=message.from_slot_id,
            category=message.category,
        )

        self._item_log.slot_items[message.to_slot_id].append(sent_item)
        self._record_item_category(sent_item)
        with open(self._item_log_file, "a") as log_file:
            log_file.write(f"{json.dumps(sent_item._asdict())}\n")  # pylint: disable = protected-access

        if message.from_slot_id in self._state.slots_released or message.to_slot_id in self._state.slots_released:
            self._record_auto_item(message.from_slot_id, message.to_slot_id)

    @Persisted.persist
    def _handle_death_link(self, message: DeathLinkMessage) -> None:
        slot = self.resolve_slot(message.slot_name)
        self._state.slot_deaths[slot.id] += 1

    # Need to clear subscriptions for a slot when goal is reached so that users aren't spammed with item
    # sends from all the released locations. Also clear from users' registered slots.
    @Persisted.persist
    def _handle_slot_completed(self, message: GoalReachedMessage | SlotReleaseMessage) -> None:
        if message.slot_id in self._state.slots_released:
            return
        self._state.slots_released.add(message.slot_id)
        if message.slot_id in self._state.slot_subscriptions:
            self._state.slot_subscriptions.pop(message.slot_id)
        for user_id in list(self._state.user_slot_ids.keys()):
            if message.slot_id in self._state.user_slot_ids[user_id]:
                self._state.user_slot_ids[user_id].remove(message.slot_id)
                if not self._state.user_slot_ids[user_id]:
                    self._state.user_slot_ids.pop(user_id)

    @Persisted.persist
    def _record_auto_item(self, from_slot_id: int, to_slot_id: int) -> None:
        if from_slot_id == to_slot_id:
            self._state.slot_self_freed[from_slot_id] += 1
            return
        if from_slot_id in self._state.slots_released:
            self._state.slot_self_freed[from_slot_id] += 1
        if to_slot_id in self._state.slots_released:
            self._state.slot_other_freed[from_slot_id] += 1

    def _record_item_category(self, info: SentItemInfo) -> None:
        if info.from_slot_id == info.to_slot_id:
            self._item_counts[info.from_slot_id].self_items[info.category] += 1
        else:
            self._item_counts[info.from_slot_id].sent_items[info.category] += 1
            self._item_counts[info.to_slot_id].received_items[info.category] += 1

    def _load_item_log(self) -> ItemLogData:
        data = ItemLogData()
        if not os.path.exists(self._item_log_file):
            return data

        _log.info("Loading item log from '%s'", self._item_log_file)
        with open(self._item_log_file, "r") as log_file:
            for line in log_file:
                if line.startswith(REPLAY_MARKER):
                    # This line indicates a replay occurred for the given user and slot ID.
                    user_slot = UserSlot(**json.loads(line.replace(REPLAY_MARKER, "").strip()))
                    data.user_slot_replay_index[user_slot] = len(data.slot_items[user_slot.slot_id])
                else:
                    sent_item = SentItemInfo(**json.loads(line))
                    data.slot_items[sent_item.to_slot_id].append(sent_item)
                    self._record_item_category(sent_item)

        _log.info("Populated item log with %d sent items", sum(len(items) for items in data.slot_items.values()))
        return data

    ################################################
    ################# SERVER DATA ##################
    ################################################

    def all_slots(self) -> list[SlotInfo]:
        return list(self._slots.values())

    def all_groups(self, game: str) -> set[str]:
        return self._game_groups.get(game, set())

    def resolve_slot(self, value: str | int) -> SlotInfo:
        if isinstance(value, int):
            if value not in self._slots:
                raise ADOSError(f"Slot ID {value} does not exist in the multiworld")
            return self._slots[value]

        value_norm = normalize(value)
        if value_norm not in self._slot_ids_by_name:
            raise ADOSError(f"Slot `{value}` does not exist in the multiworld")
        return self._slots[self._slot_ids_by_name[value_norm]]

    def resolve_group(self, game: str, group: str) -> str:
        group_norm = normalize(group)
        for game_group in self._game_groups.get(game, set()):
            if normalize(game_group) == group_norm:
                return game_group
        raise ADOSError(f"Group `{group}` does not exist in game `{game}`")

    def resolve_item(self, game: str, value: str | int) -> ItemInfo:
        if isinstance(value, int):
            if value not in self._game_items.get(game, {}):
                raise ADOSError(f"Item ID {value} does not exist in game `{game}`")
            return self._game_items[game][value]

        value_norm = normalize(value)
        if value_norm not in self._game_item_ids_by_name.get(game, {}):
            raise ADOSError(f"Item `{value}` does not exist in game `{game}`")
        item_id = self._game_item_ids_by_name[game][value_norm]
        return self._game_items[game][item_id]

    def search_items(self, game: str, search_text: str) -> list[ItemInfo]:
        search_text_norm = normalize(search_text)
        matching_items: list[ItemInfo] = []
        for item in self._game_items.get(game, {}).values():
            if search_text_norm in normalize(item.name):
                matching_items.append(item)
        return matching_items

    def resolve_location(self, game: str, value: str | int) -> LocationInfo:
        if isinstance(value, int):
            if value not in self._game_locations.get(game, {}):
                raise ADOSError(f"Location ID {value} does not exist in game `{game}`")
            return self._game_locations[game][value]

        value_norm = normalize(value)
        if value_norm not in self._game_location_ids_by_name.get(game, {}):
            raise ADOSError(f"Location `{value}` does not exist in game `{game}`")
        location_id = self._game_location_ids_by_name[game][value_norm]
        return self._game_locations[game][location_id]

    def search_locations(self, game: str, search_text: str) -> list[LocationInfo]:
        search_text_norm = normalize(search_text)
        matching_locations: list[LocationInfo] = []
        for location in self._game_locations.get(game, {}).values():
            if search_text_norm in normalize(location.name):
                matching_locations.append(location)
        return matching_locations

    def death_counts(self) -> dict[SlotInfo, int]:
        return {self._slots[slot_id]: count for slot_id, count in self._state.slot_deaths.items()}

    def slot_checks_statuses(self) -> dict[SlotInfo, SlotChecksStatus]:
        return {
            slot: SlotChecksStatus(
                self_freed=self._state.slot_self_freed.get(slot_id, 0),
                other_freed=self._state.slot_other_freed.get(slot_id, 0),
                has_released=(slot_id in self._state.slots_released),
            )
            for slot_id, slot in self._slots.items()
        }

    def slot_item_counts(self) -> dict[SlotInfo, SlotItemCounts]:
        return {self._slots[slot_id]: counts for slot_id, counts in self._item_counts.items()}

    ################################################
    ############## SLOT REGISTRATIONS ##############
    ################################################

    def get_user_slots(self, user_id: int) -> list[SlotInfo]:
        slot_ids = self._state.user_slot_ids.get(user_id, set())
        return sorted([self._slots[slot_id] for slot_id in slot_ids], key=lambda slot: slot.name)

    @Persisted.persist
    def add_user_slot(self, user_id: int, slot: SlotInfo) -> None:
        if slot.id in self._state.user_slot_ids.get(user_id, set()):
            raise ADOSError(f"User is already registered for slot `{slot}`")
        self._state.user_slot_ids[user_id].add(slot.id)

    @Persisted.persist
    def remove_user_slot(self, user_id: int, slot: SlotInfo) -> None:
        if slot.id not in self._state.user_slot_ids.get(user_id, set()):
            raise ADOSError(f"User is not registered for slot `{slot}`")
        self._state.user_slot_ids[user_id].remove(slot.id)
        if not self._state.user_slot_ids[user_id]:
            self._state.user_slot_ids.pop(user_id)

    @Persisted.persist
    def clear_user_slots(self, user_id: int) -> None:
        if user_id in self._state.user_slot_ids:
            self._state.user_slot_ids.pop(user_id)

    ################################################
    ################# ITEM REPLAY ##################
    ################################################

    def get_new_items(self, user_id: int, slot: SlotInfo) -> list[SentItemInfo]:
        user_slot = UserSlot(user_id, slot.id)
        replay_index = self._item_log.user_slot_replay_index[user_slot]
        recent_items = self._item_log.slot_items[slot.id][replay_index:]
        self._item_log.user_slot_replay_index[user_slot] = len(self._item_log.slot_items[slot.id])

        with open(self._item_log_file, "a") as log_file:
            log_file.write(f"{REPLAY_MARKER}{json.dumps(user_slot._asdict())}\n")  # pylint: disable = protected-access
        return recent_items

    def get_all_items(self, slot: SlotInfo, *, since: Optional[timedelta] = None) -> list[SentItemInfo]:
        all_items = self._item_log.slot_items[slot.id]
        if since is None:
            return all_items
        replay_time = (datetime.now() - since).timestamp()
        replay_index = bisect_left(all_items, replay_time, key=lambda item: item.timestamp)
        return all_items[replay_index:]

    ################################################
    ################ SUBSCRIPTIONS #################
    ################################################

    def get_subscribed_users(self, slot: SlotInfo, item: ItemInfo) -> set[int]:
        user_ids: set[int] = set()
        subscriptions = self._state.slot_subscriptions.get(slot.id, set())

        for subscription in subscriptions:
            if subscription.type == SubscriptionType.ITEM:
                if item.name == subscription.value:
                    user_ids.add(subscription.user_id)
            elif subscription.value in item.groups:
                user_ids.add(subscription.user_id)

        return user_ids

    def get_user_subscriptions(self, user_id: int, slot: Optional[SlotInfo]) -> dict[SlotInfo, set[SlotSubscription]]:
        user_subscriptions: dict[SlotInfo, set[SlotSubscription]] = defaultdict(set)
        to_check_slots = [slot] if slot is not None else self.get_user_slots(user_id)
        for to_check_slot in to_check_slots:
            subscriptions = self._state.slot_subscriptions.get(to_check_slot.id, set())
            for subscription in subscriptions:
                if subscription.user_id == user_id:
                    user_subscriptions[to_check_slot].add(subscription)
        return user_subscriptions

    @Persisted.persist
    def add_user_subscription(
        self, user_id: int, slot: SlotInfo, subscription_type: SubscriptionType, value: str
    ) -> None:
        subscription = SlotSubscription(subscription_type, value, user_id)
        if subscription in self._state.slot_subscriptions.get(slot.id, set()):
            raise ADOSError(f"User is already subscribed to {subscription_type.value} `{value}` in slot `{slot}`")
        self._state.slot_subscriptions[slot.id].add(subscription)

    @Persisted.persist
    def remove_user_subscriptions(self, user_id: int, slot: Optional[SlotInfo], value: Optional[str]) -> None:
        value_norm = normalize(value) if value is not None else ""
        to_check_slots = [slot] if slot is not None else self.get_user_slots(user_id)
        for to_check_slot in to_check_slots:
            subscriptions = self._state.slot_subscriptions.get(to_check_slot.id, set())
            if not subscriptions:
                continue
            self._state.slot_subscriptions[to_check_slot.id] = {
                subscription
                for subscription in subscriptions
                if not (
                    subscription.user_id == user_id and (value is None or value_norm == normalize(subscription.value))
                )
            }
