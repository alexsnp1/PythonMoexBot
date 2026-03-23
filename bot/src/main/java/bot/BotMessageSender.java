package bot;

public interface BotMessageSender {
    void sendMessage(long chatId, String text);
}

