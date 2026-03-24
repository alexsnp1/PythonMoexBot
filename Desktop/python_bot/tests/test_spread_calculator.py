import unittest

from parser.formula_parser import FormulaParser
from spread.spread_calculator import SpreadCalculator


class SpreadCalculatorTests(unittest.TestCase):
    def test_evaluate(self) -> None:
        calc = SpreadCalculator(parser=FormulaParser())
        formula = "RUS:BR1!/VELOCITY:BRENT*1000"
        prices = {"BR1!": 68.0, "BRENT": 67.5}
        value = calc.evaluate(formula, prices)
        self.assertAlmostEqual(value, 1007.407407, places=6)


if __name__ == "__main__":
    unittest.main()

