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
    amounts: Optional[Dict[str, float]] = None


def parse_snapshot_data(data: Any) -> "tuple[Optional[Dict[str, float]], Optional[Dict[str, float]]]":
    """解析快照字典，支援金額（cash/sgov/qqq/tqqq）與百分比（cash_pct/qqq_pct/tqqq_pct）。

    回傳: (weights_pct, amounts_dict)
    """
    if not isinstance(data, dict):
        return None, None

    # 1. 優先檢查金額格式：cash/sgov, qqq, tqqq
    cash_amt = data.get("cash") if data.get("cash") is not None else data.get("sgov")
    if cash_amt is None:
        cash_amt = data.get("cash_amount") if data.get("cash_amount") is not None else data.get("cash_usd")
    qqq_amt = data.get("qqq") if data.get("qqq") is not None else (data.get("qqq_amount") or data.get("qqq_usd"))
    tqqq_amt = data.get("tqqq") if data.get("tqqq") is not None else (data.get("tqqq_amount") or data.get("tqqq_usd"))

    if cash_amt is not None and qqq_amt is not None and tqqq_amt is not None:
        try:
            c = float(cash_amt)
            q = float(qqq_amt)
            t = float(tqqq_amt)
            total = c + q + t
            if total > 0:
                weights = {
                    "cash": round(c / total * 100, 2),
                    "qqq": round(q / total * 100, 2),
                    "tqqq": round(t / total * 100, 2),
                }
                amounts = {"cash": c, "qqq": q, "tqqq": t, "total": total}
                return weights, amounts
        except (ValueError, TypeError):
            pass

    # 2. 檢查百分比格式：cash_pct, qqq_pct, tqqq_pct
    if all(data.get(k) is not None for k in ("cash_pct", "qqq_pct", "tqqq_pct")):
        try:
            return {
                "cash": float(data["cash_pct"]),
                "qqq": float(data["qqq_pct"]),
                "tqqq": float(data["tqqq_pct"]),
            }, None
        except (ValueError, TypeError):
            pass

    return None, None


def _read_snapshot(path: str) -> "tuple[Optional[Dict[str, float]], Optional[Dict[str, float]]]":
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None, None
    return parse_snapshot_data(data)


def save_snapshot_amounts(
    cash: float,
    qqq: float,
    tqqq: float,
    path: str = ALLOCATION_SNAPSHOT_PATH,
) -> Dict[str, Any]:
    """儲存使用者輸入的金額快照至 snapshot 檔案，並自動換算百分比。"""
    total = cash + qqq + tqqq
    if total <= 0:
        raise ValueError("總資產金額必須大於 0")
    data = {
        "_comment": f"持倉金額快照（TQQQ {tqqq:.2f} / QQQ {qqq:.2f} / CASH {cash:.2f} USD，合計 {total:.2f} USD）",
        "cash": round(cash, 2),
        "qqq": round(qqq, 2),
        "tqqq": round(tqqq, 2),
        "total": round(total, 2),
        "cash_pct": round(cash / total * 100, 2),
        "qqq_pct": round(qqq / total * 100, 2),
        "tqqq_pct": round(tqqq / total * 100, 2),
    }
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def _fmt(weights: Dict[str, float]) -> str:
    return f"現金{weights['cash']:.1f}%/QQQ{weights['qqq']:.1f}%/TQQQ{weights['tqqq']:.1f}%"


def check_allocation(
    qqq_bars: List[PriceBar],
    settings: Optional[dict],
    snapshot_path: str = ALLOCATION_SNAPSHOT_PATH,
    state_path: str = WEALTH_FARM_STATE_PATH,
    custom_actual: Optional[Dict[str, float]] = None,
    custom_amounts: Optional[Dict[str, float]] = None,
) -> AllocationCheck:
    """執行財富種植園規則引擎並比對實際持倉快照，超過偏離門檻則提醒再平衡。"""
    result = run_wealth_farm(qqq_bars, settings, state_path=state_path)
    target = result["effective_weights"]
    
    if custom_actual is not None:
        actual = custom_actual
        amounts = custom_amounts
    else:
        actual, amounts = _read_snapshot(snapshot_path)
    threshold = _cfg(settings).get("drift_threshold_pct", _DEFAULT_DRIFT_THRESHOLD_PCT)

    regime_line = f"[{result['date']}] {result['regime_label']}。"
    if result["note"]:
        regime_line += f" {result['note']}"

    if actual is None:
        message = (
            f"{regime_line} 目標配置：{_fmt(target)}。尚無實際持倉快照，"
            f"請於 {snapshot_path} 填入 cash/qqq/tqqq 金額或使用 --set-amounts 啟用偏離度檢核。"
        )
        return AllocationCheck(
            regime=result["regime"], regime_label=result["regime_label"], target=target,
            actual=None, drift=None, needs_rebalance=False, note=result["note"], message=message,
            amounts=None,
        )

    drift = {k: actual[k] - target[k] for k in target}
    needs = any(abs(v) > threshold for v in drift.values())

    amounts_line = ""
    if amounts and amounts.get("total", 0) > 0:
        total = amounts["total"]
        rebal_actions = []
        for asset in ("cash", "qqq", "tqqq"):
            target_usd = total * (target[asset] / 100.0)
            actual_usd = amounts[asset]
            diff_usd = target_usd - actual_usd
            if abs(drift[asset]) > threshold:
                action_str = f"買入 ${diff_usd:.0f}" if diff_usd > 0 else f"賣出 ${abs(diff_usd):.0f}"
                rebal_actions.append(f"{asset.upper()}{action_str}")
        if rebal_actions:
            amounts_line = f" 建議再平衡調整金額：{'; '.join(rebal_actions)}。"

    if needs:
        parts = [
            f"{k.upper()}{'超重' if v > 0 else '低配'}{abs(v):.1f}%"
            for k, v in drift.items()
            if abs(v) > threshold
        ]
        message = (
            f"{regime_line} 再平衡警示（門檻 ±{threshold}%）：{'; '.join(parts)}。"
            f"目標 {_fmt(target)}，實際 {_fmt(actual)}，建議賣出超重資產、買入低配資產拉回目標權重。{amounts_line}"
        )
    else:
        message = f"{regime_line} 配置正常：實際 {_fmt(actual)} 與目標 {_fmt(target)} 偏離在 ±{threshold}% 門檻內，無需再平衡。"

    return AllocationCheck(
        regime=result["regime"], regime_label=result["regime_label"], target=target,
        actual=actual, drift=drift, needs_rebalance=needs, note=result["note"], message=message,
        amounts=amounts,
    )
