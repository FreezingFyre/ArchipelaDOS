import os
from datetime import timedelta
from enum import Enum
from logging import getLevelName, getLevelNamesMapping
from typing import Annotated, Any, Optional, Self

import yaml
from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    field_serializer,
    model_validator,
)

from ados.common import parse_time_delta


def _transform_logging_level(value: Any) -> int:
    try:
        return getLevelNamesMapping()[str(value).upper()]
    except KeyError as ex:
        raise ValueError(f"invalid logging level '{value}'") from ex


def _expand_path(value: Optional[str]) -> Optional[str]:
    return os.path.abspath(value) if value is not None else None


class BroadcastCategory(str, Enum):
    PROGRESSION_ITEMS = "progression_items"
    USEFUL_ITEMS = "useful_items"
    ALL_ITEMS = "all_items"
    TRAP_ITEMS = "trap_items"
    DEATH_LINKS = "death_links"
    JOIN_LEAVE = "join_leave"
    PLAYER_CHAT = "player_chat"
    SERVER_CHAT = "server_chat"
    GOAL_REACHED = "goal_reached"
    ADMIN_ALERTS = "admin_alerts"


class ExtraCommand(str, Enum):
    DEATHLINK = "deathlink"
    DEATHPOLL = "deathpoll"


# The main configuration class for ArchipelaDOS. Loaded from a YAML file on startup with strict
# validation enforced by pydantic.
class ADOSConfig(BaseModel):

    # Token is marked with exclude=True, repr=False to avoid accidental logging or exposure.
    discord_token: str = Field(..., exclude=True, repr=False)
    discord_server: str
    discord_command_prefix: str
    discord_command_channels: set[str]
    discord_broadcast_channels: dict[str, set[BroadcastCategory]]
    discord_mention_channel_blacklist: set[str]

    extra_commands_enabled: set[ExtraCommand]
    extra_command_cooldowns: Annotated[
        dict[ExtraCommand, timedelta],
        BeforeValidator(lambda data: {command: parse_time_delta(cooldown) for command, cooldown in data.items()}),
    ]

    deathpoll_timeout_default: Annotated[timedelta, BeforeValidator(parse_time_delta)]
    deathpoll_timeout_minimum: Annotated[
        Optional[timedelta], BeforeValidator(lambda d: parse_time_delta(d) if d is not None else None)
    ]
    deathpoll_timeout_maximum: Annotated[
        Optional[timedelta], BeforeValidator(lambda d: parse_time_delta(d) if d is not None else None)
    ]

    deathpoll_yes_emoji_override: Optional[str]
    deathpoll_no_emoji_override: Optional[str]

    data_path: Annotated[str, BeforeValidator(_expand_path)]
    death_link_messages_path: Annotated[Optional[str], BeforeValidator(_expand_path)]

    logging_level: Annotated[int, BeforeValidator(_transform_logging_level)]
    logging_color: bool

    # Serializes the int logging level to a string when dumping to JSON or other formats.
    @field_serializer("logging_level")
    def _serialize_logging_level(self, level: int) -> str:
        return getLevelName(level)

    # Validate that the configured command prefix is a single non-alphanumeric character.
    @model_validator(mode="after")
    def _validate_prefix(self) -> Self:
        if len(self.discord_command_prefix) != 1:
            raise ValueError("command prefix must be a single character")
        if self.discord_command_prefix.isalnum():
            raise ValueError("command prefix cannot be alphanumeric")
        return self

    # Validate that the broadcast channel configs are valid (only one item category filter
    # is set per channel).
    @model_validator(mode="after")
    def _validate_channels(self) -> Self:
        item_categories = {
            BroadcastCategory.PROGRESSION_ITEMS,
            BroadcastCategory.USEFUL_ITEMS,
            BroadcastCategory.ALL_ITEMS,
        }
        for categories in self.discord_broadcast_channels.values():
            if len(item_categories.intersection(categories)) > 1:
                raise ValueError(
                    f"broadcast channel config cannot contain multiple of {[category.value for category in item_categories]}"
                )
        for categories in self.discord_broadcast_channels.values():
            if not categories or BroadcastCategory.ADMIN_ALERTS in categories:
                break
        else:
            raise ValueError("at least one broadcast channel must be configured to receive 'admin_alerts'")
        return self

    # Validate that the default death poll timeout is between the minimum and maximum, if set.
    @model_validator(mode="after")
    def _validate_deathpoll_timeout(self) -> Self:
        if ExtraCommand.DEATHPOLL in self.extra_commands_enabled:
            if self.deathpoll_timeout_default < (self.deathpoll_timeout_minimum or timedelta.min):
                raise ValueError("default deathpoll timeout must be greater than the minimum")
            if self.deathpoll_timeout_default > (self.deathpoll_timeout_maximum or timedelta.max):
                raise ValueError("default deathpoll timeout must be less than the maximum")
        return self


def load_config(path: str) -> ADOSConfig:
    with open(path, "r") as config_file:
        data = yaml.safe_load(config_file)
    return ADOSConfig(**data)
