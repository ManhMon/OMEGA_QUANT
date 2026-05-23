#!/usr/bin/env python3
"""
Stage 5: Slippage Analysis Tool
=================================
Reads all daily shadow live logs from .ly_state/shadow_live/,
computes average slippage, compares against Phase 35 backtest baseline,
and generates a PASS/FAIL verdict (threshold: 2 bps deviation).

Author: Backend Engineer (Role 09) [L2-Impl:Role9-Backend]
Date: 2026-05-22
Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("stage5_slippage_analysis")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
SHADOW_LIVE_DIR = PROJECT_ROOT / ".ly_state" / "shadow_live"
PHASE35_RESULTS_DIR = PROJECT_ROOT / ".ly_state" / "session"

# Success criterion: shadow slippage deviation < 2 bps vs backtest baseline
SLIPPAGE_TOLERANCE_BPS = 2.0

# Default Phase 35 backtest baseline slippage (bps).
# Overridden if phase35_backtest_baseline.json exists in .ly_state/session/.
DEFAULT_BASELINE_BPS = 5.0


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def load_daily_logs(log_dir: str) -> List[Dict[str, Any]]:
    """Load all daily execution logs from shadow_live directory.

    Parameters
    ----------
    log_dir : str
        Path to directory containing YYYY-MM-DD.json log files

    Returns
    -------
    list of dict
        Parsed log records, sorted by date ascending
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        logger.warning(f"Log directory not found: {log_path}")
        return []

    records: List[Dict[str, Any]] = []
    for json_file in sorted(log_path.glob("????-??-??.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                record = json.load(f)
            records.append(record)
            logger.debug(f"Loaded log: {json_file.name}")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Skipping malformed log {json_file.name}: {exc}")

    logger.info(f"Loaded {len(records)} daily logs from {log_path}")
    return records


def compute_average_slippage(logs: List[Dict[str, Any]]) -> float:
    """Compute average slippage in bps across all daily logs.

    Parameters
    ----------
    logs : list of dict
        Daily execution log records (from load_daily_logs)

    Returns
    -------
    float
        Average slippage in basis points. Returns 0.0 if no valid logs.
    """
    if not logs:
        logger.warning("No logs provided; returning 0.0 average slippage")
        return 0.0

    slippages = [
        float(r["total_slippage_bps"])
        for r in logs
        if r.get("status") == "OK" and r.get("total_slippage_bps") is not None
    ]

    if not slippages:
        logger.warning("No valid slippage values found in logs")
        return 0.0

    avg = float(np.mean(slippages))
    logger.info(
        f"Slippage stats over {len(slippages)} days: "
        f"avg={avg:.3f}bps, min={min(slippages):.3f}bps, max={max(slippages):.3f}bps"
    )
    return avg


def load_baseline_slippage() -> float:
    """Load Phase 35 backtest baseline slippage from persisted results.

    Looks for .ly_state/session/phase35_backtest_baseline.json.
    Falls back to DEFAULT_BASELINE_BPS if file not found.

    Returns
    -------
    float
        Baseline slippage in basis points
    """
    baseline_path = PHASE35_RESULTS_DIR / "phase35_backtest_baseline.json"
    if baseline_path.exists():
        try:
            with open(baseline_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            baseline = float(data["avg_slippage_bps"])
            logger.info(f"Loaded Phase 35 baseline slippage: {baseline:.3f}bps from {baseline_path}")
            return baseline
        except (KeyError, ValueError, OSError) as exc:
            logger.warning(f"Could not parse baseline file: {exc}. Using default {DEFAULT_BASELINE_BPS}bps")

    logger.info(f"No baseline file found; using default {DEFAULT_BASELINE_BPS}bps")
    return DEFAULT_BASELINE_BPS


def compare_to_baseline(avg_slippage: float, baseline: float) -> str:
    """Compare average shadow slippage to backtest baseline.

    Parameters
    ----------
    avg_slippage : float
        Average shadow live slippage in bps
    baseline : float
        Phase 35 backtest baseline slippage in bps

    Returns
    -------
    str
        "PASS" if |avg_slippage - baseline| < SLIPPAGE_TOLERANCE_BPS, else "FAIL"
    """
    deviation = abs(avg_slippage - baseline)
    verdict = "PASS" if deviation < SLIPPAGE_TOLERANCE_BPS else "FAIL"
    logger.info(
        f"Slippage comparison: shadow={avg_slippage:.3f}bps, "
        f"baseline={baseline:.3f}bps, deviation={deviation:.3f}bps "
        f"(tolerance={SLIPPAGE_TOLERANCE_BPS}bps) -> {verdict}"
    )
    return verdict


def build_report(
    logs: List[Dict[str, Any]],
    avg_slippage: float,
    baseline: float,
    verdict: str,
) -> Dict[str, Any]:
    """Build structured analysis report.

    Parameters
    ----------
    logs : list of dict
        All daily log records
    avg_slippage : float
        Computed average slippage in bps
    baseline : float
        Phase 35 baseline slippage in bps
    verdict : str
        "PASS" or "FAIL"

    Returns
    -------
    dict
        Full report payload
    """
    ok_logs = [r for r in logs if r.get("status") == "OK"]
    slippages = [float(r["total_slippage_bps"]) for r in ok_logs if r.get("total_slippage_bps") is not None]

    per_day = [
        {
            "date": r.get("date"),
            "slippage_bps": r.get("total_slippage_bps"),
            "cost_bps": r.get("total_cost_bps"),
            "num_trades": r.get("num_trades"),
            "status": r.get("status"),
        }
        for r in logs
    ]

    return {
        "generated_at": pd.Timestamp.now("UTC").isoformat().replace("+00:00", "Z"),
        "total_days_logged": len(logs),
        "valid_days": len(ok_logs),
        "avg_slippage_bps": round(avg_slippage, 4),
        "baseline_slippage_bps": round(baseline, 4),
        "deviation_bps": round(abs(avg_slippage - baseline), 4),
        "tolerance_bps": SLIPPAGE_TOLERANCE_BPS,
        "verdict": verdict,
        "slippage_std_bps": round(float(np.std(slippages)), 4) if len(slippages) > 1 else 0.0,
        "slippage_min_bps": round(min(slippages), 4) if slippages else 0.0,
        "slippage_max_bps": round(max(slippages), 4) if slippages else 0.0,
        "per_day": per_day,
    }


def run_analysis(
    log_dir: Optional[str] = None,
    baseline_bps: Optional[float] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run full slippage analysis pipeline.

    Parameters
    ----------
    log_dir : str, optional
        Override log directory (default: .ly_state/shadow_live/)
    baseline_bps : float, optional
        Override baseline slippage in bps (default: load from file or DEFAULT_BASELINE_BPS)
    output_path : str, optional
        Write JSON report to this path if provided

    Returns
    -------
    dict
        Analysis report
    """
    effective_log_dir = log_dir or str(SHADOW_LIVE_DIR)
    logs = load_daily_logs(effective_log_dir)
    avg_slippage = compute_average_slippage(logs)
    baseline = baseline_bps if baseline_bps is not None else load_baseline_slippage()
    verdict = compare_to_baseline(avg_slippage, baseline)
    report = build_report(logs, avg_slippage, baseline, verdict)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Report written to {out}")

    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Stage 5 Slippage Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default=None,
        help=f"Shadow live log directory (default: {SHADOW_LIVE_DIR})",
    )
    parser.add_argument(
        "--baseline-bps",
        type=float,
        default=None,
        help="Override baseline slippage in bps",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write JSON report to this path",
    )
    args = parser.parse_args()

    report = run_analysis(
        log_dir=args.log_dir,
        baseline_bps=args.baseline_bps,
        output_path=args.output,
    )

    print("\n" + "=" * 55)
    print("STAGE 5 SLIPPAGE ANALYSIS REPORT")
    print("=" * 55)
    print(f"  Days logged:       {report['total_days_logged']}")
    print(f"  Valid days:        {report['valid_days']}")
    print(f"  Avg slippage:      {report['avg_slippage_bps']:.3f} bps")
    print(f"  Baseline:          {report['baseline_slippage_bps']:.3f} bps")
    print(f"  Deviation:         {report['deviation_bps']:.3f} bps")
    print(f"  Tolerance:         {report['tolerance_bps']:.1f} bps")
    print(f"  VERDICT:           {report['verdict']}")
    print("=" * 55)

    sys.exit(0 if report["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
