import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, NamedTuple, Optional

from discord.message import Message

from ados.common import parse_hms
from ados.discord.common import BotContext

_log = logging.getLogger(__name__)

MESSAGE = ":clipboard: A death poll has been triggered! React to this message before it expires in {timeout}"
KILL_MESSAGE = ":clipboard: This death poll has expired. Death link triggered {result}"
SAFE_MESSAGE = ":clipboard: This death poll has expired. Death link averted {result}"
CANCEL_MESSAGE = ":clipboard: This death poll was interrupted before it could complete"

YES_EMOJI = "💀"
NO_EMOJI = "😇"


def _describe_timeout(timeout: timedelta) -> str:
    hours, minutes, seconds = parse_hms(timeout.total_seconds())
    descriptors: list[str] = []
    if hours:
        descriptors.append(f"{hours} hour{"" if hours == 1 else "s"}")
    if minutes:
        descriptors.append(f"{minutes} minute{"" if minutes == 1 else "s"}")
    if seconds:
        descriptors.append(f"{seconds} second{"" if seconds == 1 else "s"}")
    return ", ".join(descriptors)


class UpdateTimeData(NamedTuple):
    timestamp: datetime
    timeout_left: timedelta


# Manages the lifecycle of a single death poll. Each death poll is configured with a
# timeout, and will trigger a death link after that amount of time if enough users vote
# in favor.
class DeathPoll:

    def __init__(
        self,
        ctx: BotContext,
        timeout: timedelta,
        on_kill: Callable[[], Awaitable[None]],
        on_completion: Callable[[], Any],
    ) -> None:
        _log.info("Initiating a death poll that expires in %s", _describe_timeout(timeout))
        self._task = asyncio.create_task(self._run_poll(ctx, timeout, on_kill, on_completion))

    def cancel(self) -> None:
        self._task.cancel()

    async def _run_poll(
        self,
        ctx: BotContext,
        timeout: timedelta,
        on_kill: Callable[[], Awaitable[None]],
        on_completion: Callable[[], Any],
    ) -> None:
        message: Optional[Message] = None
        try:
            update_times = self._get_update_times(timeout)
            message = await ctx.send(MESSAGE.format(timeout=_describe_timeout(timeout)))
            await message.add_reaction(YES_EMOJI)
            await message.add_reaction(NO_EMOJI)

            for time in update_times:
                await asyncio.sleep((time.timestamp - datetime.now()).total_seconds())
                if time.timeout_left:
                    await message.edit(content=MESSAGE.format(timeout=_describe_timeout(time.timeout_left)))

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
            on_completion()

        except asyncio.CancelledError:
            if message is not None:
                await message.edit(content=CANCEL_MESSAGE)

    def _get_update_times(self, timeout: timedelta) -> list[UpdateTimeData]:
        times: list[UpdateTimeData] = []
        now_timestamp = datetime.now()
        finish_timestamp = now_timestamp + timeout

        minutes = int(timeout.total_seconds()) // 60
        for minutes_left in range(minutes, 0, -1):
            delta = timedelta(minutes=minutes_left)
            times.append(UpdateTimeData(finish_timestamp - delta, delta))

        seconds = min(50, 10 * (int(timeout.total_seconds()) // 10))
        for seconds_left in range(seconds, 0, -10):
            delta = timedelta(seconds=seconds_left)
            times.append(UpdateTimeData(finish_timestamp - delta, delta))

        times.append(UpdateTimeData(finish_timestamp, timedelta(seconds=0)))
        return times


# Manages death polls initiated by users. Multiple can exist simultaneously.
class DeathPollManager:

    def __init__(self) -> None:
        self._poll_id = 0
        self._polls: dict[int, DeathPoll] = {}

    def create_death_poll(self, ctx: BotContext, timeout: timedelta, on_kill: Callable[[], Awaitable[None]]) -> None:
        poll_id = self._poll_id
        self._poll_id += 1
        self._polls[poll_id] = DeathPoll(ctx, timeout, on_kill, lambda: self._polls.pop(poll_id, None))

    def cancel_all(self) -> None:
        for poll in self._polls.values():
            poll.cancel()
        self._polls.clear()
