#!/usr/bin/env python3
"""TQQQ 槓桿輪換策略 (LRS) CLI 入口。

用法：
  python3 main.py                          # 抓取最新資料並輸出建議 + 圖表報告
  python3 main.py --qqq-csv a.csv --tqqq-csv b.csv   # 離線模式，用自備 CSV(date,close)
  python3 main.py --mark-filled --price 85.3         # 標記已進場建倉
  python3 main.py --mark-closed                      # 標記已出場清倉
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from lrs import data, position_state, rebalance, signals  # noqa: E402
from lrs.chart import render_html_report  # noqa: E402
from lrs.rules_engine import load_rules  # noqa: E402

SETTINGS_PATH = "config/settings.json"
RULES_PATH = "config/rules.json"
REPORT_PATH = "state/report.html"


def load_settings(path: str = SETTINGS_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_bars(symbol: str, csv_path: str, settings: dict):
    if csv_path:
        return data.load_history_csv(csv_path)
    data_cfg = settings["data"]
    return data.fetch_history(
        symbol,
        range_=data_cfg["history_range"],
        interval=data_cfg["interval"],
        cache_dir=data_cfg["cache_dir"],
        cache_ttl_hours=data_cfg["cache_ttl_hours"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="TQQQ 槓桿輪換策略 (LRS)")
    parser.add_argument("--qqq-csv", default=None, help="離線模式：QQQ 歷史資料 CSV (date,close)")
    parser.add_argument("--tqqq-csv", default=None, help="離線模式：TQQQ 歷史資料 CSV (date,close)")
    parser.add_argument("--output", "-o", default=REPORT_PATH, help=f"HTML 圖表報告輸出路徑 (預設: {REPORT_PATH})")
    parser.add_argument("--no-chart", action="store_true", help="不產生 HTML 圖表報告")
    parser.add_argument("--mark-filled", action="store_true", help="標記已依建議進場建倉")
    parser.add_argument("--mark-closed", action="store_true", help="標記已依建議出場清倉")
    parser.add_argument("--price", type=float, default=None, help="配合 --mark-filled 記錄進場成本價")
    args = parser.parse_args()

    if args.mark_filled or args.mark_closed:
        state = position_state.load()
        if args.mark_filled:
            state.holding = True
            state.entry_date = dt.date.today().isoformat()
            state.entry_price = args.price
        else:
            state.holding = False
            state.entry_date = None
            state.entry_price = None
        position_state.save(state)
        print(f"持倉狀態已更新: holding={state.holding}")
        return 0

    settings = load_settings()
    rules = load_rules(RULES_PATH)
    position = position_state.load()

    qqq_bars = get_bars(settings["benchmark_symbol"], args.qqq_csv, settings)
    tqqq_bars = get_bars(settings["target_symbol"], args.tqqq_csv, settings)

    ind = signals.compute_indicators(settings, qqq_bars, tqqq_bars)
    rec = signals.recommend(rules, ind, position)

    print(f"=== LRS 建議 ({rec.date}) ===")
    print(f"動作: {rec.action_label}")
    print("符合規則:")
    if rec.matched_rules:
        for r in rec.matched_rules:
            print(f"  - [{r['id']}] {r['name']}: {r['message']}")
    else:
        print("  - 無規則觸發，維持觀望")

    rb = rebalance.check_rebalance(settings)
    print("\n=== 年度再平衡檢核 (11/1) ===")
    print(rb.message)

    if not args.no_chart:
        render_html_report(args.output, ind, rec)
        print(f"\n圖表報告已輸出: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
