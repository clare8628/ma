import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lrs.rules_engine import Rule, evaluate


def make_context(qqq_close, qqq_sma, tqqq_rsi, ema_fast, ema_fast_prev, ema_slow, ema_slow_prev, holding=False):
    return {
        "qqq": {"close": qqq_close, "sma200": qqq_sma},
        "tqqq": {
            "rsi": tqqq_rsi,
            "ema_fast": ema_fast, "ema_fast_prev": ema_fast_prev,
            "ema_slow": ema_slow, "ema_slow_prev": ema_slow_prev,
            "ema_slow_distance_pct": 0,
        },
        "position": {"holding": holding},
    }


class TestConditions(unittest.TestCase):
    def test_simple_gt(self):
        rule = Rule("r1", "n", "BUY", 1, "AND",
                    [{"left": "qqq.close", "op": ">", "right": "qqq.sma200"}], "msg")
        ctx = make_context(110, 100, 50, 10, 9, 11, 11)
        self.assertEqual(evaluate([rule], ctx), [rule])

        ctx2 = make_context(90, 100, 50, 10, 9, 11, 11)
        self.assertEqual(evaluate([rule], ctx2), [])

    def test_crosses_above(self):
        rule = Rule("r2", "n", "BUY", 1, "AND",
                    [{"left": "tqqq.ema_fast", "op": "crosses_above", "right": "tqqq.ema_slow"}], "msg")
        # fast was below slow, now above -> golden cross
        ctx = make_context(100, 90, 55, 21, 19, 20, 20)
        self.assertEqual(evaluate([rule], ctx), [rule])

        # fast already above slow before -> not a fresh cross
        ctx2 = make_context(100, 90, 55, 22, 21, 20, 19)
        self.assertEqual(evaluate([rule], ctx2), [])

    def test_crosses_below(self):
        rule = Rule("r3", "n", "SELL_ALL", 1, "AND",
                    [{"left": "tqqq.ema_fast", "op": "crosses_below", "right": "tqqq.ema_slow"}], "msg")
        ctx = make_context(100, 90, 40, 19, 21, 20, 20)
        self.assertEqual(evaluate([rule], ctx), [rule])

    def test_and_logic_requires_all(self):
        rule = Rule("r4", "n", "BUY", 1, "AND",
                    [
                        {"left": "qqq.close", "op": ">", "right": "qqq.sma200"},
                        {"left": "tqqq.rsi", "op": ">", "right": 50},
                        {"left": "tqqq.rsi", "op": "<", "right": 65},
                    ], "msg")
        ctx_ok = make_context(110, 100, 55, 10, 9, 11, 11)
        self.assertEqual(evaluate([rule], ctx_ok), [rule])

        ctx_overbought = make_context(110, 100, 70, 10, 9, 11, 11)
        self.assertEqual(evaluate([rule], ctx_overbought), [])

    def test_priority_ordering(self):
        r_low = Rule("low", "n", "BUY", 5, "AND", [{"left": "qqq.close", "op": ">", "right": 0}], "m")
        r_high = Rule("high", "n", "FORCE_EXIT", 1, "AND", [{"left": "qqq.close", "op": ">", "right": 0}], "m")
        rules = [r_low, r_high]
        ctx = make_context(1, 0, 50, 10, 9, 11, 11)
        matched = evaluate(rules, ctx)
        self.assertEqual([r.id for r in matched], ["high", "low"])


if __name__ == "__main__":
    unittest.main()
