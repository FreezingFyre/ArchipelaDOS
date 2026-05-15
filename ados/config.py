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


# The main configuration class for ArchipelaDOS. Loaded from a YAML file on startup with strict
# validation enforced by pydantic.
class ADOSConfig(BaseModel):

    # Token is marked with exclude=True, repr=False to avoid accidental logging or exposure.
    discord_token: str = Field(..., exclude=True, repr=False)
    discord_server: str
    discord_command_channels: set[str]
    discord_broadcast_channels: dict[str, set[BroadcastCategory]]

    data_path: Annotated[str, BeforeValidator(_expand_path)]
    death_link_messages_path: Annotated[Optional[str], BeforeValidator(_expand_path)]

    logging_level: Annotated[int, BeforeValidator(_transform_logging_level)]
    logging_color: bool

    # Serializes the int logging level to a string when dumping to JSON or other formats.
    @field_serializer("logging_level")
    def _serialize_logging_level(self, level: int) -> str:
        return getLevelName(level)

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


def load_config(path: str) -> ADOSConfig:
    with open(path, "r") as config_file:
        data = yaml.safe_load(config_file)
    return ADOSConfig(**data)
