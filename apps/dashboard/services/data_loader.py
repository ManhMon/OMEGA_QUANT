"""
Data Loader Service
Wraps existing data loading logic from src.omega.data and monitoring_dashboard.py
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

import pandas as pd
import streamlit as st

from config.dashboard_config import (
    SESSION_DIR,
    PIPELINE_DIRS,
    DATA_DIR,
    MARKET_DATA_FILE,
    FEATURES_DATA_FILE,
    SECTOR_MAPPING_FILE,
    RISK_STATUS_FILE,
    PHASE_GATES_FILE,
    AUDIT_LOG_FILE,
    EVOLVED_ALPHAS_FILE,
    GOAL_STATE_FILE,
    CACHE_TTL_FAST,
    CACHE_TTL_MEDIUM,
    CACHE_TTL_SLOW,
    MAX_AUDIT_LOG_LINES,
    MAX_BACKTEST_RESULTS,
)


class DataLoaderService:
    """Service for loading and caching dashboard data"""

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_FAST)
    def load_risk_status() -> Optional[Dict]:
        """Load risk status from risk_status.json"""
        if not RISK_STATUS_FILE.exists():
            return None
        try:
            with open(RISK_STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"Failed to load risk status: {e}")
            return None

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_MEDIUM)
    def load_phase_gates() -> Dict[str, Dict]:
        """Load phase gates from phase_gates.json"""
        if not PHASE_GATES_FILE.exists():
            return {}
        try:
            with open(PHASE_GATES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            st.warning(f"Failed to load phase gates: {e}")
            return {}

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_FAST)
    def load_audit_log(max_lines: int = MAX_AUDIT_LOG_LINES) -> List[Dict]:
        """Load audit log from audit_log.jsonl"""
        if not AUDIT_LOG_FILE.exists():
            return []
        try:
            lines = []
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            lines.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            return lines[-max_lines:]
        except Exception as e:
            st.warning(f"Failed to load audit log: {e}")
            return []

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_MEDIUM)
    def load_evolved_alphas() -> Dict:
        """Load evolved alphas from all_regimes_evolved_alphas.json"""
        if not EVOLVED_ALPHAS_FILE.exists():
            return {}
        try:
            with open(EVOLVED_ALPHAS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"Failed to load evolved alphas: {e}")
            return {}

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_MEDIUM)
    def load_goal_state() -> Optional[Dict]:
        """Load goal runner state"""
        if not GOAL_STATE_FILE.exists():
            return None
        try:
            with open(GOAL_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"Failed to load goal state: {e}")
            return None

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_MEDIUM)
    def load_backtest_results() -> List[Dict]:
        """Load backtest results from pipeline directories"""
        results = []
        for pdir in PIPELINE_DIRS:
            if not pdir.exists():
                continue
            for f in sorted(pdir.glob("*.json")):
                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    if isinstance(data, dict):
                        results.append(data)
                except Exception:
                    continue
                if len(results) >= MAX_BACKTEST_RESULTS:
                    break
            if len(results) >= MAX_BACKTEST_RESULTS:
                break
        return results

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_SLOW)
    def load_market_data() -> Optional[pd.DataFrame]:
        """Load market data from parquet file"""
        if not MARKET_DATA_FILE.exists():
            return None
        try:
            df = pd.read_parquet(MARKET_DATA_FILE)
            return df
        except Exception as e:
            st.warning(f"Failed to load market data: {e}")
            return None

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_SLOW)
    def load_features_data() -> Optional[pd.DataFrame]:
        """Load features data from parquet file"""
        if not FEATURES_DATA_FILE.exists():
            return None
        try:
            df = pd.read_parquet(FEATURES_DATA_FILE)
            return df
        except Exception as e:
            st.warning(f"Failed to load features data: {e}")
            return None

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_SLOW)
    def load_sector_mapping() -> Optional[pd.DataFrame]:
        """Load sector mapping from CSV"""
        if not SECTOR_MAPPING_FILE.exists():
            return None
        try:
            df = pd.read_csv(SECTOR_MAPPING_FILE)
            return df
        except Exception as e:
            st.warning(f"Failed to load sector mapping: {e}")
            return None

    @staticmethod
    def get_data_files_info() -> List[Dict[str, Any]]:
        """Get information about all data files"""
        files_info = []
        
        # Market data
        if MARKET_DATA_FILE.exists():
            stat = MARKET_DATA_FILE.stat()
            files_info.append({
                "File": "Market Data",
                "Path": str(MARKET_DATA_FILE.relative_to(DATA_DIR)),
                "Size (MB)": round(stat.st_size / 1024 / 1024, 2),
                "Last Modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "Status": "✅ OK",
            })
        else:
            files_info.append({
                "File": "Market Data",
                "Path": str(MARKET_DATA_FILE.relative_to(DATA_DIR)),
                "Size (MB)": 0,
                "Last Modified": "N/A",
                "Status": "❌ Missing",
            })

        # Features data
        if FEATURES_DATA_FILE.exists():
            stat = FEATURES_DATA_FILE.stat()
            files_info.append({
                "File": "Features Data",
                "Path": str(FEATURES_DATA_FILE.relative_to(DATA_DIR)),
                "Size (MB)": round(stat.st_size / 1024 / 1024, 2),
                "Last Modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "Status": "✅ OK",
            })
        else:
            files_info.append({
                "File": "Features Data",
                "Path": str(FEATURES_DATA_FILE.relative_to(DATA_DIR)),
                "Size (MB)": 0,
                "Last Modified": "N/A",
                "Status": "❌ Missing",
            })

        # Sector mapping
        if SECTOR_MAPPING_FILE.exists():
            stat = SECTOR_MAPPING_FILE.stat()
            files_info.append({
                "File": "Sector Mapping",
                "Path": str(SECTOR_MAPPING_FILE.relative_to(DATA_DIR)),
                "Size (MB)": round(stat.st_size / 1024 / 1024, 2),
                "Last Modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "Status": "✅ OK",
            })
        else:
            files_info.append({
                "File": "Sector Mapping",
                "Path": str(SECTOR_MAPPING_FILE.relative_to(DATA_DIR)),
                "Size (MB)": 0,
                "Last Modified": "N/A",
                "Status": "⚠️ Optional",
            })

        return files_info

    @staticmethod
    def get_data_quality_summary(df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """Get data quality summary for a DataFrame"""
        if df is None or df.empty:
            return {
                "Rows": 0,
                "Columns": 0,
                "Missing Values": 0,
                "Missing %": 0,
                "Duplicates": 0,
            }

        total_cells = df.size
        missing_cells = df.isna().sum().sum()
        missing_pct = (missing_cells / total_cells * 100) if total_cells > 0 else 0
        duplicates = df.duplicated().sum()

        return {
            "Rows": len(df),
            "Columns": len(df.columns),
            "Missing Values": int(missing_cells),
            "Missing %": round(missing_pct, 2),
            "Duplicates": int(duplicates),
        }
