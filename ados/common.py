from enum import Enum
from typing import Any, Iterable, NamedTuple


# Thrown to send a particular error message to the user through Discord.
class ADOSError(Exception):
    pass


# Joins a list of stringable types with commas, marking the objects with backticks.
def join_objects(objects: Iterable[Any]) -> str:
    object_names = [f"`{obj}`" for obj in objects]
    return ", ".join(sorted(object_names))


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


# Stores information about an items that was sent from one slot to another in
# the multiworld. Do not bother storing full ItemInfo or SlotInfo objects here,
# as this is only used for user-facing outputs.
class SentItemInfo(NamedTuple):
    item_name: str
    location_name: str
    to_slot_id: int
    from_slot_id: int
    category: ItemCategory
