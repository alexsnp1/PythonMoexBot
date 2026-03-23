package parser;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class FormulaParser {
    // Full symbol token example: RUS:SV1!
    private static final Pattern FULL_SYMBOL_PATTERN = Pattern.compile("^[A-Z]+:([A-Z0-9!]+)$");
    // Raw regex example: [A-Z]+:([A-Z0-9!]+)
    private static final Pattern EXTRACT_SYMBOL_PATTERN = Pattern.compile("[A-Z]+:([A-Z0-9!]+)");

    private enum Operator {
        MULTIPLY('*'),
        DIVIDE('/');

        private final char symbol;

        Operator(char symbol) {
            this.symbol = symbol;
        }

        public static Operator fromChar(char c) {
            return switch (c) {
                case '*' -> MULTIPLY;
                case '/' -> DIVIDE;
                default -> throw new IllegalArgumentException("Unsupported operator: " + c);
            };
        }
    }

    private interface Token {
    }

    private record SymbolToken(String normalizedSymbol) implements Token {
    }

    private record NumberToken(double value) implements Token {
    }

    private record OperatorToken(Operator operator) implements Token {
    }

    public Set<String> extractAndNormalizeSymbols(String formula) {
        if (formula == null || formula.isBlank()) {
            throw new IllegalArgumentException("Formula must not be empty");
        }
        Set<String> out = new HashSet<>();
        Matcher m = EXTRACT_SYMBOL_PATTERN.matcher(formula.toUpperCase());
        while (m.find()) {
            String raw = m.group(1);
            out.add(normalizeSymbol(raw));
        }
        return out;
    }

    /**
     * Normalization examples:
     * - RUS:SV1! -> SV1
     * - FX:USDCNH -> USDCNH
     */
    public String normalizeSymbol(String symbolTokenOrGroup) {
        if (symbolTokenOrGroup == null) return "";
        // The extracted regex group includes the trailing '!'. Remove it.
        return symbolTokenOrGroup.replace("!", "").trim();
    }

    public double calculate(String formula, Map<String, Double> prices) {
        if (prices == null) throw new IllegalArgumentException("Prices map must not be null");
        List<Token> tokens = prepareTokens(formula);
        return evaluateTokens(tokens, prices);
    }

    public void validate(String formula) {
        prepareTokens(formula); // throws on invalid formats
    }

    private List<Token> prepareTokens(String formula) {
        if (formula == null) throw new IllegalArgumentException("Formula must not be null");
        String trimmed = formula.trim().toUpperCase();
        if (trimmed.isEmpty()) throw new IllegalArgumentException("Formula must not be empty");

        List<Token> tokens = new ArrayList<>();

        StringBuilder buf = new StringBuilder();
        for (int i = 0; i < trimmed.length(); i++) {
            char c = trimmed.charAt(i);
            if (c == '*' || c == '/') {
                flushFactor(tokens, buf);
                tokens.add(new OperatorToken(Operator.fromChar(c)));
            } else if (Character.isWhitespace(c)) {
                // We do not support spaces in formulas, but tolerate them by ignoring.
                continue;
            } else {
                buf.append(c);
            }
        }
        flushFactor(tokens, buf);

        // Validate sequence: factor (op factor)*
        if (tokens.isEmpty()) throw new IllegalArgumentException("Formula has no tokens");
        if (!(tokens.get(0) instanceof SymbolToken || tokens.get(0) instanceof NumberToken)) {
            throw new IllegalArgumentException("Formula must start with a factor");
        }

        for (int i = 0; i < tokens.size(); i++) {
            Token t = tokens.get(i);
            if (i % 2 == 0) {
                if (!(t instanceof SymbolToken || t instanceof NumberToken)) {
                    throw new IllegalArgumentException("Expected factor at token index " + i);
                }
            } else {
                if (!(t instanceof OperatorToken)) {
                    throw new IllegalArgumentException("Expected operator at token index " + i);
                }
            }
        }
        return tokens;
    }

    private void flushFactor(List<Token> tokens, StringBuilder buf) {
        if (buf.isEmpty()) return;
        String raw = buf.toString().trim();
        buf.setLength(0);

        if (raw.isEmpty()) return;

        Matcher symbolMatcher = FULL_SYMBOL_PATTERN.matcher(raw.toUpperCase());
        if (symbolMatcher.matches()) {
            String group = symbolMatcher.group(1);
            tokens.add(new SymbolToken(normalizeSymbol(group)));
            return;
        }

        // Otherwise it's expected to be a number.
        try {
            double v = Double.parseDouble(raw);
            tokens.add(new NumberToken(v));
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("Invalid factor token: " + raw, e);
        }
    }

    private double evaluateTokens(List<Token> tokens, Map<String, Double> prices) {
        double result;
        Token first = tokens.get(0);
        if (first instanceof SymbolToken st) {
            result = getPriceOrThrow(st.normalizedSymbol(), prices);
        } else if (first instanceof NumberToken nt) {
            result = nt.value();
        } else {
            throw new IllegalStateException("Unexpected first token type");
        }

        for (int i = 1; i < tokens.size(); i += 2) {
            OperatorToken opToken = (OperatorToken) tokens.get(i);
            Token next = tokens.get(i + 1);

            double nextValue;
            if (next instanceof SymbolToken st) {
                nextValue = getPriceOrThrow(st.normalizedSymbol(), prices);
            } else if (next instanceof NumberToken nt) {
                nextValue = nt.value();
            } else {
                throw new IllegalStateException("Unexpected next token type");
            }

            result = switch (opToken.operator()) {
                case MULTIPLY -> result * nextValue;
                case DIVIDE -> result / nextValue;
            };
        }

        return result;
    }

    private static double getPriceOrThrow(String symbol, Map<String, Double> prices) {
        Double v = prices.get(symbol);
        if (v == null) {
            throw new IllegalArgumentException("Missing price for symbol: " + symbol);
        }
        return v;
    }
}

