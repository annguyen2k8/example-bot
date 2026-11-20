"""Tests for permission check functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest
import discord
from discord.ext import commands

from utils.checks import (
    check_guild_permissions,
    check_permissions,
    is_admin,
    is_mod,
)


@pytest.fixture
def mock_ctx() -> MagicMock:
    ctx = MagicMock(spec=commands.Context)
    ctx.bot = MagicMock(spec=commands.Bot)
    ctx.bot.is_owner = AsyncMock(return_value=False)
    ctx.guild = MagicMock(spec=discord.Guild)
    ctx.channel = MagicMock()
    ctx.author = MagicMock(spec=discord.Member)
    return ctx


@pytest.mark.asyncio
async def test_owner_bypass_channel_perms(mock_ctx: MagicMock) -> None:
    mock_ctx.bot.is_owner.return_value = True
    assert await check_permissions(mock_ctx, {"send_messages": True}) is True


@pytest.mark.asyncio
async def test_channel_perms_dm_fails(mock_ctx: MagicMock) -> None:
    mock_ctx.guild = None
    assert await check_permissions(mock_ctx, {"send_messages": True}) is False


@pytest.mark.asyncio
async def test_channel_perms_evaluation(mock_ctx: MagicMock) -> None:
    perms = MagicMock()
    perms.send_messages = True
    perms.manage_messages = False
    mock_ctx.channel.permissions_for.return_value = perms

    # All match
    assert await check_permissions(mock_ctx, {"send_messages": True}) is True
    # One fails with default all
    assert await check_permissions(mock_ctx, {"send_messages": True, "manage_messages": True}) is False
    # One matches with check=any
    assert await check_permissions(mock_ctx, {"send_messages": True, "manage_messages": True}, check=any) is True


@pytest.mark.asyncio
async def test_guild_perms_evaluation(mock_ctx: MagicMock) -> None:
    guild_perms = MagicMock()
    guild_perms.administrator = True
    guild_perms.manage_guild = True
    mock_ctx.author.guild_permissions = guild_perms

    assert await check_guild_permissions(mock_ctx, {"administrator": True}) is True

    guild_perms.administrator = False
    assert await check_guild_permissions(mock_ctx, {"administrator": True}) is False


@pytest.mark.asyncio
async def test_guild_perms_dm_fails(mock_ctx: MagicMock) -> None:
    mock_ctx.guild = None
    assert await check_guild_permissions(mock_ctx, {"administrator": True}) is False
