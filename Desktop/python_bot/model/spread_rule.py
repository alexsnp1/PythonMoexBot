from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class SpreadRule:
    """id is the DB row key only; rule_number is the 1-based position in the user's ordered list."""

    id: int
    user_id: int
    formula: str
    upper_bound: float
    lower_bound: float
    last_alert_time: Optional[int] = None
    rule_number: int = 0

