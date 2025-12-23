#     self._connection_info: Optional[ConnectionInfo] = None

# async def __aenter__(self) -> Self:
#     self._http_session = ClientSession(timeout=ClientTimeout(5))
#     await self.refresh()
#     return self

# async def __aexit__(self, *_: Any) -> None:
#     await self._http_session.close()

# async def refresh(self) -> ConnectionInfo:
#     room_url = f"{BASE_URL}/room/{self._config.archipelago_room}"
#     http_ret = await self._http_session.get(room_url)
#     if not http_ret.ok:
#         raise ADOSError(f"Failed to access room at '{room_url}' (status code {http_ret.status})")

#     TRACKER_REGEX = re.compile(r"This room has a <a href=\"/tracker/(.*)\">Multiworld Tracker</a>")
#     PORT_REGEX = re.compile(r"running on archipelago.gg with port (\d*)")
#     http_text = await http_ret.text()

#     tracker_match = TRACKER_REGEX.search(http_text)
#     port_match = PORT_REGEX.search(http_text)
#     if not tracker_match or not port_match:
#         raise ADOSError(f"Failed to parse room page at '{room_url}'")

#     tracker_url = f"{BASE_URL}/tracker/{tracker_match.group(1)}"
#     server_url = f"wss://archipelago.gg:{port_match.group(1)}"
#     connection_info = ConnectionInfo(room_url, tracker_url, server_url)
#     async with self._lock:
#         self._connection_info = connection_info
#     return connection_info
