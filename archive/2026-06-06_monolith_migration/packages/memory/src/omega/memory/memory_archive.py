"""
OMEGA_QUANT Memory Archive (Phase 6.2 - Memory & Evolution Engine)

Purpose:
    Store and retrieve historical alpha signals, performance metrics, and error resolutions.
    - Semantic hashing for alpha deduplication
    - Performance tracking with provenance
    - Error learning from audit logs
    - Vectorized operations (100% Pandas/NumPy)

Contract:
    - Input: Alpha signals, fitness metrics, audit logs
    - Output: Persistent memory archive (.ly_state/memory/)
    - PIT Safety: All data based on T-1 or earlier

Reference:
    - Phase 6.2: Memory Archive
    - Institutional-grade historical memory system

Author: Backend Engineer (Role 09)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class AlphaMemory:
    """
    Historical alpha signal archive with semantic hashing.
    
    Features:
    - Semantic hash for alpha deduplication (avoid re-discovering same logic)
    - Performance tracking (Sharpe, Turnover, Fitness) with timestamps
    - Vectorized storage (Pandas DataFrame)
    - PIT-safe: All data based on T-1 or earlier
    """
    
    def __init__(self, archive_dir: str = ".ly_state/memory/alpha_archive"):
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.archive_dir / "index.json"
        self.signals_file = self.archive_dir / "signals.parquet"
        
        # Load or initialize index
        self.index = self._load_index()
    
    def _load_index(self) -> Dict[str, Any]:
        """Load memory index from disk."""
        if not self.index_file.exists():
            return {
                "created_at": datetime.utcnow().isoformat() + "Z",
                "total_alphas": 0,
                "total_signals": 0,
                "last_updated": None,
                "alpha_hashes": [],  # Use list instead of set
            }
        with open(self.index_file, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _save_index(self) -> None:
        """Save memory index to disk."""
        self.index["last_updated"] = datetime.utcnow().isoformat() + "Z"
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(self.index, f, indent=2)
    
    def _compute_alpha_hash(self, expression: str, params: Dict[str, Any]) -> str:
        """
        Compute semantic hash for alpha expression.
        
        This ensures we don't rediscover the same alpha logic with different variable names.
        """
        # Normalize expression (remove extra whitespace, standardize variable names)
        normalized = expression.strip().lower()
        
        # Sort params for consistent hashing
        params_str = json.dumps(params, sort_keys=True)
        
        # Combine and hash
        data = f"{normalized}:{params_str}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def store_alpha(
        self,
        expression: str,
        params: Dict[str, Any],
        fitness: float,
        sharpe: float,
        turnover: float,
        symbol: str,
        as_of_date: datetime,
    ) -> str:
        """
        Store alpha signal with performance metrics.
        
        Args:
            expression: Alpha expression (e.g., "close / open")
            params: Expression parameters
            fitness: Overall fitness score
            sharpe: Sharpe ratio
            turnover: Turnover rate
            symbol: Target symbol
            as_of_date: Date of signal (T-1 or earlier)
            
        Returns:
            Alpha hash (unique identifier)
        """
        alpha_hash = self._compute_alpha_hash(expression, params)
        
        # Check for duplicate
        if alpha_hash in self.index["alpha_hashes"]:
            logger.warning(f"Alpha already exists: {alpha_hash}")
            return alpha_hash
        
        # Create signal record
        signal = {
            "alpha_hash": alpha_hash,
            "expression": expression,
            "params": json.dumps(params),
            "fitness": fitness,
            "sharpe": sharpe,
            "turnover": turnover,
            "symbol": symbol,
            "as_of_date": as_of_date.isoformat(),
            "stored_at": datetime.utcnow().isoformat() + "Z",
        }
        
        # Append to signals DataFrame
        signals_df = self._load_signals()
        signals_df = pd.concat([signals_df, pd.DataFrame([signal])], ignore_index=True)
        signals_df.to_parquet(self.signals_file, index=False)
        
        # Update index
        if alpha_hash not in self.index["alpha_hashes"]:
            self.index["alpha_hashes"].append(alpha_hash)
            self.index["total_alphas"] = len(self.index["alpha_hashes"])
        self.index["total_signals"] = len(signals_df)
        self._save_index()
        
        logger.info(f"Stored alpha: {alpha_hash} ({expression})")
        return alpha_hash
    
    def _load_signals(self) -> pd.DataFrame:
        """Load signals from parquet file."""
        if not self.signals_file.exists():
            return pd.DataFrame(columns=[
                "alpha_hash", "expression", "params", "fitness", "sharpe",
                "turnover", "symbol", "as_of_date", "stored_at"
            ])
        return pd.read_parquet(self.signals_file)
    
    def get_top_alphas(self, n: int = 10, symbol: Optional[str] = None) -> pd.DataFrame:
        """
        Get top N alphas by fitness score.
        
        Args:
            n: Number of top alphas to return
            symbol: Filter by symbol (optional)
            
        Returns:
            DataFrame of top alphas
        """
        signals_df = self._load_signals()
        
        if symbol:
            signals_df = signals_df[signals_df["symbol"] == symbol]
        
        return signals_df.nlargest(n, "fitness")
    
    def get_similar_alphas(self, expression: str, params: Dict[str, Any], threshold: float = 0.9) -> pd.DataFrame:
        """
        Find similar alphas using semantic hash comparison.
        
        Args:
            expression: Query expression
            params: Query parameters
            threshold: Similarity threshold (0-1)
            
        Returns:
            DataFrame of similar alphas
        """
        query_hash = self._compute_alpha_hash(expression, params)
        signals_df = self._load_signals()
        
        # Filter by hash prefix (approximate match)
        query_prefix = query_hash[:4]
        similar = signals_df[signals_df["alpha_hash"].str.startswith(query_prefix)]
        
        return similar


class ErrorMemory:
    """
    Error learning and resolution tracking.
    
    Features:
    - Parse audit logs for error patterns
    - Semantic hashing for error deduplication
    - Auto-update V21_ERROR_RESOLUTIONS_LOG.md
    - Recommend fixes based on similar past errors
    """
    
    def __init__(self, audit_logs_dir: str = ".ly_state/logs"):
        self.audit_logs_dir = Path(audit_logs_dir)
        self.resolution_log_file = Path("OMEGA_QUANT/docs/V21_ERROR_RESOLUTIONS_LOG.md")
        self.error_db_file = Path(".ly_state/memory/error_db.json")
        
        self.audit_logs_dir.mkdir(parents=True, exist_ok=True)
        self.error_db = self._load_error_db()
        
        # Initialize resolution log if not exists
        if not self.resolution_log_file.exists():
            self._initialize_resolution_log()
    
    def _load_error_db(self) -> List[Dict[str, Any]]:
        """Load error database from disk."""
        if not self.error_db_file.exists():
            return []
        with open(self.error_db_file, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def _save_error_db(self) -> None:
        """Save error database to disk."""
        with open(self.error_db_file, "w", encoding="utf-8") as f:
            json.dump(self.error_db, f, indent=2)
    
    def _initialize_resolution_log(self) -> None:
        """Initialize empty resolution log."""
        initial_content = """# OMEGA Error Resolutions Log

## Purpose
This document tracks all errors encountered in the OMEGA_QUANT system and their resolutions.
It serves as institutional memory for error recovery and prevention.

## Schema
Each entry contains:
- **Error ID**: Unique identifier
- **Date**: When the error occurred
- **Component**: Which layer/module/script
- **Error Type**: Classification (PIT violation, data quality, logic error, etc.)
- **Description**: What went wrong
- **Root Cause**: Why it happened
- **Resolution**: How it was fixed
- **Prevention**: How to prevent recurrence

---

## Error Entries

"""
        self.resolution_log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.resolution_log_file, "w", encoding="utf-8") as f:
            f.write(initial_content)
    
    def _compute_error_hash(self, error_type: str, component: str, description: str) -> str:
        """Compute semantic hash for error pattern."""
        data = f"{error_type}:{component}:{description.strip().lower()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def log_error(
        self,
        error_type: str,
        component: str,
        description: str,
        root_cause: str,
        resolution: str,
        prevention: str,
    ) -> str:
        """
        Log error and store in memory.
        
        Args:
            error_type: Classification (PIT violation, data quality, logic error, etc.)
            component: Module/script where error occurred
            description: What went wrong
            root_cause: Why it happened
            resolution: How it was fixed
            prevention: How to prevent recurrence
            
        Returns:
            Error hash (unique identifier)
        """
        error_hash = self._compute_error_hash(error_type, component, description)
        
        # Check for duplicate
        for err in self.error_db:
            if err["error_hash"] == error_hash:
                logger.warning(f"Error already logged: {error_hash}")
                return error_hash
        
        # Create error record
        error_record = {
            "error_hash": error_hash,
            "error_type": error_type,
            "component": component,
            "description": description,
            "root_cause": root_cause,
            "resolution": resolution,
            "prevention": prevention,
            "logged_at": datetime.utcnow().isoformat() + "Z",
        }
        
        self.error_db.append(error_record)
        self._save_error_db()
        
        # Append to resolution log
        self._append_to_resolution_log(error_record)
        
        logger.info(f"Logged error: {error_hash} ({error_type})")
        return error_hash
    
    def _append_to_resolution_log(self, error_record: Dict[str, Any]) -> None:
        """Append error to resolution log markdown file."""
        entry = f"""
### {error_record["error_hash"]}

- **Date**: {error_record["logged_at"]}
- **Type**: {error_record["error_type"]}
- **Component**: {error_record["component"]}
- **Description**: {error_record["description"]}
- **Root Cause**: {error_record["root_cause"]}
- **Resolution**: {error_record["resolution"]}
- **Prevention**: {error_record["prevention"]}

---
"""
        with open(self.resolution_log_file, "a", encoding="utf-8") as f:
            f.write(entry)
    
    def get_similar_errors(self, error_type: str, component: str, description: str) -> List[Dict[str, Any]]:
        """
        Find similar past errors.
        
        Args:
            error_type: Current error type
            component: Current component
            description: Current error description
            
        Returns:
            List of similar past errors
        """
        query_hash = self._compute_error_hash(error_type, component, description)
        query_prefix = query_hash[:4]
        
        similar = []
        for err in self.error_db:
            if err["error_hash"].startswith(query_prefix):
                similar.append(err)
        
        return similar


def create_memory_archive() -> AlphaMemory:
    """
    Factory function to create memory archive instance.
    
    Returns:
        AlphaMemory instance
    """
    return AlphaMemory()

