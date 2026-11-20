"""Custom permission and role checks for Discord commands."""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping

import discord
from discord.ext import commands


async def check_permissions(
    ctx: commands.Context,
    perms: Mapping[str, bool],
    *,
    check: Callable[..., bool] = all,
) -> bool:
    """Check permissions in the current channel, with owner bypass."""
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True

    if ctx.guild is None:
        # Channel-level permission checks for guild permissions cannot succeed in DMs
        return False

    resolved = ctx.channel.permissions_for(ctx.author)  # type: ignore[arg-type]
    return check(getattr(resolved, name, None) == value for name, value in perms.items())


def has_permissions(*, check: Callable[..., bool] = all, **perms: bool):
    """Command check decorator verifying channel permissions."""
    async def pred(ctx: commands.Context) -> bool:
        return await check_permissions(ctx, perms, check=check)

    return commands.check(pred)


async def check_guild_permissions(
    ctx: commands.Context,
    perms: Mapping[str, bool],
    *,
    check: Callable[..., bool] = all,
) -> bool:
    """Check guild-level permissions for the command author, with owner bypass."""
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True

    if ctx.guild is None or not isinstance(ctx.author, discord.Member):
        return False

    resolved = ctx.author.guild_permissions
    return check(getattr(resolved, name, None) == value for name, value in perms.items())


def has_guild_permissions(*, check: Callable[..., bool] = all, **perms: bool):
    """Command check decorator verifying guild-wide permissions."""
    async def pred(ctx: commands.Context) -> bool:
        return await check_guild_permissions(ctx, perms, check=check)

    return commands.check(pred)


def is_mod():
    """Command check requiring 'manage_guild' permission."""
    async def pred(ctx: commands.Context) -> bool:
        return await check_guild_permissions(ctx, {"manage_guild": True})

    return commands.check(pred)


def is_admin():
    """Command check requiring 'administrator' permission."""
    async def pred(ctx: commands.Context) -> bool:
        return await check_guild_permissions(ctx, {"administrator": True})

    return commands.check(pred)


def mod_or_permissions(**perms: bool):
    """Command check requiring manage_guild OR any of the specified permissions."""
    check_perms: Dict[str, bool] = dict(perms)
    check_perms["manage_guild"] = True

    async def predicate(ctx: commands.Context) -> bool:
        return await check_guild_permissions(ctx, check_perms, check=any)

    return commands.check(predicate)


def admin_or_permissions(**perms: bool):
    """Command check requiring administrator OR any of the specified permissions."""
    check_perms: Dict[str, bool] = dict(perms)
    check_perms["administrator"] = True

    async def predicate(ctx: commands.Context) -> bool:
        return await check_guild_permissions(ctx, check_perms, check=any)

    return commands.check(predicate)
