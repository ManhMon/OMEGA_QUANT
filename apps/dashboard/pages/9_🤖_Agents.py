"""
Agents Page - Agent role monitoring and SOD compliance
"""
import streamlit as st
import sys
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASHBOARD_ROOT))

from config.dashboard_config import PAGE_TITLE, CUSTOM_CSS, AGENT_ROLES
from services.data_loader import DataLoaderService
import pandas as pd
import plotly.express as px

st.set_page_config(page_title=f"{PAGE_TITLE} - Agents", page_icon="🤖", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown("## 🤖 Agent Roles & SOD Compliance")

st.markdown("""
OMEGA_QUANT operates with **25 specialized agent roles** organized in 3 tiers:
- **L1 (Ly)**: Orchestration and management
- **L2 (OpenCode)**: Build, code, and design
- **L3 (Codex)**: Audit, review, and security
""")

# Agent summary
col1, col2, col3 = st.columns(3)

with col1:
    l1_count = len([r for r in AGENT_ROLES if r["Tier"] == "L1"])
    st.metric("L1 Orchestrators", l1_count)

with col2:
    l2_count = len([r for r in AGENT_ROLES if r["Tier"] == "L2"])
    st.metric("L2 Builders", l2_count)

with col3:
    l3_count = len([r for r in AGENT_ROLES if r["Tier"] == "L3"])
    st.metric("L3 Auditors", l3_count)

st.markdown("---")

# Agent hierarchy visualization
st.markdown("### 🏢 Agent Hierarchy")

df_agents = pd.DataFrame(AGENT_ROLES)

fig = px.treemap(
    df_agents,
    path=["Tier", "Platform", "Name"],
    color="Tier",
    color_discrete_map={
        "L1": "#2196F3",
        "L2": "#4CAF50",
        "L3": "#F44336"
    },
    title="Agent Role Hierarchy"
)
fig.update_layout(height=500)
st.plotly_chart(fig, width="stretch")

st.markdown("---")

# Detailed agent table
st.markdown("### 📋 Agent Details")

# Add filters
col1, col2 = st.columns(2)

with col1:
    tier_filter = st.multiselect(
        "Filter by Tier",
        ["L1", "L2", "L3"],
        default=["L1", "L2", "L3"]
    )

with col2:
    platform_filter = st.multiselect(
        "Filter by Platform",
        ["Ly", "OpenCode", "Codex"],
        default=["Ly", "OpenCode", "Codex"]
    )

# Apply filters
filtered_agents = df_agents[
    (df_agents["Tier"].isin(tier_filter)) &
    (df_agents["Platform"].isin(platform_filter))
]

st.dataframe(filtered_agents, width="stretch", hide_index=True)

st.markdown("---")

# SOD Compliance
st.markdown("### 🔐 Segregation of Duties (SOD) Compliance")

st.markdown("""
**Core Principles:**
1. **1 Agent = 1 Role**: Each session spawns one agent with one role
2. **1 Agent = 1 Task**: Each agent receives one specific task
3. **Context Blindness**: Agents only receive minimal necessary context
4. **Strict Isolation**: No multi-role agents allowed
""")

# SOD rules
st.markdown("#### ✅ SOD Rules")

st.markdown("""
- **Writer ≠ Auditor**: Implementation and audit must be separate
- **L2 terminates before L3**: Build phase must complete before audit begins
- **No self-approval**: Agents cannot approve their own work
- **Gate Contract required**: All phases must pass through gates
""")

# Gate compliance
st.markdown("#### 🚪 Phase Gate Compliance")

phase_gates = DataLoaderService.load_phase_gates()

if phase_gates:
    st.success(f"✅ Found {len(phase_gates)} phase gates")
    
    # Gate status table
    gate_data = []
    for gate_id, gate_info in phase_gates.items():
        if isinstance(gate_info, dict):
            gate_data.append({
                "Gate ID": gate_id,
                "Status": gate_info.get("status", "Unknown"),
                "L2 Session": gate_info.get("l2_session_id", "N/A"),
                "L3 Session": gate_info.get("l3_session_id", "N/A"),
                "Verdict": gate_info.get("final_verdict", "Pending")
            })
    
    if gate_data:
        df_gates = pd.DataFrame(gate_data)
        st.dataframe(df_gates, width="stretch", hide_index=True)
        
        # Gate status distribution
        status_counts = df_gates["Status"].value_counts()
        fig_status = px.pie(
            values=status_counts.values,
            names=status_counts.index,
            title="Gate Status Distribution",
            color=status_counts.index,
            color_discrete_map={
                "COMPLETED": "#4CAF50",
                "IN_PROGRESS": "#FF9800",
                "PENDING": "#9E9E9E",
                "FAILED": "#F44336"
            }
        )
        st.plotly_chart(fig_status, width="stretch")
    
else:
    st.warning("⚠️ No phase gates found. Run workflow to generate gates.")

st.markdown("---")

# Audit Trail
st.markdown("### 📝 Audit Trail")

audit_log = DataLoaderService.load_audit_log()

if audit_log:
    st.success(f"✅ Found {len(audit_log)} audit log entries")
    
    df_audit = pd.DataFrame(audit_log)
    
    # Show recent entries
    st.markdown("#### Recent Audit Entries (Last 20)")
    st.dataframe(df_audit.tail(20), width="stretch", hide_index=True)
    
    # Audit statistics
    st.markdown("#### Audit Statistics")
    
    if "action" in df_audit.columns:
        action_counts = df_audit["action"].value_counts()
        fig_actions = px.bar(
            x=action_counts.index,
            y=action_counts.values,
            title="Audit Actions Distribution",
            labels={"x": "Action", "y": "Count"}
        )
        st.plotly_chart(fig_actions, width="stretch")
    
    if "role" in df_audit.columns:
        role_counts = df_audit["role"].value_counts()
        fig_roles = px.bar(
            x=role_counts.index,
            y=role_counts.values,
            title="Audit Activity by Role",
            labels={"x": "Role", "y": "Count"}
        )
        st.plotly_chart(fig_roles, width="stretch")
    
else:
    st.warning("⚠️ No audit log entries found.")

st.markdown("---")

# Platform Integration
st.markdown("### 🔌 Platform Integration")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("#### 🎵 Ly (L1)")
    st.markdown("""
    **Purpose:** Orchestration & Management
    
    **Agents:** 5 roles (PM, PO, SM, RM, DM)
    
    **Responsibilities:**
    - Task orchestration
    - Resource allocation
    - Progress tracking
    - Gate management
    """)

with col2:
    st.markdown("#### 💻 OpenCode (L2)")
    st.markdown("""
    **Purpose:** Build & Implement
    
    **Agents:** 11 roles (Architect to ML Engineer)
    
    **Responsibilities:**
    - System design
    - Code implementation
    - Testing
    - Documentation
    """)

with col3:
    st.markdown("#### 🔍 Codex (L3)")
    st.markdown("""
    **Purpose:** Audit & Review
    
    **Agents:** 9 roles (QA to IT Auditor)
    
    **Responsibilities:**
    - Code review
    - Security audit
    - Compliance check
    - Performance testing
    """)

st.markdown("---")

# Implementation roadmap
st.markdown("### 🚧 Implementation Roadmap")

st.markdown("""
**Phase 5 (Week 6-7):**

✅ **Real-time Agent Monitoring**
- Live agent status dashboard
- Active task tracking
- Resource utilization metrics
- Performance analytics

✅ **Enhanced Gate Visualization**
- Interactive gate flow diagrams
- Approval workflow visualization
- Bottleneck identification
- SLA compliance tracking

✅ **Agent Performance Metrics**
- Task completion rates
- Quality scores
- Efficiency metrics
- Historical performance trends

**Estimated Completion:** Week 7
""")
