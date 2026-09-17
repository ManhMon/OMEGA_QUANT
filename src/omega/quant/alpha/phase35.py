"""Phase 3.5 Walk-Forward Backtest Engine.

Version: v21.38-Phase35-Stage3
Date: 2026-05-22

Walk-forward backtest for 7 Phase 3.4 microstructure alphas using real VN market data.

COMPLIANCE:
  - PIT Safety: T-1 lag enforcement
  - Vectorization: 100% Pandas/NumPy
  - Error Handling: Graceful degradation
  - Metrics: IC, Sharpe, Max DD per fold
"""
from __future__ import annotations

import logging
import sys
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from omega.quant.ml.gate_validator import validate_research_gate
from omega.quant.ml.ensemble_xgboost import XGBoostAlphaEnsemble
from omega.quant.ml.ensemble_multi import MultiModelAlphaEnsemble

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615
# Research-only opt-in ex-ante regime-conditioned alpha routing.
# Builds deterministic regimes from lagged/PIT-safe market features,
# estimates per-regime IC on train window only, and routes/scales alpha
# signals on test using ex-ante regime labels.  Never uses test returns
# for routing decisions.  Fallback to baseline when evidence insufficient.
# ---------------------------------------------------------------------------
REGIME_ROUTING_GATE_ID = "REGIME_CONDITIONED_ALPHA_ROUTING_20260615"

# ---------------------------------------------------------------------------
# GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615
# Research-only opt-in diversified alpha basket selector.
# Uses train-only IC/ICIR + pairwise correlation / vector cluster to select
# a non-redundant basket of alphas.  Max 1-2 alphas per cluster, correlation
# penalty, fallback safe basket if no candidates pass.  Never uses OOS/test
# metrics for selection decisions.
# ---------------------------------------------------------------------------
DIVERSIFIED_BASKET_GATE_ID = "DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615"

# ---------------------------------------------------------------------------
# GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615
# Research-only opt-in nonredundant alpha family set v1.
# Adds PIT-safe trailing-window alpha candidates from 5 families:
# liquidity shock reversal, range pressure/CLV, volatility compression
# breakout, sector/market-relative residual momentum/reversal, and
# breadth-conditioned reversal.  Default off, no live behavior change.
# ---------------------------------------------------------------------------
NONREDUNDANT_ALPHA_GATE_ID = "NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615"
# GATE: NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615 — positive-evidence subset
NONREDUNDANT_ALPHA_V1_PRUNED_GATE_ID = "NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615"
# GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615 — focused overlay subsets
NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID = "NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615"

# ---------------------------------------------------------------------------
# GATE: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615
# Research-only opt-in automated alpha discovery factory.
# Generates deterministic PIT-safe candidates from expression templates,
# screens on train-only data, applies correlation filtering, produces
# evidence metadata.  Default off, no live/default promotion.
# ---------------------------------------------------------------------------
AUTOMATED_DISCOVERY_GATE_ID = "AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615"

# ---------------------------------------------------------------------------
# GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615
# Research-only opt-in Phase35 OOS wiring for the approved top automated
# alpha bundle.  Injects the pre-approved bundle candidates as additional
# alpha columns during per-fold backtest.  Bundle selection was performed
# on train-only data by AutomatedAlphaDiscoveryFactory; this gate wires
# the frozen bundle into OOS evaluation without re-running discovery.
# Default off, no live/default promotion.
# ---------------------------------------------------------------------------
AUTOMATED_ALPHA_OOS_GATE_ID = "AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615"

# ---------------------------------------------------------------------------
# GATE: AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615
# Research-only opt-in extension: when enabled alongside the auto OOS bundle,
# extends the formulaic winner guard allowlist to include the auto bundle
# alpha names.  This prevents the winner guard from blocking auto bundle
# alphas that have positive train-only IC evidence.
# Default off, no live/default promotion.  Does NOT change the winner guard
# behavior for non-auto alphas.
# ---------------------------------------------------------------------------
AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_GATE_ID = (
    "AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615"
)

# ---------------------------------------------------------------------------
# GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616
# Research-only opt-in PIT-safe stability filter for auto-alpha bundle.
# Uses ONLY train/in-fold pre-OOS evidence to assess IC stability:
#   - IC sign consistency across sub-windows
#   - Rolling IC stability (mean / std ratio)
#   - ICIR threshold gate
#   - IC decay penalty
# Never uses OOS/test labels or current-bar data.  Default off,
# no live/default promotion.  Evidence serialized per fold.
# ---------------------------------------------------------------------------
AUTO_ALPHA_OOS_STABILITY_FILTER_GATE_ID = (
    "AUTO_ALPHA_OOS_STABILITY_FILTER_20260616"
)

# ---------------------------------------------------------------------------
# GATE: STAGE6_3_DRAWDOWN_RE_ENTRY_20260616
# Research-only opt-in stateful drawdown control with cooldown and HWM reset.
# After a stop-out breach, the engine enters a cooldown period (cash-only),
# then re-enters the strategy with an optionally reset high-water mark.
# This prevents permanent capital lockout after a single drawdown event
# while preserving PIT safety (all decisions use only realised test returns).
# ---------------------------------------------------------------------------
DRAWDOWN_RE_ENTRY_GATE_ID = "STAGE6_3_DRAWDOWN_RE_ENTRY_20260616"

# ---------------------------------------------------------------------------
# GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
# Research-only opt-in adaptive drawdown re-entry using HMM bear probability
# and trailing volatility.  When enabled alongside drawdown_re_entry,
# cooldown duration is dynamically adjusted: extended when HMM p_bear is
# high or volatility is elevated, shortened when regime conditions improve.
# This allows smarter re-entry timing based on PIT-safe regime signals.
# ---------------------------------------------------------------------------
DRAWDOWN_ADAPTIVE_RE_ENTRY_GATE_ID = "STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616"

# Approved top-5 automated alpha bundle (frozen from real-IC screening).
# These candidate names correspond to PIT-safe expression templates in
# automated_alpha_discovery._EXPRESSION_TEMPLATES.
AUTO_TOP5_REAL_IC_BUNDLE: Dict[str, List[str]] = {
    "auto_top5_real_ic_20260615": [
        "auto_rsi_14",
        "auto_mr_zscore_20",
        "auto_mom_ret_60",
        "auto_mom_ret_20",
        "auto_vol_std_ratio_10_30",
    ],
}

# ---------------------------------------------------------------------------
# GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614
# Research-only opt-in selector guard for formulaic v3_pruned winners.
# Constrains alpha selection/fallback pool to a pre-specified allowlist of
# strong positive-IC formulaic candidates.  PIT-safe: uses only current-fold
# train/validation IC — no future fold or stat report leakage.
# ---------------------------------------------------------------------------
FORMULAIC_WINNER_GUARD_GATE_ID = "FORMULAIC_WINNER_SELECTION_GUARD_20260614"

FORMULAIC_WINNER_DEFAULT_ALLOWLIST: List[str] = [
    "alpha_fml052_close_zscore_mr_20",
    "alpha_fml012_mean_rev_rank_10",
    "alpha_fml045_liq_turnover_5",
    "alpha_fml067_vol_price_diverge_10",
    "alpha_fml006_vp_corr_10",
]

# ---------------------------------------------------------------------------
# Helper: Robust gate verdict evaluation (P10 truthiness hotfix 2026-06-09)
# ---------------------------------------------------------------------------
def _is_gate_verdict_pass(verdict) -> bool:
    """Check if a gate verdict represents a pass.
    
    Parameters
    ----------
    verdict : any
        Gate verdict value from validate_research_gate() result dict.
        
    Returns
    -------
    bool
        True if verdict is a pass, False otherwise.
        
    Notes
    -----
    Pass conditions:
    - Boolean True
    - String exactly matching "PASS" or "APPROVED" (case-insensitive)
    
    Fail conditions:
    - Boolean False
    - String starting with "FAIL", "REJECT", "NEEDS_FIX" (case-insensitive)
    - None, empty string, or missing value
    - Any other string not explicitly recognized as pass
    
    This prevents truthiness bugs where non-empty fail strings like
    "FAIL: insufficient samples" are incorrectly treated as pass.
    """
    # Boolean True is pass
    if verdict is True:
        return True
    
    # Boolean False, None, or missing is fail
    if verdict is False or verdict is None:
        return False
    
    # String verdict: check for explicit pass/fail markers
    if isinstance(verdict, str):
        verdict_upper = verdict.strip().upper()
        
        # Empty string is fail
        if not verdict_upper:
            return False
        
        # Explicit pass markers
        if verdict_upper in ("PASS", "APPROVED"):
            return True
        
        # Explicit fail markers
        if verdict_upper.startswith(("FAIL", "REJECT", "NEEDS_FIX")):
            return False
        
        # Any other string is treated as fail (conservative)
        return False
    
    # Any other type is treated as fail
    return False

# ---------------------------------------------------------------------------
# Stage 2: reuse sector-cap enforcement from alpha_pipeline (no duplication)
# ---------------------------------------------------------------------------
def _import_apply_sector_caps():
    """Lazy import of _apply_sector_caps from alpha_pipeline.

    Searches for alpha_pipeline.py relative to this file's location so the
    import works regardless of the working directory.
    """
    _scripts_dir = str(Path(__file__).resolve().parents[4] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
    from alpha_pipeline import _apply_sector_caps  # noqa: PLC0415
    return _apply_sector_caps


@dataclass
class FoldMetrics:
    """Metrics for a single walk-forward fold."""
    fold_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    alpha_ics: Dict[str, float] = field(default_factory=dict)
    portfolio_sharpe: float = 0.0
    portfolio_max_dd: float = 0.0
    portfolio_total_return: float = 0.0
    portfolio_pnl_vnd: float = 0.0
    portfolio_ic: float = 0.0
    raw_signal_ic: float = 0.0
    raw_signal_daily_cs_ic: float = 0.0
    n_train_samples: int = 0
    n_test_samples: int = 0
    # Stage 3 ML Gate fields
    gate_results: Dict[str, dict] = field(default_factory=dict)
    gated_alphas: List[str] = field(default_factory=list)
    # P10 Gate Tuning: structured fallback-candidate labeling (Role21 Fix 2026-06-10)
    gate_metadata: Optional[Dict[str, any]] = field(default_factory=lambda: None)
    # GATE: RISK_ADJUSTED_ALPHA_SELECTION_FIX1_20260614 — per-fold evidence
    risk_adjusted_evidence: Optional[Dict[str, any]] = field(default_factory=lambda: None)
    # GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614 — per-fold guard evidence
    portfolio_guard_evidence: Optional[Dict[str, any]] = field(default_factory=lambda: None)
    # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614 — per-fold winner guard evidence
    winner_guard_evidence: Optional[Dict[str, any]] = field(default_factory=lambda: None)
    # GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — per-fold regime routing evidence
    regime_routing_evidence: Optional[Dict[str, any]] = field(default_factory=lambda: None)
    # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615 — per-fold dynamic universe evidence
    dynamic_universe_evidence: Optional[Dict[str, any]] = field(default_factory=lambda: None)
    # GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — per-fold basket evidence
    diversified_basket_evidence: Optional[Dict[str, any]] = field(default_factory=lambda: None)
    # GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615 — per-fold nonredundant alpha evidence
    nonredundant_alpha_evidence: Optional[Dict[str, any]] = field(default_factory=lambda: None)
    # GATE: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615 — per-fold automated discovery evidence
    automated_discovery_evidence: Optional[Dict[str, any]] = field(default_factory=lambda: None)
    # GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616 — per-fold stability filter evidence
    oos_stability_filter_evidence: Optional[Dict[str, any]] = field(default_factory=lambda: None)
    # GATE: BASELINE_RISK_SIZING_OPTIMIZATION_20260616 — per-fold risk/sizing overlay evidence
    risk_sizing_evidence: Optional[Dict[str, any]] = field(default_factory=lambda: None)
    # GATE: STAGE6_3_DRAWDOWN_RE_ENTRY_20260616 — per-fold drawdown re-entry evidence
    drawdown_re_entry_evidence: Optional[Dict[str, any]] = field(default_factory=lambda: None)


@dataclass
class WalkForwardResult:
    """Complete walk-forward backtest results."""
    fold_metrics: List[FoldMetrics] = field(default_factory=list)
    avg_ic_by_alpha: Dict[str, float] = field(default_factory=dict)
    avg_portfolio_sharpe: float = 0.0
    avg_portfolio_max_dd: float = 0.0
    avg_portfolio_ic: float = 0.0
    avg_raw_signal_ic: float = 0.0
    avg_raw_signal_daily_cs_ic: float = 0.0
    avg_portfolio_pnl_vnd: float = 0.0
    total_folds: int = 0
    
    def summary(self) -> str:
        """Generate summary string."""
        lines = [
            f"Walk-Forward Backtest Results ({self.total_folds} folds)",
            "=" * 60,
            f"Average Portfolio IC (post Stage 2): {self.avg_portfolio_ic:.4f}",
            f"Average Raw Signal IC (pre Stage 2):  {self.avg_raw_signal_ic:.4f}",
            f"Average Raw Signal Daily CS IC:       {self.avg_raw_signal_daily_cs_ic:.4f}",
            f"Average Portfolio Sharpe: {self.avg_portfolio_sharpe:.4f}",
            f"Average Max Drawdown: {self.avg_portfolio_max_dd:.2%}",
            "",
            "Alpha IC Summary:",
        ]
        
        for alpha, ic in sorted(self.avg_ic_by_alpha.items(), key=lambda x: abs(x[1]), reverse=True):
            lines.append(f"  {alpha}: {ic:.4f}")
        
        return "\n".join(lines)


class Phase35WalkForwardEngine:
    """Walk-forward backtest engine for Phase 3.4 microstructure alphas."""
    
    def __init__(
        self,
        alpha_module,
        min_ic_threshold: float = 0.02,
        top_n_alphas: int = 5,
        top_n_stocks: int = 15,
        rebalance_freq: int = 7,
        sector_cap_pct: float = 0.40,
        use_xgboost: bool = False,
        enable_multi_model_ensemble: bool = False,
        cost_aware: bool = False,
        cost_per_turnover: float = 0.0025,
        drawdown_control: bool = False,
        drawdown_threshold: float = 0.05,
        strategy: str = "multi_factor",
        initial_capital: float = 1_000_000_000.0,
        enable_evolved: bool = False,
        evolved_blend_weight: float = 0.5,
        multi_horizon_blend: bool = False,
        blend_horizons: Optional[List[int]] = None,
        blend_weight_method: str = "validation_ic",
        p10_gate_mode: str = "strict",
        p10_gate_min_pass: int = 1,
        p10_gate_allow_fallback_candidates: bool = False,
        risk_adjusted_alpha_selection: bool = False,
        risk_adjusted_preset: str = "balanced",
        portfolio_guard_enabled: bool = False,
        portfolio_guard_tolerance: float = 0.005,
        # GATE: RECOVERY_SELECTOR_PHASE35_WIRING_20260614
        research_pool_mode: str = "full",
        # GATE: FORMULAIC_ALPHA_ADAPTER_20260614
        enable_formulaic_alphas: bool = False,
        formulaic_alpha_set: str = "small",
        # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614
        formulaic_winner_guard: bool = False,
        formulaic_winner_allowlist: Optional[List[str]] = None,
        formulaic_winner_min_val_ic: float = 0.0,
        # GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615
        regime_routing_enabled: bool = False,
        regime_routing_min_train_days: int = 60,
        regime_routing_min_ic: float = 0.01,
        regime_routing_fallback: str = "baseline",
        # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615
        dynamic_universe_schedule: Optional[Dict[str, List[str]]] = None,
        # GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615
        diversified_basket_enabled: bool = False,
        basket_max_per_cluster: int = 2,
        basket_corr_threshold: float = 0.70,
        basket_redundancy_penalty: float = 0.3,
        basket_min_ic: float = 0.0,
        # GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615
        enable_nonredundant_alphas: bool = False,
        nonredundant_alpha_set: str = "v1",
        nonredundant_alpha_max_candidates: Optional[int] = None,
        # GATE: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615
        enable_automated_discovery: bool = False,
        automated_discovery_cap: int = 200,
        automated_discovery_corr_threshold: float = 0.85,
        automated_discovery_min_ic: float = 0.01,
        automated_discovery_seed: int = 42,
        # GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615
        enable_automated_oos_bundle: bool = False,
        automated_oos_bundle_name: str = "auto_top5_real_ic_20260615",
        # GATE: AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615
        enable_auto_winner_guard_allowlist: bool = False,
        # GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616
        enable_oos_stability_filter: bool = False,
        stability_min_icir: float = 0.15,
        stability_min_sign_consistency: float = 0.55,
        stability_decay_penalty_factor: float = 1.0,
        stability_min_sub_windows: int = 3,
        # GATE: BASELINE_RISK_SIZING_OPTIMIZATION_20260616
        risk_sizing_overlay_enabled: bool = False,
        risk_sizing_inverse_vol: bool = False,
        risk_sizing_inverse_vol_window: int = 20,
        risk_sizing_inverse_vol_floor: float = 0.3,
        risk_sizing_confidence: bool = False,
        risk_sizing_confidence_window: int = 60,
        risk_sizing_confidence_min_ic: float = 0.01,
        risk_sizing_confidence_max_scale: float = 1.2,
        risk_sizing_confidence_min_scale: float = 0.3,
        # GATE: REGIME_CONDITIONAL_SIZING_20260616
        risk_sizing_regime: bool = False,
        risk_sizing_regime_scale: float = 0.5,
        risk_sizing_regime_ma_window: int = 200,
        risk_sizing_regime_vol_window: int = 20,
        risk_sizing_regime_vol_median_window: int = 60,
        # GATE: REGIME_CONDITIONAL_SIZING_20260616 — Hướng 3 HMM + auto-optimize
        risk_sizing_regime_window: int = 200,
        risk_sizing_regime_mode: str = "heuristic",
        risk_sizing_regime_auto_optimize: bool = False,
        # GATE: REGIME_CONDITIONAL_SIZING_20260616 — HMM stride refitting
        risk_sizing_regime_refit_stride: int = 5,
        # GATE: STAGE6_3_DRAWDOWN_RE_ENTRY_20260616
        drawdown_re_entry_enabled: bool = False,
        drawdown_cooldown_days: int = 5,
        drawdown_hwm_reset: bool = True,
        # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
        drawdown_adaptive_re_entry: bool = False,
        drawdown_adaptive_bear_threshold: float = 0.5,
        drawdown_adaptive_vol_window: int = 20,
        drawdown_adaptive_vol_multiplier: float = 1.5,
        drawdown_adaptive_max_cooldown: int = 20,
    ):
        """Initialize walk-forward engine.
        
        Parameters
        ----------
        alpha_module : module
            Module containing compute_phase34_microstructure_alphas function
        min_ic_threshold : float
            Minimum IC threshold for alpha selection
        top_n_alphas : int
            Number of top alphas to use in portfolio
        top_n_stocks : int
            Stage 2 diversification: number of stocks in portfolio (default 15)
        rebalance_freq : int
            Stage 2 diversification: rebalance every N days (default 7)
        sector_cap_pct : float
            Stage 2 diversification: max sector weight fraction (default 0.40)
        use_xgboost : bool
            Stage 4: if True, replace IC-weighted signal with XGBoostAlphaEnsemble
            predictions. Baseline raw-alpha path is used when False (default).
        cost_aware : bool
            Stage 6.2: if True, penalise high-turnover alphas in selection
        cost_per_turnover : float
            Stage 6.2: cost penalty multiplier per unit of turnover (default 0.0025)
        drawdown_control : bool
            Stage 6.3: if True, stop out to cash if max drawdown threshold is breached
        drawdown_threshold : float
            Stage 6.3: drawdown threshold to trigger stop-out (default 0.05)
        strategy : str
            Trading strategy (multi_factor, momentum, mean_reversion)
        initial_capital : float
            Initial capital in VND
        enable_evolved : bool
            If True, run inline GP evolution per fold and blend evolved signal
        evolved_blend_weight : float
            Weight of evolved signal in blend (0-1), remainder is hand-crafted
        multi_horizon_blend : bool
            P10: If True, blend signals from multiple return horizons (T+1, T+3, T+5)
        blend_horizons : list of int, optional
            P10: Horizons to blend (default [1, 3, 5]). Each horizon uses separate
            return_col (fwd_ret_h), embargo, and train/gate/model path.
        blend_weight_method : str
            P10: Method for computing blend weights (default 'validation_ic').
            Options: 'validation_ic', 'train_ic'
        p10_gate_mode : str
            P10 Research Gate tuning: gate policy mode (default 'strict').
            Valid values: 'strict' (current behavior), 'relaxed' (allow fallback candidates).
        p10_gate_min_pass : int
            P10 Research Gate tuning: minimum gate passes required for horizon eligibility
            in relaxed mode (default 1). Ignored in strict mode.
        p10_gate_allow_fallback_candidates : bool
            P10 Research Gate tuning: if True in relaxed mode, allow horizons with non-empty
            top_alphas to proceed even if robust gate pass count < min_pass (default False).
            Quality guard at blend stage still rejects non-positive final-objective IC.
        risk_adjusted_alpha_selection : bool
            GATE RISK_ADJUSTED_ALPHA_SELECTION_20260614: if True, use composite
            risk-adjusted scoring for alpha selection instead of simple IC-based
            selection. Opt-in, default disabled (False). Uses only train/validation/
            embargoed data — no test future. Paper-trading-only boundary preserved.
        risk_adjusted_preset : str
            GATE RISK_ADJUSTED_ALPHA_TUNING_20260614: named weight preset for
            risk-adjusted composite scoring.  Choices: 'balanced' (default),
            'alpha_recovery', 'drawdown_guarded', 'ic_first_guarded'.  Ignored when
            risk_adjusted_alpha_selection is False.  Validated at init; unknown
            preset raises ValueError.
        portfolio_guard_enabled : bool
            GATE RISK_ADJUSTED_PORTFOLIO_GUARD_20260614: if True, evaluate
            portfolio-level validation guard after risk-adjusted alpha selection.
            Accepts risk-adjusted basket only if selected basket validation IC > 0
            and does not materially underperform baseline basket.  Falls back to
            baseline alpha basket on guard failure.  Opt-in, default disabled.
            Requires risk_adjusted_alpha_selection=True to be meaningful.
        portfolio_guard_tolerance : float
            GATE RISK_ADJUSTED_PORTFOLIO_GUARD_20260614: maximum allowed IC
            underperformance vs baseline (absolute).  Default 0.005.
        research_pool_mode : str
            GATE RECOVERY_SELECTOR_PHASE35_WIRING_20260614: research-only
            recovery pool selector mode.  One of 'full' (default, no change),
            'recovery_only' (exclude CONFIRMED_RETIRE), 'recoverable_only'
            (keep only RECOVERABLE).  Default 'full' — no live behavior change.
        enable_formulaic_alphas : bool
            GATE FORMULAIC_ALPHA_ADAPTER_20260614: if True, compute and
            include Kakushadze-inspired formulaic alpha columns.  Research-only,
            opt-in, default disabled (False).  No live/default behavior change.
        formulaic_alpha_set : str
            GATE FORMULAIC_ALPHA_ADAPTER_20260614: which formulaic alpha set
            to compute (default 'small' = 5 candidates).  Ignored when
            enable_formulaic_alphas is False.
        formulaic_winner_guard : bool
            GATE FORMULAIC_WINNER_SELECTION_GUARD_20260614: if True, constrain
            alpha selection and fallback candidate pool to the formulaic
            winner allowlist (or weight/rank by OOS-safe validation IC/ICIR).
            Prevents negative legacy alphas from entering fallback when guard
            is enabled.  PIT-safe: uses only current fold train/validation
            data.  Research-only, opt-in, default disabled (False).  No
            live/default behavior change when disabled.
        formulaic_winner_allowlist : list of str, optional
            GATE FORMULAIC_WINNER_SELECTION_GUARD_20260614: explicit allowlist
            of alpha names eligible for selection when winner guard is enabled.
            If None, uses FORMULAIC_WINNER_DEFAULT_ALLOWLIST.  Ignored when
            formulaic_winner_guard is False.
        formulaic_winner_min_val_ic : float
            GATE FORMULAIC_WINNER_SELECTION_GUARD_20260614: minimum validation
            IC threshold for allowlist candidates to remain eligible.  Default
            0.0 (any positive or zero IC passes).  Ignored when
            formulaic_winner_guard is False.
        enable_automated_discovery : bool
            GATE AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615: if True, enable
            automated alpha discovery factory that generates and screens
            PIT-safe candidates from expression templates.  Research-only,
            opt-in, default disabled (False).  No live/default behavior
            change when disabled.
        automated_discovery_cap : int
            GATE AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615: maximum number
            of candidates to generate (default 200).
        automated_discovery_corr_threshold : float
            GATE AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615: correlation
            threshold for filtering redundant candidates (default 0.85).
        automated_discovery_min_ic : float
            GATE AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615: minimum
            absolute IC for candidate screening (default 0.01).
        automated_discovery_seed : int
            GATE AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615: random seed
            for deterministic candidate generation (default 42).
        enable_automated_oos_bundle : bool
            GATE AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615: if True,
            inject the pre-approved automated alpha bundle as additional
            alpha columns during per-fold backtest.  The bundle was frozen
            from train-only IC screening by AutomatedAlphaDiscoveryFactory.
            Research-only, opt-in, default disabled (False).  No
            live/default behavior change when disabled.
        automated_oos_bundle_name : str
            GATE AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615: name of
            the approved bundle to inject (default
            'auto_top5_real_ic_20260615').  Must exist in
            AUTO_TOP5_REAL_IC_BUNDLE.  Ignored when
            enable_automated_oos_bundle is False.
        enable_auto_winner_guard_allowlist : bool
            GATE AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615:
            if True, extends the formulaic winner guard allowlist to
            include the auto bundle alpha names (auto_rsi_14, etc.)
            when both formulaic_winner_guard and
            enable_automated_oos_bundle are also True.  Prevents the
            winner guard from blocking auto bundle alphas that have
            positive train-only IC evidence.  Research-only, opt-in,
            default disabled (False).  No live/default behavior change.
        """
        self.alpha_module = alpha_module
        self.min_ic_threshold = min_ic_threshold
        self.top_n_alphas = top_n_alphas
        self.top_n_stocks = top_n_stocks
        self.rebalance_freq = rebalance_freq
        self.sector_cap_pct = sector_cap_pct
        self.use_xgboost = use_xgboost
        self.enable_multi_model_ensemble = enable_multi_model_ensemble
        self.cost_aware = cost_aware
        self.cost_per_turnover = cost_per_turnover
        self.drawdown_control = drawdown_control
        self.drawdown_threshold = drawdown_threshold
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.enable_evolved = enable_evolved
        # Validate and clamp blend weight to [0, 1]
        if not 0 <= evolved_blend_weight <= 1:
            raise ValueError(f"evolved_blend_weight must be in [0, 1], got {evolved_blend_weight}")
        self.evolved_blend_weight = evolved_blend_weight
        
        # P10: Multi-horizon blending parameters
        self.multi_horizon_blend = multi_horizon_blend
        self.blend_horizons = blend_horizons if blend_horizons is not None else [1, 3, 5]
        self.blend_weight_method = blend_weight_method
        
        # P10: Research Gate tuning parameters (v2: opt-in relaxed gate)
        # Validate p10_gate_mode
        valid_gate_modes = ["strict", "relaxed"]
        if p10_gate_mode not in valid_gate_modes:
            raise ValueError(
                f"p10_gate_mode must be one of {valid_gate_modes}, got '{p10_gate_mode}'"
            )
        self.p10_gate_mode = p10_gate_mode
        
        # Validate p10_gate_min_pass
        if not isinstance(p10_gate_min_pass, int) or p10_gate_min_pass < 0:
            raise ValueError(
                f"p10_gate_min_pass must be a non-negative integer, got {p10_gate_min_pass}"
            )
        self.p10_gate_min_pass = p10_gate_min_pass
        
        # Store p10_gate_allow_fallback_candidates
        if not isinstance(p10_gate_allow_fallback_candidates, bool):
            raise ValueError(
                f"p10_gate_allow_fallback_candidates must be a boolean, got {p10_gate_allow_fallback_candidates}"
            )
        self.p10_gate_allow_fallback_candidates = p10_gate_allow_fallback_candidates
        
        # GATE: RISK_ADJUSTED_ALPHA_SELECTION_20260614
        if not isinstance(risk_adjusted_alpha_selection, bool):
            raise ValueError(
                f"risk_adjusted_alpha_selection must be a boolean, got {risk_adjusted_alpha_selection}"
            )
        self.risk_adjusted_alpha_selection = risk_adjusted_alpha_selection

        # GATE: RISK_ADJUSTED_ALPHA_TUNING_20260614 — preset validation
        # Validate early so bad preset names fail at construction, not mid-run.
        from omega.quant.walk_forward.risk_adjusted_alpha_score import (
            PRESETS as _RA_PRESETS,
            get_preset_weights as _ra_get_preset_weights,
        )
        if risk_adjusted_preset not in _RA_PRESETS:
            _valid = ", ".join(sorted(_RA_PRESETS.keys()))
            raise ValueError(
                f"risk_adjusted_preset must be one of [{_valid}], "
                f"got '{risk_adjusted_preset}'"
            )
        self.risk_adjusted_preset = risk_adjusted_preset

        # GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614
        if not isinstance(portfolio_guard_enabled, bool):
            raise ValueError(
                f"portfolio_guard_enabled must be a boolean, got {portfolio_guard_enabled}"
            )
        self.portfolio_guard_enabled = portfolio_guard_enabled
        self.portfolio_guard_tolerance = float(portfolio_guard_tolerance)

        # GATE: RECOVERY_SELECTOR_PHASE35_WIRING_20260614 — research pool mode
        from omega.quant.walk_forward.risk_adjusted_alpha_score import (
            VALID_RESEARCH_POOL_MODES as _VALID_POOL_MODES,
        )
        if research_pool_mode not in _VALID_POOL_MODES:
            _valid = ", ".join(_VALID_POOL_MODES)
            raise ValueError(
                f"research_pool_mode must be one of [{_valid}], "
                f"got '{research_pool_mode}'"
            )
        self.research_pool_mode = research_pool_mode

        # GATE: FORMULAIC_ALPHA_ADAPTER_20260614 — formulaic alpha adapter
        if not isinstance(enable_formulaic_alphas, bool):
            raise ValueError(
                f"enable_formulaic_alphas must be a boolean, "
                f"got {enable_formulaic_alphas}"
            )
        self.enable_formulaic_alphas = enable_formulaic_alphas
        self.formulaic_alpha_set = formulaic_alpha_set

        # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614 — winner guard config
        if not isinstance(formulaic_winner_guard, bool):
            raise ValueError(
                f"formulaic_winner_guard must be a boolean, "
                f"got {formulaic_winner_guard}"
            )
        self.formulaic_winner_guard = formulaic_winner_guard
        self.formulaic_winner_allowlist = (
            list(formulaic_winner_allowlist)
            if formulaic_winner_allowlist is not None
            else list(FORMULAIC_WINNER_DEFAULT_ALLOWLIST)
        )
        self.formulaic_winner_min_val_ic = float(formulaic_winner_min_val_ic)

        # GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615 — regime routing config
        if not isinstance(regime_routing_enabled, bool):
            raise ValueError(
                f"regime_routing_enabled must be a boolean, "
                f"got {regime_routing_enabled}"
            )
        self.regime_routing_enabled = regime_routing_enabled
        if not isinstance(regime_routing_min_train_days, int) or regime_routing_min_train_days < 1:
            raise ValueError(
                f"regime_routing_min_train_days must be a positive integer, "
                f"got {regime_routing_min_train_days}"
            )
        self.regime_routing_min_train_days = regime_routing_min_train_days
        self.regime_routing_min_ic = float(regime_routing_min_ic)
        _valid_fallbacks = ("baseline", "disabled")
        if regime_routing_fallback not in _valid_fallbacks:
            raise ValueError(
                f"regime_routing_fallback must be one of {_valid_fallbacks}, "
                f"got '{regime_routing_fallback}'"
            )
        self.regime_routing_fallback = regime_routing_fallback

        # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615 — per-rebalance universe
        self.dynamic_universe_schedule = dynamic_universe_schedule

        # GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — diversified basket config
        if not isinstance(diversified_basket_enabled, bool):
            raise ValueError(
                f"diversified_basket_enabled must be a boolean, "
                f"got {diversified_basket_enabled}"
            )
        self.diversified_basket_enabled = diversified_basket_enabled
        if not isinstance(basket_max_per_cluster, int) or basket_max_per_cluster < 1:
            raise ValueError(
                f"basket_max_per_cluster must be a positive integer, "
                f"got {basket_max_per_cluster}"
            )
        self.basket_max_per_cluster = basket_max_per_cluster
        if not 0.0 <= basket_corr_threshold <= 1.0:
            raise ValueError(
                f"basket_corr_threshold must be in [0, 1], "
                f"got {basket_corr_threshold}"
            )
        self.basket_corr_threshold = basket_corr_threshold
        if not 0.0 <= basket_redundancy_penalty <= 1.0:
            raise ValueError(
                f"basket_redundancy_penalty must be in [0, 1], "
                f"got {basket_redundancy_penalty}"
            )
        self.basket_redundancy_penalty = basket_redundancy_penalty
        self.basket_min_ic = float(basket_min_ic)

        # GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615 — nonredundant alpha config
        if not isinstance(enable_nonredundant_alphas, bool):
            raise ValueError(
                f"enable_nonredundant_alphas must be a boolean, "
                f"got {enable_nonredundant_alphas}"
            )
        self.enable_nonredundant_alphas = enable_nonredundant_alphas
        self.nonredundant_alpha_set = nonredundant_alpha_set
        if nonredundant_alpha_max_candidates is not None:
            if not isinstance(nonredundant_alpha_max_candidates, int) or nonredundant_alpha_max_candidates < 1:
                raise ValueError(
                    f"nonredundant_alpha_max_candidates must be a positive integer or None, "
                    f"got {nonredundant_alpha_max_candidates}"
                )
        self.nonredundant_alpha_max_candidates = nonredundant_alpha_max_candidates

        # GATE: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615 — automated discovery config
        if not isinstance(enable_automated_discovery, bool):
            raise ValueError(
                f"enable_automated_discovery must be a boolean, "
                f"got {enable_automated_discovery}"
            )
        self.enable_automated_discovery = enable_automated_discovery
        if not isinstance(automated_discovery_cap, int) or automated_discovery_cap < 1:
            raise ValueError(
                f"automated_discovery_cap must be a positive integer, "
                f"got {automated_discovery_cap}"
            )
        self.automated_discovery_cap = automated_discovery_cap
        if not 0.0 <= automated_discovery_corr_threshold <= 1.0:
            raise ValueError(
                f"automated_discovery_corr_threshold must be in [0, 1], "
                f"got {automated_discovery_corr_threshold}"
            )
        self.automated_discovery_corr_threshold = automated_discovery_corr_threshold
        self.automated_discovery_min_ic = float(automated_discovery_min_ic)
        if not isinstance(automated_discovery_seed, int):
            raise ValueError(
                f"automated_discovery_seed must be an integer, "
                f"got {automated_discovery_seed}"
            )
        self.automated_discovery_seed = automated_discovery_seed

        # GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615 — OOS bundle config
        if not isinstance(enable_automated_oos_bundle, bool):
            raise ValueError(
                f"enable_automated_oos_bundle must be a boolean, "
                f"got {enable_automated_oos_bundle}"
            )
        self.enable_automated_oos_bundle = enable_automated_oos_bundle
        if automated_oos_bundle_name not in AUTO_TOP5_REAL_IC_BUNDLE:
            valid_names = ", ".join(AUTO_TOP5_REAL_IC_BUNDLE.keys())
            raise ValueError(
                f"automated_oos_bundle_name must be one of [{valid_names}], "
                f"got '{automated_oos_bundle_name}'"
            )
        self.automated_oos_bundle_name = automated_oos_bundle_name
        self.automated_oos_bundle_alphas = list(
            AUTO_TOP5_REAL_IC_BUNDLE[automated_oos_bundle_name]
        )

        # GATE: AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615
        # Opt-in extension of formulaic winner guard allowlist to include
        # auto bundle alpha names.  Default off, no behavior change.
        if not isinstance(enable_auto_winner_guard_allowlist, bool):
            raise ValueError(
                f"enable_auto_winner_guard_allowlist must be a boolean, "
                f"got {enable_auto_winner_guard_allowlist}"
            )
        self.enable_auto_winner_guard_allowlist = (
            enable_auto_winner_guard_allowlist
        )

        # GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616 — stability filter config
        if not isinstance(enable_oos_stability_filter, bool):
            raise ValueError(
                f"enable_oos_stability_filter must be a boolean, "
                f"got {enable_oos_stability_filter}"
            )
        self.enable_oos_stability_filter = enable_oos_stability_filter
        self.stability_min_icir = float(stability_min_icir)
        if not 0.0 <= stability_min_sign_consistency <= 1.0:
            raise ValueError(
                f"stability_min_sign_consistency must be in [0, 1], "
                f"got {stability_min_sign_consistency}"
            )
        self.stability_min_sign_consistency = float(stability_min_sign_consistency)
        if stability_decay_penalty_factor < 0.0:
            raise ValueError(
                f"stability_decay_penalty_factor must be >= 0, "
                f"got {stability_decay_penalty_factor}"
            )
        self.stability_decay_penalty_factor = float(stability_decay_penalty_factor)
        if not isinstance(stability_min_sub_windows, int) or stability_min_sub_windows < 2:
            raise ValueError(
                f"stability_min_sub_windows must be an integer >= 2, "
                f"got {stability_min_sub_windows}"
            )
        self.stability_min_sub_windows = stability_min_sub_windows

        # GATE: BASELINE_RISK_SIZING_OPTIMIZATION_20260616 — risk/sizing overlay config
        if not isinstance(risk_sizing_overlay_enabled, bool):
            raise ValueError(
                f"risk_sizing_overlay_enabled must be a boolean, "
                f"got {risk_sizing_overlay_enabled}"
            )
        self.risk_sizing_overlay_enabled = risk_sizing_overlay_enabled
        self.risk_sizing_inverse_vol = bool(risk_sizing_inverse_vol)
        if not isinstance(risk_sizing_inverse_vol_window, int) or risk_sizing_inverse_vol_window < 5:
            raise ValueError(
                f"risk_sizing_inverse_vol_window must be an integer >= 5, "
                f"got {risk_sizing_inverse_vol_window}"
            )
        self.risk_sizing_inverse_vol_window = risk_sizing_inverse_vol_window
        if not 0.0 <= risk_sizing_inverse_vol_floor <= 1.0:
            raise ValueError(
                f"risk_sizing_inverse_vol_floor must be in [0, 1], "
                f"got {risk_sizing_inverse_vol_floor}"
            )
        self.risk_sizing_inverse_vol_floor = float(risk_sizing_inverse_vol_floor)
        self.risk_sizing_confidence = bool(risk_sizing_confidence)
        if not isinstance(risk_sizing_confidence_window, int) or risk_sizing_confidence_window < 10:
            raise ValueError(
                f"risk_sizing_confidence_window must be an integer >= 10, "
                f"got {risk_sizing_confidence_window}"
            )
        self.risk_sizing_confidence_window = risk_sizing_confidence_window
        self.risk_sizing_confidence_min_ic = float(risk_sizing_confidence_min_ic)
        if risk_sizing_confidence_max_scale < 0.0:
            raise ValueError(
                f"risk_sizing_confidence_max_scale must be >= 0, "
                f"got {risk_sizing_confidence_max_scale}"
            )
        self.risk_sizing_confidence_max_scale = float(risk_sizing_confidence_max_scale)
        if not 0.0 <= risk_sizing_confidence_min_scale <= 1.0:
            raise ValueError(
                f"risk_sizing_confidence_min_scale must be in [0, 1], "
                f"got {risk_sizing_confidence_min_scale}"
            )
        self.risk_sizing_confidence_min_scale = float(risk_sizing_confidence_min_scale)

        # GATE: REGIME_CONDITIONAL_SIZING_20260616 — regime sizing config
        if not isinstance(risk_sizing_regime, bool):
            raise ValueError(
                f"risk_sizing_regime must be a boolean, "
                f"got {risk_sizing_regime}"
            )
        self.risk_sizing_regime = bool(risk_sizing_regime)
        if not 0.0 < risk_sizing_regime_scale <= 1.0:
            raise ValueError(
                f"risk_sizing_regime_scale must be in (0, 1], "
                f"got {risk_sizing_regime_scale}"
            )
        self.risk_sizing_regime_scale = float(risk_sizing_regime_scale)
        if not isinstance(risk_sizing_regime_ma_window, int) or risk_sizing_regime_ma_window < 10:
            raise ValueError(
                f"risk_sizing_regime_ma_window must be an integer >= 10, "
                f"got {risk_sizing_regime_ma_window}"
            )
        self.risk_sizing_regime_ma_window = risk_sizing_regime_ma_window
        if not isinstance(risk_sizing_regime_vol_window, int) or risk_sizing_regime_vol_window < 5:
            raise ValueError(
                f"risk_sizing_regime_vol_window must be an integer >= 5, "
                f"got {risk_sizing_regime_vol_window}"
            )
        self.risk_sizing_regime_vol_window = risk_sizing_regime_vol_window
        if not isinstance(risk_sizing_regime_vol_median_window, int) or risk_sizing_regime_vol_median_window < 10:
            raise ValueError(
                f"risk_sizing_regime_vol_median_window must be an integer >= 10, "
                f"got {risk_sizing_regime_vol_median_window}"
            )
        self.risk_sizing_regime_vol_median_window = risk_sizing_regime_vol_median_window

        # GATE: REGIME_CONDITIONAL_SIZING_20260616 — HMM + auto-optimize params
        if not isinstance(risk_sizing_regime_window, int) or risk_sizing_regime_window < 20:
            raise ValueError(
                f"risk_sizing_regime_window must be an integer >= 20, "
                f"got {risk_sizing_regime_window}"
            )
        self.risk_sizing_regime_window = risk_sizing_regime_window
        _valid_modes = ("heuristic", "hmm")
        if risk_sizing_regime_mode not in _valid_modes:
            raise ValueError(
                f"risk_sizing_regime_mode must be one of {_valid_modes}, "
                f"got '{risk_sizing_regime_mode}'"
            )
        self.risk_sizing_regime_mode = risk_sizing_regime_mode
        if not isinstance(risk_sizing_regime_auto_optimize, bool):
            raise ValueError(
                f"risk_sizing_regime_auto_optimize must be a boolean, "
                f"got {risk_sizing_regime_auto_optimize}"
            )
        self.risk_sizing_regime_auto_optimize = risk_sizing_regime_auto_optimize

        # GATE: REGIME_CONDITIONAL_SIZING_20260616 — HMM stride refitting
        if not isinstance(risk_sizing_regime_refit_stride, int) or risk_sizing_regime_refit_stride < 1:
            raise ValueError(
                f"risk_sizing_regime_refit_stride must be a positive integer >= 1, "
                f"got {risk_sizing_regime_refit_stride}"
            )
        self.risk_sizing_regime_refit_stride = risk_sizing_regime_refit_stride

        # GATE: STAGE6_3_DRAWDOWN_RE_ENTRY_20260616 — drawdown re-entry config
        if not isinstance(drawdown_re_entry_enabled, bool):
            raise ValueError(
                f"drawdown_re_entry_enabled must be a boolean, "
                f"got {drawdown_re_entry_enabled}"
            )
        self.drawdown_re_entry_enabled = drawdown_re_entry_enabled
        if not isinstance(drawdown_cooldown_days, int) or drawdown_cooldown_days < 0:
            raise ValueError(
                f"drawdown_cooldown_days must be a non-negative integer, "
                f"got {drawdown_cooldown_days}"
            )
        self.drawdown_cooldown_days = drawdown_cooldown_days
        if not isinstance(drawdown_hwm_reset, bool):
            raise ValueError(
                f"drawdown_hwm_reset must be a boolean, "
                f"got {drawdown_hwm_reset}"
            )
        self.drawdown_hwm_reset = drawdown_hwm_reset

        # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616 — adaptive re-entry config
        if not isinstance(drawdown_adaptive_re_entry, bool):
            raise ValueError(
                f"drawdown_adaptive_re_entry must be a boolean, "
                f"got {drawdown_adaptive_re_entry}"
            )
        self.drawdown_adaptive_re_entry = drawdown_adaptive_re_entry
        if not 0.0 <= drawdown_adaptive_bear_threshold <= 1.0:
            raise ValueError(
                f"drawdown_adaptive_bear_threshold must be in [0, 1], "
                f"got {drawdown_adaptive_bear_threshold}"
            )
        self.drawdown_adaptive_bear_threshold = float(drawdown_adaptive_bear_threshold)
        if not isinstance(drawdown_adaptive_vol_window, int) or drawdown_adaptive_vol_window < 5:
            raise ValueError(
                f"drawdown_adaptive_vol_window must be an integer >= 5, "
                f"got {drawdown_adaptive_vol_window}"
            )
        self.drawdown_adaptive_vol_window = drawdown_adaptive_vol_window
        if drawdown_adaptive_vol_multiplier < 1.0:
            raise ValueError(
                f"drawdown_adaptive_vol_multiplier must be >= 1.0, "
                f"got {drawdown_adaptive_vol_multiplier}"
            )
        self.drawdown_adaptive_vol_multiplier = float(drawdown_adaptive_vol_multiplier)
        if not isinstance(drawdown_adaptive_max_cooldown, int) or drawdown_adaptive_max_cooldown < 0:
            raise ValueError(
                f"drawdown_adaptive_max_cooldown must be a non-negative integer, "
                f"got {drawdown_adaptive_max_cooldown}"
            )
        self.drawdown_adaptive_max_cooldown = drawdown_adaptive_max_cooldown

        # Store reference alpha columns for feature whitelist
        self.alpha_cols_ref = getattr(alpha_module, 'PHASE34_ALPHA_COLUMNS', [])
    
    def compute_alphas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute Phase 3.4 alphas on data.

        If enable_formulaic_alphas is True, also computes and appends
        formulaic alpha columns (GATE: FORMULAIC_ALPHA_ADAPTER_20260614).
        
        Parameters
        ----------
        df : pd.DataFrame
            OHLCV data with 'ticker', 'date', 'open', 'high', 'low', 'close', 'volume'
        
        Returns
        -------
        pd.DataFrame
            Data with alpha columns added
        """
        result = self.alpha_module.compute_phase34_microstructure_alphas(
            df,
            symbol_col='ticker',
            date_col='date',
            open_col='open',
            high_col='high',
            low_col='low',
            close_col='close',
            volume_col='volume',
        )

        # GATE: FORMULAIC_ALPHA_ADAPTER_20260614 — append formulaic alphas
        if self.enable_formulaic_alphas:
            from omega.quant.alpha.formulaic_alphas import compute_formulaic_alphas
            result = compute_formulaic_alphas(
                result,
                set_name=self.formulaic_alpha_set,
                symbol_col='ticker',
                date_col='date',
                open_col='open',
                high_col='high',
                low_col='low',
                close_col='close',
                volume_col='volume',
            )

        # GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615 — append nonredundant alphas
        if self.enable_nonredundant_alphas:
            from omega.quant.alpha.nonredundant_alphas import (
                compute_nonredundant_alphas,
                load_sector_map,
            )
            # Try to load sector map for sector-relative alphas
            sector_map = load_sector_map()
            self._nr_sector_map_loaded = sector_map is not None and len(sector_map) > 0
            self._nr_sector_map_fallback_reason = (
                None if self._nr_sector_map_loaded
                else "sector_mapping_level2.csv not found or empty; using market-relative fallback"
            )
            result = compute_nonredundant_alphas(
                result,
                set_name=self.nonredundant_alpha_set,
                max_candidates=self.nonredundant_alpha_max_candidates,
                symbol_col='ticker',
                date_col='date',
                open_col='open',
                high_col='high',
                low_col='low',
                close_col='close',
                volume_col='volume',
                sector_map=sector_map,
            )

        # GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615 — inject
        # pre-approved automated alpha bundle signals (PIT-safe, T-1).
        if self.enable_automated_oos_bundle:
            from omega.quant.alpha.automated_alpha_discovery import (
                AutomatedAlphaDiscoveryFactory,
                AlphaCandidate,
                _EXPRESSION_TEMPLATES,
            )
            # Build candidate objects from the approved bundle names
            bundle_candidates = []
            template_map = {name: expr for name, expr in _EXPRESSION_TEMPLATES}
            for alpha_name in self.automated_oos_bundle_alphas:
                # Strip 'auto_' prefix to look up the template
                template_key = alpha_name.replace("auto_", "", 1)
                expr_str = template_map.get(template_key, "")
                if expr_str:
                    bundle_candidates.append(AlphaCandidate(
                        name=alpha_name,
                        expression_id=alpha_name,
                        metadata={"expression": expr_str, "template": template_key},
                    ))
                else:
                    logger.warning(
                        f"[AutoOOS] Template not found for '{template_key}', "
                        f"skipping '{alpha_name}'"
                    )
            if bundle_candidates:
                factory = AutomatedAlphaDiscoveryFactory(enabled=True)
                result = factory.compute_candidate_signals(
                    result, bundle_candidates
                )
                logger.info(
                    f"[AutoOOS] Injected {len(bundle_candidates)} bundle "
                    f"signals: {[c.name for c in bundle_candidates]}"
                )

        return result
    
    def compute_ic(
        self,
        alpha_values: pd.Series,
        returns: pd.Series,
    ) -> float:
        """Compute Spearman IC between alpha and returns.
        
        Parameters
        ----------
        alpha_values : pd.Series
            Alpha signal values
        returns : pd.Series
            Forward returns
        
        Returns
        -------
        float
            Spearman IC
        """
        # Remove NaN pairs
        mask = ~(alpha_values.isna() | returns.isna())
        if mask.sum() < 10:
            return 0.0
        
        alpha_clean = alpha_values[mask].values
        returns_clean = returns[mask].values
        
        try:
            ic, _ = spearmanr(alpha_clean, returns_clean)
            return ic if not np.isnan(ic) else 0.0
        except Exception as e:
            logger.warning(f"IC computation failed: {e}")
            return 0.0

    def compute_daily_cs_ic(
        self,
        df: pd.DataFrame,
        signal_col: str,
        return_col: str,
        min_cross_section: int = 5,
    ) -> float:
        """Compute daily cross-sectional Spearman IC, then average across dates.

        For each unique date in df, computes Spearman IC between signal_col and
        return_col across tickers. Returns the mean of per-date ICs.

        Parameters
        ----------
        df : pd.DataFrame
            Must have 'date', signal_col, return_col columns.
        signal_col : str
            Column name for the signal (alpha or portfolio weight).
        return_col : str
            Column name for forward returns.
        min_cross_section : int
            Minimum number of non-NaN pairs per date to compute IC (default 5).

        Returns
        -------
        float
            Mean daily cross-sectional Spearman IC.
        """
        if signal_col not in df.columns or return_col not in df.columns:
            return 0.0

        def _cs_ic(group: pd.DataFrame) -> float:
            mask = ~(group[signal_col].isna() | group[return_col].isna())
            if mask.sum() < min_cross_section:
                return np.nan
            try:
                ic, _ = spearmanr(
                    group.loc[mask, signal_col].values,
                    group.loc[mask, return_col].values,
                )
                return ic if not np.isnan(ic) else np.nan
            except Exception:
                return np.nan

        daily_ics = df.groupby('date').apply(_cs_ic, include_groups=False)
        valid = daily_ics.dropna()
        if valid.empty:
            return 0.0
        return float(valid.mean())

    def _evolve_inline_signal(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        return_col: str,
    ) -> Tuple[Optional[np.ndarray], float]:
        """Run inline GP evolution on train_df, execute best on test_df.

        PIT-safe: evolves only on train_actual, executes on test_df.
        Returns (evolved_signal_array, train_ic) or (None, 0.0) on failure.
        train_ic is used by caller for adaptive blend weighting.
        """
        try:
            from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig
        except ImportError:
            logger.warning("Cannot import GeneticEngine, skipping evolved signal")
            return None, 0.0

        # Extract features from train_df (OHLCV + any alpha/feature columns)
        base_cols = ['open', 'high', 'low', 'close', 'volume']
        # Add any additional numeric columns available (alphas, fwd returns, etc.)
        alpha_cols = [c for c in self.alpha_cols_ref if c in train_df.columns]
        
        # Explicitly exclude return_col and any fwd_ret_* columns (prevent look-ahead leak)
        exclude_patterns = [return_col] + [c for c in train_df.columns if c.startswith('fwd_ret_')]
        available_cols = [c for c in base_cols + alpha_cols 
                         if c in train_df.columns and c not in exclude_patterns]
        
        if len(available_cols) < 5:
            logger.warning(f"Insufficient features ({len(available_cols)}), skipping evolution")
            return None, 0.0

        # PIT Safety: T-1 lag raw OHLCV per ticker before GP sees them
        # Alpha columns are already T-1 lagged by compute_alphas(), but raw OHLCV are not.
        lagged_train = train_df.copy()
        lagged_test = test_df.copy()
        for col in base_cols:
            if col in lagged_train.columns:
                lagged_train[col] = lagged_train.groupby('ticker')[col].shift(1)
            if col in lagged_test.columns:
                lagged_test[col] = lagged_test.groupby('ticker')[col].shift(1)
        # Drop rows with NaN from lagging
        lagged_train = lagged_train.dropna(subset=[c for c in base_cols if c in lagged_train.columns])

        # Build features dict for train (using lagged OHLCV)
        train_features = {col: lagged_train[col].values for col in available_cols if col in lagged_train.columns}
        # Add target
        if return_col not in lagged_train.columns:
            logger.warning(f"Target {return_col} not in train_df, skipping evolution")
            return None, 0.0
        train_target = lagged_train[return_col].values
        # GP config: keep simple to avoid overfitting (V2 proven config)
        # Adaptive blend weight handles quality variance instead
        config = GPConfig(
            population_size=150,
            generations=3,
            max_depth=3,
            hall_of_fame_size=3,
        )
        engine = GeneticEngine(config)
        # features dict = OHLCV + alpha columns, target = forward returns
        train_target = lagged_train[return_col].values
        # Align hall_of_fame evolve with lagged train features
        hall_of_fame = engine.evolve(train_features, train_target)

        if not hall_of_fame:
            logger.warning("Evolution produced no individuals, skipping")
            return None, 0.0

        # P1: Ensemble top 3 GP trees (not just best) for robustness
        # Average signals from hall_of_fame[0:3] to reduce variance
        test_features = {col: lagged_test[col].values if col in lagged_test.columns else np.zeros(len(lagged_test))
                        for col in available_cols}
        
        try:
            # Execute all individuals in hall_of_fame
            ensemble_signals = []
            for individual in hall_of_fame:
                signal = individual._execute_tree(individual.tree, test_features)
                signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
                # Normalize each signal to zero mean, unit std
                std_val = np.std(signal)
                if std_val > 1e-9:
                    signal = (signal - np.mean(signal)) / std_val
                ensemble_signals.append(signal)
            
            # Average ensemble signals
            evolved_signal = np.mean(ensemble_signals, axis=0)
            
            # Compute train IC on ensemble signal for adaptive blending
            train_ensemble_signals = []
            for individual in hall_of_fame:
                signal = individual._execute_tree(individual.tree, train_features)
                signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
                # Normalize each signal to zero mean, unit std (same as test side for parity)
                train_std = np.std(signal)
                if train_std > 1e-9:
                    signal = (signal - np.mean(signal)) / train_std
                train_ensemble_signals.append(signal)
            
            train_signal = np.mean(train_ensemble_signals, axis=0)
            train_ic = float(np.corrcoef(train_signal, train_target)[0, 1]) if len(train_signal) > 1 else 0.0
            if np.isnan(train_ic):
                train_ic = 0.0
            
            test_ret = lagged_test[return_col].values if return_col in lagged_test.columns else np.zeros(len(lagged_test))
            test_ic = float(np.corrcoef(evolved_signal, test_ret)[0, 1]) if len(evolved_signal) > 1 else 0.0
            if np.isnan(test_ic):
                test_ic = 0.0
            
            logger.info(
                f"GP ensemble (n={len(hall_of_fame)}): train_ic={train_ic:.4f}, "
                f"test_ic={test_ic:.4f}, signal_std={np.std(evolved_signal):.4f}"
            )
            return evolved_signal, train_ic
        except Exception as e:
            logger.error(f"GP ensemble execution failed: {e}")
            return None, 0.0
    
    def compute_alpha_ics(
        self,
        df: pd.DataFrame,
        alpha_cols: List[str],
        return_col: str = 'fwd_ret_5',
    ) -> Dict[str, float]:
        """Compute IC for each alpha.
        
        Parameters
        ----------
        df : pd.DataFrame
            Data with alpha columns and forward returns
        alpha_cols : list of str
            Alpha column names
        return_col : str
            Forward return column name
        
        Returns
        -------
        dict
            Mapping of alpha name to IC
        """
        ics = {}
        
        for alpha_col in alpha_cols:
            if alpha_col not in df.columns:
                logger.warning(f"Alpha column {alpha_col} not found")
                ics[alpha_col] = 0.0
                continue
            
            # P8: IC-Decay Weighting - compute IC on 3 sub-windows with exponential decay
            # Weights: [0.2, 0.3, 0.5] for [old, middle, recent] thirds of training data
            dates = sorted(df['date'].unique())
            n_dates = len(dates)
            
            if n_dates >= 30:  # Only apply decay if enough history
                third = n_dates // 3
                windows = [
                    (0, third, 0.2),           # oldest third
                    (third, 2*third, 0.3),     # middle third
                    (2*third, n_dates, 0.5)    # most recent third
                ]
                
                weighted_ic = 0.0
                weight_sum = 0.0
                
                for start_idx, end_idx, weight in windows:
                    window_dates = dates[start_idx:end_idx]
                    window_df = df[df['date'].isin(window_dates)]
                    
                    if len(window_df) > 0:
                        ic_val = self.compute_ic(window_df[alpha_col], window_df[return_col])
                        weighted_ic += ic_val * weight
                        weight_sum += weight
                
                if weight_sum > 0:
                    ics[alpha_col] = weighted_ic / weight_sum
                else:
                    ics[alpha_col] = self.compute_ic(df[alpha_col], df[return_col])
            else:
                # Fallback to simple IC if insufficient history
                ic = self.compute_ic(df[alpha_col], df[return_col])
                ics[alpha_col] = ic
        
        return ics
    
    def _estimate_alpha_turnover(self, df: pd.DataFrame, alpha_col: str) -> float:
        """Estimate day-over-day rank turnover of alpha_col in [0, 1].

        If column missing or single-date DataFrame, return conservative fallback 0.5.
        Turnover = mean( abs( rank_t - rank_{t-1} ) ) / (N_assets - 1)
        """
        if alpha_col not in df.columns:
            return 0.5

        # Check unique dates
        dates = sorted(df['date'].unique())
        if len(dates) < 2:
            return 0.5

        # Pivoting date x ticker to compute rank turnover
        pivot = df.pivot(index='date', columns='ticker', values=alpha_col)
        
        # Rank cross-sectionally per day, normalized to [0, 1]
        # method='average' is stable, pct=True maps rank to [0, 1]
        ranks = pivot.rank(axis=1, pct=True)
        
        # Day-over-day absolute change in rank pct
        diffs = ranks.diff(axis=0).abs()
        
        # Mean absolute change over time and assets
        # If there are NaN values we drop them
        mean_diff = diffs.mean(axis=1).mean()
        if pd.isna(mean_diff):
            return 0.5
            
        # Clip to ensure in [0, 1]
        return float(np.clip(mean_diff, 0.0, 1.0))

    def adjust_alphas_for_cost(
        self,
        df: pd.DataFrame,
        alpha_cols: List[str],
        train_ics: Dict[str, float],
        cost_per_turnover: float | None = None,
    ) -> Dict[str, float]:
        """Compute cost-adjusted IC for each alpha.

        adjusted_ic = raw_ic - cost * turnover
        """
        if cost_per_turnover is None:
            cost_per_turnover = self.cost_per_turnover

        adjusted_ics = {}
        for col in alpha_cols:
            raw_ic = train_ics.get(col, 0.0)
            turnover = self._estimate_alpha_turnover(df, col)
            adjusted_ics[col] = raw_ic - cost_per_turnover * turnover

        return adjusted_ics

    def select_top_alphas(
        self,
        alpha_ics: Dict[str, float],
    ) -> List[str]:
        """Select top N alphas by absolute IC.
        
        Parameters
        ----------
        alpha_ics : dict
            Mapping of alpha name to IC
        
        Returns
        -------
        list of str
            Top N alpha names
        """
        # Filter by minimum IC threshold
        valid_alphas = {k: v for k, v in alpha_ics.items() if abs(v) >= self.min_ic_threshold}
        
        if not valid_alphas:
            logger.warning(f"No alphas meet IC threshold {self.min_ic_threshold}, using all")
            valid_alphas = alpha_ics
        
        # Sort by absolute IC
        sorted_alphas = sorted(valid_alphas.items(), key=lambda x: abs(x[1]), reverse=True)
        
        # Take top N
        top_alphas = [name for name, _ in sorted_alphas[:self.top_n_alphas]]
        
        logger.info(f"Selected top {len(top_alphas)} alphas: {top_alphas}")
        
        return top_alphas
    
    def risk_adjusted_select(
        self,
        alpha_cols: List[str],
        *,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        train_ics: Dict[str, float],
        val_ics: Optional[Dict[str, float]] = None,
        daily_ics: Optional[Dict[str, pd.Series]] = None,
        expected_sharpe_contrib: Optional[Dict[str, float]] = None,
        max_drawdowns: Optional[Dict[str, float]] = None,
        return_col: str = "fwd_ret_5",
        top_n: Optional[int] = None,
        min_composite_score: float = 0.35,
        require_positive_val_ic: bool = True,
        max_overfit_gap: float = 0.15,
        preset: Optional[str] = None,
    ):
        """Opt-in risk-adjusted alpha selection (GATE: RISK_ADJUSTED_ALPHA_TUNING_20260614).

        Computes composite risk-adjusted scores using only embargoed train/val
        data (no test future) and returns a selection result with paper-trading
        gate PASS/FAIL and evidence.

        PIT Safety: all inputs must come from train/validation periods only.
        No test-set data should appear in any argument.

        Parameters
        ----------
        alpha_cols : list of str
            Alpha column names.
        train_df, val_df : pd.DataFrame
            Embargoed training and validation data.
        train_ics : dict
            Per-alpha IC on training set.
        val_ics, daily_ics : dict, optional
            Precomputed validation ICs / daily IC series.
        expected_sharpe_contrib, max_drawdowns : dict, optional
            Per-alpha Sharpe / drawdown if safely available.
        return_col : str
            Forward return column.
        top_n : int, optional
            Max alphas to select (defaults to self.top_n_alphas).
        min_composite_score : float
            Minimum composite score threshold.
        require_positive_val_ic : bool
            Require positive validation IC.
        max_overfit_gap : float
            Maximum allowed overfit gap.
        preset : str, optional
            Weight preset name.  If None, uses self.risk_adjusted_preset.

        Returns
        -------
        RiskAdjustedSelectionResult
        """
        from omega.quant.walk_forward.risk_adjusted_alpha_score import (
            score_alpha_candidates,
            select_alphas_risk_adjusted,
            get_preset_weights,
            get_preset_rank_components,
        )

        if top_n is None:
            top_n = self.top_n_alphas

        # Resolve preset (fall back to engine-level preset)
        resolved_preset = preset or self.risk_adjusted_preset
        weights = get_preset_weights(resolved_preset)

        break_downs = score_alpha_candidates(
            alpha_cols,
            train_df=train_df,
            val_df=val_df,
            train_ics=train_ics,
            val_ics=val_ics,
            daily_ics=daily_ics,
            expected_sharpe_contrib=expected_sharpe_contrib,
            max_drawdowns=max_drawdowns,
            return_col=return_col,
            weights=weights,
        )

        result = select_alphas_risk_adjusted(
            break_downs,
            top_n=top_n,
            min_composite_score=min_composite_score,
            require_positive_val_ic=require_positive_val_ic,
            max_overfit_gap=max_overfit_gap,
        )

        # GATE: RISK_ADJUSTED_ALPHA_TUNING_20260614 — attach config with
        # preset name and resolved weights for per-fold evidence persistence.
        # GATE: RISK_ADJUSTED_ALPHA_IC_FIRST_TUNING_20260614 — include
        # primary_rank_components and soft_penalty_components for audit.
        rank_meta = get_preset_rank_components(resolved_preset)
        result.config = {
            "risk_adjusted_alpha_selection": True,
            "preset": resolved_preset,
            "weights": weights,
            "primary_rank_components": rank_meta["primary_rank_components"],
            "soft_penalty_components": rank_meta["soft_penalty_components"],
            "top_n": top_n,
            "min_composite_score": min_composite_score,
            "require_positive_val_ic": require_positive_val_ic,
            "max_overfit_gap": max_overfit_gap,
            "return_col": return_col,
        }

        logger.info(
            f"[RiskAdj] Selected {len(result.selected_alphas)}/{len(alpha_cols)} alphas: "
            f"gate={result.paper_trading_gate}, preset={resolved_preset}"
        )
        return result

    def validate_alpha_with_research_gate(
        self,
        top_alphas: List[str],
        train_ics: Dict[str, float],
        train_df_clean: pd.DataFrame,
        return_col: str = 'fwd_ret_5',
        rolling_window: int = 20,
    ) -> Tuple[List[str], Dict[str, dict]]:
        """Filter top_alphas through Research Gate using embargoed train_df_clean.

        Computes a rolling IC series (rolling_window-day window) from daily
        cross-sectional ICs on train_df_clean (PIT safe — no look-ahead).
        Each alpha is validated via validate_research_gate(). Alphas that pass
        are returned as gated_alphas. If all fail, falls back to top_alphas.

        Parameters
        ----------
        top_alphas : list of str
            Candidate alpha names from select_top_alphas().
        train_ics : dict
            Per-alpha IC on embargoed train set (used as val_ic).
        train_df_clean : pd.DataFrame
            Embargoed training data with alpha columns and return_col.
        return_col : str
            Forward return column name.
        rolling_window : int
            Window size for rolling IC series (default 20).

        Returns
        -------
        gated_alphas : list of str
            Alphas that passed the Research Gate (or fallback = top_alphas).
        gate_results : dict
            Mapping of alpha name -> validate_research_gate() result dict.

        Notes
        -----
        PIT Safety: rolling IC is computed solely on train_df_clean which has
        the embargo applied upstream. No test-period data is used here.
        """
        gate_results: Dict[str, dict] = {}

        # Compute daily cross-sectional IC per alpha on embargoed train set
        # Vectorized: groupby date, compute all alpha ICs per group
        dates = sorted(train_df_clean['date'].unique())
        _avail_alphas = [a for a in top_alphas if a in train_df_clean.columns]

        def _daily_ics(group: pd.DataFrame) -> pd.Series:
            """Return Series of IC per alpha for one date group."""
            ret = group[return_col]
            ics = {}
            for alpha in _avail_alphas:
                mask = ~(group[alpha].isna() | ret.isna())
                if mask.sum() < 5:
                    ics[alpha] = np.nan
                    continue
                try:
                    ic_val, _ = spearmanr(
                        group.loc[mask, alpha].values,
                        group.loc[mask, return_col].values,
                    )
                    ics[alpha] = ic_val if not np.isnan(ic_val) else np.nan
                except Exception:
                    ics[alpha] = np.nan
            return pd.Series(ics)

        ic_df = train_df_clean.groupby('date').apply(
            _daily_ics, include_groups=False
        )  # index=date, columns=alphas

        daily_ics: Dict[str, pd.Series] = {}
        for alpha in top_alphas:
            if alpha in ic_df.columns:
                daily_ics[alpha] = ic_df[alpha].reindex(dates)
            else:
                daily_ics[alpha] = pd.Series(dtype=float)

        # Validate each alpha through Research Gate
        gated_alphas: List[str] = []
        for alpha in top_alphas:
            val_ic = train_ics.get(alpha, 0.0)
            raw_daily = daily_ics.get(alpha, pd.Series(dtype=float))
            # Rolling mean IC series (drop NaN before rolling)
            rolling_ic = raw_daily.dropna().rolling(window=rolling_window).mean().dropna()
            result = validate_research_gate(val_ic, rolling_ic)
            gate_results[alpha] = result
            if result['passed']:
                gated_alphas.append(alpha)
            logger.info(
                f"Research Gate [{alpha}]: {result['verdict']} "
                f"(val_ic={val_ic:.4f}, n_samples={result['n_samples']})"
            )

        # Fallback: if all alphas fail gate, use original top_alphas
        used_fallback = False
        if not gated_alphas:
            logger.warning(
                "All alphas failed Research Gate — falling back to top_alphas "
                f"({top_alphas})"
            )
            gated_alphas = list(top_alphas)
            used_fallback = True

        # Role21 Fix 2026-06-10: Clarify selection source in logs
        if used_fallback:
            logger.info(f"Selected alphas (fallback candidates) ({len(gated_alphas)}/{len(top_alphas)}): {gated_alphas}")
        else:
            logger.info(f"Selected alphas (gate-passed) ({len(gated_alphas)}/{len(top_alphas)}): {gated_alphas}")
        return gated_alphas, gate_results
    
    def compute_portfolio_signal(
        self,
        df: pd.DataFrame,
        alpha_cols: List[str],
        alpha_ics: Dict[str, float],
    ) -> pd.Series:
        """Compute IC-weighted portfolio signal.
        
        Parameters
        ----------
        df : pd.DataFrame
            Data with alpha columns
        alpha_cols : list of str
            Alpha column names to combine
        alpha_ics : dict
            IC weights for each alpha
        
        Returns
        -------
        pd.Series
            Combined portfolio signal
        """
        # Extract IC weights
        weights = np.array([alpha_ics.get(col, 0.0) for col in alpha_cols])
        
        # Normalize weights to sum to 1
        weight_sum = np.abs(weights).sum()
        if weight_sum > 0:
            weights = weights / weight_sum
        else:
            weights = np.ones(len(weights)) / len(weights)
        
        # Per-alpha z-score normalization (cross-sectional per date) BEFORE blend
        # Prevents high-scale alphas from dominating IC-weighted combination
        df_norm = df[alpha_cols].copy()
        for col in alpha_cols:
            df_norm[col] = df.groupby('date')[col].transform(
                lambda x: (x - x.mean()) / (x.std() + 1e-9)
            )
        
        # Compute weighted average on normalized alphas
        alpha_matrix = df_norm[alpha_cols].values
        portfolio_signal = alpha_matrix @ weights
        
        return pd.Series(portfolio_signal, index=df.index)

    def apply_formulaic_winner_guard(
        self,
        candidate_alphas: List[str],
        val_ics: Dict[str, float],
    ) -> Tuple[List[str], Dict[str, any]]:
        """Apply formulaic winner selection guard to candidate alpha pool.

        GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614

        When formulaic_winner_guard is enabled, filters the candidate alpha
        pool to only include alphas in the winner allowlist that also meet
        the minimum validation IC threshold.  Prevents negative legacy
        alphas from entering the selection or fallback pool.

        PIT Safety: val_ics must come from current-fold validation data only.
        No future fold or aggregate stat report data should be used.

        Parameters
        ----------
        candidate_alphas : list of str
            Candidate alpha names from select_top_alphas() or risk-adjusted
            selection.
        val_ics : dict
            Per-alpha validation IC (from current fold train/validation
            split only).

        Returns
        -------
        filtered_alphas : list of str
            Alpha names passing the winner guard filter.  If all candidates
            are excluded, returns an allowlist-only fallback ranked by
            current-fold validation IC (where available).  If no allowlist
            members have qualifying val_ic, returns an empty list and sets
            evidence["no_guard_candidates"] = True.
        evidence : dict
            Per-fold evidence dict with keys: guard_enabled, allowlist,
            pre_guard_alphas, post_guard_alphas, excluded_alphas,
            val_ics_used, min_val_ic, fallback_used, no_guard_candidates.
        """
        # GATE: AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615
        # Build effective allowlist: base + auto bundle names when enabled.
        _base_allowlist = list(self.formulaic_winner_allowlist)
        _auto_allowlist_names: List[str] = []
        if (
            self.enable_auto_winner_guard_allowlist
            and self.enable_automated_oos_bundle
        ):
            _auto_allowlist_names = list(self.automated_oos_bundle_alphas)
        _effective_allowlist = list(
            dict.fromkeys(_base_allowlist + _auto_allowlist_names)
        )

        evidence = {
            "gate": FORMULAIC_WINNER_GUARD_GATE_ID,
            "guard_enabled": self.formulaic_winner_guard,
            "allowlist": _effective_allowlist,
            "auto_winner_guard_allowlist_enabled": (
                self.enable_auto_winner_guard_allowlist
            ),
            "auto_winner_guard_allowlist_names": _auto_allowlist_names,
            "base_allowlist": _base_allowlist,
            "pre_guard_alphas": list(candidate_alphas),
            "post_guard_alphas": [],
            "excluded_alphas": [],
            "val_ics_used": {
                a: round(val_ics.get(a, 0.0), 6) for a in candidate_alphas
            },
            "min_val_ic": self.formulaic_winner_min_val_ic,
            "fallback_used": False,
            "no_guard_candidates": False,
            "pit_safe": True,
        }

        if not self.formulaic_winner_guard:
            evidence["post_guard_alphas"] = list(candidate_alphas)
            return list(candidate_alphas), evidence

        # Filter: keep only allowlist members with val_ic >= min threshold
        allowlist_set = set(_effective_allowlist)
        filtered = []
        excluded = []
        for alpha in candidate_alphas:
            in_allowlist = alpha in allowlist_set
            ic_val = val_ics.get(alpha, 0.0)
            meets_ic = ic_val >= self.formulaic_winner_min_val_ic
            if in_allowlist and meets_ic:
                filtered.append(alpha)
            else:
                excluded.append(alpha)

        # FIX1: Allowlist-only fallback — never re-admit non-allowlist legacy alphas.
        # GATE: FORMULAIC_WINNER_SELECTION_GUARD_FIX1_20260614
        # When all candidates excluded, build a fallback from allowlist members
        # ranked by current-fold validation IC (where available).  If no allowlist
        # members have any val_ic data, mark fold as no_guard_candidates instead
        # of restoring original (non-allowlist) candidates.
        fallback_used = False
        no_guard_candidates = False
        if not filtered and candidate_alphas:
            # Build allowlist-only fallback ranked by val_ic
            # GATE: AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615
            # Use effective allowlist (includes auto names when enabled).
            allowlist_with_ic = []
            for al in _effective_allowlist:
                ic_val = val_ics.get(al, None)
                if ic_val is not None and ic_val >= self.formulaic_winner_min_val_ic:
                    allowlist_with_ic.append((al, ic_val))
            # Sort by absolute IC descending (best first)
            allowlist_with_ic.sort(key=lambda x: abs(x[1]), reverse=True)
            allowlist_fallback = [al for al, _ in allowlist_with_ic]

            if allowlist_fallback:
                logger.warning(
                    f"[WinnerGuard] All candidates excluded by guard "
                    f"(allowlist={self.formulaic_winner_allowlist}, "
                    f"min_val_ic={self.formulaic_winner_min_val_ic}). "
                    f"Using allowlist-only fallback ranked by val_ic: "
                    f"{allowlist_fallback}"
                )
                filtered = allowlist_fallback
                fallback_used = True
            else:
                logger.warning(
                    f"[WinnerGuard] All candidates excluded by guard and no "
                    f"allowlist members have qualifying val_ic. "
                    f"Marking fold as no_guard_candidates."
                )
                filtered = []
                no_guard_candidates = True
                fallback_used = False

        evidence["post_guard_alphas"] = list(filtered)
        evidence["excluded_alphas"] = list(excluded)
        evidence["fallback_used"] = fallback_used
        evidence["no_guard_candidates"] = no_guard_candidates

        logger.info(
            f"[WinnerGuard] {len(filtered)}/{len(candidate_alphas)} alphas "
            f"passed guard (excluded={len(excluded)}, "
            f"fallback={fallback_used}, "
            f"no_guard_candidates={no_guard_candidates})"
        )
        return filtered, evidence

    def filter_fallback_by_winner_guard(
        self,
        fallback_alphas: List[str],
        val_ics: Dict[str, float],
    ) -> Tuple[List[str], List[str]]:
        """Filter fallback alphas through winner guard when enabled.

        GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614

        When formulaic_winner_guard is enabled, removes non-allowlist legacy
        alphas from the fallback candidate pool.  This prevents negative
        legacy alphas from entering fallback when the research gate fails
        for all selected alphas.

        PIT Safety: val_ics must come from current-fold validation data only.

        Parameters
        ----------
        fallback_alphas : list of str
            Fallback candidate names (typically top_alphas when all fail gate).
        val_ics : dict
            Per-alpha validation IC from current fold.

        Returns
        -------
        filtered_fallback : list of str
            Fallback alphas passing the winner guard.  If all fallback
            alphas are non-allowlist, returns empty list (FIX1: no legacy
            re-admission).
        excluded_from_fallback : list of str
            Fallback alphas excluded by the winner guard.
        """
        if not self.formulaic_winner_guard:
            return list(fallback_alphas), []

        # GATE: AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615
        _effective_allowlist = list(self.formulaic_winner_allowlist)
        if (
            self.enable_auto_winner_guard_allowlist
            and self.enable_automated_oos_bundle
        ):
            _effective_allowlist = list(
                dict.fromkeys(
                    _effective_allowlist
                    + list(self.automated_oos_bundle_alphas)
                )
            )
        allowlist_set = set(_effective_allowlist)
        filtered = []
        excluded = []
        for alpha in fallback_alphas:
            if alpha in allowlist_set:
                filtered.append(alpha)
            else:
                excluded.append(alpha)

        # FIX1: Never re-admit non-allowlist legacy alphas into fallback pool.
        # GATE: FORMULAIC_WINNER_SELECTION_GUARD_FIX1_20260614
        # If all fallback excluded, return empty list (caller handles empty
        # gated_alphas gracefully).  Do NOT restore original legacy candidates.
        if not filtered and fallback_alphas:
            logger.warning(
                f"[WinnerGuard] Fallback filter excluded all candidates. "
                f"Returning empty fallback (no non-allowlist legacy re-admission)."
            )
            return [], list(fallback_alphas)

        if excluded:
            logger.info(
                f"[WinnerGuard] Fallback filter excluded {len(excluded)} "
                f"non-allowlist alphas: {excluded}"
            )
        return filtered, excluded
    
    # ------------------------------------------------------------------
    # GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615
    # Ex-ante regime detection, per-regime IC estimation, and signal routing.
    # All methods are PIT-safe: regime features use only lagged market data,
    # IC estimation uses train window only, and test routing uses only
    # ex-ante regime labels (never test returns).
    # ------------------------------------------------------------------

    def _compute_ex_ante_regimes(
        self,
        df: pd.DataFrame,
        vol_window: int = 20,
        trend_window: int = 20,
    ) -> pd.DataFrame:
        """Compute deterministic ex-ante regime labels from lagged market features.

        PIT Safety: regime features are computed from T-1 lagged close prices.
        No forward-looking data is used.  The regime label for date T depends
        only on data available at T-1 and earlier.

        Regime classification (4-state, quantile-based):
        - 'bull':          low vol, positive trend
        - 'bull_volatile': high vol, positive trend
        - 'sideways':      low vol, flat/negative trend
        - 'bear':          high vol, negative trend

        Parameters
        ----------
        df : pd.DataFrame
            Must contain 'date', 'ticker', 'close' columns.
        vol_window : int
            Rolling window for volatility (default 20 days).
        trend_window : int
            Rolling window for trend (default 20 days).

        Returns
        -------
        pd.DataFrame
            DataFrame with columns 'date' and 'regime', one row per date.
        """
        work = df[['date', 'ticker', 'close']].copy()
        work = work.sort_values(['ticker', 'date'])

        # Per-ticker daily returns, then T-1 lag for PIT safety
        work['ret'] = work.groupby('ticker')['close'].pct_change()
        work['ret_lagged'] = work.groupby('ticker')['ret'].shift(1)

        # Aggregate cross-sectionally per date (equal-weight market proxy)
        daily = work.groupby('date').agg(
            market_ret=('ret_lagged', 'mean'),
        ).sort_index()

        # Rolling volatility and trend from lagged returns
        daily['vol'] = daily['market_ret'].rolling(
            window=vol_window, min_periods=max(5, vol_window // 2)
        ).std()
        daily['trend'] = daily['market_ret'].rolling(
            window=trend_window, min_periods=max(5, trend_window // 2)
        ).mean()

        # Use expanding median as threshold for high/low split (PIT-safe)
        vol_threshold = daily['vol'].expanding().median()
        trend_threshold = 0.0  # positive vs non-positive

        # Classify regimes
        regimes = pd.Series('sideways', index=daily.index)
        high_vol = daily['vol'] > vol_threshold
        pos_trend = daily['trend'] > trend_threshold

        regimes[~high_vol & pos_trend] = 'bull'
        regimes[high_vol & pos_trend] = 'bull_volatile'
        regimes[~high_vol & ~pos_trend] = 'sideways'
        regimes[high_vol & ~pos_trend] = 'bear'

        # Drop NaN rows (warmup period)
        valid_mask = daily['vol'].notna() & daily['trend'].notna()
        result = pd.DataFrame({
            'date': daily.index[valid_mask],
            'regime': regimes[valid_mask].values,
        })
        return result.reset_index(drop=True)

    def _estimate_regime_ic(
        self,
        train_df: pd.DataFrame,
        alpha_cols: List[str],
        return_col: str,
        regime_df: pd.DataFrame,
    ) -> Dict[str, Dict[str, float]]:
        """Estimate per-alpha, per-regime IC using train window only.

        PIT Safety: train_df must be embargoed training data only.
        regime_df provides the regime label per date (from ex-ante features).

        Parameters
        ----------
        train_df : pd.DataFrame
            Embargoed training data with alpha columns and return_col.
        alpha_cols : list of str
            Alpha column names.
        return_col : str
            Forward return column.
        regime_df : pd.DataFrame
            DataFrame with 'date' and 'regime' columns.

        Returns
        -------
        dict
            Nested dict: {alpha_name: {regime: ic_value}}.
        """
        merged = train_df.merge(regime_df, on='date', how='inner')
        regime_ic: Dict[str, Dict[str, float]] = {}

        for alpha_col in alpha_cols:
            if alpha_col not in merged.columns:
                continue
            regime_ic[alpha_col] = {}
            for regime in merged['regime'].unique():
                subset = merged[merged['regime'] == regime]
                ic_val = self.compute_ic(subset[alpha_col], subset[return_col])
                regime_ic[alpha_col][regime] = ic_val

        return regime_ic

    def _apply_regime_routing(
        self,
        test_df: pd.DataFrame,
        portfolio_signal: pd.Series,
        regime_df: pd.DataFrame,
        regime_ics: Dict[str, Dict[str, float]],
        alpha_cols: List[str],
        train_ics: Dict[str, float],
    ) -> Tuple[pd.Series, Dict[str, any]]:
        """Apply regime-conditional scaling to portfolio signal on test data.

        PIT Safety: regime labels for test dates come from ex-ante features
        (lagged market data only).  IC weights come from train window only.
        Test returns are NEVER used for routing decisions.

        Scaling logic:
        - For each test date, look up the ex-ante regime label.
        - Compute a regime quality score = mean of per-alpha regime ICs.
        - Scale the signal by regime_quality / baseline_quality (clamped).
        - If regime quality < min_ic, fall back to baseline (scale=1.0).

        Parameters
        ----------
        test_df : pd.DataFrame
            Test data with 'date' column.
        portfolio_signal : pd.Series
            Raw portfolio signal (same index as test_df).
        regime_df : pd.DataFrame
            Ex-ante regime labels per date.
        regime_ics : dict
            Per-alpha, per-regime IC from train window.
        alpha_cols : list of str
            Alpha column names.
        train_ics : dict
            Per-alpha overall IC from train window.

        Returns
        -------
        routed_signal : pd.Series
            Regime-scaled portfolio signal.
        evidence : dict
            JSON-serializable evidence dict.
        """
        # Build date -> regime mapping
        regime_map = dict(zip(regime_df['date'], regime_df['regime']))

        # Compute per-regime quality score (mean abs IC across alphas)
        regime_quality: Dict[str, float] = {}
        all_regimes = set()
        for alpha_dict in regime_ics.values():
            all_regimes.update(alpha_dict.keys())

        for regime in all_regimes:
            ic_vals = []
            for alpha_col in alpha_cols:
                if alpha_col in regime_ics and regime in regime_ics[alpha_col]:
                    ic_vals.append(regime_ics[alpha_col][regime])
            regime_quality[regime] = (
                float(np.mean(ic_vals)) if ic_vals else 0.0
            )

        # Baseline quality (overall mean IC)
        baseline_quality = float(np.mean([
            abs(v) for v in train_ics.values()
        ])) if train_ics else 0.0

        # Compute per-date scale factor
        test_dates = test_df['date'].values
        scale_factors = np.ones(len(test_dates))
        regime_labels_used = []
        n_routed = 0
        n_fallback = 0

        for i, d in enumerate(test_dates):
            regime = regime_map.get(d, None)
            if regime is None:
                regime_labels_used.append('unknown')
                n_fallback += 1
                continue
            regime_labels_used.append(regime)
            rq = regime_quality.get(regime, 0.0)

            if abs(rq) < self.regime_routing_min_ic:
                # Insufficient evidence → fallback (scale=1.0)
                n_fallback += 1
                continue

            # Scale: ratio of regime quality to baseline, clamped to [0.5, 1.5]
            if baseline_quality > 1e-9:
                raw_scale = abs(rq) / baseline_quality
                scale_factors[i] = float(np.clip(raw_scale, 0.5, 1.5))
            else:
                scale_factors[i] = 1.0
            n_routed += 1

        routed_signal = portfolio_signal * pd.Series(
            scale_factors, index=portfolio_signal.index
        )

        evidence = {
            "gate": REGIME_ROUTING_GATE_ID,
            "enabled": True,
            "regime_quality": {k: round(v, 6) for k, v in regime_quality.items()},
            "baseline_quality": round(baseline_quality, 6),
            "n_routed": n_routed,
            "n_fallback": n_fallback,
            "n_test_dates": len(test_dates),
            "min_ic": self.regime_routing_min_ic,
            "min_train_days": self.regime_routing_min_train_days,
            "fallback_mode": self.regime_routing_fallback,
            "regime_distribution": {
                str(k): int(v)
                for k, v in pd.Series(regime_labels_used).value_counts().items()
            },
            "pit_safe": True,
        }

        return routed_signal, evidence

    # ------------------------------------------------------------------
    # GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616
    # PIT-safe stability filter for auto-alpha bundle.
    # Uses ONLY train/in-fold pre-OOS evidence to assess IC stability.
    # Never uses OOS/test labels or current-bar data.
    # ------------------------------------------------------------------

    def _apply_oos_stability_filter(
        self,
        candidate_alphas: List[str],
        train_df: pd.DataFrame,
        return_col: str,
        bundle_alpha_prefix: str = "auto_",
    ) -> Tuple[List[str], Dict[str, any]]:
        """Apply PIT-safe OOS stability filter to candidate alpha pool.

        GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616

        For each candidate alpha (especially auto-bundle alphas), computes
        train-only stability metrics:
          1. IC sign consistency: fraction of sub-windows where mean IC
             matches the overall IC sign.
          2. ICIR: |mean(daily IC)| / std(daily IC) across train dates.
          3. IC decay penalty: ratio of recent-third mean IC to
             oldest-third mean IC.  If decay < 0 (sign flip), penalize.
          4. Composite stability score: combines the above into a single
             gate score.

        An alpha passes the stability filter if:
          - ICIR >= stability_min_icir
          - sign_consistency >= stability_min_sign_consistency
          - composite_score > 0 (after decay penalty)

        PIT Safety: ALL inputs come from embargoed training data only.
        No test-set data, no OOS labels, no current-bar features.

        Parameters
        ----------
        candidate_alphas : list of str
            Candidate alpha column names from upstream selection.
        train_df : pd.DataFrame
            Embargoed training data with alpha columns and return_col.
        return_col : str
            Forward return column name (e.g. 'fwd_ret_5').
        bundle_alpha_prefix : str
            Alpha name prefix identifying auto-bundle alphas that
            require stability filtering.  Non-matching alphas pass
            through unchanged.

        Returns
        -------
        filtered_alphas : list of str
            Alpha names passing the stability filter (or all if filter
            is disabled).
        evidence : dict
            JSON-serializable per-fold evidence dict.
        """
        evidence = {
            "gate": AUTO_ALPHA_OOS_STABILITY_FILTER_GATE_ID,
            "enabled": self.enable_oos_stability_filter,
            "candidate_alphas": list(candidate_alphas),
            "n_candidates": len(candidate_alphas),
            "stability_min_icir": self.stability_min_icir,
            "stability_min_sign_consistency": self.stability_min_sign_consistency,
            "stability_decay_penalty_factor": self.stability_decay_penalty_factor,
            "stability_min_sub_windows": self.stability_min_sub_windows,
            "alpha_stability_metrics": {},
            "passed_alphas": [],
            "excluded_alphas": [],
            "filter_disabled_passthrough_alphas": [],
            "fallback_used": False,
            "pit_safe": True,
            "no_oos_label_use": True,
        }

        if not self.enable_oos_stability_filter:
            evidence["passed_alphas"] = list(candidate_alphas)
            return list(candidate_alphas), evidence

        # Identify bundle alphas (require filter) vs non-bundle (passthrough)
        bundle_alphas = [
            a for a in candidate_alphas if a.startswith(bundle_alpha_prefix)
        ]
        non_bundle_alphas = [
            a for a in candidate_alphas
            if not a.startswith(bundle_alpha_prefix)
        ]
        evidence["filter_disabled_passthrough_alphas"] = list(non_bundle_alphas)

        if not bundle_alphas:
            evidence["passed_alphas"] = list(candidate_alphas)
            evidence["note"] = "no_bundle_alphas_in_candidates"
            return list(candidate_alphas), evidence

        # Compute per-date cross-sectional IC for each bundle alpha
        avail_cols = [a for a in bundle_alphas if a in train_df.columns]
        if not avail_cols:
            evidence["passed_alphas"] = list(candidate_alphas)
            evidence["note"] = "no_bundle_alpha_columns_in_train_df"
            return list(candidate_alphas), evidence

        # Check return_col availability
        if return_col not in train_df.columns:
            evidence["passed_alphas"] = list(candidate_alphas)
            evidence["note"] = "return_col_not_in_train_df"
            return list(candidate_alphas), evidence

        dates = sorted(train_df['date'].unique())
        n_dates = len(dates)

        # Compute per-date cross-sectional IC per alpha
        per_date_ics: Dict[str, List[float]] = {a: [] for a in avail_cols}

        for date_val in dates:
            group = train_df[train_df['date'] == date_val]
            if len(group) < 5:
                continue
            ret = group[return_col]
            for alpha in avail_cols:
                if alpha not in group.columns:
                    continue
                mask = ~(group[alpha].isna() | ret.isna())
                if mask.sum() < 5:
                    continue
                try:
                    ic_val, _ = spearmanr(
                        group.loc[mask, alpha].values,
                        group.loc[mask, ret].values,
                    )
                    if not np.isnan(ic_val):
                        per_date_ics[alpha].append(ic_val)
                except Exception:
                    pass

        # Evaluate stability for each bundle alpha
        passed_bundle: List[str] = []
        excluded_bundle: List[str] = []

        for alpha in avail_cols:
            ics = per_date_ics[alpha]
            metrics: Dict[str, float] = {}

            if len(ics) < self.stability_min_sub_windows:
                # Insufficient data: conservative pass
                metrics["n_dates"] = len(ics)
                metrics["verdict"] = "pass_insufficient_data"
                evidence["alpha_stability_metrics"][alpha] = metrics
                passed_bundle.append(alpha)
                continue

            ics_arr = np.array(ics)
            mean_ic = float(np.mean(ics_arr))
            std_ic = float(np.std(ics_arr))

            # ICIR
            icir = mean_ic / std_ic if std_ic > 1e-9 else 0.0
            metrics["icir"] = round(icir, 6)
            metrics["mean_ic"] = round(mean_ic, 6)
            metrics["std_ic"] = round(std_ic, 6)
            metrics["n_dates"] = len(ics)

            # IC sign consistency: split into sub-windows
            n_windows = max(self.stability_min_sub_windows, 3)
            window_size = max(1, len(ics) // n_windows)
            sign_match_count = 0
            total_windows = 0
            ic_sign = np.sign(mean_ic) if abs(mean_ic) > 1e-9 else 1.0
            for w in range(n_windows):
                start = w * window_size
                end = start + window_size if w < n_windows - 1 else len(ics)
                window_ics = ics_arr[start:end]
                if len(window_ics) == 0:
                    continue
                window_mean = float(np.mean(window_ics))
                window_sign = np.sign(window_mean) if abs(window_mean) > 1e-9 else 1.0
                if window_sign == ic_sign:
                    sign_match_count += 1
                total_windows += 1

            sign_consistency = (
                sign_match_count / total_windows
                if total_windows > 0 else 0.0
            )
            metrics["sign_consistency"] = round(sign_consistency, 4)
            metrics["n_windows"] = total_windows

            # IC decay: recent-third vs oldest-third
            third = len(ics) // 3
            if third >= 2:
                oldest_third_mean = float(np.mean(ics_arr[:third]))
                recent_third_mean = float(np.mean(ics_arr[-third:]))
                metrics["oldest_third_ic"] = round(oldest_third_mean, 6)
                metrics["recent_third_ic"] = round(recent_third_mean, 6)

                # Decay ratio: positive means IC stable/growing, negative means decaying
                if abs(oldest_third_mean) > 1e-9:
                    decay_ratio = recent_third_mean / oldest_third_mean
                else:
                    decay_ratio = 1.0 if abs(recent_third_mean) > 1e-9 else 0.0
                metrics["decay_ratio"] = round(decay_ratio, 4)
            else:
                decay_ratio = 1.0
                metrics["decay_ratio"] = 1.0

            # Decay penalty: reduce ICIR when decay < 0
            decay_penalty = 0.0
            if decay_ratio < 0.0:
                decay_penalty = (
                    self.stability_decay_penalty_factor * abs(icir) * abs(decay_ratio)
                )
            metrics["decay_penalty"] = round(decay_penalty, 6)

            # Composite stability score
            composite = abs(icir) - decay_penalty
            metrics["composite_score"] = round(composite, 6)

            # Gate decision
            icir_pass = abs(icir) >= self.stability_min_icir
            sign_pass = sign_consistency >= self.stability_min_sign_consistency
            composite_pass = composite > 0.0

            metrics["icir_pass"] = icir_pass
            metrics["sign_consistency_pass"] = sign_pass
            metrics["composite_pass"] = composite_pass

            if icir_pass and sign_pass and composite_pass:
                passed_bundle.append(alpha)
                metrics["verdict"] = "pass"
            else:
                excluded_bundle.append(alpha)
                fail_reasons = []
                if not icir_pass:
                    fail_reasons.append("icir_below_threshold")
                if not sign_pass:
                    fail_reasons.append("sign_consistency_below_threshold")
                if not composite_pass:
                    fail_reasons.append("composite_non_positive")
                metrics["verdict"] = "exclude"
                metrics["exclude_reasons"] = fail_reasons

            evidence["alpha_stability_metrics"][alpha] = metrics

        evidence["passed_alphas"] = list(
            non_bundle_alphas + passed_bundle
        )
        evidence["excluded_alphas"] = list(excluded_bundle)
        evidence["n_passed_bundle"] = len(passed_bundle)
        evidence["n_excluded_bundle"] = len(excluded_bundle)

        # Fallback: if all bundle alphas excluded, pass them through
        # with a warning (conservative fallback, not silently dropping)
        filtered = list(non_bundle_alphas + passed_bundle)
        if not passed_bundle and bundle_alphas:
            logger.warning(
                f"[OOSStability] All {len(bundle_alphas)} bundle alphas "
                f"excluded by stability filter. Conservative fallback: "
                f"re-include all bundle alphas to avoid zero-signal fold."
            )
            filtered = list(candidate_alphas)
            evidence["fallback_used"] = True
            evidence["fallback_reason"] = "all_bundle_alphas_excluded"

        logger.info(
            f"[OOSStability] {len(passed_bundle)}/{len(bundle_alphas)} "
            f"bundle alphas passed stability filter "
            f"(excluded={len(excluded_bundle)}, "
            f"fallback={evidence['fallback_used']}): "
            f"passed={passed_bundle}, excluded={excluded_bundle}"
        )
        return filtered, evidence

    # ------------------------------------------------------------------
    # GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615
    # Train-only diversified alpha basket selector.
    # Uses train IC/ICIR + pairwise correlation / vector cluster to select
    # a non-redundant basket.  Max N alphas per cluster, correlation penalty,
    # fallback safe basket if no candidates pass.  Never uses OOS/test metrics.
    # ------------------------------------------------------------------

    def select_diversified_basket(
        self,
        candidate_alphas: List[str],
        train_df: pd.DataFrame,
        train_ics: Dict[str, float],
        return_col: str = 'fwd_ret_5',
    ) -> Tuple[List[str], Dict[str, any]]:
        """Select a diversified, non-redundant alpha basket from candidates.

        GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615

        Algorithm:
        1. Filter candidates by basket_min_ic (train IC >= threshold).
        2. Compute pairwise Pearson correlation of alpha signals on train data
           (cross-sectional, averaged over dates — PIT-safe, train only).
        3. Cluster alphas by greedy correlation grouping:
           |corr| >= basket_corr_threshold → same cluster.
        4. Within each cluster, keep top basket_max_per_cluster alphas ranked
           by train ICIR (|mean(IC)| / std(IC) over per-date ICs).
        5. Apply redundancy penalty: if two selected alphas have
           |corr| > basket_corr_threshold / 2, reduce the lower-IC alpha's
           composite score by basket_redundancy_penalty * |corr|.
        6. Sort by composite score descending, return top candidates.
        7. Fallback safe basket: if no candidates pass (basket empty), return
           top_n_alphas by train IC (original baseline behavior).

        PIT Safety: All inputs (train_df, train_ics) come from the embargoed
        training set only.  No test-set data is used.

        Parameters
        ----------
        candidate_alphas : list of str
            Candidate alpha column names (from select_top_alphas or gated).
        train_df : pd.DataFrame
            Embargoed training data with alpha columns.
        train_ics : dict
            Per-alpha IC on training set.
        return_col : str
            Forward return column (unused, kept for interface consistency).

        Returns
        -------
        selected : list of str
            Diversified alpha names.
        evidence : dict
            JSON-serializable evidence dict with full audit trail.
        """
        evidence = {
            "gate": DIVERSIFIED_BASKET_GATE_ID,
            "enabled": True,
            "candidate_alphas": list(candidate_alphas),
            "n_candidates": len(candidate_alphas),
            "min_ic": self.basket_min_ic,
            "corr_threshold": self.basket_corr_threshold,
            "max_per_cluster": self.basket_max_per_cluster,
            "redundancy_penalty": self.basket_redundancy_penalty,
            "selected_alphas": [],
            "clusters": {},
            "pairwise_correlations": {},
            "redundancy_penalties_applied": [],
            "fallback_safe_basket_used": False,
            "pit_safe": True,
        }

        # Step 1: Filter by min IC
        filtered = [
            a for a in candidate_alphas
            if abs(train_ics.get(a, 0.0)) >= self.basket_min_ic
        ]
        evidence["filtered_by_min_ic"] = list(filtered)
        evidence["n_filtered_by_min_ic"] = len(filtered)

        if len(filtered) < 2:
            # Not enough candidates to diversify — use fallback safe basket
            logger.info(
                f"[DivBasket] <2 candidates after IC filter "
                f"({len(filtered)}), using fallback safe basket"
            )
            evidence["fallback_safe_basket_used"] = True
            evidence["fallback_reason"] = "insufficient_candidates_after_ic_filter"
            fallback = sorted(
                candidate_alphas,
                key=lambda a: abs(train_ics.get(a, 0.0)),
                reverse=True,
            )[: self.top_n_alphas]
            evidence["selected_alphas"] = list(fallback)
            return fallback, evidence

        # Step 2: Compute pairwise correlation matrix on train data
        # Cross-sectional per-date Spearman/Pearson, then average across dates
        avail_cols = [a for a in filtered if a in train_df.columns]
        if len(avail_cols) < 2:
            logger.info(
                f"[DivBasket] <2 alpha columns in train_df, using fallback"
            )
            evidence["fallback_safe_basket_used"] = True
            evidence["fallback_reason"] = "insufficient_columns_in_train_df"
            fallback = sorted(
                candidate_alphas,
                key=lambda a: abs(train_ics.get(a, 0.0)),
                reverse=True,
            )[: self.top_n_alphas]
            evidence["selected_alphas"] = list(fallback)
            return fallback, evidence

        # Build per-date cross-sectional correlation, then average
        corr_sums = np.zeros((len(avail_cols), len(avail_cols)))
        corr_counts = 0
        for _, group in train_df.groupby('date'):
            if len(group) < 5:
                continue
            sub = group[avail_cols].dropna()
            if len(sub) < 5:
                continue
            c = sub.corr(method='pearson').values
            corr_sums += c
            corr_counts += 1

        if corr_counts == 0:
            avg_corr = np.eye(len(avail_cols))
        else:
            avg_corr = corr_sums / corr_counts

        # Store pairwise correlations in evidence
        for i in range(len(avail_cols)):
            for j in range(i + 1, len(avail_cols)):
                key = f"{avail_cols[i]}|{avail_cols[j]}"
                corr_val = float(avg_corr[i, j])
                evidence["pairwise_correlations"][key] = (
                    round(corr_val, 4) if not np.isnan(corr_val) else 0.0
                )

        # Step 3: Cluster alphas by greedy correlation grouping
        # |corr| >= threshold → same cluster
        clusters: Dict[int, List[str]] = {}
        assigned: Dict[str, int] = {}
        next_cluster_id = 0

        for i, alpha_i in enumerate(avail_cols):
            if alpha_i in assigned:
                continue
            # Start a new cluster
            cluster_id = next_cluster_id
            next_cluster_id += 1
            clusters[cluster_id] = [alpha_i]
            assigned[alpha_i] = cluster_id

            for j in range(i + 1, len(avail_cols)):
                alpha_j = avail_cols[j]
                if alpha_j in assigned:
                    continue
                corr_val = avg_corr[i, j]
                # Treat NaN correlation as 0 (no relationship)
                if np.isnan(corr_val):
                    corr_val = 0.0
                if abs(corr_val) >= self.basket_corr_threshold:
                    clusters[cluster_id].append(alpha_j)
                    assigned[alpha_j] = cluster_id

        evidence["clusters"] = {
            str(k): list(v) for k, v in clusters.items()
        }
        evidence["n_clusters"] = len(clusters)

        # Step 4: Within each cluster, rank by train ICIR and keep top N
        # ICIR = mean(|per_date_IC|) / std(per_date_IC)
        # We approximate ICIR using train_ics (already computed per-fold)
        # For a more robust ICIR, we compute per-date ICs
        alpha_icir: Dict[str, float] = {}
        alpha_per_date_ics: Dict[str, List[float]] = {a: [] for a in avail_cols}
        for date_val, group in train_df.groupby('date'):
            if len(group) < 5:
                continue
            ret = group[return_col] if return_col in group.columns else None
            if ret is None:
                continue
            for alpha in avail_cols:
                if alpha not in group.columns:
                    continue
                mask = ~(group[alpha].isna() | ret.isna())
                if mask.sum() < 5:
                    continue
                try:
                    ic_val, _ = spearmanr(
                        group.loc[mask, alpha].values,
                        group.loc[mask, return_col].values,
                    )
                    if not np.isnan(ic_val):
                        alpha_per_date_ics[alpha].append(ic_val)
                except Exception:
                    pass

        for alpha in avail_cols:
            ics = alpha_per_date_ics[alpha]
            if len(ics) < 3:
                alpha_icir[alpha] = 0.0
            else:
                mu = float(np.mean(ics))
                sd = float(np.std(ics))
                alpha_icir[alpha] = mu / sd if sd > 1e-9 else 0.0

        evidence["alpha_icir"] = {
            a: round(v, 4) for a, v in alpha_icir.items()
        }

        # Select top max_per_cluster per cluster, ranked by ICIR
        cluster_selected: List[str] = []
        for cluster_id, members in clusters.items():
            # Sort by ICIR descending
            ranked = sorted(
                members, key=lambda a: alpha_icir.get(a, 0.0), reverse=True
            )
            kept = ranked[: self.basket_max_per_cluster]
            cluster_selected.extend(kept)
            evidence["clusters"][str(cluster_id)] = {
                "members": list(members),
                "ranked": list(ranked),
                "kept": list(kept),
                "n_kept": len(kept),
            }

        # Step 5: Apply redundancy penalty
        # If two selected alphas have |corr| > threshold/2, penalize lower IC
        composite_scores: Dict[str, float] = {}
        penalties_applied: List[dict] = []
        corr_half = self.basket_corr_threshold / 2.0

        for alpha in cluster_selected:
            composite_scores[alpha] = abs(train_ics.get(alpha, 0.0))

        for i in range(len(cluster_selected)):
            for j in range(i + 1, len(cluster_selected)):
                ai = cluster_selected[i]
                aj = cluster_selected[j]
                idx_i = avail_cols.index(ai)
                idx_j = avail_cols.index(aj)
                corr_val_raw = avg_corr[idx_i, idx_j]
                corr_val = abs(float(corr_val_raw)) if not np.isnan(corr_val_raw) else 0.0
                if corr_val > corr_half:
                    # Penalize the alpha with lower IC
                    if abs(train_ics.get(ai, 0.0)) >= abs(train_ics.get(aj, 0.0)):
                        penalized = aj
                    else:
                        penalized = ai
                    penalty = self.basket_redundancy_penalty * corr_val
                    composite_scores[penalized] = max(
                        0.0, composite_scores[penalized] - penalty
                    )
                    penalties_applied.append({
                        "alpha_penalized": penalized,
                        "correlated_with": (
                            ai if penalized == aj else aj
                        ),
                        "correlation": round(float(corr_val), 4),
                        "penalty_applied": round(float(penalty), 4),
                    })

        evidence["redundancy_penalties_applied"] = penalties_applied
        evidence["composite_scores"] = {
            a: round(v, 4) for a, v in composite_scores.items()
        }

        # Step 6: Sort by composite score descending, take top N
        sorted_basket = sorted(
            composite_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        selected = [a for a, _ in sorted_basket[: self.top_n_alphas]]

        # Step 7: Fallback safe basket check
        if not selected:
            logger.warning(
                "[DivBasket] Empty basket after selection, "
                "using fallback safe basket (top N by train IC)"
            )
            evidence["fallback_safe_basket_used"] = True
            evidence["fallback_reason"] = "empty_basket_after_selection"
            fallback = sorted(
                candidate_alphas,
                key=lambda a: abs(train_ics.get(a, 0.0)),
                reverse=True,
            )[: self.top_n_alphas]
            evidence["selected_alphas"] = list(fallback)
            return fallback, evidence

        evidence["selected_alphas"] = list(selected)
        evidence["n_selected"] = len(selected)

        logger.info(
            f"[DivBasket] Selected {len(selected)} alphas from "
            f"{len(candidate_alphas)} candidates "
            f"({len(clusters)} clusters, "
            f"{len(penalties_applied)} redundancy penalties): "
            f"{selected}"
        )
        return selected, evidence

    def compute_sharpe_ratio(
        self,
        returns: pd.Series,
        periods_per_year: int = 252,
    ) -> float:
        """Compute annualized Sharpe ratio.
        
        Parameters
        ----------
        returns : pd.Series
            Period returns
        periods_per_year : int
            Number of periods per year (252 for daily)
        
        Returns
        -------
        float
            Annualized Sharpe ratio
        """
        if len(returns) < 2:
            return 0.0
        
        mean_return = returns.mean()
        std_return = returns.std()
        
        if std_return == 0 or np.isnan(std_return):
            return 0.0
        
        sharpe = (mean_return / std_return) * np.sqrt(periods_per_year)
        
        return sharpe if not np.isnan(sharpe) else 0.0
    
    def compute_max_drawdown(
        self,
        returns: pd.Series,
    ) -> float:
        """Compute maximum drawdown.
        
        Parameters
        ----------
        returns : pd.Series
            Period returns
        
        Returns
        -------
        float
            Maximum drawdown (negative value)
        """
        if len(returns) < 2:
            return 0.0
        
        # Compute cumulative returns
        cum_returns = (1 + returns).cumprod()
        
        # Compute running maximum
        running_max = cum_returns.expanding().max()
        
        # Compute drawdown
        drawdown = (cum_returns - running_max) / running_max
        
        # Return maximum drawdown (most negative)
        max_dd = drawdown.min()
        
        return max_dd if not np.isnan(max_dd) else 0.0

    def _apply_drawdown_control(
        self,
        daily_series: pd.Series,
        portfolio_returns: pd.Series,
        aligned_df: pd.DataFrame,
        fold_id: int,
        hmm_p_bear_dict: Optional[Dict] = None,
        close_wide: Optional[pd.DataFrame] = None,
    ) -> Dict[str, any]:
        """Apply stateful drawdown control with cooldown and HWM reset.

        GATE: STAGE6_3_DRAWDOWN_RE_ENTRY_20260616
        GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616

        Walks through daily returns sequentially, tracking NAV and drawdown.
        When drawdown breaches threshold, enters stop-out (cash) state for
        cooldown_days, then re-enters with optional HWM reset.

        When adaptive re-entry is enabled (GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616),
        cooldown duration is dynamically adjusted based on:
        - HMM bear probability: high p_bear extends cooldown
        - Trailing realized volatility: high vol extends cooldown
        Re-entry is gated: p_bear must drop below threshold AND vol must
        be within acceptable range before the strategy resumes.

        PIT Safety: uses ONLY realised test-fold returns (daily_series).
        No future data or train-period data is accessed.

        Parameters
        ----------
        daily_series : pd.Series
            Daily portfolio returns (index = date). Modified in-place.
        portfolio_returns : pd.Series
            Row-level portfolio returns. Modified in-place.
        aligned_df : pd.DataFrame
            Row-level aligned data with 'date' column.
        fold_id : int
            Current fold identifier.
        hmm_p_bear_dict : dict or None
            Mapping of date string -> HMM bear probability.
            GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616.
        close_wide : pd.DataFrame or None
            Wide-format close prices for trailing volatility computation.
            GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616.

        Returns
        -------
        dict
            Evidence dict with stop-out events, re-entry events, and config.
        """
        evidence = {
            "gate": DRAWDOWN_RE_ENTRY_GATE_ID,
            "enabled": True,
            "re_entry_enabled": self.drawdown_re_entry_enabled,
            "cooldown_days": self.drawdown_cooldown_days,
            "hwm_reset": self.drawdown_hwm_reset,
            "threshold": self.drawdown_threshold,
            "stop_out_events": [],
            "re_entry_events": [],
            "n_stop_outs": 0,
            "n_re_entries": 0,
            "total_cooldown_days": 0,
            "pit_safe": True,
            # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
            "adaptive_re_entry": self.drawdown_adaptive_re_entry,
            "adaptive_bear_threshold": self.drawdown_adaptive_bear_threshold,
            "adaptive_vol_window": self.drawdown_adaptive_vol_window,
            "adaptive_vol_multiplier": self.drawdown_adaptive_vol_multiplier,
            "adaptive_max_cooldown": self.drawdown_adaptive_max_cooldown,
            "adaptive_cooldown_extensions": 0,
            "adaptive_early_re_entries": 0,
            # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
            # Market regime re-entry filter: block re-entry when regime == 'bear'.
            # Initialized False; set True only after successful lazy import
            # of detect_market_regime AND close_wide is available.
            "regime_re_entry_filter_enabled": False,
            "regime_blocked_re_entries": 0,
        }

        # State machine: track NAV, HWM, stop-out/cooldown state
        nav = 1.0
        hwm = 1.0
        in_stop_out = False
        cooldown_remaining = 0
        stop_out_count = 0
        re_entry_count = 0
        total_cooldown = 0
        # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
        _adaptive_extensions = 0
        _adaptive_early_re_entries = 0
        # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616 — regime re-entry filter
        _regime_blocked_count = 0

        # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616 — regime re-entry filter
        # Lazy import detect_market_regime for PIT-safe regime check at re-entry
        _detect_regime_fn = None
        if self.drawdown_adaptive_re_entry and close_wide is not None:
            try:
                from omega.quant.walk_forward.risk_sizing_overlay import (
                    detect_market_regime as _detect_regime_fn,
                )
            except ImportError:
                logger.warning(
                    "Adaptive re-entry: detect_market_regime unavailable; "
                    "regime re-entry filter disabled for this fold."
                )
                _detect_regime_fn = None

        # Set regime_re_entry_filter_enabled to True only when both the
        # lazy import succeeded AND close_wide is available (PIT-safe).
        if _detect_regime_fn is not None and close_wide is not None:
            evidence["regime_re_entry_filter_enabled"] = True

        # Pre-compute market proxy returns for adaptive vol computation
        _mp_returns_series = None
        if self.drawdown_adaptive_re_entry and close_wide is not None:
            _mp = close_wide.mean(axis=1)
            _mp_ret = _mp.pct_change().dropna()
            _mp_returns_series = _mp_ret

        # Pre-compute date-to-row mapping for zeroing row-level returns
        if 'date_dt' not in aligned_df.columns:
            aligned_df['date_dt'] = pd.to_datetime(aligned_df['date'])

        for i, (date_idx, day_ret) in enumerate(daily_series.items()):
            if in_stop_out:
                # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
                # Adaptive cooldown: check HMM bear probability and volatility
                if self.drawdown_adaptive_re_entry:
                    _date_str = str(date_idx)[:10]
                    _current_p_bear = (
                        hmm_p_bear_dict.get(_date_str, 0.0)
                        if hmm_p_bear_dict is not None
                        else 0.0
                    )

                    # Compute trailing volatility ratio
                    _vol_ratio = 1.0
                    if _mp_returns_series is not None:
                        _trailing_idx = _mp_returns_series.index[
                            _mp_returns_series.index < date_idx
                        ]
                        if len(_trailing_idx) >= self.drawdown_adaptive_vol_window + 1:
                            _trail = _mp_returns_series.loc[
                                _trailing_idx[-self.drawdown_adaptive_vol_window:]
                            ]
                            _current_vol = float(_trail.std())
                            # Compute baseline vol from longer trailing window
                            _baseline_n = min(
                                self.drawdown_adaptive_vol_window * 3,
                                len(_trailing_idx),
                            )
                            _baseline = _mp_returns_series.loc[
                                _trailing_idx[-_baseline_n:]
                            ]
                            _baseline_vol = float(_baseline.std())
                            if _baseline_vol > 1e-9:
                                _vol_ratio = _current_vol / _baseline_vol

                    _bear_high = _current_p_bear >= self.drawdown_adaptive_bear_threshold
                    _vol_high = _vol_ratio >= self.drawdown_adaptive_vol_multiplier

                    if _bear_high or _vol_high:
                        # Regime unfavorable: extend cooldown by 1 day
                        cooldown_remaining += 1
                        _adaptive_extensions += 1
                        # Cap at max cooldown to prevent infinite extension
                        if total_cooldown + 1 >= self.drawdown_adaptive_max_cooldown:
                            # Force re-entry at max cooldown
                            cooldown_remaining = 1
                    elif cooldown_remaining > 1:
                        # Regime favorable: accelerate re-entry
                        # Reduce cooldown faster when conditions improve
                        cooldown_remaining = max(1, cooldown_remaining - 1)
                        _adaptive_early_re_entries += 1

                # In cooldown: zero this return
                daily_series.loc[date_idx] = 0.0
                # Zero row-level returns for this date
                row_mask = aligned_df['date_dt'] == pd.to_datetime(date_idx)
                portfolio_returns.loc[row_mask] = 0.0

                cooldown_remaining -= 1
                total_cooldown += 1

                if cooldown_remaining <= 0:
                    # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
                    # Market regime re-entry filter: block re-entry in bear regime.
                    # PIT-safe: detect_market_regime uses ONLY trailing data < dt.
                    _regime_blocked = False
                    if _detect_regime_fn is not None and close_wide is not None:
                        try:
                            _regime = _detect_regime_fn(
                                close_wide,
                                date_idx,
                                ma_window=self.risk_sizing_regime_ma_window,
                                vol_window=self.risk_sizing_regime_vol_window,
                                vol_median_window=self.risk_sizing_regime_vol_median_window,
                            )
                            if _regime == "bear":
                                # Bear regime: extend cooldown by 1 day, do not re-enter
                                _regime_blocked = True
                                cooldown_remaining = 1
                                _regime_blocked_count += 1
                                logger.info(
                                    f"Fold {fold_id}: Regime re-entry filter BLOCKED "
                                    f"re-entry at {date_idx} (regime=bear, "
                                    f"cooldown extended by 1d, "
                                    f"total blocked={_regime_blocked_count})"
                                )
                        except Exception as _regime_exc:
                            logger.warning(
                                f"Fold {fold_id}: Regime detection failed at "
                                f"{date_idx}: {_regime_exc}; proceeding with re-entry."
                            )

                    if not _regime_blocked:
                        # Cooldown expired and regime permits: re-enter
                        in_stop_out = False
                        re_entry_count += 1

                        # Optionally reset HWM to current NAV
                        if self.drawdown_hwm_reset:
                            hwm = nav  # Reset HWM to current NAV level

                        # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
                        _re_p_bear = 0.0
                        if hmm_p_bear_dict is not None:
                            _re_p_bear = hmm_p_bear_dict.get(str(date_idx)[:10], 0.0)

                        re_entry_ev = {
                            "re_entry_day_index": i,
                            "re_entry_date": str(date_idx),
                            "nav_at_re_entry": round(nav, 8),
                            "hwm_after_reset": round(hwm, 8),
                            "hwm_reset_applied": self.drawdown_hwm_reset,
                            # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
                            "p_bear_at_re_entry": round(_re_p_bear, 4),
                            "adaptive": self.drawdown_adaptive_re_entry,
                        }
                        evidence["re_entry_events"].append(re_entry_ev)

                        logger.info(
                            f"Fold {fold_id}: Drawdown re-entry at {date_idx} "
                            f"(NAV={nav:.6f}, HWM={'reset to' if self.drawdown_hwm_reset else 'kept at'} "
                            f"{hwm:.6f}"
                            f"{', p_bear=' + f'{_re_p_bear:.4f}' if self.drawdown_adaptive_re_entry else ''})"
                        )
                continue

            # Normal trading: update NAV
            nav = nav * (1.0 + day_ret)

            # Update high-water mark
            if nav > hwm:
                hwm = nav

            # Check drawdown against HWM
            current_dd = (nav - hwm) / hwm if hwm > 0 else 0.0

            if current_dd < -self.drawdown_threshold:
                # Breach: enter stop-out
                stop_out_count += 1

                stop_out_ev = {
                    "breach_day_index": i,
                    "breach_date": str(date_idx),
                    "nav_at_breach": round(nav, 8),
                    "hwm_at_breach": round(hwm, 8),
                    "drawdown_at_breach": round(current_dd, 6),
                    "cooldown_days": self.drawdown_cooldown_days,
                }
                evidence["stop_out_events"].append(stop_out_ev)

                logger.info(
                    f"Fold {fold_id}: Drawdown stop-out #{stop_out_count} at "
                    f"{date_idx} (DD={current_dd:.4f}, NAV={nav:.6f}, "
                    f"HWM={hwm:.6f}, cooldown={self.drawdown_cooldown_days}d)"
                )

                # If re-entry is disabled, zero all remaining returns and break
                if not self.drawdown_re_entry_enabled:
                    dates_after = daily_series.index > date_idx
                    daily_series.loc[dates_after] = 0.0
                    breach_dt = pd.to_datetime(date_idx)
                    indices_after = aligned_df[aligned_df['date_dt'] > breach_dt].index
                    portfolio_returns.loc[indices_after] = 0.0
                    remaining = int(dates_after.sum())
                    total_cooldown += remaining
                    break

                # If cooldown_days == 0, re-enter immediately (no cash days)
                if self.drawdown_cooldown_days == 0:
                    re_entry_count += 1
                    if self.drawdown_hwm_reset:
                        hwm = nav
                    re_entry_ev = {
                        "re_entry_day_index": i,
                        "re_entry_date": str(date_idx),
                        "nav_at_re_entry": round(nav, 8),
                        "hwm_after_reset": round(hwm, 8),
                        "hwm_reset_applied": self.drawdown_hwm_reset,
                    }
                    evidence["re_entry_events"].append(re_entry_ev)
                    logger.info(
                        f"Fold {fold_id}: Immediate re-entry (cooldown=0) at "
                        f"{date_idx} (NAV={nav:.6f}, HWM={hwm:.6f})"
                    )
                    # Do NOT set in_stop_out — continue trading next day
                    continue

                # Enter cooldown state for next iteration
                in_stop_out = True
                cooldown_remaining = self.drawdown_cooldown_days

        evidence["n_stop_outs"] = stop_out_count
        evidence["n_re_entries"] = re_entry_count
        evidence["total_cooldown_days"] = total_cooldown
        # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
        evidence["adaptive_cooldown_extensions"] = _adaptive_extensions
        evidence["adaptive_early_re_entries"] = _adaptive_early_re_entries
        # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616 — regime re-entry filter
        evidence["regime_blocked_re_entries"] = _regime_blocked_count

        return evidence

    def _compute_sequential_dynamic_freq(
        self,
        train_df: pd.DataFrame,
        available_test_df: pd.DataFrame,
        base_freq: int = 7,
    ) -> int:
        """Compute dynamic rebalance frequency for a specific point in time.
        
        P9 v4 (PIT-safe): Adjust rebalance frequency based on market volatility regime
        using only data available up to the decision point.
        
        - Compare CURRENT volatility (recent available data) vs HISTORICAL baseline (train period)
        - High volatility (current > 1.5x baseline): rebalance more often (freq=5)
        - Low volatility (current < 0.67x baseline): rebalance less often (freq=10)
        - Medium volatility: use base_freq (7)
        
        Parameters
        ----------
        train_df : pd.DataFrame
            Training period data with 'close' and 'date' columns (historical baseline)
        available_test_df : pd.DataFrame
            Test period data available up to (but not including) the decision date.
            Must contain only rows with date < decision_date for PIT safety.
        base_freq : int
            Default rebalance frequency
            
        Returns
        -------
        int
            Adjusted rebalance frequency
            
        Notes
        -----
        PIT safety: This function only uses train_df and available_test_df (strictly
        prior dates). The caller is responsible for filtering test_df to exclude
        current and future dates relative to the decision point.
        """
        # Guard: if train_df not provided, cannot compute baseline
        if train_df is None or train_df.empty:
            logger.warning("P9: train_df is None/empty, cannot compute baseline vol, using base_freq")
            return base_freq
        
        # Compute baseline volatility from TRAINING period (historical).
        # Sort first: pct_change is order-sensitive inside each ticker group.
        train_work = train_df.sort_values(['ticker', 'date'])
        train_returns = train_work.groupby('ticker')['close'].pct_change().clip(-0.5, 0.5)
        train_daily_vol = train_returns.groupby(train_work['date']).std()
        train_median_vol = train_daily_vol.median()
        
        if pd.isna(train_median_vol) or train_median_vol < 1e-9:
            logger.warning("P9: Cannot compute baseline volatility from train_df, using base_freq")
            return base_freq
        
        # Compute current volatility from AVAILABLE test data (strictly prior dates).
        # If no test data available yet (first OOS date), use train baseline only.
        if available_test_df is None or available_test_df.empty:
            # No OOS data available yet: use train median as current estimate
            current_vol = train_median_vol
            logger.debug("P9: No available test data, using train baseline as current vol")
        else:
            # Sort first: pct_change is order-sensitive inside each ticker group.
            # Clip like forward returns to avoid corporate-action/data jumps dominating regime.
            test_work = available_test_df.sort_values(['ticker', 'date'])
            test_returns = test_work.groupby('ticker')['close'].pct_change().clip(-0.5, 0.5)
            test_daily_vol = test_returns.groupby(test_work['date']).std()
            
            # Use recent 20-day rolling average for stability
            if len(test_daily_vol) >= 20:
                current_vol = test_daily_vol.rolling(window=20, min_periods=10).mean().iloc[-1]
            else:
                current_vol = test_daily_vol.median()
            
            if pd.isna(current_vol):
                current_vol = test_daily_vol.median()
            
            # Fallback to train baseline if still invalid
            if pd.isna(current_vol):
                current_vol = train_median_vol
                logger.debug("P9: Could not compute current vol from available test data, using train baseline")
        
        # Compare current vs baseline
        vol_ratio = current_vol / train_median_vol
        
        if vol_ratio > 1.5:
            # High volatility regime: rebalance more often
            adjusted_freq = max(5, base_freq - 2)
            regime = "HIGH"
        elif vol_ratio < 0.67:
            # Low volatility regime: rebalance less often
            adjusted_freq = min(10, base_freq + 3)
            regime = "LOW"
        else:
            # Medium volatility regime: use base frequency
            adjusted_freq = base_freq
            regime = "MEDIUM"
        
        logger.debug(
            f"P9 Sequential Dynamic: regime={regime}, current_vol={current_vol:.6f}, "
            f"baseline_vol={train_median_vol:.6f}, ratio={vol_ratio:.2f}, freq={base_freq}->{adjusted_freq}"
        )
        
        return adjusted_freq

    def _lookup_latest_dyn_universe_up_to(self, date_str: str) -> Optional[List[str]]:
        """Pure date-safe lookup of the latest dynamic universe schedule entry
        with key <= date_str.

        GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615 — cross-fold safety fix.

        Instead of persisting ``_last_dyn_universe`` across folds (which leaks
        state from fold N into fold N+1), this method performs a pure lookup
        from the immutable schedule dict.  It is safe to call from any fold
        without side effects.

        Parameters
        ----------
        date_str : str
            ISO date string (YYYY-MM-DD) representing the current rebalance date.

        Returns
        -------
        list of str or None
            Symbol list from the latest schedule entry with key <= date_str,
            or None when no such entry exists.
        """
        if not self.dynamic_universe_schedule:
            return None
        target = pd.Timestamp(date_str)
        best_key = None
        for sched_key in self.dynamic_universe_schedule:
            sched_ts = pd.Timestamp(sched_key)
            if sched_ts <= target:
                if best_key is None or sched_ts > pd.Timestamp(best_key):
                    best_key = sched_key
        if best_key is not None:
            return self.dynamic_universe_schedule[best_key]
        return None

    def _build_fold_dynamic_universe_evidence(
        self,
        test_df: pd.DataFrame,
    ) -> Optional[Dict[str, any]]:
        """Build per-fold dynamic universe evidence for audit persistence.

        GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615 — per-fold evidence fix.

        Collects which rebalance dates in the test fold had dynamic universe
        schedule entries, what symbols were eligible, and confirms PIT safety.

        Parameters
        ----------
        test_df : pd.DataFrame
            Test-set rows with 'date' column.

        Returns
        -------
        dict or None
            Per-fold evidence dict when dynamic universe is enabled, else None.
        """
        if self.dynamic_universe_schedule is None:
            return None

        test_dates = sorted(test_df['date'].unique())
        rebalance_dates_used = []
        carry_forward_dates_used = []

        for date in test_dates:
            date_str = str(pd.Timestamp(date).date())
            if date_str in self.dynamic_universe_schedule:
                rebalance_dates_used.append(date_str)
            else:
                carry = self._lookup_latest_dyn_universe_up_to(date_str)
                if carry is not None:
                    carry_forward_dates_used.append(date_str)

        return {
            "gate": "DYNAMIC_REBALANCE_UNIVERSE_20260615",
            "enabled": True,
            "schedule_size": len(self.dynamic_universe_schedule),
            "n_test_dates_with_exact_entry": len(rebalance_dates_used),
            "n_test_dates_with_carry_forward": len(carry_forward_dates_used),
            "rebalance_dates_in_fold": rebalance_dates_used[:10],
            "carry_forward_dates_sample": carry_forward_dates_used[:5],
            "pit_safe": True,
        }

    def _apply_stage2_constraints(
        self,
        test_df: pd.DataFrame,
        raw_signal: pd.Series,
        top_alphas: List[str],
        dynamic_rebalance: bool = False,
        train_df: Optional[pd.DataFrame] = None,
    ) -> pd.Series:
        """Apply Stage 2 behavioral constraints to the raw IC-weighted signal.

        Enforces in order:
          1. Top-N stock selection per rebalance date (nlargest on signal)
          2. Rebalance cadence (only recompute weights every rebalance_freq dates)
          3. Sector cap (delegate to alpha_pipeline._apply_sector_caps)

        Parameters
        ----------
        test_df : pd.DataFrame
            Test-set rows with columns 'date', 'ticker', and optionally 'sector'.
            Rows are in the same order as raw_signal.
        raw_signal : pd.Series
            IC-weighted combined signal, indexed identically to test_df.index.
        top_alphas : list of str
            Selected alpha column names (used only for logging context).
        dynamic_rebalance : bool
            If True, adjust rebalance frequency based on market volatility regime.
            P9 v4: Uses sequential PIT-safe frequency computation.
        train_df : pd.DataFrame, optional
            Training data for baseline volatility computation (P9 dynamic rebalance).

        Returns
        -------
        pd.Series
            Per-row portfolio weight Series, same index as raw_signal.
            Sums to ~1.0 across tickers on each date (after sector cap renorm).

        Notes
        -----
        PIT safety: test_df signals are already T-1 lagged by compute_alphas().
        P9 v4: Dynamic rebalance frequency is computed sequentially per rebalance
        checkpoint using only train_df + strictly prior test dates.
        """
        top_n = self.top_n_stocks
        sector_cap = self.sector_cap_pct

        # Attach raw signal to a working frame aligned by position
        work = test_df[['date', 'ticker']].copy().reset_index(drop=True)
        work['_signal'] = raw_signal.values

        # Build sector_map from 'sector' column if present
        if 'sector' in test_df.columns:
            sector_map: Dict[str, str] = (
                test_df[['ticker', 'sector']]
                .drop_duplicates('ticker')
                .set_index('ticker')['sector']
                .to_dict()
            )
        else:
            # No sector metadata: each ticker is its own sector (cap has no effect)
            sector_map = {t: t for t in work['ticker'].unique()}

        all_sectors = set(sector_map.values())
        resolved_caps: Dict[str, float] = {s: sector_cap for s in all_sectors}

        # Sorted unique dates in test fold (chronological)
        sorted_dates = sorted(work['date'].unique())

        # Build wide signal matrix: rows=dates, cols=tickers
        signal_wide = work.pivot_table(
            index='date', columns='ticker', values='_signal', aggfunc='first'
        )

        # Weight matrix (same shape, filled with 0)
        weight_wide = pd.DataFrame(
            0.0, index=signal_wide.index, columns=signal_wide.columns
        )

        last_weights: Optional[pd.Series] = None
        apply_sector_caps = _import_apply_sector_caps()
        
        # P9 v4 fix: Track current rebalance frequency (updated sequentially at checkpoints)
        # Drive both frequency recompute and rebalance eligibility from elapsed distance
        current_rebal_freq = self.rebalance_freq
        last_rebal_checkpoint_idx = None

        for idx, date in enumerate(sorted_dates):
            if date not in signal_wide.index:
                continue

            # P9 v4 fix: Determine if we should rebalance at this date FIRST
            # Use elapsed distance from last actual checkpoint
            if last_rebal_checkpoint_idx is None:
                # First checkpoint: always rebalance
                should_rebalance = (idx == 0)
            else:
                # Check if enough dates have passed since last checkpoint
                elapsed = idx - last_rebal_checkpoint_idx
                should_rebalance = (elapsed >= current_rebal_freq)

            if should_rebalance:
                # P9 v4 fix: At rebalance dates, recompute frequency using PIT-safe data
                # BEFORE executing rebalance, so new frequency applies to NEXT interval
                if dynamic_rebalance:
                    # Use only data available strictly BEFORE this date (train_df + prior test dates)
                    # This ensures no lookahead: decision at date D uses data < D only
                    available_test = test_df[test_df['date'] < date]
                    current_rebal_freq = self._compute_sequential_dynamic_freq(
                        train_df, available_test, self.rebalance_freq
                    )
                    logger.debug(
                        f"P9 v4: Rebalance at idx={idx}, date={date}, "
                        f"updated freq to {current_rebal_freq} for next interval"
                    )
                
                # Execute rebalance: select top-N by signal, build equal-weight, apply sector cap
                alpha_row = signal_wide.loc[date].dropna()

                # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615
                # Restrict eligible symbols to dynamic universe for this date
                if self.dynamic_universe_schedule is not None:
                    date_str = str(pd.Timestamp(date).date())
                    eligible = self.dynamic_universe_schedule.get(date_str)
                    if eligible is not None:
                        eligible_set = set(eligible)
                        alpha_row = alpha_row[alpha_row.index.isin(eligible_set)]
                    else:
                        # No exact entry for this date — use pure date-safe lookup
                        # of the latest schedule date strictly <= current date.
                        # This eliminates unsafe cross-fold carry-forward state:
                        # no _last_dyn_universe instance attribute is consulted.
                        _carry_eligible = self._lookup_latest_dyn_universe_up_to(date_str)
                        if _carry_eligible is not None:
                            alpha_row = alpha_row[
                                alpha_row.index.isin(set(_carry_eligible))
                            ]

                if len(alpha_row) > 0:
                    top_stocks = alpha_row.nlargest(min(top_n, len(alpha_row)))
                    target = pd.Series(0.0, index=signal_wide.columns)
                    target[top_stocks.index] = 1.0 / len(top_stocks)
                    # Apply sector caps (reuse alpha_pipeline logic, no duplication)
                    target = apply_sector_caps(target, sector_map, resolved_caps)
                    last_weights = target
                
                # Update checkpoint tracker AFTER rebalance
                last_rebal_checkpoint_idx = idx

            if last_weights is not None:
                weight_wide.loc[date] = last_weights

        # Log final applied frequency (may have changed during fold)
        logger.info(
            f"Stage 2 constraints applied: top_n={top_n}, "
            f"final_rebal_freq={current_rebal_freq}, sector_cap={sector_cap:.0%}, "
            f"alphas={top_alphas}, dynamic={'YES' if dynamic_rebalance else 'NO'}"
        )

        # Flatten back to per-row Series aligned with original test_df index
        work_with_weights = work.merge(
            weight_wide.stack().rename('_weight').reset_index().rename(
                columns={'ticker': 'ticker', 'date': 'date'}
            ),
            on=['date', 'ticker'],
            how='left',
        )
        result = work_with_weights['_weight'].fillna(0.0)
        result.index = raw_signal.index
        return result

    def _compute_horizon_signal(
        self,
        fold_id: int,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        alpha_cols: List[str],
        return_col: str,
        horizon: int,
        cost_aware: bool,
        final_objective_return_col: str = 'fwd_ret_5',
    ) -> Tuple[Optional[pd.Series], Dict[str, float], List[str], Dict[str, dict]]:
        """Compute raw signal for a single horizon without Stage 2 constraints.
        
        P10: Helper for multi-horizon blending. Computes IC, gates alphas,
        and produces raw portfolio signal for one return horizon.
        
        Parameters
        ----------
        fold_id : int
            Fold identifier (for logging)
        train_df : pd.DataFrame
            Training data with alphas already computed
        test_df : pd.DataFrame
            Test data with alphas already computed
        alpha_cols : list of str
            Alpha column names
        return_col : str
            Forward return column for this horizon (e.g., 'fwd_ret_1')
        horizon : int
            Horizon length in days (e.g., 1, 3, 5)
        cost_aware : bool
            If True, apply cost-aware alpha selection
        final_objective_return_col : str
            Final objective return column (usually 'fwd_ret_5') for measuring
            contribution to final monetization target
            
        Returns
        -------
        raw_signal : pd.Series or None
            Raw portfolio signal (no Stage 2 constraints), or None if horizon fails
        quality_metrics : dict
            Quality metrics with keys: 'train_ic', 'validation_ic', 
            'final_objective_validation_ic', 'own_target_train_ic', 'own_target_validation_ic'
        gated_alphas : list of str
            Alphas that passed research gate for this horizon
        gate_results : dict
            Research gate results per alpha
            
        Notes
        -----
        PIT Safety: Applies horizon-specific embargo (last h rows per ticker).
        No Stage 2 constraints applied here (caller applies after blending).
        
        Gate Failure Detection: If all alphas fail the research gate (all gate
        results are False), this horizon is excluded (returns None) even if
        validate_alpha_with_research_gate() falls back to top_alphas.
        """
        logger.info(f"[P10] Computing horizon signal: fold={fold_id}, horizon={horizon}, return_col={return_col}")
        
        # Initialize empty quality metrics
        quality_metrics = {
            'train_ic': 0.0,
            'validation_ic': 0.0,
            'final_objective_validation_ic': 0.0,
            'own_target_train_ic': 0.0,
            'own_target_validation_ic': 0.0,
        }
        
        # Check if return_col exists in data
        if return_col not in train_df.columns or return_col not in test_df.columns:
            logger.warning(f"[P10] Return column {return_col} not found, skipping horizon {horizon}")
            empty_gate_metadata = {
                'selection_source': 'excluded',
                'exclusion_reason': 'return_col_not_found',
                'used_fallback_candidates': False,
                'gate_passed_count': 0,
                'gate_total': 0,
                'gate_required_passes': self.p10_gate_min_pass,
                'gate_mode': self.p10_gate_mode,
                'gate_passed_alphas': [],
            }
            return None, quality_metrics, [], {}, empty_gate_metadata
        
        # Horizon-specific embargo: drop last h rows per ticker from train IC computation
        _tail_rank = train_df.groupby('ticker').cumcount(ascending=False)
        train_df_clean = train_df[_tail_rank >= horizon].reset_index(drop=True)
        logger.info(
            f"[P10] Horizon {horizon} embargo: "
            f"train rows before={len(train_df)}, after={len(train_df_clean)}"
        )
        
        if len(train_df_clean) < 10:
            logger.warning(f"[P10] Insufficient train data after embargo for horizon {horizon}")
            empty_gate_metadata = {
                'selection_source': 'excluded',
                'exclusion_reason': 'insufficient_train_data',
                'used_fallback_candidates': False,
                'gate_passed_count': 0,
                'gate_total': 0,
                'gate_required_passes': self.p10_gate_min_pass,
                'gate_mode': self.p10_gate_mode,
                'gate_passed_alphas': [],
            }
            return None, quality_metrics, [], {}, empty_gate_metadata
        
        # Split into train_actual and validation for IC computation
        unique_dates = sorted(train_df_clean['date'].unique())
        if len(unique_dates) >= 3:
            split_idx = int(len(unique_dates) * 2 / 3)
            val_start_date = unique_dates[split_idx]
            train_actual = train_df_clean[train_df_clean['date'] < val_start_date].reset_index(drop=True)
            val_actual = train_df_clean[train_df_clean['date'] >= val_start_date].reset_index(drop=True)
        else:
            train_actual = train_df_clean
            val_actual = train_df_clean
        
        # Compute IC on train_actual using this horizon's return column
        train_ics = self.compute_alpha_ics(train_actual, alpha_cols, return_col)
        
        # Strategy filter: momentum only keeps positive IC alphas
        if hasattr(self, "strategy") and self.strategy == "momentum":
            train_ics = {k: v for k, v in train_ics.items() if v > 0.0}
        
        logger.info(f"[P10] Horizon {horizon} train ICs: {train_ics}")
        
        # GATE: RISK_ADJUSTED_ALPHA_SELECTION_FIX1_20260614 — init for evidence capture
        _horizon_ra_result = None

        # GATE: RISK_ADJUSTED_ALPHA_SELECTION_20260614 — opt-in composite scoring
        # GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614 — portfolio guard for horizon
        _horizon_pg_result = None
        if self.risk_adjusted_alpha_selection:
            # Compute baseline alphas for portfolio guard comparison
            _horizon_baseline_alphas = None
            if self.portfolio_guard_enabled:
                if cost_aware:
                    _h_bl_adj = self.adjust_alphas_for_cost(
                        train_actual, alpha_cols, train_ics
                    )
                    _horizon_baseline_alphas = self.select_top_alphas(_h_bl_adj)
                else:
                    _horizon_baseline_alphas = self.select_top_alphas(train_ics)

            _horizon_ra_result = self.risk_adjusted_select(
                alpha_cols,
                train_df=train_actual,
                val_df=val_actual,
                train_ics=train_ics,
                return_col=return_col,
            )
            ra_result = _horizon_ra_result
            if ra_result.selected_alphas:
                top_alphas = ra_result.selected_alphas
            else:
                # Fallback to default selection if risk-adjusted yields nothing
                logger.warning("[RiskAdj] No alphas selected, falling back to default")
                if cost_aware:
                    adjusted_ics = self.adjust_alphas_for_cost(train_actual, alpha_cols, train_ics)
                    top_alphas = self.select_top_alphas(adjusted_ics)
                else:
                    top_alphas = self.select_top_alphas(train_ics)

            # GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614
            if self.portfolio_guard_enabled and ra_result.selected_alphas:
                from omega.quant.walk_forward.risk_adjusted_alpha_score import (
                    evaluate_portfolio_guard,
                )
                _horizon_pg_result = evaluate_portfolio_guard(
                    ra_result,
                    val_df=val_actual,
                    train_ics=train_ics,
                    return_col=return_col,
                    baseline_alpha_cols=_horizon_baseline_alphas,
                    underperformance_tolerance=self.portfolio_guard_tolerance,
                )
                if _horizon_pg_result.portfolio_guard_status == "FALLBACK_TO_BASELINE":
                    logger.warning(
                        f"[PortfolioGuard][H{horizon}] Fallback to baseline: "
                        f"{_horizon_pg_result.guard_reason}"
                    )
                    if _horizon_baseline_alphas:
                        top_alphas = _horizon_baseline_alphas
                    # Clear ra_result so evidence reflects fallback
                    _horizon_ra_result = None
                    ra_result = None
                else:
                    logger.info(
                        f"[PortfolioGuard][H{horizon}] ACCEPTED: "
                        f"{_horizon_pg_result.guard_reason}"
                    )
        # Cost-aware alpha selection if enabled
        elif cost_aware:
            adjusted_ics = self.adjust_alphas_for_cost(train_actual, alpha_cols, train_ics)
            top_alphas = self.select_top_alphas(adjusted_ics)
        else:
            top_alphas = self.select_top_alphas(train_ics)
        
        # Research gate validation using validation set
        gated_alphas, gate_results = self.validate_alpha_with_research_gate(
            top_alphas=top_alphas,
            train_ics=train_ics,
            train_df_clean=val_actual,
            return_col=return_col,
        )
        
        # FIX 2 + P10 Gate Tuning: Check horizon eligibility based on gate mode
        # Use robust verdict checker to avoid truthiness bugs (P10 hotfix 2026-06-09)
        gate_passed_count = sum(1 for res in gate_results.values() if _is_gate_verdict_pass(res.get('verdict')))
        
        # P10 Gate Tuning: Determine if horizon should be excluded based on gate mode
        horizon_excluded = False
        used_fallback_candidates = False
        exclusion_reason = None
        
        if self.p10_gate_mode == "strict":
            # Strict mode: exclude if no gates passed (current behavior)
            if gate_passed_count == 0:
                horizon_excluded = True
                exclusion_reason = "strict_mode_zero_passes"
        elif self.p10_gate_mode == "relaxed":
            # Relaxed mode: check if horizon meets relaxed eligibility criteria
            meets_min_pass = gate_passed_count >= self.p10_gate_min_pass
            has_fallback_candidates = (
                self.p10_gate_allow_fallback_candidates 
                and len(top_alphas) > 0
            )
            
            if meets_min_pass:
                # Horizon passes minimum gate threshold
                horizon_excluded = False
            elif has_fallback_candidates:
                # Horizon allowed via fallback candidates
                horizon_excluded = False
                used_fallback_candidates = True
                logger.info(
                    f"[P10] Horizon {horizon} relaxed gate: using fallback candidates "
                    f"(gate_passed={gate_passed_count}/{self.p10_gate_min_pass}, "
                    f"top_alphas={len(top_alphas)})"
                )
            else:
                # Horizon does not meet any eligibility criteria
                horizon_excluded = True
                exclusion_reason = "relaxed_mode_insufficient_passes_no_fallback"
        
        # Log comprehensive gate diagnostics
        logger.info(
            f"[P10] Horizon {horizon} gate diagnostics: "
            f"mode={self.p10_gate_mode}, "
            f"passed={gate_passed_count}/{len(gate_results)}, "
            f"required={self.p10_gate_min_pass}, "
            f"fallback_enabled={self.p10_gate_allow_fallback_candidates}, "
            f"used_fallback={used_fallback_candidates}, "
            f"excluded={horizon_excluded}"
        )
        
        if horizon_excluded:
            logger.warning(
                f"[P10] Research gate excluded horizon {horizon}: "
                f"reason={exclusion_reason}, "
                f"gate_passed={gate_passed_count}/{len(gate_results)}"
            )
            # Build gate_metadata for excluded horizon
            gate_passed_alphas = [
                alpha for alpha, res in gate_results.items() 
                if _is_gate_verdict_pass(res.get('verdict'))
            ]
            excluded_gate_metadata = {
                'selection_source': 'excluded',
                'exclusion_reason': exclusion_reason,
                'used_fallback_candidates': False,
                'gate_passed_count': gate_passed_count,
                'gate_total': len(gate_results),
                'gate_required_passes': self.p10_gate_min_pass,
                'gate_mode': self.p10_gate_mode,
                'gate_passed_alphas': gate_passed_alphas,
            }
            return None, quality_metrics, [], gate_results, excluded_gate_metadata
        
        if len(gated_alphas) == 0:
            logger.warning(f"[P10] No alphas passed gate for horizon {horizon}")
            # Build gate_metadata for no-alphas case
            no_alphas_gate_metadata = {
                'selection_source': 'excluded',
                'exclusion_reason': 'no_alphas_passed_gate',
                'used_fallback_candidates': False,
                'gate_passed_count': gate_passed_count,
                'gate_total': len(gate_results),
                'gate_required_passes': self.p10_gate_min_pass,
                'gate_mode': self.p10_gate_mode,
                'gate_passed_alphas': [],
            }
            return None, quality_metrics, [], gate_results, no_alphas_gate_metadata
        
        # Compute raw portfolio signal (IC-weighted, no XGBoost for multi-horizon)
        # XGBoost is disabled in multi-horizon mode to keep implementation simple
        portfolio_signal = self.compute_portfolio_signal(test_df, gated_alphas, train_ics)
        
        # Z-score normalize signal (cross-sectional per date)
        test_df_copy = test_df.copy()
        test_df_copy['_signal'] = portfolio_signal
        test_df_copy['_signal'] = test_df_copy.groupby('date')['_signal'].transform(
            lambda x: (x - x.mean()) / (x.std() + 1e-9)
        )
        portfolio_signal = test_df_copy['_signal']
        
        # FIX 1 & 5: Compute comprehensive quality metrics
        # Own-target train IC
        train_signal = self.compute_portfolio_signal(train_actual, gated_alphas, train_ics)
        own_target_train_ic = self.compute_ic(train_signal, train_actual[return_col]) if return_col in train_actual.columns else 0.0
        
        # Own-target validation IC
        val_signal = self.compute_portfolio_signal(val_actual, gated_alphas, train_ics)
        own_target_validation_ic = self.compute_ic(val_signal, val_actual[return_col]) if return_col in val_actual.columns else 0.0
        
        # Final objective train IC (contribution to final monetization target on train set)
        final_objective_train_ic = 0.0
        if final_objective_return_col in train_actual.columns:
            final_objective_train_ic = self.compute_ic(train_signal, train_actual[final_objective_return_col])
        
        # Final objective validation IC (contribution to final monetization target)
        final_objective_validation_ic = 0.0
        if final_objective_return_col in val_actual.columns:
            final_objective_validation_ic = self.compute_ic(val_signal, val_actual[final_objective_return_col])
        
        # Populate quality metrics dict
        # FIX P10 Role21 Re-Audit: train_ic and validation_ic must align to final objective return_col
        quality_metrics = {
            'train_ic': final_objective_train_ic,  # Use final-objective IC for weighting
            'validation_ic': final_objective_validation_ic,  # Use final-objective IC for weighting
            'final_objective_train_ic': final_objective_train_ic,
            'final_objective_validation_ic': final_objective_validation_ic,
            'own_target_train_ic': own_target_train_ic,
            'own_target_validation_ic': own_target_validation_ic,
        }
        
        # P10 Gate Tuning Role21 Fix: Build structured gate metadata
        # Extract alphas that actually passed the gate (not fallback candidates)
        gate_passed_alphas = [
            alpha for alpha, res in gate_results.items() 
            if _is_gate_verdict_pass(res.get('verdict'))
        ]
        
        # Determine selection source
        selection_source = "fallback_candidate" if used_fallback_candidates else "research_gate"
        
        gate_metadata = {
            'selection_source': selection_source,
            'used_fallback_candidates': used_fallback_candidates,
            'gate_passed_count': gate_passed_count,
            'gate_total': len(gate_results),
            'gate_required_passes': self.p10_gate_min_pass,
            'gate_mode': self.p10_gate_mode,
            'gate_passed_alphas': gate_passed_alphas,
            # GATE: RISK_ADJUSTED_ALPHA_SELECTION_FIX1_20260614
            'risk_adjusted_evidence': (
                _horizon_ra_result.to_dict() if _horizon_ra_result is not None else None
            ),
            # GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614
            'portfolio_guard_evidence': (
                _horizon_pg_result.to_dict() if _horizon_pg_result is not None else None
            ),
        }
        
        logger.info(
            f"[P10] Horizon {horizon} complete: "
            f"gated_alphas={len(gated_alphas)}, "
            f"own_val_ic={own_target_validation_ic:.4f}, "
            f"final_obj_val_ic={final_objective_validation_ic:.4f}, "
            f"gate_passed={gate_passed_count}/{len(gate_results)}, "
            f"selection_source={selection_source}"
        )
        
        return portfolio_signal, quality_metrics, gated_alphas, gate_results, gate_metadata
    
    def _blend_horizon_signals(
        self,
        horizon_results: Dict[int, Tuple[pd.Series, Dict[str, float]]],
        method: str = "validation_ic",
    ) -> Optional[pd.Series]:
        """Blend signals from multiple horizons using quality-based weights.
        
        P10: Combines horizon-specific signals into a single blended signal.
        
        Parameters
        ----------
        horizon_results : dict
            Mapping of horizon -> (signal, quality_metrics).
            signal is a pd.Series, quality_metrics is a dict with 'train_ic', 'validation_ic', etc.
        method : str
            Weight computation method ('validation_ic' or 'train_ic')
            
        Returns
        -------
        pd.Series or None
            Blended signal (same index as input signals), or None if all horizons have
            non-positive quality (triggering fallback to baseline)
            
        Notes
        -----
        PIT Safety: quality_metrics must be computed from train/validation only,
        never from test period. Caller is responsible for ensuring this.
        
        FIX 4: Negative or zero quality => weight 0 (no abs() weighting).
        If all horizons have non-positive quality, returns None to trigger fallback.
        If only one horizon succeeds, returns that signal directly.
        """
        logger.info(f"[P10] Blending {len(horizon_results)} horizon signals using method={method}")
        
        # Validate method parameter
        valid_methods = ['validation_ic', 'train_ic']
        if method not in valid_methods:
            logger.warning(f"[P10] Invalid blend_weight_method='{method}', defaulting to 'validation_ic'")
            method = 'validation_ic'
        
        # Filter out failed horizons (None signal or missing quality metrics)
        valid_horizons = {}
        for h, (sig, qual_dict) in horizon_results.items():
            if sig is None or qual_dict is None:
                continue
            if not isinstance(qual_dict, dict):
                logger.warning(f"[P10] Horizon {h} has invalid quality_metrics type, skipping")
                continue
            valid_horizons[h] = (sig, qual_dict)
        
        if len(valid_horizons) == 0:
            logger.error("[P10] All horizons failed, returning None to trigger fallback")
            return None
        
        # FIX P10 Role21 Re-Audit: Single horizon must also pass non-positive quality check
        if len(valid_horizons) == 1:
            h, (sig, qual_dict) = list(valid_horizons.items())[0]
            quality_val = qual_dict.get(method, 0.0)
            if quality_val <= 0:
                logger.warning(
                    f"[P10] Only horizon {h} succeeded but {method}={quality_val:.4f} is non-positive, "
                    "returning None to trigger fallback to baseline"
                )
                return None
            logger.info(f"[P10] Only horizon {h} succeeded, using it directly ({method}={quality_val:.4f})")
            return sig
        
        # FIX 1 & 4: Extract quality metrics using specified method
        # Use signed quality - negative IC => weight 0
        qualities = []
        for h, (sig, qual_dict) in valid_horizons.items():
            quality_val = qual_dict.get(method, 0.0)
            # FIX 4: Negative or zero quality => 0 weight (no abs())
            if quality_val <= 0:
                quality_val = 0.0
                logger.info(f"[P10] Horizon {h}: {method}={qual_dict.get(method, 0.0):.4f} (non-positive, weight=0)")
            qualities.append(quality_val)
        
        qualities = np.array(qualities)
        
        # FIX 4: If all qualities are non-positive, return None to trigger fallback
        if qualities.sum() <= 1e-9:
            logger.warning(
                f"[P10] All quality metrics non-positive using method={method}, "
                "returning None to trigger fallback to baseline"
            )
            return None
        
        # Normalize weights to sum to 1 (only positive qualities remain)
        weights = qualities / qualities.sum()
        
        # Blend signals
        signals = [sig for _, (sig, _) in valid_horizons.items()]
        horizons_list = list(valid_horizons.keys())
        
        # Align all signals to same index (use first signal's index as reference)
        ref_index = signals[0].index
        blended = pd.Series(0.0, index=ref_index)
        
        for i, (h, weight) in enumerate(zip(horizons_list, weights)):
            sig = signals[i].reindex(ref_index, fill_value=0.0)
            blended += weight * sig
            qual_dict = valid_horizons[h][1]
            logger.info(
                f"[P10] Horizon {h}: weight={weight:.4f}, "
                f"{method}={qual_dict.get(method, 0.0):.4f}"
            )
        
        logger.info(f"[P10] Blend complete: {len([w for w in weights if w > 0])} horizons combined")
        return blended

    def run_fold(
        self,
        fold_id: int,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        alpha_cols: List[str],
        return_col: str = 'fwd_ret_5',
        cost_aware: bool | None = None,
    ) -> FoldMetrics:
        """Run single walk-forward fold.
        
        Parameters
        ----------
        fold_id : int
            Fold identifier
        train_df : pd.DataFrame
            Training data
        test_df : pd.DataFrame
            Testing data
        alpha_cols : list of str
            Alpha column names
        return_col : str
            Forward return column name
        cost_aware : bool, optional
            If True, cost-aware alpha selection is enabled for this fold.
            If None, uses self.cost_aware.
        
        Returns
        -------
        FoldMetrics
            Fold results
        
        Notes
        -----
        Embargo logic (PIT Safety): For a return_col of the form 'fwd_ret_N',
        the last N rows per symbol are dropped from train_df before IC
        computation and alpha selection. This prevents label leakage where
        the forward return window of the final training rows overlaps with
        the test period. Alpha computation (feature generation) uses the
        full train_df so that indicators at the boundary are not distorted.
        """
        logger.info(f"Running fold {fold_id}")

        if cost_aware is None:
            cost_aware = self.cost_aware

        # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615 — defensive reset.
        # Remove any stale _last_dyn_universe from a prior fold so that
        # carry-forward state can never leak across folds.  The new
        # _lookup_latest_dyn_universe_up_to() is the authoritative path.
        if hasattr(self, '_last_dyn_universe'):
            del self._last_dyn_universe
        
        # Compute alphas on train (full train_df — no embargo yet)
        train_df = self.compute_alphas(train_df)

        # --- Cold-start fix: prepend train tail to test_df for alpha computation ---
        # Phase34 uses rolling windows (5, 10, 20 bars). Without train history,
        # the first ~20 test days get NaN/zero-fill distortion.
        # PIT safe: we only prepend already-embargoed train data, then strip it back.
        warmup_n = 30  # rows per symbol to prepend (covers max rolling window)
        train_tail = (
            train_df
            .groupby('ticker', group_keys=False)
            .tail(warmup_n)
            .copy()
        )
        # Mark original test rows so we can strip warmup back after alpha computation
        is_test_mask = pd.Series(True, index=test_df.index)
        test_df = test_df.copy()
        test_df['_is_test'] = True
        test_with_warmup = pd.concat([train_tail, test_df], ignore_index=True)
        test_with_warmup = test_with_warmup.sort_values(
            ['ticker', 'date'], ignore_index=True
        )
        test_with_warmup = self.compute_alphas(test_with_warmup)
        # Strip warmup rows — keep only original test rows
        keep_mask = test_with_warmup['_is_test'].fillna(False).astype(bool)
        test_df = (
            test_with_warmup.loc[keep_mask]
            .drop(columns=['_is_test'], errors='ignore')
            .reset_index(drop=True)
        )
        
        # GATE: RISK_ADJUSTED_ALPHA_SELECTION_FIX1_20260614 — init for both paths
        ra_result = None
        # GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614 — init for both paths
        _portfolio_guard_result = None
        # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614 — init for both paths
        _winner_guard_evidence = None
        # GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — init for both paths
        _diversified_basket_evidence = None
        # GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616 — init for both paths
        _oos_stability_evidence = None

        # ==============================================================================
        # P10: Multi-Horizon Blending Path (opt-in)
        # ==============================================================================
        if self.multi_horizon_blend:
            logger.info(
                f"[P10] Fold {fold_id}: Multi-horizon blending enabled, "
                f"horizons={self.blend_horizons}, method={self.blend_weight_method}"
            )
            
            horizon_results = {}
            horizon_details = {}
            
            # Compute signal for each horizon independently
            for horizon in self.blend_horizons:
                horizon_return_col = f'fwd_ret_{horizon}'
                
                # FIX 1, 2, 5: Updated signature with quality_metrics dict and final_objective_return_col
                # Role21 Fix 2026-06-10: Now returns gate_metadata as 5th value
                signal, quality_metrics, gated, gate_res, gate_meta = self._compute_horizon_signal(
                    fold_id=fold_id,
                    train_df=train_df,
                    test_df=test_df,
                    alpha_cols=alpha_cols,
                    return_col=horizon_return_col,
                    horizon=horizon,
                    cost_aware=cost_aware,
                    final_objective_return_col=return_col,  # FIX 5: final objective alignment
                )
                
                if signal is not None:
                    horizon_results[horizon] = (signal, quality_metrics)
                    # FIX 6: Store comprehensive diagnostics
                    # Role21 Fix 2026-06-10: Added gate_metadata to horizon_details
                    horizon_details[horizon] = {
                        'gated_alphas': gated,
                        'gate_results': gate_res,
                        'quality_metrics': quality_metrics,
                        'horizon_return_col': horizon_return_col,
                        'included': True,
                        'gate_metadata': gate_meta,
                    }
                else:
                    # FIX 6: Track excluded horizons in diagnostics
                    # Role21 Fix 2026-06-10: Added gate_metadata to horizon_details
                    horizon_details[horizon] = {
                        'gated_alphas': [],
                        'gate_results': gate_res,
                        'quality_metrics': quality_metrics,
                        'horizon_return_col': horizon_return_col,
                        'included': False,
                        'exclusion_reason': gate_meta.get('exclusion_reason', 'gate_failed_or_missing_data') if gate_meta else 'gate_failed_or_missing_data',
                        'gate_metadata': gate_meta,
                    }
            
            # FIX 3: All-horizon failure fallback to single-horizon baseline
            portfolio_signal = None
            fallback_used = False
            fallback_reason = None
            
            if len(horizon_results) == 0:
                fallback_reason = "all_horizons_failed_or_missing"
                logger.warning(
                    f"[P10] Fold {fold_id}: All requested horizons failed/missing. "
                    f"Falling back to single-horizon baseline using return_col={return_col}"
                )
                fallback_used = True
            else:
                # Attempt to blend
                portfolio_signal = self._blend_horizon_signals(
                    horizon_results, method=self.blend_weight_method
                )
                
                # FIX 3 & 4: If blend returns None (all non-positive quality), fallback
                if portfolio_signal is None:
                    fallback_reason = "all_quality_non_positive"
                    logger.warning(
                        f"[P10] Fold {fold_id}: Blend returned None (all quality non-positive). "
                        f"Falling back to single-horizon baseline using return_col={return_col}"
                    )
                    fallback_used = True
            
            # FIX 3: Execute fallback to approved single-horizon baseline
            if fallback_used:
                logger.info(
                    f"[P10] Fold {fold_id}: Executing fallback to single-horizon baseline "
                    f"(return_col={return_col})"
                )
                # Fall through to the standard single-horizon path below
                # by setting multi_horizon_blend to False temporarily
                self.multi_horizon_blend = False
                # Recursively call run_fold with single-horizon mode
                # (This ensures we use the exact same baseline logic)
                result = self.run_fold(
                    fold_id=fold_id,
                    train_df=train_df,
                    test_df=test_df,
                    alpha_cols=alpha_cols,
                    return_col=return_col,
                    cost_aware=cost_aware,
                )
                # Restore multi_horizon_blend flag
                self.multi_horizon_blend = True
                # Add fallback diagnostic to result
                # (FoldMetrics doesn't have a diagnostics field, so log it)
                logger.info(
                    f"[P10] Fold {fold_id}: Fallback complete. "
                    f"Reason: {fallback_reason}, "
                    f"Requested horizons: {self.blend_horizons}, "
                    f"Successful horizons: {list(horizon_results.keys())}"
                )
                return result
            
            # Normal multi-horizon path (blend succeeded)
            # For FoldMetrics reporting: use first successful horizon's details
            # (FoldMetrics doesn't yet support per-horizon reporting)
            # Role21 Fix 2026-06-10: Also extract gate_metadata
            # Role20 P10 Fix 2026-06-10: Use first included horizon, not first requested
            # horizon_results only contains successful horizons where signal != None
            first_horizon = list(horizon_results.keys())[0]
            gated_alphas = horizon_details[first_horizon]['gated_alphas']
            gate_results = horizon_details[first_horizon]['gate_results']
            gate_metadata = horizon_details[first_horizon].get('gate_metadata', None)

            # GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614 — extract from multi-horizon
            if isinstance(gate_metadata, dict) and gate_metadata.get('portfolio_guard_evidence'):
                from omega.quant.walk_forward.risk_adjusted_alpha_score import PortfolioGuardResult
                _pg_ev = gate_metadata['portfolio_guard_evidence']
                _portfolio_guard_result = PortfolioGuardResult(
                    portfolio_guard_enabled=_pg_ev.get('portfolio_guard_enabled', True),
                    portfolio_guard_status=_pg_ev.get('portfolio_guard_status', 'ACCEPTED'),
                    selected_basket_validation_ic=_pg_ev.get('selected_basket_validation_ic', 0.0),
                    baseline_basket_validation_ic=_pg_ev.get('baseline_basket_validation_ic'),
                    guard_reason=_pg_ev.get('guard_reason', ''),
                    selected_alphas=_pg_ev.get('selected_alphas', []),
                    rejected_risk_adjusted_evidence=_pg_ev.get('rejected_risk_adjusted_evidence'),
                )
            
            # Compute raw signal IC using default return_col (for P9 comparison)
            raw_signal_ic = self.compute_ic(portfolio_signal, test_df[return_col])
            test_df_with_signal = test_df.copy()
            test_df_with_signal['_raw_signal'] = portfolio_signal
            raw_signal_daily_cs_ic = self.compute_daily_cs_ic(
                test_df_with_signal, '_raw_signal', return_col
            )
            
            # FIX 6: Log comprehensive diagnostics
            logger.info(
                f"[P10] Fold {fold_id} multi-horizon diagnostics:\n"
                f"  Requested horizons: {self.blend_horizons}\n"
                f"  Included horizons: {[h for h, d in horizon_details.items() if d.get('included', False)]}\n"
                f"  Excluded horizons: {[h for h, d in horizon_details.items() if not d.get('included', True)]}\n"
                f"  Blend method: {self.blend_weight_method}\n"
                f"  Fallback used: {fallback_used}"
            )
            for h, details in horizon_details.items():
                if details.get('included', False):
                    qm = details['quality_metrics']
                    gate_passed = sum(1 for res in details['gate_results'].values() if _is_gate_verdict_pass(res.get('verdict')))
                    gate_total = len(details['gate_results'])
                    logger.info(
                        f"  Horizon {h}: train_ic={qm.get('train_ic', 0):.4f}, "
                        f"val_ic={qm.get('validation_ic', 0):.4f}, "
                        f"final_obj_val_ic={qm.get('final_objective_validation_ic', 0):.4f}, "
                        f"gate={gate_passed}/{gate_total}"
                    )
            
            logger.info(
                f"[P10] Fold {fold_id} multi-horizon raw signal: "
                f"IC={raw_signal_ic:.4f}, daily_cs_ic={raw_signal_daily_cs_ic:.4f}"
            )
            
            # Note: XGBoost and evolved signal are disabled in multi-horizon mode
            # to keep P10 implementation focused and avoid complexity
            
            # For metrics reporting: use train_df as train_df_clean
            # (embargo is applied per-horizon inside _compute_horizon_signal)
            train_df_clean = train_df
        
        else:
            # ==============================================================================
            # Original Single-Horizon Path (default behavior, unchanged)
            # ==============================================================================
        
            # --- Embargo: drop last h rows per symbol from IC/selection window ---
            # Extract horizon h from return_col name (e.g. 'fwd_ret_5' -> h=5).
            # Falls back to h=1 for unrecognised patterns.
            try:
                h = int(return_col.split('_')[-1])
            except (ValueError, IndexError):
                h = 1
                logger.warning(
                    f"Could not parse horizon from return_col='{return_col}'; "
                    f"defaulting embargo h={h}"
                )
            
            # Vectorized embargo: cumcount(ascending=False)==0 is the last row per symbol.
            # Keep only rows where tail_rank >= h (i.e. not in the last h rows).
            # This preserves all columns and is compatible with pandas 3.x.
            _tail_rank = train_df.groupby('ticker').cumcount(ascending=False)
            train_df_clean = train_df[_tail_rank >= h].reset_index(drop=True)
            logger.info(
                f"Fold {fold_id} embargo: h={h}, "
                f"train rows before={len(train_df)}, after={len(train_df_clean)}"
            )
            # Split train_df_clean into Train Actual and Validation dynamically (e.g. 2:1 ratio by unique dates)
            unique_dates = sorted(train_df_clean['date'].unique())
            if len(unique_dates) >= 3:
                split_idx = int(len(unique_dates) * 2 / 3)
                val_start_date = unique_dates[split_idx]
                train_actual = train_df_clean[train_df_clean['date'] < val_start_date].reset_index(drop=True)
                val_actual = train_df_clean[train_df_clean['date'] >= val_start_date].reset_index(drop=True)
            else:
                train_actual = train_df_clean
                val_actual = train_df_clean
                
            logger.info(
                f"Fold {fold_id} validation split: "
                f"train_actual={len(train_actual)} rows, val_actual={len(val_actual)} rows"
            )
            
            # Compute IC on actual training set (no label leakage)
            train_ics = self.compute_alpha_ics(train_actual, alpha_cols, return_col)
            
            # Strategy filter: momentum only keeps positive IC alphas
            if hasattr(self, "strategy") and self.strategy == "momentum":
                train_ics = {k: v for k, v in train_ics.items() if v > 0.0}
                
            logger.info(f"Fold {fold_id} train ICs (strategy={self.strategy}): {train_ics}")

            # GATE: RISK_ADJUSTED_ALPHA_SELECTION_20260614 — opt-in composite scoring
            # GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614 — portfolio guard init
            _portfolio_guard_result = None
            if self.risk_adjusted_alpha_selection:
                # Compute baseline alphas for portfolio guard comparison
                _baseline_top_alphas = None
                if self.portfolio_guard_enabled:
                    if cost_aware:
                        _bl_adj = self.adjust_alphas_for_cost(
                            train_actual, alpha_cols, train_ics
                        )
                        _baseline_top_alphas = self.select_top_alphas(_bl_adj)
                    else:
                        _baseline_top_alphas = self.select_top_alphas(train_ics)

                ra_result = self.risk_adjusted_select(
                    alpha_cols,
                    train_df=train_actual,
                    val_df=val_actual,
                    train_ics=train_ics,
                    return_col=return_col,
                )
                if ra_result.selected_alphas:
                    top_alphas = ra_result.selected_alphas
                else:
                    logger.warning("[RiskAdj] No alphas selected, falling back to default")
                    if cost_aware:
                        adjusted_ics = self.adjust_alphas_for_cost(
                            train_actual, alpha_cols, train_ics
                        )
                        top_alphas = self.select_top_alphas(adjusted_ics)
                    else:
                        top_alphas = self.select_top_alphas(train_ics)

                # GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614
                if self.portfolio_guard_enabled and ra_result.selected_alphas:
                    from omega.quant.walk_forward.risk_adjusted_alpha_score import (
                        evaluate_portfolio_guard,
                    )
                    _portfolio_guard_result = evaluate_portfolio_guard(
                        ra_result,
                        val_df=val_actual,
                        train_ics=train_ics,
                        return_col=return_col,
                        baseline_alpha_cols=_baseline_top_alphas,
                        underperformance_tolerance=self.portfolio_guard_tolerance,
                    )
                    if _portfolio_guard_result.portfolio_guard_status == "FALLBACK_TO_BASELINE":
                        logger.warning(
                            f"[PortfolioGuard] Fallback to baseline: "
                            f"{_portfolio_guard_result.guard_reason}"
                        )
                        if _baseline_top_alphas:
                            top_alphas = _baseline_top_alphas
                        # Clear ra_result so evidence reflects fallback
                        ra_result = None
                    else:
                        logger.info(
                            f"[PortfolioGuard] ACCEPTED: "
                            f"{_portfolio_guard_result.guard_reason}"
                        )
            # Stage 6.2: Cost-aware alpha selection
            elif cost_aware:
                adjusted_ics = self.adjust_alphas_for_cost(
                    train_actual, alpha_cols, train_ics
                )
                top_alphas = self.select_top_alphas(adjusted_ics)
            else:
                # Select top alphas based on train IC
                top_alphas = self.select_top_alphas(train_ics)

            # ------------------------------------------------------------------
            # GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615
            # Opt-in diversified alpha basket selector.
            # Train-only: uses train_actual for correlation/ICIR computation.
            # PIT-safe: no test data used.  Default off.
            # ------------------------------------------------------------------
            _diversified_basket_evidence = None
            if self.diversified_basket_enabled and len(top_alphas) >= 2:
                try:
                    top_alphas, _diversified_basket_evidence = (
                        self.select_diversified_basket(
                            candidate_alphas=top_alphas,
                            train_df=train_actual,
                            train_ics=train_ics,
                            return_col=return_col,
                        )
                    )
                    logger.info(
                        f"[DivBasket] Fold {fold_id}: "
                        f"selected {len(top_alphas)} alphas: {top_alphas}"
                    )
                except Exception as e:
                    logger.warning(
                        f"[DivBasket] Fold {fold_id}: failed ({e}), "
                        f"keeping original top_alphas"
                    )
                    _diversified_basket_evidence = {
                        "gate": DIVERSIFIED_BASKET_GATE_ID,
                        "enabled": True,
                        "fallback_reason": f"exception: {e}",
                        "pit_safe": True,
                    }

            # ------------------------------------------------------------------
            # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614
            # Apply winner guard filter to constrain candidate pool to allowlist.
            # PIT-safe: uses validation IC from val_actual only (no test data).
            # ------------------------------------------------------------------
            _winner_guard_evidence = None
            if self.formulaic_winner_guard:
                _val_ics_for_guard = self.compute_alpha_ics(
                    val_actual, alpha_cols, return_col
                )
                top_alphas, _winner_guard_evidence = (
                    self.apply_formulaic_winner_guard(
                        top_alphas, _val_ics_for_guard
                    )
                )

            # ------------------------------------------------------------------
            # Stage 3 ML Gate: filter top_alphas through Research Gate
            # Uses validation set (val_actual) — PIT safe, no look-ahead.
            # ------------------------------------------------------------------
            gated_alphas, gate_results = self.validate_alpha_with_research_gate(
                top_alphas=top_alphas,
                train_ics=train_ics,
                train_df_clean=val_actual,
                return_col=return_col,
            )

            # ------------------------------------------------------------------
            # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614
            # GATE: FORMULAIC_WINNER_SELECTION_GUARD_FIX1_20260614
            # Post-gate fallback filter: when winner guard is enabled, prevent
            # non-allowlist legacy alphas from entering the fallback pool.
            # FIX1: If all fallback alphas excluded, gated_alphas becomes empty
            # (no legacy re-admission).
            # ------------------------------------------------------------------
            if self.formulaic_winner_guard and _winner_guard_evidence is not None:
                _fb_filtered, _fb_excluded = self.filter_fallback_by_winner_guard(
                    gated_alphas,
                    _val_ics_for_guard,
                )
                if _fb_excluded:
                    _winner_guard_evidence["fallback_excluded_alphas"] = _fb_excluded
                    _winner_guard_evidence["fallback_filtered_alphas"] = _fb_filtered
                if not _fb_filtered and gated_alphas:
                    # FIX1: all gated_alphas excluded by fallback filter
                    _winner_guard_evidence["fallback_no_guard_candidates"] = True
                gated_alphas = _fb_filtered

            # ------------------------------------------------------------------
            # GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616
            # PIT-safe stability filter for auto-alpha bundle candidates.
            # Uses only train/in-fold pre-OOS evidence.  Default off.
            # ------------------------------------------------------------------
            _oos_stability_evidence = None
            if self.enable_oos_stability_filter:
                try:
                    gated_alphas, _oos_stability_evidence = (
                        self._apply_oos_stability_filter(
                            candidate_alphas=gated_alphas,
                            train_df=train_actual,
                            return_col=return_col,
                        )
                    )
                    logger.info(
                        f"[OOSStability] Fold {fold_id}: "
                        f"{_oos_stability_evidence.get('n_passed_bundle', 0)} "
                        f"bundle alphas passed, "
                        f"{_oos_stability_evidence.get('n_excluded_bundle', 0)} "
                        f"excluded"
                    )
                except Exception as e:
                    logger.warning(
                        f"[OOSStability] Fold {fold_id}: failed ({e}), "
                        f"keeping original gated_alphas"
                    )
                    _oos_stability_evidence = {
                        "gate": AUTO_ALPHA_OOS_STABILITY_FILTER_GATE_ID,
                        "enabled": True,
                        "fallback_reason": f"exception: {e}",
                        "pit_safe": True,
                    }

            # ------------------------------------------------------------------
            # Stage 4: optional XGBoost path (use_xgboost=True) vs baseline
            # Baseline: IC-weighted signal from gated alphas (unchanged).
            # XGBoost: train XGBoostAlphaEnsemble on train_actual MultiIndex,
            #          predict on test_df MultiIndex, standardize to portfolio_signal.
            # PIT Safety: ensemble trains only on embargoed train_actual.
            # ------------------------------------------------------------------
            if self.enable_multi_model_ensemble and len(train_actual) > 0 and len(gated_alphas) > 0:
                try:
                    X_train_multi = train_actual.set_index(['date', 'ticker']).rename_axis(index={'ticker': 'symbol'})
                    X_test_multi = test_df.set_index(['date', 'ticker']).rename_axis(index={'ticker': 'symbol'})
                    cutoff_date = str(
                        train_df_clean['date'].max().date()
                        if hasattr(train_df_clean['date'].max(), 'date')
                        else train_df_clean['date'].max()
                    )
                    ensemble = MultiModelAlphaEnsemble(min_ic_threshold=0.0)
                    ensemble.train(X_train_multi, gated_alphas, cutoff_date=cutoff_date, embargo_days=0)
                    result = ensemble.predict(X_test_multi, gated_alphas)
                    preds_df = result.predictions.reset_index().rename(columns={'symbol': 'ticker', 0: 'pred'})
                    merged = test_df[['date', 'ticker']].merge(preds_df, on=['date', 'ticker'], how='left')
                    preds_series = pd.Series(merged['pred'].fillna(0.0).values, index=test_df.index)
                    std_val = preds_series.std()
                    portfolio_signal = (preds_series - preds_series.mean()) / std_val if std_val > 0 else preds_series
                    logger.info(
                        f"Fold {fold_id}: multi-model ensemble active, "
                        f"models={result.active_models}, weights={result.weights}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Fold {fold_id}: multi-model ensemble failed ({e}), falling back to baseline"
                    )
                    portfolio_signal = self.compute_portfolio_signal(test_df, gated_alphas, train_ics)
            elif self.use_xgboost and len(train_actual) > 0 and len(gated_alphas) > 0:
                try:
                    # Convert flat ['date','ticker'] -> MultiIndex ['date','symbol']
                    X_train_multi = (
                        train_actual
                        .set_index(['date', 'ticker'])
                        .rename_axis(index={'ticker': 'symbol'})
                    )
                    X_test_multi = (
                        test_df
                        .set_index(['date', 'ticker'])
                        .rename_axis(index={'ticker': 'symbol'})
                    )

                    # Derive cutoff_date from max train date (embargo already applied)
                    cutoff_date = str(
                        train_df_clean['date'].max().date()
                        if hasattr(train_df_clean['date'].max(), 'date')
                        else train_df_clean['date'].max()
                    )

                    ensemble = XGBoostAlphaEnsemble(min_ic_threshold=0.0)
                    ensemble.train(
                        X_train_multi,
                        gated_alphas,
                        cutoff_date=cutoff_date,
                        embargo_days=0,  # embargo already applied upstream
                    )
                    raw_preds = ensemble.predict(X_test_multi, gated_alphas)

                    # Flatten MultiIndex predictions back to flat test_df index
                    # Align raw_preds (indexed by date, symbol) with test_df (columns date, ticker) to prevent drift
                    preds_df = raw_preds.reset_index().rename(columns={'symbol': 'ticker', 0: 'pred'})
                    merged = test_df[['date', 'ticker']].merge(preds_df, on=['date', 'ticker'], how='left')
                    preds_flat = merged['pred'].fillna(0.0).values
                    if len(preds_flat) == len(test_df):
                        preds_series = pd.Series(preds_flat, index=test_df.index)
                        # Standardize: zero-mean, unit-std per date cross-section
                        std_val = preds_series.std()
                        if std_val > 0:
                            portfolio_signal = (preds_series - preds_series.mean()) / std_val
                        else:
                            portfolio_signal = preds_series
                        logger.info(f"Fold {fold_id}: XGBoost path active, signal std={std_val:.4f}")
                    else:
                        logger.warning(
                            f"Fold {fold_id}: XGBoost pred length mismatch "
                            f"({len(preds_flat)} vs {len(test_df)}), falling back to baseline"
                        )
                        portfolio_signal = self.compute_portfolio_signal(test_df, gated_alphas, train_ics)
                except Exception as e:
                    logger.warning(
                        f"Fold {fold_id}: XGBoost path failed ({e}), falling back to baseline"
                    )
                    portfolio_signal = self.compute_portfolio_signal(test_df, gated_alphas, train_ics)
            else:
                # Baseline: IC-weighted signal (original path, fully preserved)
                portfolio_signal = self.compute_portfolio_signal(test_df, gated_alphas, train_ics)

            # ------------------------------------------------------------------
            # Evolved Alpha Blending (optional) with Adaptive Weight
            # If enable_evolved=True, run inline GP evolution on train_actual,
            # execute best tree on test_df, and blend with hand-crafted signal.
            # PIT Safety: evolution trains only on train_actual (embargoed).
            # Adaptive: blend weight scales with train_ic quality (cap at user weight).
            # ------------------------------------------------------------------
            if self.enable_evolved and len(train_actual) > 0:
                evolved_signal, gp_train_ic = self._evolve_inline_signal(train_actual, test_df, return_col)
                if evolved_signal is not None:
                    # Align evolved signal length with portfolio_signal
                    if len(evolved_signal) == len(portfolio_signal):
                        # Adaptive blend: scale weight by GP train quality
                        # w_adaptive = min(user_weight, abs(train_ic) * scale_factor)
                        # scale_factor=2 means IC=0.05 → weight=0.10, IC=0.10 → weight=0.20
                        abs_train_ic = abs(gp_train_ic)
                        scale_factor = 2.0
                        w_adaptive = min(self.evolved_blend_weight, abs_train_ic * scale_factor)
                        # P2: Ceiling protection - cap at 25% to prevent overfit
                        # Ensures hand-crafted signal dominates (≥75%)
                        ceiling = 0.25
                        w_evo = min(w_adaptive, ceiling)
                        # Floor: at least 10% of user weight to avoid zero contribution
                        w_evo = max(w_evo, self.evolved_blend_weight * 0.1)
                        w_hand = 1.0 - w_evo
                        portfolio_signal = pd.Series(
                            w_evo * evolved_signal + w_hand * portfolio_signal.values,
                            index=portfolio_signal.index
                        )
                        logger.info(
                            f"Fold {fold_id}: Evolved signal blended "
                            f"(evolved={w_evo:.3f}, handcrafted={w_hand:.3f}, "
                            f"gp_train_ic={gp_train_ic:.4f}, adaptive=True)"
                        )
                    else:
                        logger.warning(
                            f"Fold {fold_id}: Evolved signal length mismatch "
                            f"({len(evolved_signal)} vs {len(portfolio_signal)}), skipping blend"
                        )

            # Strategy filter: mean reversion reverses signal direction
            if hasattr(self, "strategy") and self.strategy == "mean_reversion":
                portfolio_signal = -portfolio_signal

            # --- Fix 3+4: Raw signal IC (before Stage 2) + Z-score normalization ---
            # Apply cross-sectional z-score normalization to raw signal before blending
            # This prevents scale differences between alphas from dominating weights
            test_df_copy = test_df.copy()
            test_df_copy['_raw_signal'] = portfolio_signal
            # Z-score per date (cross-sectional)
            test_df_copy['_raw_signal'] = test_df_copy.groupby('date')['_raw_signal'].transform(
                lambda x: (x - x.mean()) / (x.std() + 1e-9)
            )
            portfolio_signal = test_df_copy['_raw_signal']

            # Compute raw signal IC (pre Stage 2) — this is the true predictive power
            raw_signal_ic = self.compute_ic(portfolio_signal, test_df[return_col])
            
            # Compute daily cross-sectional IC for raw signal (more robust metric)
            test_df_with_signal = test_df.copy()
            test_df_with_signal['_raw_signal'] = portfolio_signal
            raw_signal_daily_cs_ic = self.compute_daily_cs_ic(
                test_df_with_signal, '_raw_signal', return_col
            )
            
            logger.info(
                f"Fold {fold_id} raw signal IC: {raw_signal_ic:.4f}, "
                f"daily CS IC: {raw_signal_daily_cs_ic:.4f}"
            )
            
            # Role21 Fix 2026-06-10: Single-horizon path doesn't use structured gate metadata
            gate_metadata = None
        
        # ==============================================================================
        # Both paths converge here: Stage 2 constraints apply to both single-horizon
        # and multi-horizon signals
        # ==============================================================================

        # ------------------------------------------------------------------
        # GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615
        # Opt-in ex-ante regime-conditioned alpha routing.
        # PIT-safe: regime features from lagged market data, IC from train only,
        # test routing from ex-ante regime labels only (never test returns).
        # ------------------------------------------------------------------
        _regime_routing_evidence = None
        if self.regime_routing_enabled:
            try:
                # Ensure train_ics is available (multi-horizon path may not set it)
                try:
                    _rr_train_ics = train_ics
                except NameError:
                    _rr_train_ics = self.compute_alpha_ics(
                        train_df, alpha_cols, return_col
                    )
                # Compute ex-ante regimes from lagged market features (PIT-safe)
                _all_dates = pd.concat([
                    train_df[['date', 'ticker', 'close']],
                    test_df[['date', 'ticker', 'close']],
                ], ignore_index=True)
                _regime_df = self._compute_ex_ante_regimes(_all_dates)

                # Check min train days
                _train_regime_dates = set(_regime_df['date']).intersection(
                    set(train_df['date'].unique())
                )
                _n_train_regime_days = len(_train_regime_dates)

                if _n_train_regime_days < self.regime_routing_min_train_days:
                    logger.warning(
                        f"[RegimeRouting] Insufficient train regime days "
                        f"({_n_train_regime_days} < {self.regime_routing_min_train_days}), "
                        f"falling back to baseline"
                    )
                    _regime_routing_evidence = {
                        "gate": REGIME_ROUTING_GATE_ID,
                        "enabled": True,
                        "fallback_reason": "insufficient_train_days",
                        "n_train_regime_days": _n_train_regime_days,
                        "min_train_days": self.regime_routing_min_train_days,
                        "pit_safe": True,
                    }
                else:
                    # Estimate per-regime IC on train window only
                    _regime_ics = self._estimate_regime_ic(
                        train_df, alpha_cols, return_col, _regime_df
                    )

                    # Apply routing to test signal
                    portfolio_signal, _regime_routing_evidence = (
                        self._apply_regime_routing(
                            test_df, portfolio_signal, _regime_df,
                            _regime_ics, alpha_cols, _rr_train_ics,
                        )
                    )
                    logger.info(
                        f"[RegimeRouting] Fold {fold_id}: routed "
                        f"{_regime_routing_evidence['n_routed']} dates, "
                        f"fallback={_regime_routing_evidence['n_fallback']}"
                    )
            except Exception as e:
                logger.warning(
                    f"[RegimeRouting] Fold {fold_id}: failed ({e}), "
                    f"falling back to baseline"
                )
                _regime_routing_evidence = {
                    "gate": REGIME_ROUTING_GATE_ID,
                    "enabled": True,
                    "fallback_reason": f"exception: {e}",
                    "pit_safe": True,
                }

        # ------------------------------------------------------------------
        # Stage 2 behavioral enforcement (top-N, rebalance cadence, sector cap)
        # Applied AFTER IC-weighted signal combination, BEFORE return computation.
        # PIT safety preserved: test_df signals are already T-1 lagged upstream.
        # ------------------------------------------------------------------
        try:
            portfolio_signal = self._apply_stage2_constraints(
                test_df=test_df,
                raw_signal=portfolio_signal,
                top_alphas=gated_alphas,
                dynamic_rebalance=True,
                train_df=train_df,
            )
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            # Backward-compatible path for tests or external monkeypatches that
            # still expose the original 3-argument Stage 2 hook signature.
            logger.warning(
                "Stage 2 constraints hook does not accept P9 kwargs; "
                "falling back to legacy call signature"
            )
            portfolio_signal = self._apply_stage2_constraints(
                test_df=test_df,
                raw_signal=portfolio_signal,
                top_alphas=gated_alphas,
            )

        # ------------------------------------------------------------------
        # GATE: BASELINE_RISK_SIZING_OPTIMIZATION_20260616
        # Apply risk/sizing overlay (opt-in, default-off, PIT-safe).
        # Sits on top of Stage 2 constraints. Modifies position sizing
        # (inverse-vol) and gross exposure (confidence scaling).
        # Never uses current-bar data, OOS labels, or forward returns.
        # ------------------------------------------------------------------
        _risk_sizing_evidence = None
        if self.risk_sizing_overlay_enabled:
            try:
                from omega.quant.walk_forward.risk_sizing_overlay import (
                    RiskSizingConfig,
                    apply_risk_sizing_overlay,
                    auto_optimize_regime_scale,
                )
                # GATE: REGIME_CONDITIONAL_SIZING_20260616 — auto-optimize scale
                # If enabled, grid-search on train_df to find best scale for this fold
                _effective_regime_scale = self.risk_sizing_regime_scale
                _auto_opt_evidence = None
                if (
                    self.risk_sizing_regime
                    and self.risk_sizing_regime_auto_optimize
                    and train_df is not None
                    and not train_df.empty
                ):
                    _effective_regime_scale, _auto_opt_evidence = (
                        auto_optimize_regime_scale(
                            train_df,
                            regime_window=self.risk_sizing_regime_window,
                            regime_mode=self.risk_sizing_regime_mode,
                            ma_window=self.risk_sizing_regime_ma_window,
                            vol_window=self.risk_sizing_regime_vol_window,
                            vol_median_window=self.risk_sizing_regime_vol_median_window,
                        )
                    )
                    logger.info(
                        f"[RiskSizing] Fold {fold_id}: auto-optimize selected "
                        f"scale={_effective_regime_scale:.2f} "
                        f"(Sharpe={_auto_opt_evidence.get('best_sharpe', 0.0):.4f})"
                    )

                _rs_config = RiskSizingConfig(
                    inverse_vol_sizing=self.risk_sizing_inverse_vol,
                    inverse_vol_window=self.risk_sizing_inverse_vol_window,
                    inverse_vol_floor=self.risk_sizing_inverse_vol_floor,
                    confidence_scaling=self.risk_sizing_confidence,
                    confidence_window=self.risk_sizing_confidence_window,
                    confidence_min_ic=self.risk_sizing_confidence_min_ic,
                    confidence_max_scale=self.risk_sizing_confidence_max_scale,
                    confidence_min_scale=self.risk_sizing_confidence_min_scale,
                    regime_sizing=self.risk_sizing_regime,
                    regime_sizing_scale=_effective_regime_scale,
                    regime_ma_window=self.risk_sizing_regime_ma_window,
                    regime_vol_window=self.risk_sizing_regime_vol_window,
                    regime_vol_median_window=self.risk_sizing_regime_vol_median_window,
                    regime_sizing_window=self.risk_sizing_regime_window,
                    regime_sizing_mode=self.risk_sizing_regime_mode,
                    regime_sizing_auto_optimize=self.risk_sizing_regime_auto_optimize,
                    regime_refit_stride=self.risk_sizing_regime_refit_stride,
                )
                portfolio_signal, _risk_sizing_evidence = apply_risk_sizing_overlay(
                    test_df, portfolio_signal, _rs_config
                )
                # Attach auto-optimize evidence
                if _auto_opt_evidence is not None:
                    _risk_sizing_evidence["auto_optimize_evidence"] = _auto_opt_evidence
                    _risk_sizing_evidence["effective_regime_scale"] = _effective_regime_scale
                logger.info(
                    f"[RiskSizing] Fold {fold_id}: "
                    f"ivol={self.risk_sizing_inverse_vol}, "
                    f"conf={self.risk_sizing_confidence}, "
                    f"regime={self.risk_sizing_regime} (mode={self.risk_sizing_regime_mode}), "
                    f"auto_opt={self.risk_sizing_regime_auto_optimize}, "
                    f"avg_scale={_risk_sizing_evidence.get('avg_confidence_scale', 1.0):.4f}, "
                    f"n_regime_bear={_risk_sizing_evidence.get('regime_counts', {}).get('bear', 0)}"
                )
            except Exception as e:
                logger.warning(
                    f"[RiskSizing] Fold {fold_id}: failed ({e}), "
                    f"falling back to baseline signal"
                )
                _risk_sizing_evidence = {
                    "gate": "BASELINE_RISK_SIZING_OPTIMIZATION_20260616",
                    "enabled": True,
                    "fallback_reason": f"exception: {e}",
                    "pit_safe": True,
                }

        # ------------------------------------------------------------------
        # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615
        # Build per-fold dynamic universe evidence for audit persistence.
        # Collects schedule usage stats for this fold's test dates.
        # ------------------------------------------------------------------
        _dynamic_universe_evidence = self._build_fold_dynamic_universe_evidence(
            test_df
        )

        # Compute test IC for each alpha
        test_ics = self.compute_alpha_ics(test_df, alpha_cols, return_col)
        
        # Compute portfolio IC on test set
        portfolio_ic = self.compute_ic(portfolio_signal, test_df[return_col])
        
        # Compute portfolio returns (signal * forward return)
        portfolio_returns = portfolio_signal * test_df[return_col]
        portfolio_returns = portfolio_returns.dropna()

        # Build daily aggregated returns (sum over assets on each date)
        # We must align portfolio_returns with date and group/sum.
        # Ensure PIT Safety: date aggregation is done on test_df date series.
        # Since portfolio_returns might have dropped NaNs, we align with test_df index first.
        aligned_df = pd.DataFrame({
            'date': test_df.loc[portfolio_returns.index, 'date'],
            'p_ret': portfolio_returns
        })
        daily_series = aligned_df.groupby('date')['p_ret'].sum().sort_index()

        # Plumb slippage and commission to actual realized portfolio returns
        df_weights = pd.DataFrame({'date': test_df['date'], 'ticker': test_df['ticker'], 'weight': portfolio_signal})
        pivot_weights = df_weights.pivot(index='date', columns='ticker', values='weight').fillna(0.0)
        daily_turnover = pivot_weights.diff(axis=0).abs().sum(axis=1)
        if len(daily_turnover) > 0:
            daily_turnover.iloc[0] = pivot_weights.iloc[0].abs().sum()

        daily_turnover = daily_turnover.reindex(daily_series.index, fill_value=0.0)
        daily_series = daily_series - (daily_turnover * self.cost_per_turnover)

        # Stage 6.3: Active Drawdown Control
        # GATE: STAGE6_3_DRAWDOWN_RE_ENTRY_20260616 — stateful drawdown control
        # with cooldown and high-water mark reset.
        # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616 — adaptive cooldown
        # using HMM bear probability and trailing volatility.
        _dd_re_entry_evidence = None
        if self.drawdown_control and len(daily_series) > 0:
            # Build hmm_p_bear_dict from risk sizing evidence if available
            _hmm_p_bear_dict = None
            if (
                self.drawdown_adaptive_re_entry
                and _risk_sizing_evidence is not None
                and isinstance(_risk_sizing_evidence, dict)
            ):
                _p_bear_data = _risk_sizing_evidence.get("hmm_p_bear")
                if isinstance(_p_bear_data, dict):
                    _dates = _p_bear_data.get("dates", [])
                    _values = _p_bear_data.get("values", [])
                    if _dates and _values and len(_dates) == len(_values):
                        _hmm_p_bear_dict = dict(zip(_dates, _values))

            # Build close_wide for adaptive volatility computation.
            # Include train_df trailing history so detect_market_regime has
            # sufficient lookback for MA/vol windows at early test dates.
            _close_wide = None
            if self.drawdown_adaptive_re_entry:
                try:
                    _work_close = test_df[["date", "ticker", "close"]].copy()
                    if train_df is not None and not train_df.empty:
                        _train_close = train_df[["date", "ticker", "close"]].copy()
                        _work_close = pd.concat(
                            [_train_close, _work_close], ignore_index=True
                        )
                    _work_close = _work_close.sort_values(["date", "ticker"])
                    _close_wide = _work_close.pivot(
                        index="date", columns="ticker", values="close"
                    )
                except Exception:
                    _close_wide = None

            _dd_re_entry_evidence = self._apply_drawdown_control(
                daily_series, portfolio_returns, aligned_df, fold_id,
                hmm_p_bear_dict=_hmm_p_bear_dict,
                close_wide=_close_wide,
            )

        # Compute Sharpe and Max DD from daily aggregated returns series
        sharpe = self.compute_sharpe_ratio(daily_series)
        max_dd = self.compute_max_drawdown(daily_series)
        total_return = daily_series.sum()
        pnl_val = total_return * self.initial_capital
        
        # Create metrics object
        # Role21 Fix 2026-06-10: Added gate_metadata field
        # GATE: RISK_ADJUSTED_ALPHA_SELECTION_FIX1_20260614: persist per-fold evidence
        _ra_evidence = None
        if ra_result is not None:
            _ra_evidence = ra_result.to_dict()
        elif isinstance(gate_metadata, dict) and gate_metadata.get('risk_adjusted_evidence'):
            _ra_evidence = gate_metadata['risk_adjusted_evidence']

        # GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614 — persist guard evidence
        _pg_evidence = None
        if _portfolio_guard_result is not None:
            _pg_evidence = _portfolio_guard_result.to_dict()

        # GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615 — persist per-fold NR evidence
        # GATE: NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615 — evidence uses pruned gate ID
        _nr_evidence = None
        if self.enable_nonredundant_alphas:
            _nr_computed_cols = [
                c for c in test_df.columns if c.startswith("alpha_nr_")
            ]
            _nr_sector_loaded = getattr(self, '_nr_sector_map_loaded', False)
            _nr_fallback_reason = getattr(self, '_nr_sector_map_fallback_reason', None)
            # Select gate ID based on set_name
            # GATE: NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615 — pruned gate
            # GATE: NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615 — focused overlay gate
            if self.nonredundant_alpha_set == "v1_pruned":
                _nr_gate_id = NONREDUNDANT_ALPHA_V1_PRUNED_GATE_ID
            elif self.nonredundant_alpha_set in ("v1_mrm_only", "v1_mrm_range"):
                _nr_gate_id = NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID
            else:
                _nr_gate_id = NONREDUNDANT_ALPHA_GATE_ID
            _nr_evidence = {
                "gate": _nr_gate_id,
                "enabled": True,
                "set_name": self.nonredundant_alpha_set,
                "max_candidates": self.nonredundant_alpha_max_candidates,
                "computed_candidate_columns": _nr_computed_cols,
                "computed_candidate_count": len(_nr_computed_cols),
                "sector_map_loaded": _nr_sector_loaded,
                "sector_map_fallback": not _nr_sector_loaded,
                "pit_safe": True,
                "fallback_reason": _nr_fallback_reason,
            }

        # GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615 — persist per-fold
        # automated OOS bundle evidence when enabled.
        _auto_evidence = None
        if self.enable_automated_oos_bundle:
            _auto_computed_cols = [
                c for c in self.automated_oos_bundle_alphas
                if c in test_df.columns
            ]
            _auto_evidence = {
                "gate": AUTOMATED_ALPHA_OOS_GATE_ID,
                "enabled": True,
                "bundle_name": self.automated_oos_bundle_name,
                "bundle_alphas": list(self.automated_oos_bundle_alphas),
                "computed_bundle_columns": _auto_computed_cols,
                "computed_bundle_column_count": len(_auto_computed_cols),
                "pit_safe": True,
                "no_oos_label_use": True,
                "no_live_promotion": True,
            }

        metrics = FoldMetrics(
            fold_id=fold_id,
            train_start=str(train_df['date'].min().date()),
            train_end=str(train_df['date'].max().date()),
            test_start=str(test_df['date'].min().date()),
            test_end=str(test_df['date'].max().date()),
            alpha_ics=test_ics,
            portfolio_sharpe=sharpe,
            portfolio_max_dd=max_dd,
            portfolio_total_return=total_return,
            portfolio_pnl_vnd=pnl_val,
            portfolio_ic=portfolio_ic,
            raw_signal_ic=raw_signal_ic,
            raw_signal_daily_cs_ic=raw_signal_daily_cs_ic,
            n_train_samples=len(train_df_clean),
            n_test_samples=len(test_df),
            gate_results=gate_results,
            gated_alphas=gated_alphas,
            gate_metadata=gate_metadata,
            risk_adjusted_evidence=_ra_evidence,
            portfolio_guard_evidence=_pg_evidence,
            # GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614
            winner_guard_evidence=_winner_guard_evidence,
            # GATE: REGIME_CONDITIONED_ALPHA_ROUTING_20260615
            regime_routing_evidence=_regime_routing_evidence,
            # GATE: DYNAMIC_REBALANCE_UNIVERSE_20260615 — per-fold evidence
            dynamic_universe_evidence=_dynamic_universe_evidence,
            # GATE: DYNAMIC_UNIVERSE_DIVERSIFIED_BASKET_20260615 — per-fold evidence
            diversified_basket_evidence=_diversified_basket_evidence,
            # GATE: NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615 — per-fold evidence
            nonredundant_alpha_evidence=_nr_evidence,
            # GATE: AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615 — per-fold evidence
            automated_discovery_evidence=_auto_evidence,
            # GATE: AUTO_ALPHA_OOS_STABILITY_FILTER_20260616 — per-fold evidence
            oos_stability_filter_evidence=_oos_stability_evidence,
            # GATE: BASELINE_RISK_SIZING_OPTIMIZATION_20260616 — per-fold evidence
            risk_sizing_evidence=_risk_sizing_evidence,
            # GATE: STAGE6_3_DRAWDOWN_RE_ENTRY_20260616 — per-fold evidence
            drawdown_re_entry_evidence=_dd_re_entry_evidence,
        )
        
        logger.info(
            f"Fold {fold_id} results: RawIC={raw_signal_ic:.4f}, "
            f"RawCS_IC={raw_signal_daily_cs_ic:.4f}, "
            f"PortfolioIC={portfolio_ic:.4f}, "
            f"Sharpe={sharpe:.4f}, MaxDD={max_dd:.2%}, PnL={pnl_val:+,.0f} VND"
        )
        
        return metrics
    
    def run_walk_forward(
        self,
        splits: List[Tuple[pd.DataFrame, pd.DataFrame]],
        alpha_cols: List[str],
        return_col: str = 'fwd_ret_5',
    ) -> WalkForwardResult:
        """Run complete walk-forward backtest.
        
        Parameters
        ----------
        splits : list of tuple
            List of (train_df, test_df) pairs
        alpha_cols : list of str
            Alpha column names
        return_col : str
            Forward return column name
        
        Returns
        -------
        WalkForwardResult
            Complete backtest results
        """
        logger.info(f"Starting walk-forward backtest with {len(splits)} folds")
        
        fold_metrics = []
        
        for fold_id, (train_df, test_df) in enumerate(splits, start=1):
            metrics = self.run_fold(fold_id, train_df, test_df, alpha_cols, return_col)
            fold_metrics.append(metrics)
        
        # Aggregate results
        avg_ic_by_alpha = {}
        for alpha_col in alpha_cols:
            ics = [m.alpha_ics.get(alpha_col, 0.0) for m in fold_metrics]
            avg_ic_by_alpha[alpha_col] = np.mean(ics)
        
        avg_portfolio_ic = np.mean([m.portfolio_ic for m in fold_metrics])
        avg_raw_signal_ic = np.mean([m.raw_signal_ic for m in fold_metrics])
        avg_raw_signal_daily_cs_ic = np.mean([m.raw_signal_daily_cs_ic for m in fold_metrics])
        avg_portfolio_sharpe = np.mean([m.portfolio_sharpe for m in fold_metrics])
        avg_portfolio_max_dd = np.mean([m.portfolio_max_dd for m in fold_metrics])
        avg_portfolio_pnl_vnd = np.mean([m.portfolio_pnl_vnd for m in fold_metrics])
        
        result = WalkForwardResult(
            fold_metrics=fold_metrics,
            avg_ic_by_alpha=avg_ic_by_alpha,
            avg_portfolio_sharpe=avg_portfolio_sharpe,
            avg_portfolio_max_dd=avg_portfolio_max_dd,
            avg_portfolio_ic=avg_portfolio_ic,
            avg_raw_signal_ic=avg_raw_signal_ic,
            avg_raw_signal_daily_cs_ic=avg_raw_signal_daily_cs_ic,
            avg_portfolio_pnl_vnd=avg_portfolio_pnl_vnd,
            total_folds=len(fold_metrics),
        )
        
        logger.info("Walk-forward backtest complete")
        logger.info(result.summary())
        
        return result


if __name__ == "__main__":
    # Test walk-forward engine
    logging.basicConfig(level=logging.INFO)
    
    # Import required modules
    import sys
    from pathlib import Path
    
    workspace = Path(__file__).resolve().parents[4]
    _REPO_ROOT = workspace
    if str(_REPO_ROOT / 'src') not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / 'src'))
        
    from omega.quant.alpha import phase34 as phase34_module
    from phase35_data_loader import Phase35DataLoader
    
    # Load data
    loader = Phase35DataLoader()
    df = loader.load_and_prepare(
        start_date="2018-01-01",
        end_date="2026-05-08",
        top_n_symbols=20,
    )
    
    # Create splits
    splits = loader.create_walk_forward_splits(df, n_folds=6, train_years=1, test_years=1)
    
    # Run walk-forward backtest
    engine = Phase35WalkForwardEngine(
        alpha_module=phase34_module,
        min_ic_threshold=0.02,
        top_n_alphas=5,
    )
    
    alpha_cols = list(phase34_module.PHASE34_ALPHA_COLUMNS)
    
    result = engine.run_walk_forward(splits, alpha_cols, return_col='fwd_ret_5')
    
    print("\n" + result.summary())
    alpha_cols = list(phase34_module.PHASE34_ALPHA_COLUMNS)
    
    result = engine.run_walk_forward(splits, alpha_cols, return_col='fwd_ret_5')
    
    print("\n" + result.summary())
