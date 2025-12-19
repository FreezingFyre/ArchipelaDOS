import logging
import os
import sys
from datetime import datetime
from ados.config import ADOSConfig

from ados.config import LoggingBehavior


# Formatter for writing to log files and non-colored console output
class _BasicFormatter(logging.Formatter):
    def __init__(self):
        super().__init__("%(asctime)s %(levelname)-8s %(name)s %(message)s")


# Formatter for colored console output
class _ColorFormatter(logging.Formatter):

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

        # Override the traceback to always print in red
        if record.exc_info:
            text = formatter.formatException(record.exc_info)
            record.exc_text = f"\x1b[31m{text}\x1b[0m"

        output = formatter.format(record)

        # Remove the cache layer
        record.exc_text = None
        return output


def initialize_logging(config: ADOSConfig) -> None:

    log = logging.getLogger()

    if config.logging_behavior == LoggingBehavior.NONE:
        log.disabled = True
        return

    # Always output to the console when logging is enabled
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(_ColorFormatter() if config.logging_color else _BasicFormatter())
    log.addHandler(console_handler)
    log.setLevel(config.logging_level)

    if config.logging_behavior == LoggingBehavior.CONSOLE_ONLY:
        return

    assert config.logging_path is not None

    if config.logging_behavior == LoggingBehavior.FILE_DIRECTORY:
        os.makedirs(config.logging_path, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(config.logging_path, f"ados_{timestamp}.log")
    else:
        os.makedirs(os.path.dirname(config.logging_path), exist_ok=True)
        file_path = config.logging_path
    mode = "a" if config.logging_behavior == LoggingBehavior.FILE_APPEND else "w"

    file_handler = logging.FileHandler(file_path, mode=mode)
    file_handler.setFormatter(_BasicFormatter())
    log.addHandler(file_handler)
