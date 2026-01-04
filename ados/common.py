from typing import NamedTuple


# Thrown to send a particular error message to the user through Discord.
class ADOSError(Exception):
    pass


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
