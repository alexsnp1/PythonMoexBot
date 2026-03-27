from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import re
import string
import threading
import time
import traceback
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable

import certifi

from price.moex_contract_resolver import MoexContractResolver


@dataclass(slots=True)
class PriceSnapshot:
    value: float
    fetched_at: int


class PriceService:
    """
    Price source with simple in-memory cache.
    mock provider returns synthetic prices; tradingview uses one shared WebSocket.
    """

    _EXCHANGE_REMAP = {
        "RUS": "MOEX",
    }
    _TV_WS_URL = "wss://data.tradingview.com/socket.io/websocket"
    _TV_MAX_RETRIES = 3
    _TV_TIMEOUT_SECONDS = 5
    _TV_TOKEN_EXPIRY_WARN_SECONDS = 600
    _TV_RAPID_CLOSE_AUTH_SECONDS = 3.0
    _TV_AUTH_FAILURE_NOTIFY_THRESHOLD = 2
    _TV_STABLE_CONNECTION_RESET_SECONDS = 10.0
    _TV_TOKEN_EXPIRY_THROTTLE_SECONDS = 300
    _TV_EXPIRY_NOTIFY_TEXT = (
        "⚠️ TradingView token expired or invalid.\nPlease update it using /set_token"
    )

    def __init__(
        self,
        cache_ttl_seconds: int = 10,
        provider: str = "mock",
        tradingview_timeframe: str = "1",
        tradingview_candles: int = 1,
        moex_contract_config_path: str | None = None,
        tradingview_auth_token: str | None = None,
        tradingview_human_mode: bool = False,
        tradingview_token_expires_at: int | None = None,
        token_expiry_telegram_notify: Callable[[str], None] | None = None,
    ) -> None:
        self._cache_ttl = cache_ttl_seconds
        self._provider = provider
        self._tv_timeframe = tradingview_timeframe
        self._tv_candles = tradingview_candles
        self._moex_contract_config_path = moex_contract_config_path
        self._cache: dict[str, PriceSnapshot] = {}
        self._last_sources: dict[str, str] = {}
        self._contract_resolver = MoexContractResolver(config_path=moex_contract_config_path)
        self._logger = logging.getLogger(self.__class__.__name__)
        raw_auth = (tradingview_auth_token or "").strip()
        self._tv_auth_token = raw_auth
        self._tv_human_mode = tradingview_human_mode
        self._tradingview_token_expires_at = tradingview_token_expires_at
        self._token_expiry_telegram_notify = token_expiry_telegram_notify
        self._token_fingerprint = self._token_fingerprint_for(raw_auth)
        self._last_token_expiry_notification_ts: float | None = None
        self._tv_had_auth_failure = False
        self._tv_auth_failure_count: int = 0
        self._tv_reconnect_attempts: int = 0
        self._tv_connect_opened_at: float | None = None
        self._tv_ever_had_successful_connection: bool = False

        self._tv_lock = threading.RLock()
        self._tv_ws: Any = None
        self._tv_quote_session: str | None = None
        self._tv_reader_stop = threading.Event()
        self._tv_reader_thread: threading.Thread | None = None
        self._tv_prices: dict[str, float] = {}
        self._tv_subscribed: set[str] = set()
        self._tv_symbol_to_normalized: dict[str, str] = {}
        self._tv_auth_mode_logged = False
        self._tv_subscriptions_logged = False
        self._tv_last_message_at: float | None = None
        self._tv_stale_warned_for_current_staleness: bool = False

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
                fetched = await asyncio.to_thread(
                    self._fetch_tradingview_batch_sync, stale_symbols, symbol_map or {}
                )
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

    @staticmethod
    def _mask_token(token: str) -> str:
        t = token.strip()
        if len(t) <= 6:
            return "***"
        return f"{t[:3]}***{t[-3:]}"

    @staticmethod
    def mask_token(token: str) -> str:
        t = (token or "").strip()
        if len(t) <= 10:
            return "***"
        return t[:6] + "..." + t[-4:]

    @staticmethod
    def _token_fingerprint_for(token: str) -> str:
        return hashlib.sha256(token.strip().encode()).hexdigest()[:16]

    @staticmethod
    def parse_tradingview_token_expires_at(raw: str | None) -> int | None:
        """
        Unix seconds since epoch, or ISO 8601 datetime string (UTC if Z suffix).
        """
        if raw is None:
            return None
        s = str(raw).strip()
        if not s:
            return None
        if s.isdigit():
            return int(s)
        try:
            iso = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except (ValueError, OSError, TypeError, OverflowError):
            return None

    def set_tradingview_token(
        self,
        token: str | None,
        expires_at: int | None = None,
    ) -> None:
        """Update token at runtime; resets expiry notification state when token changes."""
        new_t = (token or "").strip()
        with self._tv_lock:
            new_fp = self._token_fingerprint_for(new_t)
            if new_fp != self._token_fingerprint:
                self._tv_had_auth_failure = False
                self._tv_auth_failure_count = 0
                self._last_token_expiry_notification_ts = None
            else:
                # Even if the token string is the same, a manual /set_token should reset state.
                self._tv_had_auth_failure = False
                self._tv_auth_failure_count = 0
                self._last_token_expiry_notification_ts = None
            self._tv_auth_token = new_t
            self._token_fingerprint = new_fp
            if expires_at is not None:
                self._tradingview_token_expires_at = expires_at

    def _sync_token_fingerprint(self) -> None:
        fp = self._token_fingerprint_for(self._tv_auth_token)
        if fp != self._token_fingerprint:
            self._token_fingerprint = fp
            self._tv_had_auth_failure = False
            self._tv_auth_failure_count = 0
            self._last_token_expiry_notification_ts = None

    def is_token_valid(self, token: str | None = None, test_symbol: str = "TVC:SILVER") -> bool:
        """
        Validate a token by attempting to fetch a single TradingView price.
        Does not mutate this instance's websocket/subscription state (uses a temporary PriceService).
        """
        t = (token if token is not None else self._tv_auth_token).strip()
        if not t:
            return False
        tmp = PriceService(
            cache_ttl_seconds=0,
            provider="tradingview",
            tradingview_timeframe=self._tv_timeframe,
            tradingview_candles=self._tv_candles,
            moex_contract_config_path=self._moex_contract_config_path,
            tradingview_auth_token=t,
            tradingview_human_mode=False,
            tradingview_token_expires_at=None,
            token_expiry_telegram_notify=None,
        )
        result = tmp._fetch_tradingview_batch_sync(["__probe__"], {"__probe__": test_symbol})
        sources = tmp.get_last_sources()
        return "__probe__" in result and sources.get("__probe__") == "tradingview_real"

    def _maybe_notify_token_expires_soon_by_timestamp(self) -> None:
        if not self._tv_auth_token or self._tradingview_token_expires_at is None:
            return
        remaining = float(self._tradingview_token_expires_at) - time.time()
        if 0 < remaining < self._TV_TOKEN_EXPIRY_WARN_SECONDS:
            self._notify_token_expiry_once(self._TV_EXPIRY_NOTIFY_TEXT)

    def _notify_token_expiry_once(self, text: str) -> None:
        with self._tv_lock:
            now = time.time()
            if (
                self._last_token_expiry_notification_ts is not None
                and now - self._last_token_expiry_notification_ts < self._TV_TOKEN_EXPIRY_THROTTLE_SECONDS
            ):
                self._logger.info("Token expiry notification skipped (rate limit)")
                return
            notify = self._token_expiry_telegram_notify
            if notify is None:
                return
            self._last_token_expiry_notification_ts = now
        try:
            notify(text)
            self._logger.info("Token expiry notification sent")
        except Exception as exc:
            self._logger.warning("Token expiry Telegram notify failed: %s", exc)
            with self._tv_lock:
                # Allow a retry soon if sending failed.
                self._last_token_expiry_notification_ts = None

    def _reset_token_notification_after_auth_recovery(self) -> None:
        with self._tv_lock:
            if not self._tv_had_auth_failure:
                return
            self._tv_had_auth_failure = False
            self._tv_auth_failure_count = 0

    @staticmethod
    def _tv_is_auth_related_text(text: str) -> bool:
        t = text.lower()
        needles = (
            "auth",
            "unauthor",
            "token",
            "session",
            "login",
            "expired",
            "invalid",
            "credential",
            "permission",
            "forbidden",
        )
        return any(n in t for n in needles)

    def _tv_payload_suggests_auth_failure(self, payload: dict[str, Any]) -> bool:
        try:
            blob = json.dumps(payload, default=str).lower()
        except Exception:
            blob = str(payload).lower()
        return self._tv_is_auth_related_text(blob)

    def _reset_auth_failure_count(self) -> None:
        with self._tv_lock:
            self._tv_auth_failure_count = 0
            self._last_token_expiry_notification_ts = None

    def _record_auth_failure_signal(self, reason: str) -> None:
        if not self._tv_auth_token:
            return
        with self._tv_lock:
            self._tv_auth_failure_count += 1
            count = self._tv_auth_failure_count
            self._tv_had_auth_failure = True
        self._logger.warning("Auth failure detected (count=%s): %s", count, reason)
        if count >= self._TV_AUTH_FAILURE_NOTIFY_THRESHOLD:
            self._logger.debug("Auth failure count reached notification threshold: %s", count)
        # Notify even on repeated failure cycles; throttling prevents spam.
        self._notify_token_expiry_once(self._TV_EXPIRY_NOTIFY_TEXT)

    def _maybe_reset_auth_failure_on_stable_connection(self) -> None:
        if not self._tv_auth_token:
            return
        with self._tv_lock:
            opened = self._tv_connect_opened_at
        if opened is None or time.time() - opened < self._TV_STABLE_CONNECTION_RESET_SECONDS:
            return
        self._reset_auth_failure_count()

    def _maybe_rapid_close_auth_failure(self) -> None:
        if not self._tv_auth_token:
            return
        with self._tv_lock:
            opened = self._tv_connect_opened_at
        if opened is None:
            return
        if time.time() - opened > self._TV_RAPID_CLOSE_AUTH_SECONDS:
            return
        # Avoid false positives: rapid disconnects alone are common and shouldn't
        # immediately trigger token-expiry notifications.
        # Only count rapid close if we already observed at least one auth-related failure.
        with self._tv_lock:
            prior_auth = self._tv_auth_failure_count >= 1
        if prior_auth:
            self._record_auth_failure_signal("websocket closed soon after connect")
        else:
            # Rapid close alone is not counted as auth-failure, but still informs users
            # with throttling if the token is likely broken/expired.
            self._notify_token_expiry_once(self._TV_EXPIRY_NOTIFY_TEXT)

    @staticmethod
    def _tv_reconnect_backoff_base_seconds(attempt_number: int) -> float:
        """attempt_number is 1-based reconnect attempt (first reconnect = 1)."""
        return float(min(5.0 * (2.0 ** (attempt_number - 1)), 30.0))

    def _log_tv_auth_mode_once(self) -> None:
        if self._tv_auth_mode_logged:
            return
        self._tv_auth_mode_logged = True
        if self._tv_auth_token:
            self._logger.info("TradingView auth mode: AUTHENTICATED")
            self._logger.debug("TradingView token (masked): %s", self._mask_token(self._tv_auth_token))
        else:
            self._logger.info("TradingView auth mode: UNAUTHORIZED (delayed data)")

    def _fetch_tradingview_batch_sync(
        self,
        normalized_symbols: list[str],
        symbol_map: Dict[str, str],
    ) -> Dict[str, float]:
        self._sync_token_fingerprint()
        self._maybe_notify_token_expires_soon_by_timestamp()
        self._log_tv_auth_mode_once()
        symbol_order: list[str] = []
        tv_order: list[str] = []
        tv_to_norm: dict[str, str] = {}
        for normalized in normalized_symbols:
            raw_symbol = symbol_map.get(normalized, normalized)
            resolved_symbol = self._contract_resolver.resolve_symbol(raw_symbol)
            tv_symbol = self._to_tradingview_symbol(resolved_symbol)
            self._logger.debug(
                "TradingView symbol mapping: %s -> %s -> %s -> %s",
                normalized,
                raw_symbol,
                resolved_symbol,
                tv_symbol,
            )
            symbol_order.append(normalized)
            tv_order.append(tv_symbol)
            tv_to_norm[tv_symbol] = normalized

        unique_tv = list(dict.fromkeys(tv_order))

        if not self._tv_ensure_connection_with_backoff():
            result: dict[str, float] = {}
            for normalized in symbol_order:
                self._logger.warning("fallback to mock for %s", normalized)
                self._last_sources[normalized] = "mock_fallback"
                result[normalized] = self._fetch_mock_price(normalized)
            return result

        self._tv_subscribe_symbols(unique_tv, tv_to_norm)
        deadline = time.time() + max(
            self._TV_TIMEOUT_SECONDS,
            self._TV_TIMEOUT_SECONDS * len(unique_tv) / 2,
        )
        result = {}
        while time.time() < deadline:
            missing: list[str] = []
            with self._tv_lock:
                for normalized, tv_symbol in zip(symbol_order, tv_order):
                    if normalized in result:
                        continue
                    price = self._tv_prices.get(tv_symbol)
                    if price is not None:
                        result[normalized] = price
                    else:
                        missing.append(normalized)
            if not missing:
                break
            time.sleep(0.05)

        for normalized, tv_symbol in zip(symbol_order, tv_order):
            if normalized in result:
                self._last_sources[normalized] = "tradingview_real"
                continue
            self._logger.warning("fallback to mock for %s", normalized)
            self._last_sources[normalized] = "mock_fallback"
            result[normalized] = self._fetch_mock_price(normalized)

        if self._tv_auth_token and any(
            self._last_sources.get(n) == "tradingview_real" for n in symbol_order
        ):
            self._reset_auth_failure_count()

        if self._tv_auth_token and self._tv_had_auth_failure:
            if any(self._last_sources.get(n) == "tradingview_real" for n in symbol_order):
                self._reset_token_notification_after_auth_recovery()

        return result

    def _tv_ensure_connection_with_backoff(self) -> bool:
        with self._tv_lock:
            if self._tv_ws is not None and self._tv_is_ws_alive_unsafe():
                return True

        for attempt in (1, 2, 3):
            if attempt == 2:
                time.sleep(2)
            elif attempt == 3:
                time.sleep(5)
            connect_ok = False
            try:
                self._tv_connect_and_start_reader()
                with self._tv_lock:
                    connect_ok = self._tv_ws is not None and self._tv_is_ws_alive_unsafe()
            except Exception as exc:
                self._logger.warning(
                    "TradingView connect attempt %s/%s failed: %s\n%s",
                    attempt,
                    self._TV_MAX_RETRIES,
                    exc,
                    traceback.format_exc(),
                )
                if self._tv_auth_token and self._tv_is_auth_related_text(str(exc)):
                    self._record_auth_failure_signal(f"connect failed: {exc}")
                with self._tv_lock:
                    self._tv_close_internal_unlocked()
                if "invalid_parameters" in str(exc):
                    return False
                continue
            if connect_ok:
                return True
            with self._tv_lock:
                self._tv_close_internal_unlocked()
        return False

    def _sleep_reconnect_jitter(self, delay: float) -> None:
        """
        Pause before opening a new WebSocket after a prior successful connection.
        Runs in the asyncio.to_thread worker; time.sleep does not block the event loop.
        """
        time.sleep(delay)

    def _tv_is_ws_alive_unsafe(self) -> bool:
        ws = self._tv_ws
        if ws is None:
            return False
        try:
            connected = getattr(ws, "connected", None)
            if connected is not None:
                return bool(connected)
            sock = getattr(ws, "sock", None)
            return sock is not None
        except Exception:
            return False

    def _tv_connect_and_start_reader(self) -> None:
        try:
            from websocket import create_connection
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "websocket-client is not installed. "
                "Install dependencies with: pip install -r requirements.txt"
            ) from exc

        token = self._tv_auth_token if self._tv_auth_token else "unauthorized_user_token"
        reconnect = False
        with self._tv_lock:
            reconnect = self._tv_ever_had_successful_connection
            self._tv_close_internal_unlocked()
        if reconnect:
            with self._tv_lock:
                self._tv_reconnect_attempts += 1
                att = self._tv_reconnect_attempts
            if att > 10:
                delay = random.uniform(60, 120)
                self._logger.warning(
                    "Too many reconnect attempts, backing off (attempt=%s). Sleeping %.2fs",
                    att,
                    delay,
                )
                self._sleep_reconnect_jitter(delay)
            else:
                base = self._tv_reconnect_backoff_base_seconds(att)
                jitter = random.uniform(0, 3)
                delay = base + jitter
                self._logger.info("Reconnect attempt #%s, delay %.2fs", att, delay)
                self._sleep_reconnect_jitter(delay)
        with self._tv_lock:
            self._logger.info("TradingView WebSocket opening (shared connection)")
            ws = create_connection(
                self._TV_WS_URL,
                timeout=self._TV_TIMEOUT_SECONDS,
                sslopt={"cert_reqs": 2, "ca_certs": certifi.where()},
            )
            # Allow recv() to periodically time out so we can run heartbeat checks
            # without forcing a reconnect.
            try:
                ws.settimeout(1.0)
            except Exception:
                # If settimeout isn't supported by the underlying websocket implementation,
                # heartbeat checks will simply be less responsive.
                pass
            quote_session = self._generate_session(prefix="qs_")
            self._tv_ws = ws
            self._tv_quote_session = quote_session
            self._tv_subscribed.clear()
            self._tv_prices.clear()
            self._tv_symbol_to_normalized.clear()
            self._tv_subscriptions_logged = False
            self._tv_last_message_at = time.time()
            self._tv_stale_warned_for_current_staleness = False
            self._tv_connect_opened_at = time.time()

            self._tv_send_unlocked(ws, "set_auth_token", [token])
            self._tv_send_unlocked(ws, "quote_create_session", [quote_session])
            self._tv_send_unlocked(
                ws,
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
            )
            self._logger.info("TradingView WebSocket connected")
            self._tv_ever_had_successful_connection = True
            self._tv_reconnect_attempts = 0

        self._ensure_tv_reader_thread()

    def _tv_close_internal_unlocked(self) -> None:
        if self._tv_ws is not None:
            try:
                self._tv_ws.close()
            except Exception:
                pass
            self._logger.info("TradingView WebSocket closed")
        self._tv_ws = None
        self._tv_quote_session = None

    def _tv_send_unlocked(self, ws: Any, func: str, param_list: list) -> None:
        ws.send(self._tv_create_message(func=func, param_list=param_list))

    def _tv_subscribe_symbols(self, tv_symbols: list[str], tv_to_norm: dict[str, str]) -> None:
        new_syms: list[str] = []
        with self._tv_lock:
            ws = self._tv_ws
            qs = self._tv_quote_session
            if ws is None or qs is None:
                return
            for tv in tv_symbols:
                self._tv_symbol_to_normalized[tv] = tv_to_norm.get(tv, tv)
                if tv in self._tv_subscribed:
                    continue
                if self._tv_human_mode:
                    # Micro-pause between symbol bursts to avoid perfectly simultaneous requests.
                    time.sleep(random.uniform(0.1, 0.3))
                chart_session = self._generate_session(prefix="cs_")
                symbol_string = f'={{"symbol":"{tv}","adjustment":"splits"}}'
                self._tv_send_unlocked(ws, "chart_create_session", [chart_session, ""])
                self._tv_send_unlocked(ws, "quote_add_symbols", [qs, tv])
                self._tv_send_unlocked(
                    ws,
                    "resolve_symbol",
                    [chart_session, f"symbol_{self._tv_timeframe}", symbol_string],
                )
                self._tv_send_unlocked(
                    ws,
                    "create_series",
                    [
                        chart_session,
                        f"s{self._tv_timeframe}",
                        f"s{self._tv_timeframe}",
                        f"symbol_{self._tv_timeframe}",
                        self._tv_timeframe,
                        self._tv_candles,
                    ],
                )
                self._tv_subscribed.add(tv)
                new_syms.append(tv)

        if new_syms:
            self._logger.info("TradingView new subscriptions: %s", new_syms)
        if self._tv_subscribed and not self._tv_subscriptions_logged:
            self._tv_subscriptions_logged = True
            with self._tv_lock:
                active = sorted(self._tv_subscribed)
            self._logger.info("TradingView subscription list: %s", active)

    def _ensure_tv_reader_thread(self) -> None:
        if self._tv_reader_thread is not None and self._tv_reader_thread.is_alive():
            return

        def reader_loop() -> None:
            while not self._tv_reader_stop.is_set():
                ws_local = None
                with self._tv_lock:
                    ws_local = self._tv_ws
                if ws_local is None:
                    time.sleep(0.15)
                    continue
                try:
                    raw = ws_local.recv()
                    with self._tv_lock:
                        self._tv_last_message_at = time.time()
                        self._tv_stale_warned_for_current_staleness = False
                    self._maybe_reset_auth_failure_on_stable_connection()
                except Exception as exc:
                    if isinstance(exc, socket.timeout) or exc.__class__.__name__ == "WebSocketTimeoutException":
                        self._tv_check_staleness_heartbeat()
                        continue
                    self._logger.warning("TradingView WebSocket recv ended: %s", exc)
                    if self._tv_is_auth_related_text(str(exc)):
                        self._record_auth_failure_signal(f"recv error: {exc}")
                    else:
                        self._maybe_rapid_close_auth_failure()
                    with self._tv_lock:
                        if self._tv_ws is ws_local:
                            self._tv_close_internal_unlocked()
                            self._tv_subscribed.clear()
                            self._tv_symbol_to_normalized.clear()
                    continue
                try:
                    self._process_tv_raw(raw)
                except Exception:
                    self._logger.debug("TradingView message handler error", exc_info=True)

        self._tv_reader_thread = threading.Thread(
            target=reader_loop, daemon=True, name="tradingview-ws-reader"
        )
        self._tv_reader_thread.start()

    def _tv_check_staleness_heartbeat(self) -> None:
        """
        Heartbeat check: warn if we haven't received any TradingView messages for >60s.
        We intentionally do NOT reconnect here to avoid ban-spam; reconnect only when the socket closes.
        """
        with self._tv_lock:
            last = self._tv_last_message_at
            if last is None:
                return
            now = time.time()
            if now - last <= 60:
                return
            if self._tv_stale_warned_for_current_staleness:
                return
            self._tv_stale_warned_for_current_staleness = True
        self._logger.warning("No TradingView data for 60s (connection might be stale)")

    def _process_tv_raw(self, raw: str) -> None:
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
                self._logger.warning("TradingView critical_error: %s", payload)
                if self._tv_payload_suggests_auth_failure(payload):
                    self._record_auth_failure_signal("critical_error")
                with self._tv_lock:
                    if self._tv_ws is not None:
                        self._tv_close_internal_unlocked()
                        self._tv_subscribed.clear()
                        self._tv_symbol_to_normalized.clear()
                continue
            sym, price = self._parse_qsd_symbol_and_price(payload)
            if sym and price is not None:
                with self._tv_lock:
                    self._tv_prices[sym] = price
                    display = self._tv_symbol_to_normalized.get(sym, sym)
                if self._tv_auth_token:
                    self._reset_auth_failure_count()
                self._logger.debug(
                    "price update: %s = %s (source=tradingview)",
                    display,
                    price,
                )
                continue
            fallback = self._select_realtime_price(payload)
            if fallback is not None:
                with self._tv_lock:
                    subs = list(self._tv_subscribed)
                    if len(subs) == 1:
                        only = subs[0]
                        self._tv_prices[only] = fallback
                        display = self._tv_symbol_to_normalized.get(only, only)
                    else:
                        display = None
                if display is not None:
                    if self._tv_auth_token:
                        self._reset_auth_failure_count()
                    self._logger.debug(
                        "price update: %s = %s (source=tradingview)",
                        display,
                        fallback,
                    )

    def _parse_qsd_symbol_and_price(self, payload: dict[str, Any]) -> tuple[str | None, float | None]:
        if payload.get("m") != "qsd":
            return None, None
        p = payload.get("p")
        if not isinstance(p, list) or not p:
            return None, None
        block: dict[str, Any] | None = None
        if len(p) >= 2 and isinstance(p[1], dict):
            block = p[1]
        elif isinstance(p[0], dict):
            block = p[0]
        if block is None:
            return None, None
        sym_raw = block.get("n") or block.get("nl") or block.get("name")
        sym = str(sym_raw) if sym_raw else None
        v = block.get("v")
        if not isinstance(v, dict):
            return sym, None
        price = self._price_from_quote_v(v)
        return sym, price

    @staticmethod
    def _price_from_quote_v(v: dict[str, Any]) -> float | None:
        last_price = PriceService._find_first_numeric_by_keys(v, {"last", "lp", "last_price"})
        if last_price is not None:
            return last_price
        bid = PriceService._find_first_numeric_by_keys(v, {"bid", "bp", "bid_price"})
        ask = PriceService._find_first_numeric_by_keys(v, {"ask", "ap", "ask_price"})
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0
        if bid is not None:
            return bid
        if ask is not None:
            return ask
        return None

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
