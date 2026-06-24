import functools
import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from enum import Enum
from types import get_original_bases
from typing import Any, Callable, Iterable, NamedTuple, Self, get_args

from pydantic import BaseModel

_log = logging.getLogger(__name__)


# Thrown to send a particular error message to the user through Discord.
class ADOSError(Exception):
    pass


# Joins a list of stringable types with commas, marking the objects with backticks.
def join_objects(objects: Iterable[Any]) -> str:
    object_names = [f"`{obj}`" for obj in objects]
    return ", ".join(sorted(object_names))


# Normalization function so that user input can match names in a case-insensitive,
# purely alphanumeric way.
def normalize(value: str) -> str:
    return "".join(c for c in value.lower() if c.isalnum())


# Defined item categories for use in commands and messages. These can technically
# overlap per the Archipelago spec, but we treat them as mutually exclusive.
class ItemCategory(int, Enum):
    PROGRESSION = 0b001
    USEFUL = 0b010
    FILLER = 0b000
    TRAP = 0b100


# Defined filters for item categories. Generally matches the exact ItemCategory of
# the same name, though USEFUL and ALL include items categorized below them as well.
class ItemCategoryFilter(str, Enum):
    NONE = "none"
    PROGRESSION = "progression"
    USEFUL = "useful"
    ALL = "all"
    TRAPS = "traps"

    def check(self, category: ItemCategory) -> bool:
        if self == ItemCategoryFilter.NONE:
            return False
        if category == ItemCategory.TRAP:
            return self == ItemCategoryFilter.TRAPS
        if self == ItemCategoryFilter.ALL:
            return True
        if self == ItemCategoryFilter.USEFUL:
            return category in (ItemCategory.USEFUL, ItemCategory.PROGRESSION)
        if self == ItemCategoryFilter.PROGRESSION:
            return category == ItemCategory.PROGRESSION
        return False


# Type of a subscription registered by the user for a slot.
class SubscriptionType(str, Enum):
    ITEM = "item"
    GROUP = "group"


# Possible statuses of a hint, as per the Archipelago spec.
class HintStatus(int, Enum):
    UNSPECIFIED = 0
    UNNEEDED = 10
    AVOID = 20
    PRIORITY = 30
    FOUND = 40


# Defined filters for hint statuses. Generally follow the status names, except for
# the addition of an "unfound" filter.
class HintStatusFilter(str, Enum):
    UNSPECIFIED = "unspecified"
    UNNEEDED = "unneeded"
    AVOID = "avoid"
    PRIORITY = "priority"
    FOUND = "found"
    UNFOUND = "unfound"

    def check(self, status: HintStatus) -> bool:
        return (
            (status != HintStatus.FOUND) if (self == HintStatusFilter.UNFOUND) else (status.name.lower() == self.value)
        )


# Stores information about a particular slot in the multiworld. The id, name,
# and game are immutable, while the alias may be changed during the session.
class SlotInfo(NamedTuple):
    id: int
    name: str
    alias: str
    game: str

    def __str__(self) -> str:
        if self.alias == self.name:
            return self.name
        return f"{self.alias} ({self.name})"


# Stores information about a particular item in the multiworld.
class ItemInfo(NamedTuple):
    id: int
    name: str
    game: str
    groups: list[str] = []

    def __str__(self) -> str:
        return self.name


# Stores information about a particular location in the multiworld.
class LocationInfo(NamedTuple):
    id: int
    name: str
    game: str

    def __str__(self) -> str:
        return self.name


# Stores information about an item that was sent from one slot to another in
# the multiworld. Do not bother storing full ItemInfo or SlotInfo objects here,
# as this is only used for user-facing outputs.
class SentItemInfo(NamedTuple):
    timestamp: float
    item_name: str
    location_name: str
    to_slot_id: int
    from_slot_id: int
    category: ItemCategory


# Stores information about a hint about where an item is held in the multiworld.
class HintInfo(NamedTuple):
    item_id: int
    location_id: int
    to_slot_id: int
    from_slot_id: int
    status: HintStatus


# Encodes the full (relevant) status of a slot, including checks that were checked
# in various categories as well as whether the slot is finished.
class SlotFullStatus(NamedTuple):
    found_checks: int
    total_checks: int
    self_freed_checks: int
    other_freed_checks: int
    goal_completed: bool
    has_released: bool


# Encodes all of the items sent and received by a slot, grouped by item category
class SlotItemCounts:
    def __init__(self) -> None:
        self.sent_items: dict[ItemCategory, int] = defaultdict(int)
        self.received_items: dict[ItemCategory, int] = defaultdict(int)
        self.self_items: dict[ItemCategory, int] = defaultdict(int)


# Multiple classes in ArchipelaDOS require state to be persisted to disk, which is loaded
# on startup. This base class makes it easy to do so, providing the state via a member
# and persistence via a decorator.
class Persisted[T: BaseModel]:

    _state_type: type[T]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._state_type = get_args(get_original_bases(cls)[0])[0]

    def __init__(self, state_file: str) -> None:
        self._state_file = state_file
        self._state = self._load_state()
        self._save_state()

    def _load_state(self) -> T:
        # If the file doesn't exist, return a fresh state.
        if not os.path.exists(self._state_file):
            _log.info(
                "State file '%s' for %s does not exist; starting fresh", self._state_file, self._state_type.__name__
            )
            return self._state_type()

        try:
            with open(self._state_file, "r") as data_file:
                _log.info("Loading state file '%s' for %s", self._state_file, self._state_type.__name__)
                return self._state_type(**json.load(data_file))
        except Exception as ex:
            # If there's a validation (or other) error, back up the invalid file so it can be
            # inspected later, then start fresh.
            _log.error("Failed to load state file '%s' for %s: %s", self._state_file, self._state_type.__name__, ex)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self._state_file.replace(".json", f".invalid_{timestamp}.json")
            os.rename(self._state_file, backup_path)
            _log.info("Backed up invalid state file to '%s'; starting fresh", backup_path)
            return self._state_type()

    def _save_state(self) -> None:
        with open(self._state_file, "w") as data_file:
            data_file.write(self._state.model_dump_json(indent=4))

    @staticmethod
    def persist[U](func: Callable[..., U]) -> Callable[..., U]:
        @functools.wraps(func)
        def _wrapper(self: Self, *args: Any, **kwargs: Any) -> U:
            result = func(self, *args, **kwargs)
            self._save_state()  # pylint: disable = protected-access
            return result

        return _wrapper
