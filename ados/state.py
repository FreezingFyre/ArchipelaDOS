import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, DefaultDict, NamedTuple, Optional, Self

from pydantic import BaseModel

from ados.arch.messages import (
    ConnectedMessage,
    DataPackageMessage,
    ItemGroupsMessage,
    ItemSendMessage,
    RoomUpdateMessage,
)
from ados.arch.socket import SocketClient
from ados.common import (
    ADOSError,
    ItemInfo,
    LocationInfo,
    SentItemInfo,
    SlotInfo,
)
from ados.config import ADOSConfig

_log = logging.getLogger(__name__)

REPLAY_MARKER = "REPLAY: "


class SubscriptionType(str, Enum):
    ITEM = "item"
    GROUP = "group"


class UserSlot(NamedTuple):
    user_id: int
    slot_id: int


class SlotSubscription(NamedTuple):
    type: SubscriptionType
    value: str
    user_id: int


# The data stored in the state file
class StateData(BaseModel):
    user_slot_ids: DefaultDict[int, set[int]] = defaultdict(set)
    slot_subscriptions: DefaultDict[int, set[SlotSubscription]] = defaultdict(set)


# The data stored in the item log file
class ItemLogData(NamedTuple):
    slot_items: dict[int, list[SentItemInfo]] = defaultdict(list)
    user_slot_replay_index: dict[UserSlot, int] = defaultdict(int)


# The main ArchipelaDOS state management class. Handles information related to user state,
# like registered slots and item subscriptions, and ensures this information is persisted
# where necessary so that it is not lost on bot restarts. Also handles information fetched
# from the server, such as slot details and item mappings.
class GlobalState:

    # Decorator which will persist the state after the method is called
    @staticmethod
    def persist[T](func: Callable[..., T]) -> Callable[..., T]:
        def _wrapper(self: Self, *args: Any, **kwargs: Any) -> T:
            result = func(self, *args, **kwargs)
            self._save_state()  # pylint: disable = protected-access
            return result

        return _wrapper

    def __init__(self, config: ADOSConfig, socket: SocketClient):
        os.makedirs(config.data_path, exist_ok=True)
        self._state_file = os.path.join(config.data_path, f"{config.archipelago_room}_state.json")
        self._item_log_file = os.path.join(config.data_path, f"{config.archipelago_room}_item_log.txt")

        self._slots: dict[int, SlotInfo] = {}
        self._slot_ids_by_name: dict[str, int] = {}

        self._game_items: dict[str, dict[int, ItemInfo]] = {}
        self._game_item_ids_by_name: dict[str, dict[str, int]] = {}
        self._game_locations: dict[str, dict[int, LocationInfo]] = {}
        self._game_groups: dict[str, set[str]] = {}

        # This is the information about slot items sends
        self._item_log = self._load_item_log()

        # This is the data which is persisted to disk on every update
        self._state = self._load_state()
        self._save_state()

        socket.add_message_handler(ConnectedMessage, self._handle_slot_update)
        socket.add_message_handler(RoomUpdateMessage, self._handle_slot_update)
        socket.add_message_handler(DataPackageMessage, self._handle_data_package)
        socket.add_message_handler(ItemGroupsMessage, self._handle_item_groups)
        socket.add_message_handler(ItemSendMessage, self._handle_item_send)

    # The list of slots can change on either a ConnectedMessage or a RoomUpdateMessage. This
    # will only affect aliases, so all IDs remain valid.
    def _handle_slot_update(self, message: ConnectedMessage | RoomUpdateMessage) -> None:
        self._slots = {slot.id: slot for slot in message.slots}
        self._slot_ids_by_name = {slot.name.lower(): slot.id for slot in message.slots}
        self._slot_ids_by_name.update({slot.alias.lower(): slot.id for slot in message.slots})
        self._slot_ids_by_name.update({str(slot).lower(): slot.id for slot in message.slots})
        _log.info("Populated slot information for %d slots", len(message.slots))

    # The DataPackageMessage is sent once on startup, to populate item and location mappings
    # for each game.
    def _handle_data_package(self, message: DataPackageMessage) -> None:
        for game, items in message.game_items.items():
            self._game_items[game] = {item.id: item for item in items}
            self._game_item_ids_by_name[game] = {item.name.lower(): item.id for item in items}
        for game, locations in message.game_locations.items():
            self._game_locations[game] = {location.id: location for location in locations}
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

    # Whenever an item is sent, append it to the item log both on disk and in memory
    def _handle_item_send(self, message: ItemSendMessage) -> None:
        item = self.resolve_item(self._slots[message.to_slot_id].game, message.item_id)
        location = self.resolve_location(self._slots[message.from_slot_id].game, message.location_id)

        sent_item = SentItemInfo(
            item_name=item.name,
            location_name=location.name,
            to_slot_id=message.to_slot_id,
            from_slot_id=message.from_slot_id,
            category=message.category,
        )

        self._item_log.slot_items[message.to_slot_id].append(sent_item)
        with open(self._item_log_file, "a") as log_file:
            log_file.write(f"{json.dumps(sent_item._asdict())}\n")  # pylint: disable = protected-access

    def _load_item_log(self) -> ItemLogData:
        data = ItemLogData()
        if not os.path.exists(self._item_log_file):
            return data

        _log.info("Loading item log from '%s'", self._item_log_file)
        with open(self._item_log_file, "r") as log_file:
            for line in log_file:
                if line.startswith(REPLAY_MARKER):
                    # This line indicates a replay occurred for the given user and slot ID
                    user_slot = UserSlot(**json.loads(line.replace(REPLAY_MARKER, "").strip()))
                    data.user_slot_replay_index[user_slot] = len(data.slot_items[user_slot.slot_id])
                else:
                    sent_item = SentItemInfo(**json.loads(line))
                    data.slot_items[sent_item.to_slot_id].append(sent_item)

        _log.info("Populated item log with %d sent items", sum(len(items) for items in data.slot_items.values()))
        return data

    def _save_state(self) -> None:
        with open(self._state_file, "w") as data_file:
            data_file.write(self._state.model_dump_json(indent=4))

    def _load_state(self) -> StateData:
        # If the file doesn't exist, return a fresh state
        if not os.path.exists(self._state_file):
            _log.info("State file '%s' does not exist; starting fresh", self._state_file)
            return StateData()

        try:
            with open(self._state_file, "r") as data_file:
                _log.info("Loading state file '%s'", self._state_file)
                return StateData(**json.load(data_file))
        except Exception as ex:
            # If there's a validation (or other) error, back up the invalid file so it can be
            # inspected later, then start fresh
            _log.error("Failed to load state file '%s': %s", self._state_file, ex)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_state_file = self._state_file.replace(".json", "")
            backup_path = f"{base_state_file}.invalid_{timestamp}.json"
            os.rename(self._state_file, backup_path)
            _log.info("Backed up invalid state file to '%s'; starting fresh", backup_path)
            return StateData()

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

        value_lower = value.lower()
        if value_lower not in self._slot_ids_by_name:
            raise ADOSError(f"Slot `{value}` does not exist in the multiworld")
        return self._slots[self._slot_ids_by_name[value_lower]]

    def resolve_group(self, game: str, group: str) -> str:
        group_lower = group.lower()
        for game_group in self._game_groups.get(game, set()):
            if game_group.lower() == group_lower:
                return game_group
        raise ADOSError(f"Group `{group}` does not exist in game `{game}`")

    def resolve_item(self, game: str, value: str | int) -> ItemInfo:
        if isinstance(value, int):
            if value not in self._game_items.get(game, {}):
                raise ADOSError(f"Item ID {value} does not exist in game `{game}`")
            return self._game_items[game][value]

        value_lower = value.lower()
        if value_lower not in self._game_item_ids_by_name.get(game, {}):
            raise ADOSError(f"Item `{value}` does not exist in game `{game}`")
        item_id = self._game_item_ids_by_name[game][value_lower]
        return self._game_items[game][item_id]

    def resolve_location(self, game: str, location_id: int) -> LocationInfo:
        if location_id not in self._game_locations.get(game, {}):
            raise ADOSError(f"Location ID {location_id} does not exist in game `{game}`")
        return self._game_locations[game][location_id]

    ################################################
    ############## SLOT REGISTRATIONS ##############
    ################################################

    def get_user_slots(self, user_id: int) -> list[SlotInfo]:
        slot_ids = self._state.user_slot_ids.get(user_id, set())
        return [self._slots[slot_id] for slot_id in slot_ids]

    @persist
    def add_user_slot(self, user_id: int, slot: SlotInfo) -> None:
        if slot.id in self._state.user_slot_ids.get(user_id, set()):
            raise ADOSError(f"User is already registered for slot `{slot}`")
        self._state.user_slot_ids[user_id].add(slot.id)

    @persist
    def remove_user_slot(self, user_id: int, slot: SlotInfo) -> None:
        if slot.id not in self._state.user_slot_ids.get(user_id, set()):
            raise ADOSError(f"User is not registered for slot `{slot}`")
        self._state.user_slot_ids[user_id].remove(slot.id)
        if not self._state.user_slot_ids[user_id]:
            self._state.user_slot_ids.pop(user_id)

    @persist
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

    def get_all_items(self, slot: SlotInfo) -> list[SentItemInfo]:
        return self._item_log.slot_items[slot.id]

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

    @persist
    def add_user_subscription(
        self, user_id: int, slot: SlotInfo, subscription_type: SubscriptionType, value: str
    ) -> None:
        subscription = SlotSubscription(subscription_type, value, user_id)
        if subscription in self._state.slot_subscriptions.get(slot.id, set()):
            raise ADOSError(f"User is already subscribed to {subscription_type.value} `{value}` in slot `{slot}`")
        self._state.slot_subscriptions[slot.id].add(subscription)

    @persist
    def remove_user_subscription(self, user_id: int, slot: Optional[SlotInfo], value: str) -> None:
        value_lower = value.lower()
        to_check_slots = [slot] if slot is not None else self.get_user_slots(user_id)
        for to_check_slot in to_check_slots:
            subscriptions = self._state.slot_subscriptions.get(to_check_slot.id, set())
            if not subscriptions:
                continue
            self._state.slot_subscriptions[to_check_slot.id] = {
                subscription
                for subscription in subscriptions
                if not (subscription.user_id == user_id and value_lower in subscription.value.lower())
            }
