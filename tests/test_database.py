"""Tests for MongoManager connection lifecycle and health check."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from pymongo.errors import ConnectionFailure

from database.connection import MongoManager


@pytest.mark.asyncio
async def test_mongo_manager_lifecycle() -> None:
    manager = MongoManager(uri="mongodb://localhost:27017", db_name="test_bot")
    assert not manager.is_connected
    assert manager.client is None
    assert manager.db is None

    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(return_value={"ok": 1})
    mock_db = MagicMock()
    mock_client.__getitem__.return_value = mock_db

    with patch("database.connection.AsyncIOMotorClient", return_value=mock_client) as mock_constructor:
        await manager.connect()

        mock_constructor.assert_called_once()
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
async def test_mongo_manager_connection_failure() -> None:
    manager = MongoManager(uri="mongodb://invalid:27017", db_name="test_bot")

    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(side_effect=ConnectionFailure("Server unreachable"))

    with patch("database.connection.AsyncIOMotorClient", return_value=mock_client):
        with pytest.raises(ConnectionFailure):
            await manager.connect()

        assert not manager.is_connected
        assert manager.db is None

    # Health check when disconnected
    health = await manager.health_check()
    assert health["status"] == "disconnected"
    assert health["healthy"] is False
