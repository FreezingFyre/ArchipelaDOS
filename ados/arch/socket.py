import asyncio
import logging
from collections import defaultdict
from datetime import timedelta
from typing import Any, Callable, Optional, cast

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

_log = logging.getLogger(__name__)


RETRY_DELAYS = [timedelta(seconds=x) for x in (0, 2, 5, 10, 20)]
MAX_LOG_SIZE = 4096


# Provides access to the Archipelago socket interface. Establishes a connection in
# the connect method, and allows customization of message handling by adding handlers
# for specific message types.
class SocketClient:

    def __init__(self, *, slot_name: str, game: str, password: Optional[str]):
        self._game = game
        self._slot_name = slot_name
        self._password = password

        self._handlers: dict[type[ServerMessage], list[Callable[[Any], Any]]] = defaultdict(list)
        self._request_locks: dict[type[ServerMessage], asyncio.Lock] = defaultdict(asyncio.Lock)
        self._request_futures: dict[type[ServerMessage], asyncio.Future[Any]] = {}

        self._socket: Optional[ClientConnection] = None
        self._socket_task: Optional[asyncio.Task[None]] = None
        self._server_url: Optional[str] = None
        self._disconnecting = False

    async def connect(self, server_url: str, *, fetch_data: bool = False) -> None:
        await self.disconnect()
        self._socket = await self._initialize_connection(server_url, fetch_data)
        self._socket_task = asyncio.create_task(self._socket_loop())
        self._server_url = server_url
        _log.info("Established socket connection to '%s' for slot '%s'", self._server_url, self._slot_name)

    async def disconnect(self) -> None:
        if self._socket is not None:
            _log.info("Closing existing socket connection to '%s' for slot '%s'", self._server_url, self._slot_name)
            try:
                self._disconnecting = True
                await self._socket.close()
                if self._socket_task is not None:
                    await self._socket_task
            finally:
                self._disconnecting = False
        self._socket = None
        self._socket_task = None
        self._server_url = None

    # Allows other classes to handle incoming messages. The first argument is the type
    # of message to handle, and the second is the function to be called when that message
    # is received.
    def add_message_handler(self, message_type: type[ServerMessage], handler: Callable[[Any], Any]) -> None:
        self._handlers[message_type].append(handler)

    # Some messages follow a request-response pattern, though the server still sends the
    # response asynchronously. This function allows sending a message and waiting for a
    # particular response.
    async def perform_request[T: ServerMessage](self, response_type: type[T], message: str) -> T:
        if self._socket is None:
            raise ADOSError("Attempted request while socket is disconnected")

        # Only allow one request per type at a given time, so responses aren't misattributed.
        async with self._request_locks[cast(type[ServerMessage], response_type)]:
            future: asyncio.Future[T] = asyncio.get_running_loop().create_future()
            self._request_futures[cast(type[ServerMessage], response_type)] = future
            await self._socket.send(message)

            try:
                return await asyncio.wait_for(future, timeout=10)
            except asyncio.TimeoutError as ex:
                if cast(type[ServerMessage], response_type) in self._request_futures:
                    self._request_futures.pop(cast(type[ServerMessage], response_type)).cancel()
                _log.warning(
                    "Timed out waiting for response from server at '%s' of type '%s' for message '%s'",
                    self._server_url,
                    response_type,
                    message,
                )
                raise ADOSError(f"Timed out waiting for response from server of type '{response_type}'") from ex

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
            raise ADOSError(f"Failed to connect to websocket server at <{server_url}> after multiple attempts")

        room_info = next(deserialize(await socket.recv()))
        if not isinstance(room_info, RoomInfoMessage):
            raise ADOSError("Received invalid room info message from websocket server")
        self._handle_message(room_info)

        if fetch_data:
            _log.info("Requesting data package from server at '%s' for slot '%s'", server_url, self._slot_name)
            await socket.send(get_data_package_message(room_info.games))

            data_package = next(deserialize(await socket.recv()))
            if not isinstance(data_package, DataPackageMessage):
                raise ADOSError("Received invalid data package message from websocket server")
            self._handle_message(data_package)

        _log.info("Sending connect message to server at '%s' for slot '%s'", server_url, self._slot_name)
        await socket.send(connect_message(game=self._game, slot=self._slot_name, password=self._password))

        connect_response = next(deserialize(await socket.recv()))
        if not isinstance(connect_response, (ConnectedMessage, ConnectionRefusedMessage)):
            raise ADOSError("Received invalid connection response from websocket server")
        if not isinstance(connect_response, ConnectedMessage):
            raise ADOSError("Connection refused by websocket server: " + ", ".join(connect_response.errors))

        _log.info("Successfully connected to websocket server for slot '%s'", self._slot_name)
        self._handle_message(connect_response)

        # If fetching data, we also want to get information about item groups for each game.
        # This response is handled separately with normal message dispatch.
        if fetch_data:
            await socket.send(get_item_groups_message(room_info.games))

        return socket

    async def _socket_loop(self) -> None:
        assert self._socket is not None
        try:
            async for socket_message in self._socket:
                _log.info("Received socket message for slot '%s': %s", self._slot_name, socket_message[:MAX_LOG_SIZE])
                for message in deserialize(socket_message):
                    self._handle_message(message)
        except ConnectionClosedError as ex:
            _log.warning(
                "Connection to websocket server at '%s' for slot '%s' closed: %s", self._server_url, self._slot_name, ex
            )
        except Exception as ex:
            _log.warning(
                "Unexpected error in connection to websocket server at '%s' for slot '%s': %s",
                self._server_url,
                self._slot_name,
                ex,
            )
        self._handle_message(ConnectionClosedMessage(intended=self._disconnecting))

    def _handle_message(self, message: ServerMessage) -> None:
        for handler in self._handlers.get(type(message), []):
            try:
                handler(message)
            except Exception as ex:
                _log.warning("Exception occurred while calling message handler for %s - %s", type(message).__name__, ex)
        if type(message) in self._request_futures:
            self._request_futures.pop(type(message)).set_result(message)
