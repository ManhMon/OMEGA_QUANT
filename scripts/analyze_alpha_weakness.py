#!/usr/bin/env python3
"""
Alpha Weakness Diagnostics Script
==================================
Parses Phase 3.5 A/B guard JSON outputs and produces a comprehensive
markdown diagnostic report covering per-variant summary, fold-level
metrics, fallback frequency, guard post-fallback outcome analysis, alpha
stability, weak-alpha ranking, and recommended gates.

Usage:
    python scripts/analyze_alpha_weakness.py \
        --input-dir data/phase35_results/ab_guard_20260614_101727 \
        --output .ly_state/session/alpha_weakness_diagnostics_20260614.md

Role: 14 (data-scientist) L2 — implementation only, no self-approval.
Gate: ALPHA_WEAKNESS_DIAGNOSTICS_20260614
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Research alpha gate utilities (GATE: RESEARCH_ALPHA_GATES_20260614)
_repo_root = Path(__file__).resolve().parent.parent
_src_path = str(_repo_root / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from omega.quant.walk_forward.risk_adjusted_alpha_score import (
    compute_icir,
    compute_positive_fold_rate,
    bh_fdr_qvalues,
    compute_ic_pvalue,
    classify_research_gate_verdict,
    compute_fallback_as_failure_metrics,
    compute_alpha_recovery_diagnostics,
    filter_alphas_by_recovery_mode,
    compute_selector_ready_verdict,
    compute_dsr,
    compute_pbo_summary,
    compute_cpcv_ready_path_summary,
    compute_stat_validation_verdict,
    AlphaRecoveryReport,
    RESEARCH_VERDICT_PROMOTE_CANDIDATE,
    RESEARCH_VERDICT_ENSEMBLE_ONLY,
    RESEARCH_VERDICT_REVIEW,
    RESEARCH_VERDICT_RETIRE,
    RESEARCH_POOL_FULL,
    RESEARCH_POOL_RECOVERY_ONLY,
    RESEARCH_POOL_RECOVERABLE_ONLY,
    SELECTOR_VERDICT_DO_NOT_PROMOTE,
    SELECTOR_VERDICT_CONDITIONAL_PROMOTE,
    SELECTOR_VERDICT_INSUFFICIENT_EVIDENCE,
    STAT_VALIDATION_PASS,
    STAT_VALIDATION_FAIL,
    STAT_VALIDATION_INSUFFICIENT_DATA,
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def discover_variant_files(input_dir: str) -> Dict[str, str]:
    """Discover *_backtest_results_*.json files and map variant name -> path.

    Variant naming convention:
        baseline_...json  -> 'baseline'
        ra_guard_...json  -> 'ra_guard'
        ra_no_guard_...json -> 'ra_no_guard'
    """
    input_path = Path(input_dir)
    if not input_path.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    pattern = re.compile(
        r"^(baseline|ra_guard|ra_no_guard)_.*backtest_results_.*\.json$"
    )
    variants: Dict[str, str] = {}
    for f in sorted(input_path.iterdir()):
        m = pattern.match(f.name)
        if m:
            variants[m.group(1)] = str(f)
    if not variants:
        raise FileNotFoundError(
            f"No matching *_backtest_results_*.json files in {input_dir}"
        )
    return variants


def load_variant(path: str) -> Dict[str, Any]:
    """Load and return a single variant JSON."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Analysis helpers
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


VARIANT_LABELS = {
    "baseline": "Baseline (no RA, no guard)",
    "ra_guard": "RA + Portfolio Guard",
    "ra_no_guard": "RA + No Guard",
}


def analyze_variant(name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Compute all diagnostic metrics for a single variant."""
    folds: List[Dict[str, Any]] = data.get("fold_details", [])
    config: Dict[str, Any] = data.get("config", {})
    summary: Dict[str, Any] = data.get("summary", {})

    # -- Fold-level vectors --
    fold_ics = [f["portfolio_ic"] for f in folds]
    fold_sharpes = [f["portfolio_sharpe"] for f in folds]
    fold_dds = [f["portfolio_max_dd"] for f in folds]
    fold_returns = [f.get("portfolio_total_return", 0.0) for f in folds]
    fold_pnls = [f.get("portfolio_pnl_vnd", 0.0) for f in folds]

    # -- Positive fold rate --
    n_folds = len(folds)
    pos_ic_folds = sum(1 for v in fold_ics if v > 0)
    pos_sharpe_folds = sum(1 for v in fold_sharpes if v > 0)
    pos_return_folds = sum(1 for v in fold_returns if v > 0)

    # -- Fallback frequency --
    fallback_count = sum(
        1
        for f in folds
        if f.get("used_fallback_candidates")
        or f.get("gate_metadata", {}).get("used_fallback_candidates", False)
    )

    # -- Gate metadata --
    gate_pass_counts = [
        f.get("gate_passed_count", f.get("gate_metadata", {}).get("gate_passed_count", 0))
        for f in folds
    ]
    gate_totals = [
        f.get("gate_total", f.get("gate_metadata", {}).get("gate_total", 0))
        for f in folds
    ]

    # -- Alpha-level IC across folds --
    all_alpha_names: set = set()
    for f in folds:
        all_alpha_names.update(f.get("alpha_ics", {}).keys())
    all_alpha_names = sorted(all_alpha_names)

    alpha_fold_ics: Dict[str, List[float]] = defaultdict(list)
    alpha_positive_folds: Dict[str, int] = defaultdict(int)
    for f in folds:
        for a_name, a_ic in f.get("alpha_ics", {}).items():
            alpha_fold_ics[a_name].append(a_ic)
            if a_ic > 0:
                alpha_positive_folds[a_name] += 1

    alpha_stats: Dict[str, Dict[str, Any]] = {}
    for a_name in all_alpha_names:
        ics = alpha_fold_ics[a_name]
        alpha_stats[a_name] = {
            "mean_ic": _safe_mean(ics),
            "std_ic": _safe_std(ics),
            "min_ic": min(ics) if ics else 0.0,
            "max_ic": max(ics) if ics else 0.0,
            "positive_fold_count": alpha_positive_folds[a_name],
            "positive_fold_rate": (
                alpha_positive_folds[a_name] / n_folds if n_folds else 0.0
            ),
        }

    # -- Weak alpha ranking (sorted ascending by mean_ic — weakest first) --
    weak_ranking = sorted(alpha_stats.items(), key=lambda kv: kv[1]["mean_ic"])

    # -- Guard analysis (only relevant for ra_guard) --
    guard_analysis = _analyze_guard(folds)

    # -- Selection stability (across folds, how often each alpha was selected) --
    selection_freq: Dict[str, int] = defaultdict(int)
    rejection_freq: Dict[str, int] = defaultdict(int)
    for f in folds:
        ra_sel = _extract_selection(f)
        if ra_sel:
            for a in ra_sel.get("selected_alphas", []):
                selection_freq[a] += 1
            for a in ra_sel.get("rejected_alphas", []):
                rejection_freq[a] += 1

    # -- Research Alpha Gate metrics (GATE: RESEARCH_ALPHA_GATES_20260614) --
    # Variant-level ICIR
    variant_icir = compute_icir(fold_ics)

    # Per-alpha ICIR, p-values, and research gate data
    alpha_p_values: Dict[str, float] = {}
    alpha_icir: Dict[str, float] = {}
    for a_name, ics in alpha_fold_ics.items():
        alpha_icir[a_name] = compute_icir(ics)
        alpha_p_values[a_name] = compute_ic_pvalue(ics)

    # BH-FDR q-values across all alphas
    alpha_names_ordered = sorted(alpha_p_values.keys())
    p_vals_ordered = [alpha_p_values[a] for a in alpha_names_ordered]
    q_vals_ordered = bh_fdr_qvalues(p_vals_ordered)
    alpha_q_values: Dict[str, float] = dict(zip(alpha_names_ordered, q_vals_ordered))

    # Attach q-values and ICIR to alpha_stats
    for a_name in alpha_stats:
        alpha_stats[a_name]["icir"] = alpha_icir.get(a_name, 0.0)
        alpha_stats[a_name]["p_value"] = alpha_p_values.get(a_name, 1.0)
        alpha_stats[a_name]["q_value"] = alpha_q_values.get(a_name, 1.0)

    # Fallback-as-failure metrics
    fb_metrics = compute_fallback_as_failure_metrics(folds)

    return {
        "name": name,
        "label": VARIANT_LABELS.get(name, name),
        "config": config,
        "summary": summary,
        "n_folds": n_folds,
        "fold_ics": fold_ics,
        "fold_sharpes": fold_sharpes,
        "fold_dds": fold_dds,
        "fold_returns": fold_returns,
        "fold_pnls": fold_pnls,
        "avg_ic": _safe_mean(fold_ics),
        "avg_sharpe": _safe_mean(fold_sharpes),
        "avg_dd": _safe_mean(fold_dds),
        "avg_return": _safe_mean(fold_returns),
        "std_ic": _safe_std(fold_ics),
        "std_sharpe": _safe_std(fold_sharpes),
        "pos_ic_folds": pos_ic_folds,
        "pos_sharpe_folds": pos_sharpe_folds,
        "pos_return_folds": pos_return_folds,
        "positive_ic_rate": pos_ic_folds / n_folds if n_folds else 0.0,
        "positive_sharpe_rate": pos_sharpe_folds / n_folds if n_folds else 0.0,
        "fallback_count": fallback_count,
        "fallback_rate": fallback_count / n_folds if n_folds else 0.0,
        "gate_pass_counts": gate_pass_counts,
        "gate_totals": gate_totals,
        "alpha_stats": alpha_stats,
        "weak_ranking": weak_ranking,
        "guard_analysis": guard_analysis,
        "selection_freq": dict(selection_freq),
        "rejection_freq": dict(rejection_freq),
        "folds": folds,
        "variant_icir": variant_icir,
        "alpha_q_values": alpha_q_values,
        "alpha_icir": alpha_icir,
        "fallback_as_failure_metrics": fb_metrics,
    }


def _extract_selection(fold: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract risk_adjusted_alpha_selection from fold (multiple locations)."""
    # Direct key on fold
    if "risk_adjusted_alpha_selection" in fold:
        return fold["risk_adjusted_alpha_selection"]
    # Under gate_metadata
    gm = fold.get("gate_metadata", {})
    if gm.get("risk_adjusted_evidence"):
        return gm["risk_adjusted_evidence"]
    # Under portfolio_guard_evidence -> rejected_risk_adjusted_evidence
    pge = fold.get("portfolio_guard_evidence") or gm.get("portfolio_guard_evidence")
    if pge and isinstance(pge, dict):
        rrae = pge.get("rejected_risk_adjusted_evidence")
        if rrae:
            return rrae
    # Under gate_metadata -> portfolio_guard_evidence
    if gm.get("portfolio_guard_evidence"):
        pge2 = gm["portfolio_guard_evidence"]
        if isinstance(pge2, dict):
            rrae2 = pge2.get("rejected_risk_adjusted_evidence")
            if rrae2:
                return rrae2
    return None


def _analyze_guard(folds: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze portfolio guard behavior across folds."""
    guard_enabled_folds = 0
    guard_fallback_to_baseline = 0
    guard_accepted = 0
    guard_rejected = 0
    post_fallback_positive_count = 0
    guard_details: List[Dict[str, Any]] = []

    for fold in folds:
        pge = fold.get("portfolio_guard_evidence")
        if not pge:
            gm = fold.get("gate_metadata", {})
            pge = gm.get("portfolio_guard_evidence")
        if not pge or not isinstance(pge, dict):
            continue

        if not pge.get("portfolio_guard_enabled", False):
            continue

        guard_enabled_folds += 1
        status = pge.get("portfolio_guard_status", "UNKNOWN")

        if status == "FALLBACK_TO_BASELINE":
            guard_rejected += 1
            guard_fallback_to_baseline += 1
        elif status == "ACCEPTED":
            guard_accepted += 1
        else:
            guard_rejected += 1

        # The fold portfolio is the realized post-fallback portfolio. Guard
        # validation metrics are separate and are not treated as OOS outcomes.
        fold_sharpe = fold.get("portfolio_sharpe", 0.0)
        fold_ic = fold.get("portfolio_ic", 0.0)
        if status == "FALLBACK_TO_BASELINE" and fold_sharpe > 1.0 and fold_ic > 0:
            post_fallback_positive_count += 1

        guard_details.append(
            {
                "fold_id": fold.get("fold_id"),
                "status": status,
                "selected_basket_ic": pge.get("selected_basket_validation_ic"),
                "baseline_basket_ic": pge.get("baseline_basket_validation_ic"),
                "realized_portfolio_ic": fold_ic,
                "realized_portfolio_sharpe": fold_sharpe,
                "guard_reason": pge.get("guard_reason", ""),
                "selected_alphas": pge.get("selected_alphas", []),
            }
        )

    return {
        "guard_enabled_folds": guard_enabled_folds,
        "guard_accepted": guard_accepted,
        "guard_rejected": guard_rejected,
        "guard_fallback_to_baseline": guard_fallback_to_baseline,
        "guard_fallback_to_baseline_rate": (
            guard_fallback_to_baseline / guard_enabled_folds
            if guard_enabled_folds else 0.0
        ),
        "post_fallback_positive_count": post_fallback_positive_count,
        "guard_details": guard_details,
    }


def _compute_research_verdicts(
    variant: Dict[str, Any],
    *,
    bh_fdr_threshold: float = 0.05,
    min_icir_promote: float = 0.5,
    min_icir_ensemble: float = 0.3,
    min_pos_fold_rate_promote: float = 0.6,
    min_pos_fold_rate_ensemble: float = 0.4,
) -> Dict[str, str]:
    """Compute research gate verdicts for each alpha in a variant.

    GATE: RESEARCH_ALPHA_GATES_20260614

    Returns dict mapping alpha name -> verdict string.
    """
    verdicts: Dict[str, str] = {}
    fb_rate = variant.get("fallback_rate", 0.0)

    for a_name, stats in variant.get("alpha_stats", {}).items():
        verdict = classify_research_gate_verdict(
            mean_ic=stats["mean_ic"],
            icir=stats.get("icir", 0.0),
            positive_fold_rate=stats["positive_fold_rate"],
            q_value=stats.get("q_value", 1.0),
            fallback_rate=fb_rate,
            min_icir_promote=min_icir_promote,
            min_icir_ensemble=min_icir_ensemble,
            min_pos_fold_rate_promote=min_pos_fold_rate_promote,
            min_pos_fold_rate_ensemble=min_pos_fold_rate_ensemble,
            bh_fdr_threshold=bh_fdr_threshold,
        )
        verdicts[a_name] = verdict

    return verdicts


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _fmt(value: float, decimals: int = 4) -> str:
    """Format a float to a fixed number of decimal places."""
    return f"{value:.{decimals}f}"


def _fmt_pct(value: float, decimals: int = 1) -> str:
    return f"{value * 100:.{decimals}f}%"


def _fmt_vnd(value: float) -> str:
    if abs(value) >= 1e9:
        return f"{value / 1e9:.2f}B"
    if abs(value) >= 1e6:
        return f"{value / 1e6:.1f}M"
    return f"{value:,.0f}"


def generate_report(
    variants: Dict[str, Dict[str, Any]],
    *,
    enable_research_gates: bool = False,
    enable_recovery_diagnostics: bool = False,
    enable_recovery_pool_ab: bool = False,
    enable_selector_ready: bool = False,
    enable_stat_validation_gates: bool = False,
    max_pbo: float = 0.50,
    min_dsr: float = 0.0,
    bh_fdr_threshold: float = 0.05,
    min_icir_promote: float = 0.5,
    min_icir_ensemble: float = 0.3,
    min_pos_fold_rate_promote: float = 0.6,
    min_pos_fold_rate_ensemble: float = 0.4,
    regime_threshold_sharpe: float = 1.0,
    regime_threshold_ic: float = -0.01,
) -> str:
    """Generate the full markdown diagnostics report.

    Parameters
    ----------
    variants : dict
        Mapping of variant name to analysis result dict.
    enable_research_gates : bool
        If True, include research gate verdicts, ICIR, BH-FDR,
        and fallback-as-failure sections (GATE: RESEARCH_ALPHA_GATES_20260614).
        Default False for backward compatibility.
    enable_recovery_diagnostics : bool
        If True, include alpha recovery diagnostics sections:
        neutralized IC, regime-conditioned IC, IC decay, retirement summary
        (GATE: ALPHA_RECOVERY_DIAGNOSTICS_20260614).
        Default False for backward compatibility.
    enable_recovery_pool_ab : bool
        If True, include recovery-only pool A/B diagnostics:
        compare full pool vs recovery-only pool excluding CONFIRMED_RETIRE
        (GATE: RECOVERY_POOL_AB_DIAGNOSTICS_20260614).
        Default False for backward compatibility.
    enable_selector_ready : bool
        If True, include selector-ready report with recommendations and
        DO_NOT_PROMOTE blocker (GATE: RECOVERY_SELECTOR_OPT_IN_20260614).
        Default False for backward compatibility.
    bh_fdr_threshold : float
        BH-FDR significance threshold for q-values.
    min_icir_promote : float
        Minimum ICIR for PROMOTE_CANDIDATE verdict.
    min_icir_ensemble : float
        Minimum ICIR for ENSEMBLE_ONLY verdict.
    min_pos_fold_rate_promote : float
        Minimum positive fold rate for PROMOTE_CANDIDATE.
    min_pos_fold_rate_ensemble : float
        Minimum positive fold rate for ENSEMBLE_ONLY.
    regime_threshold_sharpe : float
        Sharpe threshold for bull-like regime classification.
    regime_threshold_ic : float
        IC threshold boundary for bear-like regime classification.
        Default -0.01 preserves backward-compatible behavior.
    """
    lines: List[str] = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("# Alpha Weakness Diagnostics Report")
    lines.append("")
    lines.append(f"**Generated**: {ts}")
    lines.append(f"**Gate**: ALPHA_WEAKNESS_DIAGNOSTICS_20260614")
    lines.append(f"**Role**: 14 (data-scientist) — L2 implementation only")
    lines.append(f"**Variants analyzed**: {len(variants)}")
    lines.append("")

    # -- Section 1: Per-variant summary --
    lines.append("## 1. Per-Variant Summary")
    lines.append("")
    lines.append("| Metric | " + " | ".join(
        VARIANT_LABELS.get(k, k) for k in sorted(variants.keys())
    ) + " |")
    lines.append("|--------|" + "|".join(
        ["--------"] * len(variants)
    ) + "|")

    metrics = [
        ("Avg Portfolio IC", "avg_ic", _fmt),
        ("IC Std", "std_ic", _fmt),
        ("Avg Portfolio Sharpe", "avg_sharpe", _fmt),
        ("Sharpe Std", "std_sharpe", _fmt),
        ("Avg Max Drawdown", "avg_dd", _fmt),
        ("Avg Total Return", "avg_return", lambda v: _fmt_pct(v)),
        ("Positive IC Rate", "positive_ic_rate", _fmt_pct),
        ("Positive Sharpe Rate", "positive_sharpe_rate", _fmt_pct),
        ("Fallback Frequency", "fallback_rate", _fmt_pct),
    ]
    for label, key, fmt_fn in metrics:
        row_vals = []
        for k in sorted(variants.keys()):
            row_vals.append(fmt_fn(variants[k][key]))
        lines.append(f"| {label} | " + " | ".join(row_vals) + " |")
    lines.append("")

    # -- Section 2: Fold-level detail --
    lines.append("## 2. Fold-Level IC / Sharpe / Max DD")
    lines.append("")
    for vname in sorted(variants.keys()):
        v = variants[vname]
        lines.append(f"### {v['label']}")
        lines.append("")
        lines.append(
            "| Fold | Train Period | Test Period | IC | Sharpe | Max DD | Return | PnL (VND) |"
        )
        lines.append("|------|-------------|------------|-----|--------|--------|--------|-----------|")
        for fold in v["folds"]:
            fid = fold.get("fold_id", "?")
            train_p = f"{fold.get('train_start', '?')} - {fold.get('train_end', '?')}"
            test_p = f"{fold.get('test_start', '?')} - {fold.get('test_end', '?')}"
            lines.append(
                f"| {fid} | {train_p} | {test_p} | "
                f"{_fmt(fold.get('portfolio_ic', 0))} | "
                f"{_fmt(fold.get('portfolio_sharpe', 0))} | "
                f"{_fmt(fold.get('portfolio_max_dd', 0))} | "
                f"{_fmt_pct(fold.get('portfolio_total_return', 0))} | "
                f"{_fmt_vnd(fold.get('portfolio_pnl_vnd', 0))} |"
            )
        lines.append("")

    # -- Section 3: Positive fold rate detail --
    lines.append("## 3. Positive Fold Rate")
    lines.append("")
    lines.append("| Variant | Positive IC Folds | Positive Sharpe Folds | Positive Return Folds |")
    lines.append("|---------|-------------------|----------------------|----------------------|")
    for vname in sorted(variants.keys()):
        v = variants[vname]
        lines.append(
            f"| {v['label']} | {v['pos_ic_folds']}/{v['n_folds']} "
            f"({_fmt_pct(v['positive_ic_rate'])}) | "
            f"{v['pos_sharpe_folds']}/{v['n_folds']} "
            f"({_fmt_pct(v['positive_sharpe_rate'])}) | "
            f"{v['pos_return_folds']}/{v['n_folds']} |"
        )
    lines.append("")

    # -- Section 4: Fallback frequency --
    lines.append("## 4. Fallback Candidate Frequency")
    lines.append("")
    lines.append("| Variant | Fallback Folds | Rate |")
    lines.append("|---------|---------------|------|")
    for vname in sorted(variants.keys()):
        v = variants[vname]
        lines.append(
            f"| {v['label']} | {v['fallback_count']}/{v['n_folds']} | "
            f"{_fmt_pct(v['fallback_rate'])} |"
        )
    lines.append("")
    lines.append(
        "> **Note**: A high fallback rate indicates the gate criteria "
        "(min IC threshold, composite score) were not met by the primary "
        "alpha selection, forcing the system to use fallback candidates."
    )
    lines.append("")

    # -- Section 5: Guard accepted / rejected / post-fallback outcomes --
    lines.append("## 5. Guard Accepted / Rejected / Post-Fallback Outcomes")
    lines.append("")
    for vname in sorted(variants.keys()):
        v = variants[vname]
        ga = v["guard_analysis"]
        lines.append(f"### {v['label']}")
        lines.append("")
        if ga["guard_enabled_folds"] == 0:
            lines.append("Portfolio guard **not enabled** for this variant.")
            lines.append("")
            continue

        lines.append(f"- **Guard enabled folds**: {ga['guard_enabled_folds']}/{v['n_folds']}")
        lines.append(f"- **Guard accepted (RA basket used)**: {ga['guard_accepted']}")
        lines.append(f"- **Guard rejected (fallback to baseline)**: {ga['guard_rejected']}")
        lines.append(f"- **Post-fallback positive realized portfolios** (guard rejected, "
                      f"realized portfolio Sharpe > 1.0 and IC > 0; not a guard correctness metric): "
                      f"{ga['post_fallback_positive_count']}")
        lines.append("")

        if ga["guard_details"]:
            lines.append("| Fold | Status | Selected RA Validation IC | Baseline Validation IC | Realized Portfolio IC | Realized Portfolio Sharpe | Reason |")
            lines.append("|------|--------|---------------------------|------------------------|-----------------------|---------------------------|--------|")
            for gd in ga["guard_details"]:
                sel_ic = _fmt(gd["selected_basket_ic"]) if gd["selected_basket_ic"] is not None else "N/A"
                base_ic = _fmt(gd["baseline_basket_ic"]) if gd["baseline_basket_ic"] is not None else "N/A"
                realized_ic = _fmt(gd["realized_portfolio_ic"])
                realized_sharpe = _fmt(gd["realized_portfolio_sharpe"])
                reason = gd["guard_reason"][:80] if gd["guard_reason"] else ""
                lines.append(
                    f"| {gd['fold_id']} | {gd['status']} | {sel_ic} | {base_ic} | "
                    f"{realized_ic} | {realized_sharpe} | {reason} |"
                )
            lines.append("")

    # -- Section 6: Selected / Rejected alpha stability --
    lines.append("## 6. Alpha Selection Stability Across Folds")
    lines.append("")
    for vname in sorted(variants.keys()):
        v = variants[vname]
        if not v["selection_freq"] and not v["rejection_freq"]:
            lines.append(f"### {v['label']}")
            lines.append("")
            lines.append("No risk-adjusted selection data available for this variant.")
            lines.append("")
            continue

        lines.append(f"### {v['label']}")
        lines.append("")
        all_alphas = sorted(
            set(list(v["selection_freq"].keys()) + list(v["rejection_freq"].keys()))
        )
        lines.append("| Alpha | Selected Folds | Rejected Folds | Stability |")
        lines.append("|-------|---------------|---------------|-----------|")
        for a in all_alphas:
            sel = v["selection_freq"].get(a, 0)
            rej = v["rejection_freq"].get(a, 0)
            total = sel + rej
            stability = sel / total if total > 0 else 0.0
            short_name = a.replace("alpha_p34_", "")
            lines.append(
                f"| {short_name} | {sel} | {rej} | {_fmt_pct(stability)} |"
            )
        lines.append("")

    # -- Section 7: Weak alpha ranking --
    lines.append("## 7. Weak Alpha Ranking (by Mean OOS IC, weakest first)")
    lines.append("")
    for vname in sorted(variants.keys()):
        v = variants[vname]
        lines.append(f"### {v['label']}")
        lines.append("")
        lines.append(
            "| Rank | Alpha | Mean IC | Std IC | Min IC | Max IC | "
            "Positive Fold Rate | Assessment |"
        )
        lines.append(
            "|------|-------|---------|--------|--------|--------|"
            "-------------------|------------|"
        )
        for rank, (a_name, stats) in enumerate(v["weak_ranking"], 1):
            short_name = a_name.replace("alpha_p34_", "")
            mean_ic = stats["mean_ic"]
            if mean_ic < -0.02:
                assessment = "WEAK - consider removing"
            elif mean_ic < 0.0:
                assessment = "MARGINAL - negative mean"
            elif mean_ic < 0.02:
                assessment = "BELOW GATE (< 0.02)"
            else:
                assessment = "PASSES IC gate"
            lines.append(
                f"| {rank} | {short_name} | {_fmt(mean_ic)} | "
                f"{_fmt(stats['std_ic'])} | {_fmt(stats['min_ic'])} | "
                f"{_fmt(stats['max_ic'])} | "
                f"{_fmt_pct(stats['positive_fold_rate'])} | "
                f"{assessment} |"
            )
        lines.append("")

    # -- Section 8: Cross-variant comparison --
    lines.append("## 8. Cross-Variant Alpha IC Comparison")
    lines.append("")
    # Gather all alpha names across variants
    all_alphas: set = set()
    for v in variants.values():
        all_alphas.update(v["alpha_stats"].keys())
    all_alphas = sorted(all_alphas)

    header = "| Alpha |"
    sep = "|-------|"
    for vname in sorted(variants.keys()):
        header += f" {VARIANT_LABELS.get(vname, vname)} Mean IC |"
        sep += "--------|"
    lines.append(header)
    lines.append(sep)
    for a in all_alphas:
        short = a.replace("alpha_p34_", "")
        row = f"| {short} |"
        for vname in sorted(variants.keys()):
            stats = variants[vname]["alpha_stats"].get(a)
            if stats:
                row += f" {_fmt(stats['mean_ic'])} |"
            else:
                row += " N/A |"
        lines.append(row)
    lines.append("")

    # -- Section 9: Recommended gates --
    lines.append("## 9. Recommended Gates and Actions")
    lines.append("")

    # Compute recommended actions based on analysis
    lines.append("### 9.1 Alpha-Level Recommendations")
    lines.append("")
    lines.append("| Alpha | Recommendation | Rationale |")
    lines.append("|-------|---------------|-----------|")

    # Use baseline variant as primary for alpha-level decisions
    primary = variants.get("baseline", list(variants.values())[0])
    for a_name, stats in primary["weak_ranking"]:
        short = a_name.replace("alpha_p34_", "")
        mean_ic = stats["mean_ic"]
        pos_rate = stats["positive_fold_rate"]

        if mean_ic < -0.02:
            rec = "**RETIRE**"
            reason = (
                f"Mean IC={_fmt(mean_ic)} is strongly negative; "
                f"positive in only {_fmt_pct(pos_rate)} of folds"
            )
        elif mean_ic < 0.0:
            rec = "**REVIEW**"
            reason = (
                f"Mean IC={_fmt(mean_ic)} is negative; "
                f"positive in {_fmt_pct(pos_rate)} of folds. "
                f"Consider removing from ensemble or reducing weight."
            )
        elif mean_ic < 0.02:
            rec = "**MONITOR**"
            reason = (
                f"Mean IC={_fmt(mean_ic)} below 0.02 gate; "
                f"positive in {_fmt_pct(pos_rate)} of folds. "
                f"Keep in ensemble but do not promote to standalone."
            )
        else:
            rec = "**KEEP**"
            reason = (
                f"Mean IC={_fmt(mean_ic)} passes 0.02 gate; "
                f"positive in {_fmt_pct(pos_rate)} of folds."
            )
        lines.append(f"| {short} | {rec} | {reason} |")
    lines.append("")

    lines.append("### 9.2 Variant-Level Recommendations")
    lines.append("")
    for vname in sorted(variants.keys()):
        v = variants[vname]
        lines.append(f"**{v['label']}**:")
        lines.append("")

        # Fallback analysis
        if v["fallback_rate"] > 0.5:
            lines.append(
                f"- **HIGH FALLBACK RATE** ({_fmt_pct(v['fallback_rate'])}): "
                f"Gate criteria too strict for current alpha quality. "
                f"Consider relaxing `min_ic_threshold` or `min_composite_score`."
            )
        # Guard analysis
        ga = v["guard_analysis"]
        if ga["guard_enabled_folds"] > 0:
            reject_rate = ga["guard_fallback_to_baseline_rate"]
            if reject_rate > 0.5:
                lines.append(
                    f"- **GUARD FALLBACK-TO-BASELINE RATE HIGH** ({_fmt_pct(reject_rate)}): "
                    f"Portfolio guard is aggressively falling back to baseline. "
                    f"Review guard tolerance ({v['config'].get('portfolio_guard_tolerance', 'N/A')})."
                )
            if ga["post_fallback_positive_count"] > 0:
                lines.append(
                    f"- **POST-FALLBACK POSITIVE REALIZED PORTFOLIOS**: {ga['post_fallback_positive_count']} "
                    f"fold(s) where the realized post-fallback portfolio had Sharpe > 1.0 "
                    f"and IC > 0. This is not a guard correctness metric."
                )

        # IC quality
        if v["positive_ic_rate"] < 0.5:
            lines.append(
                f"- **LOW POSITIVE IC RATE** ({_fmt_pct(v['positive_ic_rate'])}): "
                f"Majority of folds have negative portfolio IC."
            )

        # Sharpe quality
        if v["avg_sharpe"] < 0.5:
            lines.append(
                f"- **BELOW SHARPE GATE**: Avg Sharpe={_fmt(v['avg_sharpe'])} "
                f"is below 0.5 minimum."
            )

        lines.append("")

    lines.append("### 9.3 System-Level Recommendations")
    lines.append("")
    alpha_count = len(primary["alpha_stats"])
    below_gate_count = sum(1 for stats in primary["alpha_stats"].values() if stats["mean_ic"] < 0.02)
    best_alpha, best_stats = max(
        primary["alpha_stats"].items(), key=lambda item: item[1]["mean_ic"], default=(None, {})
    )
    weakest_alpha, weakest_stats = min(
        primary["alpha_stats"].items(), key=lambda item: item[1]["mean_ic"], default=(None, {})
    )
    lines.append(
        f"1. **{below_gate_count}/{alpha_count} alphas have mean OOS IC below 0.02** "
        "in the primary variant. The alpha pool lacks sufficient predictive power "
        "for standalone deployment."
    )
    if best_alpha:
        lines.append(
            f"2. **`{best_alpha.replace('alpha_p34_', '')}` is the strongest primary alpha** "
            f"(mean IC {_fmt(best_stats['mean_ic'])}). Retain as a research candidate."
        )
    if weakest_alpha:
        lines.append(
            f"3. **`{weakest_alpha.replace('alpha_p34_', '')}` is the weakest primary alpha** "
            f"(mean IC {_fmt(weakest_stats['mean_ic'])}). Review for retirement."
        )

    # Computed fallback rates per variant
    fallback_parts: List[str] = []
    for vname in sorted(variants.keys()):
        v = variants[vname]
        fallback_parts.append(
            f"{VARIANT_LABELS.get(vname, vname)} {v['fallback_count']}/{v['n_folds']} "
            f"({_fmt_pct(v['fallback_rate'])})"
        )
    lines.append(
        f"4. **Fallback rates**: {', '.join(fallback_parts)}. "
        f"High fallback rates indicate the gate criteria are frequently not met "
        f"by primary candidates. Consider lowering `min_ic_threshold` to 0.01 "
        f"or accept that the current alpha pool requires ensemble-only usage."
    )

    # Computed guard fallback-to-baseline rate
    guard_variants = [
        (vname, v) for vname, v in variants.items()
        if v["guard_analysis"]["guard_enabled_folds"] > 0
    ]
    if guard_variants:
        for vname, v in guard_variants:
            ga = v["guard_analysis"]
            enabled = ga["guard_enabled_folds"]
            fb_baseline = ga["guard_fallback_to_baseline"]
            lines.append(
                f"5. **Portfolio guard** ({VARIANT_LABELS.get(vname, vname)}): "
                f"{fb_baseline}/{enabled} ({_fmt_pct(ga['guard_fallback_to_baseline_rate'])}) folds fell back to baseline. "
                f"Guard tolerance is {v['config'].get('portfolio_guard_tolerance', 'N/A')}. "
                f"Consider increasing tolerance to 0.01 or disabling guard for this alpha generation."
            )
    else:
        lines.append("5. **Portfolio guard**: Not enabled in any analyzed variant.")

    lines.append("6. **No production model behavior changes** are recommended at this time. "
                  "The diagnostics are for research evaluation only.")
    lines.append("")

    # -- Section 10: Research Alpha Gates (GATE: RESEARCH_ALPHA_GATES_20260614) --
    if enable_research_gates:
        lines.append("## 10. Research Alpha Gates (Opt-In)")
        lines.append("")
        lines.append(f"**Gate**: RESEARCH_ALPHA_GATES_20260614")
        lines.append(f"**BH-FDR threshold**: {bh_fdr_threshold}")
        lines.append(f"**Min ICIR (promote)**: {min_icir_promote}")
        lines.append(f"**Min ICIR (ensemble)**: {min_icir_ensemble}")
        lines.append(f"**Min positive fold rate (promote)**: {min_pos_fold_rate_promote}")
        lines.append(f"**Min positive fold rate (ensemble)**: {min_pos_fold_rate_ensemble}")
        lines.append("")

        # 10.1 Variant-level ICIR
        lines.append("### 10.1 Variant-Level ICIR")
        lines.append("")
        lines.append("| Variant | ICIR | Assessment |")
        lines.append("|---------|------|------------|")
        for vname in sorted(variants.keys()):
            v = variants[vname]
            icir_val = v.get("variant_icir", 0.0)
            if icir_val >= min_icir_promote:
                assessment = "STRONG"
            elif icir_val >= min_icir_ensemble:
                assessment = "MARGINAL"
            else:
                assessment = "WEAK"
            lines.append(
                f"| {v['label']} | {_fmt(icir_val)} | {assessment} |"
            )
        lines.append("")

        # 10.2 Per-alpha research gate verdicts
        lines.append("### 10.2 Per-Alpha Research Gate Verdicts")
        lines.append("")
        for vname in sorted(variants.keys()):
            v = variants[vname]
            verdicts = _compute_research_verdicts(
                v,
                bh_fdr_threshold=bh_fdr_threshold,
                min_icir_promote=min_icir_promote,
                min_icir_ensemble=min_icir_ensemble,
                min_pos_fold_rate_promote=min_pos_fold_rate_promote,
                min_pos_fold_rate_ensemble=min_pos_fold_rate_ensemble,
            )
            lines.append(f"**{v['label']}**:")
            lines.append("")
            lines.append(
                "| Alpha | Mean IC | ICIR | Pos Fold Rate | p-value | "
                "q-value (BH-FDR) | Verdict |"
            )
            lines.append(
                "|-------|---------|------|--------------|---------|"
                "-----------------|---------|"
            )
            for a_name in sorted(v["alpha_stats"].keys()):
                stats = v["alpha_stats"][a_name]
                short = a_name.replace("alpha_p34_", "")
                verdict = verdicts.get(a_name, RESEARCH_VERDICT_REVIEW)
                lines.append(
                    f"| {short} | {_fmt(stats['mean_ic'])} | "
                    f"{_fmt(stats.get('icir', 0.0))} | "
                    f"{_fmt_pct(stats['positive_fold_rate'])} | "
                    f"{_fmt(stats.get('p_value', 1.0))} | "
                    f"{_fmt(stats.get('q_value', 1.0))} | "
                    f"**{verdict}** |"
                )
            lines.append("")

        # 10.3 Verdict summary
        lines.append("### 10.3 Verdict Summary")
        lines.append("")
        primary = variants.get("baseline", list(variants.values())[0])
        verdicts = _compute_research_verdicts(
            primary,
            bh_fdr_threshold=bh_fdr_threshold,
            min_icir_promote=min_icir_promote,
            min_icir_ensemble=min_icir_ensemble,
            min_pos_fold_rate_promote=min_pos_fold_rate_promote,
            min_pos_fold_rate_ensemble=min_pos_fold_rate_ensemble,
        )
        verdict_counts: Dict[str, int] = defaultdict(int)
        for verdict in verdicts.values():
            verdict_counts[verdict] += 1
        lines.append("| Verdict | Count | Alphas |")
        lines.append("|---------|-------|--------|")
        for verdict_name in [
            RESEARCH_VERDICT_PROMOTE_CANDIDATE,
            RESEARCH_VERDICT_ENSEMBLE_ONLY,
            RESEARCH_VERDICT_REVIEW,
            RESEARCH_VERDICT_RETIRE,
        ]:
            alphas_in_verdict = [
                a.replace("alpha_p34_", "")
                for a, v in verdicts.items()
                if v == verdict_name
            ]
            lines.append(
                f"| {verdict_name} | {verdict_counts.get(verdict_name, 0)} | "
                f"{', '.join(alphas_in_verdict) if alphas_in_verdict else '—'} |"
            )
        lines.append("")

        # 10.4 Fallback-as-failure diagnostics
        lines.append("### 10.4 Fallback-as-Failure Diagnostics")
        lines.append("")
        lines.append(
            "> Fallback usage does NOT count as alpha success. "
            "Folds using fallback candidates are reported separately."
        )
        lines.append("")
        lines.append(
            "| Variant | Total Folds | Alpha-Selected Folds | "
            "Fallback Folds | Alpha-Selected Pos IC Rate | "
            "Fallback Pos IC Rate | Fallback-as-Failure Rate |"
        )
        lines.append(
            "|---------|------------|---------------------|"
            "---------------|-------------------------|"
            "---------------------|----------------------|"
        )
        for vname in sorted(variants.keys()):
            v = variants[vname]
            fb = v.get("fallback_as_failure_metrics", {})
            lines.append(
                f"| {v['label']} | {fb.get('total_folds', 0)} | "
                f"{fb.get('alpha_selected_folds', 0)} | "
                f"{fb.get('fallback_folds', 0)} | "
                f"{_fmt_pct(fb.get('alpha_selected_positive_ic_rate', 0.0))} | "
                f"{_fmt_pct(fb.get('fallback_positive_ic_rate', 0.0))} | "
                f"{_fmt_pct(fb.get('fallback_as_failure_rate', 0.0))} |"
            )
        lines.append("")

    # -- Section 11: Alpha Recovery Diagnostics (GATE: ALPHA_RECOVERY_DIAGNOSTICS_20260614) --
    if enable_recovery_diagnostics:
        next_section = 11
        lines.append(f"## {next_section}. Alpha Recovery Diagnostics (Opt-In)")
        lines.append("")
        lines.append(f"**Gate**: ALPHA_RECOVERY_DIAGNOSTICS_20260614")
        lines.append(
            "> These diagnostics are for alphas classified as RETIRE by research gates. "
            "They identify potential recovery candidates through neutralized IC, "
            "regime-conditioned analysis, and IC trend assessment."
        )
        lines.append("")

        for vname in sorted(variants.keys()):
            v = variants[vname]
            lines.append(f"### {v['label']}")
            lines.append("")

            # Compute research verdicts if available
            research_verdicts: Dict[str, str] = {}
            if enable_research_gates:
                research_verdicts = _compute_research_verdicts(
                    v,
                    bh_fdr_threshold=bh_fdr_threshold,
                    min_icir_promote=min_icir_promote,
                    min_icir_ensemble=min_icir_ensemble,
                    min_pos_fold_rate_promote=min_pos_fold_rate_promote,
                    min_pos_fold_rate_ensemble=min_pos_fold_rate_ensemble,
                )

            # Build alpha_fold_ics from variant folds
            alpha_fold_ics: Dict[str, List[float]] = defaultdict(list)
            for fold in v.get("folds", []):
                for a_name, a_ic in fold.get("alpha_ics", {}).items():
                    alpha_fold_ics[a_name].append(a_ic)

            # Compute recovery diagnostics
            recovery_report = compute_alpha_recovery_diagnostics(
                v.get("folds", []),
                dict(alpha_fold_ics),
                research_verdicts=research_verdicts if research_verdicts else None,
                regime_threshold_sharpe=regime_threshold_sharpe,
                regime_threshold_ic=regime_threshold_ic,
            )

            # 11.1 Neutralized IC Proxy
            lines.append(
                f"#### {next_section}.1 Neutralized IC Proxy (by Cluster)"
            )
            lines.append("")
            lines.append(
                "> Neutralized IC approximates alpha-specific signal after "
                "removing common cluster-level factor exposure."
            )
            lines.append("")
            lines.append(
                "| Alpha | Cluster | Mean IC | Cluster Mean IC | "
                "Neutralized IC | Cluster Members |"
            )
            lines.append(
                "|-------|---------|---------|-----------------|"
                "----------------|-----------------|"
            )
            for a_name in sorted(recovery_report.neutralized_ic.keys()):
                neut = recovery_report.neutralized_ic[a_name]
                short = a_name.replace("alpha_p34_", "")
                lines.append(
                    f"| {short} | {neut['cluster']} | "
                    f"{_fmt(neut['mean_ic'])} | "
                    f"{_fmt(neut['cluster_mean_ic'])} | "
                    f"{_fmt(neut['neutralized_ic'])} | "
                    f"{neut['n_cluster_members']} |"
                )
            lines.append("")

            # 11.2 Regime-Conditioned IC
            lines.append(
                f"#### {next_section}.2 Regime-Conditioned IC"
            )
            lines.append("")
            lines.append(
                "> Regime classification uses fold-level Sharpe/IC as proxy. "
                "Bull: Sharpe>=1.0 and IC>0. Bear: Sharpe<0 or IC<-0.01. "
                "Sideways: other."
            )
            lines.append("")
            lines.append(
                "| Alpha | Bull IC (N folds) | Bear IC (N folds) | "
                "Sideways IC (N folds) | Positive Regimes | Regime Fragile |"
            )
            lines.append(
                "|-------|------------------|-------------------|"
                "----------------------|------------------|----------------|"
            )
            for a_name in sorted(recovery_report.regime_conditioned_ic.keys()):
                regime = recovery_report.regime_conditioned_ic[a_name]
                short = a_name.replace("alpha_p34_", "")
                fragile = "YES" if regime["regime_fragile"] else "no"
                lines.append(
                    f"| {short} | "
                    f"{_fmt(regime['bull_mean_ic'])} ({regime['bull_n_folds']}) | "
                    f"{_fmt(regime['bear_mean_ic'])} ({regime['bear_n_folds']}) | "
                    f"{_fmt(regime['sideways_mean_ic'])} ({regime['sideways_n_folds']}) | "
                    f"{regime['positive_regimes']}/3 | "
                    f"{fragile} |"
                )
            lines.append("")

            # 11.3 IC Decay Summary
            lines.append(f"#### {next_section}.3 IC Decay / Horizon Summary")
            lines.append("")
            lines.append(
                "> IC trend compares early-half fold IC vs late-half fold IC. "
                "Positive trend indicates improving signal over time."
            )
            lines.append("")
            lines.append(
                "| Alpha | Early-Half IC | Late-Half IC | "
                "IC Trend | Half-Life (folds) |"
            )
            lines.append(
                "|-------|--------------|--------------|"
                "----------|-------------------|"
            )
            for a_name in sorted(recovery_report.ic_decay.keys()):
                decay = recovery_report.ic_decay[a_name]
                short = a_name.replace("alpha_p34_", "")
                half_life = (
                    str(decay["half_life_folds"])
                    if decay["half_life_folds"] >= 0
                    else "N/A"
                )
                lines.append(
                    f"| {short} | {_fmt(decay['early_half_mean_ic'])} | "
                    f"{_fmt(decay['late_half_mean_ic'])} | "
                    f"{_fmt(decay['ic_trend'])} | "
                    f"{half_life} |"
                )
            lines.append("")

            # 11.4 Retirement / Control / Research-Only Summary
            lines.append(
                f"#### {next_section}.4 Retirement / Control / Research-Only Summary"
            )
            lines.append("")
            lines.append(
                "> Classification based on positive signal dimensions: "
                "neutralized IC, regime robustness, IC trend. "
                "RECOVERABLE: >=2 positive dimensions. "
                "RESEARCH_ONLY: 1 positive dimension. "
                "CONFIRMED_RETIRE: 0 positive dimensions."
            )
            lines.append("")
            lines.append(
                "| Alpha | Research Verdict | Recovery Class | "
                "Neutralized IC | Positive Regimes | IC Trend | "
                "Signal Dims | Reasons |"
            )
            lines.append(
                "|-------|-----------------|----------------|"
                "----------------|------------------|----------|"
                "-------------|---------|"
            )
            for a_name in sorted(recovery_report.retirement_summary.keys()):
                summary = recovery_report.retirement_summary[a_name]
                short = a_name.replace("alpha_p34_", "")
                reasons = "; ".join(summary["reasons"]) if summary["reasons"] else "none"
                lines.append(
                    f"| {short} | {summary['research_verdict']} | "
                    f"**{summary['recovery_classification']}** | "
                    f"{_fmt(summary['neutralized_ic'])} | "
                    f"{summary['positive_regimes']}/3 | "
                    f"{_fmt(summary['ic_trend'])} | "
                    f"{summary['positive_signal_dims']} | "
                    f"{reasons} |"
                )
            lines.append("")

            # Summary counts
            n_recoverable = len(recovery_report.recoverable_candidates)
            n_research = len(recovery_report.research_only)
            n_retire = len(recovery_report.confirmed_retire)
            total_alphas = n_recoverable + n_research + n_retire

            lines.append(f"**Summary**: {total_alphas} alphas analyzed")
            lines.append(f"- **RECOVERABLE**: {n_recoverable}")
            lines.append(f"- **RESEARCH_ONLY**: {n_research}")
            lines.append(f"- **CONFIRMED_RETIRE**: {n_retire}")
            lines.append("")

            if recovery_report.recoverable_candidates:
                lines.append(
                    "**Potential recovery candidates** (positive in >=2 dimensions):"
                )
                for a in recovery_report.recoverable_candidates:
                    lines.append(f"- {a.replace('alpha_p34_', '')}")
                lines.append("")

            lines.append(
                "> **Note**: Recovery diagnostics do NOT change default behavior. "
                "All classifications are research-only. No live trading paths affected."
            )
            lines.append("")

    # -- Section: Recovery Pool A/B Diagnostics (GATE: RECOVERY_POOL_AB_DIAGNOSTICS_20260614) --
    if enable_recovery_pool_ab:
        lines.append("## Recovery Pool A/B Diagnostics (Opt-In)")
        lines.append("")
        lines.append("**Gate**: RECOVERY_POOL_AB_DIAGNOSTICS_20260614")
        lines.append(
            "> Compares full alpha pool vs recovery-only pool "
            "(excluding CONFIRMED_RETIRE alphas). Uses existing OOS fold "
            "alpha IC evidence. PIT-safe: no look-ahead, only fold-level "
            "metrics already computed from OOS data."
        )
        lines.append("")
        lines.append(f"**Regime threshold Sharpe**: {regime_threshold_sharpe}")
        lines.append(f"**Regime threshold IC**: {regime_threshold_ic}")
        lines.append("")

        for vname in sorted(variants.keys()):
            v = variants[vname]
            lines.append(f"### {v['label']}")
            lines.append("")

            # Compute research verdicts for this variant
            research_verdicts: Dict[str, str] = {}
            if enable_research_gates:
                research_verdicts = _compute_research_verdicts(
                    v,
                    bh_fdr_threshold=bh_fdr_threshold,
                    min_icir_promote=min_icir_promote,
                    min_icir_ensemble=min_icir_ensemble,
                    min_pos_fold_rate_promote=min_pos_fold_rate_promote,
                    min_pos_fold_rate_ensemble=min_pos_fold_rate_ensemble,
                )

            # Build alpha_fold_ics from variant folds
            alpha_fold_ics_map: Dict[str, List[float]] = defaultdict(list)
            for fold in v.get("folds", []):
                for a_name, a_ic in fold.get("alpha_ics", {}).items():
                    alpha_fold_ics_map[a_name].append(a_ic)

            # Compute recovery diagnostics for pool classification
            recovery_report = compute_alpha_recovery_diagnostics(
                v.get("folds", []),
                dict(alpha_fold_ics_map),
                research_verdicts=research_verdicts if research_verdicts else None,
                regime_threshold_sharpe=regime_threshold_sharpe,
                regime_threshold_ic=regime_threshold_ic,
            )

            # Pool definitions
            all_alphas = sorted(alpha_fold_ics_map.keys())
            confirmed_retire_set = set(recovery_report.confirmed_retire)
            recoverable_set = set(recovery_report.recoverable_candidates)
            research_only_set = set(recovery_report.research_only)
            recovery_pool = sorted(
                (recoverable_set | research_only_set) - confirmed_retire_set
            )

            lines.append("**Pool Definitions**:")
            lines.append("")
            lines.append(f"- **Full pool**: {len(all_alphas)} alphas")
            lines.append(
                f"- **Recovery-only pool**: {len(recovery_pool)} alphas "
                f"(RECOVERABLE + RESEARCH_ONLY, excluding CONFIRMED_RETIRE)"
            )
            lines.append(
                f"- **CONFIRMED_RETIRE excluded**: "
                f"{len(confirmed_retire_set)} alphas"
            )
            if recovery_pool:
                short_recovery = [
                    a.replace("alpha_p34_", "") for a in recovery_pool
                ]
                lines.append(
                    f"- **Recovery pool members**: {', '.join(short_recovery)}"
                )
            lines.append("")

            # Per-fold comparison: full pool vs recovery-only pool
            folds = v.get("folds", [])
            lines.append("#### Per-Fold Mean Alpha IC: Full Pool vs Recovery-Only Pool")
            lines.append("")
            lines.append(
                "| Fold | Full Pool Mean IC | Recovery Pool Mean IC | "
                "Delta | Full Pool N | Recovery Pool N |"
            )
            lines.append(
                "|------|-------------------|----------------------|"
                "-------|-------------|-----------------|"
            )

            full_pool_ics: List[float] = []
            recovery_pool_ics: List[float] = []
            for fold in folds:
                fold_id = fold.get("fold_id", "?")
                a_ics = fold.get("alpha_ics", {})

                # Full pool
                full_ics = [v for v in a_ics.values()]
                full_mean = _safe_mean(full_ics) if full_ics else 0.0
                full_n = len(full_ics)

                # Recovery pool
                rec_ics = [
                    v for k, v in a_ics.items() if k in recovery_pool
                ]
                rec_mean = _safe_mean(rec_ics) if rec_ics else 0.0
                rec_n = len(rec_ics)

                delta = rec_mean - full_mean
                full_pool_ics.append(full_mean)
                recovery_pool_ics.append(rec_mean)

                lines.append(
                    f"| {fold_id} | {_fmt(full_mean)} | {_fmt(rec_mean)} | "
                    f"{_fmt(delta)} | {full_n} | {rec_n} |"
                )
            lines.append("")

            # Summary statistics
            full_overall = _safe_mean(full_pool_ics)
            rec_overall = _safe_mean(recovery_pool_ics)
            full_pos_rate = (
                sum(1 for v in full_pool_ics if v > 0) / len(full_pool_ics)
                if full_pool_ics else 0.0
            )
            rec_pos_rate = (
                sum(1 for v in recovery_pool_ics if v > 0) / len(recovery_pool_ics)
                if recovery_pool_ics else 0.0
            )

            lines.append("#### Summary Statistics")
            lines.append("")
            lines.append("| Metric | Full Pool | Recovery-Only Pool |")
            lines.append("|--------|-----------|-------------------|")
            lines.append(
                f"| Mean Fold IC | {_fmt(full_overall)} | {_fmt(rec_overall)} |"
            )
            lines.append(
                f"| Positive Fold Rate | {_fmt_pct(full_pos_rate)} | "
                f"{_fmt_pct(rec_pos_rate)} |"
            )
            lines.append(
                f"| N Folds | {len(full_pool_ics)} | {len(recovery_pool_ics)} |"
            )
            lines.append("")

            # RECOVERABLE vs RESEARCH_ONLY breakdown
            if recoverable_set or research_only_set:
                lines.append("#### RECOVERABLE vs RESEARCH_ONLY Breakdown")
                lines.append("")
                lines.append(
                    "| Sub-Pool | Alphas | Mean IC |"
                )
                lines.append("|----------|--------|---------|")

                for label, pool_set in [
                    ("RECOVERABLE", recoverable_set),
                    ("RESEARCH_ONLY", research_only_set),
                ]:
                    pool_list = sorted(pool_set)
                    if not pool_list:
                        lines.append(f"| {label} | (none) | N/A |")
                        continue
                    pool_fold_ics: List[float] = []
                    for fold in folds:
                        a_ics = fold.get("alpha_ics", {})
                        ics = [
                            v for k, v in a_ics.items() if k in pool_set
                        ]
                        if ics:
                            pool_fold_ics.append(_safe_mean(ics))
                    pool_mean = _safe_mean(pool_fold_ics) if pool_fold_ics else 0.0
                    short_names = [
                        a.replace("alpha_p34_", "") for a in pool_list
                    ]
                    lines.append(
                        f"| {label} | {', '.join(short_names)} | "
                        f"{_fmt(pool_mean)} |"
                    )
                lines.append("")

            # Assessment
            if not recovery_pool:
                lines.append(
                    "> **Assessment**: No recovery pool candidates identified. "
                    "All alphas classified as CONFIRMED_RETIRE."
                )
            elif rec_overall > full_overall:
                lines.append(
                    f"> **Assessment**: Recovery-only pool "
                    f"(mean IC={_fmt(rec_overall)}) outperforms full pool "
                    f"(mean IC={_fmt(full_overall)}). "
                    f"Excluding {len(confirmed_retire_set)} CONFIRMED_RETIRE "
                    f"alphas improves average signal quality."
                )
            else:
                lines.append(
                    f"> **Assessment**: Recovery-only pool "
                    f"(mean IC={_fmt(rec_overall)}) does not outperform full pool "
                    f"(mean IC={_fmt(full_overall)}). "
                    f"The excluded CONFIRMED_RETIRE alphas do not materially "
                    f"degrade the full pool average."
                )
            lines.append("")

        lines.append(
            "> **Note**: Recovery pool A/B diagnostics do NOT change default "
            "behavior. All comparisons are research-only. No live trading "
            "paths affected. Fallback remains failure."
        )
        lines.append("")

    # -- Section: Selector-Ready Report (GATE: RECOVERY_SELECTOR_OPT_IN_20260614) --
    if enable_selector_ready:
        lines.append("## Selector-Ready Report (Opt-In)")
        lines.append("")
        lines.append("**Gate**: RECOVERY_SELECTOR_OPT_IN_20260614")
        lines.append(
            "> Evaluates whether the recovery-only pool A/B evidence "
            "supports promoting the opt-in recovery selector mode. "
            "A/B showed recovery-only pool improves mean IC but NOT "
            "positive fold rate — DO_NOT_PROMOTE blocker applies."
        )
        lines.append("")
        lines.append(f"**Regime threshold Sharpe**: {regime_threshold_sharpe}")
        lines.append(f"**Regime threshold IC**: {regime_threshold_ic}")
        lines.append("")

        for vname in sorted(variants.keys()):
            v = variants[vname]
            lines.append(f"### {v['label']}")
            lines.append("")

            # Compute recovery classifications
            alpha_fold_ics_map: Dict[str, List[float]] = defaultdict(list)
            for fold in v.get("folds", []):
                for a_name, a_ic in fold.get("alpha_ics", {}).items():
                    alpha_fold_ics_map[a_name].append(a_ic)

            research_verdicts: Dict[str, str] = {}
            if enable_research_gates:
                research_verdicts = _compute_research_verdicts(
                    v,
                    bh_fdr_threshold=bh_fdr_threshold,
                    min_icir_promote=min_icir_promote,
                    min_icir_ensemble=min_icir_ensemble,
                    min_pos_fold_rate_promote=min_pos_fold_rate_promote,
                    min_pos_fold_rate_ensemble=min_pos_fold_rate_ensemble,
                )

            recovery_report = compute_alpha_recovery_diagnostics(
                v.get("folds", []),
                dict(alpha_fold_ics_map),
                research_verdicts=research_verdicts if research_verdicts else None,
                regime_threshold_sharpe=regime_threshold_sharpe,
                regime_threshold_ic=regime_threshold_ic,
            )

            # Pool definitions
            all_alphas = sorted(alpha_fold_ics_map.keys())
            recovery_pool = filter_alphas_by_recovery_mode(
                all_alphas, recovery_report, RESEARCH_POOL_RECOVERY_ONLY
            )
            recoverable_pool = filter_alphas_by_recovery_mode(
                all_alphas, recovery_report, RESEARCH_POOL_RECOVERABLE_ONLY
            )

            # Compute per-fold pool metrics for verdict
            folds = v.get("folds", [])
            full_pool_fold_ics: List[float] = []
            recovery_pool_fold_ics: List[float] = []

            for fold in folds:
                a_ics = fold.get("alpha_ics", {})
                full_ics = list(a_ics.values())
                rec_ics = [val for k, val in a_ics.items() if k in recovery_pool]

                full_mean = _safe_mean(full_ics) if full_ics else 0.0
                rec_mean = _safe_mean(rec_ics) if rec_ics else 0.0
                full_pool_fold_ics.append(full_mean)
                recovery_pool_fold_ics.append(rec_mean)

            full_overall_ic = _safe_mean(full_pool_fold_ics)
            rec_overall_ic = _safe_mean(recovery_pool_fold_ics)
            full_pos_rate = (
                sum(1 for val in full_pool_fold_ics if val > 0) / len(full_pool_fold_ics)
                if full_pool_fold_ics else 0.0
            )
            rec_pos_rate = (
                sum(1 for val in recovery_pool_fold_ics if val > 0) / len(recovery_pool_fold_ics)
                if recovery_pool_fold_ics else 0.0
            )

            verdict = compute_selector_ready_verdict(
                full_overall_ic, full_pos_rate,
                rec_overall_ic, rec_pos_rate,
            )

            lines.append("#### Pool A/B Metrics")
            lines.append("")
            lines.append("| Metric | Full Pool | Recovery-Only Pool | Delta |")
            lines.append("|--------|-----------|-------------------|-------|")
            lines.append(
                f"| Mean Fold IC | {_fmt(full_overall_ic)} | "
                f"{_fmt(rec_overall_ic)} | "
                f"{_fmt(rec_overall_ic - full_overall_ic)} |"
            )
            lines.append(
                f"| Positive Fold Rate | {_fmt_pct(full_pos_rate)} | "
                f"{_fmt_pct(rec_pos_rate)} | "
                f"{_fmt_pct(rec_pos_rate - full_pos_rate)} |"
            )
            lines.append(
                f"| Pool Size | {len(all_alphas)} | "
                f"{len(recovery_pool)} | "
                f"{len(recovery_pool) - len(all_alphas)} |"
            )
            lines.append(
                f"| Recoverable-Only Size | — | "
                f"{len(recoverable_pool)} | — |"
            )
            lines.append("")

            lines.append(f"**Selector Verdict**: `{verdict}`")
            lines.append("")

            if verdict == SELECTOR_VERDICT_DO_NOT_PROMOTE:
                lines.append(
                    "> **DO_NOT_PROMOTE**: Recovery-only pool improves mean IC "
                    f"({_fmt(rec_overall_ic)} vs {_fmt(full_overall_ic)}) but "
                    f"positive fold rate did NOT improve "
                    f"({_fmt_pct(rec_pos_rate)} vs {_fmt_pct(full_pos_rate)}). "
                    "The improvement is insufficient for production promotion. "
                    "The opt-in recovery selector mode should remain research-only."
                )
            elif verdict == SELECTOR_VERDICT_CONDITIONAL_PROMOTE:
                lines.append(
                    "> **CONDITIONAL_PROMOTE**: Both mean IC and positive fold "
                    "rate improved with recovery-only pool. Further Tier-3 "
                    "audit required before production promotion."
                )
            else:
                lines.append(
                    "> **INSUFFICIENT_EVIDENCE**: No meaningful improvement "
                    "in either metric with recovery-only pool. "
                    "Default full-pool mode remains recommended."
                )
            lines.append("")

            # Recommendations
            lines.append("#### Recommendations")
            lines.append("")
            lines.append(f"1. **Default mode**: `{RESEARCH_POOL_FULL}` (unchanged).")
            if verdict == SELECTOR_VERDICT_DO_NOT_PROMOTE:
                lines.append(
                    f"2. **Opt-in `{RESEARCH_POOL_RECOVERY_ONLY}`**: Available "
                    "for research use. Excludes CONFIRMED_RETIRE alphas. "
                    "Mean IC improves but positive fold rate does not."
                )
                lines.append(
                    f"3. **Opt-in `{RESEARCH_POOL_RECOVERABLE_ONLY}`**: "
                    f"Available for research use ({len(recoverable_pool)} alphas). "
                    "Keeps only RECOVERABLE-classified alphas."
                )
                lines.append(
                    "4. **DO_NOT_PROMOTE to production**: Positive fold rate "
                    "must also improve before the recovery selector can be "
                    "promoted to default production behavior."
                )
            elif verdict == SELECTOR_VERDICT_CONDITIONAL_PROMOTE:
                lines.append(
                    f"2. **Opt-in `{RESEARCH_POOL_RECOVERY_ONLY}`**: Both "
                    "metrics improved. Submit to Tier-3 audit for conditional "
                    "promotion consideration."
                )
            else:
                lines.append(
                    "2. **No pool mode change recommended**: Full pool "
                    "remains the best option."
                )
            lines.append("")

        lines.append(
            "> **Note**: Selector-ready report does NOT change default "
            "behavior. All recommendations are research-only. "
            "No live trading paths affected. Fallback remains failure. "
            "Submit to Tier 3 audit before any production changes."
        )
        lines.append("")

    # -- Section: Statistical Validation Gates (GATE: STAT_VALIDATION_GATES_20260614) --
    if enable_stat_validation_gates:
        lines.append("## Statistical Validation Gates (Opt-In)")
        lines.append("")
        lines.append("**Gate**: STAT_VALIDATION_GATES_20260614")
        lines.append(
            "> Opt-in statistical validation gate diagnostics: "
            "Deflated Sharpe Ratio (DSR), Probability of Backtest "
            "Overfitting (PBO), CPCV-ready path summary. "
            "These diagnostics do NOT change default behavior. "
            "PIT-safe: only fold-level OOS metrics used."
        )
        lines.append("")
        lines.append(f"**Max PBO threshold**: {max_pbo}")
        lines.append(f"**Min DSR threshold**: {min_dsr}")
        lines.append("")

        for vname in sorted(variants.keys()):
            v = variants[vname]
            lines.append(f"### {v['label']}")
            lines.append("")

            folds = v.get("folds", [])

            # Build fold/path score matrix from alpha ICs
            fold_path_scores: List[Dict[str, float]] = []
            for fold in folds:
                a_ics = fold.get("alpha_ics", {})
                fold_path_scores.append(dict(a_ics))

            # Compute DSR from fold Sharpe series
            fold_sharpes = v.get("fold_sharpes", [])
            n_alphas = len(v.get("alpha_stats", {}))
            n_trials = max(n_alphas, len(fold_sharpes))
            dsr = compute_dsr(
                fold_sharpes,
                n_trials=n_trials,
            )

            # Compute PBO summary
            pbo_result = compute_pbo_summary(fold_path_scores)
            pbo = pbo_result["pbo"]

            # Compute CPCV-ready path summary
            cpcv_result = compute_cpcv_ready_path_summary(fold_path_scores)
            cpcv_ready = cpcv_result["cpcv_ready"]

            # Determine if weak alpha is blocked
            # Current alpha pool has mean IC below 0.02 gate
            primary_stats = v.get("alpha_stats", {})
            mean_ics = [s["mean_ic"] for s in primary_stats.values()]
            any_above_gate = any(ic >= 0.02 for ic in mean_ics)
            weak_alpha_blocked = not any_above_gate

            # Compute verdict
            verdict_result = compute_stat_validation_verdict(
                dsr, pbo, cpcv_ready,
                max_pbo=max_pbo,
                min_dsr=min_dsr,
                weak_alpha_blocked=weak_alpha_blocked,
            )

            lines.append("#### DSR (Deflated Sharpe Ratio)")
            lines.append("")
            lines.append(
                f"- **DSR**: {_fmt(dsr)} (probability Sharpe is NOT due to selection bias)"
            )
            lines.append(f"- **N folds**: {len(fold_sharpes)}")
            lines.append(f"- **N trials**: {n_trials}")
            lines.append(
                f"- **Min DSR threshold**: {min_dsr}"
            )
            dsr_pass = dsr >= min_dsr
            lines.append(
                f"- **DSR gate**: {'PASS' if dsr_pass else 'FAIL'}"
            )
            lines.append("")

            lines.append("#### PBO (Probability of Backtest Overfitting)")
            lines.append("")
            lines.append(
                f"- **PBO**: {_fmt(pbo)} (fraction of folds where per-fold-best "
                f"path has below-median cross-fold mean)"
            )
            lines.append(f"- **N paths**: {pbo_result['n_paths']}")
            lines.append(
                f"- **Overfit count**: {pbo_result['overfit_count']}"
            )
            lines.append(f"- **Max PBO threshold**: {max_pbo}")
            pbo_pass = pbo <= max_pbo
            lines.append(
                f"- **PBO gate**: {'PASS' if pbo_pass else 'FAIL'}"
            )
            lines.append("")

            lines.append("#### CPCV-Ready Path Summary")
            lines.append("")
            lines.append(
                f"- **CPCV-ready**: {'YES' if cpcv_ready else 'NO'} "
                f"({cpcv_result['n_folds']} folds, need >= {cpcv_result['min_folds_required']})"
            )
            lines.append(f"- **N paths**: {cpcv_result['n_paths']}")
            if cpcv_result["best_path"]:
                short_best = cpcv_result["best_path"].replace("alpha_p34_", "")
                lines.append(
                    f"- **Best path**: {short_best} "
                    f"(consistency: {_fmt_pct(cpcv_result['best_path_consistency'])})"
                )
            lines.append("")

            if cpcv_result["path_consistency"]:
                lines.append(
                    "| Path | Consistency (fraction positive folds) |"
                )
                lines.append("|------|--------------------------------------|")
                for path in sorted(cpcv_result["path_consistency"].keys()):
                    short = path.replace("alpha_p34_", "")
                    consistency = cpcv_result["path_consistency"][path]
                    lines.append(
                        f"| {short} | {_fmt_pct(consistency)} |"
                    )
                lines.append("")

            lines.append("#### Validation Verdict")
            lines.append("")
            verdict = verdict_result["verdict"]
            lines.append(f"**Verdict**: `{verdict}`")
            lines.append("")

            if verdict_result["blockers"]:
                lines.append("**Promotion Blockers**:")
                lines.append("")
                for blocker in verdict_result["blockers"]:
                    lines.append(f"- {blocker}")
                lines.append("")

            if verdict == STAT_VALIDATION_FAIL:
                lines.append(
                    "> **STAT_VALIDATION_FAIL**: Alpha pool does NOT pass "
                    "statistical validation gates. DO_NOT_PROMOTE to live. "
                    "Current weak alpha remains blocked."
                )
            elif verdict == STAT_VALIDATION_PASS:
                lines.append(
                    "> **STAT_VALIDATION_PASS**: Alpha pool passes "
                    "statistical validation gates. Submit to Tier-3 audit."
                )
            lines.append("")

        lines.append(
            "> **Note**: Statistical validation gate diagnostics do NOT "
            "change default behavior. All results are research-only. "
            "No live trading paths affected. "
            "Submit to Tier 3 audit before any production changes."
        )
        lines.append("")

    # -- Footer --
    lines.append("---")
    lines.append("")
    lines.append("*Report generated by `scripts/analyze_alpha_weakness.py` "
                  f"at {ts}. L2 implementation only — submit to Tier 3 audit.*")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Alpha Weakness Diagnostics — Phase 3.5 A/B Guard Analysis"
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing *_backtest_results_*.json files",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the markdown diagnostics report",
    )
    # Opt-in research gate flags (GATE: RESEARCH_ALPHA_GATES_20260614)
    parser.add_argument(
        "--research-gates",
        action="store_true",
        default=False,
        help="Enable research alpha gate verdicts (ICIR, BH-FDR, fallback-as-failure). "
             "Default: disabled for backward compatibility.",
    )
    parser.add_argument(
        "--bh-fdr-alpha",
        type=float,
        default=0.05,
        help="BH-FDR significance threshold for q-values (default: 0.05).",
    )
    parser.add_argument(
        "--min-icir-promote",
        type=float,
        default=0.5,
        help="Minimum ICIR for PROMOTE_CANDIDATE verdict (default: 0.5).",
    )
    parser.add_argument(
        "--min-icir-ensemble",
        type=float,
        default=0.3,
        help="Minimum ICIR for ENSEMBLE_ONLY verdict (default: 0.3).",
    )
    parser.add_argument(
        "--min-pos-fold-rate-promote",
        type=float,
        default=0.6,
        help="Minimum positive fold rate for PROMOTE_CANDIDATE (default: 0.6).",
    )
    parser.add_argument(
        "--min-pos-fold-rate-ensemble",
        type=float,
        default=0.4,
        help="Minimum positive fold rate for ENSEMBLE_ONLY (default: 0.4).",
    )
    # Opt-in recovery diagnostics flags (GATE: ALPHA_RECOVERY_DIAGNOSTICS_20260614)
    parser.add_argument(
        "--recovery-diagnostics",
        action="store_true",
        default=False,
        help="Enable alpha recovery diagnostics (neutralized IC, regime-conditioned IC, "
             "IC decay, retirement summary). Default: disabled for backward compatibility.",
    )
    parser.add_argument(
        "--regime-threshold-sharpe",
        type=float,
        default=1.0,
        help="Sharpe threshold for bull-like regime classification (default: 1.0).",
    )
    parser.add_argument(
        "--regime-threshold-ic",
        type=float,
        default=-0.01,
        help="IC threshold boundary for bear-like regime classification (default: -0.01).",
    )
    # Opt-in recovery pool A/B diagnostics (GATE: RECOVERY_POOL_AB_DIAGNOSTICS_20260614)
    parser.add_argument(
        "--recovery-pool-ab",
        action="store_true",
        default=False,
        help="Enable recovery-only pool A/B diagnostics: compare full pool vs "
             "recovery-only pool (excluding CONFIRMED_RETIRE). "
             "Default: disabled for backward compatibility.",
    )
    # Opt-in selector-ready report (GATE: RECOVERY_SELECTOR_OPT_IN_20260614)
    parser.add_argument(
        "--selector-ready",
        action="store_true",
        default=False,
        help="Enable selector-ready report with recommendations and "
             "DO_NOT_PROMOTE blocker. Default: disabled for backward compatibility.",
    )
    # Opt-in statistical validation gates (GATE: STAT_VALIDATION_GATES_20260614)
    parser.add_argument(
        "--stat-validation-gates",
        action="store_true",
        default=False,
        help="Enable statistical validation gate diagnostics (DSR, PBO, CPCV-ready). "
             "Default: disabled for backward compatibility.",
    )
    parser.add_argument(
        "--max-pbo",
        type=float,
        default=0.50,
        help="Maximum acceptable PBO threshold (default: 0.50).",
    )
    parser.add_argument(
        "--min-dsr",
        type=float,
        default=0.0,
        help="Minimum acceptable DSR threshold (default: 0.0).",
    )
    args = parser.parse_args()

    # Discover and load
    variant_files = discover_variant_files(args.input_dir)
    print(f"[INFO] Discovered {len(variant_files)} variant(s): {list(variant_files.keys())}")

    variants: Dict[str, Dict[str, Any]] = {}
    for vname, vpath in variant_files.items():
        print(f"[INFO] Loading {vname}: {vpath}")
        data = load_variant(vpath)
        variants[vname] = analyze_variant(vname, data)
        print(f"[INFO] Analyzed {vname}: {variants[vname]['n_folds']} folds")

    # Generate report
    report = generate_report(
        variants,
        enable_research_gates=args.research_gates,
        enable_recovery_diagnostics=args.recovery_diagnostics,
        enable_recovery_pool_ab=args.recovery_pool_ab,
        enable_selector_ready=args.selector_ready,
        enable_stat_validation_gates=args.stat_validation_gates,
        max_pbo=args.max_pbo,
        min_dsr=args.min_dsr,
        bh_fdr_threshold=args.bh_fdr_alpha,
        min_icir_promote=args.min_icir_promote,
        min_icir_ensemble=args.min_icir_ensemble,
        min_pos_fold_rate_promote=args.min_pos_fold_rate_promote,
        min_pos_fold_rate_ensemble=args.min_pos_fold_rate_ensemble,
        regime_threshold_sharpe=args.regime_threshold_sharpe,
        regime_threshold_ic=args.regime_threshold_ic,
    )

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"[INFO] Report written to {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
