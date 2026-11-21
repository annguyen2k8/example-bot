"""Tests for centralized logging configuration and discord.py logging integration in BotBase."""

from __future__ import annotations

import logging
import logging.handlers
import pathlib
import sys
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


def test_log_records_captured_across_namespaces(tmp_path: pathlib.Path) -> None:
    """Ensure log records from example_bot and discord are all captured in file."""
    setup_logging(logs_dir=str(tmp_path), log_level="DEBUG")

    get_logger("submodule").info("ExampleBot submodule event")
    logging.getLogger("discord.gateway").warning("Discord gateway test event")

    for h in logging.getLogger().handlers:
        h.flush()

    log_files = list(tmp_path.glob("*.log"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")

    assert "ExampleBot submodule event" in content
    assert "Discord gateway test event" in content


def test_rotating_file_handler_configuration_and_rollover(tmp_path: pathlib.Path) -> None:
    """Ensure RotatingFileHandler is configured with maxBytes=10MB and backupCount=5, and rotates."""
    setup_logging(logs_dir=str(tmp_path), log_level="INFO")

    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(file_handlers) == 1
    rfh = file_handlers[0]

    assert rfh.maxBytes == 10 * 1024 * 1024
    assert rfh.backupCount == 5

    # Verify rollover functionality with a small-boundary RotatingFileHandler
    test_log_file = tmp_path / "rollover_test.log"
    small_rfh = logging.handlers.RotatingFileHandler(
        str(test_log_file),
        maxBytes=150,
        backupCount=3,
        encoding="utf-8",
    )
    test_logger = logging.getLogger("test_rollover")
    test_logger.addHandler(small_rfh)
    test_logger.propagate = False

    try:
        for i in range(15):
            test_logger.info("Message %02d padding bytes to trigger log file rotation...", i)
        small_rfh.flush()
        small_rfh.close()

        created_files = list(tmp_path.glob("rollover_test.log*"))
        assert len(created_files) > 1
        assert (tmp_path / "rollover_test.log.1").exists()
    finally:
        test_logger.removeHandler(small_rfh)


def test_console_formatter_has_color(tmp_path: pathlib.Path) -> None:
    """Ensure the console handler uses discord.py's native _ColourFormatter and generates ANSI codes."""
    setup_logging(logs_dir=str(tmp_path), log_level="INFO")

    root = logging.getLogger()
    stream_handlers = [
        h
        for h in root.handlers
        if getattr(h, "_example_bot_managed", False)
        and isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
    ]
    assert len(stream_handlers) == 1

    formatter = stream_handlers[0].formatter
    assert isinstance(formatter, discord.utils._ColourFormatter)

    record = logging.LogRecord(
        name="example_bot.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Color verification message",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    assert "\x1b[" in formatted
    assert "Color verification message" in formatted


def test_setup_logging_avoids_duplicate_log_records(tmp_path: pathlib.Path) -> None:
    """Ensure calling setup_logging multiple times does not write duplicate lines per event."""
    setup_logging(logs_dir=str(tmp_path), log_level="INFO")
    setup_logging(logs_dir=str(tmp_path), log_level="INFO")

    logger = get_logger("dup_test")
    logger.info("Unique single record check 12345")

    for h in logging.getLogger().handlers:
        h.flush()

    log_files = list(tmp_path.glob("*.log"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert content.count("Unique single record check 12345") == 1


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
