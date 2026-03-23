package commands;

public interface CommandHandler {
    String commandName();

    String execute(long userId, String[] args);
}

