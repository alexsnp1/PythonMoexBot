package price;

import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

/**
 * TradingView price fetcher.
 *
 * Default behavior is a deterministic mock (so the project runs without external API credentials).
 * To use a real endpoint, set:
 * - TRADINGVIEW_MOCK_PRICES=false
 * - TRADINGVIEW_PRICES_ENDPOINT to a URL that supports a `symbols` query parameter
 *   and returns a JSON object like: { "SV1": 123.45, "SILVER": 101.01 }
 */
public class TradingViewClient {
    private final HttpClient httpClient;
    private final String endpointUrl;
    private final boolean mockPrices;
    private final Duration timeout = Duration.ofSeconds(10);
    private final Gson gson = new Gson();

    public TradingViewClient(String endpointUrl, boolean mockPrices) {
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
        this.endpointUrl = endpointUrl;
        this.mockPrices = mockPrices;
    }

    public Map<String, Double> getPrices(Set<String> symbols) {
        if (symbols == null || symbols.isEmpty()) return Map.of();
        if (mockPrices || endpointUrl == null || endpointUrl.isBlank()) {
            return mockPrices(symbols);
        }

        // One request for multiple symbols.
        String joined = String.join(",", symbols);
        String encoded = URLEncoder.encode(joined, StandardCharsets.UTF_8);

        String url = endpointUrl;
        url = url.contains("?") ? (url + "&symbols=" + encoded) : (url + "?symbols=" + encoded);

        HttpRequest req = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(timeout)
                .GET()
                .build();

        try {
            HttpResponse<String> resp = httpClient.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() < 200 || resp.statusCode() >= 300) {
                throw new IllegalStateException("Price endpoint returned status: " + resp.statusCode());
            }

            // Expect: JSON object { "SYM": 123.45, ... }
            JsonElement root = JsonParser.parseString(resp.body());
            if (!root.isJsonObject()) {
                throw new IllegalStateException("Unexpected JSON response shape (expected object)");
            }

            JsonObject obj = root.getAsJsonObject();
            Map<String, Double> out = new HashMap<>();
            for (Map.Entry<String, JsonElement> e : obj.entrySet()) {
                if (e.getValue() == null || !e.getValue().isJsonPrimitive()) continue;
                JsonElement v = e.getValue();
                if (v.getAsJsonPrimitive().isNumber()) {
                    out.put(e.getKey(), v.getAsDouble());
                }
            }
            return out;
        } catch (Exception e) {
            throw new IllegalStateException("Failed to fetch prices from endpoint", e);
        }
    }

    private Map<String, Double> mockPrices(Set<String> symbols) {
        Map<String, Double> out = new HashMap<>();
        for (String s : symbols) {
            // Stable deterministic pseudo-price per symbol.
            int h = s == null ? 0 : s.hashCode();
            double base = 50.0 + (Math.abs(h) % 10_000) / 20.0;
            out.put(s, base);
        }
        return out;
    }
}

