package util;

import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public final class TimeUtil {
    public static final ZoneId MOSCOW_ZONE = ZoneId.of("Europe/Moscow");
    private static final LocalTime ALERT_START = LocalTime.of(9, 0);
    private static final LocalTime ALERT_END = LocalTime.MIDNIGHT;

    private TimeUtil() {
    }

    /**
     * Alerts work between 09:00 and 00:00 Moscow time.
     * Practically: active from 09:00 inclusive until 23:59 inclusive.
     */
    public static boolean isWithinMoscowMarketHours(ZonedDateTime nowMoscow) {
        LocalTime t = nowMoscow.toLocalTime();
        // Inclusive endpoints requirement: include 00:00.
        return t.equals(ALERT_END) || !t.isBefore(ALERT_START);
    }

    public static ZonedDateTime nowMoscow() {
        return ZonedDateTime.now(MOSCOW_ZONE);
    }
}

