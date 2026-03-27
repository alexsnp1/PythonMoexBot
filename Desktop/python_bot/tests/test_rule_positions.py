import os
import tempfile
import unittest

from db.database_service import DatabaseService


class RulePositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._fd, path = tempfile.mkstemp(suffix=".sqlite")
        os.close(self._fd)
        self._path = path
        self.db = DatabaseService(db_path=path)
        self.db.initialize()

    def tearDown(self) -> None:
        os.unlink(self._path)

    def test_list_order_and_delete_by_position(self) -> None:
        uid = 42
        self.assertEqual(self.db.add_rule(uid, "a", 10.0, 1.0), 1)
        self.assertEqual(self.db.add_rule(uid, "b", 10.0, 1.0), 2)
        self.assertEqual(self.db.add_rule(uid, "c", 10.0, 1.0), 3)

        rules = self.db.list_rules(uid)
        self.assertEqual([r.rule_number for r in rules], [1, 2, 3])
        self.assertEqual([r.formula for r in rules], ["a", "b", "c"])

        self.assertTrue(self.db.remove_rule(uid, 2))
        rules = self.db.list_rules(uid)
        self.assertEqual([r.rule_number for r in rules], [1, 2])
        self.assertEqual([r.formula for r in rules], ["a", "c"])

        self.assertEqual(self.db.add_rule(uid, "d", 10.0, 1.0), 3)
        rules = self.db.list_rules(uid)
        self.assertEqual([r.rule_number for r in rules], [1, 2, 3])
        self.assertEqual([r.formula for r in rules], ["a", "c", "d"])

    def test_remove_invalid_index_returns_false(self) -> None:
        self.db.add_rule(1, "only", 1.0, 0.0)
        self.assertFalse(self.db.remove_rule(1, 0))
        self.assertFalse(self.db.remove_rule(1, 2))

    def test_list_all_rules_numbers_per_user(self) -> None:
        self.db.add_rule(1, "u1a", 1.0, 0.0)
        self.db.add_rule(1, "u1b", 1.0, 0.0)
        self.db.add_rule(2, "u2a", 1.0, 0.0)

        all_rules = self.db.list_all_rules()
        by_user: dict[int, list[tuple[int, str]]] = {}
        for r in all_rules:
            by_user.setdefault(r.user_id, []).append((r.rule_number, r.formula))
        self.assertEqual(by_user[1], [(1, "u1a"), (2, "u1b")])
        self.assertEqual(by_user[2], [(1, "u2a")])


if __name__ == "__main__":
    unittest.main()
