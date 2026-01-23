import os
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


def _transform_logging_level(value: Any) -> int:
    try:
        return getLevelNamesMapping()[str(value).upper()]
    except KeyError as ex:
        raise ValueError(f"invalid logging level '{value}'") from ex


def _expand_path(value: Optional[str]) -> Optional[str]:
    return os.path.abspath(value) if value is not None else None


class LoggingBehavior(str, Enum):
    NONE = "none"
    CONSOLE_ONLY = "console_only"
    FILE_OVERWRITE = "file_overwrite"
    FILE_APPEND = "file_append"
    FILE_DIRECTORY = "file_directory"


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


# The main configuration class for ArchipelaDOS. Loaded from a YAML file on startup with strict
# validation enforced by pydantic
class ADOSConfig(BaseModel):

    archipelago_room: str
    archipelago_slot: str
    archipelago_game: str
    data_path: Annotated[str, BeforeValidator(_expand_path)]
    death_link_messages_path: Annotated[Optional[str], BeforeValidator(_expand_path)]

    # Token is marked with exclude=True, repr=False to avoid accidental logging or exposure
    discord_token: str = Field(..., exclude=True, repr=False)
    discord_server: str
    discord_command_channels: set[str]
    discord_broadcast_channels: dict[str, set[BroadcastCategory]]

    logging_behavior: LoggingBehavior
    logging_path: Annotated[Optional[str], BeforeValidator(_expand_path)]
    logging_level: Annotated[int, BeforeValidator(_transform_logging_level)]
    logging_color: bool

    # Serializes the int logging level to a string when dumping to JSON or other formats
    @field_serializer("logging_level")
    def _serialize_logging_level(self, level: int) -> str:
        return getLevelName(level)

    # Validate the logging path is set when needed, and that the broadcast channel configs
    # are valid (only one item category filter is set per channel)
    @model_validator(mode="after")
    def _validate_logging(self) -> Self:
        if self.logging_behavior not in (LoggingBehavior.NONE, LoggingBehavior.CONSOLE_ONLY):
            if not self.logging_path:
                raise ValueError("logging_path must be set for the selected logging_behavior")

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

        return self


def load_config(path: str) -> ADOSConfig:
    with open(path, "r") as config_file:
        data = yaml.safe_load(config_file)
    return ADOSConfig(**data)
