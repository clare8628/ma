import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lrs import indicators


class TestSMA(unittest.TestCase):
    def test_basic(self):
        vals = [1, 2, 3, 4, 5]
        out = indicators.sma(vals, 3)
        self.assertIsNone(out[0])
        self.assertIsNone(out[1])
        self.assertAlmostEqual(out[2], 2.0)
        self.assertAlmostEqual(out[3], 3.0)
        self.assertAlmostEqual(out[4], 4.0)

    def test_insufficient_data(self):
        out = indicators.sma([1, 2], 5)
        self.assertEqual(out, [None, None])


class TestEMA(unittest.TestCase):
    def test_seed_is_sma(self):
        vals = [1, 2, 3, 4, 5]
        out = indicators.ema(vals, 3)
        self.assertAlmostEqual(out[2], 2.0)  # seed = SMA of first 3
        self.assertIsNotNone(out[3])
        self.assertIsNotNone(out[4])

    def test_known_values(self):
        vals = [22, 23, 24, 25, 26, 27, 28]
        out = indicators.ema(vals, 3)
        # seed = mean(22,23,24) = 23
        self.assertAlmostEqual(out[2], 23.0)
        mult = 2 / 4
        expected_3 = (25 - 23) * mult + 23
        self.assertAlmostEqual(out[3], expected_3)


class TestRSI(unittest.TestCase):
    def test_all_gains_is_100(self):
        vals = [float(i) for i in range(1, 20)]  # strictly increasing
        out = indicators.rsi(vals, 14)
        self.assertAlmostEqual(out[14], 100.0)

    def test_all_losses_is_0(self):
        vals = [float(i) for i in range(20, 1, -1)]  # strictly decreasing
        out = indicators.rsi(vals, 14)
        self.assertAlmostEqual(out[14], 0.0)

    def test_insufficient_data_is_none(self):
        vals = [1.0, 2.0, 3.0]
        out = indicators.rsi(vals, 14)
        self.assertTrue(all(v is None for v in out))

    def test_mixed_midrange(self):
        vals = [100, 102, 101, 103, 104, 102, 105, 106, 104, 107, 108, 106, 109, 110, 108]
        out = indicators.rsi(vals, 14)
        self.assertIsNotNone(out[14])
        self.assertTrue(0 <= out[14] <= 100)


if __name__ == "__main__":
    unittest.main()
