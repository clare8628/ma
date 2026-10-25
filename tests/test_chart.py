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

        vix_values = [18.0 + (i * 0.5) for i in range(19)] + [46.5]
        self.ind_with_vix = DailyIndicators(
            dates=dates,
            qqq_close=[400.0 + i for i in range(20)],
            qqq_sma_gate=[380.0 for _ in range(20)],
            tqqq_close=close,
            tqqq_ema_fast=ema_fast,
            tqqq_ema_slow=ema_slow,
            tqqq_ema_chart_short=ema_slow,
            tqqq_sma_chart_long=sma200,
            tqqq_rsi=rsi,
            vix_close=vix_values,
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

    def test_render_price_svg_with_vix_curve(self):
        # 驗證將 VIX 指標曲線加入價格與均線圖中
        svg_html = _render_price_svg(
            self.ind_with_vix,
            window=20,
            long_sma_period=200,
            ema_fast_period=10,
            ema_slow_period=20,
        )
        # 1. 驗證 VIX 專屬圖層與折線
        self.assertIn("vix-line-layer", svg_html)
        # 2. 驗證圖例包含 VIX 恐慌指數與 45 抄底門檻
        self.assertIn("■ VIX 恐慌指數", svg_html)
        self.assertIn("VIX 45 抄底門檻", svg_html)
        # 3. 驗證包含 VIX 45 門檻水平參考虛線
        self.assertIn('stroke="#fda4af"', svg_html)
        # 4. 驗證工具列包含 VIX 顯示切換開關
        self.assertIn("toggleLayer('vix-line', this.checked)", svg_html)
        # 5. 驗證右側 Price Pills 包含最新 VIX 標籤
        self.assertIn("VIX 46.5", svg_html)

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
        self.assertIn("恐慌抄底", block_html)
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

            # 2. 驗證包含 VIX 綜合判斷與分析卡片
            self.assertIn("vix-analysis-card", content)
            self.assertIn("VIX 恐慌指數綜合判斷", content)

            # 3. 驗證「買入與賣出規則」區塊位於「建議動作」與「價格與均線」中間
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
            self.assertIn("全歷史時間軸：", content)
            self.assertIn("自 TQQQ 成立開始", content)

    def test_inception_events_and_scale_layers(self):
        events = load_events("config/events.json")
        # 驗證包含 2010 年 TQQQ 成立重大事件
        inception_events = [e for e in events if "2010" in e.get("date", "")]
        self.assertGreater(len(inception_events), 0)
        self.assertTrue(any("TQQQ" in e.get("title", "") for e in inception_events))

        # 驗證價格圖包含線性與對數座標雙圖層
        svg_html = _render_price_svg(
            self.ind,
            window=20,
            long_sma_period=200,
            ema_fast_period=10,
            ema_slow_period=20,
            events=events,
        )
        self.assertIn('id="plot-linear"', svg_html)
        self.assertIn('id="plot-log"', svg_html)
        self.assertIn('togglePriceScale', svg_html)

    def test_time_range_selector_and_wide_layout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "report.html")
            render_html_report(out_path, self.ind_with_vix, self.rec)
            with open(out_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 驗證時間區間切換按鈕群
            self.assertIn('class="range-toolbar"', content)
            self.assertIn('setChartRange', content)
            self.assertIn('data-range="1m"', content)
            self.assertIn('data-range="3m"', content)
            self.assertIn('data-range="6m"', content)
            self.assertIn('data-range="1y"', content)
            self.assertIn('data-range="2y"', content)
            self.assertIn('data-range="5y"', content)
            self.assertIn('data-range="10y"', content)
            self.assertIn('data-range="all"', content)
            self.assertIn('preset-period-select', content)
            self.assertIn('range-info-badge', content)

            # 驗證嵌入了完整前端資料 JSON (包含 VIX 歷史資料)
            self.assertIn('id="chart-data"', content)
            self.assertIn('"tqqq_close":', content)
            self.assertIn('"vix":', content)
            self.assertIn("'vix-line': true", content)

            # 驗證版面寬度充份利用 (擴充至 1760px)
            self.assertIn('max-width: 1760px', content)

            # 驗證 SVG 畫布寬度拓寬為 1600
            self.assertIn('viewBox="0 0 1600', content)

    def test_crosshair_and_tooltip_interaction(self):
        # 1. 驗證主圖包含十字線、各曲線高亮圓點與提示列
        price_svg = _render_price_svg(
            self.ind_with_vix,
            window=20,
            long_sma_period=200,
            ema_fast_period=10,
            ema_slow_period=20,
        )
        self.assertIn('id="price-crosshair"', price_svg)
        self.assertIn('id="price-crosshair-line"', price_svg)
        self.assertIn('id="price-dot-close"', price_svg)
        self.assertIn('id="price-dot-vix"', price_svg)
        self.assertIn('id="price-hover-bar"', price_svg)
        self.assertIn('price-date-pill', price_svg)

        # 2. 驗證副圖包含 RSI 游標導引線與高亮點
        rsi_svg = _render_rsi_svg(self.ind_with_vix, window=20)
        self.assertIn('id="rsi-crosshair"', rsi_svg)
        self.assertIn('id="rsi-crosshair-line"', rsi_svg)
        self.assertIn('id="rsi-dot"', rsi_svg)
        self.assertIn('rsi-date-pill', rsi_svg)

        # 3. 驗證完整報告包含 Tooltip 容器與前端互動事件引擎
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "report.html")
            render_html_report(out_path, self.ind_with_vix, self.rec)
            with open(out_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn('id="chart-tooltip"', content)
            self.assertIn('class="chart-tooltip"', content)
            self.assertIn('handleChartHover', content)
            self.assertIn('updateCrosshairAndTooltip', content)
            self.assertIn('hideCrosshairs', content)
            self.assertIn('initHoverEvents', content)
            self.assertIn('getVixRegime', content)
            self.assertIn('currentSliceData', content)
            self.assertIn('VIX 恐慌指數', content)
            self.assertIn('平台版本：v1.5.2', content)


if __name__ == "__main__":
    unittest.main()
