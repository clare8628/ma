"""現金 + QQQ + TQQQ 三資產配置層：財富種植園《TQQQ長期持有策略》規則移植。

來源：使用者提供之逐字稿（YouTube《TQQQ 長期持有策略：10年50倍策略詳解》，
頻道「財富種植園」）。核心規則（逐字稿時間戳見 docs/allocation-strategy.md）：

  1. 資金分兩份：10%「底倉」(現金，除非 QQQ 從歷史高點跌破 30% 否則不動用)，
     90%「機動倉」在 QQQ / TQQQ / 現金之間依訊號切換。
  2. 每天只看 QQQ 的三個數據：(a) 收盤價 vs 200日均線（多空分界）、
     (b) 距歷史高點的回落幅度、(c) 收盤價 vs 20日均線及其斜率。
  3. 多頭 (收盤 > 200MA)：回落 <=10% → 機動倉 45%QQQ+45%TQQQ（總倉位對照
     target_weights）；回落 >10% → 轉攻擊模式機動倉全倉TQQQ；若同時出現
     「距高點<=5% + 當日量能>65日均量2倍 + 收黑K」的出貨訊號，機動倉全轉
     QQQ（鎖定獲利、降低曝險）。
  4. 空頭 (收盤 < 200MA)：回落 >30% → 黃金坑，機動倉全倉TQQQ（不計其他訊
     號）；回落介於 bear_defensive_pct~30% 之間 → 半山腰拉扯區，站上20MA
     才進TQQQ，跌破20MA則防守持現金；回落 <bear_defensive_pct → 危險區，
     機動倉全部出清為現金。
  5. 鐵律一「今天賣，明天買」：任何需要調升 TQQQ/QQQ 曝險的訊號，當天只
     執行賣出（降低超配資產，資金暫存現金），隔天訊號若持續才真正買進。
  6. 鐵律二「防假反彈」：若前一天仍處於防守狀態（機動倉TQQQ=0），訊號轉為
     進攻時，必須同時滿足「已防守至少 defensive_min_days 天」且「20日均線
     斜率明確向上」才可轉換，否則忽略訊號、維持防守。

逐字稿未明確量化之參數（20日均線採 SMA 或 EMA、斜率判定天數、10%~30%之間
的分界細節等）已於 docs/allocation-strategy.md 標註為「本專案假設」，可於
config/settings.json 的 allocation 區塊調整，無需更動程式邏輯。

本模組僅輸出建議文字與目標權重，不連接券商、不自動下單。鐵律一/二需要的
「目前機動倉狀態」以 state/wealth_farm_state.json 逐日累進保存（見
position_state.py 的既有模式）。使用者實際持倉比例另存於
state/allocation_snapshot.json，用於與目標權重比對、超過 drift_threshold_pct
即提醒再平衡。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from . import indicators
from .data import PriceBar

ALLOCATION_SNAPSHOT_PATH = "state/allocation_snapshot.json"
WEALTH_FARM_STATE_PATH = "state/wealth_farm_state.json"

_DEFAULT_TARGET_WEIGHTS = {"cash": 10, "qqq": 45, "tqqq": 45}
_DEFAULT_THRESHOLDS = {
    "bull_dip_pct": 10,
    "bear_defensive_pct": 10,
    "golden_pit_pct": 30,
    "near_ath_pct": 5,
    "vol_spike_multiple": 2,
    "vol_avg_window": 65,
    "ma20_window": 20,
    "ma20_slope_lookback": 3,
    "defensive_min_days": 2,
}
_DEFAULT_DRIFT_THRESHOLD_PCT = 5

REGIME_LABEL = {
    "NORMAL": "多頭常態：機動倉45%QQQ+45%TQQQ",
    "AGGRESSIVE_DIP_BUY": "多頭回落>10%：機動倉全倉TQQQ（攻擊模式）",
    "TOP_SIGNAL_DERISK": "出貨訊號（近高點+爆量+收黑K）：機動倉全轉QQQ鎖定獲利",
    "GOLDEN_PIT": "空頭回落>30%：黃金坑，機動倉全倉TQQQ",
    "TUG_OF_WAR_BUY": "空頭半山腰拉扯：站上20日均線，機動倉轉TQQQ",
    "TUG_OF_WAR_DEFENSIVE": "空頭半山腰拉扯：跌破20日均線，機動倉防守持現金",
    "DEFENSIVE_CASH": "空頭剛跌破200日均線：機動倉全數出清為現金",
    "INSUFFICIENT_DATA": "資料不足（200日均線尚未成形），維持基礎目標權重",
}


def _cfg(settings: Optional[dict]) -> dict:
    return (settings or {}).get("allocation", {})


def _target_weights(settings: Optional[dict]) -> Dict[str, float]:
    w = _cfg(settings).get("target_weights", _DEFAULT_TARGET_WEIGHTS)
    return {"cash": float(w["cash"]), "qqq": float(w["qqq"]), "tqqq": float(w["tqqq"])}


def _thresholds(settings: Optional[dict]) -> Dict[str, float]:
    th = dict(_DEFAULT_THRESHOLDS)
    th.update(_cfg(settings).get("thresholds", {}))
    return th


def _rolling_avg_skip_none(values: List[Optional[float]], window: int) -> List[Optional[float]]:
    """窗口內若有任何 None（缺量資料），該日輸出 None，而不視為 0 拉低均量。"""
    out: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if i < window - 1:
            continue
        chunk = values[i - window + 1:i + 1]
        if any(v is None for v in chunk):
            continue
        out[i] = sum(chunk) / window
    return out


@dataclass
class RegimeDay:
    date: str
    regime: str
    weights: Dict[str, float]
    drawdown_pct: Optional[float]
    is_bull: Optional[bool]
    near_ath: bool
    vol_spike: bool
    red_candle: bool
    ma20_slope_up: Optional[bool]


def compute_regime_series(qqq_bars: List[PriceBar], settings: Optional[dict]) -> List[RegimeDay]:
    """依逐字稿規則，為每一天計算當日「原始訊號」機動倉目標權重（尚未套用鐵律一/二）。"""
    base = _target_weights(settings)
    th = _thresholds(settings)
    sma200_window = (settings or {}).get("moving_averages", {}).get("benchmark_gate_sma", 200)

    dates = [b.date for b in qqq_bars]
    close = [b.close for b in qqq_bars]
    open_ = [b.open for b in qqq_bars]
    volume = [b.volume for b in qqq_bars]

    sma200 = indicators.sma(close, sma200_window)
    ma20 = indicators.sma(close, int(th["ma20_window"]))
    vol_avg = _rolling_avg_skip_none(volume, int(th["vol_avg_window"]))

    ath = []
    running_max = None
    for c in close:
        running_max = c if running_max is None else max(running_max, c)
        ath.append(running_max)

    active_total = base["qqq"] + base["tqqq"]
    all_cash = {"cash": 100.0, "qqq": 0.0, "tqqq": 0.0}
    all_tqqq = {"cash": base["cash"], "qqq": 0.0, "tqqq": active_total}
    all_qqq = {"cash": base["cash"], "qqq": active_total, "tqqq": 0.0}

    out: List[RegimeDay] = []
    lookback = int(th["ma20_slope_lookback"])
    for i in range(len(close)):
        slope_up = None
        if ma20[i] is not None and i - lookback >= 0 and ma20[i - lookback] is not None:
            slope_up = ma20[i] > ma20[i - lookback]

        near_ath = ath[i] > 0 and (ath[i] - close[i]) / ath[i] * 100 <= th["near_ath_pct"]
        vol_spike = (
            volume[i] is not None and vol_avg[i] is not None and vol_avg[i] > 0
            and volume[i] > th["vol_spike_multiple"] * vol_avg[i]
        )
        red_candle = open_[i] is not None and close[i] < open_[i]

        if sma200[i] is None or ath[i] is None or ath[i] <= 0:
            out.append(RegimeDay(dates[i], "INSUFFICIENT_DATA", dict(base), None, None,
                                  near_ath, vol_spike, red_candle, slope_up))
            continue

        drawdown = (ath[i] - close[i]) / ath[i] * 100
        is_bull = close[i] > sma200[i]

        if is_bull:
            if near_ath and vol_spike and red_candle:
                regime, weights = "TOP_SIGNAL_DERISK", all_qqq
            elif drawdown > th["bull_dip_pct"]:
                regime, weights = "AGGRESSIVE_DIP_BUY", all_tqqq
            else:
                regime, weights = "NORMAL", dict(base)
        else:
            if drawdown > th["golden_pit_pct"]:
                regime, weights = "GOLDEN_PIT", all_tqqq
            elif drawdown >= th["bear_defensive_pct"]:
                if ma20[i] is not None and close[i] > ma20[i]:
                    regime, weights = "TUG_OF_WAR_BUY", all_tqqq
                else:
                    regime, weights = "TUG_OF_WAR_DEFENSIVE", all_cash
            else:
                regime, weights = "DEFENSIVE_CASH", all_cash

        out.append(RegimeDay(dates[i], regime, dict(weights), drawdown, is_bull,
                              near_ath, vol_spike, red_candle, slope_up))
    return out


@dataclass
class WealthFarmState:
    effective_weights: Dict[str, float]
    pending_target: Optional[Dict[str, float]]
    defensive_streak_days: int
    last_date: Optional[str]


def _load_state(path: str, base_weights: Dict[str, float]) -> WealthFarmState:
    if not os.path.exists(path):
        return WealthFarmState(dict(base_weights), None, 0, None)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return WealthFarmState(
            effective_weights=data["effective_weights"],
            pending_target=data.get("pending_target"),
            defensive_streak_days=data.get("defensive_streak_days", 0),
            last_date=data.get("last_date"),
        )
    except (json.JSONDecodeError, OSError, KeyError):
        return WealthFarmState(dict(base_weights), None, 0, None)


def _save_state(state: WealthFarmState, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(state), f, ensure_ascii=False, indent=2)


def _apply_day(state: WealthFarmState, day: RegimeDay, defensive_min_days: int) -> "tuple[WealthFarmState, str, Optional[str]]":
    """套用鐵律一（今天賣明天買）與鐵律二（防假反彈）於單一交易日，回傳新狀態。"""
    target = dict(day.weights)
    regime_label = day.regime
    note = None

    was_defensive = state.effective_weights["tqqq"] <= 0.0
    wants_defensive = target["tqqq"] <= 0.0

    if was_defensive and not wants_defensive:
        enough_days = state.defensive_streak_days >= defensive_min_days
        slope_ok = bool(day.ma20_slope_up)
        if not (enough_days and slope_ok):
            target = dict(state.effective_weights)
            regime_label = f"{day.regime}（鐵律二忽略：防守未滿{defensive_min_days}天或20日均線未轉上）"
            note = "鐵律二觸發：訊號轉攻擊但防守天數或均線斜率未達標，本日維持防守，忽略進場訊號。"

    new_effective: Dict[str, float] = {}
    for asset in ("qqq", "tqqq"):
        if target[asset] <= state.effective_weights[asset] + 1e-9:
            new_effective[asset] = target[asset]
        else:
            prior_pending = (state.pending_target or {}).get(asset, state.effective_weights[asset])
            if prior_pending >= target[asset] - 1e-9:
                new_effective[asset] = target[asset]
            else:
                new_effective[asset] = state.effective_weights[asset]
                if note is None:
                    note = "鐵律一觸發：訊號要求加碼，今日維持原倉位、資金暫存現金，待訊號延續至隔日才會買進。"
    new_effective["cash"] = 100.0 - new_effective["qqq"] - new_effective["tqqq"]

    new_streak = (state.defensive_streak_days + 1) if (was_defensive and new_effective["tqqq"] <= 0.0) else (
        1 if new_effective["tqqq"] <= 0.0 else 0
    )

    new_state = WealthFarmState(
        effective_weights=new_effective,
        pending_target=target,
        defensive_streak_days=new_streak,
        last_date=day.date,
    )
    return new_state, regime_label, note


def run_wealth_farm(
    qqq_bars: List[PriceBar],
    settings: Optional[dict],
    state_path: str = WEALTH_FARM_STATE_PATH,
) -> Dict[str, Any]:
    """逐日重放鐵律一/二狀態機至最新一天，回傳今日的目標配置與理由。"""
    base = _target_weights(settings)
    th = _thresholds(settings)
    series = compute_regime_series(qqq_bars, settings)

    state = _load_state(state_path, base)
    start_index = 0
    if state.last_date is not None:
        for idx, day in enumerate(series):
            if day.date > state.last_date:
                start_index = idx
                break
        else:
            start_index = len(series)

    regime_label = REGIME_LABEL.get(series[-1].regime, series[-1].regime) if series else "無資料"
    note = None
    for day in series[start_index:]:
        state, regime_label, note = _apply_day(state, day, int(th["defensive_min_days"]))

    _save_state(state, state_path)

    today = series[-1] if series else None
    return {
        "date": today.date if today else None,
        "regime": today.regime if today else None,
        "regime_label": regime_label,
        "raw_target": today.weights if today else dict(base),
        "effective_weights": state.effective_weights,
        "defensive_streak_days": state.defensive_streak_days,
        "note": note,
        "drawdown_pct": today.drawdown_pct if today else None,
        "is_bull": today.is_bull if today else None,
    }


@dataclass
class AllocationCheck:
    regime: Optional[str]
    regime_label: str
    target: Dict[str, float]
    actual: Optional[Dict[str, float]]
    drift: Optional[Dict[str, float]]
    needs_rebalance: bool
    note: Optional[str]
    message: str


def _read_snapshot(path: str) -> Optional[Dict[str, float]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if any(data.get(k) is None for k in ("cash_pct", "qqq_pct", "tqqq_pct")):
        return None
    return {
        "cash": float(data["cash_pct"]),
        "qqq": float(data["qqq_pct"]),
        "tqqq": float(data["tqqq_pct"]),
    }


def _fmt(weights: Dict[str, float]) -> str:
    return f"現金{weights['cash']:.1f}%/QQQ{weights['qqq']:.1f}%/TQQQ{weights['tqqq']:.1f}%"


def check_allocation(
    qqq_bars: List[PriceBar],
    settings: Optional[dict],
    snapshot_path: str = ALLOCATION_SNAPSHOT_PATH,
    state_path: str = WEALTH_FARM_STATE_PATH,
) -> AllocationCheck:
    """執行財富種植園規則引擎並比對實際持倉快照，超過偏離門檻則提醒再平衡。"""
    result = run_wealth_farm(qqq_bars, settings, state_path=state_path)
    target = result["effective_weights"]
    actual = _read_snapshot(snapshot_path)
    threshold = _cfg(settings).get("drift_threshold_pct", _DEFAULT_DRIFT_THRESHOLD_PCT)

    regime_line = f"[{result['date']}] {result['regime_label']}。"
    if result["note"]:
        regime_line += f" {result['note']}"

    if actual is None:
        message = (
            f"{regime_line} 目標配置：{_fmt(target)}。尚無實際持倉快照，"
            f"請於 {snapshot_path} 填入 cash_pct/qqq_pct/tqqq_pct 以啟用偏離度檢核。"
        )
        return AllocationCheck(
            regime=result["regime"], regime_label=result["regime_label"], target=target,
            actual=None, drift=None, needs_rebalance=False, note=result["note"], message=message,
        )

    drift = {k: actual[k] - target[k] for k in target}
    needs = any(abs(v) > threshold for v in drift.values())

    if needs:
        parts = [
            f"{k.upper()}{'超重' if v > 0 else '低配'}{abs(v):.1f}%"
            for k, v in drift.items()
            if abs(v) > threshold
        ]
        message = (
            f"{regime_line} 再平衡警示（門檻 ±{threshold}%）：{'; '.join(parts)}。"
            f"目標 {_fmt(target)}，實際 {_fmt(actual)}，建議賣出超重資產、買入低配資產拉回目標權重。"
        )
    else:
        message = f"{regime_line} 配置正常：實際 {_fmt(actual)} 與目標 {_fmt(target)} 偏離在 ±{threshold}% 門檻內，無需再平衡。"

    return AllocationCheck(
        regime=result["regime"], regime_label=result["regime_label"], target=target,
        actual=actual, drift=drift, needs_rebalance=needs, note=result["note"], message=message,
    )
