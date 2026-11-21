"""Tests for application entry point, lifecycle management, and error handling."""

from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from bot.client import BotBase
from bot.config import BotConfig
from database.connection import MongoManager
from main import async_main, start_bot


@pytest.mark.asyncio
async def test_async_main_missing_token_fails_early() -> None:
    """Ensure async_main fails early when token is missing."""
    config = BotConfig(token="")
    with pytest.raises(SystemExit) as exc_info:
        await async_main(config)
    assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_async_main_login_failure_distinguished() -> None:
    """Ensure async_main specifically catches LoginFailure and exits."""
    config = BotConfig(token="valid-token-format")

    with patch.object(BotBase, "start", new_callable=AsyncMock) as mock_start, \
         patch("main.logger") as mock_logger:
        mock_start.side_effect = discord.LoginFailure("Improper token has been passed.")

        with pytest.raises(SystemExit) as exc_info:
            await async_main(config)

        assert exc_info.value.code == 1
        # Verify specific authentication failure was logged
        mock_logger.critical.assert_called()
        log_message = mock_logger.critical.call_args[0][0]
        assert "Authentication failure" in log_message


@pytest.mark.asyncio
async def test_async_main_connection_failure() -> None:
    """Ensure async_main distinguishes connection/gateway failures."""
    config = BotConfig(token="valid-token-format")

    with patch.object(BotBase, "start", new_callable=AsyncMock) as mock_start, \
         patch("main.logger") as mock_logger:
        mock_start.side_effect = discord.GatewayNotFound()

        with pytest.raises(SystemExit) as exc_info:
            await async_main(config)

        assert exc_info.value.code == 1
        log_message = mock_logger.critical.call_args[0][0]
        assert "connection failure" in log_message


@pytest.mark.asyncio
async def test_async_main_general_exception() -> None:
    """Ensure async_main logs general runtime exceptions."""
    config = BotConfig(token="valid-token-format")

    with patch.object(BotBase, "start", new_callable=AsyncMock) as mock_start, \
         patch("main.logger") as mock_logger:
        mock_start.side_effect = RuntimeError("Something unexpected")

        with pytest.raises(SystemExit) as exc_info:
            await async_main(config)

        assert exc_info.value.code == 1
        log_message = mock_logger.critical.call_args[0][0]
        assert "Fatal error encountered during bot runtime" in log_message


@pytest.mark.asyncio
async def test_async_main_preserves_mongodb_lifecycle_on_failure() -> None:
    """Ensure MongoDB connection is disconnected in finally block upon failure."""
    config = BotConfig(
        token="valid-token-format",
        mongodb_uri="mongodb://localhost:27017",
    )

    mock_mongo = MagicMock(spec=MongoManager)
    mock_mongo.is_connected = True

    async def mock_disconnect() -> None:
        mock_mongo.is_connected = False

    mock_mongo.disconnect = AsyncMock(side_effect=mock_disconnect)

    with patch("main.MongoManager", return_value=mock_mongo), \
         patch.object(BotBase, "start", new_callable=AsyncMock) as mock_start:
        mock_start.side_effect = discord.LoginFailure("Improper token has been passed.")

        with pytest.raises(SystemExit):
            await async_main(config)

        # MongoDB disconnect must have been called
        mock_mongo.disconnect.assert_called_once()


def test_start_bot_invalid_config_exits(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Ensure start_bot fails early when BotConfig validation fails."""
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")

    with patch("main.logger") as mock_logger, \
         pytest.raises(SystemExit) as exc_info:
        start_bot(config_source=str(empty_env))

    assert exc_info.value.code == 1
    mock_logger.critical.assert_called()
