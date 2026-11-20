"""Abstract base repository providing typed asynchronous CRUD operations."""

from __future__ import annotations

from typing import Any, Dict, Generic, List, Mapping, Optional, Sequence, Tuple, TypeVar

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import IndexModel
from pymongo.errors import PyMongoError

from bot.logging import get_logger

logger = get_logger("repository")

T = TypeVar("T", bound=Mapping[str, Any])


class BaseRepository(Generic[T]):
    """Generic repository providing asynchronous data access primitives for a collection."""

    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        """Initialize the repository with a specific collection.

        Args:
            collection: The Motor collection instance to wrap.
        """
        self.collection = collection

    @property
    def collection_name(self) -> str:
        """Return the wrapped collection's name."""
        return self.collection.name

    async def find_one(
        self,
        filter: Mapping[str, Any],
        projection: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Find a single document matching the filter."""
        try:
            return await self.collection.find_one(filter, projection)
        except PyMongoError as e:
            logger.error(
                "Error finding document in %s with filter %s: %s",
                self.collection_name,
                filter,
                e,
            )
            raise

    async def find_many(
        self,
        filter: Optional[Mapping[str, Any]] = None,
        projection: Optional[Mapping[str, Any]] = None,
        sort: Optional[Sequence[Tuple[str, int]]] = None,
        limit: int = 100,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """Find multiple documents matching the filter with sorting, limit and skip."""
        filter_query = filter or {}
        try:
            cursor = self.collection.find(filter_query, projection)
            if sort:
                cursor = cursor.sort(list(sort))
            if skip > 0:
                cursor = cursor.skip(skip)
            if limit > 0:
                cursor = cursor.limit(limit)

            return await cursor.to_list(length=limit if limit > 0 else None)
        except PyMongoError as e:
            logger.error(
                "Error finding many in %s with filter %s: %s",
                self.collection_name,
                filter_query,
                e,
            )
            raise

    async def insert_one(self, document: Dict[str, Any]) -> str:
        """Insert a single document and return its string ID."""
        try:
            result = await self.collection.insert_one(document)
            return str(result.inserted_id)
        except PyMongoError as e:
            logger.error("Error inserting document into %s: %s", self.collection_name, e)
            raise

    async def insert_many(self, documents: List[Dict[str, Any]]) -> List[str]:
        """Insert multiple documents and return their string IDs."""
        if not documents:
            return []
        try:
            result = await self.collection.insert_many(documents)
            return [str(item_id) for item_id in result.inserted_ids]
        except PyMongoError as e:
            logger.error(
                "Error inserting %d documents into %s: %s",
                len(documents),
                self.collection_name,
                e,
            )
            raise

    async def update_one(
        self,
        filter: Mapping[str, Any],
        update: Mapping[str, Any],
        upsert: bool = False,
    ) -> int:
        """Update a single document matching the filter.

        Returns:
            Number of matched/modified documents.
        """
        try:
            result = await self.collection.update_one(filter, update, upsert=upsert)
            return result.modified_count if not upsert else (result.modified_count or (1 if result.upserted_id else 0))
        except PyMongoError as e:
            logger.error(
                "Error updating one in %s with filter %s: %s",
                self.collection_name,
                filter,
                e,
            )
            raise

    async def update_many(
        self,
        filter: Mapping[str, Any],
        update: Mapping[str, Any],
        upsert: bool = False,
    ) -> int:
        """Update multiple documents matching the filter.

        Returns:
            Number of modified documents.
        """
        try:
            result = await self.collection.update_many(filter, update, upsert=upsert)
            return result.modified_count
        except PyMongoError as e:
            logger.error(
                "Error updating many in %s with filter %s: %s",
                self.collection_name,
                filter,
                e,
            )
            raise

    async def delete_one(self, filter: Mapping[str, Any]) -> int:
        """Delete a single document matching the filter.

        Returns:
            Number of deleted documents (0 or 1).
        """
        try:
            result = await self.collection.delete_one(filter)
            return result.deleted_count
        except PyMongoError as e:
            logger.error(
                "Error deleting one in %s with filter %s: %s",
                self.collection_name,
                filter,
                e,
            )
            raise

    async def delete_many(self, filter: Mapping[str, Any]) -> int:
        """Delete all documents matching the filter.

        Returns:
            Number of deleted documents.
        """
        try:
            result = await self.collection.delete_many(filter)
            return result.deleted_count
        except PyMongoError as e:
            logger.error(
                "Error deleting many in %s with filter %s: %s",
                self.collection_name,
                filter,
                e,
            )
            raise

    async def count(self, filter: Optional[Mapping[str, Any]] = None) -> int:
        """Count documents matching the filter."""
        filter_query = filter or {}
        try:
            return await self.collection.count_documents(filter_query)
        except PyMongoError as e:
            logger.error(
                "Error counting documents in %s with filter %s: %s",
                self.collection_name,
                filter_query,
                e,
            )
            raise

    async def create_indexes(self) -> List[str]:
        """Create required indexes for this collection.

        Subclasses should override this method to define their schema indexes.
        """
        return []
