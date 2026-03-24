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
from typing import Any, Dict, Iterable

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
        raw_order: list[str] = []
        resolved_order: list[str] = []
        tv_order: list[str] = []
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
            raw_order.append(raw_symbol)
            resolved_order.append(resolved_symbol)
            tv_order.append(tv_symbol)
            tasks.append(
                asyncio.to_thread(
                    self._fetch_single_tradingview_price_sync,
                    tv_symbol,
                )
            )
        prices = await asyncio.gather(*tasks, return_exceptions=True)

        result: Dict[str, float] = {}
        for normalized, raw_symbol, resolved_symbol, tv_symbol, value in zip(
            symbol_order, raw_order, resolved_order, tv_order, prices
        ):
            if isinstance(value, Exception):
                self._last_sources[normalized] = "mock_fallback"
                self._logger.warning(
                    "TradingView fetch failed for %s: fallback to mock (%s)",
                    normalized,
                    value,
                )
                result[normalized] = self._fetch_mock_price(normalized)
            else:
                self._last_sources[normalized] = "tradingview_real"
                self._logger.info("TradingView fetch success for %s: %s", normalized, value)
                self._logger.info(
                    "%s -> %s -> %s -> %s -> %s",
                    raw_symbol,
                    normalized,
                    resolved_symbol.split(":", 1)[-1] if ":" in resolved_symbol else resolved_symbol,
                    tv_symbol,
                    value,
                )
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
                if "invalid_parameters" in str(exc):
                    break
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
                    "bid",
                    "ask",
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
            # Keep quote_add_symbols minimal to avoid invalid_parameters for many symbols.
            ("quote_add_symbols", [quote_session, tv_symbol]),
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
            try:
                raw = ws.recv()
            except Exception as exc:
                # Socket can briefly time out between messages; keep waiting until deadline.
                self._logger.debug("TradingView recv transient timeout/error for %s: %s", tv_symbol, exc)
                continue
            self._logger.info("TradingView message received for %s", tv_symbol)
            self._logger.debug("TradingView raw response for %s: %s", tv_symbol, raw)
            data_chunks = re.split(r"~m~\d+~m~", raw)

            for chunk in data_chunks:
                chunk = chunk.strip()
                if not chunk:
                    continue
                try:
                    payload = json.loads(chunk)
                except json.JSONDecodeError:
                    continue

                if payload.get("m") == "critical_error":
                    self._logger.warning("TradingView critical_error for %s: %s", tv_symbol, payload)
                    params = payload.get("p", [])
                    if len(params) >= 3 and params[2] == "quote_add_symbols":
                        raise RuntimeError(f"TradingView invalid_parameters for quote_add_symbols: {payload}")

                self._logger.debug("TradingView parsed payload for %s: %s", tv_symbol, payload)
                selected = self._select_realtime_price(payload)
                if selected is not None:
                    return selected

        self._logger.warning("NO DATA FROM TRADINGVIEW for %s", tv_symbol)
        raise TimeoutError(f"No data from TradingView for {tv_symbol} in {self._TV_TIMEOUT_SECONDS}s")

    @staticmethod
    def _select_realtime_price(payload: Dict[str, Any]) -> float | None:
        last_price = PriceService._find_first_numeric_by_keys(payload, {"last", "lp", "last_price"})
        if last_price is not None:
            return last_price

        bid = PriceService._find_first_numeric_by_keys(payload, {"bid", "bp", "bid_price"})
        ask = PriceService._find_first_numeric_by_keys(payload, {"ask", "ap", "ask_price"})
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0
        if bid is not None:
            return bid
        if ask is not None:
            return ask
        return None

    @staticmethod
    def _find_first_numeric_by_keys(data: Any, keys: set[str]) -> float | None:
        stack: list[Any] = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key, value in node.items():
                    if str(key).lower() in keys:
                        parsed = PriceService._coerce_float(value)
                        if parsed is not None:
                            return parsed
                    stack.append(value)
            elif isinstance(node, list):
                stack.extend(node)
        return None

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

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

