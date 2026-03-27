from __future__ import annotations

import asyncio
import logging
import os
import random
import ssl
import time

import certifi
from dotenv import load_dotenv  # <-- добавлено

# Загружаем переменные окружения из .env
load_dotenv()  # <-- добавлено

from bot.telegram_bot import build_telegram_bot
from bot.user_chat_registry import UserChatRegistry
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


def _build_tradingview_token_expiry_notify(
    loop: asyncio.AbstractEventLoop,
    bot,
    db,
    chats: UserChatRegistry,
):
    log = logging.getLogger(__name__)

    def notify(text: str) -> None:
        user_ids = db.list_distinct_user_ids_with_rules()
        if not user_ids:
            return

        async def _send() -> None:
            async def _send_one(uid: int) -> None:
                try:
                    chat_id = chats.get_chat_id(uid) or uid
                    await bot.send_message(chat_id=chat_id, text=text)
                except Exception as exc:
                    log.warning("TradingView token notify failed for user_id=%s: %s", uid, exc)

            await asyncio.gather(*(_send_one(uid) for uid in user_ids), return_exceptions=True)

        fut = asyncio.run_coroutine_threadsafe(_send(), loop)

        def _done(f: asyncio.Future) -> None:
            try:
                f.result()
            except Exception as exc:
                log.warning("TradingView token notify failed: %s", exc)

        fut.add_done_callback(_done)

    return notify


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    _configure_ssl_certificates()

    loop = asyncio.get_running_loop()
    bot_token = _require_env("BOT_TOKEN")
    db_path = os.getenv("DB_PATH", "bot/spread-bot.sqlite")
    interval_seconds = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
    cooldown_seconds = int(os.getenv("ALERT_COOLDOWN_SECONDS", "60"))
    price_provider = os.getenv("PRICE_PROVIDER", "mock").strip().lower()
    tv_timeframe = os.getenv("TRADINGVIEW_TIMEFRAME", "1")
    tv_candles = int(os.getenv("TRADINGVIEW_CANDLES", "1"))
    moex_contract_config_path = os.getenv("MOEX_CONTRACT_CONFIG_PATH", "price/moex_contracts.json")
    tradingview_auth_token = os.getenv("TRADINGVIEW_AUTH_TOKEN", "").strip()
    tradingview_human_mode_raw = os.getenv("TRADINGVIEW_HUMAN_MODE", "false").strip().lower()
    tradingview_human_mode = tradingview_human_mode_raw in {"1", "true", "yes", "y", "on"}
    tradingview_token_expires_raw = os.getenv("TRADINGVIEW_TOKEN_EXPIRES_AT", "").strip()
    tradingview_token_expires_at = PriceService.parse_tradingview_token_expires_at(
        tradingview_token_expires_raw or None
    )
    # Token expiry notifications are sent to all users who have at least one rule configured.

    db = DatabaseService(db_path=db_path)
    db.initialize()

    parser = FormulaParser()
    chats = UserChatRegistry()
    price_service = PriceService(
        cache_ttl_seconds=interval_seconds,
        provider=price_provider,
        tradingview_timeframe=tv_timeframe,
        tradingview_candles=tv_candles,
        moex_contract_config_path=moex_contract_config_path,
        tradingview_auth_token=tradingview_auth_token or None,
        tradingview_human_mode=tradingview_human_mode,
        tradingview_token_expires_at=tradingview_token_expires_at,
        token_expiry_telegram_notify=None,
    )
    app = build_telegram_bot(token=bot_token, db=db, price_service=price_service, chats=chats)
    tv_token_notify = _build_tradingview_token_expiry_notify(loop, app.bot, db, chats)
    # Wire after bot init (keep it internal; do not expose token in logs)
    price_service._token_expiry_telegram_notify = tv_token_notify
    calculator = SpreadCalculator(parser=parser)
    spread_scheduler = SpreadScheduler(
        bot=app.bot,
        db=db,
        parser=parser,
        price_service=price_service,
        calculator=calculator,
        interval_seconds=interval_seconds,
        cooldown_seconds=cooldown_seconds,
        human_mode=tradingview_human_mode,
    )
    if tradingview_human_mode and price_provider == "tradingview":
        delay = random.uniform(0, 10)
        logging.getLogger(__name__).info("Startup delay: %.2fs (humanized mode)", delay)
        time.sleep(delay)
    spread_scheduler.start()

    try:
        await app.run()
    finally:
        await spread_scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(run())