#!/usr/bin/env python3
"""Run Automated Alpha Discovery — PIT-safe, opt-in, research-only.

GATE: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615

Usage:
    python scripts/run_alpha_discovery.py --enable
    python scripts/run_alpha_discovery.py --enable --candidate-cap 50 --min-ic 0.02
    python scripts/run_alpha_discovery.py  # disabled by default

Research-only script.  Does NOT promote candidates to live or change
default pipeline behavior.  All screening is train-only and PIT-safe.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Add src and scripts to path
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from omega.quant.alpha.automated_alpha_discovery import (
    AutomatedAlphaDiscoveryFactory,
    AUTOMATED_DISCOVERY_GATE_ID,
    DEFAULT_CANDIDATE_CAP,
    DEFAULT_CORR_THRESHOLD,
    DEFAULT_MIN_IC,
)
from omega.quant.alpha.alpha_transfer_diagnostics import (
    run_transfer_diagnostics,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Automated Alpha Discovery (research-only, opt-in)"
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        default=False,
        help="Enable automated alpha discovery (default: disabled)",
    )
    parser.add_argument(
        "--candidate-cap",
        type=int,
        default=DEFAULT_CANDIDATE_CAP,
        help=f"Max candidates to generate (default: {DEFAULT_CANDIDATE_CAP})",
    )
    parser.add_argument(
        "--corr-threshold",
        type=float,
        default=DEFAULT_CORR_THRESHOLD,
        help=f"Correlation filter threshold (default: {DEFAULT_CORR_THRESHOLD})",
    )
    parser.add_argument(
        "--min-ic",
        type=float,
        default=DEFAULT_MIN_IC,
        help=f"Minimum IC for screening (default: {DEFAULT_MIN_IC})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for determinism (default: 42)",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default=None,
        help="Path to parquet data file (optional, uses synthetic if not provided)",
    )
    parser.add_argument(
        "--return-col",
        type=str,
        default="fwd_ret_5",
        help="Forward return column name (default: fwd_ret_5)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for results (default: .ly_state/session/)",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        default=False,
        help="Run bounded smoke test with small candidate cap",
    )
    return parser.parse_args()


def _make_synthetic_data(
    n_tickers: int = 10, n_days: int = 120, seed: int = 42
) -> pd.DataFrame:
    """Create synthetic OHLCV panel with forward returns for testing."""
    rng = np.random.RandomState(seed)
    rows = []
    dates = pd.date_range("2022-01-03", periods=n_days, freq="B")

    for t in range(n_tickers):
        ticker = f"SYM{t:02d}"
        base_price = 10000.0 + rng.randn() * 2000
        for d_idx, date in enumerate(dates):
            noise = rng.randn() * 0.02
            close = base_price * (1 + noise * (d_idx + 1) / n_days)
            open_price = close * (1 + rng.randn() * 0.005)
            high = max(open_price, close) * (1 + abs(rng.randn()) * 0.01)
            low = min(open_price, close) * (1 - abs(rng.randn()) * 0.01)
            volume = int(abs(rng.randn() * 100000) + 10000)
            fwd_ret = rng.normal(0, 0.02)
            rows.append({
                "ticker": ticker,
                "date": date,
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": volume,
                "fwd_ret_5": fwd_ret,
            })
    return pd.DataFrame(rows).sort_values(["date", "ticker"]).reset_index(drop=True)


def main():
    args = parse_args()

    # Smoke test overrides
    if args.smoke_test:
        args.enable = True
        args.candidate_cap = min(args.candidate_cap, 10)
        logger.info(f"Smoke test mode: candidate_cap={args.candidate_cap}")

    logger.info(f"GATE: {AUTOMATED_DISCOVERY_GATE_ID}")
    logger.info(f"Enabled: {args.enable}")

    # Load or generate data
    if args.data_path and Path(args.data_path).exists():
        logger.info(f"Loading data from {args.data_path}")
        df = pd.read_parquet(args.data_path)
    else:
        logger.info("Using synthetic data (no --data-path provided)")
        df = _make_synthetic_data(seed=args.seed)

    if args.return_col not in df.columns:
        logger.warning(
            f"Return column '{args.return_col}' not found. "
            f"Creating synthetic forward returns."
        )
        rng = np.random.RandomState(args.seed)
        df[args.return_col] = rng.normal(0, 0.02, len(df))

    # Run discovery
    factory = AutomatedAlphaDiscoveryFactory(
        enabled=args.enable,
        candidate_cap=args.candidate_cap,
        corr_threshold=args.corr_threshold,
        min_ic=args.min_ic,
        seed=args.seed,
        return_col=args.return_col,
    )

    result = factory.run_discovery(df)

    # Output results
    output_dir = Path(args.output_dir) if args.output_dir else (
        _REPO_ROOT / ".ly_state" / "session"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"automated_alpha_discovery_report_{timestamp}.json"

    result_dict = result.to_dict()
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2, default=str)

    logger.info(f"Results written to {output_file}")
    logger.info(json.dumps(result_dict, indent=2, default=str))

    # Transfer diagnostics (if candidates found)
    if result.selected_candidates:
        logger.info("Running transfer diagnostics...")
        signals_df = factory.compute_candidate_signals(
            df, result.selected_candidates
        )
        candidate_signals = {}
        for c in result.selected_candidates:
            if c.name in signals_df.columns:
                candidate_signals[c.name] = signals_df[c.name]

        if candidate_signals:
            diag_report = run_transfer_diagnostics(
                candidates=candidate_signals,
                existing_signals=pd.DataFrame(),
                returns=df[args.return_col],
                dates=df["date"],
                tickers=df["ticker"],
                corr_threshold=args.corr_threshold,
                min_marginal_ic=args.min_ic,
            )
            diag_file = output_dir / f"alpha_transfer_diagnostics_{timestamp}.json"
            with open(diag_file, "w", encoding="utf-8") as f:
                json.dump(diag_report.to_dict(), f, indent=2, default=str)
            logger.info(f"Transfer diagnostics written to {diag_file}")

    logger.info("Done. Research-only — no live promotion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
