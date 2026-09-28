"""
Ensemble Weight Optimizer - V21 Institutional
Optimizes weights between models using SLSQP with constraints.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Callable, Optional, Tuple
import numpy as np
from scipy.optimize import minimize


@dataclass
class WeightsConfig:
    """Configuration for ensemble weight optimization."""
    max_weight: float = 0.6           # Max weight per model
    min_weight: float = 0.0           # Min weight per model
    smoothness: float = 0.2           # Smoothing factor (η)
    use_smoothing: bool = True        # Apply weight smoothing
    use_regularization: bool = True    # L2 regularization


class EnsembleOptimizer:
    """Optimize ensemble weights using SLSQP.
    
    Objective: Maximize Sharpe/IC subject to constraints.
    Constraints: w_i >= 0, sum(w) = 1, w_i <= w_max
    """
    
    def __init__(self, config: Optional[WeightsConfig] = None):
        self.config = config or WeightsConfig()
        self.previous_weights: Optional[np.ndarray] = None
    
    def set_previous_weights(self, weights: np.ndarray):
        """Set previous weights for smoothing."""
        self.previous_weights = weights
    
    def _objective(
        self,
        weights: np.ndarray,
        scores: np.ndarray,
        returns: np.ndarray,
        alpha: float = 0.5,
        beta: float = 2.0,
        gamma: float = 0.1,
        delta: float = 0.5
    ) -> float:
        """Objective function to minimize (negative of utility).
        
        Args:
            weights: Model weights
            scores: Model scores (signals)
            returns: Actual returns
            
        Returns:
            Negative utility (to minimize)
        """
        # Weighted signal
        weighted_signal = np.dot(scores, weights)
        
        # Compute metrics
        sharpe = self._compute_sharpe(weighted_signal, returns)
        ic = self._compute_ic(weighted_signal, returns)
        maxdd = self._compute_max_drawdown(weighted_signal, returns)
        turnover = self._compute_turnover(weights, self.previous_weights)
        weight_instability = np.std(weights - self.previous_weights) if self.previous_weights is not None else 0.0
        
        # Utility (maximize)
        utility = sharpe + alpha * ic - beta * maxdd - gamma * turnover - delta * weight_instability
        
        # Add regularization
        if self.config.use_regularization:
            reg = 0.01 * np.sum(weights ** 2)
            utility -= reg
        
        return -utility  # Minimize negative utility
    
    def _compute_sharpe(self, signals: np.ndarray, returns: np.ndarray) -> float:
        """Compute Sharpe ratio."""
        if len(signals) < 2:
            return 0.0
        mean_r = np.mean(signals * returns)
        std_r = np.std(signals * returns)
        if std_r == 0:
            return 0.0
        return (mean_r / std_r) * np.sqrt(252)
    
    def _compute_ic(self, signals: np.ndarray, returns: np.ndarray) -> float:
        """Compute Information Coefficient."""
        if len(signals) < 2:
            return 0.0
        return np.corrcoef(signals, returns)[0, 1]
    
    def _compute_max_drawdown(self, signals: np.ndarray, returns: np.ndarray) -> float:
        """Compute maximum drawdown."""
        if len(signals) == 0:
            return 0.0
        pnl = signals * returns
        cum = np.cumprod(1 + pnl)
        peak = np.maximum.accumulate(cum)
        dd = (peak - cum) / (peak + 1e-10)
        return np.max(dd)
    
    def _compute_turnover(self, weights: np.ndarray, prev_weights: Optional[np.ndarray]) -> float:
        """Compute portfolio turnover."""
        if prev_weights is None:
            return 0.0
        return np.sum(np.abs(weights - prev_weights))
    
    def optimize(
        self,
        scores: Dict[str, np.ndarray],
        returns: np.ndarray,
        n_models: int
    ) -> Tuple[np.ndarray, float]:
        """Optimize ensemble weights.
        
        Args:
            scores: Dictionary of model_name -> scores
            returns: Actual returns
            n_models: Number of models
            
        Returns:
            (optimal_weights, utility_score)
        """
        # Stack scores
        score_matrix = np.column_stack([scores[f"model_{i}"] for i in range(n_models)])
        
        # Initial weights
        x0 = np.ones(n_models) / n_models
        
        # Constraints
        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0}  # sum(w) = 1
        ]
        
        # Bounds
        bounds = [(self.config.min_weight, self.config.max_weight) for _ in range(n_models)]
        
        # Optimize
        result = minimize(
            self._objective,
            x0,
            args=(score_matrix.mean(axis=1), returns),
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )
        
        weights = result.x
        
        # Apply smoothing
        if self.config.use_smoothing and self.previous_weights is not None:
            eta = self.config.smoothness
            weights = (1 - eta) * self.previous_weights + eta * weights
            weights = weights / np.sum(weights)  # Renormalize
        
        # Apply weight cap
        weights = np.clip(weights, self.config.min_weight, self.config.max_weight)
        weights = weights / np.sum(weights)  # Renormalize
        
        utility = -result.fun
        
        return weights, utility

    def apply_jev_weight_tilt(
        self, base_weights: np.ndarray, model_names: list[str], current_regime: str,
        alpha_decay_rates: dict[str, float], ic_correlations: dict[str, float],
        as_of: datetime, available_at: datetime, cache_path: Path,
        model: str = "jev-hybrid",
        influence: float = 0.0,
        alpha_families: Optional[dict[str, str]] = None,
    ) -> np.ndarray:
        """Tilt optimized weights only when historical evidence and JEV are valid."""
        from omega.core.llm_config import classify_jev

        weights = np.asarray(base_weights, dtype=float)
        if (weights.ndim != 1 or not len(weights) or len(weights) != len(model_names)
                or len(set(model_names)) != len(model_names) or any(type(n) is not str for n in model_names)
                or not np.isfinite(weights).all() or (weights < 0).any()
                or not np.isclose(weights.sum(), 1) or not isinstance(as_of, datetime)
                or not isinstance(available_at, datetime) or as_of.tzinfo is None
                or available_at.tzinfo is None or available_at > as_of
                or type(current_regime) is not str
                or set(alpha_decay_rates) != set(model_names)
                 or set(ic_correlations) != set(model_names)
                 or type(influence) not in (int, float) or not np.isfinite(influence)
                 or not 0 <= influence <= 1):
            raise ValueError("invalid JEV weight evidence")
        low, high = self.config.min_weight, self.config.max_weight
        if (not np.isfinite([low, high]).all() or low < 0 or high > 1 or low > high
                or len(weights) * low > 1 or len(weights) * high < 1
                or (weights < low - 1e-8).any() or (weights > high + 1e-8).any()):
            raise ValueError("infeasible baseline weights")
        decay = np.array([alpha_decay_rates[n] for n in model_names], dtype=float)
        correlation = np.array([ic_correlations[n] for n in model_names], dtype=float)
        if (not np.isfinite(decay).all() or not np.isfinite(correlation).all()
                or (decay < 0).any() or (np.abs(correlation) > 1).any()):
            raise ValueError("invalid alpha metrics")
        if influence == 0:
            return weights.copy()
        if (not isinstance(alpha_families, dict) or set(alpha_families) != set(model_names)
                or any(f not in ("momentum", "mean_reversion", "defensive") for f in alpha_families.values())):
            raise ValueError("explicit alpha family mapping required")
        choices = ("momentum_heavy", "mean_reversion_heavy", "balanced", "defensive")
        try:
            result = classify_jev(
                domain="alpha_weight_regime",
                facts={"regime": current_regime, "alpha_decay_rates": dict(zip(model_names, decay.tolist())),
                       "ic_correlations": dict(zip(model_names, correlation.tolist()))},
                choices={"weight_regime": choices}, cache_path=cache_path,
                as_of=as_of, available_at=available_at, model=model,
            )
            selected = result["selected"]["weight_regime"]
            if type(selected) is not str or selected not in choices:
                return weights.copy()
            if set(result["selected"]) != {"weight_regime"}:
                return weights.copy()
            disagreement_result = classify_jev(
                domain="alpha_disagreement",
                facts={"regime": current_regime, "alpha_decay_rates": dict(zip(model_names, decay.tolist())),
                       "ic_correlations": dict(zip(model_names, correlation.tolist()))},
                choices={"outcome": ("trend_supported", "reversal_supported", "mixed", "insufficient")},
                cache_path=cache_path, as_of=as_of, available_at=available_at, model=model,
            )
            if set(disagreement_result["selected"]) != {"outcome"}:
                return weights.copy()
            disagreement = disagreement_result["selected"]["outcome"]
            if disagreement not in ("trend_supported", "reversal_supported", "mixed"):
                return weights.copy()
            if (selected == "momentum_heavy" and disagreement != "trend_supported"
                    or selected == "mean_reversion_heavy" and disagreement != "reversal_supported"):
                return weights.copy()
        except Exception:
            return weights.copy()
        momentum = np.array([alpha_families[n] == "momentum" for n in model_names])
        reversal = np.array([alpha_families[n] == "mean_reversion" for n in model_names])
        multipliers = np.ones(len(weights))
        if selected == "momentum_heavy":
            multipliers[momentum] = 1.25
            multipliers[reversal] = .75
        elif selected == "mean_reversion_heavy":
            multipliers[reversal] = 1.25
            multipliers[momentum] = .75
        elif selected == "defensive":
            multipliers[momentum | reversal] = .75
        tilted = weights * multipliers
        if not tilted.sum():
            return weights.copy()
        tilted /= tilted.sum()
        tilted = (1 - influence) * weights + influence * tilted
        # Preserve SLSQP box constraints by projecting onto the bounded simplex.
        left, right = float(np.min(tilted - high)), float(np.max(tilted - low))
        for _ in range(60):
            midpoint = (left + right) / 2
            if np.clip(tilted - midpoint, low, high).sum() > 1:
                left = midpoint
            else:
                right = midpoint
        projected = np.clip(tilted - (left + right) / 2, low, high)
        if (not np.isfinite(projected).all() or abs(projected.sum() - 1) > 1e-8
                or (projected < low - 1e-8).any() or (projected > high + 1e-8).any()):
            return weights.copy()
        return projected
    
    def deactivate_poor_models(
        self,
        weights: np.ndarray,
        performance_history: Dict[int, List[float]],
        n_weeks_poor: int = 3,
        min_ic: float = 0.0
    ) -> np.ndarray:
        """Deactivate models that consistently underperform.
        
        Args:
            weights: Current weights
            performance_history: Dictionary of model_index -> list of ICs
            n_weeks_poor: Weeks of poor performance before deactivation
            min_ic: Minimum IC threshold
            
        Returns:
            Adjusted weights
        """
        for i, ic_list in performance_history.items():
            if len(ic_list) >= n_weeks_poor:
                avg_ic = np.mean(ic_list[-n_weeks_poor:])
                if avg_ic < min_ic:
                    weights[i] = 0.0
        
        # Renormalize
        weights = weights / np.sum(weights) if np.sum(weights) > 0 else weights
        
        return weights
