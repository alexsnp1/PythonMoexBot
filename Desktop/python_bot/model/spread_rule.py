from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class SpreadRule:
    id: int
    user_id: int
    formula: str
    upper_bound: float
    lower_bound: float
    last_alert_time: Optional[int] = None

