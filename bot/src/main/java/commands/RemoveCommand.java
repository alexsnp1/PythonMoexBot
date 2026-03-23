package commands;

import db.DatabaseService;

public class RemoveCommand implements CommandHandler {
    private final DatabaseService databaseService;

    public RemoveCommand(DatabaseService databaseService) {
        this.databaseService = databaseService;
    }

    @Override
    public String commandName() {
        return "remove";
    }

    @Override
    public String execute(long userId, String[] args) {
        // /remove <id>
        if (args.length != 1) {
            return "Usage: /remove <id>";
        }
        long id;
        try {
            id = Long.parseLong(args[0].trim());
        } catch (NumberFormatException e) {
            return "Invalid id: " + args[0];
        }

        boolean ok = databaseService.removeRule(userId, id);
        return ok ? ("Removed rule #" + id) : ("Rule not found: #" + id);
    }
}

