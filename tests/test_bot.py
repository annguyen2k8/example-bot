"""Tests for ExampleBot initialization, lifecycle, and cog loader."""

from __future__ import annotations

import pathlib
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pymongo.errors import ConnectionFailure

from bot.client import ExampleBot
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
    assert bot.command_prefix == ["!"]
    assert bot.mongo is None


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
