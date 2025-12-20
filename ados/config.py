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

    # Token is marked with exclude=True, repr=False to avoid accidental logging or exposure
    discord_token: str = Field(..., exclude=True, repr=False)

    logging_behavior: LoggingBehavior
    logging_path: Optional[str]
    logging_level: Annotated[int, BeforeValidator(_transform_logging_level)]
    logging_color: bool

    # Serializes the int logging level to a string when dumping to JSON or other formats
    @field_serializer("logging_level")
    def _serialize_logging_level(self, level: int) -> str:
        return getLevelName(level)

    # Validate the logging path is set when needed, and massage the path to be absolute
    @model_validator(mode="after")
    def _validate_logging(self) -> Self:
        if self.logging_behavior not in (LoggingBehavior.NONE, LoggingBehavior.CONSOLE_ONLY):
            if not self.logging_path:
                raise ValueError("logging_path must be set for the selected logging_behavior")
        if self.logging_path is not None:
            self.logging_path = os.path.abspath(self.logging_path)
        return self


def load_config(path: str) -> ADOSConfig:
    with open(path, "r") as config_file:
        data = yaml.safe_load(config_file)
    return ADOSConfig(**data)
