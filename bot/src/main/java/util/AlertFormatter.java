package util;

import model.SpreadRule;

import java.util.Locale;

public final class AlertFormatter {
    private AlertFormatter() {
    }

    public static String format(SpreadRule rule, double value) {
        // NOTE: formula is stored as user input and should be shown as-is.
        String upper = rule.getUpperBound() == null ? "-" : formatNumber(rule.getUpperBound());
        String lower = rule.getLowerBound() == null ? "-" : formatNumber(rule.getLowerBound());
        return """
                🚨 Spread Alert

                Formula:
                %s

                Value: %s

                Upper: %s
                Lower: %s
                """.formatted(rule.getFormula(), formatNumber(value), upper, lower).trim();
    }

    private static String formatNumber(double d) {
        // Avoid scientific notation for typical prices.
        return String.format(Locale.ROOT, "%.4f", d);
    }
}

