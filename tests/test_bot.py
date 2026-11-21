"""Tests for BotBase initialization, lifecycle, prefix resolution, and cog loader."""

from __future__ import annotations

import asyncio
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest
from pymongo.errors import ConnectionFailure

from bot.client import AppCommandTree, BotBase, get_command_prefix
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
    bot = BotBase(config=test_config)
    assert bot.config == test_config
    assert bot.description == "Test Bot"
    assert callable(bot.command_prefix)
    assert bot.mongo is None


@pytest.mark.asyncio
async def test_dynamic_prefix_resolution(test_config: BotConfig) -> None:
    bot = BotBase(config=test_config)

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

    bot = BotBase(config=test_config, mongo_manager=mock_mongo)

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

    bot = BotBase(config=test_config, mongo_manager=mock_mongo)

    mock_ctx = MagicMock()
    mock_ctx.command = MagicMock()
    mock_ctx.command.qualified_name = "test_cmd"

    # Simulate command start
    await bot.on_command(mock_ctx)
    assert bot._active_commands == 1
    assert not bot._all_commands_done.is_set()

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
            asyncio.create_task(delayed_command_completion())
            await bot.close()

    assert bot._active_commands == 0
    assert bot._all_commands_done.is_set()
    assert events == ["gateway_closed", "command_done", "db_disconnected"]


@pytest.mark.asyncio
async def test_tracked_background_tasks_graceful_shutdown(test_config: BotConfig) -> None:
    """Ensure shutdown tracks background tasks and cancels them safely on timeout."""
    mock_mongo = MagicMock(spec=MongoManager)
    mock_mongo.is_connected = True
    mock_mongo.disconnect = AsyncMock()

    bot = BotBase(config=test_config, mongo_manager=mock_mongo)

    task_cancelled = False

    async def long_running_task() -> None:
        nonlocal task_cancelled
        try:
            await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            task_cancelled = True
            raise

    # Spawn tracked task
    task = bot.create_tracked_task(long_running_task(), name="test-bg-task")
    assert task in bot._background_tasks
    await asyncio.sleep(0)  # Yield to loop so task starts running

    with patch.object(bot, "is_closed", return_value=False):
        with patch("discord.ext.commands.Bot.close", new_callable=AsyncMock):
            # Patch wait_for timeout to 0.05s so the test runs fast
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                await bot.close()

    assert task_cancelled is True
    mock_mongo.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_app_command_tree_lifecycle_tracking(test_config: BotConfig) -> None:
    """Ensure AppCommandTree tracks slash command invocations in _active_commands."""
    bot = BotBase(config=test_config)
    tree = bot.tree

    assert isinstance(tree, AppCommandTree)
    assert bot._active_commands == 0

    mock_interaction = MagicMock()

    # Track that _on_command_started was active during _call
    active_during_call = None

    async def mock_super_call(interaction: Any) -> None:
        nonlocal active_during_call
        active_during_call = bot._active_commands

    with patch("discord.app_commands.tree.CommandTree._call", side_effect=mock_super_call):
        await tree._call(mock_interaction)

    assert active_during_call == 1
    assert bot._active_commands == 0
    assert bot._all_commands_done.is_set()


@pytest.mark.asyncio
async def test_concurrent_database_reconnection(test_config: BotConfig) -> None:
    """Ensure multiple concurrent ensure_database_ready() calls are serialized without duplicate connects."""
    mock_mongo = MagicMock(spec=MongoManager)
    mock_mongo.is_connected = False
    mock_mongo.db = MagicMock()

    connect_call_count = 0

    async def delayed_connect() -> None:
        nonlocal connect_call_count
        connect_call_count += 1
        await asyncio.sleep(0.05)
        mock_mongo.is_connected = True

    mock_mongo.connect = AsyncMock(side_effect=delayed_connect)

    bot = BotBase(config=test_config, mongo_manager=mock_mongo)

    with patch("bot.client.GuildSettingsRepository") as mock_guild_repo, \
         patch("bot.client.BotStatsRepository") as mock_stats_repo:
        mock_guild_instance = MagicMock()
        mock_guild_instance.create_indexes = AsyncMock()
        mock_guild_repo.return_value = mock_guild_instance

        mock_stats_instance = MagicMock()
        mock_stats_instance.create_indexes = AsyncMock()
        mock_stats_repo.return_value = mock_stats_instance

        # Invoke 5 concurrent calls
        results = await asyncio.gather(*[bot.ensure_database_ready() for _ in range(5)])

        assert all(res is True for res in results)
        # connect must only have been called ONCE due to asyncio.Lock!
        assert connect_call_count == 1
        assert mock_guild_instance.create_indexes.call_count == 1
        assert mock_stats_instance.create_indexes.call_count == 1


@pytest.mark.asyncio
async def test_setup_hook_handles_db_failure(test_config: BotConfig) -> None:
    """Ensure database connection failure during setup_hook does not crash startup."""
    mock_mongo = MagicMock(spec=MongoManager)
    mock_mongo.is_connected = False
    mock_mongo.connect = AsyncMock(side_effect=ConnectionFailure("Database down"))

    bot = BotBase(config=test_config, mongo_manager=mock_mongo)

    with patch.object(bot, "load_cogs", new_callable=AsyncMock) as mock_load_cogs:
        await bot.setup_hook()
        mock_mongo.connect.assert_called_once()
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

    bot = BotBase(config=test_config)
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


@pytest.mark.asyncio
async def test_sync_commands_loads_cogs_first_if_empty(test_config: BotConfig) -> None:
    """Ensure sync_commands triggers load_cogs if cogs are not yet loaded."""
    bot = BotBase(config=test_config)
    mock_app_cmd = MagicMock(spec=discord.app_commands.AppCommand)
    mock_app_cmd.name = "test_cmd"

    async def mock_load() -> None:
        # Simulate loading by injecting a dummy command into tree and cog dict
        bot._BotBase__cogs = {"dummy": MagicMock()}  # type: ignore[attr-defined]
        bot.tree._get_all_commands = MagicMock(return_value=[mock_app_cmd])  # type: ignore[attr-defined]

    with patch.object(bot, "load_cogs", side_effect=mock_load) as mock_load_cogs, \
         patch.object(bot.tree, "get_commands", return_value=[mock_app_cmd]), \
         patch.object(bot.tree, "sync", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = [mock_app_cmd]
        res = await bot.sync_commands()

        mock_load_cogs.assert_called_once()
        mock_sync.assert_called_once_with(guild=None)
        assert res == [mock_app_cmd]


@pytest.mark.asyncio
async def test_sync_commands_skips_when_no_commands_in_tree(test_config: BotConfig) -> None:
    """Ensure sync_commands skips tree.sync when tree is empty to prevent clearing Discord commands."""
    bot = BotBase(config=test_config)
    bot._BotBase__cogs = {"dummy": MagicMock()}  # type: ignore[attr-defined]

    with patch.object(bot.tree, "get_commands", return_value=[]), \
         patch.object(bot.tree, "sync", new_callable=AsyncMock) as mock_sync:
        res = await bot.sync_commands()

        mock_sync.assert_not_called()
        assert res == []


@pytest.mark.asyncio
async def test_sync_commands_error_handling(test_config: BotConfig) -> None:
    """Ensure sync_commands catches Forbidden and HTTPException without crashing."""
    bot = BotBase(config=test_config)
    bot._BotBase__cogs = {"dummy": MagicMock()}  # type: ignore[attr-defined]
    mock_cmd = MagicMock()
    mock_cmd.name = "cmd"

    # Test Forbidden error
    mock_resp = MagicMock()
    mock_resp.status = 403
    forbidden_err = discord.Forbidden(mock_resp, "Missing access")

    with patch.object(bot.tree, "get_commands", return_value=[mock_cmd]), \
         patch.object(bot.tree, "sync", new_callable=AsyncMock) as mock_sync:
        mock_sync.side_effect = forbidden_err
        res = await bot.sync_commands()
        assert res == []

    # Test Generic Exception error
    with patch.object(bot.tree, "get_commands", return_value=[mock_cmd]), \
         patch.object(bot.tree, "sync", new_callable=AsyncMock) as mock_sync:
        mock_sync.side_effect = RuntimeError("Network error")
        res = await bot.sync_commands()
        assert res == []


@pytest.mark.asyncio
async def test_setup_hook_syncs_when_configured(test_config: BotConfig) -> None:
    """Ensure setup_hook invokes sync_commands when sync_commands_on_startup is True."""
    test_config.sync_commands_on_startup = True
    bot = BotBase(config=test_config)

    with patch.object(bot, "ensure_database_ready", new_callable=AsyncMock), \
         patch.object(bot, "load_cogs", new_callable=AsyncMock) as mock_load, \
         patch.object(bot, "sync_commands", new_callable=AsyncMock) as mock_sync:
        await bot.setup_hook()
        mock_load.assert_called_once()
        mock_sync.assert_called_once()
