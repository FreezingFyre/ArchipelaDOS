import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, DefaultDict, Self

from pydantic import BaseModel

from ados.arch.messages import ConnectedMessage, DataPackageMessage, RoomUpdateMessage
from ados.arch.socket import SocketClient
from ados.common import ADOSError, ItemInfo, LocationInfo, SlotInfo
from ados.config import ADOSConfig

_log = logging.getLogger(__name__)


# The actual data stored in the state file
class StateData(BaseModel):
    user_slots: DefaultDict[int, set[int]] = defaultdict(set)  # Maps Discord user IDs to slot IDs


# The main ArchipelaDOS state management class. Handles information related to user state,
# like registered slots and item subscriptions, and ensures this information is persisted
# so that it is not lost on bot restarts. Also handles information fetched from the server,
# such as slot details and item mappings.
class ADOSState:

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
        self._file_path = os.path.join(config.data_path, f"{config.archipelago_room}_state.json")

        self._slots_by_id: dict[int, SlotInfo] = {}
        self._slots_by_name: dict[str, SlotInfo] = {}

        self._game_items_by_id: dict[str, dict[int, ItemInfo]] = {}
        self._game_items_by_name: dict[str, dict[str, ItemInfo]] = {}
        self._game_locations_by_id: dict[str, dict[int, LocationInfo]] = {}
        self._game_locations_by_name: dict[str, dict[str, LocationInfo]] = {}

        self._data = self._load_state()
        self._save_state()

        socket.add_message_handler(ConnectedMessage, self._handle_slot_update)
        socket.add_message_handler(RoomUpdateMessage, self._handle_slot_update)
        socket.add_message_handler(DataPackageMessage, self._handle_data_package)

    async def _handle_slot_update(self, message: ConnectedMessage | RoomUpdateMessage) -> None:
        self._slots_by_id = {slot.id: slot for slot in message.slots}
        self._slots_by_name = {slot.name.lower(): slot for slot in message.slots}
        self._slots_by_name.update({slot.alias.lower(): slot for slot in message.slots})
        self._slots_by_name.update({str(slot): slot for slot in message.slots})

    async def _handle_data_package(self, message: DataPackageMessage) -> None:
        for game, items in message.game_items.items():
            self._game_items_by_id[game] = {item.id: item for item in items}
            self._game_items_by_name[game] = {item.name.lower(): item for item in items}
        for game, locations in message.game_locations.items():
            self._game_locations_by_id[game] = {location.id: location for location in locations}
            self._game_locations_by_name[game] = {location.name.lower(): location for location in locations}

    def _save_state(self) -> None:
        with open(self._file_path, "w") as data_file:
            data_file.write(self._data.model_dump_json(indent=4))

    def _load_state(self) -> StateData:
        # If the file doesn't exist, return a fresh state
        if not os.path.exists(self._file_path):
            _log.info("State file '%s' does not exist; starting fresh", self._file_path)
            return StateData()

        try:
            with open(self._file_path, "r") as data_file:
                _log.info("Loading state file '%s'", self._file_path)
                return StateData(**json.load(data_file))
        except Exception as ex:
            # If there's a validation (or other) error, back up the invalid file so it can be
            # inspected later, then start fresh
            _log.error("Failed to load state file '%s': %s", self._file_path, ex)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_file_path = self._file_path.replace(".json", "")
            backup_path = f"{base_file_path}.invalid_{timestamp}.json"
            os.rename(self._file_path, backup_path)
            _log.info("Backed up invalid state file to '%s'; starting fresh", backup_path)
            return StateData()

    ################################################
    ################# SERVER DATA ##################
    ################################################

    def all_slots(self) -> list[SlotInfo]:
        return list(self._slots_by_id.values())

    def resolve_slot(self, value: str) -> SlotInfo:
        value_lower = value.lower()
        if value_lower not in self._slots_by_name:
            raise ADOSError(f"Slot '{value}' does not exist in the multiworld")
        return self._slots_by_name[value_lower]

    ################################################
    ############## SLOT REGISTRATIONS ##############
    ################################################

    def user_slots(self, user_id: int) -> list[SlotInfo]:
        slot_ids = self._data.user_slots.get(user_id, set())
        return [self._slots_by_id[slot_id] for slot_id in slot_ids]

    @persist
    def add_user_slot(self, user_id: int, slot: SlotInfo) -> None:
        if slot.id in self._data.user_slots.get(user_id, set()):
            raise ADOSError(f"User is already registered for slot `{slot}`")
        self._data.user_slots[user_id].add(slot.id)

    @persist
    def remove_user_slot(self, user_id: int, slot: SlotInfo) -> None:
        if slot.id not in self._data.user_slots.get(user_id, set()):
            raise ADOSError(f"User is not registered for slot `{slot}`")
        self._data.user_slots[user_id].remove(slot.id)
        if not self._data.user_slots[user_id]:
            self._data.user_slots.pop(user_id)

    @persist
    def clear_user_slots(self, user_id: int) -> None:
        if user_id in self._data.user_slots:
            self._data.user_slots.pop(user_id)
