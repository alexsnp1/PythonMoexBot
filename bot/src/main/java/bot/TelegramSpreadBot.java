package bot;

import commands.CommandHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.telegram.telegrambots.bots.TelegramLongPollingBot;
import org.telegram.telegrambots.meta.TelegramBotsApi;
import org.telegram.telegrambots.meta.api.methods.send.SendMessage;
import org.telegram.telegrambots.meta.api.objects.Update;
import org.telegram.telegrambots.meta.exceptions.TelegramApiException;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class TelegramSpreadBot extends TelegramLongPollingBot implements BotMessageSender {
    private static final Logger log = LoggerFactory.getLogger(TelegramSpreadBot.class);

    private final String botToken;
    private final String botUsername;
    private final Map<String, CommandHandler> handlersByName;

    public TelegramSpreadBot(String botToken, String botUsername, List<CommandHandler> handlers) {
        this.botToken = Objects.requireNonNull(botToken, "botToken");
        this.botUsername = Objects.requireNonNull(botUsername, "botUsername");
        this.handlersByName = new HashMap<>();
        for (CommandHandler h : handlers) {
            this.handlersByName.put(h.commandName(), h);
        }
    }

    @Override
    public String getBotUsername() {
        return botUsername;
    }

    @Override
    public String getBotToken() {
        return botToken;
    }

    @Override
    public void onUpdateReceived(Update update) {
        try {
            if (update == null || !update.hasMessage()) return;
            if (!update.getMessage().hasText()) return;

            var msg = update.getMessage();
            String text = msg.getText();
            if (text == null || text.isBlank()) return;
            text = text.trim();

            if (!text.startsWith("/")) return;

            long chatId = msg.getChatId();
            long userId = msg.getFrom() != null ? msg.getFrom().getId() : chatId;

            String rawCmd = text.split("\\s+", 2)[0]; // "/add"
            rawCmd = rawCmd.startsWith("/") ? rawCmd.substring(1) : rawCmd;
            // Support commands like "/add@YourBot"
            if (rawCmd.contains("@")) rawCmd = rawCmd.substring(0, rawCmd.indexOf('@'));

            String cmd = rawCmd.toLowerCase();
            CommandHandler handler = handlersByName.get(cmd);

            String[] parts = text.split("\\s+");
            String[] args = parts.length <= 1 ? new String[0] : java.util.Arrays.copyOfRange(parts, 1, parts.length);

            String response;
            if (handler == null) {
                response = "Unknown command. Available: /add, /edit, /remove, /list";
            } else {
                response = handler.execute(userId, args);
            }

            if (response != null && !response.isBlank()) {
                sendMessage(chatId, response);
            }
        } catch (Exception e) {
            log.error("Failed to handle update", e);
        }
    }

    @Override
    public void sendMessage(long chatId, String text) {
        try {
            execute(new SendMessage(String.valueOf(chatId), text));
        } catch (TelegramApiException e) {
            log.error("Failed to send message to chatId={}", chatId, e);
        }
    }
}

