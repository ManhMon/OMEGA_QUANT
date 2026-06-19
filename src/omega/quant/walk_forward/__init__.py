"""Walk-forward package - Tier 3.1 refactoring."""
from __future__ import annotations

from omega.quant.walk_forward.alpha_selector import AlphaSelectionMixin
from omega.quant.walk_forward.evolved_blender import EvolvedBlendingMixin
from omega.quant.walk_forward.fold_executor import FoldExecutorMixin
from omega.quant.walk_forward.gate_utils import _is_gate_verdict_pass
from omega.quant.walk_forward.metrics import FoldMetrics, WalkForwardResult
from omega.quant.walk_forward.portfolio_builder import PortfolioBuilderMixin
from omega.quant.walk_forward.signal_blender import SignalBlendingMixin
from omega.quant.walk_forward.risk_adjusted_alpha_score import (
    compute_composite_score,
    score_alpha_candidates,
    select_alphas_risk_adjusted,
    AlphaScoreBreakdown,
    RiskAdjustedSelectionResult,
    DEFAULT_WEIGHTS,
    compute_icir,
    compute_positive_fold_rate,
    bh_fdr_qvalues,
    classify_research_gate_verdict,
    compute_fallback_as_failure_metrics,
    compute_ic_pvalue,
    RESEARCH_VERDICT_PROMOTE_CANDIDATE,
    RESEARCH_VERDICT_ENSEMBLE_ONLY,
    RESEARCH_VERDICT_REVIEW,
    RESEARCH_VERDICT_RETIRE,
)

__all__ = [
    "AlphaSelectionMixin",
    "AlphaScoreBreakdown",
    "DEFAULT_WEIGHTS",
    "EvolvedBlendingMixin",
    "FoldExecutorMixin",
    "FoldMetrics",
    "PortfolioBuilderMixin",
    "RESEARCH_VERDICT_ENSEMBLE_ONLY",
    "RESEARCH_VERDICT_PROMOTE_CANDIDATE",
    "RESEARCH_VERDICT_REVIEW",
    "RESEARCH_VERDICT_RETIRE",
    "RiskAdjustedSelectionResult",
    "SignalBlendingMixin",
    "WalkForwardResult",
    "_is_gate_verdict_pass",
    "bh_fdr_qvalues",
    "classify_research_gate_verdict",
    "compute_composite_score",
    "compute_fallback_as_failure_metrics",
    "compute_ic_pvalue",
    "compute_icir",
    "compute_positive_fold_rate",
    "score_alpha_candidates",
    "select_alphas_risk_adjusted",
]
