import asyncio
import logging
import os
import re
import shutil
from datetime import datetime, timedelta
from typing import Optional

import discord
from pydantic import BaseModel

from ados.arch.messages import (
    KEEPALIVE_MESSAGES,
    ConnectionClosedMessage,
    ServerMessage,
)
from ados.arch.socket import SocketClient
from ados.arch.web import WebClient
from ados.common import ADOSError, Persisted, SlotInfo
from ados.config import ADOSConfig
from ados.discord.broadcast import MessageBroadcaster
from ados.logger import add_logging_handler, remove_logging_handler
from ados.state import RoomState

_log = logging.getLogger(__name__)

HOSTED_BASE_URL = "archipelago.gg/room"
SOCKET_CLEANUP_INTERVAL = timedelta(minutes=1)
SOCKET_CLEANUP_INACTIVITY_THRESHOLD = timedelta(minutes=5)
HOSTED_INACTIVITY_THRESHOLD = timedelta(hours=12)


# Encodes all the data necessary for ArchipelaDOS to connect to a room. Supports both
# self-hosted rooms and those on archipelago.gg.
class RoomData(BaseModel):
    location: str
    slot: str
    game: str
    password: Optional[str]
    data_path: str


# State type persisted by the ActiveRoomManager, allowing for an unset room.
class ActiveRoomData(BaseModel):
    active_room: Optional[RoomData] = None


# Wraps a room as represented by ArchipelaDOS, with the associated socket connection,
# message broadcaster, and the like. One of these is held by the ActiveRoomManager at
# any given time.
class RoomWrapper:

    def __init__(self, config: ADOSConfig, client: discord.Client, room_data: RoomData) -> None:
        self._log_handler = add_logging_handler(os.path.join(room_data.data_path, "room.log"))

        self._config = config
        self._location = room_data.location
        self._password = room_data.password
        self._web = WebClient(self._location) if HOSTED_BASE_URL in self._location else None
        self._socket = SocketClient(slot_name=room_data.slot, game=room_data.game, password=room_data.password)
        self._state = RoomState(room_data.data_path, self._socket)
        self._broadcaster = MessageBroadcaster(config, self._socket, self._state, client)

        self._slot_sockets: dict[SlotInfo, tuple[datetime, SocketClient]] = {}
        self._sockets_cleanup_task = asyncio.create_task(self._sockets_cleanup_loop())
        self._reconnect_task: Optional[asyncio.Task[None]] = None

        self._last_used = datetime.now()
        self._inactivity_threshold = HOSTED_INACTIVITY_THRESHOLD if self._web is not None else timedelta.max
        self._socket.add_message_handler(ConnectionClosedMessage, self._on_socket_disconnected)

        for message_type in KEEPALIVE_MESSAGES:
            self._socket.add_message_handler(message_type, self._on_keepalive_message)

    @property
    def location(self) -> str:
        return self._location

    @property
    def socket(self) -> SocketClient:
        return self._socket

    @property
    def state(self) -> RoomState:
        return self._state

    @property
    def broadcaster(self) -> MessageBroadcaster:
        return self._broadcaster

    # Always called after construction to allow one-time async setup.
    async def initialize(self) -> None:
        await self._refresh(fetch_data=True)

    # Always called when the room is being disconnected to allow one-time async cleanup.
    async def teardown(self) -> None:
        self._sockets_cleanup_task.cancel()
        for _, slot_socket in list(self._slot_sockets.values()):
            await slot_socket.disconnect()

        if self._reconnect_task is not None:
            self._reconnect_task.cancel()

        await self._socket.disconnect()
        self._broadcaster.stop()
        remove_logging_handler(self._log_handler)

    async def refresh(self) -> None:
        await self._refresh(fetch_data=False)

    def get_info(self) -> dict[str, str]:
        info: dict[str, str] = {}
        if self._web is not None:
            port = self._web.server_url.rsplit(":", maxsplit=1)[-1]
            info["Port"] = port
            info["Room URL"] = f"<{self._web.room_url}>"
            info["Tracker URL"] = f"<{self._web.tracker_url}>"
        else:
            info["Server URL"] = f"<{self._location}>"
        return info

    # For hint commands, a socket needs to be created that will connect to the Archipelago server as
    # that slot. We do not want a connection perpetually open for every slot, but we also want repeated
    # hint commands to not necessarily suffer the cost of connecting to the server every time. So slot-
    # specific sockets are created when needed, and cleaned up after a period of inactivity.
    async def get_slot_socket(self, slot: SlotInfo) -> SocketClient:
        if slot in self._slot_sockets:
            socket = self._slot_sockets[slot][1]
        else:
            _log.info("Creating new socket for slot '%s'", slot)
            socket = SocketClient(slot_name=slot.name, game=slot.game, password=self._password)
            socket.add_message_handler(ConnectionClosedMessage, lambda _: self._slot_sockets.pop(slot, None))
            await socket.connect(self._web.server_url if self._web is not None else self._location, fetch_data=False)
        self._slot_sockets[slot] = (datetime.now(), socket)
        return socket

    # If the room disconnects, we want to make sure it was recently used before attempting a refresh.
    # This function marks the room as recently used.
    def mark_used(self) -> None:
        self._last_used = datetime.now()

    async def _refresh(self, *, fetch_data: bool) -> None:
        location = self._location
        if self._web is not None:
            await self._web.refresh()
            location = self._web.server_url
        await self._socket.connect(location, fetch_data=fetch_data)

    # Socket cleanup logic runs on a regular cadence, defined by the SOCKET_CLEANUP variables.
    async def _sockets_cleanup_loop(self) -> None:

        async def _cleanup_job() -> None:
            for slot in list(self._slot_sockets.keys()):
                last_used, socket = self._slot_sockets[slot]
                if datetime.now() - last_used > SOCKET_CLEANUP_INACTIVITY_THRESHOLD:
                    _log.info("Cleaning up socket for slot '%s' due to inactivity", slot)
                    await socket.disconnect()  # No need to pop socket, as the disconnected callback does this.

        while True:
            try:
                await asyncio.gather(
                    _cleanup_job(),
                    asyncio.sleep(SOCKET_CLEANUP_INTERVAL.total_seconds()),
                )
            except Exception as ex:
                _log.error("Error during socket cleanup: %s", ex)

    # If the socket disconnects, we want to refresh the room and attempt a reconnect before
    # erroring out, assuming the room has been used recently.
    def _on_socket_disconnected(self, message: ConnectionClosedMessage) -> None:
        if message.intended:
            return
        if datetime.now() - self._last_used > self._inactivity_threshold:
            self._broadcaster.admin_alert(
                "Lost connection to Archipelago server after inactivity timeout"
                f" — use `{self._config.discord_command_prefix}room refresh` to reconnect"
                f" or `{self._config.discord_command_prefix}room finalize` to finalize"
            )
            return

        async def _reconnect_task() -> None:
            _log.warning("Socket disconnected; attempting to refresh room and reconnect")
            try:
                await self.refresh()
                _log.info("Socket successfully reconnected after disconnect")
            except Exception as ex:
                _log.error("Failed to reconnect socket after disconnect: %s", ex)
                self._broadcaster.admin_alert(
                    "Lost connection to Archipelago server"
                    f" — use `{self._config.discord_command_prefix}room refresh` to attempt a reconnect"
                )

        self._reconnect_task = asyncio.create_task(_reconnect_task())

    def _on_keepalive_message(self, _: ServerMessage) -> None:
        self.mark_used()


# Manages the bot's active room. Only one room can be active at a time.
class ActiveRoomManager(Persisted[ActiveRoomData]):

    def __init__(self, config: ADOSConfig, client: discord.Client) -> None:
        super().__init__(os.path.join(config.data_path, "room.json"))
        self._config = config
        self._client = client
        self._room: Optional[RoomWrapper] = None
        self._broadcast_guild: Optional[discord.Guild] = None

    @property
    def active_room(self) -> RoomWrapper:
        if self._room is None:
            raise ADOSError("The bot has not been connected to a room")
        self._room.mark_used()
        return self._room

    # Always called after construction to allow one-time async setup. If there was a saved
    # active room, it is initialized as well.
    async def initialize(self) -> None:
        if self._state.active_room is None:
            return
        _log.info("Reconnecting to active room at '%s'", self._state.active_room.location)
        self._room = RoomWrapper(self._config, self._client, self._state.active_room)
        try:
            await self._room.initialize()
        except Exception:
            _log.warning("Could not reconnect to active room at '%s' on startup", self._room.location)
            self._room.broadcaster.admin_alert(
                f"Could not connect to room <{self._room.location}> on startup"
                f" — use `{self._config.discord_command_prefix}room refresh` to attempt a reconnect"
                f" or `{self._config.discord_command_prefix}room finalize` to disconnect from that room"
            )

    async def connect(self, location: str, slot: str, game: str, password: Optional[str]) -> None:
        if self._room is not None:
            raise ADOSError("Cannot connect to a new room until the current room is finalized")

        # Users can specify the location of the room in a variety of ways. Normalize to either
        # https://archipelago.gg/room/<room> or wss://<room>.
        if re.match(r"^[\w-]+$", location):
            location = f"https://{HOSTED_BASE_URL}/{location}"
        elif HOSTED_BASE_URL in location:
            location = f"https://{location.split("://")[-1]}"
        elif "://" not in location:
            location = f"wss://{location}"

        data_path = os.path.join(self._config.data_path, datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(data_path, exist_ok=True)
        new_room_data = RoomData(location=location, slot=slot, game=game, password=password, data_path=data_path)
        new_room = RoomWrapper(self._config, self._client, new_room_data)

        _log.info("Connecting to new room at '%s'", location)
        try:
            await new_room.initialize()
        except Exception as ex:
            # If there's a problem connecting to the room, we do not keep it as active. We also
            # delete its data path.
            _log.error("Issue when attempting to connect to room at '%s': %s", location, ex)
            await new_room.teardown()
            shutil.rmtree(data_path, ignore_errors=True)
            raise ADOSError(f"Failed to connect to new room at <{location}>") from ex

        # Broadcasting can be enabled/disabled orthogonally to the room being connected/disconnected.
        # Start the broadcaster if appropriate.
        if self._broadcast_guild is not None:
            new_room.broadcaster.start(self._broadcast_guild)

        # Only make the room active if all else has succeeded.
        self._update_room(new_room, new_room_data)

    async def disconnect(self) -> None:
        _log.info("Disconnecting from room at '%s'", self.active_room.location)
        room = self.active_room
        self._update_room(None, None)
        await room.teardown()

    def start_broadcasting(self, guild: discord.Guild) -> None:
        self._broadcast_guild = guild
        if self._room is not None:
            self._room.broadcaster.start(guild)

    def stop_broadcasting(self) -> None:
        self._broadcast_guild = None
        if self._room is not None:
            self._room.broadcaster.stop()

    @Persisted.persist
    def _update_room(self, room: Optional[RoomWrapper], room_data: Optional[RoomData]) -> None:
        self._room = room
        self._state.active_room = room_data
