"""Centralized configuration management for ExampleBot.

Supports environment variables, .env file loading, and optional JSON fallback.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv


@dataclass
class BotConfig:
    """Type-safe configuration container for the bot."""

    token: str = ""
    command_prefix: List[str] = field(default_factory=lambda: ["!", "?"])
    description: Optional[str] = "I'm a example bot!"
    embed_color: Optional[int] = None
    mongodb_uri: Optional[str] = None
    mongodb_db_name: str = "example_bot"
    mongodb_max_pool_size: int = 20
    mongodb_min_pool_size: int = 0
    mongodb_timeout_ms: int = 5000
    log_level: str = "INFO"
    logs_dir: str = "logs"
    sync_commands_on_startup: bool = False

    @classmethod
    def load(cls, config_path: Optional[Union[str, pathlib.Path]] = None) -> BotConfig:
        """Load configuration from environment variables with optional JSON fallback.

        Priority order:
        1. Environment variables / .env
        2. config.json (if present or specified)
        3. Default values
        """
        load_dotenv(override=False)

        json_data: Dict[str, Any] = {}
        target_path: Optional[pathlib.Path] = None

        if config_path:
            target_path = pathlib.Path(config_path)
        elif pathlib.Path("config.json").is_file():
            target_path = pathlib.Path("config.json")

        if target_path and target_path.is_file():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    json_data = json.load(f)
            except Exception as e:
                raise ValueError(f"Failed to parse config file at {target_path}: {e}") from e

        # 1. Token
        token = os.getenv("DISCORD_TOKEN") or json_data.get("token") or ""

        # 2. Command Prefix
        prefix_env = os.getenv("COMMAND_PREFIX")
        if prefix_env is not None:
            prefixes = [p.strip() for p in prefix_env.split(",") if p.strip()]
            command_prefix = prefixes if prefixes else ["!", "?"]
        elif "command_prefix" in json_data:
            raw_prefix = json_data["command_prefix"]
            if isinstance(raw_prefix, list):
                command_prefix = [str(p) for p in raw_prefix]
            elif isinstance(raw_prefix, str):
                command_prefix = [raw_prefix]
            else:
                command_prefix = ["!", "?"]
        else:
            command_prefix = ["!", "?"]

        # 3. Description
        description = os.getenv("BOT_DESCRIPTION", json_data.get("description", "I'm a example bot!"))

        # 4. Embed color
        embed_color_raw = os.getenv("EMBED_COLOR", json_data.get("embed_color"))
        embed_color: Optional[int] = None
        if embed_color_raw is not None:
            if isinstance(embed_color_raw, int):
                embed_color = embed_color_raw
            elif isinstance(embed_color_raw, str) and embed_color_raw.strip():
                val = embed_color_raw.strip()
                try:
                    embed_color = int(val, 16) if val.startswith("0x") else int(val)
                except ValueError:
                    embed_color = None

        # 5. MongoDB settings
        mongodb_uri = os.getenv("MONGODB_URI") or json_data.get("mongodb_uri")
        if mongodb_uri and not mongodb_uri.strip():
            mongodb_uri = None

        mongodb_db_name = (
            os.getenv("MONGODB_DB_NAME")
            or json_data.get("mongodb_db_name")
            or "example_bot"
        )

        def _get_int(env_name: str, json_key: str, default: int) -> int:
            raw = os.getenv(env_name, json_data.get(json_key, default))
            try:
                return int(raw)
            except (ValueError, TypeError):
                return default

        mongodb_max_pool_size = _get_int("MONGODB_MAX_POOL_SIZE", "mongodb_max_pool_size", 20)
        mongodb_min_pool_size = _get_int("MONGODB_MIN_POOL_SIZE", "mongodb_min_pool_size", 0)
        mongodb_timeout_ms = _get_int("MONGODB_TIMEOUT_MS", "mongodb_timeout_ms", 5000)

        # 6. Logging settings
        log_level = os.getenv("LOG_LEVEL", json_data.get("log_level", "INFO")).upper()
        logs_dir = os.getenv("LOGS_DIR", json_data.get("logs_dir", "logs"))

        # 7. Sync commands
        sync_env = os.getenv("SYNC_COMMANDS_ON_STARTUP")
        if sync_env is not None:
            sync_commands = sync_env.lower() in ("true", "1", "yes")
        else:
            sync_commands = bool(json_data.get("sync_commands_on_startup", False))

        return cls(
            token=token,
            command_prefix=command_prefix,
            description=description,
            embed_color=embed_color,
            mongodb_uri=mongodb_uri,
            mongodb_db_name=mongodb_db_name,
            mongodb_max_pool_size=mongodb_max_pool_size,
            mongodb_min_pool_size=mongodb_min_pool_size,
            mongodb_timeout_ms=mongodb_timeout_ms,
            log_level=log_level,
            logs_dir=logs_dir,
            sync_commands_on_startup=sync_commands,
        )
