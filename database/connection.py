"""Asynchronous MongoDB connection manager using Motor."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, PyMongoError

from bot.logging import get_logger

logger = get_logger("database")


class MongoManager:
    """Manages the MongoDB client lifecycle, connection pooling, and health checks."""

    def __init__(
        self,
        uri: str,
        db_name: str = "example_bot",
        *,
        max_pool_size: int = 50,
        min_pool_size: int = 5,
        server_selection_timeout_ms: int = 5000,
        connect_timeout_ms: int = 5000,
    ) -> None:
        """Initialize connection settings without immediately opening sockets.

        Args:
            uri: MongoDB connection string (e.g. mongodb://user:pass@host:27017/db).
            db_name: Target database name.
            max_pool_size: Maximum connections in the pool.
            min_pool_size: Minimum connections retained in the pool.
            server_selection_timeout_ms: Timeout for discovering cluster servers.
            connect_timeout_ms: Timeout for opening sockets.
        """
        self._uri = uri
        self._db_name = db_name
        self._max_pool_size = max_pool_size
        self._min_pool_size = min_pool_size
        self._server_selection_timeout_ms = server_selection_timeout_ms
        self._connect_timeout_ms = connect_timeout_ms

        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None
        self._connected: bool = False

    @property
    def client(self) -> Optional[AsyncIOMotorClient]:
        """Return the active Motor client, if connected."""
        return self._client

    @property
    def db(self) -> Optional[AsyncIOMotorDatabase]:
        """Return the default database instance, if connected."""
        return self._db

    @property
    def is_connected(self) -> bool:
        """Check whether the client is currently considered connected."""
        return self._connected and self._client is not None

    async def connect(self) -> None:
        """Initialize the client with connection pooling and ping the server.

        Raises:
            ConnectionFailure: If the server cannot be reached within the timeout.
            PyMongoError: If another database error occurs.
        """
        if self._connected and self._client is not None:
            logger.debug("MongoDB is already connected.")
            return

        logger.info("Connecting to MongoDB database: %s", self._db_name)
        try:
            self._client = AsyncIOMotorClient(
                self._uri,
                maxPoolSize=self._max_pool_size,
                minPoolSize=self._min_pool_size,
                serverSelectionTimeoutMS=self._server_selection_timeout_ms,
                connectTimeoutMS=self._connect_timeout_ms,
            )
            # Verify connectivity via ping
            await self._client.admin.command("ping")
            self._db = self._client[self._db_name]
            self._connected = True
            logger.info("Successfully connected to MongoDB.")
        except ConnectionFailure as e:
            self._connected = False
            logger.error("Failed to connect to MongoDB server: %s", e)
            raise
        except PyMongoError as e:
            self._connected = False
            logger.error("MongoDB configuration or initialization error: %s", e)
            raise

    async def disconnect(self) -> None:
        """Gracefully close all pooled sockets and clean up references."""
        if self._client is not None:
            logger.info("Closing MongoDB connection pool...")
            self._client.close()
            self._client = None
            self._db = None
            self._connected = False
            logger.info("MongoDB disconnected.")

    async def health_check(self) -> Dict[str, Any]:
        """Execute a round-trip ping command to measure latency and verify health.

        Returns:
            Dictionary with status, latency in milliseconds, and database name.
        """
        if not self.is_connected or self._client is None:
            return {
                "status": "disconnected",
                "healthy": False,
                "error": "Client is not connected",
            }

        start = time.perf_counter()
        try:
            await self._client.admin.command("ping")
            latency = (time.perf_counter() - start) * 1000.0
            return {
                "status": "healthy",
                "healthy": True,
                "latency_ms": round(latency, 2),
                "db_name": self._db_name,
            }
        except Exception as e:
            logger.warning("MongoDB health check ping failed: %s", e)
            return {
                "status": "unhealthy",
                "healthy": False,
                "error": str(e),
            }
