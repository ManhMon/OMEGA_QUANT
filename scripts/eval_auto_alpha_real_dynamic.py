#!/usr/bin/env python3
"""Evaluate automated alpha discovery candidates on real VN market data.

GATE: AUTOMATED_ALPHA_DISCOVERY_REAL_DYNAMIC_EVAL_20260615

Uses Phase35DataLoader for PIT-safe real data, runs AutomatedAlphaDiscoveryFactory
on the train portion of the last walk-forward fold, and computes transfer diagnostics.
Research-only — no live promotion, no default behavior change.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from phase35_data_loader import Phase35DataLoader
from omega.quant.alpha.automated_alpha_discovery import (
    AutomatedAlphaDiscoveryFactory,
    AUTOMATED_DISCOVERY_GATE_ID,
)
from omega.quant.alpha.alpha_transfer_diagnostics import run_transfer_diagnostics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

GATE_ID = "AUTOMATED_ALPHA_DISCOVERY_REAL_DYNAMIC_EVAL_20260615"


def main():
    logger.info(f"GATE: {GATE_ID}")
    logger.info("Loading real VN market data via Phase35DataLoader...")

    loader = Phase35DataLoader()
    df = loader.load_and_prepare(
        start_date="2015-01-05",
        end_date="2026-05-14",
        top_n_symbols=30,
        forward_horizons=[1, 3, 5],
        enable_data_cleaning=True,
        normalization_mode="expanding_zscore",
    )

    logger.info(f"Real data loaded: {len(df):,} rows, {df['ticker'].nunique()} symbols")
    logger.info(f"Date range: {df['date'].min()} to {df['date'].max()}")

    # Create walk-forward splits (same config as baseline)
    splits = loader.create_walk_forward_splits(df, n_folds=12, train_years=3, test_years=1)
    logger.info(f"Created {len(splits)} walk-forward folds")

    # Use the last fold for train-set discovery (most recent data, closest to live)
    last_train_df, last_test_df = splits[-1]
    logger.info(
        f"Last fold: train={len(last_train_df)} rows, test={len(last_test_df)} rows"
    )

    # Run automated alpha discovery on the TRAIN portion only
    logger.info("=" * 80)
    logger.info("Running AutomatedAlphaDiscoveryFactory on real train data...")
    logger.info("=" * 80)

    factory = AutomatedAlphaDiscoveryFactory(
        enabled=True,
        candidate_cap=20,
        corr_threshold=0.85,
        min_ic=0.01,
        seed=42,
        return_col="fwd_ret_5",
    )

    result = factory.run_discovery(last_train_df)
    result_dict = result.to_dict()

    logger.info(f"Discovery complete:")
    logger.info(f"  Generated: {result_dict['candidates_generated']}")
    logger.info(f"  Screened (IC pass): {result_dict['candidates_after_screening']}")
    logger.info(f"  After corr filter: {result_dict['candidates_after_corr_filter']}")
    logger.info(f"  Selected: {result_dict['n_selected']}")

    # Focus on the top 5 candidates from the synthetic ranking
    target_candidates = [
        "auto_rsi_14",
        "auto_mom_ret_60",
        "auto_mr_zscore_20",
        "auto_vol_std_ratio_10_30",
        "auto_mom_ret_20",
    ]

    logger.info("")
    logger.info("=" * 80)
    logger.info("Top-5 target candidates from synthetic ranking:")
    logger.info("=" * 80)

    selected_ics = result_dict.get("selected_ics", {})

    # Compute ICIR from selected candidates
    selected_icirs = {}
    for c in result.selected_candidates:
        ic_vals = getattr(c, "train_ic_per_fold", None) or getattr(c, "icir", None)
        if hasattr(c, "train_ic") and hasattr(c, "train_ic_std"):
            if c.train_ic_std and c.train_ic_std > 0:
                selected_icirs[c.name] = round(c.train_ic / c.train_ic_std, 6)
        # Try to get ICIR from evidence
    evidence = result_dict.get("evidence", {})
    if "selected_icirs" in evidence:
        selected_icirs = evidence["selected_icirs"]

    real_data_eval = {}
    for name in target_candidates:
        ic_val = selected_ics.get(name)
        icir_val = selected_icirs.get(name)
        status = "FOUND" if name in selected_ics else "NOT_SELECTED"
        logger.info(f"  {name}: IC={ic_val}, ICIR={icir_val}, status={status}")
        real_data_eval[name] = {
            "real_train_ic": ic_val,
            "real_train_icir": icir_val,
            "status": status,
        }

    # Also show ALL selected candidates ranked by |IC|
    logger.info("")
    logger.info("=" * 80)
    logger.info("ALL selected candidates ranked by |IC| on REAL train data:")
    logger.info("=" * 80)
    sorted_candidates = sorted(
        selected_ics.items(), key=lambda x: abs(x[1]), reverse=True
    )
    for rank, (name, ic) in enumerate(sorted_candidates, 1):
        icir = selected_icirs.get(name, "N/A")
        logger.info(f"  #{rank}: {name} — IC={ic:.6f}, ICIR={icir}")

    # Run transfer diagnostics
    logger.info("")
    logger.info("=" * 80)
    logger.info("Running transfer diagnostics on real data...")
    logger.info("=" * 80)

    signals_df = factory.compute_candidate_signals(
        last_train_df, result.selected_candidates
    )
    candidate_signals = {}
    for c in result.selected_candidates:
        if c.name in signals_df.columns:
            candidate_signals[c.name] = signals_df[c.name]

    diag_report = None
    if candidate_signals:
        diag_report = run_transfer_diagnostics(
            candidates=candidate_signals,
            existing_signals=pd.DataFrame(),
            returns=last_train_df["fwd_ret_5"],
            dates=last_train_df["date"],
            tickers=last_train_df["ticker"],
            corr_threshold=0.85,
            min_marginal_ic=0.01,
        )
        logger.info(
            f"Transfer diagnostics: evaluated={diag_report.candidates_evaluated}, "
            f"recommended={diag_report.candidates_recommended}"
        )
        for d in diag_report.diagnostics:
            logger.info(f"  {d.alpha_name}: {d.transfer_verdict}")

    # Compare with dynamic baseline — derived from baseline JSON, NOT hardcoded
    logger.info("")
    logger.info("=" * 80)
    logger.info("COMPARISON WITH DYNAMIC BASELINE (data-derived)")
    logger.info("=" * 80)

    baseline_json_path = (
        _REPO_ROOT
        / "data"
        / "phase35_results"
        / "phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json"
    )
    with open(baseline_json_path, "r", encoding="utf-8") as bf:
        baseline_data = json.load(bf)

    summary = baseline_data["summary"]
    portfolio_ic = float(summary["avg_portfolio_ic"])
    portfolio_sharpe = float(summary["avg_portfolio_sharpe"])
    portfolio_max_dd = float(summary["avg_portfolio_max_dd"]) * 100  # to percent

    # Derive 4+ baseline comparison metrics with explicit formulas
    # (A) Top-level alpha_ics median (signed): median of 12 per-alpha average ICs
    top_level_ics = list(baseline_data["alpha_ics"].values())
    baseline_top_median = float(np.median(top_level_ics))

    # (B) Top-level |alpha_ics| median: median of |IC| for 12 alphas
    baseline_top_abs_median = float(np.median([abs(v) for v in top_level_ics]))

    # (C) Fold-level alpha_ics median (signed): median of 12 folds x 12 alphas = 144 values
    fold_ics = []
    for fold in baseline_data["fold_details"]:
        for ic_val in fold["alpha_ics"].values():
            fold_ics.append(ic_val)
    baseline_fold_median = float(np.median(fold_ics))

    # (D) Fold-level |alpha_ics| median: median of |IC| across 144 fold-alpha pairs
    baseline_fold_abs_median = float(np.median([abs(v) for v in fold_ics]))

    # PRIMARY COMPARATOR: (B) top-level |alpha_ics| median
    # Rationale: each baseline alpha has one averaged IC across 12 folds;
    # each auto candidate has one IC on the train set. Using |IC| removes
    # sign-convention differences (templates may produce +/- IC depending
    # on direction). This compares signal STRENGTH directly.
    baseline_primary = baseline_top_abs_median

    logger.info(f"  Baseline source: {baseline_json_path.name}")
    logger.info(f"  Baseline Portfolio IC:      {portfolio_ic:.6f}")
    logger.info(f"  Baseline Sharpe:            {portfolio_sharpe:.4f}")
    logger.info(f"  Baseline MaxDD:             {portfolio_max_dd:.2f}%")
    logger.info(f"  (A) Top-level median IC (signed, 12 alphas):  {baseline_top_median:.10f}")
    logger.info(f"  (B) Top-level median |IC| (12 alphas):         {baseline_top_abs_median:.10f}")
    logger.info(f"  (C) Fold-level median IC (signed, 144 vals):   {baseline_fold_median:.10f}")
    logger.info(f"  (D) Fold-level median |IC| (144 vals):          {baseline_fold_abs_median:.10f}")
    logger.info(f"  PRIMARY COMPARATOR = (B) top-level median |IC| = {baseline_primary:.10f}")
    logger.info("")

    # Compute comparison metrics for auto candidates
    real_ics = [v for v in selected_ics.values() if v is not None]
    mean_auto_ic = None
    median_auto_ic = None
    median_auto_abs_ic = None
    max_auto_ic = None
    n_positive = 0
    delta_abs = None
    delta_pct = None
    if real_ics:
        mean_auto_ic = float(np.mean(real_ics))
        median_auto_ic = float(np.median(real_ics))
        auto_abs_ics = [abs(v) for v in real_ics]
        median_auto_abs_ic = float(np.median(auto_abs_ics))
        max_auto_ic = float(max(real_ics, key=abs))
        n_positive = sum(1 for v in real_ics if v > 0)

        # Compare using the primary comparator (|IC| on both sides)
        delta_abs = median_auto_abs_ic - baseline_primary
        delta_pct = (delta_abs / baseline_primary) * 100 if baseline_primary != 0 else None

        logger.info(f"  Auto-discovery Mean IC (signed):   {mean_auto_ic:.6f}")
        logger.info(f"  Auto-discovery Median IC (signed): {median_auto_ic:.6f}")
        logger.info(f"  Auto-discovery Median |IC|:        {median_auto_abs_ic:.6f}")
        logger.info(f"  Auto-discovery Max |IC|:           {max_auto_ic:.6f}")
        logger.info(f"  Auto-discovery Positive IC rate:   {n_positive}/{len(real_ics)}")
        logger.info(f"  Delta vs primary comparator (|IC|): {delta_abs:+.6f} ({delta_pct:+.1f}%)")
        logger.info(
            f"  vs Baseline |median alpha IC|:     "
            f"{'EXCEEDS' if median_auto_abs_ic > baseline_primary else 'BELOW'}"
        )

    # Save results
    output_dir = _REPO_ROOT / ".ly_state" / "session"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output = {
        "gate": GATE_ID,
        "timestamp": timestamp,
        "data_source": "real_vn_market_parquet",
        "data_rows": len(df),
        "data_symbols": df["ticker"].nunique(),
        "data_date_range": f"{df['date'].min()} to {df['date'].max()}",
        "fold_used": "last_fold_train",
        "train_rows": len(last_train_df),
        "test_rows": len(last_test_df),
        "pit_safe": True,
        "train_only": True,
        "no_live_promotion": True,
        "discovery_result": result_dict,
        "target_candidates_real_eval": real_data_eval,
        "all_candidates_ranked": [
            {"rank": i + 1, "name": n, "ic": ic, "icir": selected_icirs.get(n, None)}
            for i, (n, ic) in enumerate(sorted_candidates)
        ],
        "baseline_comparison": {
            "baseline_source": baseline_json_path.name,
            "baseline_portfolio_ic": portfolio_ic,
            "baseline_sharpe": portfolio_sharpe,
            "baseline_max_dd_pct": portfolio_max_dd,
            "baseline_metrics_derived": {
                "A_top_level_median_signed": baseline_top_median,
                "B_top_level_median_abs": baseline_top_abs_median,
                "C_fold_level_median_signed": baseline_fold_median,
                "D_fold_level_median_abs": baseline_fold_abs_median,
                "n_top_level_alphas": len(top_level_ics),
                "n_fold_level_values": len(fold_ics),
            },
            "primary_comparator": "B_top_level_median_abs",
            "primary_comparator_value": baseline_primary,
            "primary_comparator_rationale": (
                "Top-level |alpha_ics| median. Each baseline alpha has one averaged IC "
                "across 12 folds; each auto candidate has one IC on the train set. "
                "Using |IC| removes sign-convention differences between template "
                "directions and compares signal strength directly."
            ),
            "auto_mean_ic_signed": mean_auto_ic,
            "auto_median_ic_signed": median_auto_ic,
            "auto_median_abs_ic": median_auto_abs_ic,
            "auto_max_abs_ic": max_auto_ic,
            "auto_positive_ic_rate": f"{n_positive}/{len(real_ics)}" if real_ics else None,
            "delta_abs_vs_primary": delta_abs,
            "delta_pct_vs_primary": delta_pct,
        },
        "integration_gap": (
            "Phase35 walk-forward engine has config params for automated discovery "
            "(enable_automated_discovery, etc.) but per-fold invocation is NOT wired. "
            "self.enable_automated_discovery is assigned but never read in the fold loop. "
            "AutomatedAlphaDiscoveryFactory is not imported in phase35.py. "
            "Therefore, direct integration into Phase35 backtest is UNSUPPORTED. "
            "This evaluation uses standalone real-data IC/transfer diagnostics "
            "on the train portion of the last walk-forward fold."
        ),
    }

    if diag_report:
        output["transfer_diagnostics"] = {
            "n_evaluated": diag_report.candidates_evaluated,
            "n_recommended": diag_report.candidates_recommended,
            "verdicts": {d.alpha_name: d.transfer_verdict for d in diag_report.diagnostics},
        }

    output_file = output_dir / f"auto_alpha_real_dynamic_eval_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)

    logger.info(f"\nResults written to {output_file}")
    logger.info("Done. Research-only — no live promotion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
