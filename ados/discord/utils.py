import discord
from discord.ext import commands
from discord.ext.commands.context import Context

type BotContext = Context[commands.Bot]

COMMAND_PREFIX = "!"
THREAD_NAME = "ArchipelaDOS"


# For some user commands, we want the ability to reply by starting a thread
# rather than posting directly in the channel. This is controlled by the 'reply' flag.
async def send_message(ctx: BotContext, message: str, reply: bool = False) -> None:
    if not reply or isinstance(ctx.channel, (discord.DMChannel, discord.Thread)):
        await ctx.send(message)
    else:
        new_thread = await ctx.message.create_thread(name=THREAD_NAME)
        await new_thread.send(message)
        await new_thread.edit(archived=True)


async def send_success(ctx: BotContext, message: str, reply: bool = False) -> None:
    message = f":green_circle:  *{message}*"
    await send_message(ctx, message, reply)


async def send_failure(ctx: BotContext, message: str, reply: bool = False) -> None:
    message = f":red_circle:  *{message}*"
    await send_message(ctx, message, reply)
