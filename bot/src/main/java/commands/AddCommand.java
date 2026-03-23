package commands;

import db.DatabaseService;
import parser.FormulaParser;

public class AddCommand implements CommandHandler {
    private final DatabaseService databaseService;
    private final FormulaParser formulaParser;

    public AddCommand(DatabaseService databaseService, FormulaParser formulaParser) {
        this.databaseService = databaseService;
        this.formulaParser = formulaParser;
    }

    @Override
    public String commandName() {
        return "add";
    }

    @Override
    public String execute(long userId, String[] args) {
        // /add <formula> <upper> <lower>
        if (args.length != 3) {
            return "Usage: /add <formula> <upper> <lower>\nExample: /add RUS:SV1!/TVC:SILVER*1000 1010 995";
        }

        String formula = args[0];
        Double upper = parseThreshold(args[1]);
        Double lower = parseThreshold(args[2]);

        if (upper == null && lower == null) {
            return "At least one threshold must be set. Use '-' to skip a bound.";
        }

        try {
            formulaParser.validate(formula);
        } catch (Exception e) {
            return "Invalid formula: " + e.getMessage();
        }

        long id = databaseService.addRule(userId, formula, upper, lower);
        return "Added rule #" + id;
    }

    private Double parseThreshold(String raw) {
        if (raw == null) return null;
        String t = raw.trim();
        if (t.equals("-")) return null;
        try {
            return Double.parseDouble(t);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("Invalid number: " + raw);
        }
    }
}

