# ExampleBot

A modern, modular, type-safe Discord bot built with [discord.py](https://github.com/Rapptz/discord.py) (v2.3+) and native asynchronous [MongoDB](https://www.mongodb.com/) via [PyMongo Async API](https://pymongo.readthedocs.io/).

---

## Overview

ExampleBot provides a robust, production-ready foundation for Discord bots with:
- **Centralized Configuration**: Environment variables (`.env`) with JSON fallback and connection pool tuning.
- **Native Asynchronous MongoDB**: Powered by PyMongo 4.9+ `AsyncMongoClient`, avoiding deprecated drivers (`motor`) and external threadpool overhead.
- **Degraded Offline Resilience**: Bot operates smoothly in offline mode if MongoDB is unavailable; commands degrade gracefully without crashing, and reconnect dynamically when the database returns.
- **Graceful Shutdown**: Active in-flight commands and background tasks complete before database sockets are disconnected.
- **Dynamic Guild Prefixes**: Server-specific command prefixes stored in MongoDB with automatic fallback to default prefixes.
- **Domain Repositories**: Focused Data Access Layer with automated, idempotent index management.
- **Dynamic Cog Loader**: Safe discovery of modular command extensions without blocking loops.
- **Structured Centralized Logging**: Timestamps, rotating file handlers, and severity formatting.
- **Full Backward Compatibility**: Legacy utility imports (`utils.formating`) and original command names (`ping`, `uptime`, `link`) remain fully supported.

---

## Architecture

```text
example-bot/
├── main.py                     # Application entry point & lifecycle bootstrap
├── bot/
│   ├── client.py               # ExampleBot subclass (dynamic prefix, in-flight task tracking, lifecycle)
│   ├── config.py               # Centralized configuration dataclass
│   └── logging.py              # Centralized rotating file & stream logger
├── database/
│   ├── connection.py           # MongoManager (pooling, connect, disconnect, health checks)
│   └── repositories/
│       ├── base.py             # Minimal BaseRepository interface
│       ├── guild_settings.py   # Per-guild configuration repository
│       └── bot_stats.py        # Command invocation and metrics repository
├── cogs/
│   └── example/
│       └── main.py             # Diagnostic & informational hybrid commands
├── utils/
│   ├── checks.py               # Channel & guild permission decorators
│   ├── formatting.py           # Markdown & duration formatting helpers
│   └── formating.py           # Backward compatibility alias module
└── tests/                      # Unit & integration test suite (pytest)
```

---

## Requirements

- Python **3.9+** (tested up to **Python 3.14**)
- Discord Bot Token with Gateway Intents configured in the Discord Developer Portal
- (Optional) MongoDB 5.0+ instance (local or Atlas)

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/annguyen2k8/example-bot.git
   cd example-bot
   ```

2. **Create and activate a virtual environment (recommended):**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

   For development & testing:
   ```bash
   pip install pytest pytest-asyncio
   ```

---

## Configuration

Copy the example environment file and configure your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```ini
# Discord Credentials
DISCORD_TOKEN=your_bot_token_here
COMMAND_PREFIX=!,?
BOT_DESCRIPTION=I'm a example bot!
EMBED_COLOR=0x5865F2

# MongoDB Database (leave empty or unset if not using database)
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=example_bot
MONGODB_MAX_POOL_SIZE=20
MONGODB_MIN_POOL_SIZE=0
MONGODB_TIMEOUT_MS=5000

# Operational Settings
LOG_LEVEL=INFO
LOGS_DIR=logs
SYNC_COMMANDS_ON_STARTUP=false
```

Alternatively, you can provide configuration via `config.json` (see `config.example.json`). Environment variables always take precedence.

---

## MongoDB Setup

ExampleBot integrates an asynchronous Data Access Layer using PyMongo's native `AsyncMongoClient`:
- **Native Async**: Uses standard Python `asyncio` coroutines directly without threadpool delegation.
- **Connection Pooling**: Configurable connection pool (`MONGODB_MAX_POOL_SIZE=20`, `MONGODB_MIN_POOL_SIZE=0` to scale down sockets when idle and conserve Atlas M0 quotas).
- **Health Checks & Reconnection**: Periodic or on-demand health checks (`db_status` command) that automatically restore repositories if the database recovers from an outage.
- **Graceful Lifecycle**: Sockets are initialized during `setup_hook` and closed when the bot shuts down after waiting for active in-flight commands.
- **Repositories**: Clean domain-driven repository layer with automated index creation:
  - `GuildSettingsRepository` (unique index on `guild_id`)
  - `BotStatsRepository` (unique index on `command_name`)

If `MONGODB_URI` is omitted or empty, the bot boots cleanly in standalone mode without database features.

---

## Running the Bot

Run the bot with:

```bash
python3 main.py
```

### Available Commands

| Command | Type | Description | Permissions |
| :--- | :--- | :--- | :--- |
| `ping` | Hybrid (`!ping` or `/ping`) | Returns gateway latency to Discord | Everyone |
| `uptime` | Hybrid (`!uptime` or `/uptime`) | Displays elapsed bot running time | Bot Owner |
| `link` | Hybrid (`!link` or `/link`) | Generates OAuth2 bot invite link | Bot Owner |
| `prefix` | Hybrid (`!prefix` or `/prefix`) | View or set custom server prefix | Manage Server / Owner |
| `db_status` | Hybrid (`!db_status` or `/db_status`) | Displays MongoDB health, latency & top commands | Bot Owner |

---

## Testing & Development

Run the full automated test suite with `pytest`:

```bash
pytest -v
```

All 36 unit and integration tests execute offline without requiring active external Discord or MongoDB credentials.
