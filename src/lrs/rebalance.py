"""每年 11/1 再平衡檢核：提醒檢查防禦性資產（現金/國債）是否已達到目標比例，
以便有資金在「高拋低吸」策略中執行低吸。

資產配置資料來源 https://mgtasset.clare8628.workers.dev/ 。
串接方式（詳見 docs/MGTASSET-API.md）：
  1. 在資產站新增唯讀端點 GET /api/ma/defensive，以 Bearer token 驗證（不使用帳密）。
  2. 本機/CI 設定環境變數 MGTASSET_API_TOKEN（切勿提交版控）。
  3. 未設定或呼叫失敗時，退回 `state/asset_snapshot.json` 手動快照。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

MANUAL_SNAPSHOT_PATH = "state/asset_snapshot.json"
ASSET_SITE_URL = "https://mgtasset.clare8628.workers.dev/"


@dataclass
class RebalanceCheck:
    is_rebalance_window: bool
    window_label: str
    defensive_pct: Optional[float]
    defensive_target_pct: float
    needs_manual_check: bool
    message: str


def is_rebalance_window(today: dt.date, settings: dict) -> bool:
    cfg = settings["rebalance"]
    target = dt.date(today.year, cfg["month"], cfg["day"])
    return 0 <= (today - target).days <= cfg.get("window_days", 0)


def _read_manual_snapshot(path: str = MANUAL_SNAPSHOT_PATH) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


class AssetAllocationProvider:
    """抽象介面：之後若取得 mgtasset 站台的實際登入 API，於此實作自動查詢。"""

    def fetch_defensive_pct(self) -> Optional[float]:
        """呼叫資產站唯讀端點 GET /api/ma/defensive（Bearer token），規格見 docs/MGTASSET-API.md。
        未設定 MGTASSET_API_TOKEN 或呼叫失敗時回傳 None，由手動快照接手。"""
        token = os.environ.get("MGTASSET_API_TOKEN")
        if not token:
            return None
        url = os.environ.get("MGTASSET_API_URL", ASSET_SITE_URL.rstrip("/") + "/api/ma/defensive")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                   "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                pct = json.load(resp).get("defensive_pct")
            return float(pct) if pct is not None else None
        except (urllib.error.URLError, ValueError, OSError):
            return None


def check_rebalance(settings: dict, today: Optional[dt.date] = None,
                     provider: Optional[AssetAllocationProvider] = None) -> RebalanceCheck:
    today = today or dt.date.today()
    cfg = settings["rebalance"]
    in_window = is_rebalance_window(today, settings)
    target_pct = cfg["defensive_target_pct"]

    defensive_pct = None
    provider = provider or AssetAllocationProvider()
    if in_window:
        defensive_pct = provider.fetch_defensive_pct()
        if defensive_pct is None:
            snapshot = _read_manual_snapshot()
            if snapshot:
                defensive_pct = snapshot.get("defensive_pct")

    needs_manual = in_window and defensive_pct is None

    if not in_window:
        message = f"非再平衡窗口（每年 {cfg['month']}/{cfg['day']} ±{cfg.get('window_days',0)} 天）。"
    elif needs_manual:
        message = (
            f"今日為年度再平衡窗口。無法自動取得防禦性資產比例，"
            f"請至 {ASSET_SITE_URL} 登入查詢現金/國債比例，"
            f"並寫入 {MANUAL_SNAPSHOT_PATH}（格式: {{\"defensive_pct\": 數字}}）後重新執行，"
            f"或直接人工比對是否已達目標 {target_pct}%。"
        )
    elif defensive_pct >= target_pct:
        message = f"再平衡檢核通過：防禦性資產 {defensive_pct}% >= 目標 {target_pct}%，資金充足可執行低吸。"
    else:
        message = (
            f"再平衡警示：防禦性資產僅 {defensive_pct}%，低於目標 {target_pct}%，"
            f"建議檢視是否需調整持股比例以補足防禦性資產。"
        )

    return RebalanceCheck(
        is_rebalance_window=in_window,
        window_label=f"{today.year}-{cfg['month']:02d}-{cfg['day']:02d}",
        defensive_pct=defensive_pct,
        defensive_target_pct=target_pct,
        needs_manual_check=needs_manual,
        message=message,
    )
