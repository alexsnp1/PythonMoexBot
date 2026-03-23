package scheduler;

import bot.BotMessageSender;
import db.DatabaseService;
import model.SpreadRule;
import parser.FormulaParser;
import price.PriceService;
import spread.SpreadCalculator;
import util.AlertFormatter;
import util.TimeUtil;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.ZonedDateTime;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

public class SpreadScheduler {
    private static final Logger log = LoggerFactory.getLogger(SpreadScheduler.class);
    private static final long RUN_PERIOD_SECONDS = 10;
    private static final long ALERT_COOLDOWN_MILLIS = 60_000;

    private final DatabaseService databaseService;
    private final PriceService priceService;
    private final SpreadCalculator spreadCalculator;
    private final FormulaParser formulaParser;
    private final BotMessageSender messageSender;

    private final ScheduledExecutorService executor;

    public SpreadScheduler(
            DatabaseService databaseService,
            PriceService priceService,
            SpreadCalculator spreadCalculator,
            FormulaParser formulaParser,
            BotMessageSender messageSender
    ) {
        this.databaseService = databaseService;
        this.priceService = priceService;
        this.spreadCalculator = spreadCalculator;
        this.formulaParser = formulaParser;
        this.messageSender = messageSender;
        this.executor = Executors.newSingleThreadScheduledExecutor(new NamedThreadFactory("spread-scheduler"));
    }

    public void start() {
        executor.scheduleAtFixedRate(this::runOnce, 0, RUN_PERIOD_SECONDS, TimeUnit.SECONDS);
        log.info("SpreadScheduler started (period={}s)", RUN_PERIOD_SECONDS);
    }

    public void stop() {
        executor.shutdownNow();
    }

    private void runOnce() {
        try {
            ZonedDateTime nowMoscow = TimeUtil.nowMoscow();
            if (!TimeUtil.isWithinMoscowMarketHours(nowMoscow)) {
                return;
            }

            List<SpreadRule> rules = databaseService.getAllRules();
            if (rules.isEmpty()) return;

            Set<String> tradingViewSymbols = new HashSet<>();
            for (SpreadRule rule : rules) {
                tradingViewSymbols.addAll(formulaParser.extractTradingViewSymbols(rule.getFormula()));
            }

            if (tradingViewSymbols.isEmpty()) return;

            // PriceService returns normalized keys suitable for FormulaParser calculations.
            Map<String, Double> prices = priceService.getPrices(tradingViewSymbols);
            if (prices.isEmpty()) {
                log.warn("No prices fetched; skipping evaluation");
                return;
            }

            long nowMillis = System.currentTimeMillis();
            for (SpreadRule rule : rules) {
                evaluateRule(rule, prices, nowMillis);
            }
        } catch (Exception e) {
            log.error("Scheduler iteration failed", e);
        }
    }

    private void evaluateRule(SpreadRule rule, Map<String, Double> prices, long nowMillis) {
        Double upper = rule.getUpperBound();
        Double lower = rule.getLowerBound();

        double value;
        try {
            value = spreadCalculator.calculate(rule.getFormula(), prices);
        } catch (Exception e) {
            log.warn("Failed to calculate formula for ruleId={} userId={}. Skipping. {}", rule.getId(), rule.getUserId(), e.getMessage());
            return;
        }

        boolean trigger = (upper != null && value > upper) || (lower != null && value < lower);
        if (!trigger) return;

        long last = rule.getLastAlertTimeMillis();
        if (last > 0 && (nowMillis - last) < ALERT_COOLDOWN_MILLIS) {
            return; // anti-spam cooldown
        }

        String text = AlertFormatter.format(rule, value);
        try {
            messageSender.sendMessage(rule.getUserId(), text);
            databaseService.updateLastAlertTime(rule.getUserId(), rule.getId(), nowMillis);
        } catch (Exception e) {
            log.error("Failed to send/update alert for ruleId={} userId={}", rule.getId(), rule.getUserId(), e);
        }
    }

    private static final class NamedThreadFactory implements ThreadFactory {
        private final String baseName;

        private NamedThreadFactory(String baseName) {
            this.baseName = baseName;
        }

        @Override
        public Thread newThread(Runnable r) {
            Thread t = new Thread(r, baseName);
            t.setDaemon(true);
            return t;
        }
    }
}

