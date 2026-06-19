#!/usr/bin/env python3
"""LLM Nested Fold Diagnostic Script.

Runs the HybridAlphaMiner with nested-CV on synthetic or real panel data,
producing evidence for diagnostic review.

Usage:
    python scripts/llm_nested_fold_diagnostic.py \\
        --provider mock \\
        --candidate-budget 200 \\
        --top-k 10 \\
        --output .ly_state/session/hybrid_alpha_nested_diagnostic_20260612.json

Author: Backend Engineer (Role 09)
Date: 2026-06-12
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure repo root on path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from omega.quant.evolution.hybrid_alpha_miner import (
    HybridAlphaMiner,
    HybridAlphaMinerConfig,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("llm_nested_fold_diagnostic")


def generate_synthetic_panel(
    n_tickers: int = 5,
    n_dates: int = 100,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic panel for diagnostic testing."""
    rng = np.random.default_rng(seed)
    tickers = [f"SYM{i:03d}" for i in range(n_tickers)]
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="B")

    rows = []
    for t in tickers:
        base_close = 100.0 + rng.standard_normal() * 20
        base_volume = 1_000_000.0 + rng.standard_normal() * 200_000
        for d in dates:
            close = base_close + rng.standard_normal() * 2
            volume = abs(base_volume + rng.standard_normal() * 100_000)
            open_price = close + rng.standard_normal() * 0.5
            ret_1d = rng.standard_normal() * 0.02
            rows.append({
                "ticker": t,
                "date": d,
                "close": close,
                "open": open_price,
                "volume": volume,
                "ret_1d": ret_1d,
            })
            base_close = close
            base_volume = volume

    return pd.DataFrame(rows)


def generate_labels(panel: pd.DataFrame, seed: int = 42) -> np.ndarray:
    """Generate synthetic labels (correlated with close changes)."""
    rng = np.random.default_rng(seed)
    n = len(panel)
    # Labels correlated with ret_1d for some signal
    labels = panel["ret_1d"].values * 0.5 + rng.standard_normal(n) * 0.01
    return labels


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LLM Nested Fold Diagnostic"
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="mock",
        help="LLM provider (mock or openai-compatible)",
    )
    parser.add_argument(
        "--candidate-budget",
        type=int,
        default=200,
        help="Total candidate budget (default: 200)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of top candidates to select (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(
            REPO_ROOT
            / ".ly_state"
            / "session"
            / "hybrid_alpha_nested_diagnostic_20260612.json"
        ),
        help="Output JSON path for evidence",
    )
    parser.add_argument(
        "--n-tickers",
        type=int,
        default=5,
        help="Number of synthetic tickers (default: 5)",
    )
    parser.add_argument(
        "--n-dates",
        type=int,
        default=100,
        help="Number of dates per ticker (default: 100)",
    )
    parser.add_argument(
        "--n-outer-folds",
        type=int,
        default=3,
        help="Number of outer folds (default: 3)",
    )
    parser.add_argument(
        "--n-inner-folds",
        type=int,
        default=3,
        help="Number of inner folds (default: 3)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logger.info("=" * 60)
    logger.info("LLM Nested Fold Diagnostic")
    logger.info("=" * 60)
    logger.info(
        "provider=%s budget=%d top_k=%d outer=%d inner=%d",
        args.provider,
        args.candidate_budget,
        args.top_k,
        args.n_outer_folds,
        args.n_inner_folds,
    )

    # Generate synthetic data
    panel = generate_synthetic_panel(
        n_tickers=args.n_tickers,
        n_dates=args.n_dates,
    )
    labels = generate_labels(panel)
    feat_cols = ["close", "open", "volume", "ret_1d"]

    logger.info("Panel shape: %s, labels shape: %s", panel.shape, labels.shape)

    # Configure miner
    config = HybridAlphaMinerConfig(
        candidate_budget=args.candidate_budget,
        top_k=args.top_k,
        n_outer_folds=args.n_outer_folds,
        n_inner_folds=args.n_inner_folds,
        llm_provider=args.provider,
    )

    miner = HybridAlphaMiner(config)

    # Run mining
    selected, evidence = miner.run(
        panel=panel,
        feat_cols=feat_cols,
        labels=labels,
        ticker_col="ticker",
        date_col="date",
    )

    # Summary
    logger.info("=" * 60)
    logger.info("RESULTS")
    logger.info("=" * 60)
    logger.info("Total generated: %d", evidence["total_generated"])
    logger.info("Total selected: %d", evidence["total_selected"])
    logger.info("Deployment ready: %s", evidence["deployment_ready"])
    logger.info("Source proportions: %s", evidence["source_proportions"])
    logger.info("Formula memory: %s", evidence["formula_memory"])

    for i, rec in enumerate(selected):
        logger.info(
            "  [%d] %s | source=%s | obj=%.4f | ic=%.4f | cov=%.2f",
            i + 1,
            rec.formula_str[:50],
            rec.source.value,
            rec.objective_score,
            rec.inner_metrics.get("ic", 0.0),
            rec.inner_metrics.get("coverage", 0.0),
        )

    # Save evidence
    output_path = Path(args.output)
    miner.save_evidence(evidence, output_path)
    logger.info("Evidence saved to %s", output_path)


if __name__ == "__main__":
    main()
