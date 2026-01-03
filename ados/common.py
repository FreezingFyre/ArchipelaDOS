from typing import NamedTuple


# Thrown to send a particular error message to the user through Discord.
class ADOSError(Exception):
    pass


# Stores information about a particular slot in the multiworld. The id and name are
# immutable, while the alias may be changed during the session.
class SlotInfo(NamedTuple):
    id: int
    name: str
    alias: str
