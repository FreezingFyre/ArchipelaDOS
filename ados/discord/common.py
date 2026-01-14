from typing import Any

import discord
from discord.ext import commands
from discord.ext.commands.context import Context

type BotContext = Context[commands.Bot]

COMMAND_PREFIX = "!"
THREAD_NAME = "ArchipelaDOS"

MAX_MESSAGE_SIZE = 2000


# We use a placeholder link to highlight text blue in Discord for some use cases.
def highlight(text: Any) -> str:
    return f"[`{text}`](<https://_>)"


async def send_message(ctx: BotContext, message: str, *, reply: bool = False) -> None:
    await _send_raw(ctx, [message], reply=reply)


async def send_success(ctx: BotContext, message: str, *, reply: bool = False) -> None:
    await _send_raw(ctx, [f":green_circle:  *{message}*"], reply=reply)


async def send_failure(ctx: BotContext, message: str, *, reply: bool = False) -> None:
    await _send_raw(ctx, [f":red_circle:  *{message}*"], reply=reply)


# Sends a table in a monospaced code block. Paginates if necessary to fit within
# Discord's message limits.
async def send_table(ctx: BotContext, table: dict[str, list[str]], *, reply: bool = False) -> None:
    num_rows = len(next(iter(table.values())))
    assert all(len(column) == num_rows for column in table.values())

    column_widths = [max(len(entry) for entry in [header] + column) for header, column in table.items()]

    lines: list[str] = []
    lines.append(" | ".join(header.ljust(width) for header, width in zip(table.keys(), column_widths)) + "\n")
    lines.append("-+-".join("-" * width for width in column_widths) + "\n")

    for row_idx in range(num_rows):
        lines.append(
            " | ".join(column[row_idx].ljust(width) for column, width in zip(table.values(), column_widths)) + "\n"
        )

    max_line_length = max(len(line) for line in lines)
    lines_per_message = (MAX_MESSAGE_SIZE - 6) // max_line_length  # 6 characters for the code block

    messages: list[str] = []
    for idx in range(0, len(lines), lines_per_message):
        chunk = lines[idx : idx + lines_per_message]
        messages.append("```" + "".join(chunk) + "```")
    await _send_raw(ctx, messages, reply=reply)


# For some user commands, we want the ability to reply by starting a thread
# rather than posting directly in the channel.
async def _send_raw(ctx: BotContext, messages: list[str], *, reply: bool) -> None:
    if not reply or isinstance(ctx.channel, (discord.DMChannel, discord.Thread)):
        for message in messages:
            await ctx.send(message)
    else:
        thread = ctx.message.thread
        if thread is None:
            thread = await ctx.message.create_thread(name=THREAD_NAME)
        for message in messages:
            await thread.send(message)
