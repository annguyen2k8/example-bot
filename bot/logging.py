"""Centralized logging configuration for ExampleBot."""

from __future__ import annotations

import datetime
import logging
import logging.handlers
import pathlib
from typing import Optional

LOGGER_NAME = "example_bot"


def setup_logging(
    logs_dir: str = "logs",
    log_level: str = "INFO",
    start_time: Optional[datetime.datetime] = None,
) -> logging.Logger:
    """Configure centralized console and rotating file logging.

    Args:
        logs_dir: Directory where log files are stored.
        log_level: Minimum logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR').
        start_time: Reference timestamp for log file naming.

    Returns:
        The configured root or package logger.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    log_path = pathlib.Path(logs_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = (start_time or datetime.datetime.now()).strftime("%Y-%m-%d")
    file_path = log_path / f"{date_str}.log"

    formatter = logging.Formatter(
        "[{asctime}] [{levelname:<8}] {name}: {message}",
        datefmt="%Y-%m-%d %H:%M:%S",
        style="{",
    )

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(numeric_level)
    logger.propagate = False

    # Remove existing handlers on our logger to avoid duplicate log messages
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Rotating file handler (10MB per file, max 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(file_path),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Also tune discord.py logger to not flood unless in debug
    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.WARNING if numeric_level > logging.DEBUG else logging.DEBUG)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Retrieve the main bot logger or a child sub-logger."""
    if not name:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
