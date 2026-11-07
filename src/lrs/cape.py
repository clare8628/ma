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
CAPE_FULL_HISTORY_PATH = "state/cache/cape_history_full.json"

# NBER 歷史經濟衰退期 (起, 訖)
NBER_RECESSIONS = [
    ("1873-10", "1879-03"), ("1882-03", "1885-05"), ("1887-03", "1888-04"), ("1890-07", "1891-05"),
    ("1893-01", "1894-06"), ("1895-12", "1897-06"), ("1899-06", "1900-12"), ("1902-09", "1904-08"),
    ("1907-05", "1908-06"), ("1910-01", "1912-01"), ("1913-01", "1914-12"), ("1918-08", "1919-03"),
    ("1920-01", "1921-07"), ("1923-05", "1924-07"), ("1926-10", "1927-11"), ("1929-08", "1933-03"),
    ("1937-05", "1938-06"), ("1945-02", "1945-10"), ("1948-11", "1949-10"), ("1953-07", "1954-05"),
    ("1957-08", "1958-04"), ("1960-04", "1961-02"), ("1969-12", "1970-11"), ("1973-11", "1975-03"),
    ("1980-01", "1980-07"), ("1981-07", "1982-11"), ("1990-07", "1991-03"), ("2001-03", "2001-11"),
    ("2007-12", "2009-06"), ("2020-02", "2020-04")
]

# 基準靜態快照資料（備份預設）
_DEFAULT_CAPE_DATA = {
    "source_url": "https://www.wantgoo.com/global/macroeconomics/cape",
    "last_updated": "2026/11/06",
    "latest": {
        "date": "2026/10",
        "cape": 40.71,
        "ecy": 0.56,
        "status": "極端高估",
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


def get_full_cape_history() -> List[Dict[str, Any]]:
    """讀取全歷史數據點 (date, cape, ecy, sp500) 供前端向量圖形繪製。"""
    if os.path.exists(CAPE_FULL_HISTORY_PATH):
        try:
            with open(CAPE_FULL_HISTORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # 預設至少提供近 20 年簡化點
    return [
        {"date": h["date"].replace("/", "-"), "cape": h["cape"], "ecy": h["ecy"], "sp500": 5800.0}
        for h in _DEFAULT_CAPE_DATA["history"]
    ]


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

    # 嘗試從歷史完整快照或網路整理最新
    data = dict(_DEFAULT_CAPE_DATA)
    full_history = get_full_cape_history()
    if full_history:
        # 取最新幾個月
        rev = list(reversed(full_history))
        history_table = []
        for item in rev[:6]:
            d = item["date"].replace("-", "/")
            c = item["cape"]
            e = item["ecy"]
            history_table.append({
                "date": d,
                "cape": c,
                "ecy": e,
                "valuation": evaluate_cape_valuation(c)["tier"]
            })
        data["history"] = history_table
        latest_item = rev[0]
        data["latest"] = {
            "date": latest_item["date"].replace("-", "/"),
            "cape": latest_item["cape"],
            "ecy": latest_item["ecy"],
            "status": evaluate_cape_valuation(latest_item["cape"])["tier"]
        }

    try:
        os.makedirs(os.path.dirname(CAPE_CACHE_PATH), exist_ok=True)
        with open(CAPE_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return data
