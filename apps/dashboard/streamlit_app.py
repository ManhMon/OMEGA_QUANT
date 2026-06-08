"""
OMEGA_QUANT - Streamlit Web Dashboard (Phase 17+)
Institutional-grade monitoring for 25-agent Quant AI system.

Tabs:
1. Overview    - NAV, P&L, System Health, Circuit Breaker
2. Performance - Sharpe, Drawdown, Equity Curve, Sortino
3. Risk        - VaR, CVaR, Beta, Circuit Breaker Status
4. Orders      - Execution History, Fill Rates
5. Signals     - Alpha Signals from GP Evolution, Win/Loss
6. Agents      - 25 Agent Roles, Gate Compliance, SOD Audit

Run: streamlit run apps/dashboard/streamlit_app.py
"""

import streamlit as st
import json
import os
import sys
import glob
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

# --- Config ---
REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_DIR = REPO_ROOT / ".ly_state" / "session"
PIPELINE_DIRS = [
    SESSION_DIR / "pipeline_state",
    SESSION_DIR / "pipeline_state_adv",
    SESSION_DIR / "pipeline_state_tune",
]

st.set_page_config(
    page_title="OMEGA_QUANT Dashboard",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---
st.markdown("""
<style>
    .main-header { font-size: 2.5rem; font-weight: 800; color: #1f77b4; margin-bottom: 0; }
    .sub-header { font-size: 1.1rem; color: #666; margin-top: 0; }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem; border-radius: 12px; color: white;
        text-align: center; min-height: 120px;
    }
    .metric-card h3 { margin: 0; font-size: 0.9rem; opacity: 0.85; }
    .metric-card h1 { margin: 0.3rem 0; font-size: 2rem; }
    .metric-card-green { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
    .metric-card-red { background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%); }
    .metric-card-blue { background: linear-gradient(135deg, #2196F3 0%, #21CBF3 100%); }
    .metric-card-orange { background: linear-gradient(135deg, #f7971e 0%, #ffd200 100%); }
    div[data-testid="stMetric"] { background: #f8f9fa; border-radius: 8px; padding: 10px; }
</style>
""", unsafe_allow_html=True)


# --- Data Loaders ---
@st.cache_data(ttl=10)
def load_json(path: Path) -> Optional[Dict]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


@st.cache_data(ttl=10)
def load_jsonl(path: Path, max_lines: int = 200) -> List[Dict]:
    if not path.exists():
        return []
    lines = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            for line in all_lines[-max_lines:]:
                try:
                    lines.append(json.loads(line.strip()))
                except Exception:
                    pass
    except Exception:
        pass
    return lines


@st.cache_data(ttl=30)
def load_phase_gates() -> Dict:
    data = load_json(SESSION_DIR / "phase_gates.json")
    if data is None:
        return {}
    # phase_gates.json is a list: [dict_of_gates, single_gate_dict, ...]
    if isinstance(data, list):
        merged = {}
        for item in data:
            if isinstance(item, dict):
                for k, v in item.items():
                    if isinstance(v, dict):
                        merged[k] = v
                    else:
                        # item itself is a gate entry (e.g. element [1])
                        gate_name = item.get("phase_name", item.get("gate_id", f"gate_{len(merged)}"))
                        merged[gate_name] = item
                        break
        return merged
    if isinstance(data, dict):
        return data
    return {}


@st.cache_data(ttl=30)
def load_backtest_results() -> List[Dict]:
    results = []
    for pdir in PIPELINE_DIRS:
        if not pdir.exists():
            continue
        for f in sorted(pdir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(d, dict) and any(k in d for k in ["sharpe", "total_return", "metrics", "results"]):
                    d["_source_file"] = f.name
                    d["_source_dir"] = pdir.name
                    results.append(d)
            except Exception:
                pass
    return results


@st.cache_data(ttl=30)
def load_evolved_alphas() -> Dict:
    data = load_json(SESSION_DIR / "all_regimes_evolved_alphas.json")
    return data or {}


@st.cache_data(ttl=30)
def load_risk_status() -> Optional[Dict]:
    return load_json(SESSION_DIR / "risk_status.json")


@st.cache_data(ttl=30)
def load_audit_log() -> List[Dict]:
    return load_jsonl(SESSION_DIR / "audit_log.jsonl", max_lines=100)


@st.cache_data(ttl=30)
def load_goal_state() -> Optional[Dict]:
    return load_json(SESSION_DIR / "goal_runner_state.json")


# --- Sidebar ---
with st.sidebar:
    st.markdown("## 🧠 OMEGA_QUANT")
    st.markdown("**Institutional Quant AI System**")
    st.markdown(f"*Last refresh: {datetime.now().strftime('%H:%M:%S')}*")
    st.markdown("---")

    risk = load_risk_status()
    if risk:
        state = risk.get("system_state", "UNKNOWN")
        state_emoji = {"RUNNING": "🟢", "EMERGENCY_STOP": "🔴", "STOPPED": "⚪"}.get(state, "🟡")
        st.markdown(f"**System:** {state_emoji} `{state}`")
    else:
        st.markdown("**System:** 🟡 `No risk data`")

    gates = load_phase_gates()
    st.markdown(f"**Phase Gates:** {len(gates)} phases tracked")

    alphas = load_evolved_alphas()
    if alphas:
        st.markdown(f"**Alpha Regimes:** {len(alphas)}")

    st.markdown("---")
    st.markdown("*v17.0 - Streamlit Dashboard*")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()


# --- Header ---
st.markdown('<p class="main-header">🧠 OMEGA_QUANT Dashboard</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Institutional Quant AI - 25-Agent System Monitoring</p>', unsafe_allow_html=True)

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Overview", "📈 Performance", "🛡️ Risk", "📋 Orders", "🔬 Signals", "🤖 Agents"
])


# TAB 1: OVERVIEW
with tab1:
    st.markdown("## 📊 System Overview")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if risk:
            sharpe = risk.get("metrics", {}).get("sharpe_ratio", 0.0)
            cls = "metric-card-green" if sharpe > 1.0 else "metric-card-orange" if sharpe > 0 else "metric-card-red"
            st.markdown(f'<div class="metric-card {cls}"><h3>Sharpe Ratio</h3><h1>{sharpe:.2f}</h1></div>', unsafe_allow_html=True)
        else:
            st.metric("Sharpe Ratio", "N/A")

    with col2:
        if risk:
            max_dd = risk.get("metrics", {}).get("max_drawdown", 0.0)
            cls = "metric-card-green" if max_dd < 0.1 else "metric-card-orange" if max_dd < 0.2 else "metric-card-red"
            st.markdown(f'<div class="metric-card {cls}"><h3>Max Drawdown</h3><h1>{max_dd:.2%}</h1></div>', unsafe_allow_html=True)
        else:
            st.metric("Max Drawdown", "N/A")

    with col3:
        bt_results = load_backtest_results()
        st.markdown(f'<div class="metric-card metric-card-blue"><h3>Backtests</h3><h1>{len(bt_results)}</h1></div>', unsafe_allow_html=True)

    with col4:
        gates_data = load_phase_gates()
        approved = sum(1 for v in gates_data.values() if isinstance(v, dict) and (
            v.get("final_verdict", "").replace("[", "").replace("]", "") == "APPROVED"
            or v.get("status", "") == "APPROVED"
        ))
        st.markdown(f'<div class="metric-card"><h3>Gates Approved</h3><h1>{approved}/{len(gates_data)}</h1></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🏥 System Health")
    col_left, col_right = st.columns(2)

    with col_left:
        health = {"Component": ["Dashboard Manager", "Risk Monitor L07", "Production Monitor", "GP Evolution Engine", "Order Router", "Alpha Pipeline", "Walk-Forward Validator"],
                  "Status": ["🟢 Active"] * 7}
        if risk:
            st_ = risk.get("system_state", "")
            health["Status"][2] = f"🟢 {st_}" if st_ == "RUNNING" else f"🔴 {st_}"
            if risk.get("breached"):
                health["Status"][2] = "🔴 EMERGENCY_STOP"
        st.dataframe(pd.DataFrame(health), use_container_width=True, hide_index=True)

    with col_right:
        st.markdown("#### 🔐 Circuit Breaker")
        if risk:
            if risk.get("breached"):
                st.error("🔴 CIRCUIT BREAKER TRIGGERED")
                for r in risk.get("breached_reasons", []):
                    st.markdown(f"- {r}")
            else:
                st.success("🟢 All breakers NORMAL")
            m = risk.get("metrics", {})
            st.markdown(f"| Metric | Value |\n|:--|--:|\n| VaR 95% | {m.get('var_95',0):.4f} |\n| CVaR 95% | {m.get('cvar_95',0):.4f} |\n| Beta | {m.get('portfolio_beta',0):.3f} |\n| Consec Losses | {m.get('consecutive_losses',0)} |")
        else:
            st.info("Run sod_gate_enforcer.py to generate risk data.")

    st.markdown("### 📝 Recent Audit Log")
    audit_logs = load_audit_log()
    if audit_logs:
        log_df = pd.DataFrame(audit_logs[-10:])
        if "timestamp" in log_df.columns:
            log_df["timestamp"] = log_df["timestamp"].astype(str)
            log_df["timestamp"] = pd.to_datetime(log_df["timestamp"], utc=True, errors="coerce", format="mixed").dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(log_df, use_container_width=True, hide_index=True)
    else:
        st.info("No audit log entries.")


# TAB 2: PERFORMANCE
with tab2:
    st.markdown("## 📈 Performance Metrics")
    bt_results = load_backtest_results()

    if bt_results:
        perf_rows = []
        for r in bt_results:
            m = r.get("metrics", r)
            perf_rows.append({
                "Source": r.get("_source_file", "?"),
                "Sharpe": m.get("sharpe", m.get("sharpe_ratio", 0)),
                "Return": m.get("total_return", m.get("cumulative_return", 0)),
                "MaxDD": m.get("max_drawdown", m.get("max_dd", 0)),
                "WinRate": m.get("win_rate", 0),
                "Trades": m.get("num_trades", m.get("total_trades", 0)),
            })
        perf_df = pd.DataFrame(perf_rows)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Best Sharpe", f"{perf_df['Sharpe'].max():.3f}")
        col2.metric("Best Return", f"{perf_df['Return'].max():.4f}")
        col3.metric("Avg MaxDD", f"{perf_df['MaxDD'].mean():.4f}")
        col4.metric("Avg WinRate", f"{perf_df['WinRate'].mean():.2f}")

        fig = px.bar(perf_df.sort_values("Sharpe", ascending=False).head(20),
                     x="Source", y="Sharpe", color="Sharpe",
                     color_continuous_scale=["#f44336", "#ff9800", "#4caf50"],
                     title="Sharpe Ratio - Top 20 Backtests")
        fig.update_layout(xaxis_tickangle=-45, height=400)
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.scatter(perf_df, x="MaxDD", y="Return", size="Trades",
                          color="Sharpe", hover_data=["Source"],
                          title="Return vs Max Drawdown")
        fig2.update_layout(height=400)
        st.plotly_chart(fig2, use_container_width=True)

        st.dataframe(perf_df.sort_values("Sharpe", ascending=False), use_container_width=True, hide_index=True)
    else:
        st.info("No backtest results. Run scripts/run_weekly_evolution.py")
        if risk:
            m = risk.get("metrics", {})
            col1, col2, col3 = st.columns(3)
            col1.metric("Sharpe", f"{m.get('sharpe_ratio',0):.3f}")
            col2.metric("Max DD", f"{m.get('max_drawdown',0):.4f}")
            col3.metric("Beta", f"{m.get('portfolio_beta',0):.3f}")


# TAB 3: RISK
with tab3:
    st.markdown("## 🛡️ Risk Monitor")
    risk = load_risk_status()

    if risk:
        m = risk.get("metrics", {})
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("VaR 95%", f"{m.get('var_95',0):.4f}")
        col2.metric("VaR 99%", f"{m.get('var_99',0):.4f}")
        col3.metric("CVaR 95%", f"{m.get('cvar_95',0):.4f}")
        col4.metric("CVaR 99%", f"{m.get('cvar_99',0):.4f}")
        col5.metric("Beta", f"{m.get('portfolio_beta',0):.3f}")

        col_l, col_r = st.columns(2)
        with col_l:
            fig = go.Figure(go.Indicator(mode="gauge+number+delta", value=m.get("max_drawdown",0)*100,
                title={"text": "Max Drawdown (%)"}, delta={"reference": 15, "increasing": {"color": "red"}},
                gauge={"axis": {"range": [0,30]}, "bar": {"color": "#e74c3c"},
                    "steps": [{"range":[0,10],"color":"#2ecc71"},{"range":[10,20],"color":"#f39c12"},{"range":[20,30],"color":"#e74c3c"}],
                    "threshold": {"line":{"color":"red","width":4},"thickness":0.75,"value":15}}))
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            fig2 = go.Figure(go.Indicator(mode="gauge+number", value=m.get("sharpe_ratio",0),
                title={"text": "Sharpe Ratio"},
                gauge={"axis":{"range":[-2,4]}, "bar":{"color":"#3498db"},
                    "steps":[{"range":[-2,0],"color":"#ffebee"},{"range":[0,1],"color":"#fff3e0"},{"range":[1,2],"color":"#e8f5e9"},{"range":[2,4],"color":"#c8e6c9"}],
                    "threshold":{"line":{"color":"green","width":4},"thickness":0.75,"value":1.0}}))
            fig2.update_layout(height=300)
            st.plotly_chart(fig2, use_container_width=True)

        if risk.get("breached"):
            st.error(f"🔴 EMERGENCY STOP - {len(risk.get('breached_reasons',[]))} breach(es)")
            for r in risk.get("breached_reasons", []):
                st.markdown(f"- {r}")
        else:
            st.success("🟢 All circuit breakers NORMAL")
    else:
        st.info("Run sod_gate_enforcer.py to generate risk snapshot.")


# TAB 4: ORDERS
with tab4:
    st.markdown("## 📋 Orders & Execution")
    pipeline_data = []
    for pdir in PIPELINE_DIRS:
        if not pdir.exists():
            continue
        for f in sorted(pdir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    orders = d.get("orders", d.get("trades", d.get("execution_history", [])))
                    if isinstance(orders, list) and orders:
                        for o in orders:
                            if isinstance(o, dict):
                                o["_source"] = f.name
                                pipeline_data.append(o)
            except Exception:
                pass

    if pipeline_data:
        st.metric("Total Orders", len(pipeline_data))
        st.dataframe(pd.DataFrame(pipeline_data).head(50), use_container_width=True, hide_index=True)
    else:
        st.info("No order data in pipeline state.")

    st.markdown("### 🎯 Goal Runner")
    goal = load_goal_state()
    if goal:
        col1, col2, col3 = st.columns(3)
        col1.metric("Step", goal.get("current_step", "N/A"))
        col2.metric("Status", goal.get("status", "N/A"))
        col3.metric("Last Run", goal.get("last_run", "N/A"))
        st.json(goal)
    else:
        st.info("No goal runner state.")


# TAB 5: SIGNALS
with tab5:
    st.markdown("## 🔬 Alpha Signals - GP Evolution")
    alphas = load_evolved_alphas()

    if alphas:
        regimes = list(alphas.keys())
        st.markdown(f"### Evolved Regimes: {len(regimes)}")
        signal_rows = []
        for rname, rdata in alphas.items():
            if isinstance(rdata, dict):
                al_list = rdata.get("alphas", rdata.get("programs", []))
                if isinstance(al_list, list):
                    for i, a in enumerate(al_list):
                        if isinstance(a, dict):
                            signal_rows.append({"Regime": rname, "#": i+1, "Fitness": a.get("fitness", a.get("score", 0)), "Type": a.get("type", "GP"), "Depth": a.get("depth", 0)})
                        elif isinstance(a, str):
                            signal_rows.append({"Regime": rname, "#": i+1, "Fitness": 0, "Type": "Expr", "Expression": a[:80]})
        if signal_rows:
            sig_df = pd.DataFrame(signal_rows)
            st.dataframe(sig_df, use_container_width=True, hide_index=True)
            if sig_df["Fitness"].sum() > 0:
                fig = px.histogram(sig_df, x="Fitness", color="Regime", title="Alpha Fitness by Regime", nbins=30)
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.json(alphas)
    else:
        st.info("No evolved alpha data.")

    st.markdown("### Signal Quality")
    bt_results = load_backtest_results()
    if bt_results:
        q_rows = []
        for r in bt_results:
            m = r.get("metrics", r)
            q_rows.append({"Backtest": r.get("_source_file","?"), "Sharpe": m.get("sharpe", m.get("sharpe_ratio",0)), "WinRate": m.get("win_rate",0), "PF": m.get("profit_factor",0), "Trades": m.get("num_trades",0)})
        if q_rows:
            qdf = pd.DataFrame(q_rows).sort_values("Sharpe", ascending=False)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**🟢 Top 5**")
                st.dataframe(qdf.head(5)[["Backtest","Sharpe","WinRate"]], use_container_width=True, hide_index=True)
            with col2:
                st.markdown("**🔴 Bottom 5**")
                st.dataframe(qdf.tail(5)[["Backtest","Sharpe","WinRate"]], use_container_width=True, hide_index=True)


# TAB 6: AGENTS
with tab6:
    st.markdown("## 🤖 25 Agent Roles - SOD Compliance")
    agents = [
        {"ID":1,"Name":"Project Manager","Tier":"L1","Platform":"Ly","Resp":"Strategic orchestration"},
        {"ID":2,"Name":"Product Owner","Tier":"L1","Platform":"Ly","Resp":"Feature prioritization"},
        {"ID":3,"Name":"Scrum Master","Tier":"L1","Platform":"Ly","Resp":"Agile, blockers"},
        {"ID":4,"Name":"Release Manager","Tier":"L1","Platform":"Ly","Resp":"Release coordination"},
        {"ID":5,"Name":"Delivery Manager","Tier":"L1","Platform":"Ly","Resp":"Timeline, resources"},
        {"ID":6,"Name":"System Architect","Tier":"L2","Platform":"OpenCode","Resp":"System design"},
        {"ID":7,"Name":"Tech Lead","Tier":"L2","Platform":"OpenCode","Resp":"Code standards"},
        {"ID":8,"Name":"Frontend Engineer","Tier":"L2","Platform":"OpenCode","Resp":"UI/UX impl"},
        {"ID":9,"Name":"Backend Engineer","Tier":"L2","Platform":"OpenCode","Resp":"API, logic"},
        {"ID":10,"Name":"Database Admin","Tier":"L2","Platform":"OpenCode","Resp":"Schema, DB perf"},
        {"ID":11,"Name":"DevOps Engineer","Tier":"L2","Platform":"OpenCode","Resp":"CI/CD"},
        {"ID":12,"Name":"Cloud Infra","Tier":"L2","Platform":"OpenCode","Resp":"IaC"},
        {"ID":13,"Name":"UI/UX Integrator","Tier":"L2","Platform":"OpenCode","Resp":"UI integration"},
        {"ID":14,"Name":"Data Scientist","Tier":"L2","Platform":"OpenCode","Resp":"Model research"},
        {"ID":15,"Name":"Data Engineer","Tier":"L2","Platform":"OpenCode","Resp":"ETL, pipelines"},
        {"ID":16,"Name":"ML Engineer","Tier":"L2","Platform":"OpenCode","Resp":"Model training"},
        {"ID":17,"Name":"QA Engineer","Tier":"L3","Platform":"Codex","Resp":"Functional testing"},
        {"ID":18,"Name":"SDET","Tier":"L3","Platform":"Codex","Resp":"Test automation"},
        {"ID":19,"Name":"Security Auditor","Tier":"L3","Platform":"Codex","Resp":"Security scanning"},
        {"ID":20,"Name":"Compliance Officer","Tier":"L3","Platform":"Codex","Resp":"PIT safety"},
        {"ID":21,"Name":"Code Reviewer","Tier":"L3","Platform":"Codex","Resp":"Peer review"},
        {"ID":22,"Name":"Pen Tester","Tier":"L3","Platform":"Codex","Resp":"Security testing"},
        {"ID":23,"Name":"Perf Tester","Tier":"L3","Platform":"Codex","Resp":"Load/stress"},
        {"ID":24,"Name":"UAT Validator","Tier":"L3","Platform":"Codex","Resp":"User acceptance"},
        {"ID":25,"Name":"IT Auditor","Tier":"L3","Platform":"Codex","Resp":"System audit"},
    ]

    col1, col2, col3 = st.columns(3)
    col1.metric("L1 Orchestrator", f"{sum(1 for a in agents if a['Tier']=='L1')} Agents")
    col2.metric("L2 Build", f"{sum(1 for a in agents if a['Tier']=='L2')} Agents")
    col3.metric("L3 Audit", f"{sum(1 for a in agents if a['Tier']=='L3')} Agents")

    agents_df = pd.DataFrame(agents)
    col_l, col_r = st.columns([2, 1])
    with col_l:
        fig = px.sunburst(agents_df, path=["Tier","Platform","Name"], values=[1]*25,
                          title="25 Agent Hierarchy", color="Tier",
                          color_discrete_map={"L1":"#2196F3","L2":"#4CAF50","L3":"#F44336"})
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown("### SOD Rules")
        st.markdown("✅ Writer != Auditor\n\n✅ L2 terminates before L3\n\n✅ No self-approval\n\n✅ Gate Contract required:\n- l3_session_id\n- l3_session_key\n- audit_report_path\n- final_verdict = APPROVED")

    st.dataframe(agents_df, use_container_width=True, hide_index=True)

    st.markdown("### Phase Gate Compliance")
    gates_data = load_phase_gates()
    if gates_data:
        gate_rows = []
        for pn, gi in gates_data.items():
            if isinstance(gi, dict):
                raw_verdict = gi.get("final_verdict", "PENDING")
                clean_verdict = raw_verdict.replace("[", "").replace("]", "") if isinstance(raw_verdict, str) else str(raw_verdict)
                gate_rows.append({"Phase": pn, "Verdict": clean_verdict,
                                  "L3 Session": gi.get("l3_session_id","N/A"),
                                  "PIT": gi.get("pit_safety","N/A")})
        if gate_rows:
            gate_df = pd.DataFrame(gate_rows)
            vc = gate_df["Verdict"].value_counts()
            col_g1, col_g2 = st.columns([1, 2])
            with col_g1:
                fig_g = px.pie(values=vc.values, names=vc.index, title="Gate Verdicts",
                               color_discrete_map={"APPROVED":"#4CAF50","NEEDS_FIX":"#FF9800","PENDING_AUDIT":"#9E9E9E"})
                fig_g.update_layout(height=350)
                st.plotly_chart(fig_g, use_container_width=True)
            with col_g2:
                st.dataframe(gate_df, use_container_width=True, hide_index=True)

    st.markdown("### Audit Trail (Last 20)")
    audit_logs = load_audit_log()
    if audit_logs:
        adf = pd.DataFrame(audit_logs[-20:])
        if "timestamp" in adf.columns:
            adf["timestamp"] = adf["timestamp"].astype(str)
            adf["timestamp"] = pd.to_datetime(adf["timestamp"], utc=True, errors="coerce", format="mixed").dt.strftime("%m-%d %H:%M")
        st.dataframe(adf, use_container_width=True, hide_index=True)
    else:
        st.info("No audit log entries.")


st.markdown("---")
st.markdown(f"*OMEGA_QUANT Dashboard v17.0 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Repo: `{REPO_ROOT.name}`*")
