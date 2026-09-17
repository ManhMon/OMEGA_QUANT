import json
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from scripts import run_backtest
from scripts import sweep_label_horizons as sweep


def test_build_command_forces_hybrid_quick_serial():
    command = sweep.build_command(30, 1)

    assert command[1:] == [
        "scripts/run_backtest.py",
        "hybrid-regime",
        "--quick-mode",
        "--workers",
        "1",
        "--label-horizon",
        "30",
        "--output-tag",
        "horizon_30",
    ]


def test_enforce_serial_workers_rejects_parallel():
    with pytest.raises(ValueError, match="--workers 1"):
        sweep.enforce_serial_workers(2)


def test_scenario_metrics_computes_tc_drag_from_gross_minus_net():
    payload = {
        "aggregated": {
            "Hybrid": {
                "mean_sharpe": 1.25,
                "mean_return": 0.08,
                "mean_max_dd": -0.12,
                "n_folds_completed": 5,
                "n_folds_errored": 0,
                "profitability_diag": {"mean_gross_return": 0.11},
            }
        }
    }

    metrics = sweep.scenario_metrics(payload)

    assert metrics["scenario"] == "Hybrid"
    assert metrics["tc_drag"] == pytest.approx(0.03)
    assert metrics["gross_return"] == pytest.approx(0.11)
    assert metrics["mean_return"] == pytest.approx(0.08)


def test_run_horizon_invokes_subprocess_and_loads_result(tmp_path, monkeypatch):
    results_dir = tmp_path / "phase35_results"
    results_dir.mkdir()
    out_path = sweep.result_path_for_horizon(results_dir, 10)
    out_path.write_text(
        json.dumps(
            {
                "aggregated": {
                    "Hybrid": {
                        "mean_sharpe": 0.5,
                        "mean_return": 0.04,
                        "mean_max_dd": -0.1,
                        "n_folds_completed": 5,
                        "n_folds_errored": 0,
                        "profitability_diag": {"mean_gross_return": 0.06},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_run(command, cwd, check, text):
        calls.append((command, cwd, check, text))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(sweep.subprocess, "run", fake_run)
    monkeypatch.setattr(sweep, "REPO_ROOT", tmp_path)

    row = sweep.run_horizon(10, 1, results_dir)

    assert row["status"] == "ok"
    assert row["tc_drag"] == pytest.approx(0.02)
    assert calls[0][0][1:] == [
        "scripts/run_backtest.py",
        "hybrid-regime",
        "--quick-mode",
        "--workers",
        "1",
        "--label-horizon",
        "10",
        "--output-tag",
        "horizon_10",
    ]
    assert calls[0][1] == tmp_path


def test_run_sweep_writes_json_and_markdown(tmp_path):
    payload = {
        "results": [
            {
                "horizon": 10,
                "status": "ok",
                "scenario": "Hybrid",
                "mean_sharpe": 1.0,
                "gross_return": 0.12,
                "mean_return": 0.09,
                "tc_drag": 0.03,
                "mean_max_dd": -0.08,
                "n_folds_completed": 5,
            }
        ]
    }

    json_path = sweep.write_json(payload, tmp_path)
    md_path = sweep.write_markdown(payload, tmp_path)

    assert json_path.name == "horizon_sweep_20260623.json"
    assert md_path.name == "horizon_sweep_20260623.md"
    assert json.loads(json_path.read_text(encoding="utf-8"))["results"][0]["tc_drag"] == pytest.approx(0.03)
    assert "| 10 | ok | Hybrid | 1.0000 | 12.00% | 9.00% | 3.00% | -8.00% | 5 |" in md_path.read_text(encoding="utf-8")


def test_run_sweep_dry_run_all_default_horizons():
    args = Namespace(
        horizons=sweep.DEFAULT_HORIZONS,
        workers=1,
        output_dir=Path("unused"),
        backtest_results_dir=Path("unused"),
        dry_run=True,
        resume=False,
    )

    payload = sweep.run_sweep(args)

    assert payload["horizons"] == [10, 15, 20, 30, 40, 60, 90]
    assert all(row["status"] == "dry_run" for row in payload["results"])


def test_run_horizon_resume_uses_existing_result(tmp_path, monkeypatch):
    results_dir = tmp_path / "phase35_results"
    results_dir.mkdir()
    sweep.result_path_for_horizon(results_dir, 15).write_text(
        json.dumps(
            {
                "aggregated": {
                    "Hybrid": {
                        "mean_sharpe": 0.7,
                        "mean_return": 0.05,
                        "mean_max_dd": -0.09,
                        "n_folds_completed": 5,
                        "n_folds_errored": 0,
                        "profitability_diag": {"mean_gross_return": 0.08},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sweep, "REPO_ROOT", tmp_path)

    def fail_run(*args, **kwargs):  # pragma: no cover - defensive
        raise AssertionError("subprocess.run should not be called in resume mode")

    monkeypatch.setattr(sweep.subprocess, "run", fail_run)

    row = sweep.run_horizon(15, 1, results_dir, resume=True)

    assert row["status"] == "ok"
    assert row["resumed"] is True
    assert row["tc_drag"] == pytest.approx(0.03)


def test_run_backtest_enforce_worker_safety_appends_serial_workers():
    args = run_backtest.enforce_worker_safety("hybrid-regime", ["--label-horizon", "20", "--quick-mode"])

    assert args[-2:] == ["--workers", "1"]


def test_run_backtest_enforce_worker_safety_rejects_parallel_workers():
    with pytest.raises(SystemExit, match="requires --workers 1"):
        run_backtest.enforce_worker_safety(
            "hybrid-regime",
            ["--label-horizon", "20", "--quick-mode", "--workers", "2"],
        )
