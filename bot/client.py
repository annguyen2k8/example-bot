"""Discord Bot client implementation with modular extension loading and lifecycle management."""

from __future__ import annotations

import datetime
import pathlib
import sys
from typing import Any, Dict, List, Optional

import discord
from discord.ext import commands

from bot.config import BotConfig
from bot.logging import get_logger
from database.connection import MongoManager
from database.repositories.bot_stats import BotStatsRepository
from database.repositories.guild_settings import GuildSettingsRepository

logger = get_logger("client")


class ExampleBot(commands.Bot):
    """Custom Discord bot supporting asynchronous lifecycle hooks, Mongo repositories, and dynamic cogs."""

    def __init__(
        self,
        config: BotConfig,
        mongo_manager: Optional[MongoManager] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the bot with configuration and optional database manager."""
        intents = kwargs.pop("intents", discord.Intents.all())

        super().__init__(
            command_prefix=config.command_prefix,
            description=config.description,
            intents=intents,
            **kwargs,
        )

        self.config = config
        self.mongo = mongo_manager
        self.start_time: datetime.datetime = datetime.datetime.now()

        # Repositories (initialized in setup_hook when DB is ready)
        self.guild_settings: Optional[GuildSettingsRepository] = None
        self.bot_stats: Optional[BotStatsRepository] = None

    async def setup_hook(self) -> None:
        """Asynchronous initialization hook called before the bot connects to Discord gateway."""
        logger.info("Running setup_hook...")

        # 1. Initialize MongoDB connection & repositories
        if self.mongo is not None:
            try:
                if not self.mongo.is_connected:
                    await self.mongo.connect()

                if self.mongo.db is not None:
                    self.guild_settings = GuildSettingsRepository(self.mongo.db["guild_settings"])
                    self.bot_stats = BotStatsRepository(self.mongo.db["bot_stats"])

                    logger.info("Initializing collection indexes...")
                    await self.guild_settings.create_indexes()
                    await self.bot_stats.create_indexes()
                    logger.info("Database repositories ready.")
            except Exception as e:
                logger.error("Failed to initialize database during setup_hook: %s", e)
                # We continue so bot can still start in degraded/offline mode if desired

        # 2. Discover and load extensions (Cogs)
        await self.load_cogs()

        # 3. Synchronize application commands if requested
        if self.config.sync_commands_on_startup:
            await self.sync_commands()

    async def load_cogs(self, cogs_dir: str = "cogs") -> None:
        """Dynamically load extensions from the cogs directory safely."""
        cogs_path = pathlib.Path(cogs_dir)
        if not cogs_path.is_dir():
            logger.warning("Cogs directory '%s' not found. Skipping cog loading.", cogs_dir)
            return

        loaded_cogs: List[str] = []
        failed_cogs: List[str] = []

        for item in sorted(cogs_path.iterdir()):
            cog_name = item.name

            # Skip hidden files and special directories
            if cog_name.startswith((".", "_")):
                continue

            extension_target: Optional[str] = None
            if item.is_dir():
                # Directory cog: check for main.py or __init__.py
                if (item / "main.py").is_file():
                    extension_target = f"cogs.{cog_name}.main"
                elif (item / "__init__.py").is_file():
                    extension_target = f"cogs.{cog_name}"
            elif item.is_file() and item.suffix == ".py":
                # Single-file cog
                extension_target = f"cogs.{item.stem}"

            if not extension_target:
                continue

            try:
                await self.load_extension(extension_target)
                loaded_cogs.append(cog_name)
                logger.info("Loaded cog: %s (as %s)", cog_name, extension_target)
            except Exception as e:
                failed_cogs.append(cog_name)
                logger.error("Failed to load cog '%s': %s", cog_name, e, exc_info=True)

        logger.info(
            "Cog loading summary: %d loaded (%s), %d failed (%s)",
            len(loaded_cogs),
            ", ".join(loaded_cogs) or "none",
            len(failed_cogs),
            ", ".join(failed_cogs) or "none",
        )

    async def sync_commands(self) -> None:
        """Synchronize hybrid and slash commands with Discord."""
        try:
            logger.info("Syncing application command tree...")
            synced = await self.tree.sync()
            logger.info(
                "Command sync complete: %d application commands synced, %d prefix commands registered",
                len(synced),
                len(self.commands),
            )
        except Exception as error:
            logger.error("Failed to sync application commands: %s", error, exc_info=True)

    async def close(self) -> None:
        """Gracefully shutdown bot services, closing database connections and gateway sessions."""
        logger.info("Bot is shutting down...")
        if self.mongo is not None and self.mongo.is_connected:
            try:
                await self.mongo.disconnect()
            except Exception as e:
                logger.error("Error while disconnecting MongoDB: %s", e)

        await super().close()
        logger.info("Bot shutdown completed.")

    async def on_ready(self) -> None:
        """Triggered when the client is logged in and gateway cache is ready."""
        elapsed = datetime.datetime.now() - self.start_time
        user_info = f"{self.user} (ID: {self.user.id})" if self.user else "Unknown"
        logger.info("Logged in as %s", user_info)
        logger.info(
            "Startup took %dms. Connected to %d guilds with latency %dms.",
            round(elapsed.total_seconds() * 1000),
            len(self.guilds),
            round(self.latency * 1000),
        )

    async def on_command_completion(self, ctx: commands.Context) -> None:
        """Track command metrics upon successful completion."""
        if self.bot_stats is not None and ctx.command is not None:
            try:
                await self.bot_stats.record_command_invocation(ctx.command.qualified_name)
            except Exception as e:
                logger.warning("Failed to record command usage for %s: %s", ctx.command.qualified_name, e)

    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        """Global error handling for command execution."""
        # Unwrap CommandInvokeError
        if isinstance(error, commands.CommandInvokeError):
            error = error.original  # type: ignore[assignment]

        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("You do not have the required permissions to use this command.")
            return

        if isinstance(error, commands.NotOwner):
            await ctx.reply("This command is restricted to the bot owner.")
            return

        if isinstance(error, commands.NoPrivateMessage):
            await ctx.reply("This command cannot be used in private messages.")
            return

        if isinstance(error, commands.CommandNotFound):
            return  # Silently ignore unknown prefix commands

        logger.error(
            "Unhandled exception in command '%s': %s",
            ctx.command.qualified_name if ctx.command else "Unknown",
            error,
            exc_info=error,
        )
