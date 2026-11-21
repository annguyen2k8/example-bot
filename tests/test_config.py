"""Tests for environment variable configuration loading, validation, and secret redaction."""

from __future__ import annotations

import pathlib
import pytest

from bot.config import BotConfig, clean_token, redact_token, redact_uri


def test_default_config() -> None:
    config = BotConfig()
    assert config.token == ""
    assert config.command_prefix == ["!", "?"]
    assert config.description == "I'm a example bot!"
    assert config.mongodb_database == "example_bot"
    assert config.mongodb_db_name == "example_bot"
    assert config.mongodb_uri is None
    assert config.mongodb_max_pool_size == 20
    assert config.mongodb_min_pool_size == 0
    assert config.mongodb_timeout_ms == 5000
    assert config.log_level == "INFO"
    assert config.sync_commands_on_startup is False


def test_production_without_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure production containers work seamlessly with pure injected environment variables."""
    monkeypatch.setenv("DISCORD_TOKEN", "prod-token-123456")
    monkeypatch.setenv("COMMAND_PREFIX", "$,%")
    monkeypatch.setenv("BOT_DESCRIPTION", "Production Bot")
    monkeypatch.setenv("EMBED_COLOR", "0x5865F2")
    monkeypatch.setenv("MONGODB_URI", "mongodb://db.prod:27017")
    monkeypatch.setenv("MONGODB_DATABASE", "prod_bot_db")
    monkeypatch.setenv("MONGODB_MIN_POOL_SIZE", "2")
    monkeypatch.setenv("MONGODB_MAX_POOL_SIZE", "40")
    monkeypatch.setenv("MONGODB_TIMEOUT_MS", "4000")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("LOGS_DIR", "custom_logs")
    monkeypatch.setenv("SYNC_COMMANDS_ON_STARTUP", "true")

    # Pass nonexistent .env path to simulate production environment without .env file
    config = BotConfig.load(env_path="/nonexistent/.env")
    assert config.token == "prod-token-123456"
    assert config.command_prefix == ["$", "%"]
    assert config.description == "Production Bot"
    assert config.embed_color == 0x5865F2
    assert config.mongodb_uri == "mongodb://db.prod:27017"
    assert config.mongodb_database == "prod_bot_db"
    assert config.mongodb_min_pool_size == 2
    assert config.mongodb_max_pool_size == 40
    assert config.mongodb_timeout_ms == 4000
    assert config.log_level == "WARNING"
    assert config.logs_dir == "custom_logs"
    assert config.sync_commands_on_startup is True


def test_env_file_local_loading(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Ensure local development loads .env files when present."""
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("COMMAND_PREFIX", raising=False)
    monkeypatch.delenv("MONGODB_DATABASE", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=local-dev-token-999\n"
        "COMMAND_PREFIX=!,?\n"
        "MONGODB_DATABASE=local_dev\n"
        "MONGODB_MAX_POOL_SIZE=15\n",
        encoding="utf-8",
    )

    config = BotConfig.load(env_path=env_file)
    assert config.token == "local-dev-token-999"
    assert config.command_prefix == ["!", "?"]
    assert config.mongodb_database == "local_dev"
    assert config.mongodb_max_pool_size == 15


def test_env_var_precedence_over_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Ensure injected system environment variables take precedence over .env file values."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DISCORD_TOKEN=from-file-token\n"
        "COMMAND_PREFIX=.,;\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DISCORD_TOKEN", "override-env-token")
    monkeypatch.setenv("COMMAND_PREFIX", ">>")

    config = BotConfig.load(env_path=env_file)
    assert config.token == "override-env-token"
    assert config.command_prefix == [">>"]


def test_validation_require_token() -> None:
    config = BotConfig(token="")
    with pytest.raises(ValueError, match="DISCORD_TOKEN is missing"):
        config.validate(require_token=True)

    config_placeholder = BotConfig(token="<token>")
    with pytest.raises(ValueError, match="DISCORD_TOKEN is missing"):
        config_placeholder.validate(require_token=True)


def test_validation_pool_bounds() -> None:
    # min_pool_size < 0
    with pytest.raises(ValueError, match="MONGODB_MIN_POOL_SIZE must be >= 0"):
        BotConfig(mongodb_min_pool_size=-1).validate()

    # max_pool_size < 1
    with pytest.raises(ValueError, match="MONGODB_MAX_POOL_SIZE must be >= 1"):
        BotConfig(mongodb_max_pool_size=0).validate()

    # min_pool_size > max_pool_size
    with pytest.raises(ValueError, match="cannot exceed MONGODB_MAX_POOL_SIZE"):
        BotConfig(mongodb_min_pool_size=30, mongodb_max_pool_size=20).validate()


def test_validation_timeout() -> None:
    with pytest.raises(ValueError, match="MONGODB_TIMEOUT_MS must be >= 100ms"):
        BotConfig(mongodb_timeout_ms=50).validate()


def test_validation_log_level() -> None:
    with pytest.raises(ValueError, match="Invalid LOG_LEVEL"):
        BotConfig(log_level="VERBOSE").validate()


def test_non_integer_env_var_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGODB_MAX_POOL_SIZE", "not-a-number")
    with pytest.raises(ValueError, match="must be an integer"):
        BotConfig.load(env_path=None)


def test_secret_redaction() -> None:
    # Redact token
    assert redact_token("MTU1MTkxOTkzMDQxMTE4ODMyNA") == "MTU1...MyNA"
    assert redact_token("short") == "[REDACTED]"
    assert redact_token("") == "[EMPTY]"

    # Redact MongoDB URI
    raw_uri = "mongodb://botuser:supersecretpass@cluster0.abc.mongodb.net:27017/db"
    safe_uri = redact_uri(raw_uri)
    assert safe_uri == "mongodb://botuser:***@cluster0.abc.mongodb.net:27017/db"
    assert "supersecretpass" not in safe_uri

    # Test BotConfig repr masking
    config = BotConfig(
        token="super-secret-discord-token",
        mongodb_uri="mongodb://admin:mypassword@localhost:27017",
    )
    repr_str = repr(config)
    assert "super-secret-discord-token" not in repr_str
    assert "mypassword" not in repr_str
    assert "supe...oken" in repr_str
    assert "mongodb://admin:***@localhost:27017" in repr_str


def test_clean_token() -> None:
    """Test token cleaning: whitespace, quotes, and prefix stripping."""
    assert clean_token("  my_token  ") == "my_token"
    assert clean_token("\tmy_token\n\r") == "my_token"
    assert clean_token('"my_token"') == "my_token"
    assert clean_token("'my_token'") == "my_token"
    assert clean_token('"  my_token  "') == "my_token"
    assert clean_token("Bot my_token") == "my_token"
    assert clean_token("bot my_token") == "my_token"
    assert clean_token("Bearer my_token") == "my_token"
    assert clean_token("bearer my_token") == "my_token"
    assert clean_token('  "Bot my_token"  ') == "my_token"
    assert clean_token("Bot Bot my_token") == "my_token"
    assert clean_token('Bearer "Bot my_token"') == "my_token"
    assert clean_token("Bot 'Bot my_token'") == "my_token"
    assert clean_token("   ") == ""
    assert clean_token("") == ""
    assert clean_token(None) == ""


def test_bot_config_post_init() -> None:
    """Ensure BotConfig sanitizes values in __post_init__."""
    config = BotConfig(
        token="  Bot test-token-123  ",
        mongodb_uri="  mongodb://localhost:27017  ",
        mongodb_database="  my_db  ",
        logs_dir="  my_logs  ",
        log_level="  debug  ",
        description="  Bot Description  ",
    )
    assert config.token == "test-token-123"
    assert config.mongodb_uri == "mongodb://localhost:27017"
    assert config.mongodb_database == "my_db"
    assert config.logs_dir == "my_logs"
    assert config.log_level == "DEBUG"
    assert config.description == "Bot Description"


def test_validation_whitespace_and_placeholder_tokens() -> None:
    """Test that empty or placeholder tokens fail early."""
    with pytest.raises(ValueError, match="DISCORD_TOKEN is missing or set to placeholder"):
        BotConfig(token="   ").validate(require_token=True)

    with pytest.raises(ValueError, match="DISCORD_TOKEN is missing or set to placeholder"):
        BotConfig(token="your_discord_bot_token_here").validate(require_token=True)

    with pytest.raises(ValueError, match="DISCORD_TOKEN is missing or set to placeholder"):
        BotConfig(token="change_me").validate(require_token=True)


def test_validation_malformed_token_whitespace() -> None:
    """Ensure tokens containing internal whitespace are rejected."""
    with pytest.raises(ValueError, match="token cannot contain whitespace"):
        BotConfig(token="token with spaces").validate(require_token=True)


def test_validation_malformed_mongodb_uri() -> None:
    """Ensure invalid MongoDB URI schemes are rejected."""
    with pytest.raises(ValueError, match="Invalid MONGODB_URI scheme"):
        BotConfig(mongodb_uri="http://localhost:27017").validate()


def test_validation_malformed_embed_color() -> None:
    """Ensure out-of-range embed colors are rejected."""
    with pytest.raises(ValueError, match="EMBED_COLOR must be an integer between"):
        BotConfig(embed_color=-1).validate()

    with pytest.raises(ValueError, match="EMBED_COLOR must be an integer between"):
        BotConfig(embed_color=0x1000000).validate()


def test_load_with_bot_prefix(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Ensure tokens prefixed with 'Bot ' or quotes in .env are cleaned upon loading."""
    env_file = tmp_path / ".env"
    env_file.write_text('DISCORD_TOKEN="Bot my-secret-token"\n', encoding="utf-8")
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)

    config = BotConfig.load(env_path=env_file)
    assert config.token == "my-secret-token"


def test_load_token_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure token alias environment variables are recognized."""
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "alias-token-1")
    config1 = BotConfig.load(env_path=None)
    assert config1.token == "alias-token-1"

    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setenv("BOT_TOKEN", "alias-token-2")
    config2 = BotConfig.load(env_path=None)
    assert config2.token == "alias-token-2"


def test_load_fallback_when_os_env_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Ensure empty OS env var falls back to .env file value."""
    env_file = tmp_path / ".env"
    env_file.write_text("DISCORD_TOKEN=file-fallback-token\n", encoding="utf-8")

    monkeypatch.setenv("DISCORD_TOKEN", "   ")
    config = BotConfig.load(env_path=env_file)
    assert config.token == "file-fallback-token"


def test_load_fails_early_when_require_token_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure BotConfig.load with require_token=True raises ValueError on missing token."""
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    with pytest.raises(ValueError, match="DISCORD_TOKEN is missing or set to placeholder"):
        BotConfig.load(env_path=None, require_token=True)


def test_load_whitespace_padded_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure whitespace-padded env vars are stripped cleanly."""
    monkeypatch.setenv("DISCORD_TOKEN", "   token_padded   ")
    monkeypatch.setenv("MONGODB_URI", "   mongodb://localhost:27017   ")
    monkeypatch.setenv("MONGODB_DATABASE", "   custom_db   ")
    monkeypatch.setenv("LOG_LEVEL", "   warning   ")

    config = BotConfig.load(env_path=None)
    assert config.token == "token_padded"
    assert config.mongodb_uri == "mongodb://localhost:27017"
    assert config.mongodb_database == "custom_db"
    assert config.log_level == "WARNING"

