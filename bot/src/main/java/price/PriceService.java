package price;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class PriceService {
    // Cache lifetime: 10 seconds.
    private static final long CACHE_LIFETIME_MILLIS = 10_000;

    private final TradingViewClient tradingViewClient;

    private final Map<String, Double> cachedPrices = new HashMap<>();
    private long lastUpdateTimeMillis = 0;

    public PriceService(TradingViewClient tradingViewClient) {
        this.tradingViewClient = tradingViewClient;
    }

    /**
     * Fetches prices (with caching). When the cache is stale or incomplete, it performs
     * exactly one multi-symbol request for the requested symbols.
     */
    public Map<String, Double> getPrices(Set<String> symbols) {
        if (symbols == null || symbols.isEmpty()) return Map.of();

        long now = System.currentTimeMillis();
        synchronized (this) {
            boolean cacheFresh = (now - lastUpdateTimeMillis) < CACHE_LIFETIME_MILLIS;
            boolean cacheMissing = false;
            for (String s : symbols) {
                if (!cachedPrices.containsKey(s)) {
                    cacheMissing = true;
                    break;
                }
            }

            if (cacheFresh && !cacheMissing) {
                return Map.copyOf(filterSymbols(symbols));
            }

            Map<String, Double> fetched = tradingViewClient.getPrices(symbols);
            cachedPrices.clear();
            cachedPrices.putAll(fetched);
            lastUpdateTimeMillis = now;

            return Map.copyOf(filterSymbols(symbols));
        }
    }

    private Map<String, Double> filterSymbols(Set<String> symbols) {
        Map<String, Double> out = new HashMap<>();
        for (String s : symbols) {
            Double v = cachedPrices.get(s);
            if (v != null) out.put(s, v);
        }
        return out;
    }
}

