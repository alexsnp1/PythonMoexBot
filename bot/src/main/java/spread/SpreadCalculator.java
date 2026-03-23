package spread;

import parser.FormulaParser;

import java.util.Map;

public class SpreadCalculator {
    private final FormulaParser formulaParser;

    public SpreadCalculator(FormulaParser formulaParser) {
        this.formulaParser = formulaParser;
    }

    public double calculate(String formula, Map<String, Double> prices) {
        return formulaParser.calculate(formula, prices);
    }
}

