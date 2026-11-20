"""Bot statistics repository for monitoring usage and performance."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.asynchronous.collection import AsyncCollection

from database.repositories.base import BaseRepository


class BotStatsRepository(BaseRepository):
    """Repository storing command metrics and bot execution statistics."""

    def __init__(self, collection: AsyncCollection) -> None:
        super().__init__(collection)

    async def create_indexes(self) -> List[str]:
        """Ensure indexes for command name lookups and usage sorting."""
        indexes = [
            IndexModel([("command_name", ASCENDING)], unique=True, name="uniq_command_name"),
            IndexModel([("total_uses", DESCENDING)], name="idx_total_uses"),
        ]
        return await self.collection.create_indexes(indexes)

    async def record_command_invocation(self, command_name: str) -> None:
        """Increment the execution count for a command atomically."""
        now = datetime.datetime.now(datetime.timezone.utc)
        await self.collection.update_one(
            {"command_name": command_name},
            {
                "$inc": {"total_uses": 1},
                "$set": {"last_used": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def get_top_commands(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve most executed commands sorted by total uses descending."""
        cursor = self.collection.find().sort([("total_uses", DESCENDING)]).limit(limit)
        return await cursor.to_list(length=limit)
