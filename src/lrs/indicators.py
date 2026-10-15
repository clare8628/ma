"""純 Python 技術指標計算（SMA / EMA / RSI），無第三方相依套件。

每個函式輸入一組依時間排序（舊到新）的收盤價 list[float]，
回傳等長的 list[Optional[float]]，資料不足處為 None。
"""
from __future__ import annotations

from typing import List, Optional


def sma(values: List[float], window: int) -> List[Optional[float]]:
    if window <= 0:
        raise ValueError("window must be positive")
    out: List[Optional[float]] = [None] * len(values)
    running_sum = 0.0
    for i, v in enumerate(values):
        running_sum += v
        if i >= window:
            running_sum -= values[i - window]
        if i >= window - 1:
            out[i] = running_sum / window
    return out


def ema(values: List[float], window: int) -> List[Optional[float]]:
    if window <= 0:
        raise ValueError("window must be positive")
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < window:
        return out

    seed = sum(values[:window]) / window
    out[window - 1] = seed
    multiplier = 2 / (window + 1)
    prev = seed
    for i in range(window, len(values)):
        prev = (values[i] - prev) * multiplier + prev
        out[i] = prev
    return out


def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    """Wilder's RSI (標準 14 日 RSI 計算方式)。"""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if n <= period:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        if change > 0:
            gains += change
        else:
            losses += -change
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from_avg(avg_gain, avg_loss)

    for i in range(period + 1, n):
        change = values[i] - values[i - 1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _rsi_from_avg(avg_gain, avg_loss)
    return out


def _rsi_from_avg(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
