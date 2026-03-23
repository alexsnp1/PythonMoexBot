package price;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

/**
 * TradingView scanner client (unofficial).
 *
 * Endpoint:
 * POST https://scanner.tradingview.com/global/scan
 *
 * Request body:
 * {
 *   "symbols": { "tickers": ["TVC:SILVER", "FX:USDCNH", "RUS:SV1!"], "query": { "types": [] } },
 *   "columns": ["last", "close"]
 * }
 *
 * Response:
 * { "data": [ { "s": "TVC:SILVER", "d": [24.53, 24.50] }, ... ] }
 */
public class TradingViewClient {
    private static final Logger log = LoggerFactory.getLogger(TradingViewClient.class);

    private static final String SCANNER_URL = "https://scanner.tradingview.com/global/scan";
    private static final Duration HTTP_TIMEOUT = Duration.ofSeconds(15);

    private final HttpClient httpClient;
    private final Gson gson;

    public TradingViewClient() {
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
        this.gson = new Gson();
    }

    /**
     * Fetches prices for all requested tickers in a single request.
     * Uses "last" as primary source, with "close" as fallback.
     *
     * Keys in input and output are TradingView symbols as-is (e.g., TVC:SILVER, FX:USDCNH, RUS:SV1!).
     */
    public Map<String, Double> getPrices(Set<String> symbols) {
        if (symbols == null || symbols.isEmpty()) return Map.of();

        JsonObject body = new JsonObject();

        JsonObject symbolsObj = new JsonObject();
        JsonArray tickers = new JsonArray();
        for (String s : symbols) {
            if (s == null || s.isBlank()) continue;
            tickers.add(s.trim());
        }
        symbolsObj.add("tickers", tickers);

        JsonObject query = new JsonObject();
        query.add("types", new JsonArray()); // empty list as required
        symbolsObj.add("query", query);

        body.add("symbols", symbolsObj);

        JsonArray columns = new JsonArray();
        columns.add("last");
        columns.add("close");
        body.add("columns", columns);

        String payload = gson.toJson(body);

        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(SCANNER_URL))
                .timeout(HTTP_TIMEOUT)
                .header("Content-Type", "application/json")
                .header("User-Agent", "telegram-spread-bot/1.0")
                .POST(HttpRequest.BodyPublishers.ofString(payload))
                .build();

        try {
            HttpResponse<String> resp = httpClient.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() < 200 || resp.statusCode() >= 300) {
                throw new IllegalStateException("TradingView scanner HTTP status=" + resp.statusCode());
            }

            JsonObject root = JsonParser.parseString(resp.body()).getAsJsonObject();
            JsonArray dataArr = root.has("data") && root.get("data").isJsonArray() ? root.getAsJsonArray("data") : null;
            if (dataArr == null || dataArr.isEmpty()) {
                log.warn("TradingView returned empty response for symbolsCount={}", symbols.size());
                return Map.of();
            }

            Map<String, Double> out = new HashMap<>();
            for (var el : dataArr) {
                if (!el.isJsonObject()) continue;
                JsonObject o = el.getAsJsonObject();
                if (!o.has("s") || !o.has("d")) continue;

                String s = o.get("s").getAsString();
                JsonArray d = o.getAsJsonArray("d");
                if (d == null || d.size() == 0) continue;

                Double price = null;
                if (!d.get(0).isJsonNull()) {
                    price = d.get(0).getAsDouble(); // last
                    log.debug("Price used: symbol={}, type=LAST, value={}", s, price);
                } else if (d.size() > 1 && !d.get(1).isJsonNull()) {
                    price = d.get(1).getAsDouble(); // close fallback
                    log.debug("Price used: symbol={}, type=CLOSE_FALLBACK, value={}", s, price);
                }

                if (price != null) {
                    out.put(s, price);
                }
            }

            if (out.isEmpty()) {
                log.warn("TradingView response parsed but contains no prices. symbolsCount={}", symbols.size());
            }

            return out;
        } catch (Exception e) {
            throw new IllegalStateException("TradingView fetch failed: " + e.getMessage(), e);
        }
    }
}

