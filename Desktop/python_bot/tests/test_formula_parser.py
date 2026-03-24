import unittest

from parser.formula_parser import FormulaParser


class FormulaParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = FormulaParser()

    def test_extract_symbols(self) -> None:
        formula = "RUS:SV1!/TVC:SILVER*1000"
        symbols = self.parser.extract_symbols(formula)
        self.assertEqual(symbols, {"SV1!", "SILVER"})

    def test_calculate(self) -> None:
        formula = "RUS:SI2!/RUS:CR2!/FX:USDCNH*1000"
        prices = {"SI2!": 100.0, "CR2!": 80.0, "USDCNH": 7.0}
        value = self.parser.calculate(formula, prices)
        self.assertAlmostEqual(value, 178.5714285714, places=6)


if __name__ == "__main__":
    unittest.main()

