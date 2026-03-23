package price;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import parser.FormulaParser;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

/**
 * Price cache for spread evaluation.
 *
 * - Inputs are TradingView symbols (e.g., TVC:SILVER, FX:USDCNH, RUS:SV1!)
 * - Cache stores prices keyed by normalized symbols expected by FormulaParser:
 *   SV1, SILVER, USDCNH, etc.
 * - Cache lifetime: 60 seconds.
 */
public class PriceService {
    private static final long CACHE_LIFETIME_MILLIS = 60_000;
    private static final long REFRESH_MAX_WAIT_WHEN_CACHE_EMPTY_MILLIS = 10_000;

    private static final Logger log = LoggerFactory.getLogger(PriceService.class);

    private final TradingViewClient tradingViewClient;
    private final FormulaParser formulaParser;

    private final Map<String, Double> cachedNormalizedPrices = new HashMap<>();
    private long lastUpdateTimeMillis = 0;

    private final ExecutorService refreshExecutor;
    private Future<?> refreshFuture;

    public PriceService(TradingViewClient tradingViewClient, FormulaParser formulaParser) {
        this.tradingViewClient = tradingViewClient;
        this.formulaParser = formulaParser;
        this.refreshExecutor = Executors.newSingleThreadExecutor(new NamedDaemonThreadFactory("tv-price-refresh"));
    }

    /**
     * Fetch prices for requested TradingView symbols.
     *
     * Returns prices keyed by normalized symbols for formula calculation.
     */
    public Map<String, Double> getPrices(Set<String> symbols) {
        if (symbols == null || symbols.isEmpty()) return Map.of();

        Set<String> normalizedNeeded = new HashSet<>();
        for (String s : symbols) {
            if (s == null || s.isBlank()) continue;
            String n = formulaParser.normalizeTradingViewSymbol(s);
            if (n != null && !n.isBlank()) normalizedNeeded.add(n);
        }
        if (normalizedNeeded.isEmpty()) return Map.of();

        long now = System.currentTimeMillis();
        Future<?> toWait = null;

        synchronized (this) {
            boolean cacheFresh = (now - lastUpdateTimeMillis) < CACHE_LIFETIME_MILLIS;
            if (cacheFresh) return Map.copyOf(filterNormalized(normalizedNeeded));

            if (refreshFuture == null || refreshFuture.isDone()) {
                Set<String> requested = new HashSet<>(symbols);
                refreshFuture = refreshExecutor.submit(() -> refreshPricesFor(requested));
            }

            // If cache is empty, wait a bit for the first refresh.
            if (cachedNormalizedPrices.isEmpty()) {
                toWait = refreshFuture;
            }
        }

        if (toWait != null) {
            try {
                toWait.get(REFRESH_MAX_WAIT_WHEN_CACHE_EMPTY_MILLIS, TimeUnit.MILLISECONDS);
            } catch (Exception ignored) {
                // Keep going with whatever is in cache.
            }
        }

        synchronized (this) {
            return Map.copyOf(filterNormalized(normalizedNeeded));
        }
    }

    private void refreshPricesFor(Set<String> requestedTradingViewSymbols) {
        long startedAt = System.currentTimeMillis();
        try {
            Map<String, Double> tvPrices = tradingViewClient.getPrices(requestedTradingViewSymbols);
            if (tvPrices == null || tvPrices.isEmpty()) {
                log.warn("TradingView returned empty response. requestedSymbolsCount={}", requestedTradingViewSymbols.size());
                return;
            }

            Map<String, Double> fetchedNormalized = new HashMap<>();
            for (var entry : tvPrices.entrySet()) {
                String tradingViewSymbol = entry.getKey();
                Double price = entry.getValue();
                if (tradingViewSymbol == null || price == null) continue;

                String normalized = formulaParser.normalizeTradingViewSymbol(tradingViewSymbol);
                if (normalized == null || normalized.isBlank()) continue;
                fetchedNormalized.put(normalized, price);
            }

            if (fetchedNormalized.isEmpty()) {
                log.warn("TradingView response parsed but no normalized prices produced. requestedSymbolsCount={}",
                        requestedTradingViewSymbols.size());
                return;
            }

            // Missing symbols (requested but absent in TradingView response).
            for (String requested : requestedTradingViewSymbols) {
                if (requested == null || requested.isBlank()) continue;
                if (!tvPrices.containsKey(requested)) {
                    String normalized = formulaParser.normalizeTradingViewSymbol(requested);
                    log.warn("TradingView price missing. tradingViewSymbol={} normalizedSymbol={}", requested, normalized);
                }
            }

            // Update cache.
            synchronized (this) {
                cachedNormalizedPrices.clear();
                cachedNormalizedPrices.putAll(fetchedNormalized);
                lastUpdateTimeMillis = startedAt;
            }

            log.info("TradingView prices refreshed. cachedSymbolsNormalizedCount={}", fetchedNormalized.size());
        } catch (Exception e) {
            log.warn("TradingView refresh failed: {}", e.toString());
        } finally {
            synchronized (this) {
                // Prevent refresh spam: even on failure/empty response we consider cache "updated".
                lastUpdateTimeMillis = startedAt;
            }
        }
    }

    private Map<String, Double> filterNormalized(Set<String> normalizedSymbols) {
        Map<String, Double> out = new HashMap<>();
        for (String n : normalizedSymbols) {
            Double v = cachedNormalizedPrices.get(n);
            if (v != null) out.put(n, v);
        }
        return out;
    }

    private static final class NamedDaemonThreadFactory implements ThreadFactory {
        private final String baseName;

        private NamedDaemonThreadFactory(String baseName) {
            this.baseName = baseName;
        }

        @Override
        public Thread newThread(Runnable r) {
            Thread t = new Thread(r, baseName);
            t.setDaemon(true);
            return t;
        }
    }
}

