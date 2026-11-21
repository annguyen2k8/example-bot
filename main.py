"""Application entry point for ExampleBot.

Handles environment variable configuration loading, logging initialization,
database lifecycle, and Discord bot bootstrap.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional, Union

import discord

from bot.client import ExampleBot
from bot.config import BotConfig
from bot.logging import get_logger, setup_logging
from database.connection import MongoManager

logger = get_logger("bootstrap")


async def async_main(config: Optional[BotConfig] = None) -> None:
    """Asynchronous entry point orchestrating bot and database lifecycle."""
    if config is None:
        try:
            config = BotConfig.load(require_token=True)
        except ValueError as e:
            logger.critical("Configuration error: %s", e)
            sys.exit(1)

    setup_logging(
        logs_dir=config.logs_dir,
        log_level=config.log_level,
    )

    try:
        config.validate(require_token=True)
    except ValueError as e:
        logger.critical("Configuration validation error: %s", e)
        sys.exit(1)

    logger.info("Runtime configuration initialized: %s", config)

    mongo_manager: Optional[MongoManager] = None
    if config.mongodb_uri:
        logger.info("Initializing MongoDB manager (%s)...", config.mongodb_database)
        mongo_manager = MongoManager(
            uri=config.mongodb_uri,
            db_name=config.mongodb_database,
            max_pool_size=config.mongodb_max_pool_size,
            min_pool_size=config.mongodb_min_pool_size,
            server_selection_timeout_ms=config.mongodb_timeout_ms,
            connect_timeout_ms=config.mongodb_timeout_ms,
        )

    bot = ExampleBot(config=config, mongo_manager=mongo_manager)

    try:
        async with bot:
            logger.info("Starting bot gateway connection...")
            await bot.start(config.token)
    except discord.LoginFailure as e:
        logger.critical("Authentication failure: Invalid Discord credentials provided (%s).", e)
        sys.exit(1)
    except (discord.HTTPException, discord.GatewayNotFound, discord.ConnectionClosed) as e:
        logger.critical("Discord API/Gateway connection failure: %s", e, exc_info=True)
        sys.exit(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Bot execution stopped.")
    except Exception as e:
        logger.critical("Fatal error encountered during bot runtime: %s", e, exc_info=True)
        sys.exit(1)
    finally:
        if mongo_manager is not None and mongo_manager.is_connected:
            logger.info("Ensuring MongoDB manager shutdown...")
            try:
                await mongo_manager.disconnect()
            except Exception as e:
                logger.error("Error during MongoDB manager shutdown: %s", e)


def start_bot(config_source: Optional[Union[BotConfig, str]] = None) -> None:
    """Synchronous launcher provided for entrypoint invocation."""
    try:
        if isinstance(config_source, BotConfig):
            cfg = config_source
        elif isinstance(config_source, str):
            cfg = BotConfig.load(config_source, require_token=True)
        else:
            cfg = BotConfig.load(require_token=True)
    except ValueError as e:
        logger.critical("Configuration error: %s", e)
        sys.exit(1)

    try:
        asyncio.run(async_main(cfg))
    except KeyboardInterrupt:
        logger.info("Terminated by user keyboard interrupt.")


if __name__ == "__main__":
    start_bot()
