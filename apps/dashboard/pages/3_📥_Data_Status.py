"""
Data Status Page - Data quality and freshness monitoring
Phase 1 Priority: This is a key new feature
"""
import streamlit as st
import sys
from pathlib import Path
from datetime import datetime

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASHBOARD_ROOT))

from config.dashboard_config import PAGE_TITLE, CUSTOM_CSS, DATA_DIR
from services.data_loader import DataLoaderService
import pandas as pd

st.set_page_config(page_title=f"{PAGE_TITLE} - Data Status", page_icon="📥", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown("## 📥 Data Status & Quality")

# Get data files info
st.markdown("### 📁 Data Files")
files_info = DataLoaderService.get_data_files_info()

if files_info:
    df_files = pd.DataFrame(files_info)
    st.dataframe(df_files, width="stretch", hide_index=True)
else:
    st.warning("No data files found.")

st.markdown("---")

# Data Quality Summary
st.markdown("### 🔍 Data Quality Summary")

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### Market Data")
    market_data = DataLoaderService.load_market_data()
    if market_data is not None:
        quality = DataLoaderService.get_data_quality_summary(market_data)
        
        col1a, col1b, col1c = st.columns(3)
        with col1a:
            st.metric("Rows", f"{quality['Rows']:,}")
        with col1b:
            st.metric("Columns", quality['Columns'])
        with col1c:
            st.metric("Missing %", f"{quality['Missing %']:.2f}%")
        
        # Show first few rows
        with st.expander("Preview Market Data"):
            st.dataframe(market_data.head(10), width="stretch")
        
        # Show columns
        with st.expander("Column Info"):
            st.write(f"**Columns:** {', '.join(market_data.columns)}")
            st.write(f"**Data types:**")
            st.write(market_data.dtypes)
    else:
        st.info("Market data not available.")

with col2:
    st.markdown("#### Features Data")
    features_data = DataLoaderService.load_features_data()
    if features_data is not None:
        quality = DataLoaderService.get_data_quality_summary(features_data)
        
        col2a, col2b, col2c = st.columns(3)
        with col2a:
            st.metric("Rows", f"{quality['Rows']:,}")
        with col2b:
            st.metric("Columns", quality['Columns'])
        with col2c:
            st.metric("Missing %", f"{quality['Missing %']:.2f}%")
        
        # Show first few rows
        with st.expander("Preview Features Data"):
            st.dataframe(features_data.head(10), width="stretch")
        
        # Show columns count
        with st.expander("Column Info"):
            st.write(f"**Total Columns:** {len(features_data.columns)}")
            st.write(f"**First 20 columns:** {', '.join(features_data.columns[:20])}")
    else:
        st.info("Features data not available.")

st.markdown("---")

# Sector Mapping
st.markdown("### 🏢 Sector Mapping")
sector_mapping = DataLoaderService.load_sector_mapping()
if sector_mapping is not None:
    st.success(f"✅ Sector mapping loaded: {len(sector_mapping)} entries")
    
    with st.expander("Preview Sector Mapping"):
        st.dataframe(sector_mapping.head(20), width="stretch")
else:
    st.warning("⚠️ Sector mapping file not found (optional)")

st.markdown("---")

# Data Freshness
st.markdown("### 🕐 Data Freshness")

col1, col2, col3 = st.columns(3)

with col1:
    # Check market data freshness
    from config.dashboard_config import MARKET_DATA_FILE
    if MARKET_DATA_FILE.exists():
        mtime = MARKET_DATA_FILE.stat().st_mtime
        mtime_dt = datetime.fromtimestamp(mtime)
        age_days = (datetime.now() - mtime_dt).days
        
        if age_days < 7:
            st.success(f"✅ Market data is fresh ({age_days} days old)")
        else:
            st.warning(f"⚠️ Market data is {age_days} days old")
    else:
        st.error("❌ Market data not found")

with col2:
    # Check features data freshness
    from config.dashboard_config import FEATURES_DATA_FILE
    if FEATURES_DATA_FILE.exists():
        mtime = FEATURES_DATA_FILE.stat().st_mtime
        mtime_dt = datetime.fromtimestamp(mtime)
        age_days = (datetime.now() - mtime_dt).days
        
        if age_days < 7:
            st.success(f"✅ Features data is fresh ({age_days} days old)")
        else:
            st.warning(f"⚠️ Features data is {age_days} days old")
    else:
        st.error("❌ Features data not found")

with col3:
    # Check risk status freshness
    from config.dashboard_config import RISK_STATUS_FILE
    if RISK_STATUS_FILE.exists():
        mtime = RISK_STATUS_FILE.stat().st_mtime
        mtime_dt = datetime.fromtimestamp(mtime)
        age_hours = (datetime.now() - mtime_dt).total_seconds() / 3600
        
        if age_hours < 24:
            st.success(f"✅ Risk status is fresh ({age_hours:.1f} hours old)")
        else:
            st.warning(f"⚠️ Risk status is {age_hours:.1f} hours old")
    else:
        st.error("❌ Risk status not found")

st.markdown("---")

# Data Download Section
st.markdown("### 💾 Download Data")

st.info("""
**Note:** Data download functionality will be implemented in Phase 2.

Planned features:
- Export market data to CSV/Parquet
- Export features data
- Export backtest results
- Download complete data packages
""")

st.markdown("---")

# Data Directory Info
st.markdown("### 📂 Data Directory")
st.write(f"**Data Directory:** `{DATA_DIR}`")

if DATA_DIR.exists():
    total_size = sum(f.stat().st_size for f in DATA_DIR.rglob('*') if f.is_file())
    total_size_mb = total_size / (1024 * 1024)
    st.write(f"**Total Size:** {total_size_mb:.2f} MB")
    
    file_count = sum(1 for f in DATA_DIR.rglob('*') if f.is_file())
    st.write(f"**Total Files:** {file_count}")
else:
    st.error("Data directory not found!")
