"""
Trades Page - Trade history and execution
"""
import streamlit as st
import sys
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASHBOARD_ROOT))

from config.dashboard_config import PAGE_TITLE, CUSTOM_CSS
from services.data_loader import DataLoaderService
import pandas as pd

st.set_page_config(page_title=f"{PAGE_TITLE} - Trades", page_icon="💼", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown("## 💼 Trade History")

# Load data
risk_status = DataLoaderService.load_risk_status()

if risk_status:
    trades = risk_status.get("trades", [])
    
    if trades:
        # Trade summary
        st.markdown("### Trade Summary")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_trades = len(trades)
            st.metric("Total Trades", total_trades)
        
        with col2:
            metrics = risk_status.get("metrics", {})
            win_rate = metrics.get("win_rate", 0)
            st.metric("Win Rate", f"{win_rate:.1%}")
        
        with col3:
            avg_trade = metrics.get("avg_trade", 0)
            st.metric("Avg Trade", f"{avg_trade:.2%}")
        
        with col4:
            profit_factor = metrics.get("profit_factor", 0)
            st.metric("Profit Factor", f"{profit_factor:.2f}")
        
        st.markdown("---")
        
        # Recent trades table
        st.markdown("### Recent Trades")
        
        df_trades = pd.DataFrame(trades)
        
        # Show most recent 50 trades
        display_trades = df_trades.tail(50).iloc[::-1]  # Reverse to show newest first
        
        # Format columns
        display_cols = ["timestamp", "symbol", "side", "quantity", "price", "value", "pnl"]
        available_cols = [col for col in display_cols if col in display_trades.columns]
        
        if available_cols:
            st.dataframe(display_trades[available_cols], width="stretch", hide_index=True)
        else:
            st.dataframe(display_trades, width="stretch")
        
        # Trade filters
        st.markdown("---")
        st.markdown("### Trade Filters")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if "symbol" in df_trades.columns:
                symbols = df_trades["symbol"].unique()
                selected_symbols = st.multiselect("Filter by Symbol", symbols, default=symbols[:5] if len(symbols) > 5 else symbols)
        
        with col2:
            if "side" in df_trades.columns:
                sides = df_trades["side"].unique()
                selected_sides = st.multiselect("Filter by Side", sides, default=sides)
        
        with col3:
            if "timestamp" in df_trades.columns:
                date_range = st.date_input("Date Range", [])
        
        # Apply filters
        filtered_trades = display_trades.copy()
        
        if "symbol" in df_trades.columns and 'selected_symbols' in locals():
            filtered_trades = filtered_trades[filtered_trades["symbol"].isin(selected_symbols)]
        
        if "side" in df_trades.columns and 'selected_sides' in locals():
            filtered_trades = filtered_trades[filtered_trades["side"].isin(selected_sides)]
        
        if len(filtered_trades) > 0:
            st.markdown("### Filtered Results")
            st.dataframe(filtered_trades, width="stretch", hide_index=True)
        
    else:
        st.info("No trade data available in risk status.")
else:
    st.info("No risk status data available. Run risk analysis to populate trades.")

st.markdown("---")

# Execution quality placeholder
st.markdown("### 📊 Execution Quality")
st.info("""
**Phase 2+ enhancements:**
- Slippage analysis
- Fill rate metrics
- Execution timing analysis
- Order flow visualization
- Market impact assessment
""")
