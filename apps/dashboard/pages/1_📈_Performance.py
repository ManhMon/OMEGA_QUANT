"""
Performance Page - Detailed performance metrics
"""
import streamlit as st
import sys
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASHBOARD_ROOT))

from config.dashboard_config import PAGE_TITLE, CUSTOM_CSS
from services.data_loader import DataLoaderService
from ui.charts import ChartBuilder
from ui.metrics import MetricCard
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title=f"{PAGE_TITLE} - Performance", page_icon="📈", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown("## 📈 Performance Metrics")

# Load data
risk_status = DataLoaderService.load_risk_status()
backtest_results = DataLoaderService.load_backtest_results()

if risk_status:
    m = risk_status.get("metrics", {})
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        MetricCard.render_sharpe(m.get("sharpe_ratio", 0.0))
    with col2:
        MetricCard.render_sortino(m.get("sortino_ratio", 0.0))
    with col3:
        MetricCard.render_max_drawdown(m.get("max_drawdown", 0.0))
    with col4:
        MetricCard.render_total_return(m.get("total_return", 0.0))
    
    # Second row
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        MetricCard.render_win_rate(m.get("win_rate", 0.0))
    with col6:
        MetricCard.render_profit_factor(m.get("profit_factor", 0.0))
    with col7:
        MetricCard.render_num_trades(m.get("num_trades", 0))
    with col8:
        MetricCard.render_avg_trade(m.get("avg_trade", 0.0))
    
    st.markdown("---")
    
    # Equity curve placeholder
    st.markdown("### 📊 Equity Curve")
    st.info("Equity curve will be displayed here when time series data is available.")
    
    # Drawdown chart placeholder
    st.markdown("### 📉 Drawdown Analysis")
    st.info("Drawdown chart will be displayed here when time series data is available.")
    
else:
    st.info("No risk status data available.")

# Backtest comparison
st.markdown("---")
st.markdown("## 🧪 Backtest Comparison")

if backtest_results:
    # Create comparison table
    comparison_data = []
    for i, result in enumerate(backtest_results[:10], 1):
        name = result.get("name", result.get("config", f"Backtest {i}"))
        metrics = result.get("metrics", {})
        
        comparison_data.append({
            "Name": name,
            "Sharpe": metrics.get("sharpe_ratio", 0.0),
            "Return": metrics.get("total_return", 0.0),
            "Max DD": metrics.get("max_drawdown", 0.0),
            "Win Rate": metrics.get("win_rate", 0.0),
            "Trades": metrics.get("num_trades", 0),
        })
    
    df = pd.DataFrame(comparison_data)
    
    # Sort by Sharpe
    df = df.sort_values("Sharpe", ascending=False)
    
    # Display table
    st.dataframe(df, width="stretch", hide_index=True)
    
    # Sharpe bar chart
    st.markdown("### Sharpe Ratio Comparison")
    fig = ChartBuilder.create_sharpe_bar_chart(backtest_results[:10])
    st.plotly_chart(fig, width="stretch")
    
else:
    st.info("No backtest results available for comparison.")
