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
        """Append a rule; returns its 1-based position (same as len(rules) after insert)."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rules (user_id, formula, upper_bound, lower_bound, last_alert_time)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (user_id, formula, upper, lower),
            )
            conn.commit()
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM rules WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return int(row["c"])

    def list_rules(self, user_id: int) -> List[SpreadRule]:
        # ORDER BY id defines insertion order (append semantics). For explicit reordering,
        # consider adding a position column later.
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
        return [self._row_to_rule(row, rule_number=i) for i, row in enumerate(rows, start=1)]

    def list_all_rules(self) -> List[SpreadRule]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, formula, upper_bound, lower_bound, last_alert_time
                FROM rules
                ORDER BY user_id ASC, id ASC
                """
            ).fetchall()
        rules: List[SpreadRule] = []
        per_user: dict[int, int] = {}
        for row in rows:
            uid = int(row["user_id"])
            per_user[uid] = per_user.get(uid, 0) + 1
            rules.append(self._row_to_rule(row, rule_number=per_user[uid]))
        return rules

    def list_distinct_user_ids_with_rules(self) -> List[int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT user_id
                FROM rules
                ORDER BY user_id ASC
                """
            ).fetchall()
        return [int(r["user_id"]) for r in rows]

    def remove_rule(self, user_id: int, rule_number: int) -> bool:
        """rule_number is 1-based index in the user's ordered list (like list index + 1)."""
        rules = self.list_rules(user_id)
        if rule_number < 1 or rule_number > len(rules):
            return False
        row_id = rules[rule_number - 1].id
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM rules WHERE id = ? AND user_id = ?",
                (row_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def update_rule_bounds(self, user_id: int, rule_number: int, upper: float, lower: float) -> bool:
        rules = self.list_rules(user_id)
        if rule_number < 1 or rule_number > len(rules):
            return False
        row_id = rules[rule_number - 1].id
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE rules
                SET upper_bound = ?, lower_bound = ?
                WHERE id = ? AND user_id = ?
                """,
                (upper, lower, row_id, user_id),
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
    def _row_to_rule(row: sqlite3.Row, rule_number: int = 0) -> SpreadRule:
        return SpreadRule(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            formula=str(row["formula"]),
            upper_bound=float(row["upper_bound"]),
            lower_bound=float(row["lower_bound"]),
            last_alert_time=int(row["last_alert_time"]) if row["last_alert_time"] is not None else None,
            rule_number=rule_number,
        )

