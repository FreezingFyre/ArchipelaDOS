import asyncio
import logging
from collections import defaultdict
from datetime import timedelta
from typing import Any, Callable, Optional

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosedError

from ados.arch.messages import (
    ConnectedMessage,
    ConnectionClosedMessage,
    ConnectionRefusedMessage,
    DataPackageMessage,
    RoomInfoMessage,
    ServerMessage,
    connect_message,
    deserialize,
    get_data_package_message,
    get_item_groups_message,
)
from ados.common import ADOSError
from ados.config import ADOSConfig

_log = logging.getLogger(__name__)


RETRY_DELAYS = [timedelta(seconds=x) for x in (0, 2, 5, 10, 20)]


# Provides access to the Archipelago socket interface. Establishes a connection in
# the connect method, and allows customization of message handling by adding handlers
# for specific message types.
class SocketClient:

    def __init__(self, config: ADOSConfig, *, slot_name: str, game: str):
        self._config = config
        self._game = game
        self._slot_name = slot_name

        self._handlers: dict[type[ServerMessage], list[Callable[[Any], None]]] = defaultdict(list)

        self._socket: Optional[ClientConnection] = None
        self._socket_task: Optional[asyncio.Task[None]] = None
        self._server_url: Optional[str] = None

    async def connect(self, server_url: str, *, fetch_data: bool = False) -> None:
        if self._socket is not None:
            assert self._socket_task is not None
            _log.info("Closing existing socket connection to '%s' for slot '%s'", self._server_url, self._slot_name)
            await self._socket.close()
            await self._socket_task

        self._socket = await self._initialize_connection(server_url, fetch_data)
        self._socket_task = asyncio.create_task(self._socket_loop())
        self._server_url = server_url
        _log.info("Established socket connection to '%s' for slot '%s'", self._server_url, self._slot_name)

    # Allows other classes to handle incoming messages. The first argument is the type
    # of message to handle, and the second is the function to be called when that message
    # is received.
    def add_message_handler(self, message_type: type[ServerMessage], handler: Callable[[Any], None]) -> None:
        self._handlers[message_type].append(handler)

    async def _initialize_connection(self, server_url: str, fetch_data: bool) -> ClientConnection:
        # The Archipelago handshake consists of:
        #   - Server sends "RoomInfo" message on socket establishment
        #   - Client sends optional "GetDataPackage" message (if fetch_data is True)
        #   - Server responds with "DataPackage" message (if requested)
        #   - Client sends "Connect" message
        #   - Server responds with either "Connected" or "ConnectionRefused" message

        for delay in RETRY_DELAYS:
            try:
                await asyncio.sleep(delay.total_seconds())
                socket = await connect(server_url, max_size=None)
                break
            except Exception as ex:
                _log.warning("Failed to connect to websocket server at '%s': %s", server_url, ex)
        else:
            raise ADOSError(f"Failed to connect to websocket server at '{server_url}' after multiple attempts")

        server_msgs = list(deserialize(await socket.recv()))
        if len(server_msgs) != 1 or not isinstance(server_msgs[0], RoomInfoMessage):
            raise ADOSError("Received invalid room info message from websocket server")
        self._handle_message(server_msgs[0])

        games = server_msgs[0].games.copy()
        if fetch_data:
            _log.info("Requesting data package from server at '%s' for slot '%s'", server_url, self._slot_name)
            await socket.send(get_data_package_message(games))

            server_msgs = list(deserialize(await socket.recv()))
            if len(server_msgs) != 1 or not isinstance(server_msgs[0], DataPackageMessage):
                raise ADOSError("Received invalid data package message from websocket server")
            self._handle_message(server_msgs[0])

        _log.info("Sending connect message to server at '%s' for slot '%s'", server_url, self._slot_name)
        await socket.send(connect_message(game=self._game, slot=self._slot_name))

        server_msgs = list(deserialize(await socket.recv()))
        if len(server_msgs) != 1 or not isinstance(server_msgs[0], (ConnectedMessage, ConnectionRefusedMessage)):
            raise ADOSError("Received invalid connection response from websocket server")
        if not isinstance(server_msgs[0], ConnectedMessage):
            raise ADOSError("Connection refused by websocket server: " + ", ".join(server_msgs[0].errors))

        _log.info("Successfully connected to websocket server for slot '%s'", self._slot_name)
        self._handle_message(server_msgs[0])

        # If fetching data, we also want to get information about item groups for each game.
        # This response is handled separately with normal message dispatch.
        if fetch_data:
            await socket.send(get_item_groups_message(games))

        return socket

    async def _socket_loop(self) -> None:
        assert self._socket is not None
        try:
            async for socket_message in self._socket:
                for message in deserialize(socket_message):
                    self._handle_message(message)
        except ConnectionClosedError as ex:
            _log.warning(
                "Connection to websocket server at '%s' for slot '%s' closed: %s", self._server_url, self._slot_name, ex
            )
        self._handle_message(ConnectionClosedMessage())

    def _handle_message(self, message: ServerMessage) -> None:
        _log.info("Received '%s' message from the server", type(message).__name__)
        for handler in self._handlers.get(type(message), []):
            handler(message)
