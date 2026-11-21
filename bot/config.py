"""Centralized environment variable configuration management for ExampleBot.

Supports injected operating system environment variables for production environments
and local .env file loading via python-dotenv for development.
"""

from __future__ import annotations

import os
import pathlib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Union

from dotenv import load_dotenv

VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def redact_uri(uri: Optional[str]) -> Optional[str]:
    """Mask credentials in MongoDB connection URI for safe logging."""
    if not uri:
        return None
    return re.sub(r"(mongodb(\+srv)?://[^:]+:)([^@]+)(@)", r"\1***\4", uri)


def redact_token(token: Optional[str]) -> str:
    """Mask Discord token for safe logging."""
    if not token:
        return "[EMPTY]"
    if len(token) <= 8:
        return "[REDACTED]"
    return f"{token[:4]}...{token[-4:]}"


@dataclass
class BotConfig:
    """Type-safe, validated configuration container populated strictly from environment variables."""

    token: str = ""
    command_prefix: List[str] = field(default_factory=lambda: ["!", "?"])
    description: Optional[str] = "I'm a example bot!"
    embed_color: Optional[int] = None
    mongodb_uri: Optional[str] = None
    mongodb_database: str = "example_bot"
    mongodb_min_pool_size: int = 0
    mongodb_max_pool_size: int = 20
    mongodb_timeout_ms: int = 5000
    log_level: str = "INFO"
    logs_dir: str = "logs"
    sync_commands_on_startup: bool = False

    @property
    def mongodb_db_name(self) -> str:
        """Backward compatibility alias for mongodb_database."""
        return self.mongodb_database

    @property
    def safe_token(self) -> str:
        """Return masked token safe for display."""
        return redact_token(self.token)

    @property
    def safe_mongodb_uri(self) -> Optional[str]:
        """Return masked MongoDB URI safe for display."""
        return redact_uri(self.mongodb_uri)

    def __repr__(self) -> str:
        return (
            f"BotConfig("
            f"token={self.safe_token!r}, "
            f"command_prefix={self.command_prefix!r}, "
            f"description={self.description!r}, "
            f"embed_color={self.embed_color!r}, "
            f"mongodb_uri={self.safe_mongodb_uri!r}, "
            f"mongodb_database={self.mongodb_database!r}, "
            f"mongodb_min_pool_size={self.mongodb_min_pool_size!r}, "
            f"mongodb_max_pool_size={self.mongodb_max_pool_size!r}, "
            f"mongodb_timeout_ms={self.mongodb_timeout_ms!r}, "
            f"log_level={self.log_level!r}, "
            f"logs_dir={self.logs_dir!r}, "
            f"sync_commands_on_startup={self.sync_commands_on_startup!r})"
        )

    def validate(self, require_token: bool = False) -> None:
        """Validate configuration values, types, and operational bounds."""
        if require_token:
            if not self.token or self.token in ("<token>", "your_discord_bot_token_here"):
                raise ValueError(
                    "DISCORD_TOKEN is missing or set to placeholder. "
                    "Please set a valid DISCORD_TOKEN environment variable."
                )

        if self.mongodb_min_pool_size < 0:
            raise ValueError(f"MONGODB_MIN_POOL_SIZE must be >= 0, got {self.mongodb_min_pool_size}")

        if self.mongodb_max_pool_size < 1:
            raise ValueError(f"MONGODB_MAX_POOL_SIZE must be >= 1, got {self.mongodb_max_pool_size}")

        if self.mongodb_min_pool_size > self.mongodb_max_pool_size:
            raise ValueError(
                f"MONGODB_MIN_POOL_SIZE ({self.mongodb_min_pool_size}) cannot exceed "
                f"MONGODB_MAX_POOL_SIZE ({self.mongodb_max_pool_size})"
            )

        if self.mongodb_timeout_ms < 100:
            raise ValueError(f"MONGODB_TIMEOUT_MS must be >= 100ms, got {self.mongodb_timeout_ms}")

        if self.log_level not in VALID_LOG_LEVELS:
            raise ValueError(
                f"Invalid LOG_LEVEL '{self.log_level}'. Must be one of: {', '.join(VALID_LOG_LEVELS)}"
            )

    @classmethod
    def load(cls, env_path: Optional[Union[str, pathlib.Path]] = ".env") -> BotConfig:
        """Load configuration strictly from environment variables.

        If a local .env file exists (or specified), it will be loaded without
        overwriting existing injected system environment variables.
        """
        # Load local .env only if file exists, never overwriting existing OS env vars
        if env_path is not None:
            path_obj = pathlib.Path(env_path)
            if path_obj.is_file():
                load_dotenv(dotenv_path=path_obj, override=False)

        # 1. Token
        token = os.getenv("DISCORD_TOKEN", "").strip()

        # 2. Command Prefix
        prefix_env = os.getenv("COMMAND_PREFIX")
        if prefix_env is not None:
            prefixes = [p.strip() for p in prefix_env.split(",") if p.strip()]
            command_prefix = prefixes if prefixes else ["!", "?"]
        else:
            command_prefix = ["!", "?"]

        # 3. Description
        description = os.getenv("BOT_DESCRIPTION", "I'm a example bot!")

        # 4. Embed Color
        embed_color_raw = os.getenv("EMBED_COLOR")
        embed_color: Optional[int] = None
        if embed_color_raw is not None and embed_color_raw.strip():
            val = embed_color_raw.strip()
            try:
                embed_color = int(val, 16) if val.startswith("0x") else int(val)
            except ValueError:
                embed_color = None

        # 5. MongoDB Settings
        mongodb_uri = os.getenv("MONGODB_URI")
        if mongodb_uri and not mongodb_uri.strip():
            mongodb_uri = None

        mongodb_database = (
            os.getenv("MONGODB_DATABASE")
            or os.getenv("MONGODB_DB_NAME")
            or "example_bot"
        ).strip()

        def _parse_int(name: str, default: int) -> int:
            raw = os.getenv(name)
            if raw is None or not raw.strip():
                return default
            try:
                return int(raw.strip())
            except ValueError:
                raise ValueError(f"Environment variable '{name}' must be an integer, got '{raw}'")

        mongodb_min_pool_size = _parse_int("MONGODB_MIN_POOL_SIZE", 0)
        mongodb_max_pool_size = _parse_int("MONGODB_MAX_POOL_SIZE", 20)
        mongodb_timeout_ms = _parse_int("MONGODB_TIMEOUT_MS", 5000)

        # 6. Logging Settings
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        logs_dir = os.getenv("LOGS_DIR", "logs").strip()

        # 7. Sync Commands
        sync_env = os.getenv("SYNC_COMMANDS_ON_STARTUP")
        sync_commands = sync_env.lower() in ("true", "1", "yes") if sync_env is not None else False

        config = cls(
            token=token,
            command_prefix=command_prefix,
            description=description,
            embed_color=embed_color,
            mongodb_uri=mongodb_uri,
            mongodb_database=mongodb_database,
            mongodb_min_pool_size=mongodb_min_pool_size,
            mongodb_max_pool_size=mongodb_max_pool_size,
            mongodb_timeout_ms=mongodb_timeout_ms,
            log_level=log_level,
            logs_dir=logs_dir,
            sync_commands_on_startup=sync_commands,
        )

        config.validate(require_token=False)
        return config
