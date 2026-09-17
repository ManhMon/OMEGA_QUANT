"""
Gap Phase 6.3: Alpha to Execution Bridge - OMEGA Edition
Layer 08: Self-Evolving Engine

Bridges Alpha Generation / Discovery with the Execution Engine.
Enforces multi-horizon labels (T+3 / T+5) and chronological embargo requirements.

Embargo Rules:
- T+3 horizon: Validation/Promotion blocked for 4 days after training (train_end_date + 4)
- T+5 horizon: Validation/Promotion blocked for 6 days after training (train_end_date + 6)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import logging
import warnings

logger = logging.getLogger("OmegaAlphaBridge")

CANONICAL_METRIC_KEY = "signal_pnl_score"
LEGACY_METRIC_ALIASES = {"sharpe": CANONICAL_METRIC_KEY, "annualized_sharpe": CANONICAL_METRIC_KEY}


def resolve_metric_config(payload: Dict[str, Any]) -> tuple[str | None, list[str]]:
    """Return canonical metric selection from JSON-like payload.

    Canonical key wins. Conflicting legacy aliases warn but do not override.
    """
    warnings_list: list[str] = []
    canonical = payload.get(CANONICAL_METRIC_KEY)
    legacy_values = {key: payload[key] for key in LEGACY_METRIC_ALIASES if key in payload}
    if canonical is None and legacy_values:
        canonical = next(iter(legacy_values.values()))
    elif canonical is not None:
        for key, value in legacy_values.items():
            if value != canonical:
                msg = f"Conflicting metric keys: {CANONICAL_METRIC_KEY} overrides {key}"
                warnings.warn(msg, RuntimeWarning)
                warnings_list.append(msg)
    return canonical, warnings_list


def resolve_metric_cli(*, signal_pnl_score: str | None = None, sharpe: str | None = None, annualized_sharpe: str | None = None) -> str | None:
    values = [value for value in (signal_pnl_score, sharpe, annualized_sharpe) if value is not None]
    if not values:
        return None
    normalized = {str(value) for value in values}
    if len(normalized) > 1:
        raise ValueError("Conflicting metric CLI aliases")
    return values[0]


@dataclass
class AlphaBridgeConfig:
    """Configuration for Alpha to Execution Bridge"""
    t3_embargo_days: int = 4  # T+3 label becomes available at T+4
    t5_embargo_days: int = 6  # T+5 label becomes available at T+6
    min_alpha_weight: float = 0.05
    max_alpha_weight: float = 0.35


class AlphaToExecutionBridge:
    """
    Bridges alpha signals with execution routing while enforcing temporal safeguards.
    """
    
    def __init__(self, config: Optional[AlphaBridgeConfig] = None):
        self.config = config or AlphaBridgeConfig()
        self.active_alphas: Dict[str, Dict[str, Any]] = {}
    
    def register_alpha(
        self,
        alpha_id: str,
        formula: str,
        horizon: int,  # 3 or 5
        train_end_date: pd.Timestamp,
        ic: float,
        sharpe: float
    ) -> bool:
        """
        Register a new evolved alpha signal.
        
        Args:
            alpha_id: Unique signal identifier
            formula: Alpha math formula
            horizon: Return horizon in days (3 or 5)
            train_end_date: End of training date
            ic: Information Coefficient
            sharpe: Sharpe ratio
            
        Returns:
            True if registered successfully
        """
        if horizon not in [3, 5]:
            logger.warning(f"Unsupported horizon {horizon} for alpha {alpha_id}")
            return False
            
        self.active_alphas[alpha_id] = {
            "alpha_id": alpha_id,
            "formula": formula,
            "horizon": horizon,
            "train_end_date": train_end_date,
            "ic": ic,
            CANONICAL_METRIC_KEY: sharpe,
            "sharpe": sharpe,
            "status": "registered"
        }
        return True
    
    def validate_embargo(
        self,
        alpha_id: str,
        current_date: pd.Timestamp
    ) -> bool:
        """
        Enforce T-1 lag and T+3/T+5 embargo constraints.
        
        Args:
            alpha_id: Signal identifier
            current_date: Current simulation date
            
        Returns:
            True if embargo is satisfied (model is safe to deploy/validate)
        """
        alpha = self.active_alphas.get(alpha_id)
        if not alpha:
            return False
            
        horizon = alpha["horizon"]
        train_end = alpha["train_end_date"]
        
        # Enforce embargo days depending on return horizon
        required_embargo = self.config.t3_embargo_days if horizon == 3 else self.config.t5_embargo_days
        days_passed = (current_date - train_end).days
        
        is_safe = days_passed >= required_embargo
        
        if not is_safe:
            logger.warning(
                f"Alpha {alpha_id} (T+{horizon}) blocked by embargo! "
                f"Days passed: {days_passed}, Required: {required_embargo}"
            )
        
        return is_safe
    
    def convert_signals_to_weights(
        self,
        signals: Dict[str, pd.Series],
        current_date: pd.Timestamp
    ) -> Dict[str, Dict[str, float]]:
        """
        Convert active and embargo-validated alpha signals to portfolio weights.
        
        Args:
            signals: Dict of alpha_id -> Series of stock signals at current_date
            current_date: Current simulation date
            
        Returns:
            Dict of ticker -> allocation weight
        """
        validated_signals = {}
        
        # 1. Filter signals through embargo validation
        for alpha_id, signal_series in signals.items():
            if self.validate_embargo(alpha_id, current_date):
                validated_signals[alpha_id] = signal_series
                
        if not validated_signals:
            logger.warning("No embargo-validated signals available for weight allocation!")
            return {}
            
        # 2. Equal-weighted blend of active signals (vectorized)
        combined_signal = pd.Series(dtype=float)
        for alpha_id, sig in validated_signals.items():
            if combined_signal.empty:
                combined_signal = sig
            else:
                combined_signal += sig
                
        combined_signal /= len(validated_signals)
        
        # 3. Scale weights to config bounds [min_weight, max_weight]
        ranks = combined_signal.rank(pct=True)
        weights = {}
        
        for ticker, rank in ranks.items():
            if rank > 0.70:  # Top 30% stocks
                weight = self.config.min_alpha_weight + (rank - 0.70) * (self.config.max_alpha_weight - self.config.min_alpha_weight) / 0.30
                weights[ticker] = min(weight, self.config.max_alpha_weight)
                
        return weights
