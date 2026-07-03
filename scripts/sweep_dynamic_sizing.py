#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from itertools import product
from pathlib import Path
import sys

import pandas as pd
from scipy.stats import binomtest
from scipy.stats import ttest_rel

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from backtest_hybrid_regime import aggregate_fold_results
from omega.quant.validation.sharpe_diagnostics import audit_sharpe


def paired_stats(lhs: list[float], rhs: list[float]) -> dict:
    deltas = [float(a - b) for a, b in zip(lhs, rhs)]
    if not deltas:
        return {"median_delta": 0.0, "sign_test_p": 1.0, "paired_t_p": 1.0}
    non_zero = [delta for delta in deltas if delta != 0]
    sign_p = 1.0
    if non_zero:
        positives = sum(delta > 0 for delta in non_zero)
        sign_p = float(binomtest(positives, len(non_zero), 0.5).pvalue)
    t_p = 1.0 if len(deltas) < 2 else float(ttest_rel(lhs, rhs).pvalue)
    return {
        "median_delta": float(pd.Series(deltas).median()),
        "sign_test_p": sign_p,
        "paired_t_p": t_p,
    }


def build_grid(
    alphas: list[float] | None = None,
    conf_floors: list[float] | None = None,
    modes: list[str] | None = None,
) -> list[dict]:
    alphas = alphas or [0.1, 0.2]
    conf_floors = conf_floors or [0.25, 0.5]
    modes = modes or ["size", "size_gate"]
    return [
        {"conformal_alpha": alpha, "conf_floor": floor, "mode": mode}
        for alpha, floor, mode in product(alphas, conf_floors, modes)
    ]


def sweep_from_fold_runner(
    fold_specs: list[dict],
    total_combinatorial_folds: int,
    run_all_folds_fn,
) -> dict:
    baseline_results = aggregate_fold_results(
        run_all_folds_fn(fold_specs, total_combinatorial_folds, workers=1)
    )
    rows = []
    nested = {"grid": [], "baseline_reused": True}
    for point in build_grid():
        specs = []
        for spec in fold_specs:
            updated = dict(spec)
            cfg = dict(updated.get("conformal_cfg") or {})
            cfg.update(
                {
                    "enabled": True,
                    "alpha": point["conformal_alpha"],
                    "conf_floor": point["conf_floor"],
                    "mode": point["mode"],
                }
            )
            updated["conformal_cfg"] = cfg
            specs.append(updated)
        aggregated = aggregate_fold_results(
            run_all_folds_fn(specs, total_combinatorial_folds, workers=1)
        )
        aggregated["Baseline"] = baseline_results["Baseline"]
        aggregated["Hybrid"] = baseline_results["Hybrid"]
        deltas_ch = paired_stats(
            aggregated["Conformal"]["per_fold_sharpe"],
            aggregated["Hybrid"]["per_fold_sharpe"],
        )
        deltas_hb = paired_stats(
            aggregated["Hybrid"]["per_fold_sharpe"],
            aggregated["Baseline"]["per_fold_sharpe"],
        )
        nested["grid"].append(
            {
                "params": point,
                "aggregated": aggregated,
                "paired": {
                    "conformal_minus_hybrid": deltas_ch,
                    "hybrid_minus_baseline": deltas_hb,
                },
                "headline_sharpe_audit": audit_sharpe(
                    aggregated["Conformal"]["per_fold_sharpe"]
                ).__dict__,
            }
        )
        for scenario, metrics in aggregated.items():
            rows.append(
                {
                    **point,
                    "scenario": scenario,
                    "mean_sharpe": metrics["mean_sharpe"],
                    "std_sharpe": metrics["std_sharpe"],
                    "median_sharpe": metrics["median_sharpe"],
                    "mean_max_dd": metrics["mean_max_dd"],
                    "worst_max_dd": metrics["worst_max_dd"],
                    "mean_return": metrics["mean_return"],
                    "per_fold_sharpe": metrics["per_fold_sharpe"],
                }
            )
    return {"rows": rows, "nested": nested}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="default")
    args = parser.parse_args()
    results_dir = REPO_ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    payload = {"rows": [], "nested": {"grid": [], "baseline_reused": True}}
    csv_path = results_dir / f"phase20_sizing_sweep_{args.tag}.csv"
    json_path = results_dir / f"phase20_sizing_sweep_{args.tag}.json"
    pd.DataFrame(payload["rows"]).to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(payload["nested"], indent=2), encoding="utf-8")
    print(csv_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
