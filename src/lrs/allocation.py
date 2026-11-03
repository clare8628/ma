"""現金 + QQQ + TQQQ 三資產配置層（簡化版）。

概念來源：使用者提供之 YouTube 影片（財富種植園《TQQQ 長期持有策略：10年50倍
策略詳解》）談到以現金與 QQQ 搭配 TQQQ 做組合配置，用以壓低單押 TQQQ 的波動與
最大回撤。該片未提供公開逐字稿／API，故本專案依使用者指定的範例比例
（10% 現金 / 45% QQQ / 45% TQQQ）將其核心思路簡化為以下機制，取代逐字重現影片
細節：

  1. 固定「目標權重」：預設 10% 現金 / 45% QQQ / 45% TQQQ，可於
     config/settings.json 的 allocation.target_weights 調整。
  2. 既有規則引擎（signals.recommend）只負責判斷「要不要持有 TQQQ 曝險」；
     本模組再依其建議動作，把目標權重做對應縮放：
       - 出場類動作 (SELL_ALL / FORCE_EXIT) → 目標變成 100% 現金。
       - 減碼類動作 (REDUCE_50 / TRIM_PARTIAL) → TQQQ 目標權重按比例縮減，
         釋出的差額併入現金（QQQ 權重不變）。
       - 其餘（BUY / BUY_DIP_PANIC / HOLD / SKIP_ENTRY_OVERBOUGHT）→ 維持
         基礎目標權重。
  3. 無論訊號為何，只要使用者填寫的「實際持倉權重」與「目標權重」偏離超過
     drift_threshold_pct（預設 ±5 個百分點），就提醒再平衡：賣出超重的資產、
     買入低配的資產拉回目標——這就是用現金與 QQQ「平衡」TQQQ 波動的核心機制
     （越漲越減碼 TQQQ 鎖定獲利，越跌越加碼 TQQQ 逢低攤平，現金與 QQQ 是
     緩衝與再平衡的資金來源）。

本模組僅輸出建議文字，不連接券商、不自動下單。實際持倉比例需使用者自行寫入
state/allocation_snapshot.json（手動快照，格式見 ALLOCATION_SNAPSHOT_PATH）。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Optional

ALLOCATION_SNAPSHOT_PATH = "state/allocation_snapshot.json"

# 動作 -> TQQQ 目標權重保留比例（差額併入現金）；未列出的動作視為 1.0（全額維持）
_TQQQ_KEEP_FRACTION = {
    "REDUCE_50": 0.5,
    "TRIM_PARTIAL": 0.6,  # 規則訊息為「賣出1/3~1/2」，取中間值保留60%
}
_FULL_EXIT_ACTIONS = {"SELL_ALL", "FORCE_EXIT"}

# 未在 settings.json 設定 allocation 區塊時的預設值（對應影片範例：10%現金/45%QQQ/45%TQQQ）
_DEFAULT_TARGET_WEIGHTS = {"cash": 10, "qqq": 45, "tqqq": 45}
_DEFAULT_DRIFT_THRESHOLD_PCT = 5


def _allocation_cfg(settings: dict) -> dict:
    return (settings or {}).get("allocation", {})


def _base_weights(settings: dict) -> Dict[str, float]:
    w = _allocation_cfg(settings).get("target_weights", _DEFAULT_TARGET_WEIGHTS)
    return {"cash": float(w["cash"]), "qqq": float(w["qqq"]), "tqqq": float(w["tqqq"])}


def target_weights_for_action(action: str, settings: dict) -> Dict[str, float]:
    """依訊號建議動作，計算當下的現金/QQQ/TQQQ目標權重（百分比，合計100）。"""
    base = _base_weights(settings)

    if action in _FULL_EXIT_ACTIONS:
        return {"cash": 100.0, "qqq": 0.0, "tqqq": 0.0}

    keep_fraction = _TQQQ_KEEP_FRACTION.get(action)
    if keep_fraction is not None:
        tqqq = base["tqqq"] * keep_fraction
        released = base["tqqq"] - tqqq
        return {"cash": base["cash"] + released, "qqq": base["qqq"], "tqqq": tqqq}

    return base


@dataclass
class AllocationCheck:
    action: str
    target: Dict[str, float]
    actual: Optional[Dict[str, float]]
    drift: Optional[Dict[str, float]]
    needs_rebalance: bool
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
    action: str,
    settings: dict,
    snapshot_path: str = ALLOCATION_SNAPSHOT_PATH,
) -> AllocationCheck:
    """比對目標權重與使用者填寫的實際持倉權重，超過偏離門檻則提醒再平衡。"""
    target = target_weights_for_action(action, settings)
    actual = _read_snapshot(snapshot_path)
    threshold = _allocation_cfg(settings).get("drift_threshold_pct", _DEFAULT_DRIFT_THRESHOLD_PCT)

    if actual is None:
        return AllocationCheck(
            action=action,
            target=target,
            actual=None,
            drift=None,
            needs_rebalance=False,
            message=(
                f"目標配置：{_fmt(target)}。尚無實際持倉快照，"
                f"請於 {snapshot_path} 填入 cash_pct/qqq_pct/tqqq_pct 以啟用偏離度檢核。"
            ),
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
            f"再平衡警示（門檻 ±{threshold}%）：{'; '.join(parts)}。"
            f"目標 {_fmt(target)}，實際 {_fmt(actual)}，"
            f"建議賣出超重資產、買入低配資產拉回目標權重。"
        )
    else:
        message = f"配置正常：實際 {_fmt(actual)} 與目標 {_fmt(target)} 偏離在 ±{threshold}% 門檻內，無需再平衡。"

    return AllocationCheck(
        action=action,
        target=target,
        actual=actual,
        drift=drift,
        needs_rebalance=needs,
        message=message,
    )
