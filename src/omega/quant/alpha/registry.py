"""
Alpha Registry - Institutional Grade
Version: 2.4
Status: Production Ready

Manages alpha factor lifecycle:
- Registration and versioning
- IC tracking over time
- Auto-retirement (IC decay detection)
- Auto-promotion (IC stability validation)
- Audit trail (JSONL append-only log)

Contract:
- All alphas must have unique ID (hash of expression + timestamp)
- IC tracked per alpha per date
- Decay detection: rolling 60-day IC window
- Promotion criteria: IC > threshold for 90+ days
- Retirement criteria: IC < threshold for 30+ days

Author: OMEGA_QUANT Team
Last Updated: 2026-05-26
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)


@dataclass
class AlphaMetadata:
    """Metadata for a single alpha factor."""
    
    alpha_id: str  # Unique ID (SHA256 hash)
    name: str  # Human-readable name
    expression: str  # Mathematical expression or description
    created_at: str  # ISO timestamp
    status: str  # "candidate", "promoted", "retired"
    
    # Performance metrics
    ic_history: List[Tuple[str, float]] = field(default_factory=list)  # [(date, ic), ...]
    rolling_ic_60d: float = 0.0  # 60-day rolling IC
    rolling_ic_90d: float = 0.0  # 90-day rolling IC
    sharpe: float = 0.0
    turnover: float = 0.0
    
    # Lifecycle tracking
    promoted_at: Optional[str] = None
    retired_at: Optional[str] = None
    retirement_reason: Optional[str] = None
    
    # Lineage
    parent_alpha_id: Optional[str] = None
    generation: int = 0  # GP generation (0 = manual)
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class AlphaRegistryConfig:
    """Configuration for AlphaRegistry."""
    
    # IC thresholds
    promotion_ic_threshold: float = 0.02  # Min IC for promotion
    promotion_stability_days: int = 90  # Days of stable IC required
    retirement_ic_threshold: float = 0.005  # IC below this triggers retirement
    retirement_decay_days: int = 30  # Days of low IC before retirement
    
    # Rolling window sizes
    rolling_ic_window_short: int = 60  # Short-term IC window
    rolling_ic_window_long: int = 90  # Long-term IC window
    
    # Storage
    registry_path: str = "state/alpha_registry.jsonl"
    backup_path: str = "state/alpha_registry_backup.jsonl"


class AlphaRegistry:
    """
    Alpha Registry - Manages alpha factor lifecycle.
    
    Features:
    - Version control for alphas
    - IC tracking over time
    - Auto-retirement on IC decay
    - Auto-promotion on IC stability
    - Audit trail (JSONL append-only)
    
    Usage:
        registry = AlphaRegistry()
        alpha_id = registry.register_alpha("momentum_5d", "close / close.shift(5) - 1")
        registry.update_ic(alpha_id, date="2026-05-26", ic=0.035)
        registry.check_lifecycle()  # Auto-promote/retire
    """
    
    CONTRACT_HASH = "alpha_registry_v2.4_20260526"
    
    def __init__(self, config: Optional[AlphaRegistryConfig] = None):
        self.config = config or AlphaRegistryConfig()
        self.registry_path = Path(self.config.registry_path)
        self.backup_path = Path(self.config.backup_path)
        
        # In-memory registry
        self._alphas: Dict[str, AlphaMetadata] = {}
        
        # Create directories
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing registry
        self._load_registry()
        
        logger.info("AlphaRegistry initialized: %d alphas loaded", len(self._alphas))
    
    def _load_registry(self) -> None:
        """Load registry from JSONL file."""
        if not self.registry_path.exists():
            logger.info("No existing registry found, starting fresh")
            return
        
        with open(self.registry_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    alpha = AlphaMetadata(**data)
                    self._alphas[alpha.alpha_id] = alpha
        
        logger.info("Loaded %d alphas from registry", len(self._alphas))
    
    def _save_alpha(self, alpha: AlphaMetadata) -> None:
        """Append alpha to JSONL registry."""
        with open(self.registry_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(alpha)) + "\n")
    
    def _backup_registry(self) -> None:
        """Create backup of registry."""
        if self.registry_path.exists():
            import shutil
            shutil.copy(self.registry_path, self.backup_path)
            logger.info("Registry backed up to %s", self.backup_path)
    
    def register_alpha(
        self,
        name: str,
        expression: str,
        tags: Optional[List[str]] = None,
        parent_alpha_id: Optional[str] = None,
        generation: int = 0,
        notes: str = "",
    ) -> str:
        """
        Register a new alpha factor.
        
        Args:
            name: Human-readable name
            expression: Mathematical expression or description
            tags: Optional tags for categorization
            parent_alpha_id: Parent alpha (for GP evolution tracking)
            generation: GP generation (0 = manual)
            notes: Additional notes
        
        Returns:
            alpha_id: Unique ID for this alpha
        """
        # Generate unique ID
        timestamp = datetime.now(timezone.utc).isoformat()
        hash_input = f"{name}:{expression}:{timestamp}".encode("utf-8")
        alpha_id = hashlib.sha256(hash_input).hexdigest()[:16]
        
        # Check for duplicates
        if alpha_id in self._alphas:
            logger.warning("Alpha ID collision detected, appending random suffix")
            import random
            alpha_id = f"{alpha_id}_{random.randint(1000, 9999)}"
        
        # Create metadata
        alpha = AlphaMetadata(
            alpha_id=alpha_id,
            name=name,
            expression=expression,
            created_at=timestamp,
            status="candidate",
            tags=tags or [],
            parent_alpha_id=parent_alpha_id,
            generation=generation,
            notes=notes,
        )
        
        # Save to registry
        self._alphas[alpha_id] = alpha
        self._save_alpha(alpha)
        
        logger.info("Registered alpha: %s (ID=%s)", name, alpha_id)
        return alpha_id
    
    def update_ic(
        self,
        alpha_id: str,
        date: str,
        ic: float,
        sharpe: Optional[float] = None,
        turnover: Optional[float] = None,
    ) -> None:
        """
        Update IC for an alpha on a specific date.
        
        Args:
            alpha_id: Alpha ID
            date: Date (ISO format or YYYY-MM-DD)
            ic: Information Coefficient
            sharpe: Optional Sharpe ratio
            turnover: Optional turnover
        """
        if alpha_id not in self._alphas:
            raise ValueError(f"Alpha ID not found: {alpha_id}")
        
        alpha = self._alphas[alpha_id]
        
        # Append IC to history
        alpha.ic_history.append((date, ic))
        
        # Update rolling ICs
        alpha.rolling_ic_60d = self._compute_rolling_ic(
            alpha.ic_history, window=self.config.rolling_ic_window_short
        )
        alpha.rolling_ic_90d = self._compute_rolling_ic(
            alpha.ic_history, window=self.config.rolling_ic_window_long
        )
        
        # Update other metrics
        if sharpe is not None:
            alpha.sharpe = sharpe
        if turnover is not None:
            alpha.turnover = turnover
        
        # Save updated alpha
        self._save_alpha(alpha)
        
        logger.debug("Updated IC for %s: date=%s, ic=%.4f, rolling_60d=%.4f",
                    alpha.name, date, ic, alpha.rolling_ic_60d)
    
    def _compute_rolling_ic(
        self, ic_history: List[Tuple[str, float]], window: int
    ) -> float:
        """Compute rolling IC over last N days."""
        if len(ic_history) < window:
            return 0.0
        
        recent_ics = [ic for _, ic in ic_history[-window:]]
        return float(np.mean(recent_ics))
    
    def check_lifecycle(self) -> Dict[str, List[str]]:
        """
        Check lifecycle for all alphas and auto-promote/retire.
        
        Returns:
            Dict with "promoted" and "retired" alpha IDs
        """
        promoted = []
        retired = []
        
        for alpha_id, alpha in self._alphas.items():
            if alpha.status == "candidate":
                # Check for promotion
                if self._should_promote(alpha):
                    self._promote_alpha(alpha_id)
                    promoted.append(alpha_id)
                
                # Check for retirement
                elif self._should_retire(alpha):
                    self._retire_alpha(alpha_id, reason="IC decay below threshold")
                    retired.append(alpha_id)
            
            elif alpha.status == "promoted":
                # Check for retirement (promoted alphas can still decay)
                if self._should_retire(alpha):
                    self._retire_alpha(alpha_id, reason="IC decay after promotion")
                    retired.append(alpha_id)
        
        if promoted:
            logger.info("Promoted %d alphas: %s", len(promoted), promoted)
        if retired:
            logger.info("Retired %d alphas: %s", len(retired), retired)
        
        return {"promoted": promoted, "retired": retired}
    
    def _should_promote(self, alpha: AlphaMetadata) -> bool:
        """Check if alpha should be promoted."""
        # Criteria:
        # 1. Rolling 90d IC > promotion threshold
        # 2. At least 90 days of history
        # 3. IC stable (no large drops)
        
        if len(alpha.ic_history) < self.config.promotion_stability_days:
            return False
        
        if alpha.rolling_ic_90d < self.config.promotion_ic_threshold:
            return False
        
        # Check stability (no IC drop > 50% in last 30 days)
        recent_ics = [ic for _, ic in alpha.ic_history[-30:]]
        if len(recent_ics) > 0:
            ic_std = np.std(recent_ics)
            ic_mean = np.mean(recent_ics)
            if ic_mean > 0 and ic_std / ic_mean > 0.5:
                return False
        
        return True
    
    def _should_retire(self, alpha: AlphaMetadata) -> bool:
        """Check if alpha should be retired."""
        # Criteria:
        # 1. Rolling 60d IC < retirement threshold
        # 2. At least 30 days of low IC
        
        if len(alpha.ic_history) < self.config.retirement_decay_days:
            return False
        
        if alpha.rolling_ic_60d < self.config.retirement_ic_threshold:
            # Check if IC has been low for 30+ days
            recent_ics = [ic for _, ic in alpha.ic_history[-self.config.retirement_decay_days:]]
            if np.mean(recent_ics) < self.config.retirement_ic_threshold:
                return True
        
        return False
    
    def _promote_alpha(self, alpha_id: str) -> None:
        """Promote alpha to production."""
        alpha = self._alphas[alpha_id]
        alpha.status = "promoted"
        alpha.promoted_at = datetime.now(timezone.utc).isoformat()
        self._save_alpha(alpha)
        logger.info("Promoted alpha: %s (IC_90d=%.4f)", alpha.name, alpha.rolling_ic_90d)
    
    def _retire_alpha(self, alpha_id: str, reason: str) -> None:
        """Retire alpha from production."""
        alpha = self._alphas[alpha_id]
        alpha.status = "retired"
        alpha.retired_at = datetime.now(timezone.utc).isoformat()
        alpha.retirement_reason = reason
        self._save_alpha(alpha)
        logger.info("Retired alpha: %s (reason=%s)", alpha.name, reason)
    
    def get_alpha(self, alpha_id: str) -> Optional[AlphaMetadata]:
        """Get alpha metadata by ID."""
        return self._alphas.get(alpha_id)
    
    def get_promoted_alphas(self) -> List[AlphaMetadata]:
        """Get all promoted alphas."""
        return [alpha for alpha in self._alphas.values() if alpha.status == "promoted"]
    
    def get_candidate_alphas(self) -> List[AlphaMetadata]:
        """Get all candidate alphas."""
        return [alpha for alpha in self._alphas.values() if alpha.status == "candidate"]
    
    def get_retired_alphas(self) -> List[AlphaMetadata]:
        """Get all retired alphas."""
        return [alpha for alpha in self._alphas.values() if alpha.status == "retired"]
    
    def search_alphas(
        self,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_ic: Optional[float] = None,
        max_ic: Optional[float] = None,
    ) -> List[AlphaMetadata]:
        """
        Search alphas by criteria.
        
        Args:
            status: Filter by status ("candidate", "promoted", "retired")
            tags: Filter by tags (any match)
            min_ic: Minimum rolling 60d IC
            max_ic: Maximum rolling 60d IC
        
        Returns:
            List of matching alphas
        """
        results = []
        
        for alpha in self._alphas.values():
            # Status filter
            if status and alpha.status != status:
                continue
            
            # Tags filter
            if tags and not any(tag in alpha.tags for tag in tags):
                continue
            
            # IC filter
            if min_ic is not None and alpha.rolling_ic_60d < min_ic:
                continue
            if max_ic is not None and alpha.rolling_ic_60d > max_ic:
                continue
            
            results.append(alpha)
        
        return results
    
    def get_leaderboard(self, top_n: int = 10, metric: str = "rolling_ic_60d") -> List[AlphaMetadata]:
        """
        Get top N alphas by metric.
        
        Args:
            top_n: Number of alphas to return
            metric: Metric to sort by ("rolling_ic_60d", "rolling_ic_90d", "sharpe")
        
        Returns:
            List of top alphas
        """
        alphas = [alpha for alpha in self._alphas.values() if alpha.status != "retired"]
        alphas.sort(key=lambda a: getattr(a, metric, 0.0), reverse=True)
        return alphas[:top_n]
    
    def export_registry(self, output_path: str) -> None:
        """Export registry to JSON file."""
        output = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_alphas": len(self._alphas),
            "promoted": len(self.get_promoted_alphas()),
            "candidates": len(self.get_candidate_alphas()),
            "retired": len(self.get_retired_alphas()),
            "alphas": [asdict(alpha) for alpha in self._alphas.values()],
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        
        logger.info("Registry exported to %s", output_path)
    
    def compute_alpha_correlation_matrix(self) -> pd.DataFrame:
        """
        Compute correlation matrix between promoted alphas.
        
        Returns:
            DataFrame with pairwise correlations
        """
        promoted = self.get_promoted_alphas()
        
        if len(promoted) < 2:
            logger.warning("Need at least 2 promoted alphas for correlation matrix")
            return pd.DataFrame()
        
        # Extract IC time series for each alpha
        ic_series = {}
        for alpha in promoted:
            if len(alpha.ic_history) > 0:
                dates, ics = zip(*alpha.ic_history)
                ic_series[alpha.name] = pd.Series(ics, index=dates)
        
        # Align time series
        df = pd.DataFrame(ic_series)
        
        # Compute correlation
        corr_matrix = df.corr()
        
        logger.info("Computed correlation matrix for %d alphas", len(promoted))
        return corr_matrix
    
    def prune_history(self, keep_days: int = 365) -> int:
        """
        Prune old IC history to save memory.
        
        Args:
            keep_days: Number of days to keep
        
        Returns:
            Number of entries pruned
        """
        pruned_count = 0
        cutoff_date = (datetime.now(timezone.utc) - pd.Timedelta(days=keep_days)).isoformat()
        
        for alpha in self._alphas.values():
            original_len = len(alpha.ic_history)
            alpha.ic_history = [
                (date, ic) for date, ic in alpha.ic_history if date >= cutoff_date
            ]
            pruned_count += original_len - len(alpha.ic_history)
        
        logger.info("Pruned %d IC history entries (kept last %d days)", pruned_count, keep_days)
        return pruned_count
    
    def get_summary(self) -> Dict[str, Any]:
        """Get registry summary statistics."""
        promoted = self.get_promoted_alphas()
        candidates = self.get_candidate_alphas()
        retired = self.get_retired_alphas()
        
        return {
            "total_alphas": len(self._alphas),
            "promoted": len(promoted),
            "candidates": len(candidates),
            "retired": len(retired),
            "avg_ic_promoted": np.mean([a.rolling_ic_60d for a in promoted]) if promoted else 0.0,
            "avg_ic_candidates": np.mean([a.rolling_ic_60d for a in candidates]) if candidates else 0.0,
            "top_alpha": promoted[0].name if promoted else None,
            "top_alpha_ic": promoted[0].rolling_ic_60d if promoted else 0.0,
        }
