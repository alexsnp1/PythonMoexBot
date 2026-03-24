from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import string
import time
import traceback
from dataclasses import dataclass
from typing import Dict, Iterable

import certifi

from price.moex_contract_resolver import MoexContractResolver
@dataclass(slots=True)
class PriceSnapshot:
    value: float
    fetched_at: int


class PriceService:
    """
    Price source with simple in-memory cache.
    Currently returns mock prices; replace `_fetch_from_source` for live data.
    """

    _EXCHANGE_REMAP = {
        "RUS": "MOEX",
    }
    _TV_WS_URL = "wss://data.tradingview.com/socket.io/websocket"
    _TV_MAX_RETRIES = 3
    _TV_TIMEOUT_SECONDS = 5

    def __init__(
        self,
        cache_ttl_seconds: int = 10,
        provider: str = "mock",
        tradingview_timeframe: str = "1",
        tradingview_candles: int = 1,
        moex_contract_config_path: str | None = None,
    ) -> None:
        self._cache_ttl = cache_ttl_seconds
        self._provider = provider
        self._tv_timeframe = tradingview_timeframe
        self._tv_candles = tradingview_candles
        self._cache: dict[str, PriceSnapshot] = {}
        self._last_sources: dict[str, str] = {}
        self._contract_resolver = MoexContractResolver(config_path=moex_contract_config_path)
        self._logger = logging.getLogger(self.__class__.__name__)

    async def get_prices(
        self,
        symbols: Iterable[str],
        symbol_map: Dict[str, str] | None = None,
    ) -> Dict[str, float]:
        now = int(time.time())
        unique_symbols = set(symbols)
        result: Dict[str, float] = {}
        stale_symbols: list[str] = []
        self._last_sources = {}

        for symbol in unique_symbols:
            if symbol in self._cache:
                snapshot = self._cache[symbol]
                if now - snapshot.fetched_at < self._cache_ttl:
                    result[symbol] = snapshot.value
                    self._last_sources[symbol] = "cache"
                    continue
            stale_symbols.append(symbol)

        if stale_symbols:
            if self._provider == "tradingview":
                fetched = await self._fetch_from_tradingview(stale_symbols, symbol_map or {})
            else:
                fetched = {}
                for symbol in stale_symbols:
                    fetched[symbol] = self._fetch_mock_price(symbol)
                    self._last_sources[symbol] = "mock"
            for symbol, price in fetched.items():
                self._cache[symbol] = PriceSnapshot(value=price, fetched_at=now)
                result[symbol] = price

        return result

    @property
    def provider(self) -> str:
        return self._provider

    def get_last_sources(self) -> Dict[str, str]:
        return dict(self._last_sources)

    def _fetch_mock_price(self, symbol: str) -> float:
        random.seed(symbol + str(int(time.time() / self._cache_ttl)))
        return round(random.uniform(10, 500), 5)

    async def _fetch_from_tradingview(
        self,
        normalized_symbols: list[str],
        symbol_map: Dict[str, str],
    ) -> Dict[str, float]:
        tasks = []
        symbol_order: list[str] = []
        for normalized in normalized_symbols:
            raw_symbol = symbol_map.get(normalized, normalized)
            resolved_symbol = self._contract_resolver.resolve_symbol(raw_symbol)
            tv_symbol = self._to_tradingview_symbol(resolved_symbol)
            self._logger.info(
                "TradingView symbol mapping: %s -> %s -> %s -> %s",
                normalized,
                raw_symbol,
                resolved_symbol,
                tv_symbol,
            )
            symbol_order.append(normalized)
            tasks.append(
                asyncio.to_thread(
                    self._fetch_single_tradingview_price_sync,
                    tv_symbol,
                )
            )
        prices = await asyncio.gather(*tasks, return_exceptions=True)

        result: Dict[str, float] = {}
        for normalized, value in zip(symbol_order, prices):
            if isinstance(value, Exception):
                self._last_sources[normalized] = "mock_fallback"
                self._logger.warning(
                    "TradingView fetch failed for %s: fallback to mock (%s)",
                    normalized,
                    value,
                )
                result[normalized] = self._fetch_mock_price(normalized)
            else:
                self._last_sources[normalized] = "tradingview"
                self._logger.info("TradingView fetch success for %s: %s", normalized, value)
                result[normalized] = value
        return result

    def _fetch_single_tradingview_price_sync(self, tv_symbol: str) -> float:
        try:
            from websocket import create_connection
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "websocket-client is not installed. "
                "Install dependencies with: pip install -r requirements.txt"
            ) from exc

        last_error: Exception | None = None
        for attempt in range(1, self._TV_MAX_RETRIES + 1):
            ws = None
            try:
                self._logger.info(
                    "TradingView connection open for %s (attempt %s/%s)",
                    tv_symbol,
                    attempt,
                    self._TV_MAX_RETRIES,
                )
                ws = create_connection(
                    self._TV_WS_URL,
                    timeout=self._TV_TIMEOUT_SECONDS,
                    sslopt={"cert_reqs": 2, "ca_certs": certifi.where()},
                )
                self._send_tradingview_subscription(ws=ws, tv_symbol=tv_symbol)
                close_price = self._receive_tradingview_price(ws=ws, tv_symbol=tv_symbol)
                return close_price
            except Exception as exc:
                last_error = exc
                self._logger.warning(
                    "TradingView attempt failed for %s (%s/%s): %s\n%s",
                    tv_symbol,
                    attempt,
                    self._TV_MAX_RETRIES,
                    exc,
                    traceback.format_exc(),
                )
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass

        if last_error is None:
            raise RuntimeError(f"TradingView fetch failed for {tv_symbol} with unknown error")
        raise RuntimeError(f"TradingView fetch failed for {tv_symbol}: {last_error}") from last_error

    def _send_tradingview_subscription(self, ws, tv_symbol: str) -> None:
        quote_session = self._generate_session(prefix="qs_")
        chart_session = self._generate_session(prefix="cs_")
        symbol_string = f'={{"symbol":"{tv_symbol}","adjustment":"splits"}}'

        messages = [
            ("set_auth_token", ["unauthorized_user_token"]),
            ("chart_create_session", [chart_session, ""]),
            ("quote_create_session", [quote_session]),
            (
                "quote_set_fields",
                [
                    quote_session,
                    "ch",
                    "chp",
                    "current_session",
                    "description",
                    "local_description",
                    "language",
                    "exchange",
                    "fractional",
                    "is_tradable",
                    "lp",
                    "lp_time",
                    "minmov",
                    "minmove2",
                    "original_name",
                    "pricescale",
                    "pro_name",
                    "short_name",
                    "type",
                    "update_mode",
                    "volume",
                    "currency_code",
                    "rchp",
                    "rtc",
                ],
            ),
            ("quote_add_symbols", [quote_session, tv_symbol, {"flags": ["force_permission"]}]),
            ("resolve_symbol", [chart_session, f"symbol_{self._tv_timeframe}", symbol_string]),
            (
                "create_series",
                [
                    chart_session,
                    f"s{self._tv_timeframe}",
                    f"s{self._tv_timeframe}",
                    f"symbol_{self._tv_timeframe}",
                    self._tv_timeframe,
                    self._tv_candles,
                ],
            ),
        ]

        for func, params in messages:
            ws.send(self._tv_create_message(func=func, param_list=params))
        self._logger.info("TradingView subscription sent for %s", tv_symbol)

    def _receive_tradingview_price(self, ws, tv_symbol: str) -> float:
        deadline = time.time() + self._TV_TIMEOUT_SECONDS
        while time.time() < deadline:
            raw = ws.recv()
            self._logger.info("TradingView message received for %s: %s", tv_symbol, raw[:500])
            data_chunks = re.split(r"~m~\d+~m~", raw)

            for chunk in data_chunks:
                chunk = chunk.strip()
                if not chunk:
                    continue
                try:
                    payload = json.loads(chunk)
                except json.JSONDecodeError:
                    continue

                if payload.get("m") != "timescale_update":
                    continue

                series_key = f"s{self._tv_timeframe}"
                series = payload.get("p", [{}, {}])[1].get(series_key, {}).get("s", [])
                if not series:
                    continue

                latest_candle = series[-1]
                try:
                    close_price = self._extract_close_price(latest_candle)
                    return close_price
                except Exception as exc:
                    self._logger.warning(
                        "TradingView candle parse failed for %s: %s | candle=%s",
                        tv_symbol,
                        exc,
                        str(latest_candle)[:500],
                    )
                    continue

        self._logger.warning("NO DATA FROM TRADINGVIEW for %s", tv_symbol)
        raise TimeoutError(f"No data from TradingView for {tv_symbol} in {self._TV_TIMEOUT_SECONDS}s")

    @staticmethod
    def _extract_close_price(latest_candle) -> float:
        # TradingView may return candles as list or dict with numeric string keys.
        if isinstance(latest_candle, list):
            return float(latest_candle[4])
        if isinstance(latest_candle, dict):
            if 4 in latest_candle:
                return float(latest_candle[4])
            if "4" in latest_candle:
                return float(latest_candle["4"])
            if "v" in latest_candle and isinstance(latest_candle["v"], list):
                return float(latest_candle["v"][4])
            if "close" in latest_candle:
                return float(latest_candle["close"])
        raise KeyError("close price key is missing in TradingView candle payload")

    @staticmethod
    def _generate_session(prefix: str) -> str:
        return prefix + "".join(random.choice(string.ascii_lowercase) for _ in range(12))

    @staticmethod
    def _tv_create_message(func: str, param_list: list) -> str:
        message = json.dumps({"m": func, "p": param_list}, separators=(",", ":"))
        return f"~m~{len(message)}~m~{message}"

    def _to_tradingview_symbol(self, symbol: str) -> str:
        if ":" not in symbol:
            return symbol
        exchange, ticker = symbol.split(":", 1)
        return f"{self._EXCHANGE_REMAP.get(exchange, exchange)}:{ticker}"

