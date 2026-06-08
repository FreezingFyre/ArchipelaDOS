from enum import Enum, EnumType
from typing import NamedTuple, Optional, cast

from discord.ext import commands
from discord.ext.commands.flags import FlagsMeta

from ados.discord.common import send_failure, send_message


class CommandData(NamedTuple):
    name: str
    brief: str


# We implement our own help command so that we can better expose the sub-command structure
# in the main help output, and provide proper flag names in the per-command help output.
class HelpCommand(commands.HelpCommand):

    def __init__(self, command_prefix: str) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self._command_prefix = command_prefix

    # Called when the main "!help" command is invoked.
    async def send_bot_help(self, mapping: dict[Optional[commands.Cog], list[commands.Command]]) -> None:  # type: ignore[type-arg]

        # For our purposes, we do not care about grouping commands by cog.
        all_commands: list[CommandData] = []
        for _, cog_commands in mapping.items():
            for command in cog_commands:
                name = command.name
                brief = command.brief or command.help or ""
                if isinstance(command, commands.Group):
                    # We want to expose sub-commands in the main help listing, so these get added here.
                    subcommands = [sub.name for sub in sorted(command.commands, key=lambda c: c.extras.get("ord", 0))]
                    name += f" <{ '|'.join(subcommands) }>"
                all_commands.append(CommandData(name, brief))

        message_lines: list[str] = []
        message_lines.append("Available commands:")
        name_len = max(len(data.name) for data in all_commands)
        for data in all_commands:
            padding = " " * (name_len - len(data.name))
            message_lines.append(f"  {self._command_prefix}{data.name}{padding}  {data.brief}")

        message_lines.append(f"\nType '{self._command_prefix}help <command>' for more info on a particular command.")
        message = "\n".join(message_lines)
        await send_message(self.context, f"```{message}```", reply=True)

    # Called when help is requested for a specific command group, i.e. "!help slot".
    async def send_group_help(self, group: commands.Group) -> None:  # type: ignore[type-arg]
        all_commands: list[CommandData] = []
        for command in sorted(group.commands, key=lambda c: c.extras.get("ord", 0)):
            name = command.name
            brief = command.brief or command.help or ""
            all_commands.append(CommandData(name, brief))

        message_lines: list[str] = []
        message_lines.append(f"{self._command_prefix}{group.name}\n")
        if group.help:
            message_lines.append(f"{group.help}\n")
        message_lines.append("Available sub-commands:")

        name_len = max(len(data.name) for data in all_commands)
        for data in all_commands:
            padding = " " * (name_len - len(data.name))
            message_lines.append(f"  {data.name}{padding}  {data.brief}")

        message_lines.append(
            f"\nType '{self._command_prefix}help {group.name} <command>' for more info on a particular command."
        )
        message = "\n".join(message_lines)
        await send_message(self.context, f"```{message}```", reply=True)

    # Called when help is requested for a specific command, i.e. "!help hello" or "!help slot add".
    async def send_command_help(self, command: commands.Command) -> None:  # type: ignore[type-arg]

        # The default signature does not expose flag names properly, so we perform some custom
        # logic to pull flag names out of FlagConverter parameters.
        signature = command.signature
        for param in command.params.values():
            if not isinstance(param.annotation, FlagsMeta):
                continue
            flags: list[str] = []
            for flag_name, flag_details in param.annotation.__commands_flags__.items():
                if isinstance(flag_details.annotation, EnumType):
                    enum_values = "|".join(cast(Enum, e).value for e in flag_details.annotation)  # type: ignore[var-annotated]
                    flag_value = f"<{enum_values}>"
                else:
                    flag_value = f"<{flag_name}>"

                if flag_details.positional:
                    flags.insert(0, flag_value)
                else:
                    flags.append(f"[{flag_name}: {flag_value}]")

            signature = signature.replace(f"<{param.name}>", " ".join(flags))

        message_lines: list[str] = []
        message_lines.append(f"{self._command_prefix}{command.qualified_name} {signature}")
        if command.help:
            message_lines.append(f"\n{command.help}")

        message = "\n".join(message_lines)
        await send_message(self.context, f"```{message}```", reply=True)

    async def send_error_message(self, error: str) -> None:
        await send_failure(self.context, error, reply=True)
