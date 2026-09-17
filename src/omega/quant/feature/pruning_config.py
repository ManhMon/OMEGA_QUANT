"""Feature Pruning configuration and results structures."""

from __future__ import annotations

from typing import Dict, List
from dataclasses import dataclass, field


@dataclass
class FeaturePruningConfig:
    """Configuration for feature pruning"""
    min_ic_threshold: float = 0.02  # Minimum absolute IC to keep feature
    stability_window: int = 252  # Rolling window for stability analysis (1 year)
    stability_threshold: float = 0.5  # Min IC Information Ratio (mean/std)
    progressive_rate: float = 0.15  # Remove max 15% of features per iteration
    min_features: int = 10  # Never go below this number
    forward_return_period: int = 5  # Days ahead for return calculation
    use_oos_ic: bool = True  # Whether to use out-of-sample IC (walk-forward)
    max_correlation: float = 0.85  # Max allowed correlation between features


@dataclass
class PruningResult:
    """Result of feature pruning operation"""
    kept_features: List[str] = field(default_factory=list)
    removed_features: List[str] = field(default_factory=list)
    feature_ics: Dict[str, float] = field(default_factory=dict)
    stability_scores: Dict[str, float] = field(default_factory=dict)
    pruning_history: List[Dict] = field(default_factory=list)
    
    def summary(self) -> str:
        """Generate summary string"""
        return (
            f"Kept: {len(self.kept_features)} features\n"
            f"Removed: {len(self.removed_features)} features\n"
            f"Removal rate: {len(self.removed_features) / (len(self.kept_features) + len(self.removed_features)):.1%}"
        )
