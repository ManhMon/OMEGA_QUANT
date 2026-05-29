#!/usr/bin/env python3
"""Walk-forward universe selection (Phase 1.5 v2 - look-ahead fix).

For each year Y in [start..end]:
  1. Train classifier on data <= (Y-1)-12-31  (no future)
  2. Select universe AS OF Y-01-02            (PIT)
  3. Save models/universe_classifier_<Y-1>.joblib + universe_<Y>.json

This eliminates the look-ahead bias where Phase 1.7 used 2020-2024 data
to pick "high quality" tickers for the 2020-2024 backtest.
"""
from __future__ import annotations
import argparse, logging, subprocess, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("walk_forward_universe")

PROJECT_ROOT = Path(__file__).parent.parent

def run(cmd: list[str]) -> int:
    logger.info("+ %s", " ".join(cmd))
    res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        logger.error("FAIL: %s", res.stderr[-2000:])
        return res.returncode
    last = res.stdout.strip().split("\n")[-5:]
    for line in last:
        logger.info("  %s", line)
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2020, help="first OOS year")
    parser.add_argument("--end",   type=int, default=2024, help="last OOS year")
    parser.add_argument("--n",     type=int, default=50)
    parser.add_argument("--data",  default="data/market_2015_now.parquet")
    parser.add_argument("--py",    default=sys.executable)
    args = parser.parse_args()

    rc_total = 0
    for year in range(args.start, args.end + 1):
        train_end = f"{year - 1}-12-31"
        select_date = f"{year}-01-02"
        model_out = f"models/universe_classifier_{year - 1}.joblib"

        logger.info("=== Walk-forward year %d (train_end=%s, select=%s) ===", year, train_end, select_date)

        rc = run([
            args.py, "scripts/train_universe_classifier.py",
            "--data", args.data,
            "--train-end", train_end,
            "--model-out", model_out,
        ])
        if rc != 0:
            rc_total = rc
            continue

        rc = run([
            args.py, "scripts/select_universe_dynamic.py",
            "--date", select_date,
            "--data", args.data,
            "--model", model_out,
            "--n", str(args.n),
        ])
        if rc != 0:
            rc_total = rc

    logger.info("=== Walk-forward complete (final rc=%d) ===", rc_total)
    return rc_total

if __name__ == "__main__":
    sys.exit(main())
