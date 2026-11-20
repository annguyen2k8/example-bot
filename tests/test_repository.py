"""Tests for domain repositories and data access logic."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from database.repositories.guild_settings import GuildSettingsRepository
from database.repositories.bot_stats import BotStatsRepository


@pytest.fixture
def mock_collection() -> MagicMock:
    collection = MagicMock()
    collection.name = "test_collection"
    collection.find_one = AsyncMock()
    collection.find = MagicMock()
    collection.update_one = AsyncMock()
    collection.delete_one = AsyncMock()
    collection.create_indexes = AsyncMock()
    return collection


@pytest.mark.asyncio
async def test_guild_settings_repository(mock_collection: MagicMock) -> None:
    repo = GuildSettingsRepository(mock_collection)
    assert repo.collection_name == "test_collection"

    # Index creation
    mock_collection.create_indexes.return_value = ["uniq_guild_id"]
    indexes = await repo.create_indexes()
    assert indexes == ["uniq_guild_id"]
    mock_collection.create_indexes.assert_called_once()

    # get_prefix found
    mock_collection.find_one.return_value = {"prefix": "!"}
    prefix = await repo.get_prefix(123456789)
    assert prefix == "!"
    mock_collection.find_one.assert_called_with({"guild_id": 123456789}, projection={"prefix": 1})

    # get_prefix not found
    mock_collection.find_one.return_value = None
    assert await repo.get_prefix(999999999) is None

    # get_settings
    mock_collection.find_one.return_value = {"guild_id": 123456789, "prefix": "!"}
    settings = await repo.get_settings(123456789)
    assert settings == {"guild_id": 123456789, "prefix": "!"}

    # set_prefix
    mock_update_res = MagicMock()
    mock_update_res.modified_count = 1
    mock_collection.update_one.return_value = mock_update_res
    await repo.set_prefix(123456789, "?")
    mock_collection.update_one.assert_called_with(
        {"guild_id": 123456789},
        {"$set": {"prefix": "?"}},
        upsert=True,
    )

    # delete_settings
    mock_delete_res = MagicMock()
    mock_delete_res.deleted_count = 1
    mock_collection.delete_one.return_value = mock_delete_res
    assert await repo.delete_settings(123456789) is True
    mock_collection.delete_one.assert_called_with({"guild_id": 123456789})


@pytest.mark.asyncio
async def test_bot_stats_repository(mock_collection: MagicMock) -> None:
    repo = BotStatsRepository(mock_collection)

    # Index creation
    mock_collection.create_indexes.return_value = ["uniq_command_name", "idx_total_uses"]
    indexes = await repo.create_indexes()
    assert len(indexes) == 2

    # record invocation
    mock_update_res = MagicMock()
    mock_update_res.modified_count = 1
    mock_collection.update_one.return_value = mock_update_res
    await repo.record_command_invocation("ping")
    mock_collection.update_one.assert_called_once()
    filter_arg = mock_collection.update_one.call_args[0][0]
    assert filter_arg == {"command_name": "ping"}

    # get_top_commands
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[
        {"command_name": "ping", "total_uses": 42},
        {"command_name": "uptime", "total_uses": 10},
    ])
    mock_collection.find.return_value = mock_cursor

    top = await repo.get_top_commands(limit=5)
    assert len(top) == 2
    assert top[0]["command_name"] == "ping"
    mock_cursor.limit.assert_called_with(5)


@pytest.mark.asyncio
async def test_concurrent_repository_operations(mock_collection: MagicMock) -> None:
    """Ensure repositories handle concurrent operations safely without race conditions."""
    guild_repo = GuildSettingsRepository(mock_collection)
    stats_repo = BotStatsRepository(mock_collection)

    mock_collection.find_one.return_value = {"prefix": "!"}
    mock_collection.update_one.return_value = MagicMock(modified_count=1)

    tasks = [
        guild_repo.get_prefix(i) for i in range(10)
    ] + [
        guild_repo.set_prefix(i, f"!{i}") for i in range(10)
    ] + [
        stats_repo.record_command_invocation(f"cmd_{i}") for i in range(10)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert len(results) == 30
    assert not any(isinstance(r, Exception) for r in results)
