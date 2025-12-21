from inspect import Parameter
from typing import NamedTuple, Optional

from discord.ext import commands
from discord.ext.commands.flags import FlagsMeta

from ados.common import Color
from ados.discord.utils import send_failure, send_info


class _CommandData(NamedTuple):
    name: str
    brief: str


# We implement our own help command so that we can better expose the sub-command structure
# in the main help output, and provide proper flag names in the per-command help output
class HelpCommand(commands.HelpCommand):

    # Called when the main "!help" command is invoked
    async def send_bot_help(self, mapping: dict[Optional[commands.Cog], list[commands.Command]]) -> None:  # type: ignore[type-arg]

        # For our purposes, we do not care about grouping commands by cog
        all_commands: list[_CommandData] = []
        for _, cog_commands in mapping.items():
            for command in cog_commands:
                name = command.name
                brief = command.brief or command.help or ""
                if isinstance(command, commands.Group):
                    # We want to expose sub-commands in the main help listing, so these get added here
                    subcommands = [sub.name for sub in command.commands]
                    subcommands.sort()
                    name += f" <{ '|'.join(subcommands) }>"
                all_commands.append(_CommandData(name, brief))
        all_commands.sort(key=lambda data: data.name)

        message_lines: list[str] = []
        message_lines.append("Available commands:")
        name_len = max(len(data.name) for data in all_commands)
        for data in all_commands:
            padding = " " * (name_len - len(data.name))
            message_lines.append(f"  {Color.GREEN}!{data.name}{padding}{Color.RESET}  {data.brief}")

        message_lines.append("\nType '!help <command>' for more info on a particular command.")
        await send_info(self.context, "\n".join(message_lines))

    # Called when help is requested for a specific command group, i.e. "!help slot"
    async def send_group_help(self, group: commands.Group) -> None:  # type: ignore[type-arg]
        all_commands: list[_CommandData] = []
        for command in group.commands:
            name = command.name
            brief = command.brief or command.help or ""
            all_commands.append(_CommandData(name, brief))
        all_commands.sort(key=lambda data: data.name)

        message_lines: list[str] = []
        message_lines.append(f"{Color.GREEN}!{group.name}{Color.RESET}\n")
        if group.help:
            message_lines.append(f"{group.help}\n")
        message_lines.append("Sub-commands:")

        name_len = max(len(data.name) for data in all_commands)
        for data in all_commands:
            padding = " " * (name_len - len(data.name))
            message_lines.append(f"  {Color.GREEN}{data.name}{padding}{Color.RESET}  {data.brief}")

        message_lines.append(f"\nType '!help {group.name} <command>' for more info on a particular command.")
        await send_info(self.context, "\n".join(message_lines))

    # Called when help is requested for a specific command, i.e. "!help hello" or "!help slot add"
    async def send_command_help(self, command: commands.Command) -> None:  # type: ignore[type-arg]

        # The default signature does not expose flag names properly, so we perform some custom
        # logic to pull flag names out of FlagConverter parameters
        signature = command.signature
        for param in command.params.values():
            if param.annotation is Parameter.empty:
                continue
            if not isinstance(param.annotation, FlagsMeta):
                continue
            flags: list[str] = []
            for flag_name in param.annotation.__commands_flags__:
                flags.append(f"[{flag_name}:...]")
            signature = signature.replace(f"<{param.name}>", " ".join(flags))

        message_lines: list[str] = []
        message_lines.append(f"{Color.GREEN}!{command.qualified_name} {signature}{Color.RESET}")
        if command.help:
            message_lines.append(f"\n{command.help}")

        await send_info(self.context, "\n".join(message_lines))

    async def send_error_message(self, error: str) -> None:
        await send_failure(self.context, error)
