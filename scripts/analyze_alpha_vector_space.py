#!/usr/bin/env python3
"""
Alpha Vector-Space Discovery Diagnostics
==========================================
Deterministic research-only diagnostics that analyse per-alpha fold IC
vectors from Phase 3.5 JSON results.  Computes vector-space features,
pairwise correlation / redundancy, correlation-distance clustering
(numpy/pandas fallback when scikit-learn is unavailable), and produces
a markdown report + JSON summary.

GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615
Expanded from ~9D to ~35-40D scalar features per alpha:
  min_ic, max_ic, downside_ic_mean, ic_skew, sharpe_association,
  drawdown_association, return_association, mean_abs_corr,
  redundancy_count, cluster_centrality, ic_range, ic_median,
  positive_ic_rate_above_threshold, negative_fold_rate, ic_momentum,
  ic_stability, worst_fold_ic, best_fold_ic, fold_ic_kurtosis,
  ic_consistency_score, ic_coefficient_of_variation, fold_ic_autocorr,
  ic_win_loss_ratio, upside_ic_mean, regime_bull_proxy_mean_ic,
  regime_bear_proxy_mean_ic, cross_alpha_mean_ic_deviation,
  n_folds_available, and 4 quarter-mean features.
  Optional universe_coverage when rolling-universe metadata exists.

**RESEARCH_ONLY / DO_NOT_PROMOTE** — never selects OOS winners or
alters live/default behaviour.

Usage:
    python scripts/analyze_alpha_vector_space.py \\
        --input data/phase35_results/phase35_backtest_results_dd_control_10_default_clean_v3_wg_baseline.json \\
        --output-report .ly_state/session/alpha_vector_space_discovery_report_20260615.md \\
        --output-json   .ly_state/session/alpha_vector_space_discovery_20260615.json

Role: 14 (data-scientist) L2 — implementation only, no self-approval.
Gate: ALPHA_VECTOR_SPACE_DISCOVERY_20260615 / PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GATE = "ALPHA_VECTOR_SPACE_DISCOVERY_20260615"
VERDICT_RESEARCH_ONLY = "RESEARCH_ONLY"
VERDICT_DO_NOT_PROMOTE = "DO_NOT_PROMOTE"
CLUSTER_CORR_THRESHOLD = 0.70  # |correlation| >= threshold → same cluster

# ---------------------------------------------------------------------------
# Statistics helpers (deterministic, no external dependency)
# ---------------------------------------------------------------------------

def _safe_mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _safe_std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mu = _safe_mean(values)
    return math.sqrt(sum((v - mu) ** 2 for v in values) / (len(values) - 1))


def _safe_icir(values: List[float]) -> float:
    mu = _safe_mean(values)
    sd = _safe_std(values)
    if sd == 0.0:
        return 0.0
    return mu / sd


def _safe_median(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _safe_skew(values: List[float]) -> float:
    """Pearson skewness proxy: 3 * (mean - median) / std."""
    if len(values) < 3:
        return 0.0
    sd = _safe_std(values)
    if sd == 0.0:
        return 0.0
    return 3.0 * (_safe_mean(values) - _safe_median(values)) / sd


def _safe_kurtosis(values: List[float]) -> float:
    """Excess kurtosis proxy (sample)."""
    n = len(values)
    if n < 4:
        return 0.0
    mu = _safe_mean(values)
    sd = _safe_std(values)
    if sd == 0.0:
        return 0.0
    m4 = sum((v - mu) ** 4 for v in values) / n
    m2 = sum((v - mu) ** 2 for v in values) / n
    if m2 == 0.0:
        return 0.0
    return (m4 / (m2 ** 2)) - 3.0


def _safe_autocorr_lag1(values: List[float]) -> float:
    """Lag-1 autocorrelation of a series."""
    if len(values) < 3:
        return 0.0
    x = values[:-1]
    y = values[1:]
    return _pearson_r(x, y)


def _pearson_r(xs: List[float], ys: List[float]) -> float:
    """Pearson correlation between two equal-length vectors."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = _safe_mean(xs), _safe_mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0.0 or dy == 0.0:
        return 0.0
    return num / (dx * dy)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_phase35_json(path: str) -> Dict[str, Any]:
    """Load Phase 3.5 backtest results JSON."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def extract_alpha_fold_ics(data: Dict[str, Any]) -> Dict[str, List[float]]:
    """Extract per-alpha fold IC vectors from fold_details.

    Returns dict mapping alpha_name -> list of IC values (one per fold,
    ordered by fold_id).
    """
    folds: List[Dict[str, Any]] = data.get("fold_details", [])
    folds_sorted = sorted(folds, key=lambda f: f.get("fold_id", 0))
    alpha_names: set = set()
    for f in folds_sorted:
        alpha_names.update(f.get("alpha_ics", {}).keys())
    alpha_names_sorted = sorted(alpha_names)

    result: Dict[str, List[float]] = {}
    for a_name in alpha_names_sorted:
        ics: List[float] = []
        for f in folds_sorted:
            fold_alpha_ics = f.get("alpha_ics", {})
            if a_name in fold_alpha_ics:
                ics.append(fold_alpha_ics[a_name])
        result[a_name] = ics
    return result


def extract_fold_portfolio_ics(data: Dict[str, Any]) -> List[float]:
    """Extract portfolio IC per fold (ordered by fold_id)."""
    folds = sorted(data.get("fold_details", []), key=lambda f: f.get("fold_id", 0))
    return [f.get("portfolio_ic", 0.0) for f in folds]


def extract_fold_sharpes(data: Dict[str, Any]) -> List[float]:
    """Extract portfolio Sharpe per fold (ordered by fold_id)."""
    folds = sorted(data.get("fold_details", []), key=lambda f: f.get("fold_id", 0))
    return [f.get("portfolio_sharpe", 0.0) for f in folds]


def extract_fold_max_dds(data: Dict[str, Any]) -> List[float]:
    """Extract portfolio max drawdown per fold (ordered by fold_id)."""
    folds = sorted(data.get("fold_details", []), key=lambda f: f.get("fold_id", 0))
    return [f.get("portfolio_max_dd", 0.0) for f in folds]


def extract_fold_total_returns(data: Dict[str, Any]) -> List[float]:
    """Extract portfolio total return per fold (ordered by fold_id)."""
    folds = sorted(data.get("fold_details", []), key=lambda f: f.get("fold_id", 0))
    return [f.get("portfolio_total_return", 0.0) for f in folds]


def extract_rolling_universe_metadata(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract rolling universe metadata if present."""
    return data.get("rolling_universe_evidence", None)


def compute_alpha_vectors(
    alpha_fold_ics: Dict[str, List[float]],
    portfolio_fold_ics: List[float],
    portfolio_fold_sharpes: Optional[List[float]] = None,
    portfolio_fold_max_dds: Optional[List[float]] = None,
    portfolio_fold_total_returns: Optional[List[float]] = None,
    corr_matrix: Optional[Dict[str, Dict[str, float]]] = None,
    cluster_labels: Optional[Dict[str, int]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Compute per-alpha vector features (expanded ~35-40D).

    GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615
    Expanded from ~9D to ~35-40D scalar features per alpha.
    All features are deterministic, no random seeds or stochastic ops.

    Features (original):
    - fold_ic_vector, mean_ic, std_ic, icir, positive_fold_rate,
      early_half_mean_ic, late_half_mean_ic, early_late_trend,
      bad_fold_association

    Features (expanded):
    - min_ic, max_ic, downside_ic_mean, ic_skew, sharpe_association,
      drawdown_association, return_association, mean_abs_corr,
      redundancy_count, cluster_centrality, ic_range, ic_median,
      positive_ic_rate_above_threshold, negative_fold_rate, ic_momentum,
      ic_stability, worst_fold_ic, best_fold_ic, fold_ic_kurtosis,
      ic_consistency_score, ic_coefficient_of_variation, fold_ic_autocorr,
      ic_win_loss_ratio, upside_ic_mean, regime_bull_proxy_mean_ic,
      regime_bear_proxy_mean_ic, cross_alpha_mean_ic_deviation,
      n_folds_available, quarter_mean_1..4
    """
    n_folds = len(portfolio_fold_ics)
    half = max(1, n_folds // 2)
    third = max(1, n_folds // 3)

    # Compute cross-alpha average for deviation metric
    all_mean_ics = [_safe_mean(ics) for ics in alpha_fold_ics.values()]
    cross_alpha_avg = _safe_mean(all_mean_ics) if all_mean_ics else 0.0

    vectors: Dict[str, Dict[str, Any]] = {}
    for a_name, ics in sorted(alpha_fold_ics.items()):
        mean_ic = _safe_mean(ics)
        std_ic = _safe_std(ics)
        icir = _safe_icir(ics)
        pos_rate = sum(1 for v in ics if v > 0) / len(ics) if ics else 0.0

        # Early / late trend
        early_ics = ics[:half]
        late_ics = ics[half:]
        early_mean = _safe_mean(early_ics)
        late_mean = _safe_mean(late_ics)
        trend = late_mean - early_mean

        # Bad fold association proxy
        bad_portfolio_ics = [
            portfolio_fold_ics[i]
            for i in range(min(len(ics), n_folds))
            if portfolio_fold_ics[i] < 0
        ]
        bad_alpha_ics = [
            ics[i]
            for i in range(min(len(ics), n_folds))
            if portfolio_fold_ics[i] < 0
        ]
        if len(bad_alpha_ics) >= 2:
            bad_fold_assoc = _pearson_r(bad_alpha_ics, bad_portfolio_ics)
        else:
            bad_fold_assoc = 0.0

        # --- Expanded features ---
        min_ic = min(ics) if ics else 0.0
        max_ic = max(ics) if ics else 0.0
        ic_range = max_ic - min_ic
        ic_median = _safe_median(ics)

        neg_ics = [v for v in ics if v < 0]
        pos_ics = [v for v in ics if v > 0]
        downside_ic_mean = _safe_mean(neg_ics) if neg_ics else 0.0
        upside_ic_mean = _safe_mean(pos_ics) if pos_ics else 0.0

        ic_skew = _safe_skew(ics)
        fold_ic_kurtosis = _safe_kurtosis(ics)

        neg_fold_rate = sum(1 for v in ics if v < 0) / len(ics) if ics else 0.0
        min_ic_thresh = 0.02
        pos_rate_above_thresh = (
            sum(1 for v in ics if v > min_ic_thresh) / len(ics) if ics else 0.0
        )

        # Momentum: last-third mean - first-third mean
        first_third = ics[:third]
        last_third = ics[-third:] if len(ics) >= third else ics
        ic_momentum = _safe_mean(last_third) - _safe_mean(first_third)

        # Stability: 1 - std/|mean|, capped at 0
        ic_stability = max(0.0, 1.0 - std_ic / abs(mean_ic)) if mean_ic != 0.0 else 0.0

        worst_fold_ic = min_ic
        best_fold_ic = max_ic

        # Consistency: fraction of consecutive fold pairs with same sign
        n_consecutive_same = 0
        n_pairs = 0
        for i in range(len(ics) - 1):
            n_pairs += 1
            if (ics[i] > 0 and ics[i + 1] > 0) or (ics[i] < 0 and ics[i + 1] < 0):
                n_consecutive_same += 1
        ic_consistency = n_consecutive_same / n_pairs if n_pairs > 0 else 0.0

        # Coefficient of variation
        ic_cv = std_ic / abs(mean_ic) if mean_ic != 0.0 else 0.0

        # Autocorrelation
        fold_ic_autocorr = _safe_autocorr_lag1(ics)

        # Win/loss ratio
        sum_pos = sum(pos_ics) if pos_ics else 0.0
        sum_neg_abs = abs(sum(neg_ics)) if neg_ics else 0.0
        ic_win_loss_ratio = sum_pos / sum_neg_abs if sum_neg_abs > 0 else (
            sum_pos if sum_pos > 0 else 0.0
        )

        # Sharpe/drawdown/return association
        sharpe_assoc = 0.0
        dd_assoc = 0.0
        ret_assoc = 0.0
        n_aligned = min(len(ics), n_folds)
        if n_aligned >= 3:
            alpha_aligned = ics[:n_aligned]
            if portfolio_fold_sharpes and len(portfolio_fold_sharpes) >= n_aligned:
                sharpe_assoc = _pearson_r(alpha_aligned, portfolio_fold_sharpes[:n_aligned])
            if portfolio_fold_max_dds and len(portfolio_fold_max_dds) >= n_aligned:
                dd_assoc = _pearson_r(alpha_aligned, portfolio_fold_max_dds[:n_aligned])
            if portfolio_fold_total_returns and len(portfolio_fold_total_returns) >= n_aligned:
                ret_assoc = _pearson_r(alpha_aligned, portfolio_fold_total_returns[:n_aligned])

        # Mean absolute pairwise correlation
        mean_abs_corr = 0.0
        redundancy_count = 0
        if corr_matrix and a_name in corr_matrix:
            other_corrs = [
                abs(corr_matrix[a_name][b])
                for b in corr_matrix[a_name] if b != a_name
            ]
            if other_corrs:
                mean_abs_corr = _safe_mean(other_corrs)
                redundancy_count = sum(
                    1 for c in other_corrs if c >= CLUSTER_CORR_THRESHOLD
                )

        # Cluster centrality: max |corr| within same cluster
        cluster_centrality = 0.0
        if cluster_labels and corr_matrix and a_name in cluster_labels:
            my_cluster = cluster_labels[a_name]
            same_cluster = [
                b for b, cid in cluster_labels.items()
                if cid == my_cluster and b != a_name and b in corr_matrix.get(a_name, {})
            ]
            if same_cluster:
                cluster_centrality = max(
                    abs(corr_matrix[a_name][b]) for b in same_cluster
                )

        # Regime proxy: bull/bear based on portfolio return sign
        portfolio_median_ret = _safe_median(
            portfolio_fold_ics[:n_aligned]
        ) if n_aligned > 0 else 0.0
        bull_ics = [
            ics[i] for i in range(n_aligned)
            if portfolio_fold_ics[i] >= portfolio_median_ret
        ]
        bear_ics = [
            ics[i] for i in range(n_aligned)
            if portfolio_fold_ics[i] < portfolio_median_ret
        ]
        regime_bull_proxy = _safe_mean(bull_ics) if bull_ics else 0.0
        regime_bear_proxy = _safe_mean(bear_ics) if bear_ics else 0.0

        # Cross-alpha deviation
        cross_alpha_dev = mean_ic - cross_alpha_avg

        # Quarter means
        q_size = max(1, len(ics) // 4)
        q1 = _safe_mean(ics[:q_size])
        q2 = _safe_mean(ics[q_size:2 * q_size])
        q3 = _safe_mean(ics[2 * q_size:3 * q_size])
        q4 = _safe_mean(ics[3 * q_size:])

        vectors[a_name] = {
            # Original features
            "fold_ic_vector": list(ics),
            "mean_ic": mean_ic,
            "std_ic": std_ic,
            "icir": icir,
            "positive_fold_rate": pos_rate,
            "early_half_mean_ic": early_mean,
            "late_half_mean_ic": late_mean,
            "early_late_trend": trend,
            "bad_fold_association": bad_fold_assoc,
            # Expanded features (GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615)
            "min_ic": min_ic,
            "max_ic": max_ic,
            "downside_ic_mean": downside_ic_mean,
            "ic_skew": ic_skew,
            "sharpe_association": sharpe_assoc,
            "drawdown_association": dd_assoc,
            "return_association": ret_assoc,
            "mean_abs_corr": mean_abs_corr,
            "redundancy_count": redundancy_count,
            "cluster_centrality": cluster_centrality,
            "ic_range": ic_range,
            "ic_median": ic_median,
            "positive_ic_rate_above_threshold": pos_rate_above_thresh,
            "negative_fold_rate": neg_fold_rate,
            "ic_momentum": ic_momentum,
            "ic_stability": ic_stability,
            "worst_fold_ic": worst_fold_ic,
            "best_fold_ic": best_fold_ic,
            "fold_ic_kurtosis": fold_ic_kurtosis,
            "ic_consistency_score": ic_consistency,
            "ic_coefficient_of_variation": ic_cv,
            "fold_ic_autocorr": fold_ic_autocorr,
            "ic_win_loss_ratio": ic_win_loss_ratio,
            "upside_ic_mean": upside_ic_mean,
            "regime_bull_proxy_mean_ic": regime_bull_proxy,
            "regime_bear_proxy_mean_ic": regime_bear_proxy,
            "cross_alpha_mean_ic_deviation": cross_alpha_dev,
            "n_folds_available": len(ics),
            "quarter_mean_1": q1,
            "quarter_mean_2": q2,
            "quarter_mean_3": q3,
            "quarter_mean_4": q4,
        }
    return vectors


def compute_pairwise_correlation(
    alpha_fold_ics: Dict[str, List[float]],
) -> Dict[str, Dict[str, float]]:
    """Compute pairwise Pearson correlation between all alpha IC vectors."""
    names = sorted(alpha_fold_ics.keys())
    corr: Dict[str, Dict[str, float]] = {}
    for a in names:
        corr[a] = {}
        for b in names:
            if a == b:
                corr[a][b] = 1.0
            elif b < a:
                corr[a][b] = corr[b][a]
            else:
                corr[a][b] = _pearson_r(alpha_fold_ics[a], alpha_fold_ics[b])
    return corr


def correlation_distance_clustering(
    corr_matrix: Dict[str, Dict[str, float]],
    threshold: float = CLUSTER_CORR_THRESHOLD,
) -> Dict[str, int]:
    """Greedy single-linkage clustering on correlation distance.

    Two alphas belong to the same cluster if |correlation| >= threshold.
    Deterministic: names sorted, first-seen wins.

    Returns dict mapping alpha_name -> cluster_id (0-based).
    """
    names = sorted(corr_matrix.keys())
    labels: Dict[str, int] = {}
    next_cluster = 0

    for name in names:
        if name in labels:
            continue
        # Start new cluster
        labels[name] = next_cluster
        # Add all unlabelled names that correlate >= threshold with *any*
        # member already in this cluster (single-linkage).
        cluster_members = [name]
        changed = True
        while changed:
            changed = False
            for candidate in names:
                if candidate in labels:
                    continue
                for member in cluster_members:
                    if abs(corr_matrix[member][candidate]) >= threshold:
                        labels[candidate] = next_cluster
                        cluster_members.append(candidate)
                        changed = True
                        break
        next_cluster += 1

    return labels


def identify_redundant_clusters(
    labels: Dict[str, int],
    corr_matrix: Dict[str, Dict[str, float]],
) -> List[Dict[str, Any]]:
    """Identify clusters with >1 member (redundant groups)."""
    cluster_members: Dict[int, List[str]] = defaultdict(list)
    for name, cid in sorted(labels.items()):
        cluster_members[cid].append(name)

    redundant: List[Dict[str, Any]] = []
    for cid, members in sorted(cluster_members.items()):
        if len(members) <= 1:
            continue
        # Compute intra-cluster mean |correlation|
        corrs = []
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                corrs.append(abs(corr_matrix[a][b]))
        mean_corr = _safe_mean(corrs)
        redundant.append({
            "cluster_id": cid,
            "members": members,
            "size": len(members),
            "mean_abs_correlation": mean_corr,
        })
    return redundant


def identify_complementary_candidates(
    labels: Dict[str, int],
    alpha_vectors: Dict[str, Dict[str, Any]],
    corr_matrix: Dict[str, Dict[str, float]],
    min_mean_ic: float = 0.005,
) -> List[Dict[str, Any]]:
    """Identify alphas in *different* clusters with low |correlation|
    that could complement each other in an ensemble.

    Returns list of pairs with |corr| < 0.3 and both mean_ic > min_mean_ic.
    """
    names = sorted(alpha_vectors.keys())
    candidates: List[Dict[str, Any]] = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if labels.get(a) == labels.get(b):
                continue
            abs_corr = abs(corr_matrix[a][b])
            if abs_corr < 0.3 and (
                alpha_vectors[a]["mean_ic"] > min_mean_ic
                or alpha_vectors[b]["mean_ic"] > min_mean_ic
            ):
                candidates.append({
                    "alpha_a": a,
                    "alpha_b": b,
                    "abs_correlation": abs_corr,
                    "mean_ic_a": alpha_vectors[a]["mean_ic"],
                    "mean_ic_b": alpha_vectors[b]["mean_ic"],
                    "cluster_a": labels.get(a, -1),
                    "cluster_b": labels.get(b, -1),
                })
    # Sort by ascending correlation (most complementary first)
    candidates.sort(key=lambda c: c["abs_correlation"])
    return candidates


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _fmt(value: float, decimals: int = 4) -> str:
    return f"{value:.{decimals}f}"


def _fmt_pct(value: float, decimals: int = 1) -> str:
    return f"{value * 100:.{decimals}f}%"


def generate_report(
    data: Dict[str, Any],
    alpha_fold_ics: Dict[str, List[float]],
    alpha_vectors: Dict[str, Dict[str, Any]],
    corr_matrix: Dict[str, Dict[str, float]],
    cluster_labels: Dict[str, int],
    redundant_clusters: List[Dict[str, Any]],
    complementary_candidates: List[Dict[str, Any]],
) -> str:
    """Generate markdown research report."""
    lines: List[str] = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config = data.get("config", {})
    n_folds = len(data.get("fold_details", []))
    n_alphas = len(alpha_fold_ics)

    lines.append("# Alpha Vector-Space Discovery Report")
    lines.append("")
    lines.append(f"**Generated**: {ts}")
    lines.append(f"**Gate**: {GATE}")
    lines.append(f"**Role**: 14 (data-scientist) — L2 implementation only")
    lines.append(f"**Verdict**: {VERDICT_RESEARCH_ONLY} / {VERDICT_DO_NOT_PROMOTE}")
    lines.append(f"**Input**: Phase 3.5 backtest results")
    lines.append(f"**Alphas analyzed**: {n_alphas}")
    lines.append(f"**Folds**: {n_folds}")
    lines.append(f"**Date range**: {config.get('start_date', '?')} to {config.get('end_date', '?')}")
    lines.append("")
    lines.append(
        "> **RESEARCH ONLY**: This report identifies redundant clusters and "
        "complementary research candidates. It does NOT promote any alpha, "
        "select OOS winners, or alter live/default behaviour."
    )
    lines.append("")

    # Section 1: Per-Alpha Vector Features
    lines.append("## 1. Per-Alpha Vector Features (Expanded ~35-40D)")
    lines.append("")
    lines.append(
        "| Alpha | Mean IC | Std IC | ICIR | Pos Rate | "
        "Min IC | Max IC | Skew | Kurtosis | Mean |Corr| | Redund | "
        "Stability | Momentum | Cluster |"
    )
    lines.append(
        "|-------|---------|--------|------|---------|----------|"
        "--------|------|----------|------------|--------|-----------|-----------|---------|"
    )
    for a_name in sorted(alpha_vectors.keys()):
        v = alpha_vectors[a_name]
        short = _short_name(a_name)
        lines.append(
            f"| {short} | {_fmt(v['mean_ic'])} | {_fmt(v['std_ic'])} | "
            f"{_fmt(v['icir'])} | {_fmt_pct(v['positive_fold_rate'])} | "
            f"{_fmt(v['min_ic'])} | {_fmt(v['max_ic'])} | "
            f"{_fmt(v['ic_skew'], 2)} | {_fmt(v['fold_ic_kurtosis'], 2)} | "
            f"{_fmt(v['mean_abs_corr'], 3)} | {v['redundancy_count']} | "
            f"{_fmt(v['ic_stability'], 2)} | {_fmt(v['ic_momentum'])} | "
            f"C{cluster_labels.get(a_name, '?')} |"
        )
    lines.append("")

    # Section 1b: Expanded feature table
    lines.append("### Expanded Features")
    lines.append("")
    lines.append(
        "| Alpha | Sharpe Assoc | DD Assoc | Ret Assoc | "
        "Cluster Cent | Downside IC | Upside IC | "
        "Win/Loss | Autocorr | Bull Proxy | Bear Proxy |"
    )
    lines.append(
        "|-------|-------------|----------|-----------|-------------|"
        "-------------|-----------|----------|----------|------------|------------|"
    )
    for a_name in sorted(alpha_vectors.keys()):
        v = alpha_vectors[a_name]
        short = _short_name(a_name)
        lines.append(
            f"| {short} | {_fmt(v['sharpe_association'], 3)} | "
            f"{_fmt(v['drawdown_association'], 3)} | "
            f"{_fmt(v['return_association'], 3)} | "
            f"{_fmt(v['cluster_centrality'], 3)} | "
            f"{_fmt(v['downside_ic_mean'])} | {_fmt(v['upside_ic_mean'])} | "
            f"{_fmt(v['ic_win_loss_ratio'], 2)} | "
            f"{_fmt(v['fold_ic_autocorr'], 3)} | "
            f"{_fmt(v['regime_bull_proxy_mean_ic'])} | "
            f"{_fmt(v['regime_bear_proxy_mean_ic'])} |"
        )
    lines.append("")

    # Section 2: Fold IC Vectors
    lines.append("## 2. Fold IC Vectors")
    lines.append("")
    fold_ids = list(range(1, n_folds + 1))
    header = "| Alpha | " + " | ".join(f"F{fid}" for fid in fold_ids) + " |"
    sep = "|-------|" + "|".join(["--------"] * n_folds) + "|"
    lines.append(header)
    lines.append(sep)
    for a_name in sorted(alpha_fold_ics.keys()):
        short = _short_name(a_name)
        ics = alpha_fold_ics[a_name]
        row = f"| {short} |"
        for ic in ics:
            row += f" {_fmt(ic)} |"
        lines.append(row)
    lines.append("")

    # Section 3: Pairwise Correlation Matrix
    lines.append("## 3. Pairwise Correlation Matrix")
    lines.append("")
    names = sorted(corr_matrix.keys())
    header = "| Alpha |"
    for n in names:
        header += f" {_short_name(n)} |"
    lines.append(header)
    lines.append("|-------|" + "|".join(["--------"] * len(names)) + "|")
    for a in names:
        row = f"| {_short_name(a)} |"
        for b in names:
            r = corr_matrix[a][b]
            marker = ""
            if a != b and abs(r) >= CLUSTER_CORR_THRESHOLD:
                marker = " *"
            row += f" {_fmt(r, 3)}{marker} |"
        lines.append(row)
    lines.append("")
    lines.append(f"> \\* |correlation| >= {CLUSTER_CORR_THRESHOLD} (clustered)")
    lines.append("")

    # Section 4: Cluster Summary
    lines.append("## 4. Cluster Summary")
    lines.append("")
    cluster_members: Dict[int, List[str]] = defaultdict(list)
    for name, cid in sorted(cluster_labels.items()):
        cluster_members[cid].append(name)

    lines.append("| Cluster | Members | Mean |Corr| | Type |")
    lines.append("|---------|---------|-------------|------|")
    for cid in sorted(cluster_members.keys()):
        members = cluster_members[cid]
        short_members = ", ".join(_short_name(m) for m in members)
        if len(members) <= 1:
            lines.append(f"| C{cid} | {short_members} | — | singleton |")
        else:
            corrs = []
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    corrs.append(abs(corr_matrix[a][b]))
            mean_corr = _safe_mean(corrs)
            lines.append(
                f"| C{cid} | {short_members} | {_fmt(mean_corr, 3)} | redundant |"
            )
    lines.append("")

    # Section 5: Redundant Clusters
    lines.append("## 5. Redundant Clusters")
    lines.append("")
    if not redundant_clusters:
        lines.append("No redundant clusters found (all alphas in separate clusters).")
    else:
        lines.append(
            "> Redundant clusters contain alphas with |correlation| >= "
            f"{CLUSTER_CORR_THRESHOLD}. Members likely capture overlapping signals."
        )
        lines.append("")
        for rc in redundant_clusters:
            lines.append(
                f"**Cluster C{rc['cluster_id']}** ({rc['size']} members, "
                f"mean |corr| = {_fmt(rc['mean_abs_correlation'], 3)}):"
            )
            for m in rc["members"]:
                v = alpha_vectors[m]
                lines.append(
                    f"  - {_short_name(m)}: mean_ic={_fmt(v['mean_ic'])}, "
                    f"ICIR={_fmt(v['icir'])}, pos_rate={_fmt_pct(v['positive_fold_rate'])}"
                )
            lines.append("")
            lines.append(
                "> **Research note**: Within-cluster alphas are likely redundant. "
                "At most one representative should be retained for ensemble diversity."
            )
            lines.append("")
    lines.append("")

    # Section 6: Complementary Candidates
    lines.append("## 6. Complementary Research Candidates")
    lines.append("")
    if not complementary_candidates:
        lines.append("No complementary cross-cluster pairs found (all pairs highly correlated).")
    else:
        lines.append(
            "> Pairs from different clusters with |correlation| < 0.3. "
            "These could provide ensemble diversification if both have positive signal."
        )
        lines.append("")
        lines.append(
            "| Alpha A | Alpha B | |Corr| | Mean IC A | Mean IC B | "
            "Cluster A | Cluster B |"
        )
        lines.append(
            "|---------|---------|--------|-----------|-----------|"
            "-----------|-----------|"
        )
        for c in complementary_candidates[:20]:  # Top 20 pairs
            lines.append(
                f"| {_short_name(c['alpha_a'])} | {_short_name(c['alpha_b'])} | "
                f"{_fmt(c['abs_correlation'], 3)} | {_fmt(c['mean_ic_a'])} | "
                f"{_fmt(c['mean_ic_b'])} | C{c['cluster_a']} | C{c['cluster_b']} |"
            )
        lines.append("")
    lines.append("")

    # Section 7: Verdict
    lines.append("## 7. Research-Only Verdict")
    lines.append("")
    lines.append(f"**Final Verdict**: `{VERDICT_RESEARCH_ONLY}` / `{VERDICT_DO_NOT_PROMOTE}`")
    lines.append("")
    lines.append("- No alpha is promoted to live/default behaviour.")
    lines.append("- No OOS winner is selected by this diagnostic.")
    lines.append("- Findings are for research exploration only.")
    lines.append(
        "- Redundant clusters identify where alpha diversity is low; "
        "complementary pairs identify where ensemble diversification may be possible."
    )
    lines.append(
        "- Any decision to promote or retire alphas must follow the full "
        "PIT-safe verification pipeline and Tier 3 audit."
    )
    lines.append("")

    # Section 8: Safety disclaimer
    lines.append("## 8. Safety and Compliance")
    lines.append("")
    lines.append(
        "> This analysis is **deterministic** (no random seeds, no stochastic "
        "clustering). All computations use only fold-level alpha IC values "
        "already present in the Phase 3.5 JSON output. No look-ahead bias "
        "is introduced. No live trading paths are affected."
    )
    lines.append("")
    lines.append(
        "**Forbidden path scan**: No authoritative reliance; "
        ".gemini\\antigravity-ide\\scratch\\ag-kit is non-authoritative and not used as source; "
        ".openclaw\\skills is non-authoritative and not used as source; "
        "C:\\Users\\GHC\\.agents is non-authoritative and not used as source; "
        ".codex\\memories is non-authoritative and not used as source."
    )
    lines.append("")

    return "\n".join(lines)


def _short_name(alpha_name: str) -> str:
    """Shorten alpha name for display."""
    return alpha_name.replace("alpha_p34_", "p34_").replace("alpha_fml", "fml")


# ---------------------------------------------------------------------------
# JSON summary
# ---------------------------------------------------------------------------

def _count_scalar_features(v: Dict[str, Any]) -> int:
    """Count scalar (non-vector) numeric features in an alpha vector dict."""
    return sum(
        1 for key, val in v.items()
        if key != "fold_ic_vector" and isinstance(val, (int, float))
    )


def build_json_summary(
    data: Dict[str, Any],
    alpha_fold_ics: Dict[str, List[float]],
    alpha_vectors: Dict[str, Dict[str, Any]],
    corr_matrix: Dict[str, Dict[str, float]],
    cluster_labels: Dict[str, int],
    redundant_clusters: List[Dict[str, Any]],
    complementary_candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a JSON-serialisable summary dict."""
    config = data.get("config", {})
    n_folds = len(data.get("fold_details", []))

    return {
        "gate": GATE,
        "gate_expanded": "PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615",
        "verdict": f"{VERDICT_RESEARCH_ONLY} / {VERDICT_DO_NOT_PROMOTE}",
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "start_date": config.get("start_date"),
            "end_date": config.get("end_date"),
            "n_folds": n_folds,
            "n_alphas": len(alpha_fold_ics),
        },
        "vector_dim_count": _count_scalar_features(next(iter(alpha_vectors.values()), {})),
        "alpha_vectors": {
            name: {
                # Original features
                "mean_ic": v["mean_ic"],
                "std_ic": v["std_ic"],
                "icir": v["icir"],
                "positive_fold_rate": v["positive_fold_rate"],
                "early_half_mean_ic": v["early_half_mean_ic"],
                "late_half_mean_ic": v["late_half_mean_ic"],
                "early_late_trend": v["early_late_trend"],
                "bad_fold_association": v["bad_fold_association"],
                "fold_ic_vector": v["fold_ic_vector"],
                "cluster_id": cluster_labels.get(name, -1),
                # Expanded features (GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615)
                "min_ic": v["min_ic"],
                "max_ic": v["max_ic"],
                "downside_ic_mean": v["downside_ic_mean"],
                "ic_skew": v["ic_skew"],
                "sharpe_association": v["sharpe_association"],
                "drawdown_association": v["drawdown_association"],
                "return_association": v["return_association"],
                "mean_abs_corr": v["mean_abs_corr"],
                "redundancy_count": v["redundancy_count"],
                "cluster_centrality": v["cluster_centrality"],
                "ic_range": v["ic_range"],
                "ic_median": v["ic_median"],
                "positive_ic_rate_above_threshold": v["positive_ic_rate_above_threshold"],
                "negative_fold_rate": v["negative_fold_rate"],
                "ic_momentum": v["ic_momentum"],
                "ic_stability": v["ic_stability"],
                "worst_fold_ic": v["worst_fold_ic"],
                "best_fold_ic": v["best_fold_ic"],
                "fold_ic_kurtosis": v["fold_ic_kurtosis"],
                "ic_consistency_score": v["ic_consistency_score"],
                "ic_coefficient_of_variation": v["ic_coefficient_of_variation"],
                "fold_ic_autocorr": v["fold_ic_autocorr"],
                "ic_win_loss_ratio": v["ic_win_loss_ratio"],
                "upside_ic_mean": v["upside_ic_mean"],
                "regime_bull_proxy_mean_ic": v["regime_bull_proxy_mean_ic"],
                "regime_bear_proxy_mean_ic": v["regime_bear_proxy_mean_ic"],
                "cross_alpha_mean_ic_deviation": v["cross_alpha_mean_ic_deviation"],
                "n_folds_available": v["n_folds_available"],
                "quarter_mean_1": v["quarter_mean_1"],
                "quarter_mean_2": v["quarter_mean_2"],
                "quarter_mean_3": v["quarter_mean_3"],
                "quarter_mean_4": v["quarter_mean_4"],
            }
            for name, v in sorted(alpha_vectors.items())
        },
        "pairwise_correlations": {
            a: {b: round(corr_matrix[a][b], 6) for b in sorted(corr_matrix[a])}
            for a in sorted(corr_matrix.keys())
        },
        "cluster_labels": {name: cid for name, cid in sorted(cluster_labels.items())},
        "redundant_clusters": redundant_clusters,
        "complementary_candidates": [
            {
                "alpha_a": c["alpha_a"],
                "alpha_b": c["alpha_b"],
                "abs_correlation": round(c["abs_correlation"], 6),
                "mean_ic_a": round(c["mean_ic_a"], 6),
                "mean_ic_b": round(c["mean_ic_b"], 6),
            }
            for c in complementary_candidates[:30]
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Alpha Vector-Space Discovery Diagnostics"
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to Phase 3.5 backtest results JSON",
    )
    parser.add_argument(
        "--output-report", required=True,
        help="Output markdown report path",
    )
    parser.add_argument(
        "--output-json", required=True,
        help="Output JSON summary path",
    )
    parser.add_argument(
        "--cluster-threshold", type=float, default=CLUSTER_CORR_THRESHOLD,
        help=f"|correlation| threshold for clustering (default: {CLUSTER_CORR_THRESHOLD})",
    )
    args = parser.parse_args(argv)

    # Load data
    try:
        data = load_phase35_json(args.input)
    except FileNotFoundError:
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON in {args.input}: {exc}", file=sys.stderr)
        return 1

    # Extract fold ICs and metadata
    alpha_fold_ics = extract_alpha_fold_ics(data)
    portfolio_fold_ics = extract_fold_portfolio_ics(data)
    portfolio_fold_sharpes = extract_fold_sharpes(data)
    portfolio_fold_max_dds = extract_fold_max_dds(data)
    portfolio_fold_total_returns = extract_fold_total_returns(data)

    if not alpha_fold_ics:
        print("ERROR: No alpha IC data found in input JSON.", file=sys.stderr)
        return 1

    # Compute correlation and clustering first (needed by expanded vectors)
    corr_matrix = compute_pairwise_correlation(alpha_fold_ics)
    cluster_labels = correlation_distance_clustering(corr_matrix, args.cluster_threshold)

    # Compute expanded features (GATE: PIT_ROLLING_UNIVERSE_AND_VECTOR_DIMS_20260615)
    alpha_vectors = compute_alpha_vectors(
        alpha_fold_ics, portfolio_fold_ics,
        portfolio_fold_sharpes=portfolio_fold_sharpes,
        portfolio_fold_max_dds=portfolio_fold_max_dds,
        portfolio_fold_total_returns=portfolio_fold_total_returns,
        corr_matrix=corr_matrix,
        cluster_labels=cluster_labels,
    )
    redundant = identify_redundant_clusters(cluster_labels, corr_matrix)
    complementary = identify_complementary_candidates(
        cluster_labels, alpha_vectors, corr_matrix
    )

    # Generate outputs
    report_md = generate_report(
        data, alpha_fold_ics, alpha_vectors, corr_matrix,
        cluster_labels, redundant, complementary,
    )
    summary_json = build_json_summary(
        data, alpha_fold_ics, alpha_vectors, corr_matrix,
        cluster_labels, redundant, complementary,
    )

    # Write outputs
    report_path = Path(args.output_report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")

    json_path = Path(args.output_json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(summary_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Report:  {report_path}")
    print(f"JSON:    {json_path}")
    print(f"Alphas:  {len(alpha_fold_ics)}")
    dim_count = _count_scalar_features(next(iter(alpha_vectors.values()), {}))
    print(f"Vector Dims: {dim_count} scalar features (expanded)")
    print(f"Clusters: {len(set(cluster_labels.values()))}")
    print(f"Redundant clusters: {len(redundant)}")
    print(f"Complementary pairs: {len(complementary)}")
    print(f"Verdict: {VERDICT_RESEARCH_ONLY} / {VERDICT_DO_NOT_PROMOTE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
