"""Risk-adjusted alpha composite scoring for walk-forward selection.

GATE: RISK_ADJUSTED_ALPHA_TUNING_20260614
KPI: C (risk-adjusted composite)
BOUNDARY: paper-trading-ready / no live trading

This module computes a composite risk-adjusted score for each alpha
candidate using ONLY train/validation/embargoed data (no test future).

Composite components:
  1. Validation IC           — Spearman IC on embargoed validation set
  2. IC Stability            — IC Sharpe (mean/std of daily IC series)
  3. Expected Sharpe Contrib  — if safely available from fold data
  4. Turnover Penalty        — penalise high day-over-day rank churn
  5. Drawdown Penalty        — if safely available from fold data
  6. Overfit Gap             — penalise large train-IC vs val-IC gap

Named Presets (GATE: RISK_ADJUSTED_ALPHA_TUNING_20260614):
  - ``balanced``        — equal-priority baseline (= current default weights)
  - ``alpha_recovery``  — emphasises IC/Sharpe recovery when Sharpe/IC worsened
  - ``drawdown_guarded``— emphasises drawdown/turnover protection
  - ``ic_first_guarded``— IC-first guarded tuning (GATE: RISK_ADJUSTED_ALPHA_IC_FIRST_TUNING_20260614).
    Prioritises raw_validation_ic and raw_ic_sharpe as primary rank components;
    turnover/drawdown/overfit serve as soft penalties or tie-breakers so risk
    penalties cannot dominate positive IC.

Opt-in via ``--risk-adjusted-alpha-selection``.  Default disabled.
Preset selectable via ``--risk-adjusted-preset``.  Default ``balanced``.
Paper-trading-only boundary is preserved: this module never touches live
execution paths or order routing.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default component weights (sum to 1.0)
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS: Dict[str, float] = {
    "validation_ic": 0.25,
    "ic_stability": 0.20,
    "expected_sharpe": 0.15,
    "turnover_penalty": 0.15,
    "drawdown_penalty": 0.10,
    "overfit_gap": 0.15,
}

# ---------------------------------------------------------------------------
# Named weight presets (GATE: RISK_ADJUSTED_ALPHA_TUNING_20260614)
# ---------------------------------------------------------------------------
# Each preset's weights MUST sum to 1.0 (validated by get_preset_weights).
#
# Design rationale
# ~~~~~~~~~~~~~~~~
# * ``balanced`` — backward-compatible default; equal-priority spread that
#   mirrors the original DEFAULT_WEIGHTS exactly.
# * ``alpha_recovery`` — shifts weight toward validation IC, IC stability and
#   expected Sharpe.  Intended for regimes where Sharpe/IC worsened in the
#   previous validation pass and the goal is to recover signal quality.
# * ``drawdown_guarded`` — shifts weight toward drawdown penalty and turnover
#   penalty.  Intended for regimes where MaxDD improved but the team wants to
#   lock in that protection.
PRESETS: Dict[str, Dict[str, float]] = {
    "balanced": {
        "validation_ic": 0.25,
        "ic_stability": 0.20,
        "expected_sharpe": 0.15,
        "turnover_penalty": 0.15,
        "drawdown_penalty": 0.10,
        "overfit_gap": 0.15,
    },
    "alpha_recovery": {
        "validation_ic": 0.30,
        "ic_stability": 0.25,
        "expected_sharpe": 0.20,
        "turnover_penalty": 0.10,
        "drawdown_penalty": 0.05,
        "overfit_gap": 0.10,
    },
    "drawdown_guarded": {
        "validation_ic": 0.15,
        "ic_stability": 0.15,
        "expected_sharpe": 0.10,
        "turnover_penalty": 0.20,
        "drawdown_penalty": 0.25,
        "overfit_gap": 0.15,
    },
    # GATE: RISK_ADJUSTED_ALPHA_IC_FIRST_TUNING_20260614
    # Design rationale
    # ~~~~~~~~~~~~~~~~
    # A/B showed all previous presets flip Portfolio IC negative because risk
    # penalties (drawdown/turnover) dominated positive IC in the composite.
    # ``ic_first_guarded`` fixes this by making validation_ic + ic_stability
    # the *primary rank components* (65 % combined) while reducing turnover,
    # drawdown, and overfit to *soft penalty / tie-breaker* roles (20 %
    # combined).  Expected Sharpe stays at 15 % as supporting quality signal.
    # Net effect: an alpha with positive IC outranks one with better drawdown
    # but weaker IC; drawdown/turnover only break ties when IC is close.
    "ic_first_guarded": {
        "validation_ic": 0.35,
        "ic_stability": 0.30,
        "expected_sharpe": 0.15,
        "turnover_penalty": 0.08,
        "drawdown_penalty": 0.05,
        "overfit_gap": 0.07,
    },
}

# Default preset name used when --risk-adjusted-preset is not specified.
DEFAULT_PRESET: str = "balanced"

# ---------------------------------------------------------------------------
# Rank component classification for evidence persistence
# (GATE: RISK_ADJUSTED_ALPHA_IC_FIRST_TUNING_20260614)
# ---------------------------------------------------------------------------
# ``ic_first_guarded`` splits the six components into two tiers:
#   - PRIMARY_RANK_COMPONENTS drive the ranking (IC quality first).
#   - SOFT_PENALTY_COMPONENTS serve as tie-breakers only.
# Other presets treat all components uniformly; these lists are persisted in
# the evidence config so Tier-3 auditors can reconstruct ranking rationale.
IC_FIRST_PRIMARY_COMPONENTS: List[str] = [
    "validation_ic",
    "ic_stability",
    "expected_sharpe",
]
IC_FIRST_SOFT_PENALTY_COMPONENTS: List[str] = [
    "turnover_penalty",
    "drawdown_penalty",
    "overfit_gap",
]

# ---------------------------------------------------------------------------
# Recovery Selector Pool Modes (GATE: RECOVERY_SELECTOR_OPT_IN_20260614)
# ---------------------------------------------------------------------------
# Opt-in selector modes that control which alpha pool is used for selection.
# Default ``full`` is unchanged — no production behavior change.
#
# A/B finding: recovery-only pool (excluding CONFIRMED_RETIRE) improves mean
# IC but does NOT improve positive fold rate.  The selector-ready report uses
# this to issue a DO_NOT_PROMOTE blocker when the improvement is insufficient.
RESEARCH_POOL_FULL = "full"
RESEARCH_POOL_RECOVERY_ONLY = "recovery_only"
RESEARCH_POOL_RECOVERABLE_ONLY = "recoverable_only"

VALID_RESEARCH_POOL_MODES = (
    RESEARCH_POOL_FULL,
    RESEARCH_POOL_RECOVERY_ONLY,
    RESEARCH_POOL_RECOVERABLE_ONLY,
)

# Selector-ready verdict: issued when recovery-only pool improves mean IC
# but positive fold rate does not improve — insufficient for promotion.
SELECTOR_VERDICT_DO_NOT_PROMOTE = "DO_NOT_PROMOTE"
SELECTOR_VERDICT_CONDITIONAL_PROMOTE = "CONDITIONAL_PROMOTE"
SELECTOR_VERDICT_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def filter_alphas_by_recovery_mode(
    alpha_cols: List[str],
    recovery_report: "AlphaRecoveryReport",
    mode: str = RESEARCH_POOL_FULL,
) -> List[str]:
    """Filter alpha list by recovery pool mode.

    GATE: RECOVERY_SELECTOR_OPT_IN_20260614

    PIT Safety
    ----------
    Uses only recovery classifications derived from OOS fold-level metrics.
    No new data access or look-ahead.

    Parameters
    ----------
    alpha_cols : list of str
        Full alpha column names.
    recovery_report : AlphaRecoveryReport
        Recovery diagnostics report with classification lists.
    mode : str
        One of ``RESEARCH_POOL_FULL``, ``RESEARCH_POOL_RECOVERY_ONLY``,
        ``RESEARCH_POOL_RECOVERABLE_ONLY``.

    Returns
    -------
    list of str
        Filtered alpha names.  For ``full`` mode, returns the input
        unchanged.  For other modes, filters based on recovery
        classification.

    Raises
    ------
    ValueError
        If *mode* is not a valid research pool mode.
    """
    if mode not in VALID_RESEARCH_POOL_MODES:
        valid = ", ".join(VALID_RESEARCH_POOL_MODES)
        raise ValueError(
            f"Unknown research_pool_mode '{mode}'. Valid modes: {valid}"
        )

    if mode == RESEARCH_POOL_FULL:
        return list(alpha_cols)

    if mode == RESEARCH_POOL_RECOVERY_ONLY:
        # Exclude CONFIRMED_RETIRE — keep RECOVERABLE + RESEARCH_ONLY
        exclude = set(recovery_report.confirmed_retire)
        return [a for a in alpha_cols if a not in exclude]

    if mode == RESEARCH_POOL_RECOVERABLE_ONLY:
        # Keep only RECOVERABLE
        keep = set(recovery_report.recoverable_candidates)
        return [a for a in alpha_cols if a in keep]

    return list(alpha_cols)  # unreachable, but safe fallback


def compute_selector_ready_verdict(
    full_pool_mean_ic: float,
    full_pool_positive_fold_rate: float,
    recovery_pool_mean_ic: float,
    recovery_pool_positive_fold_rate: float,
    *,
    ic_improvement_threshold: float = 0.001,
    fold_rate_improvement_threshold: float = 0.0,
) -> str:
    """Compute selector-ready verdict from full vs recovery pool A/B metrics.

    GATE: RECOVERY_SELECTOR_OPT_IN_20260614

    The A/B showed recovery-only pool improves mean IC but does NOT improve
    positive fold rate.  This function codifies that finding:

    - DO_NOT_PROMOTE: mean IC improved but positive fold rate did NOT.
    - CONDITIONAL_PROMOTE: both mean IC and positive fold rate improved.
    - INSUFFICIENT_EVIDENCE: no meaningful improvement in either metric.

    PIT Safety
    ----------
    Uses only aggregate metrics already computed from OOS data.

    Parameters
    ----------
    full_pool_mean_ic : float
        Mean fold IC for the full alpha pool.
    full_pool_positive_fold_rate : float
        Positive IC fold rate for the full pool.
    recovery_pool_mean_ic : float
        Mean fold IC for the recovery-only pool.
    recovery_pool_positive_fold_rate : float
        Positive IC fold rate for the recovery-only pool.
    ic_improvement_threshold : float
        Minimum IC delta to count as improvement (default 0.001).
    fold_rate_improvement_threshold : float
        Minimum fold rate delta to count as improvement (default 0.0).

    Returns
    -------
    str
        One of: DO_NOT_PROMOTE, CONDITIONAL_PROMOTE, INSUFFICIENT_EVIDENCE.
    """
    ic_delta = recovery_pool_mean_ic - full_pool_mean_ic
    fold_rate_delta = recovery_pool_positive_fold_rate - full_pool_positive_fold_rate

    ic_improved = ic_delta > ic_improvement_threshold
    fold_rate_improved = fold_rate_delta > fold_rate_improvement_threshold

    if ic_improved and fold_rate_improved:
        return SELECTOR_VERDICT_CONDITIONAL_PROMOTE
    if ic_improved and not fold_rate_improved:
        return SELECTOR_VERDICT_DO_NOT_PROMOTE
    return SELECTOR_VERDICT_INSUFFICIENT_EVIDENCE


# Neutral fallback value used when a component is not safely computable
_NEUTRAL_SCORE = 0.5

# ---------------------------------------------------------------------------
# Research Alpha Gate Verdicts (GATE: RESEARCH_ALPHA_GATES_20260614)
# ---------------------------------------------------------------------------
# Verdicts classify each alpha for promotion decisions:
#   PROMOTE_CANDIDATE — strong IC, high ICIR, consistent sign, passes BH-FDR
#   ENSEMBLE_ONLY     — positive IC but marginal ICIR or sign consistency
#   REVIEW            — weak signal, needs further investigation
#   RETIRE            — negative or statistically indistinguishable from noise
RESEARCH_VERDICT_PROMOTE_CANDIDATE = "PROMOTE_CANDIDATE"
RESEARCH_VERDICT_ENSEMBLE_ONLY = "ENSEMBLE_ONLY"
RESEARCH_VERDICT_REVIEW = "REVIEW"
RESEARCH_VERDICT_RETIRE = "RETIRE"

# Default thresholds for research gate verdicts
DEFAULT_MIN_ICIR_PROMOTE: float = 0.5
DEFAULT_MIN_ICIR_ENSEMBLE: float = 0.3
DEFAULT_MIN_POS_FOLD_RATE_PROMOTE: float = 0.6
DEFAULT_MIN_POS_FOLD_RATE_ENSEMBLE: float = 0.4
DEFAULT_BH_FDR_ALPHA: float = 0.05

# Minimum daily IC samples for IC stability
_MIN_DAILY_IC_SAMPLES = 10

# Default tolerance for portfolio guard underperformance check.
# Selected basket IC must not fall below baseline IC by more than this
# absolute amount.  E.g. tolerance=0.005 means selected can be up to 0.005
# worse than baseline before triggering fallback.
DEFAULT_PORTFOLIO_GUARD_UNDERPERFORMANCE_TOLERANCE: float = 0.005


# ---------------------------------------------------------------------------
# Preset resolution
# ---------------------------------------------------------------------------
def get_preset_weights(preset: str) -> Dict[str, float]:
    """Return weight dict for *preset* name.

    Parameters
    ----------
    preset : str
        One of the keys in ``PRESETS`` (e.g. ``"balanced"``,
        ``"alpha_recovery"``, ``"drawdown_guarded"``).

    Returns
    -------
    dict
        Component weights summing to 1.0.

    Raises
    ------
    ValueError
        If *preset* is not a known preset name.
    """
    if preset not in PRESETS:
        valid = ", ".join(sorted(PRESETS.keys()))
        raise ValueError(
            f"Unknown risk-adjusted preset '{preset}'. "
            f"Valid presets: {valid}"
        )
    weights = PRESETS[preset]
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(
            f"Preset '{preset}' weights do not sum to 1.0 (got {total:.6f})"
        )
    return dict(weights)  # return a copy


def list_presets() -> List[str]:
    """Return sorted list of available preset names."""
    return sorted(PRESETS.keys())


def get_preset_rank_components(preset: str) -> Dict[str, List[str]]:
    """Return primary-rank and soft-penalty component lists for *preset*.

    For ``ic_first_guarded``, returns the explicit primary/soft split.
    For other presets, all components are treated uniformly (returned in
    ``primary`` with an empty ``soft`` list).

    Returns
    -------
    dict with keys ``"primary_rank_components"`` and
    ``"soft_penalty_components"``, each a list of component name strings.
    """
    if preset == "ic_first_guarded":
        return {
            "primary_rank_components": list(IC_FIRST_PRIMARY_COMPONENTS),
            "soft_penalty_components": list(IC_FIRST_SOFT_PENALTY_COMPONENTS),
        }
    # Uniform presets: all components are rank-relevant
    return {
        "primary_rank_components": list(DEFAULT_WEIGHTS.keys()),
        "soft_penalty_components": [],
    }


# ---------------------------------------------------------------------------
# Data class for per-alpha score breakdown
# ---------------------------------------------------------------------------
@dataclass
class AlphaScoreBreakdown:
    """Score breakdown for a single alpha candidate."""
    alpha_name: str
    composite_score: float = 0.0
    # Raw component scores (each in [0, 1] before weighting)
    validation_ic_score: float = _NEUTRAL_SCORE
    ic_stability_score: float = _NEUTRAL_SCORE
    expected_sharpe_score: float = _NEUTRAL_SCORE
    turnover_penalty_score: float = _NEUTRAL_SCORE
    drawdown_penalty_score: float = _NEUTRAL_SCORE
    overfit_gap_score: float = _NEUTRAL_SCORE
    # Raw values (before normalisation)
    raw_validation_ic: float = 0.0
    raw_ic_sharpe: float = 0.0
    raw_turnover: float = 0.0
    raw_overfit_gap: float = 0.0
    raw_max_drawdown: float = 0.0
    raw_expected_sharpe: float = 0.0
    # Flags
    sharpe_available: bool = False
    drawdown_available: bool = False
    # Verdict
    selected: bool = False
    rejection_reason: str = ""


@dataclass
class RiskAdjustedSelectionResult:
    """Full selection result with evidence for paper-trading gate."""
    selected_alphas: List[str] = field(default_factory=list)
    rejected_alphas: List[str] = field(default_factory=list)
    score_breakdowns: Dict[str, AlphaScoreBreakdown] = field(default_factory=dict)
    paper_trading_gate: str = "FAIL"
    paper_trading_reasons: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        result: dict = {
            "selected_alphas": self.selected_alphas,
            "rejected_alphas": self.rejected_alphas,
            "paper_trading_gate": self.paper_trading_gate,
            "paper_trading_reasons": self.paper_trading_reasons,
            "config": self.config,
            "score_breakdowns": {},
        }
        for name, bd in self.score_breakdowns.items():
            result["score_breakdowns"][name] = {
                "composite_score": round(bd.composite_score, 6),
                "validation_ic_score": round(bd.validation_ic_score, 6),
                "ic_stability_score": round(bd.ic_stability_score, 6),
                "expected_sharpe_score": round(bd.expected_sharpe_score, 6),
                "turnover_penalty_score": round(bd.turnover_penalty_score, 6),
                "drawdown_penalty_score": round(bd.drawdown_penalty_score, 6),
                "overfit_gap_score": round(bd.overfit_gap_score, 6),
                "raw_validation_ic": round(bd.raw_validation_ic, 6),
                "raw_ic_sharpe": round(bd.raw_ic_sharpe, 6),
                "raw_turnover": round(bd.raw_turnover, 6),
                "raw_overfit_gap": round(bd.raw_overfit_gap, 6),
                "raw_max_drawdown": round(bd.raw_max_drawdown, 6),
                "raw_expected_sharpe": round(bd.raw_expected_sharpe, 6),
                "sharpe_available": bd.sharpe_available,
                "drawdown_available": bd.drawdown_available,
                "selected": bd.selected,
                "rejection_reason": bd.rejection_reason,
            }
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# Portfolio-level validation guard (GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614)
# ---------------------------------------------------------------------------
@dataclass
class PortfolioGuardResult:
    """Result of portfolio-level validation guard.

    After risk-adjusted alphas are selected and before final signal
    construction, this guard computes the combined basket's validation IC
    on the validation slice and decides whether to accept the risk-adjusted
    basket or fall back to the baseline/fallback basket.

    Attributes
    ----------
    portfolio_guard_enabled : bool
        Always True when the guard was executed.
    portfolio_guard_status : str
        ``"ACCEPTED"`` if risk-adjusted basket passed; ``"FALLBACK_TO_BASELINE"``
        if the guard triggered fallback.
    selected_basket_validation_ic : float
        Spearman IC of the risk-adjusted selected basket signal on validation
        data.  Computed as the IC of an IC-weighted combined signal.
    baseline_basket_validation_ic : float or None
        Spearman IC of the baseline/fallback basket signal on validation data.
        None when no baseline is available for comparison.
    guard_reason : str
        Human-readable explanation of the guard decision.
    selected_alphas : list of str
        Alpha names in the *effective* basket (after guard decision).
    rejected_risk_adjusted_evidence : dict or None
        When fallback is triggered, contains the rejected risk-adjusted
        selection evidence for audit.  None when ACCEPTED.
    """
    portfolio_guard_enabled: bool = True
    portfolio_guard_status: str = "ACCEPTED"
    selected_basket_validation_ic: float = 0.0
    baseline_basket_validation_ic: Optional[float] = None
    guard_reason: str = ""
    selected_alphas: List[str] = field(default_factory=list)
    rejected_risk_adjusted_evidence: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "portfolio_guard_enabled": self.portfolio_guard_enabled,
            "portfolio_guard_status": self.portfolio_guard_status,
            "selected_basket_validation_ic": round(
                self.selected_basket_validation_ic, 6
            ),
            "baseline_basket_validation_ic": (
                round(self.baseline_basket_validation_ic, 6)
                if self.baseline_basket_validation_ic is not None
                else None
            ),
            "guard_reason": self.guard_reason,
            "selected_alphas": list(self.selected_alphas),
            "rejected_risk_adjusted_evidence": self.rejected_risk_adjusted_evidence,
        }


def compute_basket_validation_ic(
    alpha_cols: List[str],
    val_df: pd.DataFrame,
    train_ics: Dict[str, float],
    return_col: str = "fwd_ret_5",
) -> float:
    """Compute basket-level validation IC for a set of alpha columns.

    Builds an IC-weighted combined signal from *alpha_cols* using
    *train_ics* as weights, then computes Spearman IC against
    *return_col* on the validation DataFrame.

    PIT Safety
    ----------
    All inputs must come from validation-period data only.  *train_ics*
    are weights derived from training data; the signal itself is computed
    on *val_df* and the IC is measured on *val_df*.  No test-set data.

    Parameters
    ----------
    alpha_cols : list of str
        Alpha column names present in val_df.
    val_df : pd.DataFrame
        Validation data with alpha columns, return_col, date, ticker.
    train_ics : dict
        Per-alpha IC used as combination weights (from training set).
    return_col : str
        Forward return column name.

    Returns
    -------
    float
        Spearman IC of the combined basket signal with forward returns.
        Returns 0.0 if computation fails or insufficient data.
    """
    if not alpha_cols or val_df.empty:
        return 0.0
    if return_col not in val_df.columns:
        return 0.0

    # Filter to alpha columns actually present in val_df
    avail = [c for c in alpha_cols if c in val_df.columns]
    if not avail:
        return 0.0

    # Build IC-weighted signal (same logic as compute_portfolio_signal in phase35)
    weights = np.array([train_ics.get(c, 0.0) for c in avail])
    weight_sum = np.abs(weights).sum()
    if weight_sum > 0:
        weights = weights / weight_sum
    else:
        weights = np.ones(len(weights)) / len(weights)

    # Per-alpha z-score normalization (cross-sectional per date)
    df_norm = val_df[avail].copy()
    for col in avail:
        df_norm[col] = val_df.groupby("date")[col].transform(
            lambda x: (x - x.mean()) / (x.std() + 1e-9)
        )

    alpha_matrix = df_norm[avail].values
    basket_signal = alpha_matrix @ weights

    signal_series = pd.Series(basket_signal, index=val_df.index)
    ret_series = val_df[return_col]

    mask = ~(signal_series.isna() | ret_series.isna())
    if mask.sum() < 10:
        return 0.0

    try:
        ic, _ = spearmanr(signal_series[mask].values, ret_series[mask].values)
        return _safe_float(ic)
    except Exception:
        return 0.0


def evaluate_portfolio_guard(
    ra_result: RiskAdjustedSelectionResult,
    *,
    val_df: pd.DataFrame,
    train_ics: Dict[str, float],
    return_col: str = "fwd_ret_5",
    baseline_alpha_cols: Optional[List[str]] = None,
    baseline_train_ics: Optional[Dict[str, float]] = None,
    underperformance_tolerance: float = DEFAULT_PORTFOLIO_GUARD_UNDERPERFORMANCE_TOLERANCE,
) -> PortfolioGuardResult:
    """Evaluate portfolio-level validation guard for risk-adjusted selection.

    GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_20260614

    After risk-adjusted alpha selection, computes the selected basket's
    validation IC on the validation slice.  Accepts the risk-adjusted
    basket only if:

    1. Selected basket validation IC > 0 (positive predictive power).
    2. Selected basket validation IC does not materially underperform
       the baseline/fallback basket validation IC by more than
       *underperformance_tolerance* (when baseline is available).

    If the guard fails, the caller should fall back to the baseline
    alpha basket and persist the rejected risk-adjusted evidence.

    PIT Safety
    ----------
    Only validation-period data is used.  No test-set data.

    Parameters
    ----------
    ra_result : RiskAdjustedSelectionResult
        Risk-adjusted selection result with selected_alphas.
    val_df : pd.DataFrame
        Embargoed validation data.
    train_ics : dict
        Per-alpha IC from training set (used as combination weights).
    return_col : str
        Forward return column name.
    baseline_alpha_cols : list of str, optional
        Baseline/fallback alpha column names.  If None, baseline
        comparison is skipped.
    baseline_train_ics : dict, optional
        Per-alpha IC for the baseline basket.  If None, uses *train_ics*.
    underperformance_tolerance : float
        Maximum allowed IC underperformance vs baseline (absolute).

    Returns
    -------
    PortfolioGuardResult
    """
    guard = PortfolioGuardResult(portfolio_guard_enabled=True)

    selected_cols = ra_result.selected_alphas
    if not selected_cols:
        guard.portfolio_guard_status = "FALLBACK_TO_BASELINE"
        guard.selected_basket_validation_ic = 0.0
        guard.guard_reason = (
            "Risk-adjusted selection produced no selected alphas"
        )
        guard.rejected_risk_adjusted_evidence = ra_result.to_dict()
        if baseline_alpha_cols:
            bl_ics = baseline_train_ics if baseline_train_ics is not None else train_ics
            guard.baseline_basket_validation_ic = compute_basket_validation_ic(
                baseline_alpha_cols, val_df, bl_ics, return_col
            )
            guard.selected_alphas = list(baseline_alpha_cols)
        else:
            guard.selected_alphas = []
        return guard

    # Compute selected basket validation IC
    selected_ic = compute_basket_validation_ic(
        selected_cols, val_df, train_ics, return_col
    )
    guard.selected_basket_validation_ic = selected_ic

    # Compute baseline basket validation IC if available
    baseline_ic: Optional[float] = None
    if baseline_alpha_cols:
        bl_ics = baseline_train_ics if baseline_train_ics is not None else train_ics
        baseline_ic = compute_basket_validation_ic(
            baseline_alpha_cols, val_df, bl_ics, return_col
        )
    guard.baseline_basket_validation_ic = baseline_ic

    # Decision logic
    # Condition 1: selected basket IC must be positive
    if selected_ic <= 0.0:
        guard.portfolio_guard_status = "FALLBACK_TO_BASELINE"
        guard.guard_reason = (
            f"Selected basket validation IC={selected_ic:.4f} is non-positive"
        )
        guard.rejected_risk_adjusted_evidence = ra_result.to_dict()
        if baseline_alpha_cols:
            guard.selected_alphas = list(baseline_alpha_cols)
        else:
            guard.selected_alphas = []
        return guard

    # Condition 2: must not materially underperform baseline
    if baseline_ic is not None:
        underperformance = baseline_ic - selected_ic
        if underperformance > underperformance_tolerance:
            guard.portfolio_guard_status = "FALLBACK_TO_BASELINE"
            guard.guard_reason = (
                f"Selected basket IC={selected_ic:.4f} underperforms "
                f"baseline IC={baseline_ic:.4f} by {underperformance:.4f} "
                f"(tolerance={underperformance_tolerance})"
            )
            guard.rejected_risk_adjusted_evidence = ra_result.to_dict()
            guard.selected_alphas = list(baseline_alpha_cols)
            return guard

    # Guard passed
    guard.portfolio_guard_status = "ACCEPTED"
    guard.guard_reason = (
        f"Selected basket IC={selected_ic:.4f} > 0"
        + (
            f", baseline IC={baseline_ic:.4f}, "
            f"within tolerance={underperformance_tolerance}"
            if baseline_ic is not None
            else ""
        )
    )
    guard.selected_alphas = list(selected_cols)
    return guard


# ---------------------------------------------------------------------------
# Safe math helpers
# ---------------------------------------------------------------------------
def _safe_float(val: Any, default: float = 0.0) -> float:
    """Convert to float safely, returning *default* on NaN / non-numeric."""
    if val is None:
        return default
    try:
        f = float(val)
        return f if not (math.isnan(f) or math.isinf(f)) else default
    except (TypeError, ValueError):
        return default


def _clamp01(val: float) -> float:
    """Clamp a value to [0, 1]."""
    return max(0.0, min(1.0, val))


def _ic_to_score(ic: float) -> float:
    """Map raw IC ∈ [-1, 1] to score ∈ [0, 1].

    Linear map: score = (ic + 1) / 2, clamped to [0, 1].
    """
    return _clamp01((ic + 1.0) / 2.0)


def _ic_sharpe_to_score(ic_sharpe: float) -> float:
    """Map IC Sharpe to score ∈ [0, 1].

    Uses sigmoid-like mapping: score = 1 / (1 + exp(-2 * ic_sharpe))
    so ic_sharpe=0 → 0.5, ic_sharpe=1 → ~0.88, ic_sharpe=-1 → ~0.12.
    """
    return _clamp01(1.0 / (1.0 + math.exp(-2.0 * ic_sharpe)))


def _turnover_to_score(turnover: float) -> float:
    """Map turnover ∈ [0, 1] to penalty score ∈ [0, 1].

    Low turnover → high score.  Linear inversion: score = 1 - turnover.
    """
    return _clamp01(1.0 - _clamp01(turnover))


def _overfit_gap_to_score(gap: float) -> float:
    """Map |train_IC - val_IC| gap to score ∈ [0, 1].

    gap=0 → 1.0, gap=1 → 0.0, clamped.
    """
    return _clamp01(1.0 - abs(gap))


# ---------------------------------------------------------------------------
# Core computation functions
# ---------------------------------------------------------------------------
def compute_validation_ic(
    alpha_values: pd.Series,
    returns: pd.Series,
    min_pairs: int = 10,
) -> float:
    """Compute Spearman IC on validation (embargoed) data.

    PIT-safe: caller is responsible for passing only embargoed data.
    """
    mask = ~(alpha_values.isna() | returns.isna())
    if mask.sum() < min_pairs:
        return 0.0
    try:
        ic, _ = spearmanr(alpha_values[mask].values, returns[mask].values)
        return _safe_float(ic)
    except Exception:
        return 0.0


def compute_ic_stability(
    daily_ics: pd.Series,
    min_samples: int = _MIN_DAILY_IC_SAMPLES,
) -> float:
    """Compute IC Sharpe = mean(daily_ics) / (std(daily_ics) + eps).

    Returns 0.0 if fewer than *min_samples* non-NaN values.
    """
    clean = daily_ics.dropna()
    if len(clean) < min_samples:
        return 0.0
    mean_ic = clean.mean()
    std_ic = clean.std()
    if std_ic < 1e-12:
        return _safe_float(mean_ic * 10.0)  # constant IC → large Sharpe
    return _safe_float(mean_ic / std_ic)


def estimate_turnover(
    df: pd.DataFrame,
    alpha_col: str,
) -> float:
    """Estimate day-over-day rank turnover for *alpha_col* in [0, 1].

    Returns conservative 0.5 if insufficient data.
    """
    if alpha_col not in df.columns:
        return 0.5
    dates = sorted(df["date"].unique())
    if len(dates) < 2:
        return 0.5
    try:
        pivot = df.pivot(index="date", columns="ticker", values=alpha_col)
        ranks = pivot.rank(axis=1, pct=True)
        diffs = ranks.diff(axis=0).abs()
        mean_diff = diffs.mean(axis=1).mean()
        if pd.isna(mean_diff):
            return 0.5
        return float(np.clip(mean_diff, 0.0, 1.0))
    except Exception:
        return 0.5


def compute_overfit_gap(
    train_ic: float,
    validation_ic: float,
) -> float:
    """Compute |train_IC - validation_IC|.

    A large gap suggests overfitting.
    """
    return abs(_safe_float(train_ic) - _safe_float(validation_ic))


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------
def compute_composite_score(
    alpha_name: str,
    *,
    validation_ic: float,
    ic_sharpe: float,
    turnover: float,
    overfit_gap: float,
    expected_sharpe: Optional[float] = None,
    max_drawdown: Optional[float] = None,
    weights: Optional[Dict[str, float]] = None,
) -> AlphaScoreBreakdown:
    """Compute composite risk-adjusted score for a single alpha.

    Parameters
    ----------
    alpha_name : str
        Alpha identifier.
    validation_ic : float
        Spearman IC on embargoed validation set.
    ic_sharpe : float
        IC Sharpe ratio (mean/std of daily IC series).
    turnover : float
        Day-over-day rank turnover in [0, 1].
    overfit_gap : float
        |train_IC - val_IC|.
    expected_sharpe : float, optional
        Expected Sharpe contribution if safely available.
    max_drawdown : float, optional
        Maximum drawdown (negative value) if safely available.
    weights : dict, optional
        Component weights (defaults to ``DEFAULT_WEIGHTS``).

    Returns
    -------
    AlphaScoreBreakdown
    """
    w = weights or DEFAULT_WEIGHTS

    bd = AlphaScoreBreakdown(alpha_name=alpha_name)

    # 1. Validation IC
    bd.raw_validation_ic = _safe_float(validation_ic)
    bd.validation_ic_score = _ic_to_score(bd.raw_validation_ic)

    # 2. IC Stability
    bd.raw_ic_sharpe = _safe_float(ic_sharpe)
    bd.ic_stability_score = _ic_sharpe_to_score(bd.raw_ic_sharpe)

    # 3. Expected Sharpe Contribution
    if expected_sharpe is not None and not (math.isnan(expected_sharpe) or math.isinf(expected_sharpe)):
        bd.sharpe_available = True
        bd.raw_expected_sharpe = float(expected_sharpe)
        # Map Sharpe: sigmoid centred at 0, scale factor 1
        bd.expected_sharpe_score = _clamp01(1.0 / (1.0 + math.exp(-1.0 * bd.raw_expected_sharpe)))
    else:
        bd.sharpe_available = False
        bd.expected_sharpe_score = _NEUTRAL_SCORE

    # 4. Turnover Penalty
    bd.raw_turnover = _clamp01(_safe_float(turnover, 0.5))
    bd.turnover_penalty_score = _turnover_to_score(bd.raw_turnover)

    # 5. Drawdown Penalty
    if max_drawdown is not None and not (math.isnan(max_drawdown) or math.isinf(max_drawdown)):
        bd.drawdown_available = True
        bd.raw_max_drawdown = float(max_drawdown)
        # max_drawdown is typically negative; less negative → better
        # Map: score = 1 + max_drawdown (clamped), so dd=-0.1 → 0.9, dd=-0.5 → 0.5
        bd.drawdown_penalty_score = _clamp01(1.0 + bd.raw_max_drawdown)
    else:
        bd.drawdown_available = False
        bd.drawdown_penalty_score = _NEUTRAL_SCORE

    # 6. Overfit Gap
    bd.raw_overfit_gap = _safe_float(overfit_gap)
    bd.overfit_gap_score = _overfit_gap_to_score(bd.raw_overfit_gap)

    # Redistribute weight from unavailable components to available ones
    active_weights: Dict[str, float] = {}
    neutral_components: List[str] = []

    component_map = {
        "validation_ic": bd.validation_ic_score,
        "ic_stability": bd.ic_stability_score,
        "expected_sharpe": bd.expected_sharpe_score,
        "turnover_penalty": bd.turnover_penalty_score,
        "drawdown_penalty": bd.drawdown_penalty_score,
        "overfit_gap": bd.overfit_gap_score,
    }

    for comp, weight in w.items():
        is_available = True
        if comp == "expected_sharpe" and not bd.sharpe_available:
            is_available = False
        elif comp == "drawdown_penalty" and not bd.drawdown_available:
            is_available = False

        if is_available:
            active_weights[comp] = weight
        else:
            neutral_components.append(comp)

    # Renormalise active weights to sum to 1.0
    total_active = sum(active_weights.values())
    if total_active > 1e-12:
        for comp in active_weights:
            active_weights[comp] /= total_active

    # Compute weighted composite
    composite = 0.0
    for comp, weight in active_weights.items():
        composite += weight * component_map[comp]

    bd.composite_score = round(_clamp01(composite), 6)
    return bd


# ---------------------------------------------------------------------------
# Batch scoring
# ---------------------------------------------------------------------------
def score_alpha_candidates(
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
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, AlphaScoreBreakdown]:
    """Score all alpha candidates with risk-adjusted composite.

    PIT Safety
    ----------
    All data passed here must be from train/validation periods ONLY.
    No test-set data should appear in any of the arguments.

    Parameters
    ----------
    alpha_cols : list of str
        Alpha column names present in train_df / val_df.
    train_df : pd.DataFrame
        Embargoed training data (with alpha columns, date, ticker).
    val_df : pd.DataFrame
        Embargoed validation data (with alpha columns, date, ticker).
    train_ics : dict
        Per-alpha IC computed on training set.
    val_ics : dict, optional
        Per-alpha IC computed on validation set.  If None, computed here.
    daily_ics : dict, optional
        Per-alpha daily IC series (for IC stability).  If None, computed here.
    expected_sharpe_contrib : dict, optional
        Per-alpha expected Sharpe contribution (if safely available).
    max_drawdowns : dict, optional
        Per-alpha max drawdown (if safely available).
    return_col : str
        Forward return column name.
    weights : dict, optional
        Component weights.

    Returns
    -------
    dict mapping alpha name → AlphaScoreBreakdown
    """
    break_downs: Dict[str, AlphaScoreBreakdown] = {}

    # Compute val_ics if not provided
    if val_ics is None:
        val_ics = {}
        for col in alpha_cols:
            if col in val_df.columns and return_col in val_df.columns:
                val_ics[col] = compute_validation_ic(
                    val_df[col], val_df[return_col]
                )
            else:
                val_ics[col] = 0.0

    # Compute daily ICs if not provided
    if daily_ics is None:
        daily_ics = _compute_daily_cs_ics(val_df, alpha_cols, return_col)

    for col in alpha_cols:
        v_ic = val_ics.get(col, 0.0)
        t_ic = train_ics.get(col, 0.0)
        d_ics = daily_ics.get(col, pd.Series(dtype=float))
        ic_sharpe = compute_ic_stability(d_ics)
        turnover = estimate_turnover(train_df, col)
        gap = compute_overfit_gap(t_ic, v_ic)
        es = expected_sharpe_contrib.get(col) if expected_sharpe_contrib else None
        mdd = max_drawdowns.get(col) if max_drawdowns else None

        bd = compute_composite_score(
            col,
            validation_ic=v_ic,
            ic_sharpe=ic_sharpe,
            turnover=turnover,
            overfit_gap=gap,
            expected_sharpe=es,
            max_drawdown=mdd,
            weights=weights,
        )
        break_downs[col] = bd

    return break_downs


def _compute_daily_cs_ics(
    df: pd.DataFrame,
    alpha_cols: List[str],
    return_col: str,
    min_cross_section: int = 5,
) -> Dict[str, pd.Series]:
    """Compute per-date cross-sectional IC for each alpha.

    Returns dict mapping alpha name → Series(index=date, values=ic).
    """
    if return_col not in df.columns:
        return {col: pd.Series(dtype=float) for col in alpha_cols}

    avail = [c for c in alpha_cols if c in df.columns]
    if not avail:
        return {col: pd.Series(dtype=float) for col in alpha_cols}

    def _daily_ics(group: pd.DataFrame) -> pd.Series:
        ret = group[return_col]
        ics = {}
        for alpha in avail:
            mask = ~(group[alpha].isna() | ret.isna())
            if mask.sum() < min_cross_section:
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

    ic_df = df.groupby("date").apply(_daily_ics, include_groups=False)

    result: Dict[str, pd.Series] = {}
    for col in alpha_cols:
        if col in ic_df.columns:
            result[col] = ic_df[col]
        else:
            result[col] = pd.Series(dtype=float)
    return result


# ---------------------------------------------------------------------------
# Selection with paper-trading gate
# ---------------------------------------------------------------------------
def select_alphas_risk_adjusted(
    score_breakdowns: Dict[str, AlphaScoreBreakdown],
    *,
    top_n: int = 5,
    min_composite_score: float = 0.35,
    require_positive_val_ic: bool = True,
    max_overfit_gap: float = 0.15,
) -> RiskAdjustedSelectionResult:
    """Select top alphas by composite score with paper-trading gate.

    Parameters
    ----------
    score_breakdowns : dict
        Mapping of alpha name → AlphaScoreBreakdown.
    top_n : int
        Maximum number of alphas to select.
    min_composite_score : float
        Minimum composite score to be eligible.
    require_positive_val_ic : bool
        If True, reject alphas with non-positive validation IC.
    max_overfit_gap : float
        Maximum allowed overfit gap (|train_IC - val_IC|).

    Returns
    -------
    RiskAdjustedSelectionResult
    """
    result = RiskAdjustedSelectionResult()

    eligible: List[tuple] = []
    rejected: List[str] = []

    for name, bd in score_breakdowns.items():
        reasons: List[str] = []

        if bd.composite_score < min_composite_score:
            reasons.append(
                f"composite_score={bd.composite_score:.4f} < min={min_composite_score}"
            )
        if require_positive_val_ic and bd.raw_validation_ic <= 0.0:
            reasons.append(f"validation_ic={bd.raw_validation_ic:.4f} <= 0")
        if bd.raw_overfit_gap > max_overfit_gap:
            reasons.append(
                f"overfit_gap={bd.raw_overfit_gap:.4f} > max={max_overfit_gap}"
            )

        if reasons:
            bd.selected = False
            bd.rejection_reason = "; ".join(reasons)
            rejected.append(name)
        else:
            eligible.append((name, bd.composite_score))

    # Sort by composite score descending
    eligible.sort(key=lambda x: x[1], reverse=True)

    # Select top N
    selected_names = [name for name, _ in eligible[:top_n]]
    for name, _ in eligible[:top_n]:
        score_breakdowns[name].selected = True

    # Additional rejected (eligible but beyond top_n)
    for name, _ in eligible[top_n:]:
        score_breakdowns[name].selected = False
        score_breakdowns[name].rejection_reason = "beyond top_n"
        rejected.append(name)

    result.selected_alphas = selected_names
    result.rejected_alphas = rejected
    result.score_breakdowns = score_breakdowns

    # Paper-trading gate
    gate_reasons: List[str] = []
    if not selected_names:
        gate_reasons.append("No alphas selected by risk-adjusted composite")
    if len(selected_names) < 1:
        gate_reasons.append("Need at least 1 alpha for paper-trading")

    # Check that at least one selected alpha has positive validation IC
    if selected_names:
        best_bd = score_breakdowns[selected_names[0]]
        if best_bd.raw_validation_ic <= 0.0:
            gate_reasons.append(
                f"Best alpha '{selected_names[0]}' has non-positive val IC"
            )

    if gate_reasons:
        result.paper_trading_gate = "FAIL"
        result.paper_trading_reasons = gate_reasons
    else:
        result.paper_trading_gate = "PASS"
        result.paper_trading_reasons = [
            f"{len(selected_names)} alphas selected with positive val IC and "
            f"composite >= {min_composite_score}"
        ]

    return result


# ---------------------------------------------------------------------------
# Evidence persistence
# ---------------------------------------------------------------------------
def save_evidence(
    result: RiskAdjustedSelectionResult,
    output_path: str | Path,
) -> Path:
    """Persist selection evidence as JSON.

    Parameters
    ----------
    result : RiskAdjustedSelectionResult
    output_path : str or Path

    Returns
    -------
    Path
        Path to written JSON file.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.to_json(indent=2), encoding="utf-8")
    logger.info(f"Risk-adjusted selection evidence saved to: {path}")
    return path


# ---------------------------------------------------------------------------
# Research Alpha Gate Utilities (GATE: RESEARCH_ALPHA_GATES_20260614)
# ---------------------------------------------------------------------------
def compute_icir(ic_series: Sequence[float]) -> float:
    """Compute Information Coefficient Information Ratio (ICIR).

    ICIR = mean(IC) / std(IC)

    A higher ICIR indicates a more consistent predictive signal.

    Parameters
    ----------
    ic_series : sequence of float
        Per-fold or per-period IC values.

    Returns
    -------
    float
        ICIR value. Returns 0.0 if fewer than 2 samples or std is zero.
    """
    vals = [v for v in ic_series if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if len(vals) < 2:
        return 0.0
    mean_ic = sum(vals) / len(vals)
    variance = sum((v - mean_ic) ** 2 for v in vals) / (len(vals) - 1)
    std_ic = math.sqrt(variance)
    if std_ic < 1e-12:
        return 0.0
    return mean_ic / std_ic


def compute_positive_fold_rate(ic_series: Sequence[float]) -> float:
    """Compute the fraction of folds with positive IC.

    Parameters
    ----------
    ic_series : sequence of float
        Per-fold IC values.

    Returns
    -------
    float
        Fraction of folds with IC > 0. Returns 0.0 if empty.
    """
    vals = [v for v in ic_series if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not vals:
        return 0.0
    return sum(1 for v in vals if v > 0) / len(vals)


def bh_fdr_qvalues(p_values: Sequence[float]) -> List[float]:
    """Compute Benjamini-Hochberg FDR adjusted q-values.

    Implements the BH step-up procedure for multiple testing correction.

    Parameters
    ----------
    p_values : sequence of float
        Raw p-values from individual hypothesis tests.

    Returns
    -------
    list of float
        BH-FDR adjusted q-values, same order as input.
    """
    n = len(p_values)
    if n == 0:
        return []
    if n == 1:
        return [min(p_values[0], 1.0)]

    # Create indexed pairs and sort by p-value ascending
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])

    # Compute adjusted values: q_i = p_i * n / rank_i
    q_values = [0.0] * n
    for rank_minus_1, (orig_idx, p_val) in enumerate(indexed):
        rank = rank_minus_1 + 1
        q_values[orig_idx] = min(p_val * n / rank, 1.0)

    # Enforce monotonicity from the largest rank downward:
    # q[i] = min(q[i], q[i+1]) when iterating from largest to smallest rank
    # We iterate from the highest rank (last sorted) down
    sorted_indices = [idx for idx, _ in indexed]
    for i in range(n - 2, -1, -1):
        curr_idx = sorted_indices[i]
        next_idx = sorted_indices[i + 1]
        q_values[curr_idx] = min(q_values[curr_idx], q_values[next_idx])

    return q_values


def compute_ic_pvalue(ic_series: Sequence[float]) -> float:
    """Compute two-sided t-test p-value for H0: mean(IC) = 0.

    Parameters
    ----------
    ic_series : sequence of float
        Per-fold or per-period IC values.

    Returns
    -------
    float
        Two-sided p-value. Returns 1.0 if fewer than 3 samples.
    """
    vals = [v for v in ic_series if v is not None and not (isinstance(v, float) and math.isnan(v))]
    n = len(vals)
    if n < 3:
        return 1.0
    mean_ic = sum(vals) / n
    variance = sum((v - mean_ic) ** 2 for v in vals) / (n - 1)
    std_err = math.sqrt(variance / n)
    if std_err < 1e-12:
        # All values identical: if mean != 0, p → 0; if mean == 0, p = 1
        return 0.0 if abs(mean_ic) > 1e-12 else 1.0
    t_stat = mean_ic / std_err
    df = n - 1
    # Approximate two-sided p-value using the survival function of t-distribution.
    # Use a simple approximation based on normal for large df.
    # For |t| > 0, p ≈ 2 * (1 - Phi(|t| * sqrt(df / (df + t^2))))
    # Using the incomplete beta function approximation via the regularized form.
    abs_t = abs(t_stat)
    # Use the relationship: p = 2 * (1 - CDF_t(|t|, df))
    # For practical use with moderate df (>= 2), use the normal approximation
    # with a correction factor.
    x = df / (df + abs_t * abs_t)
    # Regularized incomplete beta function approximation using series expansion
    p_value = _regularized_incomplete_beta(df / 2.0, 0.5, x)
    return min(max(p_value, 0.0), 1.0)


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """Approximate regularized incomplete beta I_x(a, b) for t-test p-value.

    Uses continued fraction expansion (Lentz's method) for numerical stability.
    This is sufficient for the t-test p-value computation where b=0.5.
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    # Use the relationship between beta and gamma for the prefactor
    # I_x(a, b) = x^a * (1-x)^b / (a * B(a,b)) * continued_fraction
    # where B(a,b) = Gamma(a)*Gamma(b)/Gamma(a+b)
    lbeta = (math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b))
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - lbeta) / a

    # Lentz's continued fraction for I_x(a, b)
    max_iter = 200
    eps = 1e-14
    tiny = 1e-30

    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1.0)
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d

    for m in range(1, max_iter + 1):
        # Even step
        m2 = 2 * m
        numerator = m * (b - m) * x / ((a + m2 - 1.0) * (a + m2))
        d = 1.0 + numerator * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + numerator / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c

        # Odd step
        numerator = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1.0))
        d = 1.0 + numerator * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + numerator / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta

        if abs(delta - 1.0) < eps:
            break

    return front * h


def classify_research_gate_verdict(
    mean_ic: float,
    icir: float,
    positive_fold_rate: float,
    q_value: float,
    *,
    fallback_rate: float = 0.0,
    min_icir_promote: float = DEFAULT_MIN_ICIR_PROMOTE,
    min_icir_ensemble: float = DEFAULT_MIN_ICIR_ENSEMBLE,
    min_pos_fold_rate_promote: float = DEFAULT_MIN_POS_FOLD_RATE_PROMOTE,
    min_pos_fold_rate_ensemble: float = DEFAULT_MIN_POS_FOLD_RATE_ENSEMBLE,
    bh_fdr_threshold: float = DEFAULT_BH_FDR_ALPHA,
) -> str:
    """Classify an alpha into a research gate verdict category.

    GATE: RESEARCH_ALPHA_GATES_20260614

    Parameters
    ----------
    mean_ic : float
        Mean OOS IC across folds.
    icir : float
        ICIR = mean(IC) / std(IC).
    positive_fold_rate : float
        Fraction of folds with positive IC.
    q_value : float
        BH-FDR adjusted q-value for the alpha's IC significance test.
    fallback_rate : float
        Fraction of folds where fallback candidates were used (0 to 1).
        High fallback rate reduces confidence in the alpha.
    min_icir_promote : float
        Minimum ICIR for PROMOTE_CANDIDATE verdict.
    min_icir_ensemble : float
        Minimum ICIR for ENSEMBLE_ONLY verdict.
    min_pos_fold_rate_promote : float
        Minimum positive fold rate for PROMOTE_CANDIDATE.
    min_pos_fold_rate_ensemble : float
        Minimum positive fold rate for ENSEMBLE_ONLY.
    bh_fdr_threshold : float
        Maximum q-value for statistical significance.

    Returns
    -------
    str
        One of: PROMOTE_CANDIDATE, ENSEMBLE_ONLY, REVIEW, RETIRE.
    """
    # RETIRE: negative mean IC or fails BH-FDR
    if mean_ic < 0.0:
        return RESEARCH_VERDICT_RETIRE
    if q_value > bh_fdr_threshold:
        return RESEARCH_VERDICT_RETIRE

    # PROMOTE_CANDIDATE: strong ICIR, consistent sign, passes FDR
    if (
        icir >= min_icir_promote
        and positive_fold_rate >= min_pos_fold_rate_promote
        and mean_ic >= 0.02
        and fallback_rate < 0.5
    ):
        return RESEARCH_VERDICT_PROMOTE_CANDIDATE

    # ENSEMBLE_ONLY: positive IC but marginal metrics
    if (
        icir >= min_icir_ensemble
        and positive_fold_rate >= min_pos_fold_rate_ensemble
        and mean_ic > 0.0
    ):
        return RESEARCH_VERDICT_ENSEMBLE_ONLY

    # REVIEW: everything else with non-negative IC
    return RESEARCH_VERDICT_REVIEW


def compute_fallback_as_failure_metrics(
    fold_details: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute fallback-as-failure diagnostics.

    Fallback usage should NOT count as alpha success. This function
    separates fold outcomes into: alpha-selected (gate passed) and
    fallback-used (gate failed), and reports success rates separately.

    Parameters
    ----------
    fold_details : list of dict
        Per-fold detail dicts with keys like 'used_fallback_candidates',
        'portfolio_ic', 'portfolio_sharpe'.

    Returns
    -------
    dict
        Keys: total_folds, alpha_selected_folds, fallback_folds,
        alpha_selected_positive_ic_rate, fallback_positive_ic_rate,
        fallback_as_failure_rate.
    """
    total = len(fold_details)
    if total == 0:
        return {
            "total_folds": 0,
            "alpha_selected_folds": 0,
            "fallback_folds": 0,
            "alpha_selected_positive_ic_rate": 0.0,
            "fallback_positive_ic_rate": 0.0,
            "fallback_as_failure_rate": 0.0,
        }

    alpha_selected_ics: List[float] = []
    fallback_ics: List[float] = []

    for fold in fold_details:
        ic = fold.get("portfolio_ic", 0.0)
        used_fallback = (
            fold.get("used_fallback_candidates", False)
            or fold.get("gate_metadata", {}).get("used_fallback_candidates", False)
        )
        if used_fallback:
            fallback_ics.append(ic)
        else:
            alpha_selected_ics.append(ic)

    n_alpha = len(alpha_selected_ics)
    n_fallback = len(fallback_ics)

    alpha_pos_rate = (
        sum(1 for v in alpha_selected_ics if v > 0) / n_alpha
        if n_alpha > 0
        else 0.0
    )
    fallback_pos_rate = (
        sum(1 for v in fallback_ics if v > 0) / n_fallback
        if n_fallback > 0
        else 0.0
    )

    # Fallback-as-failure rate: fraction of total folds where fallback was used
    fallback_as_failure_rate = n_fallback / total

    return {
        "total_folds": total,
        "alpha_selected_folds": n_alpha,
        "fallback_folds": n_fallback,
        "alpha_selected_positive_ic_rate": alpha_pos_rate,
        "fallback_positive_ic_rate": fallback_pos_rate,
        "fallback_as_failure_rate": fallback_as_failure_rate,
    }


# ---------------------------------------------------------------------------
# Alpha Recovery Diagnostics (GATE: ALPHA_RECOVERY_DIAGNOSTICS_20260614)
# ---------------------------------------------------------------------------
# Opt-in diagnostics for alphas classified as RETIRE by research gates.
# These functions provide deeper analysis to understand WHY alphas are weak
# and whether any sub-component or regime-specific signal can be recovered.
#
# Default behavior is UNCHANGED — all functions are opt-in and never affect
# live trading or production paths.

# Alpha cluster classification based on naming patterns.
# Maps cluster name -> list of substrings that identify the cluster.
# NOTE: Order matters — more specific patterns (microstructure) should
# precede broader patterns (volume) to avoid misclassification.
ALPHA_CLUSTER_PATTERNS: Dict[str, List[str]] = {
    "microstructure": ["tick_signed", "imbalance", "micro_momentum"],
    "momentum": ["momentum", "drift"],
    "volatility": ["volatility", "vol_", "compression"],
    "liquidity": ["liquidity", "kyle_lambda", "provision_ratio"],
    "volume": ["volume", "volume_clock", "acceleration"],
}


def classify_alpha_cluster(alpha_name: str) -> str:
    """Classify an alpha into a cluster based on its name.

    Parameters
    ----------
    alpha_name : str
        Alpha identifier (may include ``alpha_p34_`` prefix).

    Returns
    -------
    str
        Cluster name, or ``"uncategorized"`` if no pattern matches.
    """
    lower = alpha_name.lower()
    for cluster, patterns in ALPHA_CLUSTER_PATTERNS.items():
        for pat in patterns:
            if pat in lower:
                return cluster
    return "uncategorized"


def compute_neutralized_ic_proxy(
    alpha_fold_ics: Dict[str, List[float]],
) -> Dict[str, Dict[str, Any]]:
    """Compute neutralized IC proxy by subtracting cluster mean IC.

    For each alpha, computes the cluster-mean IC (across all alphas in
    the same cluster) and subtracts it from the alpha's own mean IC.
    The result approximates the alpha-specific signal after removing
    common cluster-level factor exposure.

    PIT Safety
    ----------
    Uses only per-fold IC values that are already computed from OOS data.
    No new data access or look-ahead.

    Parameters
    ----------
    alpha_fold_ics : dict
        Mapping of alpha name to list of per-fold IC values.

    Returns
    -------
    dict
        Per-alpha dict with keys: cluster, mean_ic, cluster_mean_ic,
        neutralized_ic (mean_ic - cluster_mean_ic), n_cluster_members.
    """
    # Group alphas by cluster
    clusters: Dict[str, List[str]] = {}
    for alpha_name in alpha_fold_ics:
        cluster = classify_alpha_cluster(alpha_name)
        clusters.setdefault(cluster, []).append(alpha_name)

    # Compute cluster-mean IC
    cluster_mean_ics: Dict[str, float] = {}
    for cluster, members in clusters.items():
        all_ics: List[float] = []
        for alpha_name in members:
            all_ics.extend(alpha_fold_ics[alpha_name])
        cluster_mean_ics[cluster] = (
            sum(all_ics) / len(all_ics) if all_ics else 0.0
        )

    # Compute per-alpha neutralized IC
    result: Dict[str, Dict[str, Any]] = {}
    for alpha_name, ics in alpha_fold_ics.items():
        cluster = classify_alpha_cluster(alpha_name)
        mean_ic = sum(ics) / len(ics) if ics else 0.0
        cluster_mean = cluster_mean_ics.get(cluster, 0.0)
        neutralized = mean_ic - cluster_mean
        result[alpha_name] = {
            "cluster": cluster,
            "mean_ic": mean_ic,
            "cluster_mean_ic": cluster_mean,
            "neutralized_ic": neutralized,
            "n_cluster_members": len(clusters.get(cluster, [])),
        }
    return result


def compute_regime_conditioned_ic(
    fold_details: List[Dict[str, Any]],
    *,
    regime_threshold_sharpe: float = 1.0,
    regime_threshold_ic: float = -0.01,
) -> Dict[str, Dict[str, Any]]:
    """Compute regime-conditioned IC per alpha using fold-level proxies.

    Uses fold-level portfolio Sharpe and IC as regime proxies:
    - **Bull-like**: fold Sharpe >= threshold AND fold IC > 0
    - **Bear-like**: fold Sharpe < 0 OR fold IC < regime_threshold_ic
    - **Sideways**: all other folds

    PIT Safety
    ----------
    Only uses fold-level metrics already computed from OOS data.
    No new data access or look-ahead.

    Parameters
    ----------
    fold_details : list of dict
        Per-fold detail dicts with 'portfolio_sharpe', 'portfolio_ic',
        and 'alpha_ics' keys.
    regime_threshold_sharpe : float
        Sharpe threshold for bull-like classification.
    regime_threshold_ic : float
        IC threshold boundary for bear-like classification.
        Default -0.01 preserves backward-compatible behavior.

    Returns
    -------
    dict
        Per-alpha dict with keys: bull_ics, bear_ics, sideways_ics,
        bull_mean_ic, bear_mean_ic, sideways_mean_ic,
        bull_n_folds, bear_n_folds, sideways_n_folds,
        regime_fragile (bool: True if alpha only positive in one regime).
    """
    # Classify folds into regimes
    bull_folds: List[Dict[str, Any]] = []
    bear_folds: List[Dict[str, Any]] = []
    sideways_folds: List[Dict[str, Any]] = []

    for fold in fold_details:
        sharpe = fold.get("portfolio_sharpe", 0.0)
        ic = fold.get("portfolio_ic", 0.0)
        if sharpe >= regime_threshold_sharpe and ic > 0:
            bull_folds.append(fold)
        elif sharpe < 0 or ic < regime_threshold_ic:
            bear_folds.append(fold)
        else:
            sideways_folds.append(fold)

    # Collect alpha names
    all_alphas: set = set()
    for fold in fold_details:
        all_alphas.update(fold.get("alpha_ics", {}).keys())

    result: Dict[str, Dict[str, Any]] = {}
    for alpha_name in sorted(all_alphas):
        bull_ics = [
            f["alpha_ics"].get(alpha_name, 0.0)
            for f in bull_folds
            if alpha_name in f.get("alpha_ics", {})
        ]
        bear_ics = [
            f["alpha_ics"].get(alpha_name, 0.0)
            for f in bear_folds
            if alpha_name in f.get("alpha_ics", {})
        ]
        sideways_ics = [
            f["alpha_ics"].get(alpha_name, 0.0)
            for f in sideways_folds
            if alpha_name in f.get("alpha_ics", {})
        ]

        bull_mean = sum(bull_ics) / len(bull_ics) if bull_ics else 0.0
        bear_mean = sum(bear_ics) / len(bear_ics) if bear_ics else 0.0
        sideways_mean = sum(sideways_ics) / len(sideways_ics) if sideways_ics else 0.0

        # Count positive regimes
        positive_regimes = sum(
            1 for m in [bull_mean, bear_mean, sideways_mean] if m > 0
        )
        regime_fragile = positive_regimes <= 1

        result[alpha_name] = {
            "bull_ics": bull_ics,
            "bear_ics": bear_ics,
            "sideways_ics": sideways_ics,
            "bull_mean_ic": bull_mean,
            "bear_mean_ic": bear_mean,
            "sideways_mean_ic": sideways_mean,
            "bull_n_folds": len(bull_ics),
            "bear_n_folds": len(bear_ics),
            "sideways_n_folds": len(sideways_ics),
            "positive_regimes": positive_regimes,
            "regime_fragile": regime_fragile,
        }

    return result


def compute_ic_decay_summary(
    alpha_fold_ics: Dict[str, List[float]],
    *,
    n_folds: int = 0,
) -> Dict[str, Dict[str, Any]]:
    """Compute IC decay summary per alpha across fold ordering.

    Since walk-forward folds are chronologically ordered, we can
    assess whether alpha IC is decaying over time by comparing
    early-half IC vs late-half IC.

    PIT Safety
    ----------
    Uses only fold-level IC values already computed. No look-ahead.

    Parameters
    ----------
    alpha_fold_ics : dict
        Mapping of alpha name to list of per-fold IC values
        (assumed in chronological fold order).
    n_folds : int
        Total number of folds. If 0, inferred from the longest IC list.

    Returns
    -------
    dict
        Per-alpha dict with keys: early_half_mean_ic, late_half_mean_ic,
        ic_trend (positive = improving, negative = decaying),
        half_life_folds (estimated folds until IC halves, or -1 if N/A).
    """
    if n_folds <= 0:
        n_folds = max((len(v) for v in alpha_fold_ics.values()), default=0)
    mid = max(n_folds // 2, 1)

    result: Dict[str, Dict[str, Any]] = {}
    for alpha_name, ics in alpha_fold_ics.items():
        if not ics:
            result[alpha_name] = {
                "early_half_mean_ic": 0.0,
                "late_half_mean_ic": 0.0,
                "ic_trend": 0.0,
                "half_life_folds": -1,
            }
            continue

        early = ics[:mid]
        late = ics[mid:]
        early_mean = sum(early) / len(early) if early else 0.0
        late_mean = sum(late) / len(late) if late else 0.0
        trend = late_mean - early_mean

        # Half-life estimation: if early > 0 and late < early,
        # estimate how many folds until IC would reach half of early.
        half_life = -1
        if early_mean > 0.01 and trend < 0:
            decay_per_fold = abs(trend) / max(mid, 1)
            if decay_per_fold > 1e-9:
                half_life = int(early_mean / (2 * decay_per_fold))
            else:
                half_life = -1

        result[alpha_name] = {
            "early_half_mean_ic": early_mean,
            "late_half_mean_ic": late_mean,
            "ic_trend": trend,
            "half_life_folds": half_life,
        }

    return result


@dataclass
class AlphaRecoveryReport:
    """Complete alpha recovery diagnostics report.

    GATE: ALPHA_RECOVERY_DIAGNOSTICS_20260614

    Contains all opt-in diagnostics for alphas classified as RETIRE.
    """
    neutralized_ic: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    regime_conditioned_ic: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    ic_decay: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    retirement_summary: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    recoverable_candidates: List[str] = field(default_factory=list)
    confirmed_retire: List[str] = field(default_factory=list)
    research_only: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "neutralized_ic": self.neutralized_ic,
            "regime_conditioned_ic": {
                k: {
                    "bull_mean_ic": v["bull_mean_ic"],
                    "bear_mean_ic": v["bear_mean_ic"],
                    "sideways_mean_ic": v["sideways_mean_ic"],
                    "bull_n_folds": v["bull_n_folds"],
                    "bear_n_folds": v["bear_n_folds"],
                    "sideways_n_folds": v["sideways_n_folds"],
                    "positive_regimes": v["positive_regimes"],
                    "regime_fragile": v["regime_fragile"],
                }
                for k, v in self.regime_conditioned_ic.items()
            },
            "ic_decay": self.ic_decay,
            "retirement_summary": self.retirement_summary,
            "recoverable_candidates": self.recoverable_candidates,
            "confirmed_retire": self.confirmed_retire,
            "research_only": self.research_only,
        }


def compute_alpha_recovery_diagnostics(
    fold_details: List[Dict[str, Any]],
    alpha_fold_ics: Dict[str, List[float]],
    *,
    research_verdicts: Optional[Dict[str, str]] = None,
    regime_threshold_sharpe: float = 1.0,
    regime_threshold_ic: float = -0.01,
) -> AlphaRecoveryReport:
    """Compute full alpha recovery diagnostics.

    GATE: ALPHA_RECOVERY_DIAGNOSTICS_20260614

    This is the main entry point for recovery diagnostics. It combines:
    1. Neutralized IC proxy by cluster
    2. Regime-conditioned IC
    3. IC decay summary
    4. Retirement/control/research-only classification

    PIT Safety
    ----------
    All inputs are fold-level OOS metrics. No new data access.

    Parameters
    ----------
    fold_details : list of dict
        Per-fold detail dicts.
    alpha_fold_ics : dict
        Per-alpha per-fold IC values.
    research_verdicts : dict, optional
        Pre-computed research gate verdicts. If None, all alphas
        are treated as RETIRE candidates for diagnostics.
    regime_threshold_sharpe : float
        Sharpe threshold for bull-like regime classification.
    regime_threshold_ic : float
        IC threshold boundary for bear-like classification.
        Default -0.01 preserves backward-compatible behavior.

    Returns
    -------
    AlphaRecoveryReport
    """
    report = AlphaRecoveryReport()

    # 1. Neutralized IC proxy
    report.neutralized_ic = compute_neutralized_ic_proxy(alpha_fold_ics)

    # 2. Regime-conditioned IC
    report.regime_conditioned_ic = compute_regime_conditioned_ic(
        fold_details,
        regime_threshold_sharpe=regime_threshold_sharpe,
        regime_threshold_ic=regime_threshold_ic,
    )

    # 3. IC decay summary
    report.ic_decay = compute_ic_decay_summary(alpha_fold_ics)

    # 4. Retirement/control/research-only classification
    # An alpha classified as RETIRE by research gates may still have:
    #   - Positive neutralized IC (signal exists but masked by cluster)
    #   - Positive IC in specific regimes (regime-conditional signal)
    #   - Improving IC trend (signal recovering over time)
    #
    # Classification:
    #   RECOVERABLE: has at least one positive signal dimension
    #   RESEARCH_ONLY: mixed signals, needs further study
    #   CONFIRMED_RETIRE: no positive signal in any dimension

    for alpha_name in sorted(alpha_fold_ics.keys()):
        verdict = (
            research_verdicts.get(alpha_name, RESEARCH_VERDICT_RETIRE)
            if research_verdicts
            else RESEARCH_VERDICT_RETIRE
        )

        neut = report.neutralized_ic.get(alpha_name, {})
        regime = report.regime_conditioned_ic.get(alpha_name, {})
        decay = report.ic_decay.get(alpha_name, {})

        neutralized_ic = neut.get("neutralized_ic", 0.0)
        positive_regimes = regime.get("positive_regimes", 0)
        ic_trend = decay.get("ic_trend", 0.0)
        regime_fragile = regime.get("regime_fragile", True)

        # Count positive signal dimensions
        positive_dims = 0
        reasons: List[str] = []

        if neutralized_ic > 0.005:
            positive_dims += 1
            reasons.append(
                f"neutralized_ic={neutralized_ic:.4f}>0.005"
            )
        if positive_regimes >= 2:
            positive_dims += 1
            reasons.append(
                f"positive in {positive_regimes} regimes"
            )
        if ic_trend > 0.005:
            positive_dims += 1
            reasons.append(f"improving trend={ic_trend:.4f}")
        if not regime_fragile:
            positive_dims += 1
            reasons.append("not regime-fragile")

        # Classification
        if positive_dims >= 2:
            classification = "RECOVERABLE"
            report.recoverable_candidates.append(alpha_name)
        elif positive_dims == 1:
            classification = "RESEARCH_ONLY"
            report.research_only.append(alpha_name)
        else:
            classification = "CONFIRMED_RETIRE"
            report.confirmed_retire.append(alpha_name)

        report.retirement_summary[alpha_name] = {
            "research_verdict": verdict,
            "recovery_classification": classification,
            "neutralized_ic": neutralized_ic,
            "positive_regimes": positive_regimes,
            "ic_trend": ic_trend,
            "regime_fragile": regime_fragile,
            "positive_signal_dims": positive_dims,
            "reasons": reasons,
            "cluster": neut.get("cluster", "uncategorized"),
        }

    return report


# ---------------------------------------------------------------------------
# Statistical Validation Gates (GATE: STAT_VALIDATION_GATES_20260614)
# ---------------------------------------------------------------------------
# Opt-in statistical validation gate diagnostics: DSR, PBO, CPCV-ready.
# These helpers compute summary metrics from existing fold-level data.
# They do NOT change default behavior or affect live trading paths.
# PIT-safe: only uses fold-level metrics already computed from OOS data.

# Validation verdict constants
STAT_VALIDATION_PASS = "PASS"
STAT_VALIDATION_FAIL = "FAIL"
STAT_VALIDATION_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

# Minimum folds required for CPCV-ready path summary
_MIN_CPCV_FOLDS = 10

# Euler-Mascheroni constant used in DSR benchmark estimation
_EULER_GAMMA = 0.5772156649015329


def compute_dsr(
    sharpe_series: Sequence[float],
    *,
    n_trials: int = 0,
    annualization_factor: float = 252.0,
) -> float:
    """Compute Deflated Sharpe Ratio (DSR).

    Adjusts the observed Sharpe ratio for the number of strategies/trials
    tested, addressing selection bias (Bailey & Lopez de Prado, 2014).

    DSR estimates the probability that the observed Sharpe is NOT due to
    selection bias from testing multiple strategies.

    PIT Safety
    ----------
    Uses only OOS fold-level Sharpe values. No look-ahead.

    Parameters
    ----------
    sharpe_series : sequence of float
        Per-fold or per-path Sharpe ratios (OOS).
    n_trials : int
        Number of strategies/trials tested. If 0, inferred as len(sharpe_series).
    annualization_factor : float
        Factor for annualization (default 252 for daily).

    Returns
    -------
    float
        DSR value in [0, 1]. Higher = less likely to be overfit.
        Returns 0.0 if insufficient data.
    """
    vals = [
        v for v in sharpe_series
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]
    n = len(vals)
    if n < 3:
        return 0.0

    if n_trials <= 0:
        n_trials = n

    mean_sr = sum(vals) / n
    variance = sum((v - mean_sr) ** 2 for v in vals) / (n - 1)
    std_sr = math.sqrt(variance)

    if std_sr < 1e-12:
        # All Sharpe values identical
        return 1.0 if mean_sr > 0 else 0.0

    # Benchmark SR: expected maximum SR under the null of no skill
    # Using the Bailey & Lopez de Prado formula:
    # SR* ≈ std(SR) * [(1-γ)*Φ⁻¹(1-1/N) + γ*Φ⁻¹(1-1/(N*e))]
    # where γ is Euler-Mascheroni constant
    z1 = _norm_ppf(1.0 - 1.0 / max(n_trials, 2))
    z2 = _norm_ppf(1.0 - 1.0 / (max(n_trials, 2) * math.e))
    sr_benchmark = std_sr * ((1.0 - _EULER_GAMMA) * z1 + _EULER_GAMMA * z2)

    # DSR = P(SR_obs > SR_benchmark) under normal distribution
    # = 1 - Φ((SR_benchmark - mean_SR) / std_SR)
    z_score = (sr_benchmark - mean_sr) / std_sr
    dsr = 1.0 - _norm_cdf(z_score)
    return max(0.0, min(1.0, dsr))


def compute_pbo_summary(
    fold_path_scores: List[Dict[str, float]],
) -> Dict[str, Any]:
    """Compute Probability of Backtest Overfitting (PBO) summary.

    PBO measures how often the in-sample best strategy underperforms
    out-of-sample. Computed from a fold/path score matrix where each
    fold has per-path scores.

    PIT Safety
    ----------
    Uses only fold-level scores. The "IS best" is determined per-fold
    from all paths' scores; the "OOS rank" is also per-fold. No look-ahead.

    Parameters
    ----------
    fold_path_scores : list of dict
        Each dict maps path/alpha name to its score for that fold.
        Keys are path names, values are per-fold performance scores.

    Returns
    -------
    dict
        Keys: pbo (float in [0,1]), n_folds, n_paths,
        is_best_oos_rank_mean, is_best_count, overfit_count.
    """
    if not fold_path_scores:
        return {
            "pbo": 0.0,
            "n_folds": 0,
            "n_paths": 0,
            "is_best_oos_rank_mean": 0.0,
            "is_best_count": 0,
            "overfit_count": 0,
        }

    # Collect all path names
    all_paths: set = set()
    for fold_scores in fold_path_scores:
        all_paths.update(fold_scores.keys())
    all_paths = sorted(all_paths)
    n_paths = len(all_paths)

    if n_paths < 2:
        return {
            "pbo": 0.0,
            "n_folds": len(fold_path_scores),
            "n_paths": n_paths,
            "is_best_oos_rank_mean": 0.0,
            "is_best_count": 0,
            "overfit_count": 0,
        }

    # For each fold: identify IS-best path, check its OOS rank
    overfit_count = 0
    is_best_ranks: List[int] = []
    n_valid_folds = 0

    for fold_scores in fold_path_scores:
        if len(fold_scores) < 2:
            continue
        n_valid_folds += 1

        # Sort paths by score descending (higher = better)
        sorted_paths = sorted(
            fold_scores.items(), key=lambda x: x[1], reverse=True
        )
        is_best_path = sorted_paths[0][0]

        # OOS rank of IS-best (1-indexed): rank 1 = best OOS
        # For OOS, we use the same fold's scores as a proxy.
        # In walk-forward, the fold score IS the OOS score for that period.
        # PBO checks: is the IS-best also the OOS-best?
        # Since we only have OOS scores, we check if the highest-scoring
        # path in fold i also has the highest mean score across all OTHER folds.
        # Simplified: rank within the fold.
        is_best_rank = 1  # By definition, it's #1 in this fold
        # For true PBO, we'd compare IS vs OOS. Here we use a fold-level
        # proxy: how many paths outperform the "IS-best" on average across folds?
        is_best_ranks.append(is_best_rank)

    # Compute IS mean score vs all-paths mean to detect overfitting
    # PBO proxy: fraction of paths whose mean across folds exceeds
    # the mean of the per-fold-best path's cross-fold mean
    path_means: Dict[str, float] = {}
    for path in all_paths:
        scores = [
            fold_scores.get(path, 0.0) for fold_scores in fold_path_scores
        ]
        path_means[path] = sum(scores) / len(scores) if scores else 0.0

    # Per-fold-best path
    per_fold_bests: List[str] = []
    for fold_scores in fold_path_scores:
        if fold_scores:
            best = max(fold_scores, key=fold_scores.get)
            per_fold_bests.append(best)

    # PBO: fraction of folds where the per-fold-best path has a
    # cross-fold mean BELOW the overall median path mean
    if per_fold_bests:
        median_mean = sorted(path_means.values())[len(path_means) // 2]
        overfit_count = sum(
            1 for best in per_fold_bests
            if path_means.get(best, 0.0) < median_mean
        )
        pbo = overfit_count / len(per_fold_bests)
    else:
        pbo = 0.0

    is_best_oos_rank_mean = (
        sum(is_best_ranks) / len(is_best_ranks) if is_best_ranks else 0.0
    )

    return {
        "pbo": max(0.0, min(1.0, pbo)),
        "n_folds": len(fold_path_scores),
        "n_paths": n_paths,
        "is_best_oos_rank_mean": is_best_oos_rank_mean,
        "is_best_count": len(is_best_ranks),
        "overfit_count": overfit_count,
    }


def compute_cpcv_ready_path_summary(
    fold_path_scores: List[Dict[str, float]],
    *,
    min_folds: int = _MIN_CPCV_FOLDS,
) -> Dict[str, Any]:
    """Compute CPCV-ready path summary from existing walk-forward folds.

    Assesses whether existing fold data is sufficient for CPCV analysis
    and provides a path consistency summary.

    PIT Safety
    ----------
    Uses only existing fold-level OOS scores. No look-ahead.

    Parameters
    ----------
    fold_path_scores : list of dict
        Each dict maps path/alpha name to its score for that fold.
    min_folds : int
        Minimum folds required for CPCV-ready assessment (default 10).

    Returns
    -------
    dict
        Keys: cpcv_ready (bool), n_folds, n_paths, min_folds_required,
        path_consistency (dict: path -> fraction of folds positive),
        best_path, best_path_consistency.
    """
    n_folds = len(fold_path_scores)
    cpcv_ready = n_folds >= min_folds

    # Collect all paths
    all_paths: set = set()
    for fold_scores in fold_path_scores:
        all_paths.update(fold_scores.keys())
    all_paths = sorted(all_paths)

    if not all_paths or not fold_path_scores:
        return {
            "cpcv_ready": cpcv_ready,
            "n_folds": n_folds,
            "n_paths": 0,
            "min_folds_required": min_folds,
            "path_consistency": {},
            "best_path": None,
            "best_path_consistency": 0.0,
        }

    # Compute per-path consistency: fraction of folds where score > 0
    path_consistency: Dict[str, float] = {}
    for path in all_paths:
        scores = [
            fold_scores.get(path, 0.0) for fold_scores in fold_path_scores
        ]
        positive_count = sum(1 for s in scores if s > 0)
        path_consistency[path] = positive_count / len(scores) if scores else 0.0

    # Best path: highest mean score
    path_means: Dict[str, float] = {}
    for path in all_paths:
        scores = [
            fold_scores.get(path, 0.0) for fold_scores in fold_path_scores
        ]
        path_means[path] = sum(scores) / len(scores) if scores else 0.0

    best_path = max(path_means, key=path_means.get) if path_means else None
    best_consistency = path_consistency.get(best_path, 0.0) if best_path else 0.0

    return {
        "cpcv_ready": cpcv_ready,
        "n_folds": n_folds,
        "n_paths": len(all_paths),
        "min_folds_required": min_folds,
        "path_consistency": path_consistency,
        "best_path": best_path,
        "best_path_consistency": best_consistency,
    }


def compute_stat_validation_verdict(
    dsr: float,
    pbo: float,
    cpcv_ready: bool,
    *,
    max_pbo: float = 0.50,
    min_dsr: float = 0.0,
    weak_alpha_blocked: bool = True,
) -> Dict[str, Any]:
    """Compute statistical validation gate verdict.

    GATE: STAT_VALIDATION_GATES_20260614

    Combines DSR, PBO, and CPCV-ready status into a single verdict.
    Current weak alpha should remain blocked/DO_NOT_PROMOTE or
    validation fail.

    PIT Safety
    ----------
    Uses only already-computed summary metrics.

    Parameters
    ----------
    dsr : float
        Deflated Sharpe Ratio in [0, 1].
    pbo : float
        Probability of Backtest Overfitting in [0, 1].
    cpcv_ready : bool
        Whether fold data is sufficient for CPCV.
    max_pbo : float
        Maximum acceptable PBO threshold (default 0.50).
    min_dsr : float
        Minimum acceptable DSR threshold (default 0.0).
    weak_alpha_blocked : bool
        If True, current weak alpha is blocked regardless of metrics.

    Returns
    -------
    dict
        Keys: verdict (str), blockers (list of str),
        dsr, pbo, cpcv_ready, max_pbo, min_dsr.
    """
    blockers: List[str] = []

    if pbo > max_pbo:
        blockers.append(
            f"PBO={pbo:.4f} > max_pbo={max_pbo:.4f} (overfitting likely)"
        )

    if dsr < min_dsr:
        blockers.append(
            f"DSR={dsr:.4f} < min_dsr={min_dsr:.4f} (selection bias likely)"
        )

    if weak_alpha_blocked:
        blockers.append(
            "Weak alpha blocked: current alpha pool has mean IC below 0.02 gate"
        )

    if not cpcv_ready:
        blockers.append(
            "Insufficient folds for CPCV validation (need >= 10 folds)"
        )

    if blockers:
        verdict = STAT_VALIDATION_FAIL
    else:
        verdict = STAT_VALIDATION_PASS

    return {
        "verdict": verdict,
        "blockers": blockers,
        "dsr": dsr,
        "pbo": pbo,
        "cpcv_ready": cpcv_ready,
        "max_pbo": max_pbo,
        "min_dsr": min_dsr,
        "weak_alpha_blocked": weak_alpha_blocked,
    }


# ---------------------------------------------------------------------------
# Normal distribution helpers (for DSR computation)
# ---------------------------------------------------------------------------
def _norm_cdf(x: float) -> float:
    """Approximate standard normal CDF using error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Approximate standard normal inverse CDF (percent point function).

    Uses the rational approximation by Abramowitz & Stegun (26.2.23).
    Accurate to ~4.5e-4 for 0 < p < 1.
    """
    if p <= 0.0:
        return -6.0
    if p >= 1.0:
        return 6.0
    if p == 0.5:
        return 0.0

    if p < 0.5:
        sign = -1.0
        t_p = p
    else:
        sign = 1.0
        t_p = 1.0 - p

    t = math.sqrt(-2.0 * math.log(t_p))
    # Rational approximation
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    result = t - (c0 + c1 * t + c2 * t * t) / (
        1.0 + d1 * t + d2 * t * t + d3 * t * t * t
    )
    return sign * result
