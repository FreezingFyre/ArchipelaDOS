import json
import logging
import re
from collections import defaultdict
from enum import Enum
from typing import Any, Iterator, NamedTuple, Optional

from websockets.typing import Data

from ados.common import (
    ADOSError,
    HintInfo,
    HintStatus,
    ItemCategory,
    ItemInfo,
    LocationInfo,
    SlotInfo,
)

_log = logging.getLogger(__name__)

ARCH_VERSION = "0.6.7"
ARCH_MAJOR, ARCH_MINOR, ARCH_BUILD = [int(part) for part in ARCH_VERSION.split(".")]


class JoinLeaveType(str, Enum):
    JOIN = "join"
    LEAVE = "leave"


class SlotStatus(NamedTuple):
    found_checks: int
    total_checks: int
    goal_completed: bool


def _slot_from_data(player: dict[str, Any], slots_info: dict[str, Any]) -> SlotInfo:
    alias = player["alias"].replace(f"({player["name"]})", "").strip()
    game = slots_info[str(player["slot"])]["game"]
    return SlotInfo(id=player["slot"], name=player["name"], alias=alias, game=game)


################################################
############### CLIENT MESSAGES ################
################################################


# Sent to the server to initiate a connection after receiving the RoomInfo message.
def connect_message(*, game: str, slot: str) -> str:
    return json.dumps(
        [
            {
                "cmd": "Connect",
                "password": None,
                "game": game,
                "name": slot,
                "uuid": "ArchipelaDOS",
                "version": {"major": ARCH_MAJOR, "minor": ARCH_MINOR, "build": ARCH_BUILD, "class": "Version"},
                "items_handling": 0b000,
                "tags": ["TextOnly", "DeathLink"],
                "slot_data": False,
            }
        ]
    )


# Sent to the server to request the data package for the multiworld.
def get_data_package_message(games: list[str]) -> str:
    return json.dumps(
        [
            {
                "cmd": "GetDataPackage",
                "games": games,
            }
        ]
    )


# Sent to the server to request item groups for games in the multiworld.
def get_item_groups_message(games: list[str]) -> str:
    return json.dumps(
        [
            {
                "cmd": "Get",
                "keys": [f"_read_item_name_groups_{game}" for game in games],
            }
        ]
    )


# Sent to the server to request information about current hints or hint point levels.
def get_hint_message() -> str:
    return json.dumps([{"cmd": "Say", "text": "!hint"}])


# Sent to the server to request a hint for a particular item.
def get_hint_item_message(item_name: str) -> str:
    return json.dumps([{"cmd": "Say", "text": f"!hint {item_name}"}])


# Sent to the server to request a hint for what is at a particular location.
def get_hint_location_message(location_name: str) -> str:
    return json.dumps([{"cmd": "Say", "text": f"!hint_location {location_name}"}])


# Sent to the server to request found/total check counts per slot.
def get_status_message() -> str:
    return json.dumps([{"cmd": "Say", "text": "!status"}])


################################################
############### SERVER MESSAGES ################
################################################


# Sent by the server after the client establishes a websocket connection.
class RoomInfoMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.games: list[str] = data["games"]


# Sent by the server in response to a GetDataPackage message.
class DataPackageMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.game_items: dict[str, list[ItemInfo]] = {}
        self.game_locations: dict[str, list[LocationInfo]] = {}
        for game, game_data in data["data"]["games"].items():
            self.game_items[game] = [ItemInfo(id, name, game) for name, id in game_data["item_name_to_id"].items()]
            self.game_locations[game] = [
                LocationInfo(id, name, game) for name, id in game_data["location_name_to_id"].items()
            ]


# Sent by the server in response to a Connect message if the connection is successful.
class ConnectedMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.slot_id = int(data["slot"])
        self.slots = [_slot_from_data(info, data["slot_info"]) for info in data["players"]]


# Sent by the server in response to a Connect message if the connection is unsuccessful.
class ConnectionRefusedMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.errors: list[str] = data.get("errors", [])


# Sent internally by the websocket client when the connection to Archipelago is closed.
class ConnectionClosedMessage:
    pass


# Sent by the server when the room information is updated -- particularly slot aliases.
class RoomUpdateMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.slots = [_slot_from_data(info, data["slot_info"]) for info in data["players"]]


# Sent by the server when returning information about item groups for its games.
class ItemGroupsMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.game_groups: dict[str, list[str]] = defaultdict(list)
        self.game_item_groups: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for game_key, groups in data["keys"].items():
            game = game_key.replace("_read_item_name_groups_", "")
            for group, item_names in groups.items():
                if len(item_names) < 2:
                    # No sense bothering with single-item groups.
                    continue
                self.game_groups[game].append(group)
                for item_name in item_names:
                    self.game_item_groups[game][item_name].append(group)


# Sent by the server when one slot sends an item to another slot.
class ItemSendMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        item_data = data["item"]

        self.item_id: int = item_data["item"]
        self.location_id: int = item_data["location"]
        self.to_slot_id: int = data["receiving"]
        self.from_slot_id: int = item_data["player"]

        self.category = ItemCategory.FILLER
        category_flag = item_data["flags"]
        for category in (ItemCategory.TRAP, ItemCategory.PROGRESSION, ItemCategory.USEFUL):
            if category_flag & category:
                self.category = category
                break


# Sent by the server when a slot triggers a death link.
class DeathLinkMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.slot_name: str = data["data"]["source"]


# Sent by the server when a slot connects or disconnects.
class JoinLeaveMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.slot_id: int = data["slot"]
        self.join_or_leave: JoinLeaveType = JoinLeaveType.JOIN if data["type"] == "Join" else JoinLeaveType.LEAVE


# Sent by the server when a player sends a chat message.
class PlayerChatMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.slot_id: int = data["slot"]
        self.message: str = data["message"]


# Sent by the server when the server sends a global chat message.
class ServerChatMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.message: str = data["message"]


# Sent by the server when a player reaches their goal.
class GoalReachedMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.slot_id: int = data["slot"]


# Sent by the server when a game's items are being released (either by goal completion or)
# manual release by an admin.
class SlotReleaseMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.slot_id: int = data["slot"]


# Sent by the server to notify a client of the hint points available/required in for a slot.
class HintPointsMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        text = data["data"][0]["text"]
        match = re.search(r"A hint costs (\d+) points?\. You have (\d+) points?\.", text)
        if not match:
            raise ADOSError(f"Unexpected hint points message format: {text}")
        self.points_required = int(match.group(1))
        self.points_available = int(match.group(2))


# Sent by the server to notify a client of a collection of hints for a slot.
class HintsMessage:

    class Result(str, Enum):
        SUCCESS = "success"
        NOT_FOUND = "not found"
        NO_POINTS = "no points"

    def __init__(self, data: Optional[list[dict[str, Any]]] = None, result: Result = Result.SUCCESS) -> None:
        def _get_status(info: dict[str, Any]) -> HintStatus:
            for info_element in info.get("data", [])[::-1]:
                if "hint_status" in info_element:
                    return HintStatus(info_element["hint_status"])
            return HintStatus.UNSPECIFIED

        self.hints = [
            HintInfo(
                item_id=info["item"]["item"],
                location_id=info["item"]["location"],
                to_slot_id=info["receiving"],
                from_slot_id=info["item"]["player"],
                found=info["found"],
                status=_get_status(info),
            )
            for info in data or []
        ]
        self.result = result


# Sent by the server in response to a status request, outlining the found/total check counts for all slots.
class StatusMessage:
    def __init__(self, data: dict[str, Any]) -> None:
        self.statuses: dict[str, SlotStatus] = {}
        text: str = data["data"][0]["text"]
        for line in text.splitlines():
            match = re.match(r"(.*) has \d+ connect.*\((\d+)/(\d+)\)", line)
            if not match or match.group(3) == "0":  # Don't bother with slots with no checks (like the bot itself).
                continue
            found_checks = int(match.group(2))
            total_checks = int(match.group(3))

            self.statuses[match.group(1)] = SlotStatus(
                found_checks=found_checks, total_checks=total_checks, goal_completed=(" has finished. " in line)
            )


type ServerMessage = (
    RoomInfoMessage
    | DataPackageMessage
    | ConnectedMessage
    | ConnectionRefusedMessage
    | ConnectionClosedMessage
    | RoomUpdateMessage
    | ItemGroupsMessage
    | ItemSendMessage
    | DeathLinkMessage
    | JoinLeaveMessage
    | PlayerChatMessage
    | ServerChatMessage
    | GoalReachedMessage
    | SlotReleaseMessage
    | HintPointsMessage
    | HintsMessage
    | StatusMessage
)

# When received, some messages should indicate to the bot that the room is alive, and should be
# reconnected to if possible.
KEEPALIVE_MESSAGES = (
    ItemSendMessage,
    DeathLinkMessage,
    PlayerChatMessage,
    ServerChatMessage,
    GoalReachedMessage,
    SlotReleaseMessage,
)


# Server messages are sent to connected clients as lists of JSON objects. This deserialize function
# splits each list into the requisite message types and yields them individually. The exception is for
# responses to hint messages, which are bundled into one message type for return.
def deserialize(raw_message: Data) -> Iterator[ServerMessage]:
    try:
        messages = json.loads(raw_message)

        if len(messages) > 0 and all(
            message.get("cmd") == "PrintJSON" and message.get("type") == "Hint" for message in messages
        ):
            yield HintsMessage(messages)
            return

        for message in messages:
            cmd = message["cmd"]

            if cmd == "RoomInfo":
                yield RoomInfoMessage(message)
            elif cmd == "DataPackage":
                yield DataPackageMessage(message)
            elif cmd == "Connected":
                yield ConnectedMessage(message)
            elif cmd == "ConnectionRefused":
                yield ConnectionRefusedMessage(message)
            elif cmd == "RoomUpdate" and "players" in message:
                yield RoomUpdateMessage(message)
            elif cmd == "Retrieved" and all("_read_item_name_groups_" in key for key in message["keys"]):
                yield ItemGroupsMessage(message)
            elif cmd == "PrintJSON" and message.get("type") == "ItemSend":
                yield ItemSendMessage(message)
            elif cmd == "Bounced" and "DeathLink" in message.get("tags", []):
                yield DeathLinkMessage(message)
            elif (
                cmd == "PrintJSON"
                and message.get("type") in {"Join", "Part"}
                and " viewing " not in message.get("data", [{}])[0].get("text", "")
                and " tracking " not in message.get("data", [{}])[0].get("text", "")
            ):
                yield JoinLeaveMessage(message)
            elif cmd == "PrintJSON" and message.get("type") == "Chat" and not message["message"].startswith("!"):
                yield PlayerChatMessage(message)
            elif cmd == "PrintJSON" and message.get("type") == "ServerChat":
                yield ServerChatMessage(message)
            elif cmd == "PrintJSON" and message.get("type") == "Goal":
                yield GoalReachedMessage(message)
            elif cmd == "PrintJSON" and message.get("type") in {"Collect", "Release"}:
                yield SlotReleaseMessage(message)
            elif (
                cmd == "PrintJSON"
                and message.get("type") == "CommandResult"
                and message.get("data", [{}])[0].get("text", "").startswith("A hint costs")
            ):
                yield HintPointsMessage(message)
            elif (
                cmd == "PrintJSON"
                and message.get("type") == "CommandResult"
                and "Nothing found for recognized" in message.get("data", [{}])[0].get("text", "")
            ):
                yield HintsMessage(result=HintsMessage.Result.NOT_FOUND)
            elif (
                cmd == "PrintJSON"
                and message.get("type") == "CommandResult"
                and "You can't afford the hint" in message.get("data", [{}])[0].get("text", "")
            ):
                yield HintsMessage(result=HintsMessage.Result.NO_POINTS)
            elif (
                cmd == "PrintJSON"
                and message.get("type") == "CommandResult"
                and message.get("data", [{}])[0].get("text", "").startswith("Player Status")
            ):
                yield StatusMessage(message)

    except Exception as ex:
        _log.error("Failed to deserialize server message: %s - %s", ex, raw_message)
