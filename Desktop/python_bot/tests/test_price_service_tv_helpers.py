import unittest

from price.price_service import PriceService


class PriceServiceTvHelpersTests(unittest.TestCase):
    def test_reconnect_backoff_base_sequence(self) -> None:
        self.assertEqual(PriceService._tv_reconnect_backoff_base_seconds(1), 5.0)
        self.assertEqual(PriceService._tv_reconnect_backoff_base_seconds(2), 10.0)
        self.assertEqual(PriceService._tv_reconnect_backoff_base_seconds(3), 20.0)
        self.assertEqual(PriceService._tv_reconnect_backoff_base_seconds(4), 30.0)
        self.assertEqual(PriceService._tv_reconnect_backoff_base_seconds(10), 30.0)


if __name__ == "__main__":
    unittest.main()
