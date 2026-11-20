"""Tests for text and markdown formatting utilities."""

from __future__ import annotations

import pytest

from utils.formatting import (
    bold,
    box,
    escape,
    escape_mass_mentions,
    format_time,
    format_timestamp,
    inline,
    italics,
    strikethrough,
    time as format_time_alias,
    underline,
)


def test_markdown_styling() -> None:
    assert bold("hello") == "**hello**"
    assert italics("world") == "*world*"
    assert inline("code") == "`code`"
    assert underline("under") == "__under__"
    assert strikethrough("strike") == "~~strike~~"
    assert box("test", "py") == "```py\ntest\n```"
    assert box("test") == "```\ntest\n```"


def test_escape() -> None:
    text = "@everyone look at this `code` and *stars*"
    escaped_mentions = escape(text, mass_mentions=True)
    assert "@everyone" not in escaped_mentions
    assert "@\u200beveryone" in escaped_mentions

    escaped_formatting = escape(text, formatting=True)
    assert "\\`code\\`" in escaped_formatting
    assert "\\*stars\\*" in escaped_formatting

    assert escape_mass_mentions("@here") == "@\u200bhere"


def test_format_timestamp() -> None:
    ts = 1700000000.0
    assert format_timestamp(ts) == "<t:1700000000>"
    assert format_timestamp(ts, "R") == "<t:1700000000:R>"
    assert format_time_alias(ts) == "<t:1700000000>"


def test_format_time_durations() -> None:
    # 0 seconds
    assert format_time(0) == "**`0d` `0h` `0m` `0s`**"
    # Negative seconds clamped to 0
    assert format_time(-10) == "**`0d` `0h` `0m` `0s`**"
    # 65 seconds -> 1m 5s
    assert format_time(65) == "**`0d` `0h` `1m` `5s`**"
    # 3661 seconds -> 1h 1m 1s
    assert format_time(3661) == "**`0d` `1h` `1m` `1s`**"
    # 90061 seconds -> 1d 1h 1m 1s
    assert format_time(90061) == "**`1d` `1h` `1m` `1s`**"


def test_backward_compatibility_import() -> None:
    """Ensure legacy module utils.formating (one 't') can be imported and works identically."""
    import utils.formating as legacy

    assert legacy.bold("test") == "**test**"
    assert legacy.format_time(100) == format_time(100)
    assert legacy.time(1700000000) == "<t:1700000000>"
