import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lrs import chart, signals
from lrs.chart import (
    VERSION,
    load_events,
    _render_price_svg,
    _render_rsi_svg,
    _render_rules_block,
    render_html_report,
)
from lrs.rules_engine import load_rules
from lrs.signals import DailyIndicators, Recommendation


class TestChart(unittest.TestCase):
    def setUp(self):
        # 建立簡易假資料
        dates = [f"2026-01-{i:02d}" for i in range(1, 21)]
        close = [50.0 + i * 0.5 for i in range(20)]
        sma200 = [45.0 for _ in range(20)]
        ema_fast = [48.0 + i * 0.4 for i in range(20)]
        ema_slow = [47.0 + i * 0.3 for i in range(20)]
        rsi = [55.0 + (i % 5) for i in range(20)]

        self.ind = DailyIndicators(
            dates=dates,
            qqq_close=[400.0 + i for i in range(20)],
            qqq_sma_gate=[380.0 for _ in range(20)],
            tqqq_close=close,
            tqqq_ema_fast=ema_fast,
            tqqq_ema_slow=ema_slow,
            tqqq_ema_chart_short=ema_slow,
            tqqq_sma_chart_long=sma200,
            tqqq_rsi=rsi,
        )

        self.rec = Recommendation(
            date="2026-01-20",
            action="HOLD",
            action_label="持有／觀望（無訊號）",
            matched_rules=[],
            context={
                "tqqq": {"close": close[-1], "ema_slow_distance_pct": 2.5, "rsi": rsi[-1]},
                "qqq": {"close": 419.0, "sma200": 380.0},
                "position": {"holding": False},
            },
        )

    def test_load_events(self):
        events = load_events("config/events.json")
        self.assertIsInstance(events, list)
        self.assertGreater(len(events), 0)
        self.assertIn("date", events[0])
        self.assertIn("title", events[0])

    def test_render_price_svg_features(self):
        events = [{"date": "2026-01-10", "title": "測試金融事件", "description": "重大經濟決策"}]
        svg_html = _render_price_svg(
            self.ind,
            window=20,
            long_sma_period=200,
            ema_fast_period=10,
            ema_slow_period=20,
            events=events,
        )
        # 驗證右側延伸與標籤
        self.assertIn("測試金融事件", svg_html)
        self.assertIn("financial-event", svg_html)
        self.assertIn("TQQQ", svg_html)
        self.assertIn("EMA10", svg_html)
        self.assertIn("EMA20", svg_html)
        self.assertIn("SMA200", svg_html)
        # 驗證右側最新數值標籤與雙側刻度
        self.assertIn("viewBox", svg_html)

    def test_render_rsi_svg(self):
        rsi_svg = _render_rsi_svg(self.ind, window=20)
        self.assertIn("TQQQ RSI(14)", rsi_svg)
        self.assertIn("70 過熱止盈", rsi_svg)
        self.assertIn("45 避險", rsi_svg)
        self.assertIn("RSI", rsi_svg)

    def test_render_rules_block(self):
        rules = load_rules("config/rules.json")
        block_html = _render_rules_block(rules, self.rec)
        self.assertIn("trading-rules-block", block_html)
        self.assertIn("策略執行規範：目前遵守之「買入與賣出規則」", block_html)
        self.assertIn("大盤空頭禁令", block_html)
        self.assertIn("進場(黃金交叉+RSI確認)", block_html)
        self.assertIn("11/1 資產再平衡", block_html)

    def test_render_html_report_order_and_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "report.html")
            render_html_report(out_path, self.ind, self.rec)
            self.assertTrue(os.path.exists(out_path))

            with open(out_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 1. 驗證版本與時間戳記
            self.assertIn(f"平台版本：{VERSION}", content)
            self.assertIn("產出時間戳記：", content)

            # 2. 驗證「買入與賣出規則」區塊位於「建議動作」與「價格與均線」中間
            action_pos = content.find("建議動作：")
            rules_pos = content.find("id=\"trading-rules-block\"")
            chart_pos = content.find("價格與均線（長期SMA框架")

            self.assertNotEqual(action_pos, -1, "必須包含建議動作區塊")
            self.assertNotEqual(rules_pos, -1, "必須包含買入與賣出規則區塊")
            self.assertNotEqual(chart_pos, -1, "必須包含價格與均線區塊")

            self.assertLess(action_pos, rules_pos, "建議動作區塊必須在規則區塊之前")
            self.assertLess(rules_pos, chart_pos, "規則區塊必須在價格與均線區塊之前")

            # 3. 驗證包含重大金融事件
            self.assertIn("重大金融事件", content)


if __name__ == "__main__":
    unittest.main()
