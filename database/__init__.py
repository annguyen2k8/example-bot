"""Database package providing asynchronous MongoDB client and repository layer."""

from database.connection import MongoManager
from database.repositories.base import BaseRepository
from database.repositories.guild_settings import GuildSettingsRepository
from database.repositories.bot_stats import BotStatsRepository

__all__ = [
    "MongoManager",
    "BaseRepository",
    "GuildSettingsRepository",
    "BotStatsRepository",
]
