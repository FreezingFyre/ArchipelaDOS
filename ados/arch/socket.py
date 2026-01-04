import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Optional

from websockets.asyncio.client import ClientConnection, connect

from ados.arch.messages import *  # pylint: disable = unused-wildcard-import, wildcard-import
from ados.common import ADOSError
from ados.config import ADOSConfig

_log = logging.getLogger(__name__)


# Provides access to the Archipelago socket interface. Establishes a connection in
# the connect method, and allows customization of message handling by adding message
# handlers for specific message types.
class SocketClient:

    def __init__(self, config: ADOSConfig, *, slot_name: str, game: str, fetch_data: bool):
        self._config = config
        self._game = game
        self._slot_name = slot_name
        self._fetch_data = fetch_data

        self._handlers: dict[type[ServerMessage], list[Callable[[Any], Awaitable[None]]]] = defaultdict(list)

        self._socket: Optional[ClientConnection] = None
        self._socket_task: Optional[asyncio.Task[None]] = None
        self._server_url: Optional[str] = None

    async def connect(self, server_url: str) -> None:
        if self._socket is not None:
            assert self._socket_task is not None
            _log.info("Closing existing socket connection to '%s' for slot '%s'", self._server_url, self._slot_name)
            await self._socket.close()
            await self._socket_task

        self._socket = await self._initialize_connection(server_url)
        self._socket_task = asyncio.create_task(self._socket_loop())
        self._server_url = server_url
        _log.info("Established socket connection to '%s' for slot '%s'", self._server_url, self._slot_name)

    # Allows other classes to handle incoming messages. The first argument is the type
    # of message to handle, and the second is the async function to be called when that
    # message is received.
    def add_message_handler(
        self,
        message_type: type[ServerMessage],
        handler: Callable[[Any], Awaitable[None]],
    ) -> None:
        self._handlers[message_type].append(handler)

    async def _initialize_connection(self, server_url: str) -> ClientConnection:
        # The Archipelago handshake consists of:
        #   - Server sends "RoomInfo" message on socket establishment
        #   - Client sends optional "GetDataPackage" message (if fetch_data is True)
        #   - Server responds with "DataPackage" message (if requested)
        #   - Client sends "Connect" message
        #   - Server responds with either "Connected" or "ConnectionRefused" message
        socket = await connect(server_url, max_size=None)
        server_msgs = list(deserialize(await socket.recv()))
        if len(server_msgs) != 1 or not isinstance(server_msgs[0], RoomInfoMessage):
            raise ADOSError("Received invalid room info message from websocket server")
        await self._handle_message(server_msgs[0])

        if self._fetch_data:
            _log.info("Requesting data package from server at '%s' for slot '%s'", server_url, self._slot_name)
            await socket.send(get_data_package_message(server_msgs[0].games))

            server_msgs = list(deserialize(await socket.recv()))
            if len(server_msgs) != 1 or not isinstance(server_msgs[0], DataPackageMessage):
                raise ADOSError("Received invalid data package message from websocket server")
            await self._handle_message(server_msgs[0])

        _log.info("Sending connect message to server at '%s' for slot '%s'", server_url, self._slot_name)
        await socket.send(connect_message(game=self._game, slot=self._slot_name))

        server_msgs = list(deserialize(await socket.recv()))
        if len(server_msgs) != 1 or not isinstance(server_msgs[0], (ConnectedMessage, ConnectionRefusedMessage)):
            raise ADOSError("Received invalid connection response from websocket server")
        if not isinstance(server_msgs[0], ConnectedMessage):
            raise ADOSError("Connection refused by websocket server: " + ", ".join(server_msgs[0].errors))

        _log.info("Successfully connected to websocket server for slot '%s'", self._slot_name)
        await self._handle_message(server_msgs[0])
        return socket

    async def _socket_loop(self) -> None:
        assert self._socket is not None
        async for socket_message in self._socket:
            _log.warning("Received socket message for slot '%s': %s", self._slot_name, str(socket_message))
            for message in deserialize(socket_message):
                await self._handle_message(message)

    async def _handle_message(self, message: ServerMessage) -> None:
        for handler in self._handlers[type(message)]:
            await handler(message)
