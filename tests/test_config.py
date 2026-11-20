"""Tests for configuration parsing and loading."""

from __future__ import annotations

import json
import pathlib
import pytest

from bot.config import BotConfig


def test_default_config() -> None:
    config = BotConfig()
    assert config.token == ""
    assert config.command_prefix == ["!", "?"]
    assert config.description == "I'm a example bot!"
    assert config.mongodb_db_name == "example_bot"
    assert config.mongodb_uri is None
    assert config.mongodb_max_pool_size == 20
    assert config.mongodb_min_pool_size == 0
    assert config.mongodb_timeout_ms == 5000
    assert config.log_level == "INFO"
    assert config.sync_commands_on_startup is False


def test_load_from_json(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    config_file = tmp_path / "test_config.json"
    data = {
        "token": "test-json-token",
        "command_prefix": ["$"],
        "description": "Custom Description",
        "embed_color": "0x5865F2",
        "mongodb_uri": "mongodb://localhost:27017",
        "mongodb_db_name": "custom_db",
        "mongodb_max_pool_size": 30,
        "mongodb_min_pool_size": 2,
        "mongodb_timeout_ms": 3000,
        "log_level": "DEBUG",
        "sync_commands_on_startup": True,
    }
    config_file.write_text(json.dumps(data), encoding="utf-8")

    config = BotConfig.load(config_path=config_file)
    assert config.token == "test-json-token"
    assert config.command_prefix == ["$"]
    assert config.description == "Custom Description"
    assert config.embed_color == 0x5865F2
    assert config.mongodb_uri == "mongodb://localhost:27017"
    assert config.mongodb_db_name == "custom_db"
    assert config.mongodb_max_pool_size == 30
    assert config.mongodb_min_pool_size == 2
    assert config.mongodb_timeout_ms == 3000
    assert config.log_level == "DEBUG"
    assert config.sync_commands_on_startup is True


def test_env_var_override(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"token": "old-token"}), encoding="utf-8")

    monkeypatch.setenv("DISCORD_TOKEN", "secret-token-from-env")
    monkeypatch.setenv("COMMAND_PREFIX", ".,?,>")
    monkeypatch.setenv("MONGODB_URI", "mongodb://db.internal:27017")
    monkeypatch.setenv("MONGODB_DB_NAME", "production_bot")
    monkeypatch.setenv("MONGODB_MAX_POOL_SIZE", "50")
    monkeypatch.setenv("MONGODB_MIN_POOL_SIZE", "5")
    monkeypatch.setenv("MONGODB_TIMEOUT_MS", "8000")
    monkeypatch.setenv("SYNC_COMMANDS_ON_STARTUP", "1")

    config = BotConfig.load(config_path=config_file)
    assert config.token == "secret-token-from-env"
    assert config.command_prefix == [".", "?", ">"]
    assert config.mongodb_uri == "mongodb://db.internal:27017"
    assert config.mongodb_db_name == "production_bot"
    assert config.mongodb_max_pool_size == 50
    assert config.mongodb_min_pool_size == 5
    assert config.mongodb_timeout_ms == 8000
    assert config.sync_commands_on_startup is True


def test_invalid_json_handling(tmp_path: pathlib.Path) -> None:
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError, match="Failed to parse config file"):
        BotConfig.load(config_path=bad_file)


def test_invalid_pool_size_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGODB_MAX_POOL_SIZE", "not-an-integer")
    monkeypatch.setenv("MONGODB_MIN_POOL_SIZE", "invalid")
    config = BotConfig.load()
    assert config.mongodb_max_pool_size == 20
    assert config.mongodb_min_pool_size == 0
