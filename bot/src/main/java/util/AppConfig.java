package util;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public final class AppConfig {
    private static final String SECRETS_FILE_NAME = "secrets.properties";
    private static volatile Properties secrets;

    private AppConfig() {
    }

    public static String requireEnv(String key) {
        String v = getEnvOrSecrets(key);
        if (v == null || v.isBlank()) {
            throw new IllegalStateException("Missing required value for: " + key + ". Provide env var or secrets.properties");
        }
        return v.trim();
    }

    public static String getEnvOrDefault(String key, String defaultValue) {
        String v = getEnvOrSecrets(key);
        if (v == null || v.isBlank()) return defaultValue;
        return v.trim();
    }

    public static boolean getEnvOrDefaultBoolean(String key, boolean defaultValue) {
        String v = getEnvOrSecrets(key);
        if (v == null || v.isBlank()) return defaultValue;
        return Boolean.parseBoolean(v.trim());
    }

    public static long getEnvOrDefaultLong(String key, long defaultValue) {
        String v = getEnvOrSecrets(key);
        if (v == null || v.isBlank()) return defaultValue;
        return Long.parseLong(v.trim());
    }

    public static double getEnvOrDefaultDouble(String key, double defaultValue) {
        String v = getEnvOrSecrets(key);
        if (v == null || v.isBlank()) return defaultValue;
        return Double.parseDouble(v.trim());
    }

    public static Path dbPath() {
        String p = getEnvOrDefault("DB_PATH", "spread-bot.sqlite");
        return Path.of(p).toAbsolutePath();
    }

    private static String getEnvOrSecrets(String key) {
        String v = System.getenv(key);
        if (v != null && !v.isBlank()) return v;

        Properties s = loadSecrets();
        if (s == null) return null;
        String sv = s.getProperty(key);
        if (sv == null || sv.isBlank()) return null;
        return sv;
    }

    private static Properties loadSecrets() {
        if (secrets != null) return secrets;
        synchronized (AppConfig.class) {
            if (secrets != null) return secrets;

            // Try a few likely locations for local development.
            // Production deployments should rely on environment variables.
            Path[] candidates = new Path[]{
                    // 1) Working directory (when running from project root)
                    Path.of(SECRETS_FILE_NAME).toAbsolutePath(),
                    // 2) If user placed it in their current src/main/java/bot folder
                    Path.of("src/main/java/bot").resolve(SECRETS_FILE_NAME).toAbsolutePath(),
                    // 3) Resource-like location (not required for this project, but supported)
                    Path.of("src/main/resources").resolve(SECRETS_FILE_NAME).toAbsolutePath(),
            };

            // 4) Next to the running jar (useful for some deployment setups)
            try {
                var codeSource = AppConfig.class.getProtectionDomain().getCodeSource();
                if (codeSource != null && codeSource.getLocation() != null) {
                    Path loc = Path.of(codeSource.getLocation().toURI());
                    Path dir = Files.isDirectory(loc) ? loc : loc.getParent();
                    if (dir != null) {
                        candidates = appendCandidate(candidates, dir.resolve(SECRETS_FILE_NAME).toAbsolutePath());
                    }
                }
            } catch (Exception ignored) {
            }

            Path found = null;
            for (Path p : candidates) {
                if (p != null && Files.exists(p) && Files.isRegularFile(p)) {
                    found = p;
                    break;
                }
            }

            if (found == null) {
                secrets = new Properties();
                return secrets;
            }

            Properties p = new Properties();
            try (InputStream in = Files.newInputStream(found)) {
                p.load(in);
            } catch (Exception e) {
                // If secrets can't be loaded, fail fast only when a required key is asked for.
                secrets = new Properties();
                return secrets;
            }

            secrets = p;
            return secrets;
        }
    }

    private static Path[] appendCandidate(Path[] base, Path extra) {
        Path[] out = new Path[base.length + 1];
        System.arraycopy(base, 0, out, 0, base.length);
        out[base.length] = extra;
        return out;
    }
}

