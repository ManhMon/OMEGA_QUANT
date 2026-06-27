#!/usr/bin/env python3
"""
Unified Backtest CLI - OMEGA_QUANT
Entry point for all backtest modes (v2_cpcv, phase35, v22-v33 variants,
hybrid-regime, walk-forward, stress-test, regime-nested-cv).

Usage:
    python scripts/run_backtest.py v2-cpcv [args]
    python scripts/run_backtest.py phase35 [args]
    python scripts/run_backtest.py v22-diverse [args]
    python scripts/run_backtest.py v23-ensemble [args]
    python scripts/run_backtest.py v24-multihorizon [args]
    python scripts/run_backtest.py v25-altfeatures [args]
    python scripts/run_backtest.py multihorizon-ensemble [args]
    python scripts/run_backtest.py v30-full [args]
    python scripts/run_backtest.py v31-unified [args]
    python scripts/run_backtest.py v32-ml-system [args]
    python scripts/run_backtest.py v33-optuna [args]
    python scripts/run_backtest.py e2e-full [args]
    python scripts/run_backtest.py e2e-ml [args]
    python scripts/run_backtest.py advanced-features [args]
    python scripts/run_backtest.py evolution [args]
    python scripts/run_backtest.py evolution-integration [args]
    python scripts/run_backtest.py evolution-multiseed [args]
    python scripts/run_backtest.py flow [args]
    python scripts/run_backtest.py export-detailed [args]
    python scripts/run_backtest.py full-pipeline [args]
    python scripts/run_backtest.py hybrid-regime [args]
    python scripts/run_backtest.py walk-forward [args]
    python scripts/run_backtest.py stress-test [args]
    python scripts/run_backtest.py regime-nested-cv [args]

Author: Backend Engineer (Role 09)
Date: 2026-06-10
T2.3: Backtest script consolidation
Gate: HYBRID_REGIME_BACKTEST_PERF_20260621 — expanded hybrid-regime scope
"""
import sys
import subprocess
from pathlib import Path

SCRIPTS = {
    "v2-cpcv": "backtest_v2_cpcv.py",
    "phase35": "run_phase35_backtest.py",
    "v22-diverse": "backtest_v22_diverse.py",
    "v23-ensemble": "backtest_v23_ensemble.py",
    "v24-multihorizon": "backtest_v24_multihorizon.py",
    "multihorizon-ensemble": "backtest_multihorizon_ensemble.py",
    "v25-altfeatures": "backtest_v25_altfeatures.py",
    "v30-full": "backtest_v30_full.py",
    "v31-unified": "backtest_v31_unified.py",
    "v32-ml-system": "backtest_v32_ml_system.py",
    "v33-optuna": "backtest_v33_optuna.py",
    "e2e-full": "backtest_e2e_full.py",
    "e2e-ml": "backtest_e2e_ml.py",
    "advanced-features": "backtest_advanced_features.py",
    "evolution": "backtest_evolution.py",
    "evolution-integration": "backtest_evolution_integration.py",
    "evolution-multiseed": "backtest_evolution_multiseed.py",
    "flow": "backtest_flow.py",
    "export-detailed": "export_backtest_detailed.py",
    "full-pipeline": "run_full_pipeline_backtest.py",
    # Gate: HYBRID_REGIME_BACKTEST_PERF_20260621 — expanded scope
    "hybrid-regime": "backtest_hybrid_regime.py",
    "walk-forward": "run_walk_forward_validation.py",
    "stress-test": "run_stress_test.py",
    "regime-nested-cv": "run_regime_nested_cv.py",
}


def _workers_value(args: list[str]) -> str | None:
    for index, arg in enumerate(args):
        if arg == "--workers" and index + 1 < len(args):
            return args[index + 1]
        if arg.startswith("--workers="):
            return arg.split("=", 1)[1]
    return None


def enforce_worker_safety(mode: str, args: list[str]) -> list[str]:
    if mode != "hybrid-regime" or "--label-horizon" not in args:
        return args

    workers = _workers_value(args)
    if workers is None:
        return [*args, "--workers", "1"]
    if workers != "1":
        raise SystemExit("Error: hybrid-regime label horizon sweep requires --workers 1")
    return args


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("\nAvailable backtest modes:")
        for alias, script in sorted(SCRIPTS.items()):
            print(f"  {alias:30s} -> scripts/{script}")
        sys.exit(0)

    mode = sys.argv[1]
    if mode not in SCRIPTS:
        print(f"Error: Unknown backtest mode '{mode}'", file=sys.stderr)
        print(f"Available modes: {', '.join(sorted(SCRIPTS.keys()))}", file=sys.stderr)
        sys.exit(1)

    script_path = Path(__file__).parent / SCRIPTS[mode]
    if not script_path.exists():
        print(f"Error: Script not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    # Forward all remaining args to the target script
    forwarded_args = enforce_worker_safety(mode, sys.argv[2:])
    args = [sys.executable, str(script_path)] + forwarded_args
    exit_code = subprocess.call(args)
    if exit_code == 0 and mode == "hybrid-regime":
        report_script = Path(__file__).parent / "generate_report.py"
        exit_code = subprocess.call([sys.executable, str(report_script)])
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
