"""Application entry point for ExampleBot.

Handles configuration loading, logging initialization, database lifecycle,
and Discord bot bootstrap.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from typing import Any, Dict, Optional, Union

from bot.client import ExampleBot
from bot.config import BotConfig
from bot.logging import get_logger, setup_logging
from database.connection import MongoManager

logger = get_logger("bootstrap")


async def async_main(config: Optional[BotConfig] = None) -> None:
    """Asynchronous entry point orchestrating bot and database lifecycle."""
    if config is None:
        config = BotConfig.load()

    setup_logging(
        logs_dir=config.logs_dir,
        log_level=config.log_level,
    )

    if not config.token or config.token == "<token>":
        logger.critical(
            "Discord bot token is missing or unset. "
            "Please set DISCORD_TOKEN in .env or provide 'token' in config.json."
        )
        sys.exit(1)

    mongo_manager: Optional[MongoManager] = None
    if config.mongodb_uri:
        logger.info("Initializing MongoDB manager...")
        mongo_manager = MongoManager(
            uri=config.mongodb_uri,
            db_name=config.mongodb_db_name,
        )

    bot = ExampleBot(config=config, mongo_manager=mongo_manager)

    loop = asyncio.get_running_loop()

    # Register OS signals for graceful shutdown when supported
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.close()))
            except (NotImplementedError, RuntimeError):
                pass

    try:
        logger.info("Starting bot gateway connection...")
        await bot.start(config.token)
    except asyncio.CancelledError:
        logger.info("Main loop received cancellation signal.")
    except Exception as e:
        logger.critical("Fatal error encountered during bot runtime: %s", e, exc_info=True)
        sys.exit(1)
    finally:
        if not bot.is_closed():
            await bot.close()


def start_bot(config_source: Optional[Union[Dict[str, Any], BotConfig, str]] = None) -> None:
    """Synchronous launcher provided for backward compatibility."""
    if isinstance(config_source, BotConfig):
        cfg = config_source
    elif isinstance(config_source, dict):
        cfg = BotConfig(
            token=config_source.get("token", ""),
            command_prefix=config_source.get("command_prefix", ["!", "?"]),
            description=config_source.get("description", "I'm a example bot!"),
            embed_color=config_source.get("embed_color"),
            mongodb_uri=config_source.get("mongodb_uri"),
            mongodb_db_name=config_source.get("mongodb_db_name", "example_bot"),
            log_level=config_source.get("log_level", "INFO"),
            logs_dir=config_source.get("logs_dir", "logs"),
        )
    elif isinstance(config_source, str):
        cfg = BotConfig.load(config_source)
    else:
        cfg = BotConfig.load()

    try:
        asyncio.run(async_main(cfg))
    except KeyboardInterrupt:
        logger.info("Terminated by user keyboard interrupt.")


if __name__ == "__main__":
    start_bot()
