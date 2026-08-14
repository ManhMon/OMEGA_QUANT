"""Hybrid Alpha Miner with Nested Cross-Validation.

Multi-source candidate generation (LLM v3 + templates + GP mutation/crossover +
random safe) with strict nested-CV discipline: outer test labels are never used
for candidate generation or selection.

Objective: validation IC, sign consistency, DSR proxy, coverage, low correlation.
Deployment gate: deployment_ready=False unless strict thresholds pass.

Author: Backend Engineer (Role 09)
Date: 2026-06-12
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from omega.quant.evolution.genetic_programming import (
    GPIndividual,
    GPNode,
    GeneticProgrammingConfig,
    GeneticProgrammingEngine,
)

logger = logging.getLogger(__name__)


def _spearman_corr_via_ranks(a: np.ndarray, b: np.ndarray) -> float:
    """Compute Spearman correlation from average ranks for finite arrays."""
    if len(a) != len(b):
        raise ValueError("Array shapes are incompatible for broadcasting.")
    if len(a) < 2:
        return float("nan")

    a_ranks = rankdata(a, method="average")
    b_ranks = rankdata(b, method="average")
    if np.all(a_ranks == a_ranks[0]) or np.all(b_ranks == b_ranks[0]):
        return float("nan")
    return float(np.corrcoef(a_ranks, b_ranks)[0, 1])


# =============================================================================
# Enums and Constants
# =============================================================================

class CandidateSource(Enum):
    """Source of candidate formula."""
    LLM_V3 = "llm_v3"
    TEMPLATE = "template"
    GP_MUTATION = "gp_mutation"
    GP_CROSSOVER = "gp_crossover"
    RANDOM_SAFE = "random_safe"


# Default template formulas (known-good patterns for VN market)
_TEMPLATE_FORMULAS: List[str] = [
    "ts_mean(close, 20)",
    "ts_std(close, 10)",
    "ts_rank(volume, 20)",
    "div(ts_mean(close, 20), ts_mean(close, 5))",
    "ts_std(volume, 10)",
    "div(close, ts_mean(close, 10))",
    "rank(close)",
    "abs(sub(close, ts_mean(close, 10)))",
    "ts_rank(close, 5)",
    "div(ts_std(close, 20), ts_mean(close, 20))",
]


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class HybridAlphaMinerConfig:
    """Configuration for hybrid alpha miner with nested CV."""

    # Candidate budget
    candidate_budget: int = 200
    top_k: int = 10

    # Source proportions (fractions of candidate_budget)
    llm_fraction: float = 0.30
    template_fraction: float = 0.20
    gp_mutation_fraction: float = 0.20
    gp_crossover_fraction: float = 0.15
    random_safe_fraction: float = 0.15

    # Nested CV
    n_outer_folds: int = 3
    n_inner_folds: int = 3

    # LLM settings
    llm_provider: str = "mock"
    prompt_version: str = "vn_alpha_search_v3_closed_loop"

    # Objective weights
    w_ic: float = 0.30
    w_sign_consistency: float = 0.15
    w_dsr_proxy: float = 0.20
    w_coverage: float = 0.15
    w_low_correlation: float = 0.20

    # Deployment thresholds (strict)
    min_deploy_ic: float = 0.05
    min_deploy_sign_consistency: float = 0.60
    min_deploy_dsr: float = 0.50
    min_deploy_coverage: float = 0.90
    max_deploy_correlation: float = 0.70

    # Scoring thresholds (inner validation)
    min_coverage: float = 0.80
    min_variance: float = 1e-8
    max_nan_inf_ratio: float = 0.20

    def __post_init__(self):
        total = (
            self.llm_fraction
            + self.template_fraction
            + self.gp_mutation_fraction
            + self.gp_crossover_fraction
            + self.random_safe_fraction
        )
        assert abs(total - 1.0) < 0.01, (
            f"Source fractions must sum to 1.0, got {total:.4f}"
        )
        assert self.candidate_budget > 0, "candidate_budget must be positive"
        assert self.top_k > 0, "top_k must be positive"
        assert self.n_outer_folds >= 2, "n_outer_folds must be >= 2"
        assert self.n_inner_folds >= 2, "n_inner_folds must be >= 2"

    def source_budgets(self) -> Dict[CandidateSource, int]:
        """Compute per-source candidate counts from budget and fractions."""
        budgets = {
            CandidateSource.LLM_V3: max(1, int(self.candidate_budget * self.llm_fraction)),
            CandidateSource.TEMPLATE: max(1, int(self.candidate_budget * self.template_fraction)),
            CandidateSource.GP_MUTATION: max(1, int(self.candidate_budget * self.gp_mutation_fraction)),
            CandidateSource.GP_CROSSOVER: max(1, int(self.candidate_budget * self.gp_crossover_fraction)),
            CandidateSource.RANDOM_SAFE: max(1, int(self.candidate_budget * self.random_safe_fraction)),
        }
        # Adjust rounding to match total budget
        total = sum(budgets.values())
        diff = self.candidate_budget - total
        if diff > 0:
            budgets[CandidateSource.LLM_V3] += diff
        elif diff < 0:
            budgets[CandidateSource.LLM_V3] = max(1, budgets[CandidateSource.LLM_V3] + diff)
        return budgets


# =============================================================================
# Candidate Tracking
# =============================================================================

@dataclass
class CandidateRecord:
    """Tracked candidate with source and metrics."""
    node: GPNode
    source: CandidateSource
    formula_str: str
    formula_hash: str
    inner_metrics: Dict[str, float] = field(default_factory=dict)
    objective_score: float = -np.inf
    is_selected: bool = False
    # Internal: per-outer-fold executed values for correlation computation
    # Key = outer_fold_idx, Value = executed values array on outer-train panel
    _fold_values: Dict[int, np.ndarray] = field(
        default_factory=dict, repr=False, compare=False,
    )
    # Internal: per-outer-fold metrics for nested-CV aggregation
    # Key = outer_fold_idx, Value = dict of metrics from that fold
    _fold_metrics: Dict[int, Dict[str, float]] = field(
        default_factory=dict, repr=False, compare=False,
    )
    _alpha_values: np.ndarray = field(
        default_factory=lambda: np.array([]), repr=False, compare=False,
    )

    def clear_signals(self) -> None:
        """Release cached arrays for candidates excluded from selection."""
        self._fold_values.clear()
        self._fold_metrics.clear()
        self._alpha_values = np.array([])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.value,
            "formula_str": self.formula_str,
            "formula_hash": self.formula_hash,
            "inner_metrics": self.inner_metrics,
            "objective_score": self.objective_score,
            "is_selected": self.is_selected,
        }


# =============================================================================
# Formula Memory and Motif Metrics
# =============================================================================

@dataclass
class FormulaMemory:
    """Tracks seen formulas and motif frequency for deduplication."""
    seen_hashes: Set[str] = field(default_factory=set)
    motif_counts: Dict[str, int] = field(default_factory=dict)
    total_generated: int = 0
    total_duplicates: int = 0
    total_parse_errors: int = 0
    total_safety_rejected: int = 0

    def is_duplicate(self, formula_hash: str) -> bool:
        return formula_hash in self.seen_hashes

    def add(self, formula_hash: str, formula_str: str) -> None:
        self.seen_hashes.add(formula_hash)
        self._update_motifs(formula_str)

    def _update_motifs(self, formula_str: str) -> None:
        """Extract and count top-level function motifs."""
        if "(" in formula_str:
            top_func = formula_str.split("(")[0].strip()
            if top_func:
                self.motif_counts[top_func] = self.motif_counts.get(top_func, 0) + 1

    def get_motif_metrics(self) -> Dict[str, Any]:
        return {
            "unique_formulas": len(self.seen_hashes),
            "total_generated": self.total_generated,
            "total_duplicates": self.total_duplicates,
            "total_parse_errors": self.total_parse_errors,
            "total_safety_rejected": self.total_safety_rejected,
            "top_motifs": dict(
                sorted(self.motif_counts.items(), key=lambda x: -x[1])[:10]
            ),
        }

    @staticmethod
    def hash_formula(formula_str: str) -> str:
        """Normalize and hash a formula for deduplication."""
        import re
        normalized = formula_str.lower().strip()
        # Collapse whitespace
        normalized = " ".join(normalized.split())
        # Remove spaces around parens and commas
        normalized = re.sub(r'\s*\(\s*', '(', normalized)
        normalized = re.sub(r'\s*\)\s*', ')', normalized)
        normalized = re.sub(r'\s*,\s*', ',', normalized)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]


# =============================================================================
# Nested CV Splitter
# =============================================================================

class NestedCVSplitter:
    """
    Chronological nested cross-validation splitter.

    Outer loop: expanding-window folds (time-ordered).
    Inner loop: k-fold within outer train set.

    PIT Safety:
    - Outer test indices are NEVER used for candidate generation/selection.
    - Inner validation only uses indices within outer train.
    """

    _PURGE_SESSIONS = 5

    def __init__(self, n_outer_folds: int = 3, n_inner_folds: int = 3):
        self.n_outer_folds = n_outer_folds
        self.n_inner_folds = n_inner_folds

    def generate_outer_splits(
        self, n_samples: int
    ) -> List[Dict[str, np.ndarray]]:
        """Generate outer fold splits (chronological expanding window).

        Returns list of dicts with 'train' and 'test' index arrays.
        """
        splits = []
        fold_size = n_samples // (self.n_outer_folds + 1)

        for fold_idx in range(self.n_outer_folds):
            # Expanding window: train = [0, (fold_idx+1)*fold_size)
            # Test = [(fold_idx+1)*fold_size, (fold_idx+2)*fold_size)
            train_end = (fold_idx + 1) * fold_size
            test_start = train_end + self._PURGE_SESSIONS
            test_end = min(test_start + fold_size, n_samples)

            if test_end <= test_start:
                continue

            train_idx = np.arange(0, train_end)
            test_idx = np.arange(test_start, test_end)

            splits.append({
                "fold": fold_idx,
                "train": train_idx,
                "test": test_idx,
            })

        return splits

    def generate_inner_splits(
        self, outer_train_idx: np.ndarray
    ) -> List[Dict[str, np.ndarray]]:
        """Generate inner fold splits within outer train indices.

        PIT Safety: inner indices are always a subset of outer_train_idx.
        """
        n_inner = len(outer_train_idx)
        inner_fold_size = n_inner // (self.n_inner_folds + 1)
        splits = []

        for inner_fold in range(self.n_inner_folds):
            inner_train_end = (inner_fold + 1) * inner_fold_size
            inner_val_start = inner_train_end + self._PURGE_SESSIONS
            inner_val_end = min(inner_val_start + inner_fold_size, n_inner)

            if inner_val_end <= inner_val_start:
                continue

            inner_train_local = np.arange(0, inner_train_end)
            inner_val_local = np.arange(inner_val_start, inner_val_end)

            # Map local indices to global indices
            inner_train_global = outer_train_idx[inner_train_local]
            inner_val_global = outer_train_idx[inner_val_local]

            splits.append({
                "inner_fold": inner_fold,
                "train": inner_train_global,
                "val": inner_val_global,
            })

        return splits


# =============================================================================
# Candidate Generation
# =============================================================================

class HybridCandidateGenerator:
    """Generates candidates from multiple sources with safety parsing."""

    def __init__(
        self,
        config: HybridAlphaMinerConfig,
        feature_names: List[str],
        memory: Optional[FormulaMemory] = None,
    ):
        self.config = config
        self.feature_names = feature_names
        self.memory = memory or FormulaMemory()

        # Safe operators and terminals for random generation
        self._safe_unary = ["abs", "log", "sqrt", "rank", "neg"]
        self._safe_binary = ["+", "-", "*", "/"]
        self._safe_ts = ["ts_mean", "ts_std", "ts_rank"]
        self._safe_windows = [5, 10, 20]

    def generate_all_sources(self) -> List[CandidateRecord]:
        """Generate candidates from all sources according to budget."""
        budgets = self.config.source_budgets()
        all_candidates: List[CandidateRecord] = []

        # 1. LLM v3 candidates
        llm_nodes = self._generate_llm(budgets[CandidateSource.LLM_V3])
        for node in llm_nodes:
            rec = self._make_record(node, CandidateSource.LLM_V3)
            if rec:
                all_candidates.append(rec)

        # 2. Template candidates
        tmpl_nodes = self._generate_templates(budgets[CandidateSource.TEMPLATE])
        for node in tmpl_nodes:
            rec = self._make_record(node, CandidateSource.TEMPLATE)
            if rec:
                all_candidates.append(rec)

        # 3. GP mutation candidates
        mut_nodes = self._generate_gp_mutation(budgets[CandidateSource.GP_MUTATION])
        for node in mut_nodes:
            rec = self._make_record(node, CandidateSource.GP_MUTATION)
            if rec:
                all_candidates.append(rec)

        # 4. GP crossover candidates
        cross_nodes = self._generate_gp_crossover(
            budgets[CandidateSource.GP_CROSSOVER]
        )
        for node in cross_nodes:
            rec = self._make_record(node, CandidateSource.GP_CROSSOVER)
            if rec:
                all_candidates.append(rec)

        # 5. Random safe candidates
        rand_nodes = self._generate_random_safe(
            budgets[CandidateSource.RANDOM_SAFE]
        )
        for node in rand_nodes:
            rec = self._make_record(node, CandidateSource.RANDOM_SAFE)
            if rec:
                all_candidates.append(rec)

        logger.info(
            "Generated %d candidates from %d sources (budget=%d)",
            len(all_candidates),
            len(budgets),
            self.config.candidate_budget,
        )
        return all_candidates

    def _make_record(
        self, node: GPNode, source: CandidateSource
    ) -> Optional[CandidateRecord]:
        """Create a CandidateRecord with deduplication check."""
        self.memory.total_generated += 1
        formula_str = self._node_to_string(node)
        formula_hash = FormulaMemory.hash_formula(formula_str)

        if self.memory.is_duplicate(formula_hash):
            self.memory.total_duplicates += 1
            return None

        self.memory.add(formula_hash, formula_str)
        return CandidateRecord(
            node=node,
            source=source,
            formula_str=formula_str,
            formula_hash=formula_hash,
        )

    def _generate_llm(self, count: int) -> List[GPNode]:
        """Generate candidates via LLM v3 (mock-safe)."""
        try:
            from omega.quant.evolution.llm_symbolic_synthesizer import (
                LLMSymbolicSynthesizer,
            )

            synth = LLMSymbolicSynthesizer(
                provider=self.config.llm_provider,
                prompt_version=self.config.prompt_version,
                max_candidates=count,
            )
            features = {
                name: np.random.randn(50) for name in self.feature_names[:5]
            }
            if not features:
                features = {"close": np.random.randn(50)}
            nodes, _stats = synth.synthesize(features)
            return nodes[:count]
        except Exception as exc:
            logger.warning("LLM generation failed, falling back to templates: %s", exc)
            self.memory.total_parse_errors += 1
            return self._generate_templates(count)

    def _generate_templates(self, count: int) -> List[GPNode]:
        """Generate candidates from known-good template formulas."""
        from omega.quant.evolution.llm_symbolic_synthesizer import (
            LLMSymbolicSynthesizer,
        )

        synth = LLMSymbolicSynthesizer(provider="mock")
        nodes: List[GPNode] = []
        for formula in _TEMPLATE_FORMULAS[:count]:
            try:
                node = synth.parse_formula(formula)
                nodes.append(node)
            except Exception:
                self.memory.total_parse_errors += 1
        return nodes

    def _generate_gp_mutation(self, count: int) -> List[GPNode]:
        """Generate candidates via GP mutation of seed trees."""
        gp_cfg = GeneticProgrammingConfig(
            population_size=max(4, count),
            generations=2,
            max_depth=4,
            min_observations=10,
        )
        engine = GeneticProgrammingEngine(gp_cfg)
        engine.feature_names = self.feature_names if self.feature_names else ["close"]

        nodes: List[GPNode] = []
        for _ in range(count):
            tree = engine.generate_random_tree(depth=0)
            # Mutate: replace a random subtree
            subtree = tree.get_random_subtree()
            new_subtree = engine.generate_random_tree(depth=0)
            tree.replace_subtree(subtree, new_subtree)
            nodes.append(tree)
        return nodes

    def _generate_gp_crossover(self, count: int) -> List[GPNode]:
        """Generate candidates via GP crossover of seed trees."""
        gp_cfg = GeneticProgrammingConfig(
            population_size=max(4, count * 2),
            generations=1,
            max_depth=4,
            min_observations=10,
        )
        engine = GeneticProgrammingEngine(gp_cfg)
        engine.feature_names = self.feature_names if self.feature_names else ["close"]

        nodes: List[GPNode] = []
        for _ in range(count):
            tree1 = engine.generate_random_tree(depth=0)
            tree2 = engine.generate_random_tree(depth=0)
            subtree1 = tree1.get_random_subtree()
            subtree2 = tree2.get_random_subtree()
            tree1.replace_subtree(subtree1, subtree2)
            nodes.append(tree1)
        return nodes

    def _generate_random_safe(self, count: int) -> List[GPNode]:
        """Generate random safe candidates using only approved operators."""
        features = self.feature_names if self.feature_names else ["close"]
        nodes: List[GPNode] = []

        for _ in range(count):
            op_type = random.choice(["unary", "binary", "ts"])
            if op_type == "unary":
                op = random.choice(self._safe_unary)
                child = GPNode(
                    operator="terminal",
                    value=random.choice(features),
                )
                node = GPNode(operator=op, children=[child])
            elif op_type == "binary":
                op = random.choice(self._safe_binary)
                left = GPNode(
                    operator="terminal",
                    value=random.choice(features),
                )
                right = GPNode(
                    operator="terminal",
                    value=random.choice(features),
                )
                node = GPNode(operator=op, children=[left, right])
            else:
                op = random.choice(self._safe_ts)
                child = GPNode(
                    operator="terminal",
                    value=random.choice(features),
                )
                window = GPNode(
                    operator="terminal",
                    value=str(random.choice(self._safe_windows)),
                )
                node = GPNode(operator=op, children=[child, window])
            nodes.append(node)

        return nodes

    @staticmethod
    def _node_to_string(node: GPNode) -> str:
        """Convert GPNode tree to string representation."""
        return node.to_string()


# =============================================================================
# Nested CV Objective Scorer
# =============================================================================

class NestedCVObjective:
    """
    Multi-objective scorer for inner validation only.

    PIT Safety: ONLY uses inner validation data (subset of outer train).
    Outer test labels are NEVER touched by this scorer.

    Objectives:
    - Validation IC (Spearman rank correlation with labels)
    - Sign consistency (fraction of inner folds with same IC sign)
    - DSR proxy (directional success rate approximation)
    - Coverage (fraction of non-NaN values)
    - Low correlation (penalty for high correlation with selected candidates)
    """

    def __init__(self, config: HybridAlphaMinerConfig):
        self.config = config

    def score_candidate(
        self,
        candidate: CandidateRecord,
        panel: pd.DataFrame,
        feat_cols: List[str],
        labels: np.ndarray,
        inner_splits: List[Dict[str, np.ndarray]],
        selected_values: Optional[List[np.ndarray]] = None,
        ticker_col: str = "ticker",
        date_col: str = "date",
        outer_fold_idx: int = 0,
        synth: Optional[Any] = None,
    ) -> CandidateRecord:
        """Score a candidate on inner validation folds only.

        PIT Safety: caller MUST pass an outer-train-sliced panel and
        locally-remapped inner splits.  This method never sees outer-test
        rows because the panel has already been sliced upstream.

        Args:
            candidate: Candidate to score.
            panel: Outer-train-sliced panel (NOT the full panel).
            feat_cols: Feature column names.
            labels: Labels array aligned with sliced panel (outer-train only).
            inner_splits: Inner fold splits with LOCAL indices (into the
                sliced panel).
            selected_values: Already-selected candidate values (for
                correlation penalty).  Must be same length as *panel*.
            ticker_col: Ticker column name.
            date_col: Date column name.
            outer_fold_idx: Outer fold index for storing per-fold values.
        """
        if synth is None:
            from omega.quant.evolution.llm_symbolic_synthesizer import (
                LLMSymbolicSynthesizer,
            )

            synth = LLMSymbolicSynthesizer(provider="mock")

        # Execute candidate on the outer-train-sliced panel (PIT-safe)
        try:
            values = synth.execute_node_grouped(
                candidate.node, panel, feat_cols,
                ticker_col=ticker_col, date_col=date_col,
            )
        except Exception as exc:
            logger.debug("Execution failed for %s: %s", candidate.formula_str, exc)
            candidate.inner_metrics = {
                "ic": 0.0,
                "signed_ic": 0.0,
                "sign_consistency": 0.0,
                "dsr_proxy": 0.0,
                "coverage": 0.0,
                "max_correlation": 1.0,
            }
            candidate.objective_score = -np.inf
            return candidate

        # Store executed values for later pairwise correlation computation
        candidate._fold_values[outer_fold_idx] = values.copy()

        # Compute per-inner-fold IC (validation only, PIT-safe)
        fold_ics: List[float] = []
        for split in inner_splits:
            val_idx = split["val"]
            if len(val_idx) < 5:
                continue

            val_values = values[val_idx]
            val_labels = labels[val_idx]

            valid_mask = np.isfinite(val_values) & np.isfinite(val_labels)
            if np.sum(valid_mask) < 5:
                continue

            ic = _spearman_corr_via_ranks(
                val_values[valid_mask], val_labels[valid_mask],
            )
            if np.isfinite(ic):
                fold_ics.append(float(ic))

        # Validation IC: mean across inner folds
        mean_ic = float(np.mean(fold_ics)) if fold_ics else 0.0

        # IC sign semantics: rank by signed positive IC only.
        # Negative-IC candidates are deprioritised (contribute 0 to the
        # IC component of the objective) to avoid hidden sign inversion.
        signed_ic = max(0.0, mean_ic)

        # Sign consistency: fraction of folds agreeing with mean sign
        if len(fold_ics) >= 2 and abs(mean_ic) > 1e-8:
            sign = np.sign(mean_ic)
            agreeing = sum(1 for ic in fold_ics if np.sign(ic) == sign)
            sign_consistency = agreeing / len(fold_ics)
        else:
            sign_consistency = 0.0

        # DSR proxy: fraction of folds with positive IC
        if fold_ics:
            dsr_proxy = sum(1 for ic in fold_ics if ic > 0) / len(fold_ics)
        else:
            dsr_proxy = 0.0

        # Coverage: fraction of non-NaN values (on outer-train panel only)
        finite_count = np.sum(np.isfinite(values))
        coverage = float(finite_count / len(values)) if len(values) > 0 else 0.0

        # Max correlation with already-selected candidates
        max_corr = 0.0
        if selected_values:
            finite_mask = np.isfinite(values)
            for sel_vals in selected_values:
                common = finite_mask & np.isfinite(sel_vals)
                if np.sum(common) >= 10:
                    corr = _spearman_corr_via_ranks(
                        values[common], sel_vals[common],
                    )
                    if np.isfinite(corr):
                        max_corr = max(max_corr, abs(float(corr)))

        # Weighted objective – uses signed_ic (not abs_ic)
        objective = (
            self.config.w_ic * signed_ic
            + self.config.w_sign_consistency * sign_consistency
            + self.config.w_dsr_proxy * dsr_proxy
            + self.config.w_coverage * coverage
            + self.config.w_low_correlation * (1.0 - max_corr)
        )

        fold_metrics = {
            "ic": mean_ic,
            "signed_ic": signed_ic,
            "sign_consistency": sign_consistency,
            "dsr_proxy": dsr_proxy,
            "coverage": coverage,
            "max_correlation": max_corr,
            "n_inner_folds_scored": len(fold_ics),
        }

        # Store per-outer-fold metrics for later aggregation (P1 fix)
        candidate._fold_metrics[outer_fold_idx] = fold_metrics

        # Set inner_metrics to current fold (will be overwritten by
        # aggregate after the outer-fold loop completes)
        candidate.inner_metrics = dict(fold_metrics)
        candidate.objective_score = objective

        return candidate

    def check_deploy_ready(self, candidate: CandidateRecord) -> bool:
        """Check if candidate meets strict deployment thresholds.

        Returns False unless ALL thresholds pass.
        Uses signed IC (not abs) so negative-IC candidates are blocked.
        Correlation gate blocks when max_correlation exceeds threshold.
        """
        m = candidate.inner_metrics
        if not m:
            return False

        # Signed IC must meet threshold (negative IC fails)
        ic_ok = m.get("ic", 0.0) >= self.config.min_deploy_ic
        sign_ok = m.get("sign_consistency", 0.0) >= self.config.min_deploy_sign_consistency
        dsr_ok = m.get("dsr_proxy", 0.0) >= self.config.min_deploy_dsr
        cov_ok = m.get("coverage", 0.0) >= self.config.min_deploy_coverage

        # Correlation gate: block deploy when max_correlation exceeds threshold
        max_corr = m.get("max_correlation", 0.0)
        corr_ok = max_corr <= self.config.max_deploy_correlation

        return ic_ok and sign_ok and dsr_ok and cov_ok and corr_ok


# =============================================================================
# Main Orchestrator
# =============================================================================

class HybridAlphaMiner:
    """
    Hybrid Alpha Miner with Nested Cross-Validation.

    Workflow:
    1. Generate candidates from multiple sources (LLM v3, templates, GP, random).
    2. For each outer fold:
       a. Generate inner folds within outer train.
       b. Score candidates on inner validation ONLY (never outer test).
    3. Select top_k candidates by aggregate objective across outer folds.
    4. Evaluate deployment readiness (strict thresholds).

    PIT Safety Guarantees:
    - Outer test labels are NEVER used for candidate generation or selection.
    - Inner train/validation selection only within outer train.
    - Aggregate evidence only (no row-level test data persisted).
    """

    def __init__(self, config: Optional[HybridAlphaMinerConfig] = None):
        self.config = config or HybridAlphaMinerConfig()
        self.splitter = NestedCVSplitter(
            n_outer_folds=self.config.n_outer_folds,
            n_inner_folds=self.config.n_inner_folds,
        )
        self.memory = FormulaMemory()
        self.generator: Optional[HybridCandidateGenerator] = None
        self.scorer = NestedCVObjective(self.config)

    def run(
        self,
        panel: pd.DataFrame,
        feat_cols: List[str],
        labels: np.ndarray,
        ticker_col: str = "ticker",
        date_col: str = "date",
    ) -> Tuple[List[CandidateRecord], Dict[str, Any]]:
        """
        Run hybrid alpha mining with nested CV.

        Args:
            panel: Full panel data.
            feat_cols: Feature column names.
            labels: Full-sample labels (only train subsets used internally).
            ticker_col: Ticker column name.
            date_col: Date column name.

        Returns:
            (selected_candidates, evidence_dict)

        PIT Safety:
        - For each outer fold the panel is sliced to outer-train rows
          *before* any execution or scoring.  Time-series / rank operators
          therefore never see outer-test rows.
        - Inner splits are remapped from global to local indices.
        """
        n_samples = len(panel)
        feature_names = list(feat_cols)

        # Initialize generator
        self.generator = HybridCandidateGenerator(
            config=self.config,
            feature_names=feature_names,
            memory=self.memory,
        )

        # Step 1: Generate candidates (no label usage here)
        all_candidates = self.generator.generate_all_sources()
        logger.info("Generated %d total candidates", len(all_candidates))

        if not all_candidates:
            return [], self._build_evidence([], {}, n_outer=0)

        # Step 2: Outer fold loop – PIT-safe panel slicing
        outer_splits = self.splitter.generate_outer_splits(n_samples)
        fold_objectives: Dict[str, List[float]] = {}  # hash -> [objective_per_fold]

        for outer_fold_idx, outer_split in enumerate(outer_splits):
            outer_train_idx = outer_split["train"]
            # CRITICAL PIT FIX: slice panel and labels to outer-train rows
            # before any execution/scoring.  ts/rank operators cannot see
            # outer-test rows because those rows are absent from panel_train.
            panel_train = panel.iloc[outer_train_idx].reset_index(drop=True)
            labels_train = labels[outer_train_idx]

            # Build global-to-local index mapping for inner splits
            global_to_local: Dict[int, int] = {
                int(g): l for l, g in enumerate(outer_train_idx)
            }

            # Generate inner folds within outer train
            inner_splits = self.splitter.generate_inner_splits(outer_train_idx)

            # Remap inner splits from global to local indices
            local_inner_splits: List[Dict[str, Any]] = []
            for split in inner_splits:
                local_inner_splits.append({
                    "inner_fold": split["inner_fold"],
                    "train": np.array(
                        [global_to_local[int(g)] for g in split["train"]]
                    ),
                    "val": np.array(
                        [global_to_local[int(g)] for g in split["val"]]
                    ),
                })

            # Score each candidate on inner validation (PIT-safe: on
            # outer-train-sliced panel with local indices)
            for candidate in all_candidates:
                self.scorer.score_candidate(
                    candidate=candidate,
                    panel=panel_train,
                    feat_cols=feat_cols,
                    labels=labels_train,
                    inner_splits=local_inner_splits,
                    selected_values=None,  # first pass: no correlation
                    ticker_col=ticker_col,
                    date_col=date_col,
                    outer_fold_idx=outer_fold_idx,
                )

                # Track per-fold objectives
                fh = candidate.formula_hash
                if fh not in fold_objectives:
                    fold_objectives[fh] = []
                fold_objectives[fh].append(candidate.objective_score)

        # Step 3: Aggregate objective across outer folds
        for candidate in all_candidates:
            fh = candidate.formula_hash
            fold_objs = fold_objectives.get(fh, [])
            if fold_objs:
                candidate.objective_score = float(np.mean(fold_objs))
            else:
                candidate.objective_score = -np.inf

        # Step 3b: Aggregate per-outer-fold metrics (P1 fix)
        # inner_metrics must reflect the nested-CV aggregate across all
        # outer folds, NOT the last outer fold's overwrite.
        for candidate in all_candidates:
            if candidate._fold_metrics:
                fold_m = list(candidate._fold_metrics.values())
                agg_ic = float(np.mean([m["ic"] for m in fold_m]))
                # P1 fix3: aggregate signed_ic = max(0.0, aggregate_ic).
                # Do NOT give positive signed_ic credit to negative aggregate IC.
                # This is the deploy/objective metric.
                agg_signed_ic = max(0.0, agg_ic)
                # Per-fold-positive IC diagnostic: average of per-fold
                # max(0, fold_ic).  NOT used for deploy/objective; kept as
                # a separate diagnostic field only.
                per_fold_positive_ic_diagnostic = float(
                    np.mean([m["signed_ic"] for m in fold_m])
                )
                agg_sign_consistency = float(np.mean(
                    [m["sign_consistency"] for m in fold_m]
                ))
                agg_dsr = float(np.mean([m["dsr_proxy"] for m in fold_m]))
                agg_coverage = float(np.mean([m["coverage"] for m in fold_m]))
                # max_correlation will be recomputed during greedy selection;
                # keep last-fold value as placeholder until then.
                candidate.inner_metrics = {
                    "ic": agg_ic,
                    "signed_ic": agg_signed_ic,
                    "sign_consistency": agg_sign_consistency,
                    "dsr_proxy": agg_dsr,
                    "coverage": agg_coverage,
                    "max_correlation": fold_m[-1].get("max_correlation", 0.0),
                    "n_outer_folds_scored": len(fold_m),
                    "n_inner_folds_scored": int(np.mean(
                        [m.get("n_inner_folds_scored", 0) for m in fold_m]
                    )),
                    "per_fold_positive_ic_diagnostic": (
                        per_fold_positive_ic_diagnostic
                    ),
                }

        # Step 4: Greedy top-K selection with real pairwise correlation
        sorted_candidates = sorted(
            all_candidates, key=lambda c: c.objective_score, reverse=True,
        )
        top_k = min(self.config.top_k, len(sorted_candidates))

        selected: List[CandidateRecord] = []
        # Per-fold selected values for pairwise correlation computation
        # Key = outer_fold_idx, Value = list of value arrays
        selected_fold_values: Dict[int, List[np.ndarray]] = {
            i: [] for i in range(len(outer_splits))
        }

        for candidate in sorted_candidates:
            if len(selected) >= top_k:
                break

            # Compute real pairwise correlation with already-selected candidates
            fold_corrs: List[float] = []
            for fold_idx, fold_vals_list in selected_fold_values.items():
                cand_vals = candidate._fold_values.get(fold_idx)
                if cand_vals is None:
                    continue
                fold_max_corr = 0.0
                cand_finite = np.isfinite(cand_vals)
                for sel_vals in fold_vals_list:
                    common = cand_finite & np.isfinite(sel_vals)
                    if np.sum(common) >= 10:
                        corr = _spearman_corr_via_ranks(
                            cand_vals[common], sel_vals[common],
                        )
                        if np.isfinite(corr):
                            fold_max_corr = max(
                                fold_max_corr, abs(float(corr)),
                            )
                fold_corrs.append(fold_max_corr)

            # P0 fix: worst-case (max) correlation across all outer folds.
            # If ANY fold breaches the threshold, deployment must be blocked.
            # Mean is kept only as a separate diagnostic field.
            max_corr = float(max(fold_corrs)) if fold_corrs else 0.0
            mean_fold_max_corr = (
                float(np.mean(fold_corrs)) if fold_corrs else 0.0
            )

            # Update metrics with real correlation (worst-case)
            candidate.inner_metrics["max_correlation"] = max_corr
            candidate.inner_metrics["mean_fold_max_correlation"] = (
                mean_fold_max_corr
            )

            # Recompute objective with real correlation penalty
            m = candidate.inner_metrics
            candidate.objective_score = (
                self.config.w_ic * m.get("signed_ic", 0.0)
                + self.config.w_sign_consistency * m.get("sign_consistency", 0.0)
                + self.config.w_dsr_proxy * m.get("dsr_proxy", 0.0)
                + self.config.w_coverage * m.get("coverage", 0.0)
                + self.config.w_low_correlation * (1.0 - max_corr)
            )

            # Accept candidate into selected set
            candidate.is_selected = True
            selected.append(candidate)

            # Add this candidate's values to the selected pool per fold
            for fold_idx in selected_fold_values:
                cand_vals = candidate._fold_values.get(fold_idx)
                if cand_vals is not None:
                    selected_fold_values[fold_idx].append(cand_vals)

        # Re-sort selected by updated objective (correlation may change order)
        selected.sort(key=lambda c: c.objective_score, reverse=True)
        selected_hashes = {candidate.formula_hash for candidate in selected}
        for candidate in all_candidates:
            if candidate.formula_hash not in selected_hashes:
                candidate.clear_signals()

        # Step 5: Correlation gate – computed FIRST (P0 fix3)
        # Worst-case max_pairwise_correlation across selected candidates/folds.
        corr_values = [
            c.inner_metrics.get("max_correlation", 0.0) for c in selected
        ]
        max_pairwise = max(corr_values) if corr_values else 0.0
        correlation_blocked = (
            max_pairwise > self.config.max_deploy_correlation
            if corr_values else False
        )
        correlation_stats = {
            "max_pairwise_correlation": max_pairwise,
            "mean_pairwise_correlation": (
                float(np.mean(corr_values)) if corr_values else 0.0
            ),
            "correlation_threshold": self.config.max_deploy_correlation,
            "correlation_blocked": correlation_blocked,
        }

        # Step 6: Deployment readiness check (strict)
        # P0 fix3: deployment_ready requires BOTH at least one deploy-ready
        # candidate AND no selected-candidate global correlation breach.
        any_candidate_deploy_ready = any(
            self.scorer.check_deploy_ready(c) for c in selected
        )
        deployment_ready = any_candidate_deploy_ready and not correlation_blocked

        # Build source proportion evidence
        source_counts: Dict[str, int] = {}
        for c in all_candidates:
            src = c.source.value
            source_counts[src] = source_counts.get(src, 0) + 1

        # Build evidence
        evidence = self._build_evidence(
            selected=selected,
            source_counts=source_counts,
            n_outer=len(outer_splits),
            total_generated=len(all_candidates),
            deployment_ready=deployment_ready,
            correlation_stats=correlation_stats,
        )

        logger.info(
            "Hybrid mining complete: %d candidates, %d selected, deploy_ready=%s",
            len(all_candidates),
            len(selected),
            deployment_ready,
        )

        return selected, evidence

    def _build_evidence(
        self,
        selected: List[CandidateRecord],
        source_counts: Dict[str, int],
        n_outer: int,
        total_generated: int = 0,
        deployment_ready: bool = False,
        correlation_stats: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build evidence dict for persistence."""
        evidence: Dict[str, Any] = {
            "config": {
                "candidate_budget": self.config.candidate_budget,
                "top_k": self.config.top_k,
                "n_outer_folds": self.config.n_outer_folds,
                "n_inner_folds": self.config.n_inner_folds,
                "llm_provider": self.config.llm_provider,
            },
            "source_proportions": source_counts,
            "total_generated": total_generated,
            "total_selected": len(selected),
            "n_outer_folds_evaluated": n_outer,
            "deployment_ready": deployment_ready,
            "requires_full_cpcv": True,
            "formula_memory": self.memory.get_motif_metrics(),
            "selected_candidates": [c.to_dict() for c in selected],
            "objective_weights": {
                "w_ic": self.config.w_ic,
                "w_sign_consistency": self.config.w_sign_consistency,
                "w_dsr_proxy": self.config.w_dsr_proxy,
                "w_coverage": self.config.w_coverage,
                "w_low_correlation": self.config.w_low_correlation,
            },
            "deploy_thresholds": {
                "min_deploy_ic": self.config.min_deploy_ic,
                "min_deploy_sign_consistency": self.config.min_deploy_sign_consistency,
                "min_deploy_dsr": self.config.min_deploy_dsr,
                "min_deploy_coverage": self.config.min_deploy_coverage,
                "max_deploy_correlation": self.config.max_deploy_correlation,
            },
            "pit_safety": {
                "panel_sliced_per_outer_fold": True,
                "ts_operators_cannot_see_outer_test": True,
                "inner_splits_use_local_indices": True,
                "ic_uses_signed_positive_only": True,
            },
        }
        if correlation_stats:
            evidence["correlation_gate"] = correlation_stats
        return evidence

    def save_evidence(self, evidence: Dict[str, Any], filepath: Path) -> None:
        """Save evidence to JSON file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(evidence, f, indent=2, default=str)
        logger.info("Evidence saved to %s", filepath)
