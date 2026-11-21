"""Tests for centralized logging configuration and discord.py logging integration in ExampleBot."""

from __future__ import annotations

import logging
import logging.handlers
import pathlib
from unittest.mock import patch
import discord.utils
import pytest

from bot.logging import LOGGER_NAME, get_logger, setup_logging


def test_get_logger_naming() -> None:
    """Ensure get_logger resolves correctly under example_bot hierarchy."""
    assert LOGGER_NAME == "example_bot"
    root_pkg_logger = get_logger()
    assert root_pkg_logger.name == "example_bot"

    child_logger = get_logger("client")
    assert child_logger.name == "example_bot.client"

    nested_logger = get_logger("cogs.example")
    assert nested_logger.name == "example_bot.cogs.example"

    full_name_logger = get_logger("example_bot.database")
    assert full_name_logger.name == "example_bot.database"


def test_setup_logging_avoids_duplicate_handlers(tmp_path: pathlib.Path) -> None:
    """Ensure calling setup_logging multiple times does not duplicate handlers."""
    root = logging.getLogger()

    setup_logging(logs_dir=str(tmp_path), log_level="INFO")
    count_first = len(root.handlers)
    managed_stream_count_first = sum(
        1
        for h in root.handlers
        if getattr(h, "_example_bot_managed", False)
        and isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
    )
    managed_file_count_first = sum(
        1 for h in root.handlers if getattr(h, "_example_bot_managed", False) and isinstance(h, logging.FileHandler)
    )

    assert managed_stream_count_first == 1
    assert managed_file_count_first == 1

    # Call setup_logging a second time
    setup_logging(logs_dir=str(tmp_path), log_level="INFO")
    count_second = len(root.handlers)
    managed_stream_count_second = sum(
        1
        for h in root.handlers
        if getattr(h, "_example_bot_managed", False)
        and isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
    )
    managed_file_count_second = sum(
        1 for h in root.handlers if getattr(h, "_example_bot_managed", False) and isinstance(h, logging.FileHandler)
    )

    assert count_first == count_second
    assert managed_stream_count_second == 1
    assert managed_file_count_second == 1


def test_setup_logging_preserves_external_handlers(tmp_path: pathlib.Path) -> None:
    """Ensure setup_logging does not indiscriminately remove handlers managed by other tools."""
    root = logging.getLogger()
    external_handler = logging.StreamHandler()
    external_handler.set_name("third_party_tool_handler")
    root.addHandler(external_handler)

    try:
        setup_logging(logs_dir=str(tmp_path), log_level="INFO")
        assert external_handler in root.handlers

        # Even after repeated setup_logging
        setup_logging(logs_dir=str(tmp_path), log_level="INFO")
        assert external_handler in root.handlers
    finally:
        root.removeHandler(external_handler)


def test_file_logging_is_plain_text_without_ansi(tmp_path: pathlib.Path) -> None:
    """Ensure file logging remains clean plain text and never contains ANSI escape codes."""
    setup_logging(logs_dir=str(tmp_path), log_level="INFO")

    logger = get_logger("test_plain")
    logger.info("Informational test message.")
    logger.warning("Warning test message.")
    try:
        raise RuntimeError("Sample simulated failure with traceback.")
    except RuntimeError:
        logger.error("Error encountered", exc_info=True)

    # Flush file handlers
    for h in logging.getLogger().handlers:
        h.flush()

    log_files = list(tmp_path.glob("*.log"))
    assert len(log_files) == 1

    content = log_files[0].read_text(encoding="utf-8")
    assert "Informational test message." in content
    assert "Warning test message." in content
    assert "Error encountered" in content
    assert "Sample simulated failure with traceback." in content
    assert "Traceback" in content

    # Assert no ANSI escape codes exist in file
    assert "\x1b[" not in content
    assert "\x1b" not in content


def test_discord_logger_level_tuning(tmp_path: pathlib.Path) -> None:
    """Ensure discord library logger level is adjusted based on log_level."""
    # When INFO, discord logger should be WARNING
    setup_logging(logs_dir=str(tmp_path), log_level="INFO")
    assert logging.getLogger("discord").level == logging.WARNING

    # When DEBUG, discord logger should be DEBUG
    setup_logging(logs_dir=str(tmp_path), log_level="DEBUG")
    assert logging.getLogger("discord").level == logging.DEBUG


def test_terminal_logging_uses_discord_setup(tmp_path: pathlib.Path) -> None:
    """Ensure discord.utils.setup_logging is invoked during setup."""
    with patch("discord.utils.setup_logging", wraps=discord.utils.setup_logging) as mock_discord_setup:
        setup_logging(logs_dir=str(tmp_path), log_level="WARNING")
        assert mock_discord_setup.called
        call_kwargs = mock_discord_setup.call_args[1]
        assert call_kwargs["level"] == logging.WARNING
        assert call_kwargs["root"] is True
        assert isinstance(call_kwargs["handler"], logging.StreamHandler)
