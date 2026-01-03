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

    @abstractmethod
    async def on_connect(self, message: ConnectedMessage) -> None:
        pass

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
            raise ADOSError("Received invalid room info message from Archipelago server")

        _log.info("Sending connect message to server at '%s' for slot '%s'", server_url, self._slot)
        await socket.send(connect_message(game=self._game, slot=self._slot))

        server_msgs = list(deserialize(await socket.recv()))
        if len(server_msgs) != 1 or not isinstance(server_msgs[0], (ConnectedMessage, ConnectionRefusedMessage)):
            raise ADOSError("Received invalid connection response from Archipelago server")
        if not isinstance(server_msgs[0], ConnectedMessage):
            raise ADOSError("Connection refused by Archipelago server: " + ", ".join(server_msgs[0].errors))

        await self.on_connect(server_msgs[0])
        return socket

    async def _socket_loop(self) -> None:
        assert self._socket is not None
        async for message in self._socket:
            print(message)


class WorldSocketClient(SocketClientBase):

    def __init__(self, config: ADOSConfig):
        super().__init__(config, "Archipelago", config.archipelago_slot)

    async def on_connect(self, message: ConnectedMessage) -> None:
        pass

    async def on_message(self, message: ServerMessage) -> None:
        pass
