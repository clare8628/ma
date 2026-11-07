"""S&P 500 席勒本益比 (CAPE, Shiller PE) 與超額報酬率 (ECY) 模組。

指標說明：
- 席勒本益比 (CAPE, Shiller PE / PE10)：
  股價 / 近10年平均實質EPS（經通膨與季節性調整），由諾貝爾經濟學獎得主 Robert Shiller 提出。
  用於評估大盤實質長期估值水準與中長期回報潛力，較不適用於短線交易。
- 超額調整後本益比報酬率 (ECY, Excess CAPE Yield)：
  ECY = (1 / CAPE) - 美國實質10年期公債殖利率。代表股票獲利率相對於無風險公債之實質超額回報。
  ECY 越高表示相對於公債更便宜、安全邊際越高；反之越低代表股票相對昂貴或吸引力偏低。
- 參考資料來源：
  玩股網 (WantGoo): https://www.wantgoo.com/global/macroeconomics/cape
  Robert Shiller Yale Data / Multpl
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional

CAPE_CACHE_PATH = "state/cache/cape_stats.json"

# 基準靜態快照資料（取自 WantGoo 官方統計圖表最新月份紀錄，確保離線或無網路亦能秒級載入）
_DEFAULT_CAPE_DATA = {
    "source_url": "https://www.wantgoo.com/global/macroeconomics/cape",
    "last_updated": "2026/11/02",
    "latest": {
        "date": "2026/10",
        "cape": 40.71,
        "ecy": 0.56,
        "status": "極度高估（歷史高檔警戒區）",
        "percentile_approx": 98.5,
    },
    "history": [
        {"date": "2026/10", "cape": 40.71, "ecy": 0.56, "valuation": "歷史極端高檔（僅次於2000網路泡沫）"},
        {"date": "2026/09", "cape": 40.58, "ecy": 0.82, "valuation": "歷史極端高檔"},
        {"date": "2026/08", "cape": 40.99, "ecy": 1.11, "valuation": "歷史極端高檔"},
        {"date": "2026/07", "cape": 40.01, "ecy": 1.23, "valuation": "歷史高檔區間"},
        {"date": "2026/06", "cape": 40.15, "ecy": 1.34, "valuation": "歷史高檔區間"},
        {"date": "2026/05", "cape": 39.80, "ecy": 1.45, "valuation": "歷史高檔區間"},
    ],
    "historical_benchmarks": {
        "historical_median": 16.0,
        "historical_mean": 17.5,
        "dot_com_peak_2000": 44.19,
        "pre_gfc_peak_2007": 27.55,
        "covid_trough_2020": 24.82,
        "post_covid_peak_2021": 38.58,
    }
}


def evaluate_cape_valuation(cape: float) -> Dict[str, str]:
    """評估 CAPE 水準與長期投資安全邊際。"""
    if cape >= 38.0:
        return {
            "tier": "極端高估",
            "badge_color": "#dc2626",
            "desc": "估值處於百年歷史前 2% 極端昂貴區間（僅次於 2000 年網路泡沫高點 44.19），長期預期報酬率顯著壓縮，須強化動態均線防守紀律，嚴防系統性估值修復風險。",
        }
    elif cape >= 30.0:
        return {
            "tier": "偏高（熱絡）",
            "badge_color": "#ea580c",
            "desc": "估值處於相對偏高水準，市場情緒偏樂觀，仍可順應均線趨勢順勢交易，但應避免在無均線保護下大額單筆追高。",
        }
    elif cape >= 20.0:
        return {
            "tier": "合理健全",
            "badge_color": "#0284c7",
            "desc": "估值處於現代科技股溢價下之合理常態區間，風險報酬比適中。",
        }
    else:
        return {
            "tier": "便宜（高安全邊際）",
            "badge_color": "#16a34a",
            "desc": "估值處於歷史均值或低估水準，為長期資金極佳之資產累積甜蜜點。",
        }


def get_cape_statistics(cache_ttl_hours: int = 48) -> Dict[str, Any]:
    """取得 CAPE 與 ECY 數據。優先從本地快取讀取，若快取過期則嘗試更新並寫回快取。"""
    if os.path.exists(CAPE_CACHE_PATH):
        try:
            mtime = os.path.getmtime(CAPE_CACHE_PATH)
            age = (dt.datetime.now().timestamp() - mtime) / 3600
            with open(CAPE_CACHE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if age < cache_ttl_hours:
                return cached
        except Exception:
            pass

    # 嘗試從網路即時爬取更新
    data = dict(_DEFAULT_CAPE_DATA)
    try:
        req = urllib.request.Request(
            "https://www.multpl.com/shiller-pe/table/by-month",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode("utf-8")
        rows = re.findall(r"<td>([A-Za-z]+ \d+, \d{4})</td>\s*<td>\s*&#x2002;\s*([\d\.]+)\s*</td>", html)
        if rows:
            # 轉換前幾個月的資料
            history = []
            for date_str, val_str in rows[:12]:
                try:
                    d = dt.datetime.strptime(date_str, "%b %d, %Y")
                    month_key = d.strftime("%Y/%m")
                    cape_val = float(val_str)
                    # 估算 ECY (1/CAPE * 100 - 實質利率約 1.85%~1.90%)
                    real_rate_est = 1.90
                    ecy_val = round(100.0 / cape_val - real_rate_est, 2)
                    history.append({
                        "date": month_key,
                        "cape": cape_val,
                        "ecy": ecy_val,
                        "valuation": evaluate_cape_valuation(cape_val)["tier"],
                    })
                except Exception:
                    continue
            if history:
                # 依月份去重排序
                seen = set()
                dedup = []
                for h in history:
                    if h["date"] not in seen:
                        seen.add(h["date"])
                        dedup.append(h)
                data["history"] = dedup[:6]
                data["latest"] = {
                    "date": dedup[0]["date"],
                    "cape": dedup[0]["cape"],
                    "ecy": dedup[0]["ecy"],
                    "status": evaluate_cape_valuation(dedup[0]["cape"])["tier"],
                }
    except Exception:
        # 網路失敗時沿用預設
        pass

    try:
        os.makedirs(os.path.dirname(CAPE_CACHE_PATH), exist_ok=True)
        with open(CAPE_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return data
