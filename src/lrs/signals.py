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
# VIX > 45 極度恐慌逆勢抄底具備歷史級勝率，優先權高於常規空頭禁令
ACTION_PRIORITY = {
    "BUY_DIP_PANIC": 0,
    "FORCE_EXIT": 1,
    "SELL_ALL": 2,
    "REDUCE_50": 3,
    "TRIM_PARTIAL": 4,
    "SKIP_ENTRY_OVERBOUGHT": 5,
    "BUY": 6,
}

ACTION_LABEL = {
    "BUY_DIP_PANIC": "恐慌抄底買進（VIX超過45極度恐慌）",
    "FORCE_EXIT": "強制清倉（大盤空頭禁令）",
    "SELL_ALL": "全數賣出（死亡交叉）",
    "REDUCE_50": "減碼50%／移至成本線停損",
    "TRIM_PARTIAL": "分批止盈（賣出1/3~1/2）",
    "SKIP_ENTRY_OVERBOUGHT": "放棄進場（RSI過熱）",
    "BUY": "買進（黃金交叉）",
    "HOLD": "持有／觀望（無訊號）",
}


def evaluate_vix_regime(vix_val: Optional[float]) -> Dict[str, Any]:
    """對 VIX 恐慌指數進行綜合市場情緒分級與抄底勝率評估。"""
    if vix_val is None:
        return {
            "level": "UNKNOWN",
            "label": "無資料",
            "badge_color": "#64748b",
            "is_panic_bottom": False,
            "description": "目前無 VIX 恐慌指數數據",
            "guidance": "維持常規均線與動能指標判斷。",
        }
    if vix_val >= 45.0:
        return {
            "level": "EXTREME_PANIC",
            "label": "極度恐慌（≥45 歷史抄底機會）",
            "badge_color": "#dc2626",
            "is_panic_bottom": True,
            "description": "VIX 超過 45，市場處於歷史級極度恐慌（如 2008 金融海嘯、2020 疫情熔斷、2024 日圓平倉黑天鵝）。歷史統計顯示極度恐慌拋售後進場抄底勝率極高，為非對稱高勝率機會。",
            "guidance": "啟動恐慌抄底機制 (BUY_DIP_PANIC)，建議分批逆勢建倉／抄底買進。",
        }
    elif vix_val >= 30.0:
        return {
            "level": "HIGH_VOLATILITY",
            "label": "恐慌警戒（30~45）",
            "badge_color": "#f59e0b",
            "is_panic_bottom": False,
            "description": "市場恐慌情緒顯著升溫，價格劇烈震盪，波動溢價攀升。",
            "guidance": "密切關注恐慌是否衝破 45 抄底門檻或見頂回落，嚴格執行風控。",
        }
    elif vix_val >= 20.0:
        return {
            "level": "ELEVATED_VOLATILITY",
            "label": "中度波動（20~30）",
            "badge_color": "#64748b",
            "is_panic_bottom": False,
            "description": "市場波動處於正常回檔或洗盤區間，市場情緒適度分歧。",
            "guidance": "遵循標準 QQQ 200SMA 框架與 TQQQ 均線交叉及 RSI 訊號操作。",
        }
    else:
        return {
            "level": "LOW_VOLATILITY",
            "label": "低波動平穩（<20）",
            "badge_color": "#16a34a",
            "is_panic_bottom": False,
            "description": "市場情緒穩定偏樂觀，波動率偏低，多頭趨勢延續性強。",
            "guidance": "多頭環境穩定，標準黃金交叉進場訊號可靠度高。",
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
    vix_close: Optional[List[Optional[float]]] = None


@dataclass
class Recommendation:
    date: str
    action: str
    action_label: str
    matched_rules: List[Dict[str, str]]
    context: Dict[str, Any]


def align_by_date(
    qqq_bars: List[PriceBar],
    tqqq_bars: List[PriceBar],
    vix_bars: Optional[List[PriceBar]] = None,
):
    qqq_map = {b.date: b.close for b in qqq_bars}
    tqqq_map = {b.date: b.close for b in tqqq_bars}
    common_dates = sorted(set(qqq_map) & set(tqqq_map))
    qqq_close = [qqq_map[d] for d in common_dates]
    tqqq_close = [tqqq_map[d] for d in common_dates]
    if vix_bars is None:
        return common_dates, qqq_close, tqqq_close
    vix_map = {b.date: b.close for b in vix_bars}
    vix_close: List[Optional[float]] = [vix_map.get(d) for d in common_dates]
    return common_dates, qqq_close, tqqq_close, vix_close


def compute_indicators(
    settings: dict,
    qqq_bars: List[PriceBar],
    tqqq_bars: List[PriceBar],
    vix_bars: Optional[List[PriceBar]] = None,
) -> DailyIndicators:
    if vix_bars is not None:
        dates, qqq_close, tqqq_close, vix_close = align_by_date(qqq_bars, tqqq_bars, vix_bars)
    else:
        dates, qqq_close, tqqq_close = align_by_date(qqq_bars, tqqq_bars)
        vix_close = [None] * len(dates)

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
        vix_close=vix_close,
    )


def build_context(ind: DailyIndicators, i: int, position: PositionState) -> Dict[str, Any]:
    def prev(series):
        if series is None:
            return None
        return series[i - 1] if i > 0 else None

    ema_slow = ind.tqqq_ema_slow[i]
    distance_pct = None
    if ema_slow is not None and ema_slow != 0:
        distance_pct = (ind.tqqq_close[i] - ema_slow) / ema_slow * 100

    vix_val = ind.vix_close[i] if ind.vix_close is not None else None
    vix_prev = prev(ind.vix_close) if ind.vix_close is not None else None
    vix_regime = evaluate_vix_regime(vix_val)

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
        "vix": {
            "close": vix_val,
            "close_prev": vix_prev,
            "level": vix_regime["level"],
            "label": vix_regime["label"],
            "badge_color": vix_regime["badge_color"],
            "is_panic_bottom": vix_regime["is_panic_bottom"],
            "description": vix_regime["description"],
            "guidance": vix_regime["guidance"],
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
