#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from omega.quant.validation.dsr import deflated_sharpe_ratio
from omega.quant.validation.sharpe_diagnostics import audit_sharpe
from omega.quant.validation.sharpe_diagnostics import assert_matches_production


BANNER = """RISK-FREE RATE: 0.0 (implicit; no subtraction in production path)
RETURN SERIES : per-date portfolio return, net of tcost, gross of rf
ANNUALIZATION : per-fold Sharpe = per-bar (NOT annualized)
                DSR Sharpe      = per-bar * sqrt(252)
sr_benchmark  : DSR null-hypothesis threshold, NOT an rf deduction"""


def _extract_returns(payload: dict) -> tuple[str, list[float]]:
    if isinstance(payload.get("per_fold_sharpe"), list):
        return "per_fold_sharpe", [float(v) for v in payload["per_fold_sharpe"]]
    for value in payload.values():
        if isinstance(value, dict) and isinstance(value.get("per_fold_sharpe"), list):
            return "per_fold_sharpe", [float(v) for v in value["per_fold_sharpe"]]
    raise ValueError("No per_fold_sharpe series found in JSON payload")


def run_synthetic() -> int:
    rng = np.random.default_rng(42)
    print(BANNER)
    series_map = {
        "constant": [0.001] * 5,
        "single": [0.001],
        "seeded_8": rng.normal(0.001, 0.01, 8).tolist(),
        "seeded_64": rng.normal(0.0005, 0.012, 64).tolist(),
        "seeded_252": rng.normal(0.0008, 0.009, 252).tolist(),
    }
    for name, returns in series_map.items():
        assert_matches_production(returns)
        audit = audit_sharpe(returns)
        print(
            f"[{name}] n={audit.n} sharpe_per_bar={audit.sharpe_per_bar:.12f} "
            f"annualized={audit.sharpe_annualized:.12f}"
        )
    return 0


def run_from_json(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    label, returns = _extract_returns(payload)
    audit = audit_sharpe(returns)
    assert_matches_production(returns)
    print(BANNER)
    print(f"source={path} series={label}")
    print(f"recomputed_per_bar={audit.sharpe_per_bar:.12f}")
    print(f"recomputed_annualized={audit.sharpe_annualized:.12f}")
    print(f"dsr_probability={deflated_sharpe_ratio(returns).dsr:.12f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--from-json", type=Path)
    args = parser.parse_args()
    if args.from_json is not None:
        return run_from_json(args.from_json)
    return run_synthetic()


if __name__ == "__main__":
    raise SystemExit(main())
