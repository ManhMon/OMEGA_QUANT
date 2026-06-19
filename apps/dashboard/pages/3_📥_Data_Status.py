"""
Data Status Page - Bloomberg command-center data ops interface
Gate: DASHBOARD_UI_POLISH_20260613
Preserves all DataLoaderService calls and safety lock/update behavior.
"""
import streamlit as st
import sys
from pathlib import Path
from datetime import datetime

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASHBOARD_ROOT))

from config.dashboard_config import (
    PAGE_TITLE,
    CUSTOM_CSS,
    DATA_DIR,
    MARKET_DATA_FILE,
    FEATURES_DATA_FILE,
    RISK_STATUS_FILE,
)
from services.data_loader import DataLoaderService
import pandas as pd

st.set_page_config(
    page_title=f"{PAGE_TITLE} - Data Status",
    page_icon="📥",
    layout="wide",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ── Helper: freshness pill ───────────────────────────────────────────────────

def _freshness_pill(label: str, fpath: Path, unit: str, threshold: float) -> str:
    """Return HTML pill for data freshness status."""
    if not fpath.exists():
        return f'<span class="pill pill-error">{label}: MISSING</span>'
    mtime = fpath.stat().st_mtime
    age = (datetime.now() - datetime.fromtimestamp(mtime)).total_seconds()
    if unit == "days":
        age_val = age / 86400
        display = f"{age_val:.1f}d"
    else:
        age_val = age / 3600
        display = f"{age_val:.1f}h"
    if age_val < threshold:
        return f'<span class="pill pill-ok">{label}: FRESH {display}</span>'
    return f'<span class="pill pill-warn">{label}: STALE {display}</span>'


def _validation_pill(vs: str) -> str:
    """Return HTML pill for validation status."""
    if vs == "PASS":
        return '<span class="pill pill-ok">VALIDATION: PASS</span>'
    if vs == "WARN":
        return '<span class="pill pill-warn">VALIDATION: WARN</span>'
    if vs == "MISSING":
        return '<span class="pill pill-error">VALIDATION: MISSING</span>'
    return f'<span class="pill pill-error">VALIDATION: {vs}</span>'


# ══════════════════════════════════════════════════════════════════════════════
# LOAD ALL DATA UPFRONT (preserve existing service calls)
# ══════════════════════════════════════════════════════════════════════════════
canon = DataLoaderService.load_canonical_market_summary()
universe = DataLoaderService.load_vci_universe_summary()
files_info = DataLoaderService.get_data_files_info()
market_data = DataLoaderService.load_market_data()
features_data = DataLoaderService.load_features_data()
sector_mapping = DataLoaderService.load_sector_mapping()
legacy = DataLoaderService.load_legacy_loader_inventory()
last_result = DataLoaderService.load_update_market_data_result()

# ══════════════════════════════════════════════════════════════════════════════
# 1. COMMAND HEADER
# ══════════════════════════════════════════════════════════════════════════════
_canon_exists = canon.get("exists", False)
_vs = canon.get("validation_status", "MISSING")
_date_max = canon.get("date_max", "N/A")
_sha_short = (canon.get("sha256", "N/A") or "N/A")[:16]

_freshness_pills = " ".join([
    _freshness_pill("MARKET", MARKET_DATA_FILE, "days", 7),
    _freshness_pill("FEATURES", FEATURES_DATA_FILE, "days", 7),
    _freshness_pill("RISK", RISK_STATUS_FILE, "hours", 24),
])

st.markdown(
    f"""<div class="cmd-header">
    <h1>📥 DATA STATUS // COMMAND CENTER</h1>
    <div class="cmd-sub">
        GATE: DASHBOARD_UI_POLISH_20260613 &nbsp;|&nbsp;
        CANONICAL: {'ONLINE' if _canon_exists else 'OFFLINE'} &nbsp;|&nbsp;
        MAX DATE: {_date_max} &nbsp;|&nbsp;
        SHA: {_sha_short}... &nbsp;|&nbsp;
        {_validation_pill(_vs)}
    </div>
    <div style="margin-top:8px;">{_freshness_pills}</div>
    </div>""",
    unsafe_allow_html=True,
)

# ══════════════════════════════════════════════════════════════════════════════
# 2. KPI STRIP
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-hdr"><h3>KPI Strip</h3></div>', unsafe_allow_html=True)

if _canon_exists:
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1:
        st.markdown(
            f"""<div class="metric-tile">
            <div class="tile-label">ROWS</div>
            <div class="tile-value">{canon.get('rows', 0):,}</div>
            </div>""", unsafe_allow_html=True)
    with k2:
        st.markdown(
            f"""<div class="metric-tile">
            <div class="tile-label">TICKERS</div>
            <div class="tile-value">{canon.get('ticker_count', 'N/A')}</div>
            </div>""", unsafe_allow_html=True)
    with k3:
        st.markdown(
            f"""<div class="metric-tile">
            <div class="tile-label">DATE MIN</div>
            <div class="tile-value" style="font-size:1.1rem;">{canon.get('date_min', 'N/A')}</div>
            </div>""", unsafe_allow_html=True)
    with k4:
        st.markdown(
            f"""<div class="metric-tile">
            <div class="tile-label">DATE MAX</div>
            <div class="tile-value amber" style="font-size:1.1rem;">{canon.get('date_max', 'N/A')}</div>
            </div>""", unsafe_allow_html=True)
    with k5:
        exch = canon.get("exchange_split", {})
        exch_str = " / ".join(f"{k}:{v}" for k, v in exch.items()) if exch else "N/A"
        st.markdown(
            f"""<div class="metric-tile">
            <div class="tile-label">EXCHANGES</div>
            <div class="tile-value" style="font-size:0.85rem;">{exch_str}</div>
            </div>""", unsafe_allow_html=True)
    with k6:
        st.markdown(
            f"""<div class="metric-tile">
            <div class="tile-label">SHA-256</div>
            <div class="tile-delta" style="font-size:0.7rem;margin-top:10px;">{(canon.get('sha256', 'N/A') or 'N/A')[:24]}...</div>
            </div>""", unsafe_allow_html=True)
else:
    st.markdown(
        '<div class="op-panel-danger">Canonical market parquet not found. Run an update below.</div>',
        unsafe_allow_html=True,
    )

# VCI Universe sub-strip
if universe.get("exists"):
    st.markdown(
        f"""<div style="margin-top:6px;">
        <span class="pill pill-info">VCI UNIVERSE: HSX {universe.get('hsx_count', 0)} / HNX {universe.get('hnx_count', 0)} / TOTAL {universe.get('total', 0)}</span>
        </div>""",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div style="margin-top:6px;"><span class="pill pill-warn">VCI UNIVERSE: FALLBACK (file not found)</span></div>',
        unsafe_allow_html=True,
    )

# ══════════════════════════════════════════════════════════════════════════════
# 3. DATA HEALTH MATRIX
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-hdr"><h3>Data Health Matrix</h3></div>', unsafe_allow_html=True)
st.markdown('<div class="op-panel">', unsafe_allow_html=True)

if _canon_exists:
    dup = canon.get("duplicate_ticker_date", -1)
    ohlcv_nulls = canon.get("ohlcv_nulls", {})
    total_nulls = sum(ohlcv_nulls.values()) if ohlcv_nulls else 0
    size_mb = canon.get("size_mb", "N/A")
    modified = canon.get("modified", "N/A")
    columns = canon.get("columns", "N/A")

    dup_cls = "ok" if dup == 0 else ("warn" if dup > 0 else "warn")
    null_cls = "ok" if total_nulls == 0 else "warn"

    health_html = f"""<div class="health-grid">
    <div class="health-cell"><div class="hc-label">DUP (TICKER,DATE)</div><div class="hc-val {dup_cls}">{dup if dup >= 0 else 'N/A'}</div></div>
    <div class="health-cell"><div class="hc-label">OHLCV NULLS</div><div class="hc-val {null_cls}">{total_nulls}</div></div>
    <div class="health-cell"><div class="hc-label">COLUMNS</div><div class="hc-val">{columns}</div></div>
    <div class="health-cell"><div class="hc-label">SIZE (MB)</div><div class="hc-val">{size_mb}</div></div>
    <div class="health-cell"><div class="hc-label">MODIFIED</div><div class="hc-val" style="font-size:0.8rem;">{modified}</div></div>
    <div class="health-cell"><div class="hc-label">SCHEMA</div><div class="hc-val ok">CANONICAL</div></div>
    </div>"""
    st.markdown(health_html, unsafe_allow_html=True)

    if ohlcv_nulls and total_nulls > 0:
        null_detail = " | ".join(f"{k}:{v}" for k, v in ohlcv_nulls.items())
        st.markdown(f'<p class="mono-micro">NULL BREAKDOWN: {null_detail}</p>', unsafe_allow_html=True)
else:
    st.markdown('<p class="mono-micro">No canonical data available for health check.</p>', unsafe_allow_html=True)

# Data quality from loaded DataFrames
st.markdown('<hr class="cmd-divider">', unsafe_allow_html=True)
dq1, dq2 = st.columns(2)
with dq1:
    st.markdown("**Market Data Quality**")
    if market_data is not None:
        quality = DataLoaderService.get_data_quality_summary(market_data)
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Rows", f"{quality['Rows']:,}")
        with m2:
            st.metric("Columns", quality["Columns"])
        with m3:
            st.metric("Missing %", f"{quality['Missing %']:.2f}%")
        with st.expander("Preview Market Data"):
            st.dataframe(market_data.head(10), width="stretch")
    else:
        st.info("Market data not loaded.")

with dq2:
    st.markdown("**Features Data Quality**")
    if features_data is not None:
        quality = DataLoaderService.get_data_quality_summary(features_data)
        f1, f2, f3 = st.columns(3)
        with f1:
            st.metric("Rows", f"{quality['Rows']:,}")
        with f2:
            st.metric("Columns", quality["Columns"])
        with f3:
            st.metric("Missing %", f"{quality['Missing %']:.2f}%")
    else:
        st.info("Features data not loaded.")

# Sector mapping
if sector_mapping is not None:
    st.markdown(f'<div style="margin-top:8px;"><span class="pill pill-ok">SECTOR MAP: {len(sector_mapping)} entries</span></div>', unsafe_allow_html=True)
else:
    st.markdown('<div style="margin-top:8px;"><span class="pill pill-warn">SECTOR MAP: NOT FOUND (optional)</span></div>', unsafe_allow_html=True)

# Data files table
if files_info:
    with st.expander("Data Files Inventory"):
        st.dataframe(pd.DataFrame(files_info), width="stretch", hide_index=True)

st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 4. OPERATOR PANEL - UPDATE CONTROLS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-hdr"><h3>Operator Panel // Update Controls</h3></div>', unsafe_allow_html=True)
st.markdown('<div class="op-panel">', unsafe_allow_html=True)

st.markdown(
    '<div class="op-panel-warn">These controls invoke <code>scripts/update_market_data.py</code>. '
    'Dry-run is safe (no writes). Real update writes to canonical parquet with atomic backup.</div>',
    unsafe_allow_html=True,
)

# Input fields
ic1, ic2, ic3 = st.columns(3)
with ic1:
    symbols_input = st.text_input(
        "Symbols (space-separated, optional)",
        value="",
        help="Leave blank for full universe. Example: VCB HPG FPT",
    )
with ic2:
    start_input = st.text_input(
        "Start date (YYYY-MM-DD, optional)",
        value="",
        help="Override start date. Default: canonical max date + 1 day",
    )
with ic3:
    end_input = st.text_input(
        "End date (YYYY-MM-DD, optional)",
        value="",
        help="Override end date. Default: today",
    )

symbols_list = [s.strip().upper() for s in symbols_input.split() if s.strip()] or None
start_str = start_input.strip() or None
end_str = end_input.strip() or None

# Dry-run button
if st.button("Dry-Run Update", type="secondary"):
    with st.spinner("Running dry-run..."):
        before_hash = canon.get("sha256", "")
        result = DataLoaderService.run_market_data_update(
            dry_run=True,
            symbols=symbols_list,
            start=start_str,
            end=end_str,
        )

    st.markdown("#### Dry-Run Result")
    rc1, rc2 = st.columns([1, 3])
    with rc1:
        status = result.get("status", "UNKNOWN")
        if status == "OK":
            st.success(f"Status: {status}")
        else:
            st.error(f"Status: {status}")
    with rc2:
        st.write(f"Return code: {result.get('returncode', 'N/A')}")

    if result.get("stdout"):
        with st.expander("stdout"):
            st.code(result["stdout"], language="text")
    if result.get("stderr"):
        with st.expander("stderr"):
            st.code(result["stderr"], language="text")

    # Verify canonical unchanged
    after_summary = DataLoaderService.load_canonical_market_summary()
    after_hash = after_summary.get("sha256", "")
    if before_hash and after_hash:
        if before_hash == after_hash:
            st.markdown('<div class="pill pill-ok">CANONICAL HASH UNCHANGED (safe)</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="pill pill-error">WARNING: CANONICAL HASH CHANGED AFTER DRY-RUN</div>', unsafe_allow_html=True)

# Real update section
st.markdown('<hr class="cmd-divider">', unsafe_allow_html=True)
st.markdown("#### Real Update (writes canonical)")
st.markdown(
    '<div class="op-panel-danger"><b>WARNING:</b> This will invoke the canonical VCI updater '
    'which writes to <code>data/market_2015_now.parquet</code>. '
    'An atomic backup is created automatically. Confirm below to enable.</div>',
    unsafe_allow_html=True,
)

confirm_real = st.checkbox(
    "I confirm I want to run a REAL update (writes canonical parquet)",
    value=False,
)

real_btn = st.button(
    "Run Real Update",
    type="primary",
    disabled=not confirm_real,
)

if real_btn and confirm_real:
    before_summary = DataLoaderService.load_canonical_market_summary()
    before_hash = before_summary.get("sha256", "")
    before_rows = before_summary.get("rows", 0)

    st.markdown("**Before update:**")
    st.write(f"  Rows: {before_rows:,} | Hash: `{before_hash[:16]}...`")

    with st.spinner("Running real update..."):
        result = DataLoaderService.run_market_data_update(
            dry_run=False,
            symbols=symbols_list,
            start=start_str,
            end=end_str,
        )

    st.markdown("**After update:**")
    after_summary = DataLoaderService.load_canonical_market_summary()
    after_hash = after_summary.get("sha256", "")
    after_rows = after_summary.get("rows", 0)
    st.write(f"  Rows: {after_rows:,} | Hash: `{after_hash[:16]}...`")

    rc1, rc2 = st.columns([1, 3])
    with rc1:
        status = result.get("status", "UNKNOWN")
        if status == "OK":
            st.success(f"Status: {status}")
        else:
            st.error(f"Status: {status}")
    with rc2:
        st.write(f"Return code: {result.get('returncode', 'N/A')}")

    if result.get("stdout"):
        with st.expander("stdout"):
            st.code(result["stdout"], language="text")
    if result.get("stderr"):
        with st.expander("stderr"):
            st.code(result["stderr"], language="text")

    if before_hash and after_hash:
        if before_hash != after_hash:
            row_delta = after_rows - before_rows
            st.info(
                f"Canonical CHANGED. Row delta: {row_delta:+,}. "
                f"New hash: `{after_hash[:32]}...`"
            )
        else:
            st.success("Canonical hash unchanged (no new data written).")

st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 5. LEGACY LOADER PANEL
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-hdr"><h3>Legacy Loader Inventory</h3></div>', unsafe_allow_html=True)
st.markdown('<div class="op-panel">', unsafe_allow_html=True)

if legacy.get("json_exists") and legacy.get("json_data"):
    inv_data = legacy["json_data"]
    inventory_list = inv_data.get("inventory", [])
    if inventory_list:
        inv_rows = []
        for item in inventory_list:
            inv_rows.append({
                "File": item.get("file", ""),
                "Status": item.get("status", ""),
                "Replacement": item.get("replacement", ""),
                "Gate": item.get("superseded_by_gate", ""),
            })
        st.dataframe(pd.DataFrame(inv_rows), width="stretch", hide_index=True)
    st.markdown(
        f'<p class="mono-micro">GATE: {inv_data.get("gate", "N/A")} | DATE: {inv_data.get("date", "N/A")}</p>',
        unsafe_allow_html=True,
    )
else:
    st.markdown('<p class="mono-micro">Legacy inventory JSON not found.</p>', unsafe_allow_html=True)

if legacy.get("md_exists") and legacy.get("md_text"):
    with st.expander("Legacy Inventory Markdown (full)"):
        st.markdown(legacy["md_text"])

st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 6. UPDATE RESULT / LOG PANEL
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-hdr"><h3>Update Result // Log Panel</h3></div>', unsafe_allow_html=True)
st.markdown('<div class="op-panel">', unsafe_allow_html=True)

if last_result.get("exists") and last_result.get("data"):
    rd = last_result["data"]
    r_status = rd.get("status", "unknown")
    status_cls = "pill-ok" if r_status == "OK" else "pill-error"

    st.markdown(f'<span class="pill {status_cls}">LAST STATUS: {r_status}</span>', unsafe_allow_html=True)

    if "fetch_stats" in rd:
        fs = rd["fetch_stats"]
        st.markdown(
            f'<div class="log-panel">'
            f'<span class="log-ts">FETCH STATS</span><br>'
            f'Fetched: <span class="log-ok">{fs.get("fetched", 0)}</span> | '
            f'Empty: <span class="log-warn">{fs.get("empty", 0)}</span> | '
            f'Errors: <span class="log-err">{fs.get("errors", 0)}</span> | '
            f'Rows: <span class="log-ok">{fs.get("rows", 0)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if fs.get("empty_tickers"):
            st.markdown(
                f'<p class="mono-micro">EMPTY TICKERS: {", ".join(fs["empty_tickers"])}</p>',
                unsafe_allow_html=True,
            )

    st.markdown(
        f'<p class="mono-micro">RESULT FILE MODIFIED: {last_result.get("modified", "N/A")}</p>',
        unsafe_allow_html=True,
    )

    with st.expander("Raw result JSON"):
        st.json(rd)
else:
    st.markdown(
        '<div class="log-panel"><span class="log-ts">NO PREVIOUS UPDATE RESULT FOUND</span></div>',
        unsafe_allow_html=True,
    )

st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 7. DATA DIRECTORY FOOTER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-hdr"><h3>Data Directory</h3></div>', unsafe_allow_html=True)
st.markdown(f'<p class="mono-micro">PATH: {DATA_DIR}</p>', unsafe_allow_html=True)
if DATA_DIR.exists():
    total_size = sum(f.stat().st_size for f in DATA_DIR.rglob("*") if f.is_file())
    total_size_mb = total_size / (1024 * 1024)
    file_count = sum(1 for f in DATA_DIR.rglob("*") if f.is_file())
    st.markdown(
        f'<p class="mono-micro">SIZE: {total_size_mb:.2f} MB | FILES: {file_count}</p>',
        unsafe_allow_html=True,
    )
else:
    st.markdown('<div class="pill pill-error">DATA DIRECTORY NOT FOUND</div>', unsafe_allow_html=True)
