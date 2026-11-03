import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lrs.backtest import run_signal_basis_backtest, buy_and_hold_result


def make_dates(n):
    return [f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]


class TestSignalBasisBacktest(unittest.TestCase):
    # RSI entry gate (50~65) depends on recent up/down mix; disable it here (0~100) so these
    # tests isolate crossover + SMA-gate behavior, which is what "signal basis" actually changes.
    NO_RSI_GATE = dict(rsi_entry_min=-1, rsi_entry_max=200)

    def test_golden_cross_entry_and_death_cross_exit_tqqq_basis(self):
        n = 60
        dates = make_dates(n)
        qqq_close = [100 + i for i in range(n)]  # always above its SMA gate once warmed up
        # TQQQ: flat then a clean up-leg (golden cross) then a down-leg (death cross)
        tqqq_close = [50.0] * 25 + [50 + i for i in range(20)] + [69 - i for i in range(15)]

        r = run_signal_basis_backtest(dates, qqq_close, tqqq_close, basis="tqqq",
                                       gate_sma_period=20, fast_ema_period=3, slow_ema_period=6,
                                       **self.NO_RSI_GATE)
        self.assertGreaterEqual(r.trade_count, 1)
        self.assertIsNotNone(r.win_rate_pct)
        self.assertIsNotNone(r.total_return_pct)

    def test_tqqq_basis_whipsaws_more_on_choppy_price_than_qqq_basis(self):
        n = 60
        dates = make_dates(n)
        # QQQ has one clean golden cross/death cross cycle; TQQQ chops around a flat line
        # with no real trend, which is exactly the kind of leveraged-ETF noise the "basis"
        # question is about. A TQQQ-basis run should whipsaw on that noise far more than a
        # QQQ-basis run (which ignores TQQQ's own wiggle and only reacts to QQQ's trend).
        qqq_close = [100.0] * 25 + [100 + i for i in range(20)] + [119 - i for i in range(15)]
        tqqq_close = [50 + (i % 3) * 0.1 for i in range(n)]

        r_qqq = run_signal_basis_backtest(dates, qqq_close, tqqq_close, basis="qqq",
                                           gate_sma_period=20, fast_ema_period=3, slow_ema_period=6,
                                           **self.NO_RSI_GATE)
        r_tqqq = run_signal_basis_backtest(dates, qqq_close, tqqq_close, basis="tqqq",
                                            gate_sma_period=20, fast_ema_period=3, slow_ema_period=6,
                                            **self.NO_RSI_GATE)
        self.assertGreaterEqual(r_tqqq.trade_count, r_qqq.trade_count)
        self.assertGreater(r_tqqq.trade_count, 0)

    def test_win_rate_and_total_return_are_consistent(self):
        n = 40
        dates = make_dates(n)
        qqq_close = [100 + i * 0.1 for i in range(n)]
        tqqq_close = [10 + i * 0.2 for i in range(n)]
        r = run_signal_basis_backtest(dates, qqq_close, tqqq_close, basis="tqqq",
                                       gate_sma_period=10, fast_ema_period=3, slow_ema_period=6)
        if r.trade_count:
            self.assertEqual(r.win_count, sum(1 for t in r.trades if t.is_win))
            self.assertAlmostEqual(
                r.win_rate_pct, r.win_count / r.trade_count * 100, places=6
            )

    def test_buy_and_hold_matches_full_period_return(self):
        dates = make_dates(10)
        tqqq_close = [10, 11, 12, 11, 13, 14, 15, 14, 16, 20]
        r = buy_and_hold_result(dates, tqqq_close)
        self.assertEqual(r.trade_count, 1)
        self.assertAlmostEqual(r.total_return_pct, (20 / 10 - 1) * 100, places=6)
        self.assertAlmostEqual(r.equity_curve[-1], 2.0, places=6)


if __name__ == "__main__":
    unittest.main()
