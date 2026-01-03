import json
import logging
from typing import Any, Iterator

from websockets.typing import Data

from ados.common import SlotInfo

_log = logging.getLogger(__name__)

ARCH_VERSION = "0.6.5"
ARCH_MAJOR, ARCH_MINOR, ARCH_BUILD = [int(part) for part in ARCH_VERSION.split(".")]


def _slot_from_data(data: dict[str, Any]) -> SlotInfo:
    alias = data["alias"].replace(f"({data["name"]})", "").strip()
    return SlotInfo(id=data["slot"], name=data["name"], alias=alias)


################################################
############### CLIENT MESSAGES ################
################################################


def serialize(message: dict[str, Any]) -> str:
    return json.dumps([message])


# Sent to the server to initiate a connection after receiving the RoomInfo message
def connect_message(*, game: str, slot: str) -> str:
    return serialize(
        {
            "cmd": "Connect",
            "password": None,
            "game": game,
            "name": slot,
            "uuid": "ArchipelaDOS",
            "version": {"major": ARCH_MAJOR, "minor": ARCH_MINOR, "build": ARCH_BUILD, "class": "Version"},
            "items_handling": 0b000,
            "tags": ["TextOnly", "Tracker", "DeathLink"],
            "slot_data": False,
        }
    )


################################################
############### SERVER MESSAGES ################
################################################


# Sent by the server after the client establishes a websocket connection
class RoomInfoMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        pass


# Sent by the server in response to a Connect message if the connection is successful
class ConnectedMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.slot_id = int(data["slot"])
        self.slots = [_slot_from_data(info) for info in data["players"]]


# Sent by the server in response to a Connect message if the connection is unsuccessful
class ConnectionRefusedMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.errors: list[str] = data.get("errors", [])


# Sent by the server when the room information is updated -- particularly slot aliases
class RoomUpdateMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.slots = [_slot_from_data(info) for info in data["players"]]


type ServerMessage = RoomInfoMessage | ConnectedMessage | ConnectionRefusedMessage | RoomUpdateMessage


def deserialize(raw_message: Data) -> Iterator[ServerMessage]:
    for data in json.loads(raw_message):
        try:
            cmd = data.get("cmd", None)
            if cmd is None:
                _log.warning("Received server message without 'cmd' field: %s", data)
                continue

            if cmd == "RoomInfo":
                yield RoomInfoMessage(data)
            elif cmd == "Connected":
                yield ConnectedMessage(data)
            elif cmd == "ConnectionRefused":
                yield ConnectionRefusedMessage(data)
            elif cmd == "RoomUpdate" and "players" in data:
                yield RoomUpdateMessage(data)

        except Exception as ex:
            _log.error("Failed to deserialize server message: %s - %s", ex, data)
