"""Example Cog demonstrating hybrid commands and health monitoring."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands
from discord.utils import oauth_url

from bot.logging import get_logger
from utils.formatting import bold, format_time, inline

logger = get_logger("cogs.example")

if TYPE_CHECKING:
    from bot.client import ExampleBot


class ExampleCog(commands.Cog, name="Example"):
    """Core informational and diagnostic commands."""

    def __init__(self, bot: ExampleBot) -> None:
        self.bot: ExampleBot = bot

    def get_uptime_seconds(self) -> float:
        """Calculate the total seconds since bot startup."""
        delta = datetime.datetime.now() - self.bot.start_time
        return delta.total_seconds()

    # Backward compatibility alias
    def get_uptime(self) -> float:
        return self.get_uptime_seconds()

    @commands.hybrid_command(name="ping", description="Check latency from the bot to discord.com")
    async def ping(self, ctx: commands.Context) -> None:
        """Measure gateway latency."""
        latency_ms = round(self.bot.latency * 1000)
        await ctx.reply(f"Pong! {latency_ms}ms")

    @commands.hybrid_command(name="link", description="Get install link for your server.")
    @commands.is_owner()
    async def link(self, ctx: commands.Context) -> None:
        """Generate a bot invite URL."""
        app_id = self.bot.application_id or (self.bot.user.id if self.bot.user else None)
        if app_id is None:
            await ctx.reply("Error: Bot application ID is not available.")
            return

        url = oauth_url(
            app_id,
            permissions=discord.Permissions(8),
            scopes=["bot", "applications.commands"],
        )
        await ctx.reply(url)

    @commands.hybrid_command(name="uptime", description="Get uptime from bot.")
    @commands.is_owner()
    async def uptime(self, ctx: commands.Context) -> None:
        """Display elapsed bot uptime."""
        await ctx.reply(f"{bold('Uptime:')} {format_time(self.get_uptime_seconds())}")

    @commands.hybrid_command(name="db_status", description="Check MongoDB connection health and metrics.")
    @commands.is_owner()
    async def db_status(self, ctx: commands.Context) -> None:
        """Inspect database connection health and top executed commands."""
        if self.bot.mongo is None:
            await ctx.reply("MongoDB is not configured for this bot instance.")
            return

        health = await self.bot.mongo.health_check()
        if not health.get("healthy"):
            error_msg = health.get("error", "Unknown error")
            await ctx.reply(f"MongoDB Status: {bold('Offline/Unhealthy')} ({inline(error_msg)})")
            return

        latency_str = f"{health.get('latency_ms')}ms"
        db_name_str = str(health.get("db_name"))
        status_text = (
            f"MongoDB Status: {bold('Healthy')}\n"
            f"Latency: {inline(latency_str)}\n"
            f"Database: {inline(db_name_str)}"
        )

        if self.bot.bot_stats is not None:
            try:
                top_cmds = await self.bot.bot_stats.get_top_commands(limit=3)
                if top_cmds:
                    cmd_summary = ", ".join(f"{c['command_name']} ({c['total_uses']})" for c in top_cmds)
                    status_text += f"\nTop Commands: {cmd_summary}"
            except Exception as e:
                logger.warning("Failed to fetch top command metrics: %s", e)

        await ctx.reply(status_text)


async def setup(bot: ExampleBot) -> None:
    """Extension entrypoint adding ExampleCog to the bot."""
    await bot.add_cog(ExampleCog(bot))
