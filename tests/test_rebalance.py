import datetime as dt
import io
import sys
import unittest
import urllib.error
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lrs import rebalance

SETTINGS = {
    "rebalance": {
        "month": 11,
        "day": 1,
        "window_days": 3,
        "defensive_target_pct": 50,
        "asset_site_url": "https://mgtasset.clare8628.workers.dev/",
    }
}


class FakeProvider(rebalance.AssetAllocationProvider):
    def __init__(self, pct):
        self.pct = pct

    def fetch_defensive_pct(self):
        return self.pct


class TestRebalanceWindow(unittest.TestCase):
    def test_outside_window(self):
        self.assertFalse(rebalance.is_rebalance_window(dt.date(2024, 6, 15), SETTINGS))

    def test_on_nov_1(self):
        self.assertTrue(rebalance.is_rebalance_window(dt.date(2024, 11, 1), SETTINGS))

    def test_within_window_days(self):
        self.assertTrue(rebalance.is_rebalance_window(dt.date(2024, 11, 3), SETTINGS))

    def test_just_outside_window(self):
        self.assertFalse(rebalance.is_rebalance_window(dt.date(2024, 11, 5), SETTINGS))


class TestCheckRebalance(unittest.TestCase):
    def test_not_in_window_no_manual_check_needed(self):
        result = rebalance.check_rebalance(SETTINGS, today=dt.date(2024, 6, 15))
        self.assertFalse(result.is_rebalance_window)
        self.assertFalse(result.needs_manual_check)

    def test_in_window_without_provider_needs_manual(self):
        result = rebalance.check_rebalance(SETTINGS, today=dt.date(2024, 11, 1))
        self.assertTrue(result.is_rebalance_window)
        self.assertTrue(result.needs_manual_check)

    def test_in_window_with_provider_meets_target(self):
        result = rebalance.check_rebalance(SETTINGS, today=dt.date(2024, 11, 1), provider=FakeProvider(60))
        self.assertFalse(result.needs_manual_check)
        self.assertEqual(result.defensive_pct, 60)
        self.assertIn("通過", result.message)

    def test_in_window_with_provider_below_target(self):
        result = rebalance.check_rebalance(SETTINGS, today=dt.date(2024, 11, 1), provider=FakeProvider(30))
        self.assertIn("警示", result.message)


class TestApiProvider(unittest.TestCase):
    def test_no_token_returns_none(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(rebalance.AssetAllocationProvider().fetch_defensive_pct())

    def test_fetches_pct_with_bearer(self):
        resp = mock.MagicMock()
        resp.__enter__.return_value = io.BytesIO(b'{"defensive_pct": 52.3}')
        with mock.patch.dict("os.environ", {"MGTASSET_API_TOKEN": "t"}, clear=True), \
             mock.patch("urllib.request.urlopen", return_value=resp) as uo:
            self.assertEqual(rebalance.AssetAllocationProvider().fetch_defensive_pct(), 52.3)
            self.assertEqual(uo.call_args[0][0].get_header("Authorization"), "Bearer t")

    def test_http_error_returns_none(self):
        with mock.patch.dict("os.environ", {"MGTASSET_API_TOKEN": "t"}, clear=True), \
             mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("x")):
            self.assertIsNone(rebalance.AssetAllocationProvider().fetch_defensive_pct())


if __name__ == "__main__":
    unittest.main()
