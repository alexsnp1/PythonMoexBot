from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import List, Optional

from model.spread_rule import SpreadRule


class DatabaseService:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    formula TEXT NOT NULL,
                    upper_bound REAL NOT NULL,
                    lower_bound REAL NOT NULL,
                    last_alert_time INTEGER
                )
                """
            )
            conn.commit()

    def add_rule(self, user_id: int, formula: str, upper: float, lower: float) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO rules (user_id, formula, upper_bound, lower_bound, last_alert_time)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (user_id, formula, upper, lower),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_rules(self, user_id: int) -> List[SpreadRule]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, formula, upper_bound, lower_bound, last_alert_time
                FROM rules
                WHERE user_id = ?
                ORDER BY id ASC
                """,
                (user_id,),
            ).fetchall()
        return [self._row_to_rule(row) for row in rows]

    def list_all_rules(self) -> List[SpreadRule]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, formula, upper_bound, lower_bound, last_alert_time
                FROM rules
                ORDER BY id ASC
                """
            ).fetchall()
        return [self._row_to_rule(row) for row in rows]

    def remove_rule(self, user_id: int, rule_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM rules WHERE id = ? AND user_id = ?",
                (rule_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def update_rule_bounds(self, user_id: int, rule_id: int, upper: float, lower: float) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE rules
                SET upper_bound = ?, lower_bound = ?
                WHERE id = ? AND user_id = ?
                """,
                (upper, lower, rule_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def update_last_alert_time(self, rule_id: int, timestamp: Optional[int] = None) -> None:
        if timestamp is None:
            timestamp = int(time.time())
        with self._connect() as conn:
            conn.execute(
                "UPDATE rules SET last_alert_time = ? WHERE id = ?",
                (timestamp, rule_id),
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_rule(row: sqlite3.Row) -> SpreadRule:
        return SpreadRule(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            formula=str(row["formula"]),
            upper_bound=float(row["upper_bound"]),
            lower_bound=float(row["lower_bound"]),
            last_alert_time=int(row["last_alert_time"]) if row["last_alert_time"] is not None else None,
        )

