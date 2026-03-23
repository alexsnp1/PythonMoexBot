package commands;

import db.DatabaseService;
import model.SpreadRule;

import java.util.List;

public class ListCommand implements CommandHandler {
    private final DatabaseService databaseService;

    public ListCommand(DatabaseService databaseService) {
        this.databaseService = databaseService;
    }

    @Override
    public String commandName() {
        return "list";
    }

    @Override
    public String execute(long userId, String[] args) {
        // /list
        if (args.length != 0) {
            return "Usage: /list";
        }

        List<SpreadRule> rules = databaseService.listRules(userId);
        if (rules.isEmpty()) {
            return "No rules found. Add one with /add";
        }

        StringBuilder sb = new StringBuilder();
        int i = 1;
        for (SpreadRule r : rules) {
            sb.append(i++).append(". ").append(r.getFormula()).append('\n');
            sb.append("upper: ").append(r.getUpperBound() == null ? "-" : r.getUpperBound()).append('\n');
            sb.append("lower: ").append(r.getLowerBound() == null ? "-" : r.getLowerBound()).append('\n');
            sb.append('\n');
        }
        return sb.toString().trim();
    }
}

