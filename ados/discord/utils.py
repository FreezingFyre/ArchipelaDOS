from discord.ext import commands

from ados.common import Color

type BotContext = commands.context.Context[commands.Bot]


async def send_info(ctx: BotContext, message: str) -> None:
    await ctx.send(f"```ansi\n{message}```")


async def send_success(ctx: BotContext, message: str) -> None:
    await ctx.send(f"```ansi\n{Color.CYAN}{message}```")


async def send_failure(ctx: BotContext, message: str) -> None:
    await ctx.send(f"```ansi\n{Color.RED}{message}```")
