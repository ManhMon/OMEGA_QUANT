"""
Reusable Metric Display Components
"""
import streamlit as st
from typing import Optional, Union


class MetricCard:
    """Builder for metric display cards"""

    @staticmethod
    def render(
        label: str,
        value: Union[str, float, int],
        delta: Optional[Union[str, float]] = None,
        delta_color: str = "normal",
        help_text: Optional[str] = None,
    ):
        """Render a metric card with optional delta"""
        st.metric(
            label=label,
            value=value,
            delta=delta,
            delta_color=delta_color,
            help=help_text,
        )

    @staticmethod
    def render_sharpe(sharpe: float, benchmark: Optional[float] = None):
        """Render Sharpe ratio metric"""
        delta = None
        if benchmark is not None:
            delta = sharpe - benchmark
        
        st.metric(
            label="Sharpe Ratio",
            value=f"{sharpe:.2f}",
            delta=f"{delta:+.2f}" if delta is not None else None,
            delta_color="normal" if delta is not None and delta > 0 else "inverse",
            help="Risk-adjusted return (higher is better)",
        )

    @staticmethod
    def render_sortino(sortino: float, benchmark: Optional[float] = None):
        """Render Sortino ratio metric"""
        delta = None
        if benchmark is not None:
            delta = sortino - benchmark
        
        st.metric(
            label="Sortino Ratio",
            value=f"{sortino:.2f}",
            delta=f"{delta:+.2f}" if delta is not None else None,
            delta_color="normal" if delta is not None and delta > 0 else "inverse",
            help="Downside risk-adjusted return (higher is better)",
        )

    @staticmethod
    def render_max_drawdown(max_dd: float, threshold: float = -0.20):
        """Render max drawdown metric"""
        color = "normal" if max_dd > threshold else "inverse"
        
        st.metric(
            label="Max Drawdown",
            value=f"{max_dd:.1%}",
            help="Maximum peak-to-trough decline (less negative is better)",
        )

    @staticmethod
    def render_var_95(var: float, threshold: float = -0.02):
        """Render 95% VaR metric"""
        st.metric(
            label="VaR 95%",
            value=f"{var:.2%}",
            help="95% Value at Risk (daily loss expected 5% of the time)",
        )

    @staticmethod
    def render_cvar_95(cvar: float, var: float):
        """Render 95% CVaR metric"""
        delta = cvar - var
        st.metric(
            label="CVaR 95%",
            value=f"{cvar:.2%}",
            delta=f"{delta:+.2%}",
            delta_color="inverse",
            help="95% Conditional VaR (expected loss when VaR is breached)",
        )

    @staticmethod
    def render_win_rate(win_rate: float, benchmark: float = 0.5):
        """Render win rate metric"""
        delta = win_rate - benchmark
        st.metric(
            label="Win Rate",
            value=f"{win_rate:.1%}",
            delta=f"{delta:+.1%}",
            delta_color="normal" if delta > 0 else "inverse",
            help="Percentage of winning trades",
        )

    @staticmethod
    def render_total_return(total_return: float, benchmark_return: Optional[float] = None):
        """Render total return metric"""
        delta = None
        if benchmark_return is not None:
            delta = total_return - benchmark_return
        
        st.metric(
            label="Total Return",
            value=f"{total_return:.1%}",
            delta=f"{delta:+.1%}" if delta is not None else None,
            delta_color="normal" if delta is not None and delta > 0 else "inverse",
            help="Cumulative return over the period",
        )

    @staticmethod
    def render_annual_return(annual_return: float, benchmark_return: Optional[float] = None):
        """Render annualized return metric"""
        delta = None
        if benchmark_return is not None:
            delta = annual_return - benchmark_return
        
        st.metric(
            label="Annual Return",
            value=f"{annual_return:.1%}",
            delta=f"{delta:+.1%}" if delta is not None else None,
            delta_color="normal" if delta is not None and delta > 0 else "inverse",
            help="Annualized return",
        )

    @staticmethod
    def render_volatility(volatility: float, threshold: float = 0.20):
        """Render volatility metric"""
        st.metric(
            label="Volatility",
            value=f"{volatility:.1%}",
            help="Annualized standard deviation of returns",
        )

    @staticmethod
    def render_beta(beta: float):
        """Render beta metric"""
        st.metric(
            label="Beta",
            value=f"{beta:.2f}",
            help="Sensitivity to market movements (1.0 = market)",
        )

    @staticmethod
    def render_alpha(alpha: float):
        """Render alpha metric"""
        st.metric(
            label="Alpha",
            value=f"{alpha:.1%}",
            help="Excess return over benchmark (higher is better)",
        )

    @staticmethod
    def render_profit_factor(profit_factor: float):
        """Render profit factor metric"""
        st.metric(
            label="Profit Factor",
            value=f"{profit_factor:.2f}",
            help="Gross profit / Gross loss (higher is better, >1.5 is good)",
        )

    @staticmethod
    def render_num_trades(num_trades: int):
        """Render number of trades"""
        st.metric(
            label="Total Trades",
            value=f"{num_trades:,}",
            help="Total number of trades executed",
        )

    @staticmethod
    def render_avg_trade(avg_trade: float):
        """Render average trade return"""
        st.metric(
            label="Avg Trade",
            value=f"{avg_trade:.2%}",
            help="Average return per trade",
        )

    @staticmethod
    def render_exposure(exposure: float):
        """Render market exposure"""
        st.metric(
            label="Exposure",
            value=f"{exposure:.1%}",
            help="Percentage of time invested in market",
        )
