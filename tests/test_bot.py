"""Tests for ExampleBot initialization, lifecycle, prefix resolution, and cog loader."""

from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pymongo.errors import ConnectionFailure

from bot.client import ExampleBot, get_command_prefix
from bot.config import BotConfig
from database.connection import MongoManager


@pytest.fixture
def test_config() -> BotConfig:
    return BotConfig(
        token="mock_token",
        command_prefix=["!"],
        description="Test Bot",
        mongodb_uri="mongodb://localhost:27017",
    )


@pytest.mark.asyncio
async def test_bot_initialization(test_config: BotConfig) -> None:
    bot = ExampleBot(config=test_config)
    assert bot.config == test_config
    assert bot.description == "Test Bot"
    assert callable(bot.command_prefix)
    assert bot.mongo is None


@pytest.mark.asyncio
async def test_dynamic_prefix_resolution(test_config: BotConfig) -> None:
    bot = ExampleBot(config=test_config)

    # 1. Message without guild (DM)
    dm_msg = MagicMock()
    dm_msg.guild = None
    prefixes = await get_command_prefix(bot, dm_msg)
    assert prefixes == ["!"]

    # 2. Message with guild but no database
    guild_msg = MagicMock()
    guild_msg.guild = MagicMock()
    guild_msg.guild.id = 123456
    prefixes = await get_command_prefix(bot, guild_msg)
    assert prefixes == ["!"]

    # 3. Message with custom prefix from guild settings
    mock_guild_settings = MagicMock()
    mock_guild_settings.get_prefix = AsyncMock(return_value=">>")
    bot.guild_settings = mock_guild_settings
    prefixes = await get_command_prefix(bot, guild_msg)
    assert prefixes == [">>"]

    # 4. Message when database query raises error
    mock_guild_settings.get_prefix = AsyncMock(side_effect=ConnectionFailure("DB lost"))
    prefixes = await get_command_prefix(bot, guild_msg)
    assert prefixes == ["!"]


@pytest.mark.asyncio
async def test_bot_lifecycle_and_close(test_config: BotConfig) -> None:
    mock_mongo = MagicMock(spec=MongoManager)
    mock_mongo.is_connected = True
    mock_mongo.disconnect = AsyncMock()

    bot = ExampleBot(config=test_config, mongo_manager=mock_mongo)

    with patch.object(bot, "is_closed", return_value=False):
        with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock) as mock_super_close:
            await bot.close()
            mock_super_close.assert_called_once()
            mock_mongo.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_waits_for_active_commands(test_config: BotConfig) -> None:
    """Ensure bot close() waits for currently executing commands before disconnecting MongoDB."""
    mock_mongo = MagicMock(spec=MongoManager)
    mock_mongo.is_connected = True
    mock_mongo.disconnect = AsyncMock()

    bot = ExampleBot(config=test_config, mongo_manager=mock_mongo)

    mock_ctx = MagicMock()
    mock_ctx.command = MagicMock()
    mock_ctx.command.qualified_name = "test_cmd"

    # Simulate command start
    await bot.on_command(mock_ctx)
    assert bot._active_commands == 1
    assert not bot._all_commands_done.is_set()

    # Track order of operations
    events = []

    async def delayed_command_completion() -> None:
        await asyncio.sleep(0.05)
        events.append("command_done")
        await bot.on_command_completion(mock_ctx)

    async def mock_super_close() -> None:
        events.append("gateway_closed")

    async def mock_mongo_disconnect() -> None:
        events.append("db_disconnected")

    mock_mongo.disconnect = AsyncMock(side_effect=mock_mongo_disconnect)

    with patch.object(bot, "is_closed", return_value=False):
        with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock, side_effect=mock_super_close):
            # Run delayed command completion concurrently with close
            asyncio.create_task(delayed_command_completion())
            await bot.close()

    assert bot._active_commands == 0
    assert bot._all_commands_done.is_set()
    # Verify command finished before database was disconnected!
    assert events == ["gateway_closed", "command_done", "db_disconnected"]


@pytest.mark.asyncio
async def test_setup_hook_handles_db_failure(test_config: BotConfig) -> None:
    """Ensure database connection failure during setup_hook does not crash startup."""
    mock_mongo = MagicMock(spec=MongoManager)
    mock_mongo.is_connected = False
    mock_mongo.connect = AsyncMock(side_effect=ConnectionFailure("Database down"))

    bot = ExampleBot(config=test_config, mongo_manager=mock_mongo)

    with patch.object(bot, "load_cogs", new_callable=AsyncMock) as mock_load_cogs:
        await bot.setup_hook()
        mock_mongo.connect.assert_called_once()
        # Cog loading must still proceed so bot can run in offline mode
        mock_load_cogs.assert_called_once()
        assert bot.guild_settings is None
        assert bot.bot_stats is None


@pytest.mark.asyncio
async def test_ensure_database_ready_reconnection(test_config: BotConfig) -> None:
    """Test dynamic reconnection when database becomes available after startup."""
    mock_mongo = MagicMock(spec=MongoManager)
    mock_mongo.is_connected = False
    mock_mongo.db = MagicMock()
    mock_mongo.connect = AsyncMock()

    bot = ExampleBot(config=test_config, mongo_manager=mock_mongo)

    with patch("bot.client.GuildSettingsRepository") as mock_guild_repo, \
         patch("bot.client.BotStatsRepository") as mock_stats_repo:
        mock_guild_instance = MagicMock()
        mock_guild_instance.create_indexes = AsyncMock()
        mock_guild_repo.return_value = mock_guild_instance

        mock_stats_instance = MagicMock()
        mock_stats_instance.create_indexes = AsyncMock()
        mock_stats_repo.return_value = mock_stats_instance

        # First connection attempt succeeds
        success = await bot.ensure_database_ready()
        assert success is True
        mock_mongo.connect.assert_called_once()
        assert bot.guild_settings is mock_guild_instance
        assert bot.bot_stats is mock_stats_instance


@pytest.mark.asyncio
async def test_load_cogs_safe_and_resilient(tmp_path: pathlib.Path, test_config: BotConfig) -> None:
    cogs_dir = tmp_path / "cogs"
    cogs_dir.mkdir()

    # Valid cog dir
    good_cog = cogs_dir / "good"
    good_cog.mkdir()
    (good_cog / "main.py").write_text("# good", encoding="utf-8")

    # Pycache dir (should be skipped)
    pycache = cogs_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "cached.pyc").write_text("", encoding="utf-8")

    # Single-file cog
    (cogs_dir / "single.py").write_text("# single", encoding="utf-8")

    bot = ExampleBot(config=test_config)
    loaded_extensions = []

    async def mock_load_extension(ext: str) -> None:
        if "failing" in ext:
            raise ImportError("Simulated failure")
        loaded_extensions.append(ext)

    with patch.object(bot, "load_extension", side_effect=mock_load_extension):
        await bot.load_cogs(cogs_dir=str(cogs_dir))

    assert "cogs.good.main" in loaded_extensions
    assert "cogs.single" in loaded_extensions
    assert not any("__pycache__" in ext for ext in loaded_extensions)
