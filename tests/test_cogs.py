"""Tests for ExampleCog commands."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock
import pytest

from cogs.example.main import ExampleCog


@pytest.fixture
def mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.start_time = datetime.datetime.now() - datetime.timedelta(seconds=125)
    bot.latency = 0.042
    bot.application_id = 987654321
    bot.user = MagicMock()
    bot.user.id = 987654321
    bot.mongo = None
    bot.bot_stats = None
    return bot


@pytest.fixture
def mock_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.reply = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_ping_command(mock_bot: MagicMock, mock_ctx: MagicMock) -> None:
    cog = ExampleCog(mock_bot)
    await cog.ping.callback(cog, mock_ctx)
    mock_ctx.reply.assert_called_once_with("Pong! 42ms")


@pytest.mark.asyncio
async def test_uptime_command(mock_bot: MagicMock, mock_ctx: MagicMock) -> None:
    cog = ExampleCog(mock_bot)
    await cog.uptime.callback(cog, mock_ctx)
    mock_ctx.reply.assert_called_once()
    reply_text = mock_ctx.reply.call_args[0][0]
    assert "**Uptime:**" in reply_text
    assert "2m" in reply_text


@pytest.mark.asyncio
async def test_link_command(mock_bot: MagicMock, mock_ctx: MagicMock) -> None:
    cog = ExampleCog(mock_bot)
    await cog.link.callback(cog, mock_ctx)
    mock_ctx.reply.assert_called_once()
    reply_text = mock_ctx.reply.call_args[0][0]
    assert "discord.com" in reply_text
    assert "987654321" in reply_text


@pytest.mark.asyncio
async def test_db_status_unconfigured(mock_bot: MagicMock, mock_ctx: MagicMock) -> None:
    cog = ExampleCog(mock_bot)
    await cog.db_status.callback(cog, mock_ctx)
    mock_ctx.reply.assert_called_once_with("MongoDB is not configured for this bot instance.")


@pytest.mark.asyncio
async def test_db_status_healthy(mock_bot: MagicMock, mock_ctx: MagicMock) -> None:
    mock_mongo = MagicMock()
    mock_mongo.health_check = AsyncMock(return_value={
        "healthy": True,
        "latency_ms": 2.5,
        "db_name": "example_bot",
    })
    mock_bot.mongo = mock_mongo

    cog = ExampleCog(mock_bot)
    await cog.db_status.callback(cog, mock_ctx)
    mock_ctx.reply.assert_called_once()
    reply_text = mock_ctx.reply.call_args[0][0]
    assert "Healthy" in reply_text
    assert "2.5ms" in reply_text
