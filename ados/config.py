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


class LoggingBehavior(str, Enum):
    NONE = "none"
    CONSOLE_ONLY = "console_only"
    FILE_OVERWRITE = "file_overwrite"
    FILE_APPEND = "file_append"
    FILE_DIRECTORY = "file_directory"


# The main configuration class for ArchipelaDOS. Loaded from a YAML file on startup with strict
# validation enforced by pydantic
class ADOSConfig(BaseModel):

    archipelago_room: str
    archipelago_slot: str

    # Token is marked with exclude=True, repr=False to avoid accidental logging or exposure
    discord_token: str = Field(..., exclude=True, repr=False)
    discord_server: str
    discord_channels: list[str]

    data_path: str

    logging_behavior: LoggingBehavior
    logging_path: Optional[str]
    logging_level: Annotated[int, BeforeValidator(_transform_logging_level)]
    logging_color: bool

    # Serializes the int logging level to a string when dumping to JSON or other formats
    @field_serializer("logging_level")
    def _serialize_logging_level(self, level: int) -> str:
        return getLevelName(level)

    # Expand paths to be absolute
    @field_serializer("data_path", "logging_path")
    def _expand_path(self, path: Optional[str]) -> Optional[str]:
        return os.path.abspath(path) if path is not None else None

    # Validate the logging path is set when needed
    @model_validator(mode="after")
    def _validate_logging(self) -> Self:
        if self.logging_behavior not in (LoggingBehavior.NONE, LoggingBehavior.CONSOLE_ONLY):
            if not self.logging_path:
                raise ValueError("logging_path must be set for the selected logging_behavior")
        return self


def load_config(path: str) -> ADOSConfig:
    with open(path, "r") as config_file:
        data = yaml.safe_load(config_file)
    return ADOSConfig(**data)
