import os
import unittest
from lrs import cape


class TestCape(unittest.TestCase):
    def test_evaluate_cape_valuation(self):
        v1 = cape.evaluate_cape_valuation(40.71)
        self.assertEqual(v1["tier"], "極端高估")
        self.assertEqual(v1["badge_color"], "#dc2626")

        v2 = cape.evaluate_cape_valuation(32.5)
        self.assertEqual(v2["tier"], "偏高（熱絡）")

        v3 = cape.evaluate_cape_valuation(22.0)
        self.assertEqual(v3["tier"], "合理健全")

        v4 = cape.evaluate_cape_valuation(15.0)
        self.assertEqual(v4["tier"], "便宜（高安全邊際）")

    def test_get_cape_statistics(self):
        data = cape.get_cape_statistics()
        self.assertIn("latest", data)
        self.assertIn("history", data)
        self.assertIn("source_url", data)
        self.assertEqual(data["source_url"], "https://www.wantgoo.com/global/macroeconomics/cape")
        self.assertGreater(len(data["history"]), 0)
        self.assertGreater(data["latest"]["cape"], 0)


if __name__ == "__main__":
    unittest.main()

