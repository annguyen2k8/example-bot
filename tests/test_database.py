"""Tests for MongoManager connection lifecycle, pooling, and health checks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pymongo.errors import ConnectionFailure

from database.connection import MongoManager


@pytest.mark.asyncio
async def test_mongo_manager_lifecycle() -> None:
    manager = MongoManager(
        uri="mongodb://localhost:27017",
        db_name="test_bot",
        max_pool_size=20,
        min_pool_size=0,
    )
    assert not manager.is_connected
    assert manager.client is None
    assert manager.db is None

    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(return_value={"ok": 1})
    mock_client.close = AsyncMock()
    mock_db = MagicMock()
    mock_client.__getitem__.return_value = mock_db

    with patch("database.connection.AsyncMongoClient", return_value=mock_client) as mock_constructor:
        await manager.connect()

        mock_constructor.assert_called_once_with(
            "mongodb://localhost:27017",
            maxPoolSize=20,
            minPoolSize=0,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
        mock_client.admin.command.assert_called_with("ping")
        assert manager.is_connected
        assert manager.db is mock_db

        # Health check
        health = await manager.health_check()
        assert health["status"] == "healthy"
        assert health["healthy"] is True
        assert "latency_ms" in health
        assert health["db_name"] == "test_bot"

        # Disconnect
        await manager.disconnect()
        mock_client.close.assert_called_once()
        assert not manager.is_connected
        assert manager.client is None


@pytest.mark.asyncio
async def test_mongo_manager_connection_failure_cleanup() -> None:
    """Ensure client instance is closed on failure to avoid leaking background monitors."""
    manager = MongoManager(uri="mongodb://invalid:27017", db_name="test_bot")

    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(side_effect=ConnectionFailure("Server unreachable"))
    mock_client.close = AsyncMock()

    with patch("database.connection.AsyncMongoClient", return_value=mock_client):
        with pytest.raises(ConnectionFailure):
            await manager.connect()

        # Verify close was called to prevent background thread leak
        mock_client.close.assert_called_once()
        assert not manager.is_connected
        assert manager.client is None
        assert manager.db is None

    # Health check when disconnected
    health = await manager.health_check()
    assert health["status"] == "disconnected"
    assert health["healthy"] is False


@pytest.mark.asyncio
async def test_mongo_manager_health_check_failure() -> None:
    manager = MongoManager(uri="mongodb://localhost:27017", db_name="test_bot")

    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(return_value={"ok": 1})
    mock_client.close = AsyncMock()

    with patch("database.connection.AsyncMongoClient", return_value=mock_client):
        await manager.connect()

        # Subsequent ping failure
        mock_client.admin.command = AsyncMock(side_effect=ConnectionFailure("Connection reset"))
        health = await manager.health_check()
        assert health["status"] == "unhealthy"
        assert health["healthy"] is False
        assert "Connection reset" in health["error"]
