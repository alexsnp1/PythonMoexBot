import unittest

from price.price_service import PriceService


class PriceServiceRealtimeParserTests(unittest.TestCase):
    def test_masks_long_token(self) -> None:
        self.assertEqual(PriceService._mask_token("abcdef123456"), "abc***456")

    def test_masks_short_token(self) -> None:
        self.assertEqual(PriceService._mask_token("short"), "***")

    def test_parse_qsd_with_exchange_symbol(self) -> None:
        ps = PriceService()
        sym, price = ps._parse_qsd_symbol_and_price(
            {"m": "qsd", "p": ["qs_x", {"n": "MOEX:FOO", "v": {"lp": 12.5}}]}
        )
        self.assertEqual(sym, "MOEX:FOO")
        self.assertEqual(price, 12.5)

    def test_parse_token_expires_at_unix(self) -> None:
        self.assertEqual(PriceService.parse_tradingview_token_expires_at("1700000000"), 1700000000)

    def test_parse_token_expires_at_iso_z(self) -> None:
        ts = PriceService.parse_tradingview_token_expires_at("2024-01-15T12:00:00Z")
        self.assertIsNotNone(ts)
        self.assertGreater(ts, 1_700_000_000)

    def test_mask_token_for_ui(self) -> None:
        self.assertEqual(PriceService.mask_token("short"), "***")
        self.assertEqual(PriceService.mask_token("12345678901"), "123456...8901")

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

