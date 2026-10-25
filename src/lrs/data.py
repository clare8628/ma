"""歷史股價資料來源：Yahoo Finance chart API（免金鑰），僅用 Python 標準庫。

含本地 JSON 快取（預設 12 小時 TTL），避免重複呼叫；若網路不可用，
會嘗試回退使用快取（即使過期）。亦支援從本地 CSV 載入資料（離線/測試用）。
"""
from __future__ import annotations

import csv
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
USER_AGENT = "Mozilla/5.0 (compatible; LRS-Bot/1.0)"


def _get_ssl_context() -> Optional[ssl.SSLContext]:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        return ssl.create_default_context()
    except Exception:
        return None


@dataclass
class PriceBar:
    date: str  # YYYY-MM-DD
    close: float


class DataFetchError(RuntimeError):
    pass


def _cache_path(cache_dir: str, symbol: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    clean_symbol = symbol.upper().replace("^", "")
    # 若存在含 ^ 的舊檔名優先沿用，否則使用乾淨檔名
    raw_path = os.path.join(cache_dir, f"{symbol.upper()}.json")
    if os.path.exists(raw_path):
        return raw_path
    return os.path.join(cache_dir, f"{clean_symbol}.json")


def _load_cache(cache_dir: str, symbol: str) -> Optional[dict]:
    path = _cache_path(cache_dir, symbol)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_cache(cache_dir: str, symbol: str, payload: dict) -> None:
    path = _cache_path(cache_dir, symbol)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def fetch_history(
    symbol: str,
    range_: str = "max",
    interval: str = "1d",
    cache_dir: str = "state/cache",
    cache_ttl_hours: float = 12.0,
) -> List[PriceBar]:
    """抓取指定 symbol 的歷史日收盤價，舊到新排序。失敗時回退快取。"""
    cached = _load_cache(cache_dir, symbol)
    now = time.time()
    # 若請求全歷史 (max)，但快取資料少於 1500 筆（代表僅有短天期快取），則強制重新抓取全歷史
    cached_bars = cached.get("bars", []) if cached else []
    cache_valid = (
        cached is not None
        and (now - cached.get("_fetched_at", 0) < cache_ttl_hours * 3600)
        and (range_ != "max" or len(cached_bars) >= 1500)
    )
    if cache_valid:
        return [PriceBar(d, c) for d, c in cached_bars]

    if range_ == "max":
        query = f"period1=0&period2=9999999999&interval={interval}"
    else:
        query = f"range={range_}&interval={interval}"
    safe_symbol = urllib.parse.quote(symbol)
    url = YAHOO_CHART_URL.format(symbol=safe_symbol) + f"?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = _get_ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            raw = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        if cached:
            return [PriceBar(d, c) for d, c in cached["bars"]]
        raise DataFetchError(f"無法取得 {symbol} 資料且無可用快取: {exc}") from exc

    try:
        result = raw["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError) as exc:
        if cached:
            return [PriceBar(d, c) for d, c in cached["bars"]]
        raise DataFetchError(f"{symbol} 回應格式不符預期: {exc}") from exc

    bars: List[PriceBar] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        date_str = time.strftime("%Y-%m-%d", time.gmtime(ts))
        bars.append(PriceBar(date_str, float(close)))

    if not bars:
        if cached:
            return [PriceBar(d, c) for d, c in cached["bars"]]
        raise DataFetchError(f"{symbol} 無有效資料")

    _save_cache(cache_dir, symbol, {
        "_fetched_at": now,
        "bars": [[b.date, b.close] for b in bars],
    })
    return bars


def load_history_csv(path: str) -> List[PriceBar]:
    """從本地 CSV（欄位: date,close）載入資料，用於離線測試或自備資料。"""
    bars: List[PriceBar] = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bars.append(PriceBar(row["date"], float(row["close"])))
    bars.sort(key=lambda b: b.date)
    return bars
