"""
Risk Page - Risk metrics and monitoring
"""
import streamlit as st
import sys
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASHBOARD_ROOT))

from config.dashboard_config import PAGE_TITLE, CUSTOM_CSS
from services.data_loader import DataLoaderService
from ui.metrics import MetricCard
from ui.charts import ChartBuilder

st.set_page_config(page_title=f"{PAGE_TITLE} - Risk", page_icon="🛡️", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown("## 🛡️ Risk Monitor")

# Load data
risk_status = DataLoaderService.load_risk_status()

if risk_status:
    m = risk_status.get("metrics", {})
    
    # VaR and CVaR
    st.markdown("### Value at Risk (VaR)")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        MetricCard.render_var_95(m.get("var_95", 0.0))
    with col2:
        var_99 = m.get("var_99", 0.0)
        st.metric(label="VaR 99%", value=f"{var_99:.2%}", help="99% Value at Risk")
    with col3:
        cvar_95 = m.get("cvar_95", 0.0)
        var_95 = m.get("var_95", 0.0)
        MetricCard.render_cvar_95(cvar_95, var_95)
    with col4:
        cvar_99 = m.get("cvar_99", 0.0)
        st.metric(label="CVaR 99%", value=f"{cvar_99:.2%}", help="99% Conditional VaR")
    
    st.markdown("---")
    
    # Other risk metrics
    st.markdown("### Risk Metrics")
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        MetricCard.render_max_drawdown(m.get("max_drawdown", 0.0))
    with col6:
        MetricCard.render_beta(m.get("beta", 1.0))
    with col7:
        vol = m.get("volatility", 0.0)
        MetricCard.render_volatility(vol)
    with col8:
        exposure = m.get("exposure", 0.0)
        MetricCard.render_exposure(exposure)
    
    st.markdown("---")
    
    # Circuit Breaker Status
    st.markdown("### 🔐 Circuit Breaker Status")
    if risk_status.get("breached"):
        st.error("🔴 CIRCUIT BREAKER TRIGGERED")
        reasons = risk_status.get("breached_reasons", [])
        for reason in reasons:
            st.markdown(f"- {reason}")
    else:
        st.success("🟢 All circuit breakers NORMAL")
    
    # Risk gauges
    st.markdown("---")
    st.markdown("### Risk Gauges")
    
    col1, col2 = st.columns(2)
    
    with col1:
        max_dd = abs(m.get("max_drawdown", 0.0))
        fig1 = ChartBuilder.create_risk_metrics_gauge(
            value=max_dd,
            title="Max Drawdown",
            min_val=0,
            max_val=0.5,
            thresholds=[0.1, 0.2],
        )
        st.plotly_chart(fig1, width="stretch")
    
    with col2:
        var_95 = abs(m.get("var_95", 0.0))
        fig2 = ChartBuilder.create_risk_metrics_gauge(
            value=var_95,
            title="VaR 95%",
            min_val=0,
            max_val=0.1,
            thresholds=[0.02, 0.05],
        )
        st.plotly_chart(fig2, width="stretch")
    
    # Monte Carlo placeholder
    st.markdown("---")
    st.markdown("### 🎲 Monte Carlo Simulation")
    st.info("Monte Carlo simulation will be implemented in Phase 2 with GARCH(1,1) + Copula methods.")
    
else:
    st.info("No risk status data available. Run risk analysis to populate metrics.")
