"""Backward compatibility proxy module for utils.formatting."""

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
    time,
    underline,
)

__all__ = [
    "bold",
    "box",
    "inline",
    "italics",
    "strikethrough",
    "underline",
    "escape",
    "escape_mass_mentions",
    "format_timestamp",
    "time",
    "format_time",
]
