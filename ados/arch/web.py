import logging
import re
from typing import Optional

from aiohttp import ClientSession, ClientTimeout

from ados.common import ADOSError
from ados.config import ADOSConfig

_log = logging.getLogger(__name__)

BASE_URL = "archipelago.gg"

TRACKER_REGEX = re.compile(r"This room has a <a href=\"/tracker/(.*)\">Multiworld Tracker</a>")
PORT_REGEX = re.compile(r"running on archipelago.gg with port (\d*)")


# Provides access to the data served by the Archipelago web interface. Stores a cached
# version of some information and will only refresh it when needed, to avoid excessive
# requests to archipelago.gg.
class WebClient:

    def __init__(self, config: ADOSConfig):
        self._room_url = f"https://{BASE_URL}/room/{config.archipelago_room}"
        self._tracker_url: Optional[str] = None
        self._server_url: Optional[str] = None

    @property
    def room_url(self) -> str:
        return self._room_url

    @property
    def tracker_url(self) -> str:
        assert self._tracker_url is not None
        return self._tracker_url

    @property
    def server_url(self) -> str:
        assert self._server_url is not None
        return self._server_url

    async def refresh(self) -> None:

        _log.info("Refreshing web information from '%s'", self.room_url)

        async with ClientSession(timeout=ClientTimeout(5)) as http_session:
            http_ret = await http_session.get(self.room_url)
            if not http_ret.ok:
                raise ADOSError(f"Failed to access room at '{self.room_url}' (status code {http_ret.status})")

            http_text = await http_ret.text()
            tracker_match = TRACKER_REGEX.search(http_text)
            port_match = PORT_REGEX.search(http_text)
            if not tracker_match or not port_match:
                raise ADOSError(f"Failed to parse URL information at '{self.room_url}'")

            self._tracker_url = f"https://{BASE_URL}/tracker/{tracker_match.group(1)}"
            self._server_url = f"wss://{BASE_URL}:{port_match.group(1)}"

        _log.info("Completed web information refresh; server is running at '%s'", self.server_url)
