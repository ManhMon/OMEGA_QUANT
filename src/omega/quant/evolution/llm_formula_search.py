"""Closed-Loop LLM Formula Search.

Iterative formula search with aggregate failure feedback (PIT-safe).
Maintains failed formula memory, deduplicate across iterations, and provides
train-only scoring metadata without test-label leakage.

Author: Backend Engineer (Role 09)
Date: 2026-06-12
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from omega.quant.evolution.genetic_programming import GPNode
from omega.quant.evolution.llm_formula_scorer import (
    FormulaScorer,
    FormulaScorerConfig,
)
from omega.quant.evolution.llm_symbolic_synthesizer import LLMSymbolicSynthesizer

logger = logging.getLogger(__name__)


@dataclass
class FormulaSearchConfig:
    """Configuration for closed-loop LLM formula search."""
    
    # Search parameters
    max_iterations: int = 3  # Number of search iterations
    candidates_per_iteration: int = 10  # Formulas generated per iteration
    
    # Prompt configuration
    prompt_version: str = "vn_alpha_search_v3_closed_loop"  # V3 closed-loop prompt
    
    # LLM provider settings
    llm_provider: str = "mock"  # 'mock' or 'openai-compatible'
    
    # Scoring thresholds (train-only, PIT-safe)
    min_coverage: float = 0.80  # Minimum non-NaN coverage
    min_variance: float = 1e-8  # Minimum variance
    max_nan_inf_ratio: float = 0.20  # Maximum NaN/inf ratio
    
    # Deployment thresholds (require supervised validation on full CPCV)
    min_test_ic_for_deploy: float = 0.05  # Minimum test IC for deployment
    min_dsr_for_deploy: float = 0.5  # Minimum DSR for deployment
    
    # Memory management
    enable_formula_memory: bool = True  # Track failed formulas
    enable_motif_blacklist: bool = True  # Track bad motifs/patterns
    
    def __post_init__(self):
        """Validate configuration."""
        assert self.max_iterations > 0, "max_iterations must be positive"
        assert self.candidates_per_iteration > 0, "candidates_per_iteration must be positive"
        assert 0.0 <= self.min_coverage <= 1.0, "min_coverage must be in [0, 1]"
        assert self.min_variance >= 0, "min_variance must be non-negative"
        assert 0.0 <= self.max_nan_inf_ratio <= 1.0, "max_nan_inf_ratio must be in [0, 1]"


@dataclass
class FormulaSearchState:
    """State tracking for closed-loop formula search."""
    
    # Iteration tracking
    current_iteration: int = 0
    
    # Stage-by-stage counts (accumulated across all iterations)
    total_raw_generated: int = 0  # Raw LLM output count
    total_safety_validated: int = 0  # Passed safety parser
    total_unique_after_dedup: int = 0  # After memory deduplication
    total_scoring_input: int = 0  # Input to scorer (same as unique_after_dedup)
    total_scoring_accepted: int = 0  # Passed scoring thresholds
    total_scoring_rejected: int = 0  # Failed scoring thresholds
    
    # Failed formula memory (normalized formulas to avoid duplicates)
    failed_formulas: Set[str] = field(default_factory=set)
    
    # Bad motif blacklist (common failure patterns)
    bad_motifs: Set[str] = field(default_factory=set)
    
    # Aggregate failure stats (PIT-safe: no row-level data)
    aggregate_failure_stats: Dict[str, Any] = field(default_factory=dict)
    
    # Iteration history
    iteration_results: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_failed_formula(self, formula_normalized: str) -> None:
        """Add a normalized formula to the failed set."""
        self.failed_formulas.add(formula_normalized)
    
    def add_bad_motif(self, motif: str) -> None:
        """Add a bad motif pattern to the blacklist."""
        self.bad_motifs.add(motif)
    
    def update_aggregate_stats(self, stats: Dict[str, Any]) -> None:
        """Update aggregate failure statistics (PIT-safe)."""
        self.aggregate_failure_stats.update(stats)
    
    def is_duplicate(self, formula_normalized: str) -> bool:
        """Check if formula has been tried before."""
        return formula_normalized in self.failed_formulas
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to dict for JSON export."""
        return {
            "current_iteration": self.current_iteration,
            "total_raw_generated": self.total_raw_generated,
            "total_safety_validated": self.total_safety_validated,
            "total_unique_after_dedup": self.total_unique_after_dedup,
            "total_scoring_input": self.total_scoring_input,
            "total_scoring_accepted": self.total_scoring_accepted,
            "total_scoring_rejected": self.total_scoring_rejected,
            "failed_formulas": list(self.failed_formulas),
            "bad_motifs": list(self.bad_motifs),
            "aggregate_failure_stats": self.aggregate_failure_stats,
            "iteration_results": self.iteration_results,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FormulaSearchState:
        """Deserialize state from dict with backward compatibility."""
        state = cls()
        state.current_iteration = data.get("current_iteration", 0)
        
        # New stage-by-stage counts (with backward compatibility)
        state.total_raw_generated = data.get("total_raw_generated", data.get("total_candidates_generated", 0))
        state.total_safety_validated = data.get("total_safety_validated", 0)
        state.total_unique_after_dedup = data.get("total_unique_after_dedup", 0)
        state.total_scoring_input = data.get("total_scoring_input", 0)
        state.total_scoring_accepted = data.get("total_scoring_accepted", data.get("total_candidates_accepted", 0))
        state.total_scoring_rejected = data.get("total_scoring_rejected", 0)
        
        state.failed_formulas = set(data.get("failed_formulas", []))
        state.bad_motifs = set(data.get("bad_motifs", []))
        state.aggregate_failure_stats = data.get("aggregate_failure_stats", {})
        state.iteration_results = data.get("iteration_results", [])
        return state


class FormulaSearchRunner:
    """
    Closed-loop LLM formula search orchestrator.
    
    Workflow:
    1. Initialize synthesizer with v3 closed-loop prompt
    2. For each iteration:
       a. Generate candidates using LLM with aggregate failure context
       b. Deduplicate against failed formula memory
       c. Score on train-only data (PIT-safe)
       d. Track failures and update aggregate stats
       e. Feed aggregate stats back to next iteration
    3. Return final candidates (require full CPCV validation)
    
    PIT Safety:
    - Only uses train-fold data for candidate scoring
    - Aggregate failure stats only (no test labels)
    - Final candidates must pass full CPCV before deployment
    """
    
    def __init__(self, config: FormulaSearchConfig):
        """
        Initialize search runner.
        
        Args:
            config: Search configuration
        """
        self.config = config
        self.state = FormulaSearchState()
        
        # Initialize synthesizer with v3 prompt
        self.synthesizer = LLMSymbolicSynthesizer(
            provider=config.llm_provider,
            prompt_version=config.prompt_version,
            max_candidates=config.candidates_per_iteration,
        )
        
        # Initialize scorer with train-only config
        self.scorer_config = FormulaScorerConfig(
            min_coverage=config.min_coverage,
            min_variance=config.min_variance,
            max_nan_inf_ratio=config.max_nan_inf_ratio,
            allow_unvalidated=True,  # Accept unsupervised for train-only scoring
        )
        
        logger.info(
            "FormulaSearchRunner initialized: max_iterations=%d candidates_per_iter=%d prompt=%s",
            config.max_iterations,
            config.candidates_per_iteration,
            config.prompt_version,
        )
    
    def run_search(
        self,
        panel: pd.DataFrame,
        feat_cols: List[str],
        labels: Optional[np.ndarray] = None,
        ticker_col: str = "ticker",
        date_col: str = "date",
        top_features: Optional[List[Tuple[str, float]]] = None,
        correlation_clusters: Optional[List[List[str]]] = None,
    ) -> Tuple[List[GPNode], Dict[str, Any]]:
        """
        Run closed-loop formula search.
        
        PIT Safety:
        - panel and labels are train-fold only (provided by caller)
        - Scoring uses train-only data
        - Aggregate stats only (no row-level labels)
        - Final candidates require full CPCV validation before deployment
        
        Args:
            panel: Training panel (PIT-safe subset)
            feat_cols: Feature column names
            labels: Optional train-only labels for supervised metrics
            ticker_col: Ticker column name
            date_col: Date column name
            top_features: Optional top features for prompt
            correlation_clusters: Optional feature clusters for prompt
        
        Returns:
            Tuple of (final_candidate_nodes, search_evidence)
        """
        logger.info(
            "Starting closed-loop search: %d iterations, %d candidates/iter",
            self.config.max_iterations,
            self.config.candidates_per_iteration,
        )
        
        # Build feature dict for validation
        features = {col: panel[col].to_numpy() for col in feat_cols}
        
        # Accumulator for accepted candidates across all iterations
        final_candidates = []
        
        # Iterative search loop
        for iteration in range(self.config.max_iterations):
            self.state.current_iteration = iteration
            
            logger.info(
                "=== Iteration %d/%d ===",
                iteration + 1,
                self.config.max_iterations,
            )
            
            # Generate candidates with aggregate failure context
            prior_failure_stats = (
                self.state.aggregate_failure_stats
                if self.state.aggregate_failure_stats
                else None
            )
            
            candidate_nodes, synth_stats = self.synthesizer.synthesize(
                features=features,
                top_features=top_features,
                correlation_clusters=correlation_clusters,
                prior_failure_stats=prior_failure_stats,
                bad_motifs=self.state.bad_motifs if self.config.enable_motif_blacklist else None,
            )
            
            # Track stage 1: raw generation and safety validation
            raw_count = synth_stats.get("total_raw", 0)
            safety_validated_count = synth_stats.get("accepted", len(candidate_nodes))
            
            self.state.total_raw_generated += raw_count
            self.state.total_safety_validated += safety_validated_count
            
            logger.info(
                "Iteration %d: Generated %d raw, %d passed safety validation",
                iteration + 1,
                raw_count,
                safety_validated_count,
            )
            
            if not candidate_nodes:
                logger.warning("Iteration %d: No candidates generated, continuing", iteration + 1)
                self.state.iteration_results.append({
                    "iteration": iteration + 1,
                    "raw_generated": raw_count,
                    "safety_validated": safety_validated_count,
                    "unique_after_dedup": 0,
                    "scoring_input": 0,
                    "scoring_accepted": 0,
                    "scoring_rejected": 0,
                    "synthesis_stats": synth_stats,
                })
                continue
            
            # Track stage 2: deduplication
            unique_nodes = []
            duplicate_count = 0
            
            if self.config.enable_formula_memory:
                for node in candidate_nodes:
                    # Generate formula string for deduplication check
                    formula_str = self._node_to_formula_string(node)
                    normalized = self.synthesizer.normalize_formula(formula_str)
                    
                    if not self.state.is_duplicate(normalized):
                        unique_nodes.append(node)
                    else:
                        duplicate_count += 1
                        logger.debug("Duplicate formula rejected: %s", formula_str)
                
                unique_count = len(unique_nodes)
                self.state.total_unique_after_dedup += unique_count
                
                logger.info(
                    "Iteration %d: Deduplication - %d unique, %d duplicates",
                    iteration + 1,
                    unique_count,
                    duplicate_count,
                )
                candidate_nodes = unique_nodes
            else:
                # No deduplication, all candidates are unique
                unique_count = len(candidate_nodes)
                self.state.total_unique_after_dedup += unique_count
            
            if not candidate_nodes:
                logger.warning("Iteration %d: All candidates were duplicates", iteration + 1)
                self.state.iteration_results.append({
                    "iteration": iteration + 1,
                    "raw_generated": raw_count,
                    "safety_validated": safety_validated_count,
                    "unique_after_dedup": 0,
                    "scoring_input": 0,
                    "scoring_accepted": 0,
                    "scoring_rejected": 0,
                    "all_duplicates": True,
                })
                continue
            
            # Track stage 3: scoring
            scoring_input_count = len(candidate_nodes)
            self.state.total_scoring_input += scoring_input_count
            
            # Adjust scorer config based on label availability
            # If labels provided, use supervised thresholds for acceptance
            # Otherwise, use unsupervised-only mode
            scorer_config = self.scorer_config
            if labels is not None:
                # Supervised mode: require IC/DSR thresholds
                scorer_config = FormulaScorerConfig(
                    min_coverage=self.config.min_coverage,
                    min_variance=self.config.min_variance,
                    max_nan_inf_ratio=self.config.max_nan_inf_ratio,
                    min_absolute_ic=0.01,  # Require minimum IC
                    min_dsr_proxy=-0.5,  # Require non-negative DSR proxy
                    allow_unvalidated=False,  # Supervised validation required
                )
                logger.info(
                    "Iteration %d: Using supervised scoring (IC >= 0.01, DSR >= -0.5)",
                    iteration + 1,
                )
            else:
                logger.info(
                    "Iteration %d: Using unsupervised scoring (no labels available)",
                    iteration + 1,
                )
            
            # Score candidates on train-only data
            accepted_nodes, score_stats = self.synthesizer.score_and_filter_formulas(
                nodes=candidate_nodes,
                panel=panel,
                feat_cols=feat_cols,
                labels=labels,  # Train-only labels (PIT-safe)
                scorer_config=scorer_config,
                ticker_col=ticker_col,
                date_col=date_col,
                synthesis_stats=synth_stats,
            )
            
            scoring_accepted_count = len(accepted_nodes)
            scoring_rejected_count = scoring_input_count - scoring_accepted_count
            
            self.state.total_scoring_accepted += scoring_accepted_count
            self.state.total_scoring_rejected += scoring_rejected_count
            
            logger.info(
                "Iteration %d: Scoring - %d input, %d accepted, %d rejected",
                iteration + 1,
                scoring_input_count,
                scoring_accepted_count,
                scoring_rejected_count,
            )
            
            # Accumulate accepted nodes from this iteration
            final_candidates.extend(accepted_nodes)
            
            # Update failed formula memory and extract bad motifs
            if self.config.enable_formula_memory:
                for name, details in score_stats.get("details", {}).items():
                    if not details.get("accepted", False):
                        # Reconstruct formula string from node
                        node_idx = int(name.split("_")[-1])
                        if node_idx < len(candidate_nodes):
                            formula_str = self._node_to_formula_string(candidate_nodes[node_idx])
                            normalized = self.synthesizer.normalize_formula(formula_str)
                            self.state.add_failed_formula(normalized)
                            
                            # Extract bad motifs from failed formula
                            if self.config.enable_motif_blacklist:
                                motifs = self._extract_motifs(formula_str)
                                for motif in motifs:
                                    self.state.add_bad_motif(motif)
            
            # Extract aggregate failure stats (PIT-safe: no row-level data)
            if scoring_rejected_count > 0 and labels is not None:
                aggregate_stats = self._compute_aggregate_failure_stats(
                    score_stats, labels
                )
                self.state.update_aggregate_stats(aggregate_stats)
                
                logger.info(
                    "Iteration %d: Aggregate failure stats updated - median_ic=%.4f",
                    iteration + 1,
                    aggregate_stats.get("median_train_ic", 0.0),
                )
            
            # Record iteration results with detailed stage counts
            self.state.iteration_results.append({
                "iteration": iteration + 1,
                "raw_generated": raw_count,
                "safety_validated": safety_validated_count,
                "unique_after_dedup": unique_count,
                "scoring_input": scoring_input_count,
                "scoring_accepted": scoring_accepted_count,
                "scoring_rejected": scoring_rejected_count,
                "synthesis_stats": synth_stats,
                "scoring_stats": score_stats,
            })
        
        # Final candidates accumulated from all iterations (no re-synthesis)
        logger.info(
            "Closed-loop search complete: accumulated %d candidates from %d iterations",
            len(final_candidates),
            self.config.max_iterations,
        )
        
        # Build search evidence with detailed stage-by-stage counts (never negative)
        search_evidence = {
            "config": {
                "max_iterations": self.config.max_iterations,
                "candidates_per_iteration": self.config.candidates_per_iteration,
                "prompt_version": self.config.prompt_version,
                "llm_provider": self.config.llm_provider,
            },
            "final_state": self.state.to_dict(),
            "summary": {
                # Stage-by-stage accumulated counts (across all iterations)
                "total_raw_generated": self.state.total_raw_generated,
                "total_safety_validated": self.state.total_safety_validated,
                "total_unique_after_dedup": self.state.total_unique_after_dedup,
                "total_scoring_input": self.state.total_scoring_input,
                "total_scoring_accepted": self.state.total_scoring_accepted,
                "total_scoring_rejected": self.state.total_scoring_rejected,
                
                # Legacy field names for backward compatibility
                "total_candidates_generated": self.state.total_raw_generated,
                "total_candidates_accepted": self.state.total_scoring_accepted,
                
                # Final accumulated candidate count (may differ from scoring_accepted if multiple iterations)
                "final_candidate_count": len(final_candidates),
                
                # Memory stats
                "failed_formulas_count": len(self.state.failed_formulas),
                "bad_motifs_count": len(self.state.bad_motifs),
            },
            "requires_full_cpcv": True,  # Final candidates MUST pass full CPCV
            "deployment_ready": False,  # Set to True only after full CPCV passes thresholds
        }
        
        logger.info(
            "Search complete: %d raw generated, %d safety validated, %d unique, "
            "%d scoring accepted, %d scoring rejected, %d final candidates",
            self.state.total_raw_generated,
            self.state.total_safety_validated,
            self.state.total_unique_after_dedup,
            self.state.total_scoring_accepted,
            self.state.total_scoring_rejected,
            len(final_candidates),
        )
        
        return final_candidates, search_evidence
    
    def select_top_k_candidates(
        self,
        candidate_nodes: List[GPNode],
        panel: pd.DataFrame,
        feat_cols: List[str],
        labels: Optional[np.ndarray] = None,
        top_k: int = 10,
        ticker_col: str = "ticker",
        date_col: str = "date",
    ) -> Tuple[List[GPNode], Dict[str, Any]]:
        """
        Select top K candidates based on supervised or unsupervised metrics.
        
        If labels are provided, ranks by absolute IC (supervised).
        Otherwise, ranks by variance (unsupervised proxy for signal strength).
        
        Args:
            candidate_nodes: List of candidate GPNode formulas
            panel: Panel data for execution
            feat_cols: Feature column names
            labels: Optional labels for supervised ranking (PIT-safe: train-only)
            top_k: Number of top candidates to select
            ticker_col: Ticker column name
            date_col: Date column name
        
        Returns:
            Tuple of (selected_nodes, selection_stats)
        """
        if not candidate_nodes:
            logger.warning("No candidates to select from")
            return [], {"top_k": top_k, "selected": 0, "selection_mode": "none"}
        
        if len(candidate_nodes) <= top_k:
            logger.info(
                "Candidate count %d <= top_k %d, returning all candidates",
                len(candidate_nodes),
                top_k,
            )
            return candidate_nodes, {
                "top_k": top_k,
                "selected": len(candidate_nodes),
                "selection_mode": "supervised" if labels is not None else "unsupervised",
                "metric_name": "absolute_ic" if labels is not None else "variance",
                "ranking_skipped": True,  # Indicate ranking was skipped
                "top_scores": [],  # No ranking performed
                "all_scores": [],  # No ranking performed
            }
        
        logger.info(
            "Selecting top %d candidates from %d using %s metrics",
            top_k,
            len(candidate_nodes),
            "supervised" if labels is not None else "unsupervised",
        )
        
        # Execute all candidates and compute ranking metrics
        candidate_scores = []
        
        for i, node in enumerate(candidate_nodes):
            try:
                # Execute node on panel (PIT-safe grouped execution)
                values = self.synthesizer.execute_node_grouped(
                    node, panel, feat_cols, ticker_col=ticker_col, date_col=date_col
                )
                
                # Compute ranking metric
                if labels is not None:
                    # Supervised: rank by absolute IC
                    valid_mask = np.isfinite(values) & np.isfinite(labels)
                    if np.sum(valid_mask) >= 2:
                        ic = abs(float(np.corrcoef(values[valid_mask], labels[valid_mask])[0, 1]))
                    else:
                        ic = 0.0
                    score = ic
                    metric_name = "absolute_ic"
                else:
                    # Unsupervised: rank by variance (proxy for signal strength)
                    valid_values = values[np.isfinite(values)]
                    if len(valid_values) >= 2:
                        variance = float(np.var(valid_values, ddof=1))
                    else:
                        variance = 0.0
                    score = variance
                    metric_name = "variance"
                
                candidate_scores.append({
                    "index": i,
                    "node": node,
                    "score": score,
                    "metric": metric_name,
                })
            except Exception as e:
                logger.warning(
                    "Failed to execute candidate %d for ranking: %s",
                    i,
                    str(e),
                )
                candidate_scores.append({
                    "index": i,
                    "node": node,
                    "score": 0.0,
                    "metric": "error",
                })
        
        # Sort by score descending and select top K
        candidate_scores.sort(key=lambda x: x["score"], reverse=True)
        top_k_scores = candidate_scores[:top_k]
        
        selected_nodes = [item["node"] for item in top_k_scores]
        
        # Build selection stats
        selection_stats = {
            "top_k": top_k,
            "selected": len(selected_nodes),
            "selection_mode": "supervised" if labels is not None else "unsupervised",
            "metric_name": top_k_scores[0]["metric"] if top_k_scores else "none",
            "top_scores": [item["score"] for item in top_k_scores],
            "all_scores": [item["score"] for item in candidate_scores],
        }
        
        logger.info(
            "Selected top %d candidates: %s scores: [%.4f, %.4f, ..., %.4f]",
            len(selected_nodes),
            selection_stats["metric_name"],
            selection_stats["top_scores"][0] if selection_stats["top_scores"] else 0.0,
            selection_stats["top_scores"][1] if len(selection_stats["top_scores"]) > 1 else 0.0,
            selection_stats["top_scores"][-1] if selection_stats["top_scores"] else 0.0,
        )
        
        return selected_nodes, selection_stats
    
    def _node_to_formula_string(self, node: GPNode) -> str:
        """
        Convert GPNode to formula string for deduplication.
        
        Args:
            node: GPNode tree
        
        Returns:
            Formula string representation
        """
        if node.operator == "terminal":
            return str(node.value)
        
        if not node.children:
            return f"{node.operator}()"
        
        # Recursive reconstruction
        args_str = ", ".join([self._node_to_formula_string(child) for child in node.children])
        
        # Map operator to function name
        op_to_func = {
            "+": "add",
            "-": "sub",
            "*": "mul",
            "/": "div",
        }
        func_name = op_to_func.get(node.operator, node.operator)
        
        return f"{func_name}({args_str})"
    
    def _extract_motifs(self, formula: str) -> Set[str]:
        """
        Extract bad motif patterns from a failed formula.
        
        Extracts aggregate patterns only (no specific lookback values).
        Examples:
        - "ts_mean(close, 20)" -> {"ts_mean", "ts_mean(close"}
        - "div(volume, ret_1d)" -> {"div", "div(volume"}
        
        Args:
            formula: Formula string
        
        Returns:
            Set of motif patterns
        """
        motifs = set()
        
        # Extract top-level function (first token before '(')
        if '(' in formula:
            top_func = formula.split('(')[0]
            motifs.add(top_func)
            
            # Extract function + first argument patterns
            # This helps identify patterns like "ts_mean(volume" or "div(close"
            try:
                # Find first opening paren
                start = formula.index('(') + 1
                # Find first comma or closing paren
                end = start
                depth = 0
                while end < len(formula):
                    char = formula[end]
                    if char == '(':
                        depth += 1
                    elif char == ')':
                        if depth == 0:
                            break
                        depth -= 1
                    elif char == ',' and depth == 0:
                        break
                    end += 1
                
                first_arg = formula[start:end].strip()
                if first_arg and not first_arg[0].isdigit():  # Exclude numeric constants
                    motifs.add(f"{top_func}({first_arg}")
            except (ValueError, IndexError):
                pass  # Malformed formula, skip pattern extraction
        
        return motifs
    
    def _compute_aggregate_failure_stats(
        self,
        score_stats: Dict[str, Any],
        labels: np.ndarray,
    ) -> Dict[str, float]:
        """
        Compute aggregate failure statistics (PIT-safe).
        
        Only uses aggregate metrics (median, mean) from rejected formulas.
        Does NOT include row-level label data or individual formula predictions.
        
        Args:
            score_stats: Scoring statistics from score_and_filter_formulas
            labels: Train-only labels (used only for aggregate IC computation)
        
        Returns:
            Dict of aggregate stats (median_train_ic, median_dsr, etc.)
        """
        # Collect metrics from rejected formulas only
        rejected_ics = []
        rejected_dsrs = []
        
        for name, details in score_stats.get("details", {}).items():
            if not details.get("accepted", False):
                # Only include supervised metrics if available
                if details.get("absolute_ic") is not None:
                    rejected_ics.append(details["absolute_ic"])
                if details.get("dsr_proxy") is not None:
                    rejected_dsrs.append(details["dsr_proxy"])
        
        # Compute aggregate stats (PIT-safe)
        aggregate_stats = {}
        
        if rejected_ics:
            aggregate_stats["median_train_ic"] = float(np.median(rejected_ics))
            aggregate_stats["mean_train_ic"] = float(np.mean(rejected_ics))
        
        if rejected_dsrs:
            aggregate_stats["median_dsr"] = float(np.median(rejected_dsrs))
            aggregate_stats["mean_dsr"] = float(np.mean(rejected_dsrs))
        
        return aggregate_stats
    
    def save_state(self, filepath: Path) -> None:
        """Save search state to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.state.to_dict(), f, indent=2)
        logger.info("Search state saved to %s", filepath)
    
    def load_state(self, filepath: Path) -> None:
        """Load search state from JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)
        self.state = FormulaSearchState.from_dict(data)
        logger.info("Search state loaded from %s", filepath)
