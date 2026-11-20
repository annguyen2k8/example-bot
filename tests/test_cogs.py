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
    bot.guild_settings = None
    bot.config = MagicMock()
    bot.config.command_prefix = ["!", "?"]
    bot.is_owner = AsyncMock(return_value=False)
    bot.ensure_database_ready = AsyncMock(return_value=False)
    return bot


@pytest.fixture
def mock_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.reply = AsyncMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456789
    ctx.author = MagicMock()
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.manage_guild = True
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
    mock_mongo.is_connected = True
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


@pytest.mark.asyncio
async def test_prefix_command_offline_database(mock_bot: MagicMock, mock_ctx: MagicMock) -> None:
    """Ensure prefix command returns graceful error without crashing when MongoDB is down."""
    mock_bot.ensure_database_ready.return_value = False

    cog = ExampleCog(mock_bot)
    # View prefix
    await cog.prefix.callback(cog, mock_ctx, None)
    mock_ctx.reply.assert_called_once()
    assert "Database is currently unavailable" in mock_ctx.reply.call_args[0][0]

    # Attempt to set prefix
    mock_ctx.reply.reset_mock()
    await cog.prefix.callback(cog, mock_ctx, ">>")
    mock_ctx.reply.assert_called_once()
    assert "Database is currently unavailable" in mock_ctx.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_prefix_command_get_and_set(mock_bot: MagicMock, mock_ctx: MagicMock) -> None:
    """Test viewing and updating prefix when database is healthy."""
    mock_bot.ensure_database_ready.return_value = True
    mock_guild_settings = MagicMock()
    mock_guild_settings.get_prefix = AsyncMock(return_value="?")
    mock_guild_settings.set_prefix = AsyncMock()
    mock_bot.guild_settings = mock_guild_settings

    cog = ExampleCog(mock_bot)

    # View existing custom prefix
    await cog.prefix.callback(cog, mock_ctx, None)
    mock_ctx.reply.assert_called_with("Server prefix is set to: `?`")

    # Set new prefix
    await cog.prefix.callback(cog, mock_ctx, ">>")
    mock_guild_settings.set_prefix.assert_called_with(123456789, ">>")
    mock_ctx.reply.assert_called_with("Server prefix updated to: `>>`")


@pytest.mark.asyncio
async def test_prefix_command_permission_denied(mock_bot: MagicMock, mock_ctx: MagicMock) -> None:
    """Ensure non-admin cannot update guild prefix."""
    mock_bot.ensure_database_ready.return_value = True
    mock_bot.guild_settings = MagicMock()
    mock_ctx.author.guild_permissions.manage_guild = False
    mock_bot.is_owner.return_value = False

    cog = ExampleCog(mock_bot)
    await cog.prefix.callback(cog, mock_ctx, "$")
    mock_ctx.reply.assert_called_with("You need the 'Manage Server' permission to change the prefix.")
