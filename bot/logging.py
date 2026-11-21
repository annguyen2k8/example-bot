"""Centralized logging configuration for ExampleBot."""

from __future__ import annotations

import datetime
import logging
import logging.handlers
import pathlib
from typing import Optional

import discord.utils

LOGGER_NAME = "example_bot"

_managed_terminal_handler: Optional[logging.Handler] = None
_managed_file_handler: Optional[logging.Handler] = None


def setup_logging(
    logs_dir: str = "logs",
    log_level: str = "INFO",
    start_time: Optional[datetime.datetime] = None,
) -> logging.Logger:
    """Configure centralized console and rotating file logging.

    Uses discord.py's native discord.utils.setup_logging for colored terminal output
    and a separate plain-text RotatingFileHandler for disk logging without ANSI codes.

    Args:
        logs_dir: Directory where log files are stored.
        log_level: Minimum logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL').
        start_time: Reference timestamp for log file naming.

    Returns:
        The configured main package logger.
    """
    global _managed_terminal_handler, _managed_file_handler

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()

    # 1. Clean previous example-bot managed handlers to avoid duplicate log entries
    # Carefully avoid removing indiscriminately any handlers managed by other components
    for handler in list(root_logger.handlers):
        if getattr(handler, "_example_bot_managed", False) or handler in (
            _managed_terminal_handler,
            _managed_file_handler,
        ):
            if isinstance(handler, logging.FileHandler):
                try:
                    handler.close()
                except Exception:
                    pass
            root_logger.removeHandler(handler)

    pkg_logger = logging.getLogger(LOGGER_NAME)
    for handler in list(pkg_logger.handlers):
        if getattr(handler, "_example_bot_managed", False) or handler in (
            _managed_terminal_handler,
            _managed_file_handler,
        ):
            if isinstance(handler, logging.FileHandler):
                try:
                    handler.close()
                except Exception:
                    pass
            pkg_logger.removeHandler(handler)
    pkg_logger.propagate = True
    pkg_logger.setLevel(numeric_level)

    # 2. Terminal logging via discord.py native setup_logging with colored terminal formatter
    terminal_handler = logging.StreamHandler()
    terminal_handler._example_bot_managed = True  # type: ignore[attr-defined]
    discord.utils.setup_logging(
        handler=terminal_handler,
        level=numeric_level,
        root=True,
    )
    _managed_terminal_handler = terminal_handler

    # 3. Configure separate rotating file handler in plain text without ANSI escape sequences
    log_path = pathlib.Path(logs_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = (start_time or datetime.datetime.now()).strftime("%Y-%m-%d")
    file_path = log_path / f"{date_str}.log"

    file_formatter = logging.Formatter(
        "[{asctime}] [{levelname:<8}] {name}: {message}",
        datefmt="%Y-%m-%d %H:%M:%S",
        style="{",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(file_path),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler._example_bot_managed = True  # type: ignore[attr-defined]
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    _managed_file_handler = file_handler

    # 4. Tune discord.py logger level (suppress verbose internal gateway chatter unless in debug)
    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(logging.WARNING if numeric_level > logging.DEBUG else logging.DEBUG)

    return get_logger()


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Retrieve the main bot logger or a child sub-logger."""
    if not name:
        return logging.getLogger(LOGGER_NAME)
    if name == LOGGER_NAME or name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
