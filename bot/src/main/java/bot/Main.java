package bot;

import commands.AddCommand;
import commands.CommandHandler;
import commands.EditCommand;
import commands.ListCommand;
import commands.RemoveCommand;
import db.DatabaseService;
import parser.FormulaParser;
import price.PriceService;
import price.TradingViewClient;
import scheduler.SpreadScheduler;
import spread.SpreadCalculator;
import util.AppConfig;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.telegram.telegrambots.meta.TelegramBotsApi;
import org.telegram.telegrambots.updatesreceivers.DefaultBotSession;

import java.nio.file.Path;
import java.util.List;

public class Main {
    private static final Logger log = LoggerFactory.getLogger(Main.class);

    public static void main(String[] args) throws Exception {
        String telegramToken = AppConfig.requireEnv("TELEGRAM_BOT_TOKEN");
        String telegramUsername = AppConfig.requireEnv("TELEGRAM_BOT_USERNAME");

        boolean mockPrices = AppConfig.getEnvOrDefaultBoolean("TRADINGVIEW_MOCK_PRICES", true);
        String tradingViewEndpoint = AppConfig.getEnvOrDefault("TRADINGVIEW_PRICES_ENDPOINT", "");

        Path dbPath = AppConfig.dbPath();
        log.info("Using DB path: {}", dbPath);

        DatabaseService databaseService = new DatabaseService(dbPath);
        databaseService.init();

        FormulaParser formulaParser = new FormulaParser();
        SpreadCalculator spreadCalculator = new SpreadCalculator(formulaParser);

        TradingViewClient tvClient = new TradingViewClient(tradingViewEndpoint, mockPrices);
        PriceService priceService = new PriceService(tvClient);

        List<CommandHandler> handlers = List.of(
                new AddCommand(databaseService, formulaParser),
                new RemoveCommand(databaseService),
                new EditCommand(databaseService),
                new ListCommand(databaseService)
        );

        TelegramSpreadBot bot = new TelegramSpreadBot(telegramToken, telegramUsername, handlers);

        TelegramBotsApi botsApi = new TelegramBotsApi(DefaultBotSession.class);
        botsApi.registerBot(bot);

        SpreadScheduler scheduler = new SpreadScheduler(
                databaseService,
                priceService,
                spreadCalculator,
                formulaParser,
                bot
        );
        scheduler.start();

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try {
                scheduler.stop();
            } catch (Exception ignored) {
            }
        }));
    }
}

