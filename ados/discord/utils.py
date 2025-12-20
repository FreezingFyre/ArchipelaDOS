from enum import Enum

import discord
from discord.ext import commands

type BotContext = commands.context.Context[commands.Bot]


class MessageType(int, Enum):
    SUCCESS = discord.Color.dark_green()
    INFO = discord.Color.light_grey()
    FAILURE = discord.Color.dark_red()


async def send_embed(ctx: BotContext, embed: discord.Embed) -> None:
    await ctx.send(embed=embed)


async def send_message(ctx: BotContext, message: str, message_type: MessageType = MessageType.INFO) -> None:
    embed = discord.Embed(description=f"*{message}*", color=message_type)
    await send_embed(ctx, embed)
