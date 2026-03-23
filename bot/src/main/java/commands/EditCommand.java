package commands;

import db.DatabaseService;

public class EditCommand implements CommandHandler {
    private final DatabaseService databaseService;

    public EditCommand(DatabaseService databaseService) {
        this.databaseService = databaseService;
    }

    @Override
    public String commandName() {
        return "edit";
    }

    @Override
    public String execute(long userId, String[] args) {
        // /edit <id> <upper> <lower>
        if (args.length != 3) {
            return "Usage: /edit <id> <upper> <lower>\nUse '-' to skip a bound.";
        }

        long id;
        try {
            id = Long.parseLong(args[0].trim());
        } catch (NumberFormatException e) {
            return "Invalid id: " + args[0];
        }

        Double upper;
        Double lower;
        try {
            upper = parseThreshold(args[1]);
            lower = parseThreshold(args[2]);
        } catch (IllegalArgumentException e) {
            return e.getMessage();
        }

        if (upper == null && lower == null) {
            return "At least one threshold must be set. Use '-' to skip a bound.";
        }

        boolean ok = databaseService.updateThresholds(userId, id, upper, lower);
        return ok ? ("Updated rule #" + id) : ("Rule not found: #" + id);
    }

    private static Double parseThreshold(String raw) {
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

