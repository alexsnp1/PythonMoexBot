import unittest

from price.price_service import PriceService


class PriceServiceRealtimeParserTests(unittest.TestCase):
    def test_selects_last_price_with_priority(self) -> None:
        payload = {"m": "qsd", "p": [{"v": {"lp": 104.7, "bid": 104.6, "ask": 104.8}}]}
        selected = PriceService._select_realtime_price(payload)
        self.assertEqual(selected, 104.7)

    def test_falls_back_to_bid_ask_mid(self) -> None:
        payload = {"m": "qsd", "p": [{"v": {"bid": 100.0, "ask": 102.0}}]}
        selected = PriceService._select_realtime_price(payload)
        self.assertEqual(selected, 101.0)

    def test_falls_back_to_single_side(self) -> None:
        payload = {"m": "qsd", "p": [{"v": {"ask": 50.5}}]}
        selected = PriceService._select_realtime_price(payload)
        self.assertEqual(selected, 50.5)

    def test_returns_none_when_no_supported_fields(self) -> None:
        payload = {"m": "timescale_update", "p": [{"x": 1}]}
        selected = PriceService._select_realtime_price(payload)
        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()

