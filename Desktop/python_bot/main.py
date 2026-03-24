from __future__ import annotations

import asyncio
import logging
import os
import ssl

import certifi
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


def _configure_ssl_certificates() -> None:
    """
    Ensure Python uses a valid CA bundle for outbound TLS connections.
    This helps websocket clients on macOS where system certs may be missing.
    """
    if not os.getenv("SSL_CERT_FILE"):
        os.environ["SSL_CERT_FILE"] = certifi.where()
    if not os.getenv("REQUESTS_CA_BUNDLE"):
        os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
    ssl._create_default_https_context = ssl.create_default_context


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    _configure_ssl_certificates()

    bot_token = _require_env("BOT_TOKEN")
    db_path = os.getenv("DB_PATH", "bot/spread-bot.sqlite")
    interval_seconds = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
    cooldown_seconds = int(os.getenv("ALERT_COOLDOWN_SECONDS", "60"))
    price_provider = os.getenv("PRICE_PROVIDER", "mock").strip().lower()
    tv_timeframe = os.getenv("TRADINGVIEW_TIMEFRAME", "1")
    tv_candles = int(os.getenv("TRADINGVIEW_CANDLES", "1"))
    moex_contract_config_path = os.getenv("MOEX_CONTRACT_CONFIG_PATH", "price/moex_contracts.json")

    db = DatabaseService(db_path=db_path)
    db.initialize()

    app = build_telegram_bot(token=bot_token, db=db)

    parser = FormulaParser()
    price_service = PriceService(
        cache_ttl_seconds=interval_seconds,
        provider=price_provider,
        tradingview_timeframe=tv_timeframe,
        tradingview_candles=tv_candles,
        moex_contract_config_path=moex_contract_config_path,
    )
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