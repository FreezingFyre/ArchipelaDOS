import asyncio
import logging
from datetime import datetime, timedelta
from typing import Awaitable, Callable, NamedTuple, Optional

from discord.message import Message

from ados.common import describe_timeout
from ados.discord.common import BotContext

_log = logging.getLogger(__name__)

MESSAGE = ":clipboard: A death poll has been triggered! React to this message before it expires in {timeout}"
KILL_MESSAGE = ":clipboard: This death poll has expired. Death link triggered {result}"
SAFE_MESSAGE = ":clipboard: This death poll has expired. Death link averted {result}"
CANCEL_MESSAGE = ":clipboard: This death poll was interrupted before it could complete"

YES_EMOJI = "💀"
NO_EMOJI = "😇"


class UpdateTimeData(NamedTuple):
    timestamp: datetime
    timeout_left: timedelta


def _get_update_times(timeout: timedelta) -> tuple[datetime, list[UpdateTimeData]]:
    times: list[UpdateTimeData] = []
    now_timestamp = datetime.now()
    finish_timestamp = now_timestamp + timeout

    hours = int(timeout.total_seconds()) // 3600
    for hours_left in range(hours, 1, -1):
        delta = timedelta(hours=hours_left)
        times.append(UpdateTimeData(finish_timestamp - delta, delta))

    minutes = min(119, int(timeout.total_seconds()) // 60)
    for minutes_left in range(minutes, 0, -1):
        delta = timedelta(minutes=minutes_left)
        times.append(UpdateTimeData(finish_timestamp - delta, delta))

    seconds = min(50, 10 * (int(timeout.total_seconds()) // 10))
    for seconds_left in range(seconds, 0, -10):
        delta = timedelta(seconds=seconds_left)
        times.append(UpdateTimeData(finish_timestamp - delta, delta))

    return finish_timestamp, times


# Manages death polls initiated by users. Each death poll is configured with a timeout, and
# will trigger a death link after that amount of time if enough users vote in favor.
class DeathPollManager:

    def __init__(self) -> None:
        self._poll_id = 0
        self._polls: dict[int, asyncio.Task[None]] = {}

    def create_death_poll(self, ctx: BotContext, timeout: timedelta, on_kill: Callable[[], Awaitable[None]]) -> None:
        _log.info("Initiating a death poll that expires in %s", describe_timeout(timeout))
        poll_id = self._poll_id
        self._poll_id += 1
        self._polls[poll_id] = asyncio.create_task(self._run_poll(poll_id, ctx, timeout, on_kill))

    def cancel_all(self) -> None:
        if not self._polls:
            return
        _log.info("Flushing all active death polls")
        for poll in self._polls.values():
            poll.cancel()
        self._polls.clear()

    async def _run_poll(
        self,
        poll_id: int,
        ctx: BotContext,
        timeout: timedelta,
        on_kill: Callable[[], Awaitable[None]],
    ) -> None:
        message: Optional[Message] = None
        try:
            finish_timestamp, update_times = _get_update_times(timeout)
            message = await ctx.send(MESSAGE.format(timeout=describe_timeout(timeout)))
            await message.add_reaction(YES_EMOJI)
            await message.add_reaction(NO_EMOJI)

            # Each of these represents a time when the poll message should be updated.
            for time in update_times:
                await asyncio.sleep((time.timestamp - datetime.now()).total_seconds())
                await message.edit(content=MESSAGE.format(timeout=describe_timeout(time.timeout_left)))

            # Wait the final amount of time before collecting results.
            await asyncio.sleep((finish_timestamp - datetime.now()).total_seconds())

            message = await ctx.fetch_message(message.id)
            votes = {str(reaction.emoji): reaction.count for reaction in message.reactions}
            votes_yes = votes.get(YES_EMOJI, 1) - 1
            votes_no = votes.get(NO_EMOJI, 1) - 1
            will_kill = votes_yes > votes_no

            _log.info("Death poll concluded with kill status %s: %d to %d", str(will_kill), votes_yes, votes_no)

            if will_kill:
                await on_kill()
            result_text = (KILL_MESSAGE if will_kill else SAFE_MESSAGE).format(result=f"{votes_yes}-{votes_no}")
            await message.edit(content=result_text)
            self._polls.pop(poll_id, None)

        except asyncio.CancelledError:
            if message is not None:
                await message.edit(content=CANCEL_MESSAGE)
