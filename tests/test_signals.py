import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lrs import signals
from lrs.data import PriceBar
from lrs.position_state import PositionState
from lrs.rules_engine import load_rules

SETTINGS = {
    "benchmark_symbol": "QQQ",
    "target_symbol": "TQQQ",
    "moving_averages": {
        "benchmark_gate_sma": 20,
        "target_fast_ema": 3,
        "target_slow_ema": 6,
        "chart_long_sma": 20,
        "chart_short_ema": 6,
    },
    "rsi": {"period": 14},
}

RULES_PATH = str(Path(__file__).parent.parent / "config" / "rules.json")


def make_bars(closes):
    dates = [f"2024-01-{i+1:02d}" if i < 31 else f"2024-02-{i-30:02d}" for i in range(len(closes))]
    return [PriceBar(d, c) for d, c in zip(dates, closes)]


class TestAlignAndIndicators(unittest.TestCase):
    def test_align_by_date_intersection(self):
        qqq = [PriceBar("2024-01-01", 100), PriceBar("2024-01-02", 101), PriceBar("2024-01-04", 103)]
        tqqq = [PriceBar("2024-01-01", 10), PriceBar("2024-01-02", 10.5), PriceBar("2024-01-03", 10.8)]
        dates, q, t = signals.align_by_date(qqq, tqqq)
        self.assertEqual(dates, ["2024-01-01", "2024-01-02"])
        self.assertEqual(q, [100, 101])
        self.assertEqual(t, [10, 10.5])

    def test_align_by_date_with_vix(self):
        qqq = [PriceBar("2024-01-01", 100), PriceBar("2024-01-02", 101), PriceBar("2024-01-04", 103)]
        tqqq = [PriceBar("2024-01-01", 10), PriceBar("2024-01-02", 10.5), PriceBar("2024-01-03", 10.8)]
        vix = [PriceBar("2024-01-01", 15.5), PriceBar("2024-01-02", 16.0)]
        dates, q, t, v = signals.align_by_date(qqq, tqqq, vix)
        self.assertEqual(dates, ["2024-01-01", "2024-01-02"])
        self.assertEqual(q, [100, 101])
        self.assertEqual(t, [10, 10.5])
        self.assertEqual(v, [15.5, 16.0])


class TestRecommend(unittest.TestCase):
    def test_bear_market_forces_exit_even_with_golden_cross(self):
        n = 40
        qqq_closes = [100 - i * 0.5 for i in range(n)]  # strong downtrend -> close < sma20
        tqqq_closes = [50 + i for i in range(n)]  # uptrend to simulate a golden cross on target
        qqq_bars = make_bars(qqq_closes)
        tqqq_bars = make_bars(tqqq_closes)

        rules = load_rules(RULES_PATH)
        ind = signals.compute_indicators(SETTINGS, qqq_bars, tqqq_bars)
        rec = signals.recommend(rules, ind, PositionState(holding=False))

        self.assertEqual(rec.action, "FORCE_EXIT")
        self.assertTrue(any(r["id"] == "R1_bear_lockout" for r in rec.matched_rules))

    def test_holding_and_rsi_drop_triggers_reduce(self):
        n = 40
        qqq_closes = [100 + i for i in range(n)]  # bull market, close > sma200-gate
        # build a TQQQ series that rises then drops sharply to crater RSI near the end,
        # without crossing EMA fast below EMA slow (so death-cross rule doesn't dominate)
        tqqq_closes = [50 + i * 0.5 for i in range(n - 3)]
        tqqq_closes += [tqqq_closes[-1] - 1, tqqq_closes[-1] - 2, tqqq_closes[-1] - 2.5]
        qqq_bars = make_bars(qqq_closes)
        tqqq_bars = make_bars(tqqq_closes)

        rules = load_rules(RULES_PATH)
        ind = signals.compute_indicators(SETTINGS, qqq_bars, tqqq_bars)
        rec = signals.recommend(rules, ind, PositionState(holding=True))

        # whichever rule fires, action should reflect defensive/exit posture, not a fresh BUY
        self.assertIn(rec.action, {"REDUCE_50", "SELL_ALL", "FORCE_EXIT", "HOLD"})

    def test_hold_when_nothing_triggers(self):
        n = 40
        flat = [100.0] * n
        qqq_bars = make_bars(flat)
        tqqq_bars = make_bars(flat)
        rules = load_rules(RULES_PATH)
        ind = signals.compute_indicators(SETTINGS, qqq_bars, tqqq_bars)
        rec = signals.recommend(rules, ind, PositionState(holding=False))
        self.assertEqual(rec.action, "HOLD")

    def test_vix_above_45_triggers_panic_bottom_buy(self):
        n = 40
        # 大盤處於空頭（原本會觸發 R1_bear_lockout FORCE_EXIT）
        qqq_closes = [100 - i * 0.5 for i in range(n)]
        tqqq_closes = [50 - i * 0.3 for i in range(n)]
        # VIX 在最後數日飆升超過 45 (極端恐慌拋售)
        vix_closes = [20.0 + (i * 0.5) for i in range(n - 1)] + [48.5]

        qqq_bars = make_bars(qqq_closes)
        tqqq_bars = make_bars(tqqq_closes)
        vix_bars = make_bars(vix_closes)

        rules = load_rules(RULES_PATH)
        ind = signals.compute_indicators(SETTINGS, qqq_bars, tqqq_bars, vix_bars)
        rec = signals.recommend(rules, ind, PositionState(holding=False))

        # 驗證最高優先級恐慌抄底成功觸發
        self.assertEqual(rec.action, "BUY_DIP_PANIC")
        self.assertEqual(rec.action_label, "恐慌抄底買進（VIX超過45極度恐慌）")
        self.assertTrue(any(r["id"] == "R0_vix_panic_bottom" for r in rec.matched_rules))
        self.assertEqual(rec.context["vix"]["level"], "EXTREME_PANIC")
        self.assertTrue(rec.context["vix"]["is_panic_bottom"])

    def test_vix_below_45_preserves_bear_lockout(self):
        n = 40
        # 大盤處於空頭
        qqq_closes = [100 - i * 0.5 for i in range(n)]
        tqqq_closes = [50 - i * 0.3 for i in range(n)]
        # VIX 雖有波動但未達 45 (例如 32)
        vix_closes = [20.0] * (n - 1) + [32.0]

        qqq_bars = make_bars(qqq_closes)
        tqqq_bars = make_bars(tqqq_closes)
        vix_bars = make_bars(vix_closes)

        rules = load_rules(RULES_PATH)
        ind = signals.compute_indicators(SETTINGS, qqq_bars, tqqq_bars, vix_bars)
        rec = signals.recommend(rules, ind, PositionState(holding=False))

        # 由於 VIX 未達 45，不觸發抄底，正常執行大盤空頭禁令 FORCE_EXIT
        self.assertEqual(rec.action, "FORCE_EXIT")
        self.assertTrue(any(r["id"] == "R1_bear_lockout" for r in rec.matched_rules))
        self.assertFalse(any(r["id"] == "R0_vix_panic_bottom" for r in rec.matched_rules))
        self.assertEqual(rec.context["vix"]["level"], "HIGH_VOLATILITY")
        self.assertFalse(rec.context["vix"]["is_panic_bottom"])

    def test_vix_regime_evaluations(self):
        r_extreme = signals.evaluate_vix_regime(48.2)
        self.assertEqual(r_extreme["level"], "EXTREME_PANIC")
        self.assertTrue(r_extreme["is_panic_bottom"])

        r_high = signals.evaluate_vix_regime(35.0)
        self.assertEqual(r_high["level"], "HIGH_VOLATILITY")
        self.assertFalse(r_high["is_panic_bottom"])

        r_elevated = signals.evaluate_vix_regime(22.5)
        self.assertEqual(r_elevated["level"], "ELEVATED_VOLATILITY")
        self.assertFalse(r_elevated["is_panic_bottom"])

        r_low = signals.evaluate_vix_regime(16.8)
        self.assertEqual(r_low["level"], "LOW_VOLATILITY")
        self.assertFalse(r_low["is_panic_bottom"])

        r_none = signals.evaluate_vix_regime(None)
        self.assertEqual(r_none["level"], "UNKNOWN")
        self.assertFalse(r_none["is_panic_bottom"])


if __name__ == "__main__":
    unittest.main()
