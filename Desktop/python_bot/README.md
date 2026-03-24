# Telegram Spread Monitor Bot

Production-ready Python Telegram bot that monitors spread formulas and sends alerts.

## Features

- Modular architecture (bot, commands, parser, DB, scheduler, pricing).
- SQLite storage with per-user rules.
- Formula support for `*` and `/`.
- Cached symbol prices (10-second TTL by default).
- Scheduler checks every 10 seconds.
- Cooldown (60s per rule) to avoid spam alerts.
- Alert window in Moscow time: 09:00-00:00.

## Project Structure

```text
project/
├─ bot/
│  └─ telegram_bot.py
├─ commands/
│  ├─ add_command.py
│  ├─ remove_command.py
│  ├─ edit_command.py
│  └─ list_command.py
├─ parser/
│  └─ formula_parser.py
├─ price/
│  └─ price_service.py
├─ spread/
│  └─ spread_calculator.py
├─ scheduler/
│  └─ spread_scheduler.py
├─ db/
│  └─ database_service.py
├─ model/
│  └─ spread_rule.py
└─ main.py
```

## Quick Start

1. Create and activate virtual env:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Set environment variables:

   ```bash
   cp .env.example .env
   export BOT_TOKEN="<your_token>"
   export DB_PATH="bot/spread-bot.sqlite"
   export POLL_INTERVAL_SECONDS=10
   export ALERT_COOLDOWN_SECONDS=60
   ```

4. Run:

   ```bash
   python main.py
   ```

## Telegram Commands

- `/add <formula> <upper> <lower>`
- `/list`
- `/remove <id>`
- `/edit <id> <upper> <lower>`

Examples:

```text
/add RUS:SV1!/TVC:SILVER*1000 1400 1200
/add RUS:SI2!/RUS:CR2!/FX:USDCNH*1000 2200 1800
```

## Testing

```bash
python -m unittest discover -s tests -v
```

## Extending to Live TradingView Data

To replace mock prices:

1. Implement a live connector in `price/price_service.py`.
2. Replace `_fetch_from_source` to query a WebSocket/feed cache.
3. Keep `get_prices` contract unchanged so scheduler code stays untouched.

