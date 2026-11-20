"""Guild settings repository for managing per-server configuration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ASCENDING, IndexModel

from database.repositories.base import BaseRepository


class GuildSettingsRepository(BaseRepository[Dict[str, Any]]):
    """Repository managing per-guild configuration documents."""

    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        super().__init__(collection)

    async def create_indexes(self) -> List[str]:
        """Ensure unique index on guild_id."""
        index = IndexModel([("guild_id", ASCENDING)], unique=True, name="uniq_guild_id")
        return await self.collection.create_indexes([index])

    async def get_settings(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve settings for a given guild."""
        return await self.find_one({"guild_id": guild_id})

    async def get_prefix(self, guild_id: int) -> Optional[str]:
        """Get the custom prefix configured for a guild, if any."""
        doc = await self.find_one({"guild_id": guild_id}, projection={"prefix": 1})
        return doc.get("prefix") if doc else None

    async def set_prefix(self, guild_id: int, prefix: str) -> None:
        """Set or update the custom prefix for a guild."""
        await self.update_one(
            {"guild_id": guild_id},
            {"$set": {"prefix": prefix}},
            upsert=True,
        )
