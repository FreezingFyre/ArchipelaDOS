from enum import Enum

import discord
from discord.ext import commands

type BotContext = commands.context.Context[commands.Bot]


# Messages from the bot will always be embedded with a different color based on type.
# Below are helper functions to send these messages.
async def _send_message(ctx: BotContext, message: str, color: discord.Color) -> None:
    embed = discord.Embed(description=f"*{message}*", color=color)
    await ctx.send(embed=embed)


async def send_info(ctx: BotContext, message: str) -> None:
    await _send_message(ctx, message, discord.Color.light_grey())


async def send_success(ctx: BotContext, message: str) -> None:
    await _send_message(ctx, message, discord.Color.dark_green())


async def send_failure(ctx: BotContext, message: str) -> None:
    await _send_message(ctx, message, discord.Color.dark_red())
