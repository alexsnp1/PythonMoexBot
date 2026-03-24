from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from db.database_service import DatabaseService
from parser.formula_parser import FormulaParser
from price.price_service import PriceService
from spread.spread_calculator import SpreadCalculator


MOSCOW_TZ = ZoneInfo("Europe/Moscow")


@dataclass(slots=True)
class SpreadScheduler:
    bot: Bot
    db: DatabaseService
    parser: FormulaParser
    price_service: PriceService
    calculator: SpreadCalculator
    interval_seconds: int = 10
    cooldown_seconds: int = 60
    _scheduler: AsyncIOScheduler = field(init=False, repr=False)
    _logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone=MOSCOW_TZ)
        self._logger = logging.getLogger(self.__class__.__name__)

    def start(self) -> None:
        self._scheduler.add_job(
            self._process_rules,
            trigger=IntervalTrigger(seconds=self.interval_seconds),
            max_instances=1,
            coalesce=True,
            misfire_grace_time=5,
        )
        self._scheduler.start()
        self._logger.info("Spread scheduler started (interval=%ss)", self.interval_seconds)

    async def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    async def _process_rules(self) -> None:
        if not self._is_within_alert_window():
            return

        rules = self.db.list_all_rules()
        if not rules:
            return

        symbols: set[str] = set()
        symbol_map: dict[str, str] = {}
        for rule in rules:
            symbols.update(self.parser.extract_symbols(rule.formula))
            symbol_map.update(self.parser.extract_symbol_map(rule.formula))
        if not symbols:
            return

        try:
            prices = await self.price_service.get_prices(symbols, symbol_map=symbol_map)
        except asyncio.CancelledError:
            # Can happen if scheduler/job is interrupted while awaiting thread-backed fetch.
            self._logger.warning("Price fetch was cancelled for current scheduler cycle")
            return
        except Exception as exc:
            self._logger.warning("Price fetch failed for scheduler cycle: %s", exc)
            return
        price_sources = self.price_service.get_last_sources()
        now_ts = int(time.time())

        for rule in rules:
            try:
                value = self.calculator.evaluate(rule.formula, prices)
            except Exception as exc:  # keep scheduler robust
                self._logger.warning("Failed to evaluate rule %s: %s", rule.id, exc)
                continue

            rule_symbols = self.parser.extract_symbols(rule.formula)
            source_details = ", ".join(
                f"{sym}:{price_sources.get(sym, 'unknown')}" for sym in sorted(rule_symbols)
            )
            self._logger.info(
                "Rule #%s source=%s symbols=%s value=%.6f",
                rule.id,
                self.price_service.provider,
                source_details,
                value,
            )

            if rule.last_alert_time is not None and now_ts - rule.last_alert_time < self.cooldown_seconds:
                continue

            if value > rule.upper_bound:
                await self._send_alert(rule.user_id, rule.id, rule.formula, value, "above upper")
                self.db.update_last_alert_time(rule.id, now_ts)
            elif value < rule.lower_bound:
                await self._send_alert(rule.user_id, rule.id, rule.formula, value, "below lower")
                self.db.update_last_alert_time(rule.id, now_ts)

    async def _send_alert(
        self,
        user_id: int,
        rule_id: int,
        formula: str,
        value: float,
        reason: str,
    ) -> None:
        text = (
            f"Alert for rule #{rule_id}\n"
            f"Formula: {formula}\n"
            f"Value: {value:.6f}\n"
            f"Reason: {reason}"
        )
        await self.bot.send_message(chat_id=user_id, text=text)

    @staticmethod
    def _is_within_alert_window() -> bool:
        now = datetime.now(tz=MOSCOW_TZ).time()
        start = datetime.strptime("09:00", "%H:%M").time()
        end = datetime.strptime("00:00", "%H:%M").time()
        # Window crossing midnight: [09:00, 24:00)
        return now >= start or now <= end

