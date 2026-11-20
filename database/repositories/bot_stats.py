"""Bot statistics repository for monitoring usage and performance."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ASCENDING, DESCENDING, IndexModel

from database.repositories.base import BaseRepository


class BotStatsRepository(BaseRepository[Dict[str, Any]]):
    """Repository storing command metrics and bot execution statistics."""

    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def create_indexes(self) -> List[str]:
        """Ensure indexes for command name lookups and usage sorting."""
        indexes = [
            IndexModel([("command_name", ASCENDING)], unique=True, name="uniq_command_name"),
            IndexModel([("total_uses", DESCENDING)], name="idx_total_uses"),
        ]
        return await self.collection.create_indexes(indexes)

    async def record_command_invocation(self, command_name: str) -> None:
        """Increment the execution count for a command and record last used timestamp."""
        now = datetime.datetime.now(datetime.timezone.utc)
        await self.update_one(
            {"command_name": command_name},
            {
                "$inc": {"total_uses": 1},
                "$set": {"last_used": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def get_top_commands(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve most executed commands."""
        return await self.find_many(
            sort=[("total_uses", DESCENDING)],
            limit=limit,
        )
