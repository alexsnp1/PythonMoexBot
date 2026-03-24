from __future__ import annotations

import asyncio
import logging
import os
from dotenv import load_dotenv  # <-- добавлено

# Загружаем переменные окружения из .env
load_dotenv()  # <-- добавлено

from bot.telegram_bot import build_telegram_bot
from db.database_service import DatabaseService
from parser.formula_parser import FormulaParser
from price.price_service import PriceService
from scheduler.spread_scheduler import SpreadScheduler
from spread.spread_calculator import SpreadCalculator


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    bot_token = _require_env("BOT_TOKEN")
    db_path = os.getenv("DB_PATH", "bot/spread-bot.sqlite")
    interval_seconds = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
    cooldown_seconds = int(os.getenv("ALERT_COOLDOWN_SECONDS", "60"))

    db = DatabaseService(db_path=db_path)
    db.initialize()

    app = build_telegram_bot(token=bot_token, db=db)

    parser = FormulaParser()
    price_service = PriceService(cache_ttl_seconds=interval_seconds)
    calculator = SpreadCalculator(parser=parser)
    spread_scheduler = SpreadScheduler(
        bot=app.bot,
        db=db,
        parser=parser,
        price_service=price_service,
        calculator=calculator,
        interval_seconds=interval_seconds,
        cooldown_seconds=cooldown_seconds,
    )
    spread_scheduler.start()

    try:
        await app.run()
    finally:
        await spread_scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(run())