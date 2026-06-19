"""
OMEGA_QUANT E2E Command Center
Full E2E topology + analytics + SRE + governance console.

Scope: End-to-end (data -> features -> alpha/model -> backtest -> portfolio
-> risk -> execution/OMS -> SRE -> governance/SOD -> dashboard).
All action buttons are SAFE mode: status/dry-run/read-only only.
No subprocess execution, no mutation, no live trading from UI.

Run: streamlit run apps/dashboard/Home.py
Then navigate to "Command Center" in the sidebar.
"""
import streamlit as st
import sys
from pathlib import Path
from datetime import datetime

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASHBOARD_ROOT))

from config.dashboard_config import (
    PAGE_TITLE, PAGE_ICON, LAYOUT, DASHBOARD_VERSION,
    CUSTOM_CSS, COMMAND_CENTER_VERSION, COMMAND_CENTER_READ_ONLY,
    COMMAND_CENTER_SECTIONS, COMMAND_CENTER_TABS, PHASE_DEFINITIONS,
    E2E_COMPONENT_DEFINITIONS, E2E_DEFAULT_MODE,
)
from services.data_loader import DataLoaderService

# -- Page Config ----------------------------------------------------------
st.set_page_config(
    page_title=f"E2E Command Center -- {PAGE_TITLE}",
    page_icon="🎯",
    layout=LAYOUT,
    initial_sidebar_state="expanded",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# -- Sidebar --------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🎯 E2E Command Center")
    st.markdown("**Full E2E Topology**")
    st.markdown(
        f"*v{COMMAND_CENTER_VERSION} | "
        f"SAFE: {'✅' if COMMAND_CENTER_READ_ONLY else '❌'}*"
    )
    st.markdown("---")

    e2e_summary = DataLoaderService.get_e2e_dashboard_summary()
    topo = e2e_summary["topology"]
    health_pct = topo["health_pct"]
    if health_pct >= 75:
        st.success(f"E2E Health: **{health_pct}%**")
    elif health_pct >= 50:
        st.warning(f"E2E Health: **{health_pct}%**")
    else:
        st.error(f"E2E Health: **{health_pct}%**")

    risk_state = e2e_summary["risk_state"]
    risk_emoji = {
        "RUNNING": "🟢", "BREACH": "🔴", "UNKNOWN": "🟡"
    }.get(risk_state, "🟡")
    st.markdown(f"**Risk:** {risk_emoji} `{risk_state}`")

    gates_ok = e2e_summary["gates_approved"]
    gates_total = e2e_summary["gates_total"]
    st.markdown(f"**Gates:** {gates_ok}/{gates_total}")

    st.markdown("---")
    st.markdown(f"*{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

# =========================================================================
# SECTION 1: Executive Header
# =========================================================================
st.markdown(
    '<div class="cmd-header">'
    '<h1>🎯 E2E Command Center</h1>'
    f'<div class="cmd-sub">Full E2E Topology | v{COMMAND_CENTER_VERSION} | '
    f'SAFE Mode: {"ACTIVE" if COMMAND_CENTER_READ_ONLY else "INACTIVE"} | '
    f'Mode: {E2E_DEFAULT_MODE} | '
    f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>'
    '</div>',
    unsafe_allow_html=True,
)

# Executive KPI Row
topology_data = DataLoaderService.get_e2e_topology()
risk_summary = DataLoaderService.get_risk_summary()
bt_summary = DataLoaderService.get_backtest_summary()
connectivity = DataLoaderService.get_phase_connectivity()

pass_phases = sum(1 for p in connectivity if p["status"] == "PASS")
total_phases = len(connectivity)

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    hp = topology_data["summary"]["health_pct"]
    hp_cls = "green" if hp >= 75 else "amber" if hp >= 50 else "red"
    st.markdown(
        f'<div class="metric-tile">'
        f'<div class="tile-label">E2E Readiness</div>'
        f'<div class="tile-value {hp_cls}">{hp}%</div>'
        f'<div class="tile-delta">'
        f'{topology_data["summary"]["ok"]}/{topology_data["summary"]["total"]} OK'
        f'</div></div>',
        unsafe_allow_html=True,
    )

with col2:
    sod_approved = e2e_summary["gates_approved"]
    sod_total = e2e_summary["gates_total"]
    st.markdown(
        f'<div class="metric-tile">'
        f'<div class="tile-label">SOD Gates</div>'
        f'<div class="tile-value {"green" if sod_approved == sod_total and sod_total > 0 else "amber"}">'
        f'{sod_approved}/{sod_total}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

with col3:
    comp_ok = topology_data["summary"]["ok"]
    comp_warn = topology_data["summary"]["warn"]
    comp_fail = topology_data["summary"]["fail"]
    st.markdown(
        f'<div class="metric-tile">'
        f'<div class="tile-label">Component Health</div>'
        f'<div class="tile-value {"green" if comp_fail == 0 else "red"}">'
        f'🟢{comp_ok} 🟡{comp_warn} 🔴{comp_fail}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

with col4:
    if risk_summary.get("available"):
        rs = risk_summary.get("system_state", "UNKNOWN")
        if risk_summary.get("breached"):
            risk_cls = "red"
            risk_txt = "🔴 BREACH"
        elif rs == "RUNNING":
            risk_cls = "green"
            risk_txt = "🟢 NORMAL"
        else:
            risk_cls = "amber"
            risk_txt = f"🟡 {rs}"
    else:
        risk_cls = "amber"
        risk_txt = "🟡 NO DATA"
    st.markdown(
        f'<div class="metric-tile">'
        f'<div class="tile-label">Risk / Kill-Switch</div>'
        f'<div class="tile-value {risk_cls}">{risk_txt}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

with col5:
    last_ts = topology_data.get("timestamp", "N/A")
    st.markdown(
        f'<div class="metric-tile">'
        f'<div class="tile-label">Last Verification</div>'
        f'<div class="tile-value" style="font-size:0.9rem">{last_ts[:19]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown('<hr class="cmd-divider">', unsafe_allow_html=True)

# =========================================================================
# SECTION 2: E2E Topology Map
# =========================================================================
st.markdown(
    '<div class="section-hdr"><h3>E2E Topology Map</h3></div>',
    unsafe_allow_html=True,
)

components = topology_data["components"]
edges = topology_data["edges"]

comp_keys_ordered = [
    "data", "feature_store", "alpha_model", "backtest", "portfolio",
    "risk", "execution", "sre", "governance", "dashboard",
]
visible_keys = [k for k in comp_keys_ordered if k in components]

topo_cols = st.columns(len(visible_keys))
for i, ck in enumerate(visible_keys):
    c = components[ck]
    status_cls_map = {
        "OK": "status-pass",
        "WARN": "status-warn",
        "OPTIONAL": "status-warn",
        "MISSING": "status-missing",
        "FAIL_CLOSED": "status-missing",
        "ERROR": "status-missing",
        "UNKNOWN": "status-missing",
    }
    pill_cls_map = {
        "OK": "pill-ok",
        "WARN": "pill-warn",
        "OPTIONAL": "pill-warn",
        "MISSING": "pill-error",
        "FAIL_CLOSED": "pill-error",
        "ERROR": "pill-error",
        "UNKNOWN": "pill-error",
    }
    s_cls = status_cls_map.get(c["status"], "status-missing")
    p_cls = pill_cls_map.get(c["status"], "pill-error")

    with topo_cols[i]:
        fc_badge = ""
        if c.get("fail_closed"):
            fc_badge = (
                '<div style="font-size:0.55rem;color:#FF3D00;'
                'margin-top:2px;font-family:Courier New,monospace">'
                'FAIL-CLOSED</div>'
            )
        st.markdown(
            f'<div class="phase-node {s_cls}">'
            f'<div class="pn-icon">{c["icon"]}</div>'
            f'<div class="pn-name">{c["name"]}</div>'
            f'<div class="pn-status">'
            f'<span class="pill {p_cls}">{c["status"]}</span>'
            f'</div>'
            f'{fc_badge}'
            f'</div>',
            unsafe_allow_html=True,
        )

with st.expander("Subsystem Details", expanded=False):
    for ck in visible_keys:
        c = components[ck]
        st.markdown(
            f"**{c['icon']} {c['name']}** ({c['status']}) "
            f"-- {c['description']}"
        )

st.markdown('<hr class="cmd-divider">', unsafe_allow_html=True)

# =========================================================================
# SECTION 3: Phase 1-5 Connectivity Map
# =========================================================================
st.markdown(
    '<div class="section-hdr"><h3>Phase 1-5 Connectivity</h3></div>',
    unsafe_allow_html=True,
)

connectivity = DataLoaderService.get_phase_connectivity()
phase_cols = st.columns([1, 0.3, 1, 0.3, 1, 0.3, 1, 0.3, 1])
for i, phase in enumerate(connectivity):
    col_idx = i * 2
    status_cls = {
        "PASS": "status-pass",
        "WARN": "status-warn",
        "MISSING": "status-missing",
    }.get(phase["status"], "status-missing")
    pill_cls = {
        "PASS": "pill-ok",
        "WARN": "pill-warn",
        "MISSING": "pill-error",
    }.get(phase["status"], "pill-error")

    with phase_cols[col_idx]:
        st.markdown(
            f'<div class="phase-node {status_cls}">'
            f'<div class="pn-icon">{phase["icon"]}</div>'
            f'<div class="pn-name">{phase["short"]}</div>'
            f'<div class="pn-status">'
            f'<span class="pill {pill_cls}">{phase["status"]}</span>'
            f'</div>'
            f'<div style="font-size:0.6rem;color:#666;margin-top:4px;'
            f'font-family:Courier New,monospace">'
            f'{phase["approved_count"]}/{phase["gate_count"]} gates</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if i < len(connectivity) - 1:
        with phase_cols[col_idx + 1]:
            next_status = connectivity[i + 1]["status"]
            arrow_color = (
                "#00C853"
                if (phase["status"] == "PASS" and next_status == "PASS")
                else "#FFB300"
                if (
                    phase["status"] != "MISSING"
                    and next_status != "MISSING"
                )
                else "#FF3D00"
            )
            st.markdown(
                f'<div class="phase-arrow" style="color:{arrow_color}">'
                f'-></div>',
                unsafe_allow_html=True,
            )

st.markdown('<hr class="cmd-divider">', unsafe_allow_html=True)

# =========================================================================
# SECTION 4: Safe Command Catalog (E2E + Phase buttons)
# =========================================================================
st.markdown(
    '<div class="section-hdr">'
    '<h3>Function Cards (SAFE Mode -- Read-Only)</h3></div>',
    unsafe_allow_html=True,
)

e2e_catalog = DataLoaderService.get_e2e_command_catalog()
phase_catalog = DataLoaderService.get_safe_command_catalog()
all_cards = e2e_catalog + phase_catalog

btn_cols = st.columns(3)
for idx, cmd in enumerate(all_cards):
    col = btn_cols[idx % 3]
    mode_badge = cmd.get("mode", "READ_ONLY")
    badge_color = (
        "#00C853" if mode_badge == "READ_ONLY"
        else "#FFB300" if mode_badge == "DRY_RUN"
        else "#FF3D00"
    )
    with col:
        st.markdown(
            f'<div class="action-card">'
            f'<div class="ac-label">{cmd["label"]}</div>'
            f'<div class="ac-desc">{cmd["description"]}</div>'
            f'<div class="ac-badge" style="color:{badge_color};'
            f'border-color:{badge_color};'
            f'background:rgba(0,200,83,0.08)">{mode_badge}</div>'
            f'<div style="font-size:0.6rem;color:#555;margin-top:3px;'
            f'font-family:Courier New,monospace">'
            f'$ {cmd["full_command"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        btn_key = f"btn_{cmd['id']}"
        if st.button(f"📋 Status: {cmd['label']}", key=btn_key):
            st.info(
                f"**{cmd['label']}** -- `{cmd['full_command']}`\n\n"
                f"Mode: **{mode_badge}**. "
                f"This button is **read-only/safe**. "
                f"No subprocess or mutation from the UI."
            )

st.markdown('<hr class="cmd-divider">', unsafe_allow_html=True)

# =========================================================================
# SECTION 5: CLI / E2E Trace Panel
# =========================================================================
st.markdown(
    '<div class="section-hdr"><h3>E2E Trace Panel</h3></div>',
    unsafe_allow_html=True,
)

trace_entries = DataLoaderService.get_latest_test_and_audit_trace()
trace_lines = []
for entry in trace_entries:
    etype = entry.get("type", "info")
    text = entry.get("text", "")
    css_cls = {
        "ok": "cli-ok", "warn": "cli-warn", "err": "cli-err",
        "prompt": "cli-prompt", "dim": "cli-dim", "info": "",
    }.get(etype, "")
    trace_lines.append(f'<span class="{css_cls}">{text}</span>')

trace_html = '<div class="cli-trace">' + "\n".join(trace_lines) + "</div>"
st.markdown(trace_html, unsafe_allow_html=True)

st.markdown('<hr class="cmd-divider">', unsafe_allow_html=True)

# =========================================================================
# SECTION 6: Detailed Tabs
# =========================================================================
st.markdown(
    '<div class="section-hdr"><h3>Detailed Tabs</h3></div>',
    unsafe_allow_html=True,
)

tabs = st.tabs(COMMAND_CENTER_TABS)
import pandas as pd

# -- Tab 1: E2E Topology -------------------------------------------------
with tabs[0]:
    st.markdown("#### E2E Artifact Status")
    artifacts = DataLoaderService.get_e2e_artifact_status()
    if artifacts:
        art_rows = []
        for a in artifacts:
            art_rows.append({
                "Artifact": a["label"],
                "Key": a["key"],
                "Required": "Yes" if a["required"] else "No",
                "Exists": "Yes" if a.get("exists") else "No",
                "Status": a["status"],
                "Size (MB)": a.get("size_mb", 0),
                "Age (hrs)": a.get("age_hours", "N/A"),
                "Freshness": a.get("freshness", "N/A"),
            })
        st.dataframe(
            pd.DataFrame(art_rows),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No artifact data available.")

# -- Tab 2: SOD / Gates --------------------------------------------------
with tabs[1]:
    st.markdown("#### SOD / Gate Compliance")
    gates = DataLoaderService.parse_phase_gates_flat()
    if gates:
        gate_rows = []
        for gk, gv in gates.items():
            if isinstance(gv, dict):
                verdict = gv.get("final_verdict", "PENDING")
                gate_rows.append({
                    "Gate": gk,
                    "Verdict": str(verdict).replace("[", "").replace("]", ""),
                    "L3 Session": gv.get("l3_session_id", "N/A"),
                    "L3 Role": gv.get("l3_role_name", "N/A"),
                    "Report": gv.get("audit_report_path", "N/A"),
                    "SOD": "pass" if gv.get("writer_auditor_separated") else "--",
                })
        if gate_rows:
            st.dataframe(
                pd.DataFrame(gate_rows),
                width="stretch",
                hide_index=True,
            )
    else:
        st.info("No phase gate data available.")

# -- Tab 3: Data Health --------------------------------------------------
with tabs[2]:
    st.markdown("#### Data File Health & Freshness")
    health = DataLoaderService.get_data_health_status()
    st.dataframe(
        pd.DataFrame(health),
        width="stretch",
        hide_index=True,
    )

# -- Tab 4: PIT / Backtest -----------------------------------------------
with tabs[3]:
    st.markdown("#### PIT / Backtest Summary")
    bt = DataLoaderService.get_backtest_summary()
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Backtests", bt.get("count", 0))
    col2.metric("Best Sharpe", f"{bt.get('best_sharpe', 0) or 0:.4f}")
    col3.metric("Latest Source", bt.get("latest_source", "N/A") or "N/A")

    results = DataLoaderService.load_backtest_results()
    if results:
        rows = []
        for r in results[:20]:
            m = r.get("metrics", r)
            rows.append({
                "Source": r.get("_source_file", "?"),
                "Sharpe": m.get("sharpe", m.get("sharpe_ratio", 0)),
                "Return": m.get("total_return", m.get("cumulative_return", 0)),
                "MaxDD": m.get("max_drawdown", m.get("max_dd", 0)),
                "WinRate": m.get("win_rate", 0),
                "Trades": m.get("num_trades", m.get("total_trades", 0)),
            })
        st.dataframe(
            pd.DataFrame(rows),
            width="stretch",
            hide_index=True,
        )

# -- Tab 5: Model / Evolution --------------------------------------------
with tabs[4]:
    st.markdown("#### Model / GP Evolution")
    alphas = DataLoaderService.load_evolved_alphas()
    if alphas:
        st.markdown(f"**Evolved Regimes:** {len(alphas)}")
        for rname, rdata in alphas.items():
            if isinstance(rdata, dict):
                al_list = rdata.get("alphas", rdata.get("programs", []))
                count = len(al_list) if isinstance(al_list, list) else 0
                st.markdown(f"- **{rname}**: {count} alphas/programs")
        st.json(alphas)
    else:
        st.info("No evolved alpha data available.")

# -- Tab 6: Portfolio / Risk ---------------------------------------------
with tabs[5]:
    st.markdown("#### Portfolio / Risk / Kill-Switch")
    risk = DataLoaderService.get_risk_summary()
    if risk.get("available"):
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("System State", risk["system_state"])
        col2.metric("Sharpe", f"{risk['sharpe_ratio']:.3f}")
        col3.metric("Max DD", f"{risk['max_drawdown']:.4f}")
        col4.metric("VaR 95%", f"{risk['var_95']:.4f}")
        col5.metric("Beta", f"{risk['portfolio_beta']:.3f}")

        if risk.get("breached"):
            st.error(
                f"CIRCUIT BREAKER TRIGGERED -- "
                f"{len(risk.get('breached_reasons', []))} reason(s)"
            )
            for r in risk.get("breached_reasons", []):
                st.markdown(f"- {r}")
        else:
            st.success("All circuit breakers NORMAL")
    else:
        st.warning(
            "No risk data. Risk/execution unknown -> FAIL-CLOSED. "
            "Run sod_gate_enforcer.py to generate."
        )

# -- Tab 7: Execution / OMS ----------------------------------------------
with tabs[6]:
    st.markdown("#### Execution / OMS / Orders")
    goal = DataLoaderService.load_goal_state()
    if goal:
        col1, col2, col3 = st.columns(3)
        col1.metric("Goal Step", goal.get("current_step", "N/A"))
        col2.metric("Goal Status", goal.get("status", "N/A"))
        col3.metric("Last Run", goal.get("last_run", "N/A"))
    else:
        st.warning(
            "No goal runner state. Execution unknown -> FAIL-CLOSED. "
            "No live trading or order submission."
        )

    st.markdown(
        "*Execution and OMS are status-only. "
        "No live trading or order submission from this UI.*"
    )

# -- Tab 8: SRE / Observability ------------------------------------------
with tabs[7]:
    st.markdown("#### SRE / Observability Console")
    obs = DataLoaderService.get_observability_status()
    col1, col2, col3 = st.columns(3)
    col1.metric("Audit Log Entries", obs.get("audit_log_entries", 0))
    col2.metric("Worker Heartbeats", obs.get("worker_heartbeats", 0))
    col3.metric("SAFE Mode", "pass" if obs.get("read_only_mode") else "FAIL")

    st.markdown(
        f"**Dashboard:** v{obs.get('dashboard_version', '?')} | "
        f"**Command Center:** v{obs.get('command_center_version', '?')}"
    )

    audit_logs = DataLoaderService.load_audit_log(max_lines=20)
    if audit_logs:
        st.dataframe(
            pd.DataFrame(audit_logs),
            width="stretch",
            hide_index=True,
        )

# -- Tab 9: Governance ---------------------------------------------------
with tabs[8]:
    st.markdown("#### Governance / SOD")
    gates = DataLoaderService.parse_phase_gates_flat()
    gate_total = len(gates)
    gate_approved = sum(
        1
        for v in gates.values()
        if isinstance(v, dict)
        and "APPROVED" in str(v.get("final_verdict", ""))
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Gates", gate_total)
    col2.metric("Approved", gate_approved)
    col3.metric("Pending", gate_total - gate_approved)

    st.markdown(f"**SOD Mode:** `{E2E_DEFAULT_MODE}`")
    st.markdown(
        f"**Read-Only:** "
        f"{'ACTIVE' if COMMAND_CENTER_READ_ONLY else 'INACTIVE'}"
    )

# -- Footer ---------------------------------------------------------------
st.markdown('<hr class="cmd-divider">', unsafe_allow_html=True)
st.markdown(
    f"*OMEGA_QUANT E2E Command Center v{COMMAND_CENTER_VERSION} | "
    f"Full E2E Topology | SAFE Mode: "
    f"{'ACTIVE' if COMMAND_CENTER_READ_ONLY else 'INACTIVE'} | "
    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
)
