"""LLM Formula Quality Scorer.

Scores and filters LLM-generated formulas before they enter the model feature set.
Rejects weak formulas based on coverage, variance, stability, and optional IC/DSR.

PIT Safety: Only uses training/panel data available at synthesis time.
No future/test labels are used in feature generation decisions.

Author: Backend Engineer (Role 09)
Date: 2026-06-12
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FormulaQualityMetrics:
    """Quality metrics for a single formula."""
    
    # Unsupervised metrics (always computed)
    non_nan_coverage: float  # Fraction of valid (non-NaN, non-inf) values
    variance: float  # Variance of valid values
    per_ticker_stability: float  # Average per-ticker variance (lower = more stable)
    nan_inf_ratio: float  # Fraction of NaN/inf values
    
    # Supervised metrics (computed only if labels provided)
    absolute_ic: Optional[float] = None  # Absolute Information Coefficient
    dsr_proxy: Optional[float] = None  # Simple Sharpe-like ratio (mean/std)
    
    # Validation metadata (L3 audit requirement: explicit deployment safety tracking)
    is_supervised_validated: bool = False  # True if labels provided and supervised checks passed
    is_deployable: bool = False  # False for unsupervised-only formulas (not production-ready)
    validation_mode: str = "unknown"  # "supervised", "unsupervised_only", "unsupervised_panel_only"
    
    # Status
    accepted: bool = False
    rejection_reasons: list[str] = None
    
    def __post_init__(self):
        if self.rejection_reasons is None:
            self.rejection_reasons = []


@dataclass
class FormulaScorerConfig:
    """Configuration for formula quality thresholds."""
    
    # Unsupervised thresholds (always applied)
    min_coverage: float = 0.80  # Require 80% non-NaN coverage
    min_variance: float = 1e-8  # Reject near-constant formulas
    max_per_ticker_variance: float = 1e6  # Reject unstable formulas (huge variance)
    max_nan_inf_ratio: float = 0.20  # Reject if >20% NaN/inf
    
    # Supervised thresholds (applied only if labels available)
    min_absolute_ic: float = 0.01  # Require |IC| >= 0.01 (weak signal threshold)
    min_dsr_proxy: float = -0.5  # Reject if DSR proxy suggests negative edge
    
    # Override flag
    allow_unvalidated: bool = False  # If True, accept formulas without supervised checks
    
    def __post_init__(self):
        """Validate config values."""
        assert 0.0 <= self.min_coverage <= 1.0, "min_coverage must be in [0, 1]"
        assert self.min_variance >= 0, "min_variance must be non-negative"
        assert self.max_per_ticker_variance > 0, "max_per_ticker_variance must be positive"
        assert 0.0 <= self.max_nan_inf_ratio <= 1.0, "max_nan_inf_ratio must be in [0, 1]"


class FormulaScorer:
    """
    Scores and filters LLM-generated formulas based on quality metrics.
    
    PIT Safety:
    - Only uses data available at synthesis time (training/panel data)
    - If labels provided, assumes they are from same time period (PIT-safe)
    - Never uses future/test labels in decision
    
    Default behavior: Safe (reject if uncertain)
    - Formulas without supervised validation are rejected unless allow_unvalidated=True
    - Borderline cases are rejected to avoid polluting the feature set
    """
    
    def __init__(self, config: Optional[FormulaScorerConfig] = None):
        """
        Initialize scorer.
        
        Args:
            config: Quality thresholds configuration (default: safe defaults)
        """
        self.config = config or FormulaScorerConfig()
        logger.info(
            "FormulaScorer initialized: min_coverage=%.2f min_var=%.2e "
            "min_|IC|=%.3f min_DSR=%.2f allow_unvalidated=%s",
            self.config.min_coverage,
            self.config.min_variance,
            self.config.min_absolute_ic,
            self.config.min_dsr_proxy,
            self.config.allow_unvalidated,
        )
    
    def _compute_unsupervised_metrics(
        self,
        values: np.ndarray,
        ticker_groups: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Compute unsupervised quality metrics.
        
        Args:
            values: Formula output values (1-D array)
            ticker_groups: Optional ticker group indices for stability check
        
        Returns:
            Dictionary of unsupervised metrics
        """
        # Coverage: fraction of valid (non-NaN, non-inf) values
        valid_mask = np.isfinite(values)
        non_nan_coverage = float(np.mean(valid_mask))
        nan_inf_ratio = 1.0 - non_nan_coverage
        
        # Variance of valid values
        valid_values = values[valid_mask]
        if len(valid_values) < 2:
            variance = 0.0
        else:
            variance = float(np.var(valid_values, ddof=1))
        
        # Per-ticker stability (average within-ticker variance)
        per_ticker_stability = None
        if ticker_groups is not None and len(valid_values) > 0:
            ticker_variances = []
            for ticker_id in np.unique(ticker_groups):
                ticker_mask = (ticker_groups == ticker_id) & valid_mask
                ticker_vals = values[ticker_mask]
                if len(ticker_vals) >= 2:
                    ticker_var = float(np.var(ticker_vals, ddof=1))
                    ticker_variances.append(ticker_var)
            
            if ticker_variances:
                per_ticker_stability = float(np.mean(ticker_variances))
            else:
                per_ticker_stability = 0.0
        else:
            # Fallback: use global variance as stability proxy
            per_ticker_stability = variance
        
        return {
            "non_nan_coverage": non_nan_coverage,
            "variance": variance,
            "per_ticker_stability": per_ticker_stability,
            "nan_inf_ratio": nan_inf_ratio,
        }
    
    def _compute_supervised_metrics(
        self,
        values: np.ndarray,
        labels: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Compute supervised quality metrics (IC, DSR proxy).
        
        PIT Safety: Assumes labels are from the same time period as values
        (training data only). Caller must ensure no future labels are used.
        
        Args:
            values: Formula output values (1-D array)
            labels: Target labels (1-D array, same length as values)
        
        Returns:
            Dictionary of supervised metrics
        """
        # Filter to rows where both values and labels are valid
        valid_mask = np.isfinite(values) & np.isfinite(labels)
        
        if np.sum(valid_mask) < 2:
            # Not enough valid pairs for correlation
            return {
                "absolute_ic": 0.0,
                "dsr_proxy": 0.0,
            }
        
        valid_values = values[valid_mask]
        valid_labels = labels[valid_mask]
        
        # Information Coefficient (Pearson correlation)
        try:
            ic = float(np.corrcoef(valid_values, valid_labels)[0, 1])
            absolute_ic = abs(ic)
        except Exception:
            ic = 0.0
            absolute_ic = 0.0
        
        # DSR proxy: simple Sharpe-like ratio
        # Compute per-observation "returns" as sign(prediction) * actual_return
        # DSR proxy = mean / std of these aligned returns
        aligned_returns = np.sign(valid_values) * valid_labels
        if len(aligned_returns) >= 2 and np.std(aligned_returns, ddof=1) > 1e-12:
            dsr_proxy = float(np.mean(aligned_returns) / np.std(aligned_returns, ddof=1))
        else:
            dsr_proxy = 0.0
        
        return {
            "absolute_ic": absolute_ic,
            "dsr_proxy": dsr_proxy,
        }
    
    def score_formula(
        self,
        values: np.ndarray,
        labels: Optional[np.ndarray] = None,
        ticker_groups: Optional[np.ndarray] = None,
        formula_name: str = "unnamed",
    ) -> FormulaQualityMetrics:
        """
        Score a formula and decide accept/reject.
        
        PIT Safety:
        - Only uses provided values and labels (assumed to be training data)
        - No future data access
        - If labels=None, only unsupervised checks are used
        
        Args:
            values: Formula output values (1-D array)
            labels: Optional target labels for supervised metrics (PIT-safe)
            ticker_groups: Optional ticker group indices for stability check
            formula_name: Formula identifier for logging
        
        Returns:
            FormulaQualityMetrics with accept/reject decision and reasons
        """
        rejection_reasons = []
        
        # Compute unsupervised metrics
        unsup_metrics = self._compute_unsupervised_metrics(values, ticker_groups)
        
        # Check unsupervised thresholds
        if unsup_metrics["non_nan_coverage"] < self.config.min_coverage:
            rejection_reasons.append(
                f"Low coverage: {unsup_metrics['non_nan_coverage']:.2%} < "
                f"{self.config.min_coverage:.2%}"
            )
        
        if unsup_metrics["variance"] < self.config.min_variance:
            rejection_reasons.append(
                f"Near-zero variance: {unsup_metrics['variance']:.2e} < "
                f"{self.config.min_variance:.2e}"
            )
        
        if unsup_metrics["per_ticker_stability"] > self.config.max_per_ticker_variance:
            rejection_reasons.append(
                f"Unstable per-ticker: var={unsup_metrics['per_ticker_stability']:.2e} > "
                f"{self.config.max_per_ticker_variance:.2e}"
            )
        
        if unsup_metrics["nan_inf_ratio"] > self.config.max_nan_inf_ratio:
            rejection_reasons.append(
                f"Excessive NaN/inf: {unsup_metrics['nan_inf_ratio']:.2%} > "
                f"{self.config.max_nan_inf_ratio:.2%}"
            )
        
        # Compute supervised metrics if labels provided
        sup_metrics = {}
        is_supervised_validated = False
        validation_mode = "unknown"
        
        if labels is not None:
            sup_metrics = self._compute_supervised_metrics(values, labels)
            validation_mode = "supervised"
            
            # Check supervised thresholds
            if sup_metrics["absolute_ic"] < self.config.min_absolute_ic:
                rejection_reasons.append(
                    f"Weak IC: |IC|={sup_metrics['absolute_ic']:.4f} < "
                    f"{self.config.min_absolute_ic:.4f}"
                )
            
            if sup_metrics["dsr_proxy"] < self.config.min_dsr_proxy:
                rejection_reasons.append(
                    f"Negative DSR proxy: {sup_metrics['dsr_proxy']:.3f} < "
                    f"{self.config.min_dsr_proxy:.3f}"
                )
            
            # If supervised checks passed (no supervised-related rejections), mark as validated
            supervised_rejection_reasons = [r for r in rejection_reasons if "IC" in r or "DSR" in r]
            if len(supervised_rejection_reasons) == 0:
                is_supervised_validated = True
        else:
            # No labels provided - mark as unsupervised only
            validation_mode = "unsupervised_only"
            if not self.config.allow_unvalidated:
                rejection_reasons.append(
                    "No supervised validation available (labels=None) and "
                    "allow_unvalidated=False"
                )
        
        # Determine if formula is deployable
        # Only supervised-validated formulas with no rejections are deployable
        is_accepted = len(rejection_reasons) == 0
        is_deployable = is_accepted and is_supervised_validated
        
        # Build metrics object
        metrics = FormulaQualityMetrics(
            non_nan_coverage=unsup_metrics["non_nan_coverage"],
            variance=unsup_metrics["variance"],
            per_ticker_stability=unsup_metrics["per_ticker_stability"],
            nan_inf_ratio=unsup_metrics["nan_inf_ratio"],
            absolute_ic=sup_metrics.get("absolute_ic"),
            dsr_proxy=sup_metrics.get("dsr_proxy"),
            is_supervised_validated=is_supervised_validated,
            is_deployable=is_deployable,
            validation_mode=validation_mode,
            accepted=is_accepted,
            rejection_reasons=rejection_reasons,
        )
        
        # Log result
        if metrics.accepted:
            logger.info(
                "Formula ACCEPTED [%s] mode=%s deployable=%s: coverage=%.2f%% var=%.2e |IC|=%s DSR=%s",
                formula_name,
                metrics.validation_mode,
                metrics.is_deployable,
                metrics.non_nan_coverage * 100,
                metrics.variance,
                f"{metrics.absolute_ic:.4f}" if metrics.absolute_ic else "N/A",
                f"{metrics.dsr_proxy:.3f}" if metrics.dsr_proxy else "N/A",
            )
            # L3 audit requirement: explicit warning for unsupervised-only formulas
            if not metrics.is_deployable:
                logger.warning(
                    "Formula [%s] accepted with UNSUPERVISED checks only - "
                    "NOT PRODUCTION-DEPLOYABLE without supervised validation",
                    formula_name,
                )
        else:
            logger.warning(
                "Formula REJECTED [%s] mode=%s: %s",
                formula_name,
                metrics.validation_mode,
                "; ".join(rejection_reasons),
            )
        
        return metrics
    
    def score_batch(
        self,
        formulas: Dict[str, np.ndarray],
        labels: Optional[np.ndarray] = None,
        ticker_groups: Optional[np.ndarray] = None,
    ) -> Dict[str, FormulaQualityMetrics]:
        """
        Score a batch of formulas.
        
        Args:
            formulas: Dictionary mapping formula names to value arrays
            labels: Optional target labels for supervised metrics
            ticker_groups: Optional ticker group indices for stability check
        
        Returns:
            Dictionary mapping formula names to quality metrics
        """
        results = {}
        for name, values in formulas.items():
            metrics = self.score_formula(
                values=values,
                labels=labels,
                ticker_groups=ticker_groups,
                formula_name=name,
            )
            results[name] = metrics
        
        # Summary log
        accepted = sum(1 for m in results.values() if m.accepted)
        rejected = len(results) - accepted
        deployable = sum(1 for m in results.values() if m.is_deployable)
        unsupervised_only = sum(
            1 for m in results.values() 
            if m.accepted and m.validation_mode == "unsupervised_only"
        )
        
        logger.info(
            "Batch scoring complete: %d formulas, %d accepted (%d deployable, %d unsupervised_only), %d rejected",
            len(results),
            accepted,
            deployable,
            unsupervised_only,
            rejected,
        )
        
        # L3 audit requirement: explicit warning if any unsupervised-only formulas accepted
        if unsupervised_only > 0:
            logger.warning(
                "Batch contains %d UNSUPERVISED-ONLY formulas - "
                "NOT PRODUCTION-DEPLOYABLE without supervised validation",
                unsupervised_only,
            )
        
        return results
