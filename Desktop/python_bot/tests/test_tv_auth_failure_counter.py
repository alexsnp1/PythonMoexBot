import logging
import unittest
import time

from price.price_service import PriceService


class TvAuthFailureCounterTests(unittest.TestCase):
    def setUp(self) -> None:
        logging.getLogger("PriceService").setLevel(logging.CRITICAL)

    def test_telegram_notify_only_after_threshold(self) -> None:
        notified: list[str] = []
        ps = PriceService(
            tradingview_auth_token="user_token_here",
            token_expiry_telegram_notify=lambda t: notified.append(t),
        )
        ps._record_auth_failure_signal("first")
        self.assertEqual(len(notified), 1)
        self.assertIn("TradingView", notified[0])
        # Throttling: third signal within 5 minutes should NOT notify again.
        ps._record_auth_failure_signal("second")
        self.assertEqual(len(notified), 1)

    def test_reset_auth_failure_count(self) -> None:
        ps = PriceService(tradingview_auth_token="t")
        ps._record_auth_failure_signal("a")
        ps._reset_auth_failure_count()
        with ps._tv_lock:
            self.assertEqual(ps._tv_auth_failure_count, 0)
            self.assertIsNone(ps._last_token_expiry_notification_ts)

    def test_rapid_close_does_not_count_without_prior_auth_failure(self) -> None:
        ps = PriceService(tradingview_auth_token="t")
        with ps._tv_lock:
            ps._tv_auth_failure_count = 0
            ps._tv_had_auth_failure = False
            ps._tv_connect_opened_at = time.time()
        ps._maybe_rapid_close_auth_failure()
        with ps._tv_lock:
            self.assertEqual(ps._tv_auth_failure_count, 0)

    def test_rapid_close_counts_after_prior_auth_failure(self) -> None:
        ps = PriceService(tradingview_auth_token="t")
        ps._record_auth_failure_signal("prior")
        with ps._tv_lock:
            ps._tv_connect_opened_at = time.time()
        ps._maybe_rapid_close_auth_failure()
        with ps._tv_lock:
            self.assertEqual(ps._tv_auth_failure_count, 2)


if __name__ == "__main__":
    unittest.main()
