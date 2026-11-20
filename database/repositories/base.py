"""Base repository interface for domain data access layers."""

from __future__ import annotations

import abc
from typing import List

from pymongo.asynchronous.collection import AsyncCollection


class BaseRepository(abc.ABC):
    """Abstract base repository wrapping an AsyncCollection with index management."""

    def __init__(self, collection: AsyncCollection) -> None:
        """Initialize the repository with an asynchronous collection."""
        self.collection = collection

    @property
    def collection_name(self) -> str:
        """Name of the underlying MongoDB collection."""
        return self.collection.name

    @abc.abstractmethod
    async def create_indexes(self) -> List[str]:
        """Ensure collection indexes exist idempotently."""
        ...
