"""核心訊號邏輯：整合 QQQ（大盤環境過濾）與 TQQQ（執行觸發）指標，
透過 rules_engine 產生「買進/賣出/減碼/止盈/持有」建議，並列出符合的規則。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import indicators
from .data import PriceBar
from .rules_engine import Rule, evaluate
from .position_state import PositionState

# 多個動作同時成立時的最終建議優先順序（數字越小越先採用）
ACTION_PRIORITY = {
    "FORCE_EXIT": 0,
    "SELL_ALL": 1,
    "REDUCE_50": 2,
    "TRIM_PARTIAL": 3,
    "SKIP_ENTRY_OVERBOUGHT": 4,
    "BUY": 5,
}

ACTION_LABEL = {
    "FORCE_EXIT": "強制清倉（大盤空頭禁令）",
    "SELL_ALL": "全數賣出（死亡交叉）",
    "REDUCE_50": "減碼50%／移至成本線停損",
    "TRIM_PARTIAL": "分批止盈（賣出1/3~1/2）",
    "SKIP_ENTRY_OVERBOUGHT": "放棄進場（RSI過熱）",
    "BUY": "買進（黃金交叉）",
    "HOLD": "持有／觀望（無訊號）",
}


@dataclass
class DailyIndicators:
    dates: List[str]
    qqq_close: List[float]
    qqq_sma_gate: List[Optional[float]]
    tqqq_close: List[float]
    tqqq_ema_fast: List[Optional[float]]
    tqqq_ema_slow: List[Optional[float]]
    tqqq_ema_chart_short: List[Optional[float]]
    tqqq_sma_chart_long: List[Optional[float]]
    tqqq_rsi: List[Optional[float]]


@dataclass
class Recommendation:
    date: str
    action: str
    action_label: str
    matched_rules: List[Dict[str, str]]
    context: Dict[str, Any]


def align_by_date(qqq_bars: List[PriceBar], tqqq_bars: List[PriceBar]):
    qqq_map = {b.date: b.close for b in qqq_bars}
    tqqq_map = {b.date: b.close for b in tqqq_bars}
    common_dates = sorted(set(qqq_map) & set(tqqq_map))
    qqq_close = [qqq_map[d] for d in common_dates]
    tqqq_close = [tqqq_map[d] for d in common_dates]
    return common_dates, qqq_close, tqqq_close


def compute_indicators(settings: dict, qqq_bars: List[PriceBar], tqqq_bars: List[PriceBar]) -> DailyIndicators:
    dates, qqq_close, tqqq_close = align_by_date(qqq_bars, tqqq_bars)
    ma = settings["moving_averages"]
    rsi_cfg = settings["rsi"]

    qqq_sma_gate = indicators.sma(qqq_close, ma["benchmark_gate_sma"])
    tqqq_ema_fast = indicators.ema(tqqq_close, ma["target_fast_ema"])
    tqqq_ema_slow = indicators.ema(tqqq_close, ma["target_slow_ema"])
    tqqq_ema_chart_short = indicators.ema(tqqq_close, ma["chart_short_ema"])
    tqqq_sma_chart_long = indicators.sma(tqqq_close, ma["chart_long_sma"])
    tqqq_rsi = indicators.rsi(tqqq_close, rsi_cfg["period"])

    return DailyIndicators(
        dates=dates,
        qqq_close=qqq_close,
        qqq_sma_gate=qqq_sma_gate,
        tqqq_close=tqqq_close,
        tqqq_ema_fast=tqqq_ema_fast,
        tqqq_ema_slow=tqqq_ema_slow,
        tqqq_ema_chart_short=tqqq_ema_chart_short,
        tqqq_sma_chart_long=tqqq_sma_chart_long,
        tqqq_rsi=tqqq_rsi,
    )


def build_context(ind: DailyIndicators, i: int, position: PositionState) -> Dict[str, Any]:
    def prev(series):
        return series[i - 1] if i > 0 else None

    ema_slow = ind.tqqq_ema_slow[i]
    distance_pct = None
    if ema_slow is not None and ema_slow != 0:
        distance_pct = (ind.tqqq_close[i] - ema_slow) / ema_slow * 100

    return {
        "qqq": {
            "close": ind.qqq_close[i],
            "sma200": ind.qqq_sma_gate[i],
            "sma200_prev": prev(ind.qqq_sma_gate),
        },
        "tqqq": {
            "close": ind.tqqq_close[i],
            "ema_fast": ind.tqqq_ema_fast[i],
            "ema_fast_prev": prev(ind.tqqq_ema_fast),
            "ema_slow": ema_slow,
            "ema_slow_prev": prev(ind.tqqq_ema_slow),
            "rsi": ind.tqqq_rsi[i],
            "ema_slow_distance_pct": distance_pct,
        },
        "position": {
            "holding": position.holding,
        },
    }


def recommend(
    rules: List[Rule],
    ind: DailyIndicators,
    position: PositionState,
    as_of_index: int = -1,
) -> Recommendation:
    i = as_of_index if as_of_index >= 0 else len(ind.dates) - 1
    context = build_context(ind, i, position)
    matched = evaluate(rules, context)

    if matched:
        top_action = min(matched, key=lambda r: ACTION_PRIORITY.get(r.action, 99)).action
    else:
        top_action = "HOLD"

    return Recommendation(
        date=ind.dates[i],
        action=top_action,
        action_label=ACTION_LABEL.get(top_action, top_action),
        matched_rules=[{"id": r.id, "name": r.name, "message": r.message} for r in matched],
        context=context,
    )
