from __future__ import annotations

import random
import time
from typing import Dict, Iterable


class PriceService:
    """
    Price source with simple in-memory cache.
    Currently returns mock prices; replace `_fetch_from_source` for live data.
    """

    def __init__(self, cache_ttl_seconds: int = 10) -> None:
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, int]] = {}

    def get_prices(self, symbols: Iterable[str]) -> Dict[str, float]:
        now = int(time.time())
        unique_symbols = set(symbols)
        result: Dict[str, float] = {}

        for symbol in unique_symbols:
            if symbol in self._cache:
                value, fetched_at = self._cache[symbol]
                if now - fetched_at < self._cache_ttl:
                    result[symbol] = value
                    continue

            price = self._fetch_from_source(symbol)
            self._cache[symbol] = (price, now)
            result[symbol] = price

        return result

    def _fetch_from_source(self, symbol: str) -> float:
        random.seed(symbol + str(int(time.time() / self._cache_ttl)))
        return round(random.uniform(10, 500), 5)

