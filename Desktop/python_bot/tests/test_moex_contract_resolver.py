import json
import tempfile
import unittest
from pathlib import Path

from price.moex_contract_resolver import MoexContractResolver


class MoexContractResolverTests(unittest.TestCase):
    def test_resolves_continuous_symbol_using_config(self) -> None:
        payload = {
            "aliases": {"SV1!": "SV"},
            "rollover": {
                "SV": [
                    {"contract": "SVH2020", "rollover_at": "2020-03-20"},
                    {"contract": "SVM2035", "rollover_at": "2035-06-20"},
                ]
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "contracts.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            resolver = MoexContractResolver(config_path=str(config_path))
            resolved = resolver.resolve_symbol("RUS:SV1!")
            self.assertEqual(resolved, "RUS:SVM2035")
            resolved_plain = resolver.resolve_symbol("SV1!")
            self.assertEqual(resolved_plain, "SVM2035")

    def test_keeps_symbol_when_no_mapping(self) -> None:
        resolver = MoexContractResolver(config_path=None)
        self.assertEqual(resolver.resolve_symbol("RUS:UNKNOWN1!"), "RUS:UNKNOWN1!")


if __name__ == "__main__":
    unittest.main()

