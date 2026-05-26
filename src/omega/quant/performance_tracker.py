"""
Performance Tracker - Institutional Elite Grade

Tracks portfolio performance metrics:
- Returns (period, cumulative, CAGR)
- Risk-adjusted ratios (Sharpe, Sortino, Calmar, Information Ratio)
- Drawdown (current, max)
- Trade statistics (win rate, profit factor)
- Turnover
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional
import numpy as np


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot."""
    period_return: float = 0.0
    cumulative_return: float = 0.0
    cagr: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    information_ratio: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    turnover: float = 0.0
    total_trades: int = 0


class PerformanceTracker:
    """
    Institutional-grade performance tracker.

    Features:
    - Multi-horizon returns (daily, cumulative, CAGR)
    - Risk-adjusted ratios (Sharpe, Sortino, Calmar, IR)
    - Drawdown tracking (current, max)
    - Trade statistics (win rate, profit factor, avg win/loss)
    - Turnover calculation
    """

    def __init__(
        self,
        initial_equity: float = 100_000_000.0,  # 100M VND
        risk_free_rate: float = 0.05,  # 5% annual
        benchmark_returns: Optional[List[float]] = None,
    ):
        """
        Args:
            initial_equity: Starting portfolio value
            risk_free_rate: Annual risk-free rate (for Sharpe/Sortino)
            benchmark_returns: Benchmark return series (for Information Ratio)
        """
        self.initial_equity = initial_equity
        self.risk_free_rate = risk_free_rate
        self.benchmark_returns = benchmark_returns or []

        # State
        self.equity_curve: List[float] = [initial_equity]
        self.returns: List[float] = []
        self.trade_log: List[Dict] = []
        self._peak = initial_equity
        self._total_volume = 0.0

    def update(
        self,
        current_equity: float,
        trades: Optional[List[Dict]] = None,
    ) -> PerformanceMetrics:
        """
        Update tracker with new equity value and trades.

        Args:
            current_equity: Current portfolio value
            trades: List of trades executed {symbol, side, qty, price, pnl}

        Returns:
            PerformanceMetrics snapshot
        """
        # Update equity curve
        self.equity_curve.append(current_equity)

        # Calculate return
        if len(self.equity_curve) >= 2:
            prev = self.equity_curve[-2]
            ret = (current_equity - prev) / prev if prev > 0 else 0.0
            self.returns.append(ret)

        # Update peak
        if current_equity > self._peak:
            self._peak = current_equity

        # Record trades
        if trades:
            for trade in trades:
                self.trade_log.append(trade)
                # Accumulate volume for turnover
                volume = abs(trade.get("qty", 0) * trade.get("price", 0.0))
                self._total_volume += volume

        return self.get_metrics()

    def get_metrics(self) -> PerformanceMetrics:
        """Calculate current performance metrics."""
        if not self.equity_curve:
            return PerformanceMetrics()

        current_equity = self.equity_curve[-1]
        n_periods = len(self.returns)

        # Returns
        period_return = self.returns[-1] if self.returns else 0.0
        cumulative_return = (
            (current_equity - self.initial_equity) / self.initial_equity
            if self.initial_equity > 0 else 0.0
        )

        # CAGR (annualized)
        if n_periods > 0 and self.initial_equity > 0:
            years = n_periods / 252.0  # Assume 252 trading days
            if years > 0:
                cagr = ((current_equity / self.initial_equity) ** (1.0 / years)) - 1.0
            else:
                cagr = 0.0
        else:
            cagr = 0.0

        # Drawdown: Track peak dynamically for correct historical max DD
        peaks = np.maximum.accumulate(self.equity_curve)
        drawdowns = (peaks - self.equity_curve) / peaks
        max_dd = float(np.max(drawdowns))
        current_dd = float(drawdowns[-1])

        # Sharpe ratio (annualized)
        sharpe = self._calculate_sharpe()

        # Sortino ratio (annualized)
        sortino = self._calculate_sortino()

        # Calmar ratio
        calmar = cagr / max_dd if max_dd > 0 else 0.0

        # Information ratio
        information_ratio = self._calculate_information_ratio()

        # Trade statistics
        wins = [t for t in self.trade_log if t.get("pnl", 0) > 0]
        losses = [t for t in self.trade_log if t.get("pnl", 0) < 0]

        total_trades = len(self.trade_log)
        win_rate = len(wins) / total_trades if total_trades > 0 else 0.0

        gross_profit = sum(t["pnl"] for t in wins) if wins else 0.0
        gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0.0

        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0
            else float("inf") if gross_profit > 0
            else 0.0
        )

        avg_win = gross_profit / len(wins) if wins else 0.0
        avg_loss = gross_loss / len(losses) if losses else 0.0

        # Turnover
        avg_equity = sum(self.equity_curve) / len(self.equity_curve) if self.equity_curve else 1.0
        turnover = self._total_volume / avg_equity if avg_equity > 0 else 0.0

        return PerformanceMetrics(
            period_return=period_return,
            cumulative_return=cumulative_return,
            cagr=cagr,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            information_ratio=information_ratio,
            max_drawdown=max_dd,
            current_drawdown=current_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            turnover=turnover,
            total_trades=total_trades,
        )

    # ------------------------------------------------------------------
    def _calculate_sharpe(self) -> float:
        """Calculate annualized Sharpe ratio."""
        if len(self.returns) < 2:
            return 0.0

        returns_arr = np.array(self.returns)
        mean_ret = np.mean(returns_arr)
        std_ret = np.std(returns_arr, ddof=1)

        if std_ret == 0:
            return 0.0

        # Annualize (252 trading days)
        daily_rf = self.risk_free_rate / 252.0
        sharpe = (mean_ret - daily_rf) / std_ret * np.sqrt(252)
        return float(sharpe)

    def _calculate_sortino(self) -> float:
        """Calculate annualized Sortino ratio (downside deviation)."""
        if len(self.returns) < 2:
            return 0.0

        returns_arr = np.array(self.returns)
        # Daily minimum acceptable return (MAR) - using risk_free_rate
        daily_mar = self.risk_free_rate / 252.0

        # Downside deviation: sqrt(mean(min(0, r - MAR)^2))
        excess = returns_arr - daily_mar
        downside = np.minimum(excess, 0.0)
        downside_deviation = np.sqrt(np.mean(downside**2))
        if downside_deviation == 0:
            return 0.0

        # Annualize
        sortino = (np.mean(returns_arr) - daily_mar) / downside_deviation * np.sqrt(252)
        return float(sortino)

    def _calculate_information_ratio(self) -> float:
        """Calculate Information Ratio (excess return vs benchmark / tracking error)."""
        if not self.benchmark_returns or len(self.returns) < 2:
            return 0.0

        # Align lengths
        n = min(len(self.returns), len(self.benchmark_returns))
        if n < 2:
            return 0.0

        port_rets = np.array(self.returns[-n:])
        bench_rets = np.array(self.benchmark_returns[-n:])

        # Excess returns
        excess = port_rets - bench_rets
        mean_excess = np.mean(excess)
        tracking_error = np.std(excess, ddof=1)

        if tracking_error == 0:
            return 0.0

        # Annualize
        ir = mean_excess / tracking_error * np.sqrt(252)
        return float(ir)

    def reset(self, initial_equity: Optional[float] = None) -> None:
        """Reset tracker state."""
        if initial_equity is not None:
            self.initial_equity = initial_equity
        self.equity_curve = [self.initial_equity]
        self.returns = []
        self.trade_log = []
        self._peak = self.initial_equity
        self._total_volume = 0.0
