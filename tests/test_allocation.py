import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lrs import allocation

SETTINGS = {
    "allocation": {
        "target_weights": {"cash": 10, "qqq": 45, "tqqq": 45},
        "drift_threshold_pct": 5,
    }
}


class TestTargetWeightsForAction(unittest.TestCase):
    def test_buy_keeps_base_weights(self):
        w = allocation.target_weights_for_action("BUY", SETTINGS)
        self.assertEqual(w, {"cash": 10.0, "qqq": 45.0, "tqqq": 45.0})

    def test_hold_keeps_base_weights(self):
        w = allocation.target_weights_for_action("HOLD", SETTINGS)
        self.assertEqual(w, {"cash": 10.0, "qqq": 45.0, "tqqq": 45.0})

    def test_sell_all_goes_full_cash(self):
        w = allocation.target_weights_for_action("SELL_ALL", SETTINGS)
        self.assertEqual(w, {"cash": 100.0, "qqq": 0.0, "tqqq": 0.0})

    def test_force_exit_goes_full_cash(self):
        w = allocation.target_weights_for_action("FORCE_EXIT", SETTINGS)
        self.assertEqual(w, {"cash": 100.0, "qqq": 0.0, "tqqq": 0.0})

    def test_reduce_50_halves_tqqq(self):
        w = allocation.target_weights_for_action("REDUCE_50", SETTINGS)
        self.assertAlmostEqual(w["tqqq"], 22.5)
        self.assertAlmostEqual(w["qqq"], 45.0)
        self.assertAlmostEqual(w["cash"], 32.5)
        self.assertAlmostEqual(sum(w.values()), 100.0)

    def test_trim_partial_keeps_60pct_tqqq(self):
        w = allocation.target_weights_for_action("TRIM_PARTIAL", SETTINGS)
        self.assertAlmostEqual(w["tqqq"], 27.0)
        self.assertAlmostEqual(w["qqq"], 45.0)
        self.assertAlmostEqual(w["cash"], 28.0)
        self.assertAlmostEqual(sum(w.values()), 100.0)

    def test_missing_allocation_cfg_uses_defaults(self):
        w = allocation.target_weights_for_action("BUY", {})
        self.assertEqual(w, {"cash": 10.0, "qqq": 45.0, "tqqq": 45.0})


class TestCheckAllocation(unittest.TestCase):
    def _write_snapshot(self, data):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, tmp)
        tmp.close()
        return tmp.name

    def test_no_snapshot_file_no_rebalance_needed(self):
        result = allocation.check_allocation("BUY", SETTINGS, snapshot_path="state/__does_not_exist__.json")
        self.assertIsNone(result.actual)
        self.assertFalse(result.needs_rebalance)
        self.assertIn("尚無實際持倉快照", result.message)

    def test_snapshot_with_null_fields_treated_as_missing(self):
        path = self._write_snapshot({"cash_pct": None, "qqq_pct": None, "tqqq_pct": None})
        result = allocation.check_allocation("BUY", SETTINGS, snapshot_path=path)
        self.assertIsNone(result.actual)

    def test_within_threshold_no_rebalance(self):
        path = self._write_snapshot({"cash_pct": 12, "qqq_pct": 44, "tqqq_pct": 44})
        result = allocation.check_allocation("BUY", SETTINGS, snapshot_path=path)
        self.assertFalse(result.needs_rebalance)
        self.assertIn("配置正常", result.message)

    def test_drift_beyond_threshold_triggers_rebalance(self):
        path = self._write_snapshot({"cash_pct": 5, "qqq_pct": 35, "tqqq_pct": 60})
        result = allocation.check_allocation("BUY", SETTINGS, snapshot_path=path)
        self.assertTrue(result.needs_rebalance)
        self.assertIn("再平衡警示", result.message)
        self.assertAlmostEqual(result.drift["tqqq"], 15.0)

    def test_sell_all_action_compares_against_full_cash_target(self):
        path = self._write_snapshot({"cash_pct": 50, "qqq_pct": 25, "tqqq_pct": 25})
        result = allocation.check_allocation("SELL_ALL", SETTINGS, snapshot_path=path)
        self.assertEqual(result.target, {"cash": 100.0, "qqq": 0.0, "tqqq": 0.0})
        self.assertTrue(result.needs_rebalance)


if __name__ == "__main__":
    unittest.main()
