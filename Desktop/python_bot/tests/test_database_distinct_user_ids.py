import os
import tempfile
import unittest

from db.database_service import DatabaseService


class DistinctUserIdsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._fd, self._path = tempfile.mkstemp(suffix=".sqlite")
        os.close(self._fd)
        self.db = DatabaseService(db_path=self._path)
        self.db.initialize()

    def tearDown(self) -> None:
        os.unlink(self._path)

    def test_list_distinct_user_ids_with_rules(self) -> None:
        self.db.add_rule(user_id=1, formula="RUS:SV1!", upper=10.0, lower=1.0)
        self.db.add_rule(user_id=1, formula="RUS:SV2!", upper=10.0, lower=1.0)
        self.db.add_rule(user_id=2, formula="RUS:SV3!", upper=10.0, lower=1.0)

        ids = self.db.list_distinct_user_ids_with_rules()
        self.assertEqual(ids, [1, 2])


if __name__ == "__main__":
    unittest.main()

