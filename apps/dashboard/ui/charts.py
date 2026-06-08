"""
Reusable Plotly Charts for Dashboard
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from typing import List, Dict, Optional


class ChartBuilder:
    """Builder for common Plotly charts"""

    @staticmethod
    def create_equity_curve(
        returns: pd.Series,
        benchmark: Optional[pd.Series] = None,
        title: str = "Equity Curve",
    ) -> go.Figure:
        """Create equity curve with optional benchmark"""
        equity = (1 + returns).cumprod()
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=equity.index,
            y=equity.values,
            mode="lines",
            name="Portfolio",
            line=dict(color="#2196F3", width=2),
        ))
        
        if benchmark is not None:
            bench_equity = (1 + benchmark).cumprod()
            fig.add_trace(go.Scatter(
                x=bench_equity.index,
                y=bench_equity.values,
                mode="lines",
                name="Benchmark",
                line=dict(color="#9E9E9E", width=2, dash="dash"),
            ))
        
        fig.update_layout(
            title=title,
            xaxis_title="Date",
            yaxis_title="Cumulative Return",
            height=400,
            hovermode="x unified",
            showlegend=True,
        )
        
        return fig

    @staticmethod
    def create_drawdown_chart(
        returns: pd.Series,
        title: str = "Drawdown",
    ) -> go.Figure:
        """Create drawdown chart"""
        equity = (1 + returns).cumprod()
        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=drawdown.index,
            y=drawdown.values,
            mode="lines",
            fill="tozeroy",
            name="Drawdown",
            line=dict(color="#F44336", width=1),
            fillcolor="rgba(244, 67, 54, 0.2)",
        ))
        
        fig.update_layout(
            title=title,
            xaxis_title="Date",
            yaxis_title="Drawdown",
            yaxis_tickformat=".1%",
            height=300,
            hovermode="x unified",
        )
        
        return fig

    @staticmethod
    def create_returns_distribution(
        returns: pd.Series,
        title: str = "Returns Distribution",
    ) -> go.Figure:
        """Create returns distribution histogram"""
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=returns.values,
            nbinsx=50,
            name="Returns",
            marker_color="#2196F3",
            opacity=0.7,
        ))
        
        # Add normal distribution overlay
        mean = returns.mean()
        std = returns.std()
        x_norm = np.linspace(returns.min(), returns.max(), 100)
        y_norm = np.exp(-0.5 * ((x_norm - mean) / std) ** 2) / (std * np.sqrt(2 * np.pi))
        y_norm = y_norm * len(returns) * (returns.max() - returns.min()) / 50
        
        fig.add_trace(go.Scatter(
            x=x_norm,
            y=y_norm,
            mode="lines",
            name="Normal Dist",
            line=dict(color="#FF9800", width=2, dash="dash"),
        ))
        
        fig.update_layout(
            title=title,
            xaxis_title="Daily Return",
            yaxis_title="Frequency",
            height=400,
            showlegend=True,
            barmode="overlay",
        )
        
        return fig

    @staticmethod
    def create_monthly_returns_heatmap(
        returns: pd.Series,
        title: str = "Monthly Returns Heatmap",
    ) -> go.Figure:
        """Create monthly returns heatmap"""
        # Convert to monthly returns
        monthly = returns.resample("M").apply(lambda x: (1 + x).prod() - 1)
        
        # Create pivot table
        monthly_df = pd.DataFrame({
            "Year": monthly.index.year,
            "Month": monthly.index.month,
            "Return": monthly.values,
        })
        
        pivot = monthly_df.pivot(index="Year", columns="Month", values="Return")
        
        # Create heatmap
        fig = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
            y=pivot.index,
            colorscale=[
                [0, "#F44336"],      # Red for negative
                [0.5, "#FFFFFF"],    # White for zero
                [1, "#4CAF50"],      # Green for positive
            ],
            zmid=0,
            text=np.round(pivot.values * 100, 1),
            texttemplate="%{text}%",
            textfont={"size": 10},
            hoverongaps=False,
        ))
        
        fig.update_layout(
            title=title,
            xaxis_title="Month",
            yaxis_title="Year",
            height=400,
        )
        
        return fig

    @staticmethod
    def create_sharpe_bar_chart(
        results: List[Dict],
        title: str = "Sharpe Ratio Comparison",
    ) -> go.Figure:
        """Create bar chart of Sharpe ratios from backtest results"""
        names = []
        sharpes = []
        
        for r in results:
            name = r.get("name", r.get("config", "Unknown"))
            sharpe = r.get("metrics", {}).get("sharpe_ratio", 0)
            names.append(name)
            sharpes.append(sharpe)
        
        # Sort by Sharpe
        sorted_idx = np.argsort(sharpes)[::-1]
        names = [names[i] for i in sorted_idx]
        sharpes = [sharpes[i] for i in sorted_idx]
        
        # Color based on Sharpe value
        colors = ["#4CAF50" if s > 1 else "#FF9800" if s > 0 else "#F44336" for s in sharpes]
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=names,
            y=sharpes,
            marker_color=colors,
            text=[f"{s:.2f}" for s in sharpes],
            textposition="auto",
        ))
        
        fig.update_layout(
            title=title,
            xaxis_title="Strategy",
            yaxis_title="Sharpe Ratio",
            height=400,
            showlegend=False,
        )
        
        return fig

    @staticmethod
    def create_risk_metrics_gauge(
        value: float,
        title: str,
        min_val: float = 0,
        max_val: float = 1,
        thresholds: Optional[List[float]] = None,
    ) -> go.Figure:
        """Create gauge chart for risk metrics"""
        if thresholds is None:
            thresholds = [0.5, 0.75]
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=value,
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": title},
            gauge={
                "axis": {"range": [min_val, max_val]},
                "bar": {"color": "#2196F3"},
                "steps": [
                    {"range": [min_val, thresholds[0]], "color": "#4CAF50"},
                    {"range": [thresholds[0], thresholds[1]], "color": "#FF9800"},
                    {"range": [thresholds[1], max_val], "color": "#F44336"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 4},
                    "thickness": 0.75,
                    "value": value,
                },
            },
        ))
        
        fig.update_layout(height=300)
        
        return fig
