import json
import logging
from typing import Any, Iterator

from websockets.typing import Data

from ados.common import SlotInfo

_log = logging.getLogger(__name__)

ARCH_VERSION = "0.6.5"
ARCH_MAJOR, ARCH_MINOR, ARCH_BUILD = [int(part) for part in ARCH_VERSION.split(".")]


################################################
############### CLIENT MESSAGES ################
################################################


def serialize(message: dict[str, Any]) -> str:
    return json.dumps([message])


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


class RoomInfoMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        pass


class ConnectedMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.slots: list[SlotInfo] = [
            SlotInfo(id=info["slot"], name=info["name"], alias=info["alias"]) for info in data["players"]
        ]
        self.slot_id: int = data["slot"]


class ConnectionRefusedMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.errors: list[str] = data.get("errors", [])


type ServerMessage = RoomInfoMessage | ConnectedMessage | ConnectionRefusedMessage


def deserialize(raw_message: Data) -> Iterator[ServerMessage]:
    for data in json.loads(raw_message):
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
