import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lrs import allocation
from lrs.data import PriceBar

SETTINGS = {
    "allocation": {
        "target_weights": {"cash": 10, "qqq": 45, "tqqq": 45},
        "thresholds": {
            "bull_dip_pct": 10,
            "bear_defensive_pct": 10,
            "golden_pit_pct": 30,
            "near_ath_pct": 5,
            "vol_spike_multiple": 2,
            "vol_avg_window": 65,
            "ma20_window": 20,
            "ma20_slope_lookback": 3,
            "defensive_min_days": 2,
        },
        "drift_threshold_pct": 5,
    },
    "moving_averages": {"benchmark_gate_sma": 200},
}


def _bars(closes, opens=None, volumes=None):
    opens = opens if opens is not None else list(closes)
    volumes = volumes if volumes is not None else [1_000_000.0] * len(closes)
    return [
        PriceBar(f"D{i:05d}", c, open=o, volume=v)
        for i, (c, o, v) in enumerate(zip(closes, opens, volumes))
    ]


class TestComputeRegimeSeries(unittest.TestCase):
    def test_insufficient_data_before_200_days(self):
        closes = [100.0] * 150
        series = allocation.compute_regime_series(_bars(closes), SETTINGS)
        self.assertEqual(series[-1].regime, "INSUFFICIENT_DATA")
        self.assertEqual(series[-1].weights, {"cash": 10.0, "qqq": 45.0, "tqqq": 45.0})

    def test_normal_regime_bull_small_drawdown(self):
        closes = [150.0] * 200 + [151.0]
        series = allocation.compute_regime_series(_bars(closes), SETTINGS)
        day = series[-1]
        self.assertEqual(day.regime, "NORMAL")
        self.assertEqual(day.weights, {"cash": 10.0, "qqq": 45.0, "tqqq": 45.0})
        self.assertTrue(day.is_bull)

    def test_aggressive_dip_buy_bull_large_drawdown(self):
        up = [50 + i * (100 / 199) for i in range(200)]
        down = [150 - i * (50 / 59) for i in range(1, 60)]
        closes = up + down
        series = allocation.compute_regime_series(_bars(closes), SETTINGS)
        day = series[220]
        self.assertEqual(day.regime, "AGGRESSIVE_DIP_BUY")
        self.assertTrue(day.is_bull)
        self.assertGreater(day.drawdown_pct, 10)
        self.assertEqual(day.weights, {"cash": 10.0, "qqq": 0.0, "tqqq": 90.0})

    def test_top_signal_derisk_near_high_volume_spike_red_candle(self):
        up = [50 + i * (100 / 199) for i in range(200)]
        closes = up + [146.0]
        opens = up + [150.0]
        volumes = [1_000_000.0] * 200 + [5_000_000.0]
        series = allocation.compute_regime_series(_bars(closes, opens, volumes), SETTINGS)
        day = series[-1]
        self.assertEqual(day.regime, "TOP_SIGNAL_DERISK")
        self.assertTrue(day.near_ath)
        self.assertTrue(day.vol_spike)
        self.assertTrue(day.red_candle)
        self.assertEqual(day.weights, {"cash": 10.0, "qqq": 90.0, "tqqq": 0.0})

    def test_golden_pit_large_bear_drawdown(self):
        closes = [150.0] * 200 + [95.0]
        series = allocation.compute_regime_series(_bars(closes), SETTINGS)
        day = series[-1]
        self.assertEqual(day.regime, "GOLDEN_PIT")
        self.assertFalse(day.is_bull)
        self.assertGreater(day.drawdown_pct, 30)
        self.assertEqual(day.weights, {"cash": 10.0, "qqq": 0.0, "tqqq": 90.0})

    def test_tug_of_war_buy_above_ma20(self):
        closes = [150.0] * 200 + [110.0] * 25 + [112.0]
        series = allocation.compute_regime_series(_bars(closes), SETTINGS)
        day = series[-1]
        self.assertEqual(day.regime, "TUG_OF_WAR_BUY")
        self.assertFalse(day.is_bull)
        self.assertEqual(day.weights, {"cash": 10.0, "qqq": 0.0, "tqqq": 90.0})

    def test_tug_of_war_defensive_below_ma20(self):
        closes = [150.0] * 200 + [110.0] * 25 + [108.0]
        series = allocation.compute_regime_series(_bars(closes), SETTINGS)
        day = series[-1]
        self.assertEqual(day.regime, "TUG_OF_WAR_DEFENSIVE")
        self.assertFalse(day.is_bull)
        self.assertEqual(day.weights, {"cash": 100.0, "qqq": 0.0, "tqqq": 0.0})

    def test_defensive_cash_small_bear_drawdown(self):
        closes = [150.0] * 200 + [145.0]
        series = allocation.compute_regime_series(_bars(closes), SETTINGS)
        day = series[-1]
        self.assertEqual(day.regime, "DEFENSIVE_CASH")
        self.assertFalse(day.is_bull)
        self.assertLess(day.drawdown_pct, 10)
        self.assertEqual(day.weights, {"cash": 100.0, "qqq": 0.0, "tqqq": 0.0})


class TestApplyDayIronRules(unittest.TestCase):
    def _day(self, regime, weights, ma20_slope_up=True):
        return allocation.RegimeDay(
            date="D99999", regime=regime, weights=weights, drawdown_pct=0.0,
            is_bull=True, near_ath=False, vol_spike=False, red_candle=False,
            ma20_slope_up=ma20_slope_up,
        )

    def test_iron_rule1_sell_today_buy_tomorrow(self):
        state = allocation.WealthFarmState(
            effective_weights={"cash": 10.0, "qqq": 45.0, "tqqq": 45.0},
            pending_target={"cash": 10.0, "qqq": 45.0, "tqqq": 45.0},
            defensive_streak_days=0, last_date="D00199",
        )
        day = self._day("AGGRESSIVE_DIP_BUY", {"cash": 10.0, "qqq": 0.0, "tqqq": 90.0})

        state, label, note = allocation._apply_day(state, day, defensive_min_days=2)
        self.assertEqual(state.effective_weights, {"cash": 55.0, "qqq": 0.0, "tqqq": 45.0})
        self.assertIn("鐵律一", note)

        state, label, note = allocation._apply_day(state, day, defensive_min_days=2)
        self.assertEqual(state.effective_weights, {"cash": 10.0, "qqq": 0.0, "tqqq": 90.0})

    def test_iron_rule2_blocks_reentry_before_min_defensive_days(self):
        state = allocation.WealthFarmState(
            effective_weights={"cash": 100.0, "qqq": 0.0, "tqqq": 0.0},
            pending_target={"cash": 100.0, "qqq": 0.0, "tqqq": 0.0},
            defensive_streak_days=1, last_date="D00199",
        )
        day = self._day("TUG_OF_WAR_BUY", {"cash": 10.0, "qqq": 0.0, "tqqq": 90.0}, ma20_slope_up=True)

        state, label, note = allocation._apply_day(state, day, defensive_min_days=2)
        self.assertEqual(state.effective_weights, {"cash": 100.0, "qqq": 0.0, "tqqq": 0.0})
        self.assertIn("鐵律二忽略", label)
        self.assertIn("鐵律二", note)

    def test_iron_rule2_blocks_reentry_when_ma20_slope_not_up(self):
        state = allocation.WealthFarmState(
            effective_weights={"cash": 100.0, "qqq": 0.0, "tqqq": 0.0},
            pending_target={"cash": 100.0, "qqq": 0.0, "tqqq": 0.0},
            defensive_streak_days=5, last_date="D00199",
        )
        day = self._day("TUG_OF_WAR_BUY", {"cash": 10.0, "qqq": 0.0, "tqqq": 90.0}, ma20_slope_up=False)

        state, label, note = allocation._apply_day(state, day, defensive_min_days=2)
        self.assertEqual(state.effective_weights, {"cash": 100.0, "qqq": 0.0, "tqqq": 0.0})
        self.assertIn("鐵律二忽略", label)

    def test_iron_rule2_allows_reentry_after_min_days_with_slope_up_but_still_delayed_by_rule1(self):
        state = allocation.WealthFarmState(
            effective_weights={"cash": 100.0, "qqq": 0.0, "tqqq": 0.0},
            pending_target={"cash": 100.0, "qqq": 0.0, "tqqq": 0.0},
            defensive_streak_days=2, last_date="D00199",
        )
        day = self._day("TUG_OF_WAR_BUY", {"cash": 10.0, "qqq": 0.0, "tqqq": 90.0}, ma20_slope_up=True)

        state, label, note = allocation._apply_day(state, day, defensive_min_days=2)
        self.assertNotIn("忽略", label)
        # 鐵律一：訊號被接受，但買進動作仍延後一天
        self.assertEqual(state.effective_weights, {"cash": 100.0, "qqq": 0.0, "tqqq": 0.0})
        self.assertIn("鐵律一", note)

        state, label, note = allocation._apply_day(state, day, defensive_min_days=2)
        self.assertEqual(state.effective_weights, {"cash": 10.0, "qqq": 0.0, "tqqq": 90.0})


class TestCheckAllocation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = os.path.join(self.tmpdir.name, "wealth_farm_state.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_snapshot(self, data):
        path = os.path.join(self.tmpdir.name, "snapshot.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def test_no_snapshot_file_no_rebalance_needed(self):
        bars = _bars([150.0] * 200 + [151.0] * 5)
        result = allocation.check_allocation(
            bars, SETTINGS,
            snapshot_path=os.path.join(self.tmpdir.name, "__does_not_exist__.json"),
            state_path=self.state_path,
        )
        self.assertIsNone(result.actual)
        self.assertFalse(result.needs_rebalance)
        self.assertIn("尚無實際持倉快照", result.message)
        self.assertEqual(result.target, {"cash": 10.0, "qqq": 45.0, "tqqq": 45.0})

    def test_drift_beyond_threshold_triggers_rebalance(self):
        bars = _bars([150.0] * 200 + [151.0] * 5)
        snap = self._write_snapshot({"cash_pct": 5, "qqq_pct": 35, "tqqq_pct": 60})
        result = allocation.check_allocation(bars, SETTINGS, snapshot_path=snap, state_path=self.state_path)
        self.assertTrue(result.needs_rebalance)
        self.assertIn("再平衡警示", result.message)
        self.assertAlmostEqual(result.drift["tqqq"], 15.0)

    def test_within_threshold_no_rebalance(self):
        bars = _bars([150.0] * 200 + [151.0] * 5)
        snap = self._write_snapshot({"cash_pct": 12, "qqq_pct": 44, "tqqq_pct": 44})
        result = allocation.check_allocation(bars, SETTINGS, snapshot_path=snap, state_path=self.state_path)
        self.assertFalse(result.needs_rebalance)
        self.assertIn("配置正常", result.message)

    def test_state_persists_and_replays_across_runs(self):
        up = [50 + i * (100 / 199) for i in range(200)]
        down = [150 - i * (50 / 59) for i in range(1, 60)]
        closes = up + down

        bars_day1 = _bars(closes[:200])  # index199 -> NORMAL
        result1 = allocation.check_allocation(
            bars_day1, SETTINGS,
            snapshot_path=os.path.join(self.tmpdir.name, "__none__.json"),
            state_path=self.state_path,
        )
        self.assertEqual(result1.target, {"cash": 10.0, "qqq": 45.0, "tqqq": 45.0})

        bars_day2 = _bars(closes[:220])  # replays index200..219, ends AGGRESSIVE_DIP_BUY
        result2 = allocation.check_allocation(
            bars_day2, SETTINGS,
            snapshot_path=os.path.join(self.tmpdir.name, "__none__.json"),
            state_path=self.state_path,
        )
        self.assertEqual(result2.target, {"cash": 10.0, "qqq": 0.0, "tqqq": 90.0})


if __name__ == "__main__":
    unittest.main()
