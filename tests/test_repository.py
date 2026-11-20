"""Tests for BaseRepository and domain repositories."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest

from database.repositories.base import BaseRepository
from database.repositories.guild_settings import GuildSettingsRepository
from database.repositories.bot_stats import BotStatsRepository


@pytest.fixture
def mock_collection() -> MagicMock:
    collection = MagicMock()
    collection.name = "test_collection"
    collection.find_one = AsyncMock()
    collection.find = MagicMock()
    collection.insert_one = AsyncMock()
    collection.insert_many = AsyncMock()
    collection.update_one = AsyncMock()
    collection.update_many = AsyncMock()
    collection.delete_one = AsyncMock()
    collection.delete_many = AsyncMock()
    collection.count_documents = AsyncMock()
    collection.create_indexes = AsyncMock()
    return collection


@pytest.mark.asyncio
async def test_base_repository_crud(mock_collection: MagicMock) -> None:
    repo = BaseRepository(mock_collection)
    assert repo.collection_name == "test_collection"

    # 1. find_one
    mock_collection.find_one.return_value = {"_id": "1", "key": "value"}
    res = await repo.find_one({"key": "value"})
    assert res == {"_id": "1", "key": "value"}
    mock_collection.find_one.assert_called_with({"key": "value"}, None)

    # 2. find_many
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[{"_id": "1"}, {"_id": "2"}])
    mock_collection.find.return_value = mock_cursor

    items = await repo.find_many({"active": True}, sort=[("created_at", -1)], limit=10, skip=5)
    assert len(items) == 2
    mock_collection.find.assert_called_with({"active": True}, None)
    mock_cursor.sort.assert_called_with([("created_at", -1)])
    mock_cursor.skip.assert_called_with(5)
    mock_cursor.limit.assert_called_with(10)

    # 3. insert_one
    mock_insert_res = MagicMock()
    mock_insert_res.inserted_id = "doc123"
    mock_collection.insert_one.return_value = mock_insert_res
    inserted_id = await repo.insert_one({"name": "test"})
    assert inserted_id == "doc123"

    # 4. update_one
    mock_update_res = MagicMock()
    mock_update_res.modified_count = 1
    mock_collection.update_one.return_value = mock_update_res
    modified = await repo.update_one({"name": "test"}, {"$set": {"name": "updated"}})
    assert modified == 1

    # 5. delete_one
    mock_delete_res = MagicMock()
    mock_delete_res.deleted_count = 1
    mock_collection.delete_one.return_value = mock_delete_res
    deleted = await repo.delete_one({"name": "updated"})
    assert deleted == 1

    # 6. count
    mock_collection.count_documents.return_value = 42
    count = await repo.count({"active": True})
    assert count == 42


@pytest.mark.asyncio
async def test_guild_settings_repository(mock_collection: MagicMock) -> None:
    repo = GuildSettingsRepository(mock_collection)

    # Index creation
    mock_collection.create_indexes.return_value = ["uniq_guild_id"]
    indexes = await repo.create_indexes()
    assert indexes == ["uniq_guild_id"]

    # get_prefix
    mock_collection.find_one.return_value = {"prefix": "!"}
    prefix = await repo.get_prefix(123456789)
    assert prefix == "!"

    # set_prefix
    mock_update_res = MagicMock()
    mock_update_res.modified_count = 1
    mock_collection.update_one.return_value = mock_update_res
    await repo.set_prefix(123456789, "?")
    mock_collection.update_one.assert_called_once()


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
