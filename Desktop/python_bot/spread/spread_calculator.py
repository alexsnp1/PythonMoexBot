from __future__ import annotations

from typing import Dict

from parser.formula_parser import FormulaParser


class SpreadCalculator:
    def __init__(self, parser: FormulaParser | None = None) -> None:
        self._parser = parser or FormulaParser()

    def evaluate(self, formula: str, prices: Dict[str, float]) -> float:
        return self._parser.calculate(formula=formula, prices=prices)

