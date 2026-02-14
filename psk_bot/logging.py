"""Application logging utilities."""

import logging
import os
from typing import Optional

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(level: Optional[str] = None) -> None:
    """Configure the root logger with sane defaults."""
    resolved_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    if logging.getLogger().handlers:
        # Respect existing configuration if already set up
        return
    logging.basicConfig(level=resolved_level, format=_DEFAULT_FORMAT)


def get_logger(name: str = "psk_bot") -> logging.Logger:
    """Return a namespaced logger, ensuring configuration exists."""
    configure_logging()
    return logging.getLogger(name)
