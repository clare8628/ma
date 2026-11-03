#!/usr/bin/env python3
"""研究腳本：比較「TQQQ 自身均線/RSI」vs.「QQQ 均線/RSI、買賣 TQQQ」兩種訊號基礎的歷史表現。

用法：
  python3 scripts/compare_signal_basis.py              # 全历史 + 分段報表
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lrs.backtest import run_signal_basis_backtest, buy_and_hold_result  # noqa: E402

CACHE_DIR = Path(__file__).parent.parent / "state" / "cache"


def load_closes(symbol: str):
    with open(CACHE_DIR / f"{symbol}.json", "r", encoding="utf-8") as f:
        bars = json.load(f)["bars"]
    return {d: c for d, c in bars}


def align(qqq_map, tqqq_map, start=None, end=None):
    dates = sorted(set(qqq_map) & set(tqqq_map))
    if start:
        dates = [d for d in dates if d >= start]
    if end:
        dates = [d for d in dates if d <= end]
    return dates, [qqq_map[d] for d in dates], [tqqq_map[d] for d in dates]


def fmt(v, suffix="%"):
    return "N/A" if v is None else f"{v:.1f}{suffix}"


def print_report(label, dates, qqq_close, tqqq_close):
    print(f"\n### {label} ({dates[0]} ~ {dates[-1]}, {len(dates)} 個交易日)")
    bh = buy_and_hold_result(dates, tqqq_close)
    print(f"- Buy&Hold TQQQ: 總回報 {fmt(bh.total_return_pct)} | MaxDD {fmt(bh.max_drawdown_pct)}")
    for basis, name in [("tqqq", "A.TQQQ自身均線(現行)"), ("qqq", "B.QQQ均線/買賣TQQQ")]:
        r = run_signal_basis_backtest(dates, qqq_close, tqqq_close, basis=basis)
        print(
            f"- {name}: 交易{r.trade_count}次 | 勝率{fmt(r.win_rate_pct)} | "
            f"均勝{fmt(r.avg_win_pct)} | 均虧{fmt(r.avg_loss_pct)} | "
            f"總回報{fmt(r.total_return_pct)} | MaxDD{fmt(r.max_drawdown_pct)} | "
            f"持倉時間{fmt(r.time_in_market_pct)}"
        )


def main():
    qqq_map = load_closes("QQQ")
    tqqq_map = load_closes("TQQQ")

    periods = [
        ("全歷史 (TQQQ 上市以來)", None, None),
        ("2010-2021 多頭循環", "2010-01-01", "2021-12-31"),
        ("2022 熊市", "2022-01-01", "2022-12-31"),
        ("2023-2026 復甦+近期", "2023-01-01", None),
    ]
    for label, start, end in periods:
        dates, qqq_close, tqqq_close = align(qqq_map, tqqq_map, start, end)
        if len(dates) < 150:
            continue
        print_report(label, dates, qqq_close, tqqq_close)


if __name__ == "__main__":
    main()
