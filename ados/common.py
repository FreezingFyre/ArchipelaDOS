from enum import Enum
from typing import NamedTuple


# Thrown to send a particular error message to the user through Discord.
class ADOSError(Exception):
    pass


# Defined levels of item rarity for use in commands and messages.
class ItemRarity(int, Enum):
    PROGRESSION = 0b001
    USEFUL = 0b010
    FILLER = 0b000
    TRAP = 0b100


# Defined filters for item rarity
class ItemRarityFilter(str, Enum):
    PROGRESSION = "progression"
    USEFUL = "useful"
    ALL = "all"


def check_rarity(rarity: ItemRarity, item_filter: ItemRarityFilter) -> bool:
    if rarity == ItemRarity.TRAP:
        return False
    if item_filter == ItemRarityFilter.ALL:
        return True
    if item_filter == ItemRarityFilter.USEFUL:
        return rarity in (ItemRarity.USEFUL, ItemRarity.PROGRESSION)
    if item_filter == ItemRarityFilter.PROGRESSION:
        return rarity == ItemRarity.PROGRESSION
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
    rarity: ItemRarity
