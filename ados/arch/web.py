import logging
import re
from typing import NamedTuple, Optional

from aiohttp import ClientSession, ClientTimeout

from ados.common import ADOSError
from ados.config import ADOSConfig

_log = logging.getLogger(__name__)

BASE_URL = "archipelago.gg"

TRACKER_REGEX = re.compile(r"This room has a <a href=\"/tracker/(.*)\">Multiworld Tracker</a>")
PORT_REGEX = re.compile(r"running on archipelago.gg with port (\d*)")
SLOT_ID_REGEX = re.compile(r"^\s*\d+\s*$")
COMPLETION_REGEX = re.compile(r"^\s*\d+/\d+\s*$")

CHECK_START_SENTINEL = "This tracker will automatically update itself"
CHECK_END_SENTINEL = "<td>All Games</td>"


class CheckCounts(NamedTuple):
    found: int
    total: int
    percent: int


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
            http_ret = await http_session.get(f"{self.room_url}?update")
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

    async def fetch_slot_check_counts(self) -> dict[int, CheckCounts]:

        check_counts: dict[int, CheckCounts] = {}
        _log.info("Fetching slot check completion info from tracker at '%s'", self.tracker_url)

        async with ClientSession(timeout=ClientTimeout(5)) as http_session:
            http_ret = await http_session.get(self.tracker_url)
            if not http_ret.ok:
                raise ADOSError(f"Failed to access tracker at '{self.tracker_url}' (status code {http_ret.status})")

            next_slot_id: Optional[int] = -1
            async for line in http_ret.content:
                line_text = line.decode()
                if CHECK_START_SENTINEL in line_text:
                    next_slot_id = None
                    continue
                if CHECK_END_SENTINEL in line_text:
                    break

                if re.match(SLOT_ID_REGEX, line_text):
                    next_slot_id = int(line_text.strip())
                elif re.match(COMPLETION_REGEX, line_text) and next_slot_id is not None:
                    found_str, total_str = line_text.strip().split("/")
                    found, total = int(found_str), int(total_str)
                    percent = int(found / total * 100) if total > 0 else 0
                    check_counts[next_slot_id] = CheckCounts(found, total, percent)
                    next_slot_id = None

        _log.info("Completed fetching slot check completion info")
        return check_counts
