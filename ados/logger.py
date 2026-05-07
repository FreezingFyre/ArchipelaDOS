import logging
import os
import sys

from ados.config import ADOSConfig


# Formatter for writing to log files and non-colored console output.
class BasicFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-8s %(name)s %(message)s")


# Formatter for colored console output, shamelessly stolen and adapted from the discord.py project:
# https://github.com/Rapptz/discord.py/blob/9be91cb093402f54a44726c7dc4c04ff3b2c5a63/discord/utils.py#L1303
class ColorFormatter(logging.Formatter):

    LEVEL_COLORS = [
        (logging.DEBUG, "\x1b[40;1m"),
        (logging.INFO, "\x1b[34;1m"),
        (logging.WARNING, "\x1b[33;1m"),
        (logging.ERROR, "\x1b[31m"),
        (logging.CRITICAL, "\x1b[41m"),
    ]

    FORMATS = {
        level: logging.Formatter(
            f"\x1b[30;1m%(asctime)s\x1b[0m {color}%(levelname)-8s\x1b[0m \x1b[35m%(name)s\x1b[0m %(message)s"
        )
        for level, color in LEVEL_COLORS
    }

    def format(self, record: logging.LogRecord) -> str:
        formatter = self.FORMATS.get(record.levelno)
        if formatter is None:
            formatter = self.FORMATS[logging.DEBUG]
        return formatter.format(record)


def initialize_logging(config: ADOSConfig) -> None:

    log = logging.getLogger()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColorFormatter() if config.logging_color else BasicFormatter())
    log.addHandler(console_handler)
    log.setLevel(config.logging_level)

    file_path = os.path.join(config.room_data_path, "ados.log")
    file_handler = logging.FileHandler(file_path, mode="a")
    file_handler.setFormatter(BasicFormatter())
    log.addHandler(file_handler)
