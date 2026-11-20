"""Text and Discord markdown formatting helpers."""

from __future__ import annotations

from typing import Optional


def bold(text: str) -> str:
    """Format string as Discord bold."""
    return f"**{text}**"


def box(text: str, lang: str = "") -> str:
    """Format string inside a fenced code block."""
    return f"```{lang}\n{text}\n```"


def inline(text: str) -> str:
    """Format string inside inline backticks."""
    return f"`{text}`"


def italics(text: str) -> str:
    """Format string as Discord italics."""
    return f"*{text}*"


def strikethrough(text: str) -> str:
    """Format string with strikethrough."""
    return f"~~{text}~~"


def underline(text: str) -> str:
    """Format string as Discord underlined."""
    return f"__{text}__"


def escape(text: str, *, mass_mentions: bool = False, formatting: bool = False) -> str:
    """Escape Discord markdown or mass mentions in text."""
    if mass_mentions:
        text = text.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
    if formatting:
        text = (
            text.replace("`", "\\`")
            .replace("*", "\\*")
            .replace("_", "\\_")
            .replace("~", "\\~")
        )
    return text


def escape_mass_mentions(text: str) -> str:
    """Escape @everyone and @here mentions with zero-width spaces."""
    return escape(text, mass_mentions=True)


def format_timestamp(timestamp: float, style: Optional[str] = None) -> str:
    """Format a UNIX timestamp into Discord timestamp markdown (e.g. <t:123456789:R>)."""
    ts_int = int(timestamp)
    if style:
        return f"<t:{ts_int}:{style}>"
    return f"<t:{ts_int}>"


# Backward compatibility alias for legacy code
time = format_timestamp


def format_time(uptime: float) -> str:
    """Format seconds into human-readable days, hours, minutes, seconds string."""
    uptime = max(0.0, uptime)
    days, remainder = divmod(uptime, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"**`{int(days)}d` `{int(hours)}h` `{int(minutes)}m` `{int(seconds)}s`**"
