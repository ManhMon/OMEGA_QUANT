#!/usr/bin/env python3
"""Sequential label-horizon sweep for hybrid-regime quick backtests."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = REPO_ROOT / "data" / "horizon_sweep_results"
BACKTEST_RESULT_DIR = REPO_ROOT / "data" / "phase35_results"
DEFAULT_HORIZONS = [10, 15, 20, 30, 40, 60, 90]
RUN_DATE = "20260623"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sweep hybrid-regime label horizons serially.")
    parser.add_argument("--horizons", type=int, nargs="+", default=DEFAULT_HORIZONS)
    parser.add_argument("--workers", type=int, default=1, help="Sweep/backtest workers. Must be 1.")
    parser.add_argument("--output-dir", type=Path, default=RESULT_DIR)
    parser.add_argument("--backtest-results-dir", type=Path, default=BACKTEST_RESULT_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Build commands without running backtests.")
    parser.add_argument("--resume", action="store_true", help="Reuse existing per-horizon JSON results when present.")
    return parser.parse_args()


def enforce_serial_workers(workers: int) -> int:
    if workers != 1:
        raise ValueError("Label horizon sweep is memory-safe only with --workers 1")
    return workers


def build_command(horizon: int, workers: int) -> list[str]:
    return [
        sys.executable,
        "scripts/run_backtest.py",
        "hybrid-regime",
        "--quick-mode",
        "--workers",
        str(workers),
        "--label-horizon",
        str(horizon),
        "--output-tag",
        f"horizon_{horizon}",
    ]


def result_path_for_horizon(results_dir: Path, horizon: int) -> Path:
    return results_dir / f"hybrid_regime_cpcv_comparison_horizon_{horizon}.json"


def scenario_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    aggregated = payload.get("aggregated", {})
    scenario = aggregated.get("Hybrid") or aggregated.get("Baseline") or next(iter(aggregated.values()), {})
    diag = scenario.get("profitability_diag", {}) if isinstance(scenario, dict) else {}

    gross = diag.get("mean_gross_return")
    net = scenario.get("mean_return") if isinstance(scenario, dict) else None
    tc_drag = gross - net if isinstance(gross, (int, float)) and isinstance(net, (int, float)) else None

    return {
        "scenario": "Hybrid" if "Hybrid" in aggregated else "Baseline" if "Baseline" in aggregated else "first_available",
        "mean_sharpe": scenario.get("mean_sharpe") if isinstance(scenario, dict) else None,
        "mean_return": net,
        "mean_max_dd": scenario.get("mean_max_dd") if isinstance(scenario, dict) else None,
        "gross_return": gross,
        "tc_drag": tc_drag,
        "n_folds_completed": scenario.get("n_folds_completed") if isinstance(scenario, dict) else None,
        "n_folds_errored": scenario.get("n_folds_errored") if isinstance(scenario, dict) else None,
    }


def load_horizon_result(results_dir: Path, horizon: int) -> dict[str, Any]:
    path = result_path_for_horizon(results_dir, horizon)
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    metrics = scenario_metrics(payload)
    metrics["source_json"] = str(path.relative_to(REPO_ROOT))
    return metrics


def run_horizon(
    horizon: int,
    workers: int,
    results_dir: Path,
    dry_run: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    command = build_command(horizon, workers)
    if dry_run:
        return {"horizon": horizon, "command": command, "status": "dry_run"}

    if resume and result_path_for_horizon(results_dir, horizon).exists():
        row = {"horizon": horizon, "command": command, "resumed": True}
        row.update(load_horizon_result(results_dir, horizon))
        row["status"] = "ok"
        return row

    completed = subprocess.run(command, cwd=REPO_ROOT, check=False, text=True)
    row = {"horizon": horizon, "command": command, "returncode": completed.returncode}
    if completed.returncode != 0:
        row["status"] = "failed"
        return row

    row.update(load_horizon_result(results_dir, horizon))
    row["status"] = "ok"
    return row


def write_json(payload: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"horizon_sweep_{RUN_DATE}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    return path


def pct(value: Any) -> str:
    return "NA" if value is None else f"{value * 100:.2f}%"


def num(value: Any) -> str:
    return "NA" if value is None else f"{value:.4f}"


def write_markdown(payload: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"horizon_sweep_{RUN_DATE}.md"
    rows = payload["results"]
    lines = [
        "# Label Horizon Sweep - 20260623",
        "",
        "Command template: `python scripts/run_backtest.py hybrid-regime --quick-mode --workers 1 --label-horizon <H> --output-tag horizon_<H>`",
        "",
        "| Horizon | Status | Scenario | Sharpe | Gross | Net | TC Drag | Max DD | Folds |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        folds = row.get("n_folds_completed", "NA")
        lines.append(
            f"| {row['horizon']} | {row.get('status', 'unknown')} | {row.get('scenario', 'NA')} | "
            f"{num(row.get('mean_sharpe'))} | {pct(row.get('gross_return'))} | "
            f"{pct(row.get('mean_return'))} | {pct(row.get('tc_drag'))} | "
            f"{pct(row.get('mean_max_dd'))} | {folds} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_sweep(args: argparse.Namespace) -> dict[str, Any]:
    workers = enforce_serial_workers(args.workers)
    results = [
        run_horizon(h, workers, args.backtest_results_dir, args.dry_run, args.resume)
        for h in args.horizons
    ]
    return {
        "gate": "LABEL_HORIZON_SWEEP_ENSEMBLE_20260623",
        "run_date": RUN_DATE,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "horizons": args.horizons,
        "workers": workers,
        "quick_mode": True,
        "results": results,
    }


def main() -> int:
    args = parse_args()
    payload = run_sweep(args)
    json_path = write_json(payload, args.output_dir)
    md_path = write_markdown(payload, args.output_dir)
    print(f"Wrote {json_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {md_path.relative_to(REPO_ROOT)}")
    return 1 if any(r.get("status") == "failed" for r in payload["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
