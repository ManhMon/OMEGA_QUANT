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

# --- CSS ---
CUSTOM_CSS = """
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
    .status-ok { color: #4CAF50; font-weight: bold; }
    .status-warn { color: #FF9800; font-weight: bold; }
    .status-error { color: #F44336; font-weight: bold; }
</style>
"""

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
