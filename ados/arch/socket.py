import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional

from websockets.asyncio.client import ClientConnection, connect

from ados.arch.messages import *  # pylint: disable = unused-wildcard-import, wildcard-import
from ados.common import ADOSError
from ados.config import ADOSConfig

_log = logging.getLogger(__name__)


# Provides access to the Archipelago socket interface. Establishes a connection in
# the connect method, and allows customization of message handling by overriding the
# on_connect and on_message methods.
class SocketClientBase(ABC):

    def __init__(self, config: ADOSConfig, game: str, slot: str):
        self._config = config
        self._game = game
        self._slot = slot

        self._socket: Optional[ClientConnection] = None
        self._socket_task: Optional[asyncio.Task[None]] = None
        self._server_url: Optional[str] = None

    # Notify that the connection has been established successfully
    @abstractmethod
    async def on_connect(self, message: ConnectedMessage) -> None:
        pass

    # Handle an incoming server message
    @abstractmethod
    async def on_message(self, message: ServerMessage) -> None:
        pass

    async def connect(self, server_url: str) -> None:
        if self._socket is not None:
            assert self._socket_task is not None
            _log.info("Closing existing socket connection to '%s' for slot '%s'", self._server_url, self._slot)
            await self._socket.close()
            await self._socket_task

        self._socket = await self._initialize_connection(server_url)
        self._socket_task = asyncio.create_task(self._socket_loop())
        self._server_url = server_url
        _log.info("Established socket connection to '%s' for slot '%s'", self._server_url, self._slot)

    async def _initialize_connection(self, server_url: str) -> ClientConnection:
        # The Archipelago handshake consists of:
        #   - Server sends "RoomInfo" message
        #   - Client responds with "Connect" message
        #   - Server responds with either "Connected" or "ConnectionRefused" message
        socket = await connect(server_url)
        server_msgs = list(deserialize(await socket.recv()))
        if len(server_msgs) != 1 or not isinstance(server_msgs[0], RoomInfoMessage):
            raise ADOSError("Received invalid room info message from websocket server")

        _log.info("Sending connect message to server at '%s' for slot '%s'", server_url, self._slot)
        await socket.send(connect_message(game=self._game, slot=self._slot))

        server_msgs = list(deserialize(await socket.recv()))
        if len(server_msgs) != 1 or not isinstance(server_msgs[0], (ConnectedMessage, ConnectionRefusedMessage)):
            raise ADOSError("Received invalid connection response from websocket server")
        if not isinstance(server_msgs[0], ConnectedMessage):
            raise ADOSError("Connection refused by websocket server: " + ", ".join(server_msgs[0].errors))

        _log.info("Successfully connected to websocket server for slot '%s'", self._slot)
        await self.on_connect(server_msgs[0])
        return socket

    async def _socket_loop(self) -> None:
        assert self._socket is not None
        async for socket_message in self._socket:
            _log.debug("Received socket message for slot '%s': %s", self._slot, str(socket_message))
            for message in deserialize(socket_message):
                await self.on_message(message)


# The primary socket client for the ArchipelaDOS bot. Maintains a connection for the
# entirety of the bot's life, and tracks/forwards messages from the server.
class WorldSocketClient(SocketClientBase):

    def __init__(self, config: ADOSConfig):
        super().__init__(config, "Archipelago", config.archipelago_slot)
        self._slots_by_id: dict[int, SlotInfo] = {}
        self._slots_by_name: dict[str, SlotInfo] = {}

    @property
    def slots(self) -> list[SlotInfo]:
        return list(self._slots_by_id.values())

    async def on_connect(self, message: ConnectedMessage) -> None:
        self._update_slots(message.slots)

    async def on_message(self, message: ServerMessage) -> None:
        if isinstance(message, RoomUpdateMessage):
            self._update_slots(message.slots)

    # Resolve a slot to its SlotInfo by either ID or name/alias
    def resolve_slot(self, input: int | str) -> SlotInfo:
        if isinstance(input, int):
            if input not in self._slots_by_id:
                raise ADOSError(f"Slot ID {input} does not exist in the multiworld")
            return self._slots_by_id[input]

        input_lower = input.lower()
        if input_lower not in self._slots_by_name:
            raise ADOSError(f"Slot '{input}' does not exist in the multiworld")
        return self._slots_by_name[input_lower]

    # Update the internal slot mappings, either on startup or as a result of a RoomUpdate
    # message from the server
    def _update_slots(self, new_slots: list[SlotInfo]) -> None:
        self._slots_by_id = {}
        self._slots_by_name = {}
        for slot in new_slots:
            self._slots_by_id[slot.id] = slot
            # We index slots by both name and alias, so that users can refer to either
            self._slots_by_name[slot.name.lower()] = slot
            self._slots_by_name[slot.alias.lower()] = slot
