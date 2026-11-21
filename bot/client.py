"""Discord Bot client implementation with modular extension loading and lifecycle management."""

from __future__ import annotations

import asyncio
import datetime
import pathlib
from typing import TYPE_CHECKING, Any, Coroutine, List, Optional, Set, TypeVar

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import BotConfig
from bot.logging import get_logger
from database.repositories.bot_stats import BotStatsRepository
from database.repositories.guild_settings import GuildSettingsRepository

if TYPE_CHECKING:
    from database.connection import MongoManager

logger = get_logger("client")
T = TypeVar("T")


class AppCommandTree(app_commands.CommandTree):
    """Custom command tree tracking application and slash command lifecycles."""

    async def _call(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        client: BotBase = self.client  # type: ignore[assignment]
        if hasattr(client, "_on_command_started"):
            client._on_command_started()
        try:
            await super()._call(interaction)
        finally:
            if hasattr(client, "_on_command_finished"):
                await client._on_command_finished()


async def get_command_prefix(bot: BotBase, message: discord.Message) -> List[str]:
    """Dynamically resolve command prefixes, checking per-guild custom prefix if available."""
    default_prefixes = list(bot.config.command_prefix)
    if message.guild is not None and bot.guild_settings is not None:
        try:
            custom = await bot.guild_settings.get_prefix(message.guild.id)
            if custom:
                return [custom]
        except Exception as e:
            logger.warning("Failed to lookup guild prefix; using defaults: %s", e)
    return default_prefixes


class BotBase(commands.Bot):
    """Custom Discord bot supporting asynchronous lifecycle hooks, Mongo repositories, and dynamic cogs."""

    def __init__(
        self,
        config: BotConfig,
        mongo_manager: Optional[MongoManager] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the bot with configuration and optional database manager."""
        intents = kwargs.pop("intents", discord.Intents.all())
        tree_cls = kwargs.pop("tree_cls", AppCommandTree)

        super().__init__(
            command_prefix=get_command_prefix,
            description=config.description,
            intents=intents,
            tree_cls=tree_cls,
            **kwargs,
        )

        self.config = config
        self.mongo = mongo_manager
        self.start_time: datetime.datetime = datetime.datetime.now()

        # Repositories (initialized when DB is ready)
        self.guild_settings: Optional[GuildSettingsRepository] = None
        self.bot_stats: Optional[BotStatsRepository] = None

        # Lock to eliminate race conditions during concurrent database reconnections
        self._db_lock = asyncio.Lock()

        # Active commands and background task tracking for safe teardown
        self._active_commands: int = 0
        self._all_commands_done: asyncio.Event = asyncio.Event()
        self._all_commands_done.set()
        self._background_tasks: Set[asyncio.Task[Any]] = set()

    def create_tracked_task(
        self,
        coro: Coroutine[Any, Any, T],
        *,
        name: Optional[str] = None,
    ) -> asyncio.Task[T]:
        """Create and track an asynchronous background task to ensure safe completion during shutdown."""
        task = asyncio.get_running_loop().create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def ensure_database_ready(self) -> bool:
        """Ensure MongoDB connection and repositories are ready without concurrent duplicate connects."""
        if self.mongo is None:
            return False

        if self.mongo.is_connected and self.guild_settings is not None and self.bot_stats is not None:
            return True

        async with self._db_lock:
            # Double-check connection state after acquiring lock
            if self.mongo.is_connected and self.guild_settings is not None and self.bot_stats is not None:
                return True

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
                    return True
            except Exception as e:
                logger.warning("Failed to establish database connection/repositories: %s", e)
                self.guild_settings = None
                self.bot_stats = None

            return False

    async def setup_hook(self) -> None:
        """Asynchronous initialization hook called before the bot connects to Discord gateway."""
        logger.info("Running setup_hook...")

        # 1. Initialize MongoDB connection & repositories (supports degraded mode if unavailable)
        await self.ensure_database_ready()

        # 2. Discover and load extensions (Cogs)
        await self.load_cogs()

        # 3. Synchronize application commands if requested
        if self.config.sync_commands_on_startup:
            await self.sync_commands()

    async def load_cogs(self, cogs_dir: str = "cogs") -> None:
        """Dynamically load extensions from the cogs directory safely."""
        cogs_path = pathlib.Path(cogs_dir)
        if not cogs_path.is_dir():
            project_cogs = pathlib.Path(__file__).resolve().parent.parent / cogs_dir
            if project_cogs.is_dir():
                cogs_path = project_cogs
            else:
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
                if (item / "main.py").is_file():
                    extension_target = f"cogs.{cog_name}.main"
                elif (item / "__init__.py").is_file():
                    extension_target = f"cogs.{cog_name}"
            elif item.is_file() and item.suffix == ".py":
                extension_target = f"cogs.{item.stem}"

            if not extension_target:
                continue

            if extension_target in self.extensions:
                logger.debug("Extension '%s' already loaded. Skipping.", extension_target)
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

    async def sync_commands(
        self,
        guild: Optional[discord.abc.Snowflake] = None,
    ) -> List[app_commands.AppCommand]:
        """Synchronize hybrid and slash commands with Discord."""
        # Ensure cogs and commands are discovered and loaded before syncing
        if not self.cogs:
            logger.info("No cogs loaded yet; loading cogs before syncing command tree...")
            await self.load_cogs()

        target_desc = f"guild {guild.id}" if guild is not None else "global scope"
        tree_commands = self.tree.get_commands(guild=guild)

        if not tree_commands:
            logger.warning(
                "No application commands registered in CommandTree for %s. Skipping tree.sync() to prevent clearing commands.",
                target_desc,
            )
            return []

        try:
            logger.info(
                "Syncing %d application command(s) (%s) to %s...",
                len(tree_commands),
                ", ".join(cmd.name for cmd in tree_commands),
                target_desc,
            )
            synced = await self.tree.sync(guild=guild)
            logger.info(
                "Command sync complete for %s: %d application commands synced, %d prefix commands registered",
                target_desc,
                len(synced),
                len(self.commands),
            )
            return synced
        except discord.Forbidden as error:
            logger.error(
                "Forbidden error while syncing application commands to %s: Bot lacks 'applications.commands' scope or authorization: %s",
                target_desc,
                error,
            )
            return []
        except discord.HTTPException as error:
            logger.error(
                "HTTPException while syncing application commands to %s (status %s): %s",
                target_desc,
                error.status,
                error,
                exc_info=True,
            )
            return []
        except Exception as error:
            logger.error("Failed to sync application commands to %s: %s", target_desc, error, exc_info=True)
            return []

    async def close(self) -> None:
        """Gracefully shutdown bot services, closing gateway sessions and database connections."""
        logger.info("Bot is shutting down...")

        # 1. Close Discord gateway session so no new commands arrive
        try:
            await super().close()
        except Exception as e:
            logger.error("Error while closing Discord client session: %s", e)

        # 2. Wait for in-flight commands and background tasks to finish accessing database
        has_pending = (self._active_commands > 0) or bool(self._background_tasks)
        if has_pending:
            logger.info(
                "Waiting for %d in-flight command(s) and %d background task(s) to finish...",
                self._active_commands,
                len(self._background_tasks),
            )
            try:
                wait_tasks = []
                if self._active_commands > 0:
                    wait_tasks.append(self._all_commands_done.wait())
                if self._background_tasks:
                    wait_tasks.append(asyncio.gather(*self._background_tasks, return_exceptions=True))

                await asyncio.wait_for(asyncio.gather(*wait_tasks), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Grace timeout reached; cancelling remaining tasks before database disconnect.")
                for task in list(self._background_tasks):
                    if not task.done():
                        task.cancel()
                if self._background_tasks:
                    await asyncio.gather(*list(self._background_tasks), return_exceptions=True)

        # 3. Disconnect MongoDB connection pool
        if self.mongo is not None and self.mongo.is_connected:
            try:
                await self.mongo.disconnect()
            except Exception as e:
                logger.error("Error while disconnecting MongoDB: %s", e)

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

    def _on_command_started(self) -> None:
        """Internal tracker called when any command (prefix or application) begins."""
        self._active_commands += 1
        self._all_commands_done.clear()

    async def _on_command_finished(self) -> None:
        """Internal tracker called when any command (prefix or application) finishes."""
        if self._active_commands > 0:
            self._active_commands -= 1
            if self._active_commands == 0:
                self._all_commands_done.set()

    async def on_command(self, ctx: commands.Context) -> None:
        """Track beginning of prefix command execution."""
        self._on_command_started()

    async def on_command_completion(self, ctx: commands.Context) -> None:
        """Track command metrics upon successful completion."""
        try:
            if self.bot_stats is not None and ctx.command is not None:
                try:
                    await self.bot_stats.record_command_invocation(ctx.command.qualified_name)
                except Exception as e:
                    logger.warning("Failed to record command usage for %s: %s", ctx.command.qualified_name, e)
        finally:
            await self._on_command_finished()

    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        """Global error handling for prefix command execution."""
        try:
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
                return

            logger.error(
                "Unhandled exception in command '%s': %s",
                ctx.command.qualified_name if ctx.command else "Unknown",
                error,
                exc_info=error,
            )
        finally:
            await self._on_command_finished()
