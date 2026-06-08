"""
OMEGA_QUANT Dashboard - Home Page
Multi-page Streamlit entry point with 9 tabs.

Run: streamlit run apps/dashboard/Home.py
"""
import streamlit as st
import sys
from pathlib import Path

# Add dashboard to path for imports
DASHBOARD_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(DASHBOARD_ROOT))

from config.dashboard_config import (
    PAGE_TITLE, PAGE_ICON, LAYOUT, DASHBOARD_VERSION, CUSTOM_CSS,
)
from services.data_loader import DataLoaderService
from ui.metrics import MetricCard

# --- Page Config ---
st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout=LAYOUT,
    initial_sidebar_state="expanded",
)

# --- Inject CSS ---
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# --- Header ---
st.markdown('<p class="main-header">🧠 OMEGA_QUANT Dashboard</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Institutional Quant AI - 25-Agent System Monitoring</p>', unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.markdown("## 🧠 OMEGA_QUANT")
    st.markdown("**Institutional Quant AI System**")
    from datetime import datetime
    st.markdown(f"*Last refresh: {datetime.now().strftime('%H:%M:%S')}*")
    st.markdown("---")

    # System Status
    risk = DataLoaderService.load_risk_status()
    if risk:
        state = risk.get("system_state", "UNKNOWN")
        emoji = {"RUNNING": "🟢", "EMERGENCY_STOP": "🔴", "STOPPED": "⚪"}.get(state, "🟡")
        st.markdown(f"**System:** {emoji} `{state}`")
    else:
        st.markdown("**System:** 🟡 `No risk data`")

    # Phase Gates
    gates = DataLoaderService.load_phase_gates()
    st.markdown(f"**Phase Gates:** {len(gates)} phases tracked")

    # Evolved Alphas
    alphas = DataLoaderService.load_evolved_alphas()
    if alphas:
        st.markdown(f"**Alpha Regimes:** {len(alphas)}")

    st.markdown("---")
    st.markdown(f"*v{DASHBOARD_VERSION} - Multi-Page Dashboard*")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

# --- Main Content: Overview ---
st.markdown("## 📊 System Overview")

risk = DataLoaderService.load_risk_status()
backtest_results = DataLoaderService.load_backtest_results()

if risk:
    m = risk.get("metrics", {})

    # Top metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        sharpe = m.get("sharpe_ratio", 0.0)
        cls = "metric-card-green" if sharpe > 1.0 else "metric-card-orange" if sharpe > 0 else "metric-card-red"
        st.markdown(f'<div class="metric-card {cls}"><h3>Sharpe Ratio</h3><h1>{sharpe:.2f}</h1></div>', unsafe_allow_html=True)
    with col2:
        max_dd = m.get("max_drawdown", 0.0)
        cls = "metric-card-green" if max_dd < 0.1 else "metric-card-orange" if max_dd < 0.2 else "metric-card-red"
        st.markdown(f'<div class="metric-card {cls}"><h3>Max Drawdown</h3><h1>{max_dd:.2%}</h1></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="metric-card metric-card-blue"><h3>Backtests</h3><h1>{len(backtest_results)}</h1></div>', unsafe_allow_html=True)
    with col4:
        gates_data = DataLoaderService.load_phase_gates()
        approved = sum(1 for v in gates_data.values() if isinstance(v, dict) and (
            v.get("final_verdict", "").replace("[", "").replace("]", "") == "APPROVED"
            or v.get("status", "") == "APPROVED"
        ))
        st.markdown(f'<div class="metric-card"><h3>Gates Approved</h3><h1>{approved}/{len(gates_data)}</h1></div>', unsafe_allow_html=True)

    # System Health
    st.markdown("---")
    st.markdown("### 🏥 System Health")
    col_left, col_right = st.columns(2)

    with col_left:
        import pandas as pd
        health = {
            "Component": ["Dashboard Manager", "Risk Monitor", "Production Monitor",
                          "GP Evolution Engine", "Order Router", "Alpha Pipeline", "Walk-Forward Validator"],
            "Status": ["🟢 Active"] * 7,
        }
        if risk:
            st_ = risk.get("system_state", "")
            health["Status"][2] = f"🟢 {st_}" if st_ == "RUNNING" else f"🔴 {st_}"
            if risk.get("breached"):
                health["Status"][2] = "🔴 EMERGENCY_STOP"
        st.dataframe(pd.DataFrame(health), width="stretch", hide_index=True)

    with col_right:
        st.markdown("#### 🔐 Circuit Breaker")
        if risk.get("breached"):
            st.error("🔴 CIRCUIT BREAKER TRIGGERED")
            for r in risk.get("breached_reasons", []):
                st.markdown(f"- {r}")
        else:
            st.success("🟢 All breakers NORMAL")
        st.markdown(
            f"| Metric | Value |\n|:--|--:|\n"
            f"| VaR 95% | {m.get('var_95', 0):.4f} |\n"
            f"| CVaR 95% | {m.get('cvar_95', 0):.4f} |\n"
            f"| Beta | {m.get('portfolio_beta', 0):.3f} |\n"
            f"| Consec Losses | {m.get('consecutive_losses', 0)} |"
        )

    # Recent Audit Log
    st.markdown("### 📝 Recent Audit Log")
    audit_logs = DataLoaderService.load_audit_log()
    if audit_logs:
        log_df = pd.DataFrame(audit_logs[-10:])
        if "timestamp" in log_df.columns:
            log_df["timestamp"] = log_df["timestamp"].astype(str)
            log_df["timestamp"] = pd.to_datetime(
                log_df["timestamp"], utc=True, errors="coerce", format="mixed"
            ).dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(log_df, width="stretch", hide_index=True)
    else:
        st.info("No audit log entries.")
else:
    st.info("Run sod_gate_enforcer.py to generate risk data.")

# --- Navigation Guide ---
st.markdown("---")
st.markdown("### 📍 Navigate to:")
st.markdown(
    "- **📈 Performance** — Sharpe, Drawdown, Equity Curve, Attribution\n"
    "- **🛡️ Risk** — VaR, CVaR, Monte Carlo, Stress Tests\n"
    "- **📂 Portfolio** — Holdings, Allocation, Concentration\n"
    "- **💼 Trades** — Execution History, Fill Rates\n"
    "- **📥 Data Status** — Data Quality, Freshness, Downloads\n"
    "- **🧪 Backtest Runner** — Run backtests with options\n"
    "- **📉 Advanced Analytics** — Attribution, Alpha Decay, Reports\n"
    "- **🌊 Regime Detection** — Market Regimes, Regime-aware Metrics"
)

st.markdown("---")
st.markdown(f"*OMEGA_QUANT Dashboard v{DASHBOARD_VERSION} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
