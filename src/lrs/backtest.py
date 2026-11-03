"""訊號基礎比較回測引擎：比較「以 TQQQ 自身價格計算進出場訊號」vs.
「以 QQQ 價格計算進出場訊號、但實際買賣 TQQQ」兩種基礎孰優。

僅用於研究評估，不影響 main.py 的正式建議邏輯／config/rules.json。
交易規則簡化為單一多/空倉位（不含 VIX 恐慌抄底、不含分批減碼），
因為這些機制在兩種基礎下相同，不影響「訊號基礎」本身的比較。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from . import indicators


@dataclass
class Trade:
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float

    @property
    def return_pct(self) -> float:
        return (self.exit_price - self.entry_price) / self.entry_price * 100

    @property
    def is_win(self) -> bool:
        return self.exit_price > self.entry_price


@dataclass
class BacktestResult:
    basis: str
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def win_count(self) -> int:
        return sum(1 for t in self.trades if t.is_win)

    @property
    def win_rate_pct(self) -> Optional[float]:
        if not self.trades:
            return None
        return self.win_count / self.trade_count * 100

    @property
    def avg_win_pct(self) -> Optional[float]:
        wins = [t.return_pct for t in self.trades if t.is_win]
        return sum(wins) / len(wins) if wins else None

    @property
    def avg_loss_pct(self) -> Optional[float]:
        losses = [t.return_pct for t in self.trades if not t.is_win]
        return sum(losses) / len(losses) if losses else None

    @property
    def total_return_pct(self) -> Optional[float]:
        if not self.equity_curve:
            return None
        return (self.equity_curve[-1] / self.equity_curve[0] - 1) * 100

    @property
    def max_drawdown_pct(self) -> Optional[float]:
        if not self.equity_curve:
            return None
        peak = self.equity_curve[0]
        max_dd = 0.0
        for v in self.equity_curve:
            peak = max(peak, v)
            dd = (v - peak) / peak * 100
            max_dd = min(max_dd, dd)
        return max_dd

    @property
    def time_in_market_pct(self) -> Optional[float]:
        if not self.dates:
            return None
        covered = sum(
            _trading_days_between(t.entry_date, t.exit_date, self.dates)
            for t in self.trades
        )
        return covered / len(self.dates) * 100


def _trading_days_between(start: str, end: str, dates: List[str]) -> int:
    try:
        i = dates.index(start)
        j = dates.index(end)
    except ValueError:
        return 0
    return max(0, j - i)


def run_signal_basis_backtest(
    dates: List[str],
    qqq_close: List[float],
    tqqq_close: List[float],
    *,
    basis: str = "tqqq",
    gate_sma_period: int = 200,
    fast_ema_period: int = 10,
    slow_ema_period: int = 20,
    rsi_period: int = 14,
    rsi_entry_min: float = 50,
    rsi_entry_max: float = 65,
    rsi_defensive_exit: float = 45,
    rsi_overheat: float = 70,
    overheat_extension_pct: float = 15,
) -> BacktestResult:
    """basis="tqqq": 進出場均線/RSI 以 TQQQ 自身價格計算（目前上線邏輯）。
    basis="qqq": 進出場均線/RSI 以 QQQ 價格計算，但實際買賣標的仍是 TQQQ。
    兩者皆以 QQQ 200SMA 作為大盤多空閘門（與現行規則一致，非比較變因）。
    """
    if basis not in ("tqqq", "qqq"):
        raise ValueError("basis must be 'tqqq' or 'qqq'")

    signal_price = tqqq_close if basis == "tqqq" else qqq_close

    qqq_sma_gate = indicators.sma(qqq_close, gate_sma_period)
    ema_fast = indicators.ema(signal_price, fast_ema_period)
    ema_slow = indicators.ema(signal_price, slow_ema_period)
    rsi = indicators.rsi(signal_price, rsi_period)

    result = BacktestResult(basis=basis, dates=dates)
    holding = False
    entry_date = None
    entry_price = None

    for i in range(1, len(dates)):
        gate_ok = qqq_sma_gate[i] is not None and qqq_close[i] > qqq_sma_gate[i]

        if holding:
            ema_slow_dist_pct = None
            if ema_slow[i] not in (None, 0):
                ema_slow_dist_pct = (signal_price[i] - ema_slow[i]) / ema_slow[i] * 100

            death_cross = (
                ema_fast[i - 1] is not None and ema_slow[i - 1] is not None
                and ema_fast[i] is not None and ema_slow[i] is not None
                and ema_fast[i - 1] >= ema_slow[i - 1] and ema_fast[i] < ema_slow[i]
            )
            defensive_exit = rsi[i] is not None and rsi[i] < rsi_defensive_exit
            overheat_exit = (
                rsi[i] is not None and rsi[i] > rsi_overheat
                and ema_slow_dist_pct is not None and ema_slow_dist_pct > overheat_extension_pct
            )

            if death_cross or (not gate_ok) or defensive_exit or overheat_exit:
                exit_price = tqqq_close[i]
                result.trades.append(Trade(entry_date, entry_price, dates[i], exit_price))
                holding = False
                entry_date = None
                entry_price = None
        else:
            golden_cross = (
                ema_fast[i - 1] is not None and ema_slow[i - 1] is not None
                and ema_fast[i] is not None and ema_slow[i] is not None
                and ema_fast[i - 1] <= ema_slow[i - 1] and ema_fast[i] > ema_slow[i]
            )
            rsi_ok = rsi[i] is not None and rsi_entry_min < rsi[i] < rsi_entry_max

            if gate_ok and golden_cross and rsi_ok:
                holding = True
                entry_date = dates[i]
                entry_price = tqqq_close[i]

    if holding:
        result.trades.append(Trade(entry_date, entry_price, dates[-1], tqqq_close[-1]))

    equity = 1.0
    equity_curve = [1.0]
    trade_idx = 0
    for i in range(1, len(dates)):
        if trade_idx < len(result.trades):
            t = result.trades[trade_idx]
            if t.entry_date <= dates[i] <= t.exit_date and tqqq_close[i - 1] != 0:
                equity *= tqqq_close[i] / tqqq_close[i - 1]
            if dates[i] == t.exit_date:
                trade_idx += 1
        equity_curve.append(equity)
    result.equity_curve = equity_curve

    return result


def buy_and_hold_result(dates: List[str], tqqq_close: List[float]) -> BacktestResult:
    result = BacktestResult(basis="buy_and_hold", dates=dates)
    result.trades = [Trade(dates[0], tqqq_close[0], dates[-1], tqqq_close[-1])]
    base = tqqq_close[0]
    result.equity_curve = [c / base for c in tqqq_close]
    return result
