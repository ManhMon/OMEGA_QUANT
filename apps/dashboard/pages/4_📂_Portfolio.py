"""
Portfolio Page - Portfolio composition and holdings
"""
import streamlit as st
import sys
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASHBOARD_ROOT))

from config.dashboard_config import PAGE_TITLE, CUSTOM_CSS
from services.data_loader import DataLoaderService
import pandas as pd

st.set_page_config(page_title=f"{PAGE_TITLE} - Portfolio", page_icon="📂", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown("## 📂 Portfolio Overview")

# Load data
risk_status = DataLoaderService.load_risk_status()

if risk_status:
    portfolio = risk_status.get("portfolio", {})
    
    if portfolio:
        # Portfolio summary
        st.markdown("### Portfolio Summary")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_value = portfolio.get("total_value", 0)
            st.metric("Total Value", f"${total_value:,.2f}")
        
        with col2:
            cash = portfolio.get("cash", 0)
            st.metric("Cash", f"${cash:,.2f}")
        
        with col3:
            positions = portfolio.get("num_positions", 0)
            st.metric("Positions", positions)
        
        with col4:
            exposure = portfolio.get("market_exposure", 0)
            st.metric("Market Exposure", f"{exposure:.1%}")
        
        st.markdown("---")
        
        # Holdings table
        st.markdown("### Holdings")
        
        holdings = portfolio.get("holdings", [])
        if holdings:
            df_holdings = pd.DataFrame(holdings)
            
            # Format columns
            display_cols = ["symbol", "shares", "avg_price", "current_price", "value", "pnl", "pnl_pct"]
            available_cols = [col for col in display_cols if col in df_holdings.columns]
            
            if available_cols:
                st.dataframe(df_holdings[available_cols], width="stretch", hide_index=True)
            else:
                st.dataframe(df_holdings, width="stretch")
        else:
            st.info("No holdings data available.")
        
        # Sector allocation
        st.markdown("---")
        st.markdown("### Sector Allocation")
        
        sectors = portfolio.get("sectors", {})
        if sectors:
            df_sectors = pd.DataFrame([
                {"Sector": k, "Value": v} for k, v in sectors.items()
            ])
            df_sectors = df_sectors.sort_values("Value", ascending=False)
            
            st.dataframe(df_sectors, width="stretch", hide_index=True)
        else:
            st.info("No sector allocation data available.")
        
    else:
        st.info("No portfolio data available in risk status.")
else:
    st.info("No risk status data available. Run risk analysis to populate portfolio.")

st.markdown("---")

# Placeholder for future features
st.markdown("### 🚧 Planned Features")
st.info("""
**Phase 2+ enhancements:**
- Portfolio optimization recommendations
- Concentration risk analysis
- Correlation matrix
- Sector heatmap visualization
- Portfolio rebalancing suggestions
""")
