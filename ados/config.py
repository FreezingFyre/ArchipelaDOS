import os
from enum import Enum
from logging import getLevelNamesMapping
from typing import Annotated, Any, Optional, Self

import yaml
from pydantic import BaseModel, BeforeValidator, model_validator


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


class ADOSConfig(BaseModel):
    discord_token: str

    logging_behavior: LoggingBehavior
    logging_path: Optional[str]
    logging_level: Annotated[int, BeforeValidator(_transform_logging_level)]
    logging_color: bool

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
    config = ADOSConfig(**data)
    return config
