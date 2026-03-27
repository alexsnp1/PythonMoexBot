from __future__ import annotations

import asyncio
import logging
import time
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
    human_mode: bool = False
    _scheduler: AsyncIOScheduler = field(init=False, repr=False)
    _logger: logging.Logger = field(init=False, repr=False)
    _job_id: str = field(init=False, repr=False, default="spread_scheduler_job")
    _next_human_pause_at_ts: float | None = field(init=False, repr=False, default=None)
    _pause_until_ts: float | None = field(init=False, repr=False, default=None)

    def __post_init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone=MOSCOW_TZ)
        self._logger = logging.getLogger(self.__class__.__name__)
        if self.human_mode and self.price_service.provider == "tradingview":
            self._next_human_pause_at_ts = time.time() + random.randint(30 * 60, 50 * 60)

    def start(self) -> None:
        self._schedule_next_run(delay_seconds=0)
        self._scheduler.start()
        self._logger.debug("Spread scheduler started (interval=%ss)", self.interval_seconds)

    async def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    def _schedule_next_run(self, delay_seconds: float) -> None:
        delay_seconds = max(0, float(delay_seconds))
        run_date = datetime.now(tz=MOSCOW_TZ) + timedelta(seconds=delay_seconds)
        self._scheduler.add_job(
            self._run_and_reschedule,
            trigger="date",
            run_date=run_date,
            id=self._job_id,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=5,
            replace_existing=True,
        )
        if self.human_mode and self.price_service.provider == "tradingview":
            self._logger.info("Next polling in %ss (humanized mode)", int(delay_seconds))

    def _compute_next_poll_interval_seconds(self) -> int:
        if self.price_service.provider != "tradingview":
            return self.interval_seconds
        if not self.human_mode:
            return self.interval_seconds
        return random.randint(15, 45)

    def _human_pause_should_run(self, now_ts: float) -> bool:
        return (
            self.human_mode
            and self.price_service.provider == "tradingview"
            and self._next_human_pause_at_ts is not None
            and now_ts >= self._next_human_pause_at_ts
        )

    async def _run_and_reschedule(self) -> None:
        now_ts = time.time()
        if self._pause_until_ts is not None and now_ts < self._pause_until_ts:
            remaining = self._pause_until_ts - now_ts
            self._schedule_next_run(delay_seconds=remaining)
            return

        await self._process_rules()

        now_ts = time.time()
        if self._human_pause_should_run(now_ts):
            pause_duration = random.randint(2 * 60, 5 * 60)
            self._pause_until_ts = now_ts + pause_duration
            self._next_human_pause_at_ts = self._pause_until_ts + random.randint(30 * 60, 50 * 60)
            self._logger.info(
                "Pausing TradingView fetch for %ss (human-like break)", pause_duration
            )
            self._schedule_next_run(delay_seconds=pause_duration)
            return

        self._schedule_next_run(delay_seconds=self._compute_next_poll_interval_seconds())

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
                self._logger.warning(
                    "Failed to evaluate rule #%s (id=%s) (user %s): %s",
                    rule.rule_number,
                    rule.id,
                    rule.user_id,
                    exc,
                )
                continue

            rule_symbols = self.parser.extract_symbols(rule.formula)
            source_details = ", ".join(
                f"{sym}:{price_sources.get(sym, 'unknown')}" for sym in sorted(rule_symbols)
            )
            self._logger.debug(
                "Rule #%s (user %s) source=%s symbols=%s value=%.6f",
                rule.rule_number,
                rule.user_id,
                self.price_service.provider,
                source_details,
                value,
            )

            if rule.last_alert_time is not None and now_ts - rule.last_alert_time < self.cooldown_seconds:
                continue

            if value > rule.upper_bound:
                await self._send_alert(
                    rule.user_id,
                    rule.rule_number,
                    rule.id,
                    rule.formula,
                    value,
                    "above upper",
                )
                self.db.update_last_alert_time(rule.id, now_ts)
            elif value < rule.lower_bound:
                await self._send_alert(
                    rule.user_id,
                    rule.rule_number,
                    rule.id,
                    rule.formula,
                    value,
                    "below lower",
                )
                self.db.update_last_alert_time(rule.id, now_ts)

    async def _send_alert(
        self,
        user_id: int,
        rule_number: int,
        rule_id: int,
        formula: str,
        value: float,
        reason: str,
    ) -> None:
        self._logger.info(
            "Alert triggered for rule #%s (id=%s) (reason=%s)",
            rule_number,
            rule_id,
            reason,
        )
        text = (
            f"Alert for rule #{rule_number}\n"
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

