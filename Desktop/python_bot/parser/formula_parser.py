from __future__ import annotations

import ast
import re
from typing import Dict, List, Set


SYMBOL_RE = re.compile(r"[A-Za-z0-9]+:[A-Za-z0-9!._-]+")
NORMALIZED_RE = re.compile(r"[A-Za-z0-9!._-]+")


def normalize_symbol(raw_symbol: str) -> str:
    """Convert TradingView-like symbol into internal normalized symbol."""
    if ":" in raw_symbol:
        _, right = raw_symbol.split(":", 1)
        return right
    return raw_symbol


class FormulaParser:
    """Parse and safely evaluate formulas with * and / operators."""

    def extract_symbols(self, formula: str) -> Set[str]:
        """Extract raw symbols and return normalized values."""
        raw_symbols = SYMBOL_RE.findall(formula)
        normalized = {normalize_symbol(sym) for sym in raw_symbols}
        return normalized

    def normalize_formula(self, formula: str) -> str:
        """Replace exchange-prefixed symbols by normalized symbol names."""
        def _replace(match: re.Match[str]) -> str:
            return normalize_symbol(match.group(0))

        return SYMBOL_RE.sub(_replace, formula)

    def prepare_tokens(self, formula: str) -> List[str]:
        normalized = self.normalize_formula(formula)
        return re.findall(r"[A-Za-z0-9!._-]+|[*/()]", normalized)

    def calculate(self, formula: str, prices: Dict[str, float]) -> float:
        normalized_formula = self.normalize_formula(formula)
        safe_expr = self._inject_prices(normalized_formula, prices)
        return self._safe_eval(safe_expr)

    def _inject_prices(self, normalized_formula: str, prices: Dict[str, float]) -> str:
        def _replace(match: re.Match[str]) -> str:
            token = match.group(0)
            if token in prices:
                return str(float(prices[token]))
            if token.replace(".", "", 1).isdigit():
                return token
            raise ValueError(f"Missing price for symbol: {token}")

        return NORMALIZED_RE.sub(_replace, normalized_formula)

    def _safe_eval(self, expression: str) -> float:
        try:
            node = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Invalid formula syntax: {expression}") from exc

        def _eval(expr_node: ast.AST) -> float:
            if isinstance(expr_node, ast.Expression):
                return _eval(expr_node.body)
            if isinstance(expr_node, ast.BinOp):
                left = _eval(expr_node.left)
                right = _eval(expr_node.right)
                if isinstance(expr_node.op, ast.Mult):
                    return left * right
                if isinstance(expr_node.op, ast.Div):
                    if right == 0:
                        raise ValueError("Division by zero in formula")
                    return left / right
                raise ValueError("Only * and / operators are supported")
            if isinstance(expr_node, ast.UnaryOp) and isinstance(expr_node.op, ast.USub):
                return -_eval(expr_node.operand)
            if isinstance(expr_node, ast.Constant) and isinstance(expr_node.value, (int, float)):
                return float(expr_node.value)
            raise ValueError("Unsupported expression in formula")

        return _eval(node)

