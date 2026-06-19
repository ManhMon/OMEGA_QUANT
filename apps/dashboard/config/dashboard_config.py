"""
OMEGA_QUANT Dashboard Configuration
Central config for multi-page Streamlit dashboard.
"""
from pathlib import Path
from typing import List

# --- Paths ---
REPO_ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_ROOT = REPO_ROOT / "apps" / "dashboard"
SESSION_DIR = REPO_ROOT / ".ly_state" / "session"
DATA_DIR = REPO_ROOT / "data"
SCRIPTS_DIR = REPO_ROOT / "scripts"
SRC_DIR = REPO_ROOT / "src"

# --- Pipeline State Directories ---
PIPELINE_DIRS: List[Path] = [
    SESSION_DIR / "pipeline_state",
    SESSION_DIR / "pipeline_state_adv",
    SESSION_DIR / "pipeline_state_tune",
]

# --- Data Files ---
MARKET_DATA_FILE = DATA_DIR / "market_2015_now.parquet"
FEATURES_DATA_FILE = DATA_DIR / "features_full_2015_now.parquet"
SECTOR_MAPPING_FILE = DATA_DIR / "sector_mapping_level2.csv"

# --- Canonical VCI Updater Paths ---
MARKET_UPDATE_SCRIPT = SCRIPTS_DIR / "update_market_data.py"
VCI_UNIVERSE_FILE = SESSION_DIR / "vci_universe_hsx_hnx.json"
MARKET_UPDATE_RESULT_FILE = SESSION_DIR / "update_market_data_result.json"
LEGACY_LOADER_INVENTORY_JSON = SESSION_DIR / "legacy_data_loader_inventory_20260613.json"
LEGACY_LOADER_INVENTORY_MD = SESSION_DIR / "legacy_data_loader_inventory_20260613.md"
MARKET_UPDATE_LOCK_FILE = SESSION_DIR / "market_update.lock"

# --- Backtest Scripts ---
BACKTEST_SCRIPT = SCRIPTS_DIR / "run_phase35_backtest.py"
EVOLUTION_SCRIPT = SCRIPTS_DIR / "run_weekly_evolution.py"
REGIME_SCRIPT = SCRIPTS_DIR / "run_regime_detection.py"
ATTRIBUTION_SCRIPT = SCRIPTS_DIR / "run_attribution.py"

# --- State Files ---
RISK_STATUS_FILE = SESSION_DIR / "risk_status.json"
PHASE_GATES_FILE = SESSION_DIR / "phase_gates.json"
AUDIT_LOG_FILE = SESSION_DIR / "audit_log.jsonl"
EVOLVED_ALPHAS_FILE = SESSION_DIR / "all_regimes_evolved_alphas.json"
GOAL_STATE_FILE = SESSION_DIR / "goal_runner_state.json"
BACKTEST_LOCK_FILE = SESSION_DIR / "backtest.lock"

# --- Dashboard Settings ---
DASHBOARD_VERSION = "18.0"
PAGE_TITLE = "OMEGA_QUANT Dashboard"
PAGE_ICON = "🧠"
LAYOUT = "wide"

# --- Cache TTL (seconds) ---
CACHE_TTL_FAST = 10       # Frequently changing data (risk status)
CACHE_TTL_MEDIUM = 30     # Medium frequency (phase gates, backtests)
CACHE_TTL_SLOW = 300      # Slowly changing (data files metadata)

# --- Performance Limits ---
MAX_AUDIT_LOG_LINES = 200
MAX_BACKTEST_RESULTS = 500
MAX_ORDERS_DISPLAY = 100
MAX_MEMORY_MB = 4096      # 4GB RAM cap for dashboard

# --- Monte Carlo Settings ---
MC_DEFAULT_SIMULATIONS = 10000
MC_DEFAULT_HORIZON = 252  # 1 trading year
MC_DEFAULT_CONFIDENCE = 0.95
MC_MIN_CONFIDENCE = 0.50
MC_MAX_CONFIDENCE = 0.999

# --- Backtest Settings ---
BACKTEST_DEFAULT_CAPITAL = 1_000_000_000  # 1B VND
BACKTEST_MIN_CAPITAL = 10_000_000
BACKTEST_MAX_CAPITAL = 100_000_000_000
BACKTEST_MAX_YEARS = 10
BACKTEST_QUICK_MAX_TICKERS = 1
BACKTEST_QUICK_MAX_YEARS = 1

# --- Regime Detection ---
REGIME_DEFAULT_N = 3      # Bull, Bear, Sideways
REGIME_LABELS = {
    0: ("🐂 Bull Market", "green"),
    1: ("🐻 Bear Market", "red"),
    2: ("➡️ Sideways", "orange"),
}

# --- CSS: Bloomberg Command Center Theme ---
CUSTOM_CSS = """
<style>
    /* ── Global Shell ────────────────────────────────────────────────── */
    .stApp { background: #0D0D0D; color: #D4D4D4; }
    section[data-testid="stSidebar"] { background: #111111; }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown li { color: #B0B0B0; }

    /* ── Typography ──────────────────────────────────────────────────── */
    h1, h2, h3 { color: #E8E8E8; font-family: 'Inter', 'Segoe UI', system-ui, sans-serif; }
    .stMarkdown p, .stMarkdown li { color: #C0C0C0; }
    .stMarkdown code { color: #FFB300; background: #1A1A1A; padding: 2px 6px; border-radius: 3px; }

    /* ── Command Header ──────────────────────────────────────────────── */
    .cmd-header {
        background: linear-gradient(135deg, #141414 0%, #1C1C1C 100%);
        border-left: 4px solid #FFB300;
        padding: 1.2rem 1.5rem; border-radius: 4px;
        margin-bottom: 0.8rem;
    }
    .cmd-header h1 { margin: 0; font-size: 1.6rem; color: #FFB300; font-weight: 700; letter-spacing: 0.5px; }
    .cmd-header .cmd-sub { color: #888; font-size: 0.82rem; font-family: 'Courier New', monospace; margin-top: 4px; }

    /* ── Section Headers ─────────────────────────────────────────────── */
    .section-hdr {
        border-bottom: 2px solid #FFB300;
        padding-bottom: 6px; margin: 1.2rem 0 0.8rem 0;
    }
    .section-hdr h3 { margin: 0; font-size: 1.05rem; color: #FFB300; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; }

    /* ── Metric Tiles (dark institutional) ───────────────────────────── */
    .metric-tile {
        background: #161616; border: 1px solid #2A2A2A; border-radius: 6px;
        padding: 1rem 1.2rem; text-align: center; min-height: 90px;
        transition: border-color 0.2s;
    }
    .metric-tile:hover { border-color: #FFB300; }
    .metric-tile .tile-label { font-size: 0.7rem; color: #888; text-transform: uppercase; letter-spacing: 1.2px; font-family: 'Courier New', monospace; }
    .metric-tile .tile-value { font-size: 1.5rem; color: #E8E8E8; font-weight: 700; margin: 4px 0; }
    .metric-tile .tile-value.green { color: #00C853; }
    .metric-tile .tile-value.amber { color: #FFB300; }
    .metric-tile .tile-value.red { color: #FF3D00; }
    .metric-tile .tile-delta { font-size: 0.75rem; color: #666; font-family: 'Courier New', monospace; }

    /* ── Status Pills ────────────────────────────────────────────────── */
    .pill {
        display: inline-block; padding: 3px 12px; border-radius: 12px;
        font-size: 0.72rem; font-weight: 600; letter-spacing: 0.8px;
        font-family: 'Courier New', monospace; text-transform: uppercase;
    }
    .pill-ok { background: rgba(0,200,83,0.15); color: #00C853; border: 1px solid rgba(0,200,83,0.3); }
    .pill-warn { background: rgba(255,179,0,0.15); color: #FFB300; border: 1px solid rgba(255,179,0,0.3); }
    .pill-error { background: rgba(255,61,0,0.15); color: #FF3D00; border: 1px solid rgba(255,61,0,0.3); }
    .pill-info { background: rgba(41,121,255,0.15); color: #448AFF; border: 1px solid rgba(41,121,255,0.3); }

    /* ── Operator Panel ──────────────────────────────────────────────── */
    .op-panel {
        background: #141414; border: 1px solid #2A2A2A; border-radius: 6px;
        padding: 1.2rem; margin-bottom: 1rem;
    }
    .op-panel-warn {
        background: rgba(255,179,0,0.06); border: 1px solid rgba(255,179,0,0.25);
        border-radius: 6px; padding: 0.8rem 1rem; margin: 0.5rem 0;
        color: #FFB300; font-size: 0.85rem;
    }
    .op-panel-danger {
        background: rgba(255,61,0,0.06); border: 1px solid rgba(255,61,0,0.25);
        border-radius: 6px; padding: 0.8rem 1rem; margin: 0.5rem 0;
        color: #FF3D00; font-size: 0.85rem;
    }

    /* ── Log / Terminal Panel ────────────────────────────────────────── */
    .log-panel {
        background: #0A0A0A; border: 1px solid #222; border-radius: 4px;
        padding: 1rem; font-family: 'Courier New', monospace; font-size: 0.78rem;
        color: #888; line-height: 1.6; max-height: 320px; overflow-y: auto;
    }
    .log-panel .log-ok { color: #00C853; }
    .log-panel .log-warn { color: #FFB300; }
    .log-panel .log-err { color: #FF3D00; }
    .log-panel .log-ts { color: #555; }

    /* ── Data Health Matrix ──────────────────────────────────────────── */
    .health-grid {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 8px; margin: 0.5rem 0;
    }
    .health-cell {
        background: #161616; border: 1px solid #222; border-radius: 4px;
        padding: 0.6rem 0.8rem; text-align: center;
    }
    .health-cell .hc-label { font-size: 0.65rem; color: #666; text-transform: uppercase; letter-spacing: 1px; font-family: 'Courier New', monospace; }
    .health-cell .hc-val { font-size: 1.1rem; font-weight: 700; color: #E8E8E8; margin-top: 2px; }
    .health-cell .hc-val.ok { color: #00C853; }
    .health-cell .hc-val.warn { color: #FFB300; }
    .health-cell .hc-val.err { color: #FF3D00; }

    /* ── Hash / Mono Microcopy ────────────────────────────────────────── */
    .mono-micro {
        font-family: 'Courier New', monospace; font-size: 0.72rem;
        color: #666; word-break: break-all; letter-spacing: 0.3px;
    }

    /* ── Freshness Indicator ─────────────────────────────────────────── */
    .fresh-bar {
        height: 4px; border-radius: 2px; margin-top: 4px;
    }
    .fresh-ok { background: #00C853; }
    .fresh-warn { background: #FFB300; }
    .fresh-stale { background: #FF3D00; }

    /* ── Divider ─────────────────────────────────────────────────────── */
    .cmd-divider {
        border: 0; height: 1px; background: #2A2A2A;
        margin: 1rem 0;
    }

    /* ── Override Streamlit defaults for dark theme ──────────────────── */
    div[data-testid="stMetric"] {
        background: #161616; border: 1px solid #2A2A2A; border-radius: 6px;
        padding: 10px 14px;
    }
    div[data-testid="stMetric"] label { color: #888; }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] { color: #E8E8E8; }

    /* ── Status helpers (legacy compat) ─────────────────────────────── */
    .main-header { font-size: 1.6rem; font-weight: 700; color: #FFB300; margin-bottom: 0; }
    .sub-header { font-size: 0.82rem; color: #888; margin-top: 0; font-family: 'Courier New', monospace; }
    .metric-card {
        background: #161616; border: 1px solid #2A2A2A;
        padding: 1.2rem; border-radius: 6px; color: #E8E8E8;
        text-align: center; min-height: 90px;
    }
    .metric-card h3 { margin: 0; font-size: 0.7rem; color: #888; text-transform: uppercase; letter-spacing: 1.2px; }
    .metric-card h1 { margin: 0.3rem 0; font-size: 1.5rem; color: #E8E8E8; }
    .metric-card-green { border-left: 3px solid #00C853; }
    .metric-card-red { border-left: 3px solid #FF3D00; }
    .metric-card-blue { border-left: 3px solid #448AFF; }
    .metric-card-orange { border-left: 3px solid #FFB300; }
    .status-ok { color: #00C853; font-weight: bold; }
    .status-warn { color: #FFB300; font-weight: bold; }
    .status-error { color: #FF3D00; font-weight: bold; }

    /* ── Expander styling ────────────────────────────────────────────── */
    .streamlit-expanderHeader { color: #B0B0B0; font-size: 0.85rem; }
    .streamlit-expanderContent { background: #111; border: 1px solid #222; border-radius: 4px; }

    /* ── Dataframe styling ───────────────────────────────────────────── */
    .stDataFrame { border: 1px solid #222; border-radius: 4px; }

    /* ── Command Center: Phase Map ───────────────────────────────────── */
    .phase-map-grid {
        display: grid; grid-template-columns: repeat(5, 1fr);
        gap: 10px; margin: 0.8rem 0;
    }
    .phase-node {
        background: #161616; border: 1px solid #2A2A2A; border-radius: 6px;
        padding: 0.8rem; text-align: center; position: relative;
        transition: border-color 0.2s, box-shadow 0.2s;
    }
    .phase-node:hover { border-color: #FFB300; box-shadow: 0 0 8px rgba(255,179,0,0.15); }
    .phase-node .pn-icon { font-size: 1.4rem; margin-bottom: 4px; }
    .phase-node .pn-name { font-size: 0.72rem; color: #B0B0B0; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; font-family: 'Courier New', monospace; }
    .phase-node .pn-status { margin-top: 6px; }
    .phase-node.status-pass { border-left: 3px solid #00C853; }
    .phase-node.status-warn { border-left: 3px solid #FFB300; }
    .phase-node.status-missing { border-left: 3px solid #FF3D00; }
    .phase-arrow {
        display: flex; align-items: center; justify-content: center;
        color: #444; font-size: 1.2rem; font-family: 'Courier New', monospace;
    }

    /* ── Command Center: Action Button Grid ──────────────────────────── */
    .action-grid {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 8px; margin: 0.8rem 0;
    }
    .action-card {
        background: #141414; border: 1px solid #2A2A2A; border-radius: 6px;
        padding: 0.7rem 0.9rem; cursor: default;
        transition: border-color 0.2s;
    }
    .action-card:hover { border-color: #FFB300; }
    .action-card .ac-label { font-size: 0.78rem; color: #E8E8E8; font-weight: 600; }
    .action-card .ac-desc { font-size: 0.65rem; color: #888; margin-top: 2px; font-family: 'Courier New', monospace; }
    .action-card .ac-badge { display: inline-block; margin-top: 4px; font-size: 0.6rem; padding: 1px 6px; border-radius: 8px; background: rgba(0,200,83,0.12); color: #00C853; border: 1px solid rgba(0,200,83,0.2); font-family: 'Courier New', monospace; text-transform: uppercase; letter-spacing: 0.5px; }

    /* ── Command Center: CLI Trace ───────────────────────────────────── */
    .cli-trace {
        background: #050505; border: 1px solid #1A1A1A; border-radius: 4px;
        padding: 1rem; font-family: 'Courier New', 'Fira Code', monospace;
        font-size: 0.74rem; color: #7C7C7C; line-height: 1.7;
        max-height: 380px; overflow-y: auto; white-space: pre-wrap;
    }
    .cli-trace .cli-prompt { color: #FFB300; }
    .cli-trace .cli-ok { color: #00C853; }
    .cli-trace .cli-warn { color: #FFB300; }
    .cli-trace .cli-err { color: #FF3D00; }
    .cli-trace .cli-dim { color: #444; }

    /* ── Command Center: Executive KPI Row ───────────────────────────── */
    .exec-kpi-row {
        display: grid; grid-template-columns: repeat(5, 1fr);
        gap: 10px; margin: 0.5rem 0 1rem 0;
    }
</style>
"""

# --- Command Center: Phase 1-5 Definitions ---
COMMAND_CENTER_VERSION = "2.0.0"
COMMAND_CENTER_READ_ONLY = True  # No subprocess execution from UI buttons

PHASE_DEFINITIONS = {
    "phase1": {
        "id": 1,
        "name": "Data Foundation",
        "short": "P1: Data",
        "description": "Registry, sanitizer, canonical data, VCI universe",
        "gate_keys": [
            "OMEGA_GAP_PHASE1_FOUNDATION",
            "VNSTOCK_LATEST_STANDARDIZATION_20260612",
        ],
        "icon": "📦",
    },
    "phase2": {
        "id": 2,
        "name": "Data Storage & Features",
        "short": "P2: Features",
        "description": "Feature/model registry, artifact layer, parquet storage",
        "gate_keys": [
            "OMEGA_GAP_PHASE2_DATA_STORAGE",
        ],
        "icon": "🗄️",
    },
    "phase3": {
        "id": 3,
        "name": "Memory, Quant & Backtest",
        "short": "P3: Quant",
        "description": "GP evolution, backtest engine, execution simulator, CPCV",
        "gate_keys": [
            "PHASE_35_CANONICAL_MIGRATION_20260521",
        ],
        "icon": "🧪",
    },
    "phase4": {
        "id": 4,
        "name": "Live Adapter & OMS",
        "short": "P4: Execution",
        "description": "Live adapter, OMS, reconciliation, risk control",
        "gate_keys": [
            "phase16_execution_gate",
        ],
        "icon": "⚡",
    },
    "phase5": {
        "id": 5,
        "name": "Observability & SRE",
        "short": "P5: SRE",
        "description": "Observability, deployment, failover, SRE console",
        "gate_keys": [
            "architecture_gate",
        ],
        "icon": "🔭",
    },
}

# Phase 6 is explicitly EXCLUDED from Command Center scope
PHASE6_EXCLUDED = True

# ── E2E Status Modes ────────────────────────────────────────────────────
STATUS_MODE_READ_ONLY = "READ_ONLY"
STATUS_MODE_DRY_RUN = "DRY_RUN"
STATUS_MODE_MUTATING_BLOCKED = "MUTATING_BLOCKED"
E2E_DEFAULT_MODE = STATUS_MODE_READ_ONLY

# ── E2E Component Definitions (full topology) ──────────────────────────
E2E_COMPONENT_DEFINITIONS = {
    "data": {
        "name": "Data Foundation",
        "icon": "📦",
        "description": "Market data, VCI universe, canonical parquet, registry",
        "artifact_keys": ["market_data", "vci_universe", "sector_mapping"],
        "fail_closed": False,
    },
    "feature_store": {
        "name": "Feature Store",
        "icon": "🗄️",
        "description": "Feature engineering, model registry, artifact layer",
        "artifact_keys": ["features_data", "legacy_loader_inventory"],
        "fail_closed": False,
    },
    "alpha_model": {
        "name": "Alpha / Model",
        "icon": "🧬",
        "description": "GP evolution, alpha programs, regime models",
        "artifact_keys": ["evolved_alphas"],
        "fail_closed": False,
    },
    "backtest": {
        "name": "Backtest Engine",
        "icon": "🧪",
        "description": "Backtest results, walk-forward, CPCV",
        "artifact_keys": ["backtest_results", "walk_forward_log"],
        "fail_closed": False,
    },
    "portfolio": {
        "name": "Portfolio",
        "icon": "💼",
        "description": "Portfolio construction, PnL tracking",
        "artifact_keys": ["pnl_latest"],
        "fail_closed": False,
    },
    "risk": {
        "name": "Risk / Kill-Switch",
        "icon": "🛡️",
        "description": "Risk metrics, circuit breakers, kill-switch",
        "artifact_keys": ["risk_status"],
        "fail_closed": True,
    },
    "execution": {
        "name": "Execution / OMS",
        "icon": "⚡",
        "description": "Live adapter, OMS, order routing, reconciliation",
        "artifact_keys": ["goal_state"],
        "fail_closed": True,
    },
    "sre": {
        "name": "SRE / Observability",
        "icon": "🔭",
        "description": "Monitoring, audit log, heartbeat, SRE console",
        "artifact_keys": ["audit_log", "worker_heartbeat"],
        "fail_closed": False,
    },
    "governance": {
        "name": "Governance / SOD",
        "icon": "🏛️",
        "description": "Phase gates, SOD enforcement, audit reports",
        "artifact_keys": ["phase_gates", "audit_reports_dir"],
        "fail_closed": False,
    },
    "dashboard": {
        "name": "Dashboard",
        "icon": "🎯",
        "description": "Command Center, Streamlit dashboard, E2E view",
        "artifact_keys": [],
        "fail_closed": False,
    },
}

# ── E2E Artifact Catalog (file paths for health probing) ───────────────
E2E_ARTIFACT_CATALOG = {
    "market_data": {
        "label": "Canonical Market Parquet",
        "path_key": "MARKET_DATA_FILE",
        "required": True,
    },
    "vci_universe": {
        "label": "VCI Universe (HSX/HNX)",
        "path_key": "VCI_UNIVERSE_FILE",
        "required": True,
    },
    "sector_mapping": {
        "label": "Sector Mapping",
        "path_key": "SECTOR_MAPPING_FILE",
        "required": False,
    },
    "features_data": {
        "label": "Features Parquet",
        "path_key": "FEATURES_DATA_FILE",
        "required": True,
    },
    "legacy_loader_inventory": {
        "label": "Legacy Loader Inventory",
        "path_key": "LEGACY_LOADER_INVENTORY_JSON",
        "required": False,
    },
    "evolved_alphas": {
        "label": "Evolved Alphas (all regimes)",
        "path_key": "EVOLVED_ALPHAS_FILE",
        "required": False,
    },
    "backtest_results": {
        "label": "Backtest Results (pipeline dirs)",
        "path_key": "PIPELINE_DIRS",
        "required": False,
    },
    "walk_forward_log": {
        "label": "Walk-Forward Log",
        "path_key": "WALK_FORWARD_LOG",
        "required": False,
    },
    "pnl_latest": {
        "label": "Latest PnL",
        "path_key": "PNL_LATEST_FILE",
        "required": False,
    },
    "risk_status": {
        "label": "Risk Status JSON",
        "path_key": "RISK_STATUS_FILE",
        "required": True,
    },
    "goal_state": {
        "label": "Goal Runner State",
        "path_key": "GOAL_STATE_FILE",
        "required": False,
    },
    "audit_log": {
        "label": "Audit Log (JSONL)",
        "path_key": "AUDIT_LOG_FILE",
        "required": False,
    },
    "worker_heartbeat": {
        "label": "Worker Heartbeat",
        "path_key": "WORKER_HEARTBEAT_FILE",
        "required": False,
    },
    "phase_gates": {
        "label": "Phase Gates JSON",
        "path_key": "PHASE_GATES_FILE",
        "required": True,
    },
    "audit_reports_dir": {
        "label": "Audit Reports Directory",
        "path_key": "AUDIT_REPORTS_DIR",
        "required": False,
    },
}

# Additional artifact paths for E2E
WALK_FORWARD_LOG = SESSION_DIR / "walk_forward.log"
PNL_LATEST_FILE = SESSION_DIR / "pnl_latest.json"
WORKER_HEARTBEAT_FILE = SESSION_DIR / "worker_heartbeat.jsonl"
AUDIT_REPORTS_DIR = SESSION_DIR / "audit_reports"

# ── E2E Command Catalog (SAFE mode: status/dry-run/read-only only) ────
E2E_COMMAND_CATALOG = [
    {
        "id": "e2e_topology_check",
        "label": "E2E Topology Health",
        "description": "Full E2E subsystem health check",
        "script": "scripts/sod_gate_enforcer.py",
        "args": ["--informational"],
        "category": "e2e",
        "mode": STATUS_MODE_READ_ONLY,
        "read_only": True,
    },
    {
        "id": "e2e_artifact_probe",
        "label": "Artifact Status Probe",
        "description": "Probe all E2E artifacts for existence/freshness",
        "script": "scripts/sod_gate_enforcer.py",
        "args": ["--check-artifacts"],
        "category": "e2e",
        "mode": STATUS_MODE_READ_ONLY,
        "read_only": True,
    },
    {
        "id": "e2e_pit_safety",
        "label": "PIT / Look-Ahead Safety",
        "description": "Point-in-time safety and no-look-ahead validation",
        "script": "scripts/sod_gate_enforcer.py",
        "args": ["--check-pit"],
        "category": "data",
        "mode": STATUS_MODE_READ_ONLY,
        "read_only": True,
    },
    {
        "id": "e2e_risk_failclosed",
        "label": "Risk Fail-Closed Check",
        "description": "Verify risk/execution components fail closed when unknown",
        "script": "scripts/sod_gate_enforcer.py",
        "args": ["--check-risk"],
        "category": "risk",
        "mode": STATUS_MODE_READ_ONLY,
        "read_only": True,
    },
    {
        "id": "e2e_test_trace",
        "label": "Test / Audit Trace",
        "description": "Show latest test results and audit traces",
        "script": "python -m pytest",
        "args": ["tests/", "-q", "--tb=short"],
        "category": "testing",
        "mode": STATUS_MODE_READ_ONLY,
        "read_only": True,
    },
    {
        "id": "e2e_gate_enforcer",
        "label": "SOD Gate Enforcer",
        "description": "Run SOD gate enforcer in informational mode",
        "script": "scripts/sod_gate_enforcer.py",
        "args": [],
        "category": "governance",
        "mode": STATUS_MODE_READ_ONLY,
        "read_only": True,
    },
]

# ── Safe Command Catalog (read-only / status-only) ──────────────────────
SAFE_COMMAND_CATALOG = [
    {
        "id": "connectivity_check",
        "label": "Phase 1→5 Connectivity",
        "description": "Full phase connectivity check",
        "script": "scripts/sod_gate_enforcer.py",
        "args": ["--informational"],
        "category": "audit",
        "read_only": True,
    },
    {
        "id": "backtest_status",
        "label": "Backtest Status",
        "description": "Show latest backtest results from pipeline state",
        "script": "scripts/run_phase35_backtest.py",
        "args": ["--status-only"],
        "category": "quant",
        "read_only": True,
    },
    {
        "id": "pit_validation",
        "label": "PIT / Data Validation",
        "description": "Point-in-time safety and data validation status",
        "script": "scripts/sod_gate_enforcer.py",
        "args": ["--check-pit"],
        "category": "data",
        "read_only": True,
    },
    {
        "id": "model_evolution",
        "label": "Model / Evolution",
        "description": "GP evolution and model workflow status",
        "script": "scripts/run_weekly_evolution.py",
        "args": ["--status-only"],
        "category": "quant",
        "read_only": True,
    },
    {
        "id": "execution_dryrun",
        "label": "Execution / OMS Dry-Run",
        "description": "Execution and OMS dry-run status",
        "script": "scripts/run_phase35_backtest.py",
        "args": ["--dry-run"],
        "category": "execution",
        "read_only": True,
    },
    {
        "id": "risk_killswitch",
        "label": "Risk / Kill-Switch",
        "description": "Risk metrics and kill-switch status",
        "script": "scripts/sod_gate_enforcer.py",
        "args": ["--check-risk"],
        "category": "risk",
        "read_only": True,
    },
    {
        "id": "sod_gate",
        "label": "SOD Gate Enforcer",
        "description": "Run SOD gate enforcer in informational mode",
        "script": "scripts/sod_gate_enforcer.py",
        "args": [],
        "category": "audit",
        "read_only": True,
    },
    {
        "id": "all_tests",
        "label": "All Tests",
        "description": "Run full pytest suite (status display only)",
        "script": "python -m pytest",
        "args": ["tests/", "-q", "--tb=short"],
        "category": "testing",
        "read_only": True,
    },
    {
        "id": "export_report",
        "label": "Export Audit Report",
        "description": "Export current audit/status report",
        "script": "scripts/sod_gate_enforcer.py",
        "args": ["--export"],
        "category": "audit",
        "read_only": True,
    },
]

# --- CLI Trace Panel Settings ---
CLI_TRACE_MAX_LINES = 100
CLI_TRACE_MAX_ENTRIES = 50

# --- Required Command Center Sections ---
COMMAND_CENTER_SECTIONS = [
    "executive_header",
    "e2e_topology_map",
    "phase_connectivity_map",
    "action_buttons",
    "cli_trace_panel",
    "detail_tabs",
]

# --- Detail Tab Names ---
COMMAND_CENTER_TABS = [
    "E2E Topology",
    "SOD / Gates",
    "Data Health",
    "PIT / Backtest",
    "Model / Evolution",
    "Portfolio / Risk",
    "Execution / OMS",
    "SRE / Observability",
    "Governance",
]

# --- Agent Roles (25 roles) ---
AGENT_ROLES = [
    {"ID": 1, "Name": "Project Manager", "Tier": "L1", "Platform": "Ly", "Resp": "Strategic orchestration"},
    {"ID": 2, "Name": "Product Owner", "Tier": "L1", "Platform": "Ly", "Resp": "Feature prioritization"},
    {"ID": 3, "Name": "Scrum Master", "Tier": "L1", "Platform": "Ly", "Resp": "Agile, blockers"},
    {"ID": 4, "Name": "Release Manager", "Tier": "L1", "Platform": "Ly", "Resp": "Release coordination"},
    {"ID": 5, "Name": "Delivery Manager", "Tier": "L1", "Platform": "Ly", "Resp": "Timeline, resources"},
    {"ID": 6, "Name": "System Architect", "Tier": "L2", "Platform": "OpenCode", "Resp": "System design"},
    {"ID": 7, "Name": "Tech Lead", "Tier": "L2", "Platform": "OpenCode", "Resp": "Code standards"},
    {"ID": 8, "Name": "Frontend Engineer", "Tier": "L2", "Platform": "OpenCode", "Resp": "UI/UX impl"},
    {"ID": 9, "Name": "Backend Engineer", "Tier": "L2", "Platform": "OpenCode", "Resp": "API, logic"},
    {"ID": 10, "Name": "Database Admin", "Tier": "L2", "Platform": "OpenCode", "Resp": "Schema, DB perf"},
    {"ID": 11, "Name": "DevOps Engineer", "Tier": "L2", "Platform": "OpenCode", "Resp": "CI/CD"},
    {"ID": 12, "Name": "Cloud Infra", "Tier": "L2", "Platform": "OpenCode", "Resp": "IaC"},
    {"ID": 13, "Name": "UI/UX Integrator", "Tier": "L2", "Platform": "OpenCode", "Resp": "UI integration"},
    {"ID": 14, "Name": "Data Scientist", "Tier": "L2", "Platform": "OpenCode", "Resp": "Model research"},
    {"ID": 15, "Name": "Data Engineer", "Tier": "L2", "Platform": "OpenCode", "Resp": "ETL, pipelines"},
    {"ID": 16, "Name": "ML Engineer", "Tier": "L2", "Platform": "OpenCode", "Resp": "Model training"},
    {"ID": 17, "Name": "QA Engineer", "Tier": "L3", "Platform": "Codex", "Resp": "Functional testing"},
    {"ID": 18, "Name": "SDET", "Tier": "L3", "Platform": "Codex", "Resp": "Test automation"},
    {"ID": 19, "Name": "Security Auditor", "Tier": "L3", "Platform": "Codex", "Resp": "Security scanning"},
    {"ID": 20, "Name": "Compliance Officer", "Tier": "L3", "Platform": "Codex", "Resp": "PIT safety"},
    {"ID": 21, "Name": "Code Reviewer", "Tier": "L3", "Platform": "Codex", "Resp": "Peer review"},
    {"ID": 22, "Name": "Pen Tester", "Tier": "L3", "Platform": "Codex", "Resp": "Security testing"},
    {"ID": 23, "Name": "Perf Tester", "Tier": "L3", "Platform": "Codex", "Resp": "Load/stress"},
    {"ID": 24, "Name": "UAT Validator", "Tier": "L3", "Platform": "Codex", "Resp": "User acceptance"},
    {"ID": 25, "Name": "IT Auditor", "Tier": "L3", "Platform": "Codex", "Resp": "System audit"},
]
