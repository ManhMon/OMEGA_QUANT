from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import backtest_hybrid_regime as bhr
import sweep_dynamic_sizing as sweep
from omega.quant.models.conformal_predictor import ConformalTrendPredictor
from omega.quant.pipeline.overlays.risk_sizing import RiskSizingOverlay


class StubPredictor:
    def __init__(self, widths, groups=None):
        self.widths = np.asarray(widths, dtype=float)
        self._groups = groups

    def predict(self, X, groups, alpha=None):
        point = np.ones(len(X))
        widths = self.widths[: len(X)]
        group_keys = self._groups or list(
            zip(groups["regime"].astype(str), groups["liquidity_bucket"].astype(str))
        )
        return type(
            "Pred",
            (),
            {
                "lower": point - widths / 2.0,
                "upper": point + widths / 2.0,
                "point": point,
                "groups": group_keys,
            },
        )()

    def conditional_coverage(self, y_true, pred):
        return {key: 1.0 for key in pred.groups}


def _panel_and_weights():
    dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    panel = pd.DataFrame(
        {
            "date": [dates[0], dates[0], dates[1], dates[1], dates[2], dates[2]],
            "symbol": ["AAA", "BBB"] * 3,
            "feature": [1.0, 2.0, 1.5, 2.5, 1.2, 2.2],
            "adv_vnd": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            "returns": [0.01, 0.01, 0.02, 0.03, 0.01, 0.04],
        }
    )
    weights = pd.DataFrame(
        [[0.5, 0.5], [0.5, 0.5], [0.5, 0.5]],
        index=dates,
        columns=["AAA", "BBB"],
    )
    return panel, weights


def test_apply_preserves_shape_and_index():
    panel, weights = _panel_and_weights()
    overlay = bhr.ConformalGateOverlay(StubPredictor([0.1] * len(panel)), ["feature"])
    out = overlay.apply(weights, panel, {"gmm_regime_labels": {}})
    assert out.index.equals(weights.index)
    assert out.columns.equals(weights.columns)


def test_low_confidence_shrinks_weights():
    panel, weights = _panel_and_weights()
    overlay = bhr.ConformalGateOverlay(
        StubPredictor([10.0] * len(panel)),
        ["feature"],
        width_ref=1.0,
        conf_floor=0.25,
    )
    out = overlay.apply(weights, panel, {"gmm_regime_labels": {}})
    assert float(out.iloc[0, 0]) == pytest.approx(0.125)


def test_gate_zeroes_wide_intervals():
    panel, weights = _panel_and_weights()
    overlay = bhr.ConformalGateOverlay(
        StubPredictor([0.9] * len(panel), groups=[("neutral", "low")] * len(panel)),
        ["feature"],
        mode="gate",
        max_width_abs=0.5,
    )
    out = overlay.apply(
        weights,
        panel,
        {"gmm_regime_labels": {}, "conformal_coverage": {("neutral", "low"): 0.5}},
    )
    assert out.to_numpy().sum() == 0.0


def test_gate_ignores_realized_coverage_state():
    panel, weights = _panel_and_weights()
    overlay = bhr.ConformalGateOverlay(
        StubPredictor([0.1] * len(panel), groups=[("neutral", "low")] * len(panel)),
        ["feature"],
        mode="gate",
        min_coverage=0.95,
        max_width_abs=0.5,
    )
    out = overlay.apply(
        weights,
        panel,
        {"gmm_regime_labels": {}, "conformal_coverage": {("neutral", "low"): 0.0}},
    )
    assert out.equals(weights)


def test_missing_regime_falls_back():
    panel, weights = _panel_and_weights()
    overlay = bhr.ConformalGateOverlay(StubPredictor([0.0] * len(panel)), ["feature"])
    out = overlay.apply(weights, panel, {"gmm_regime_labels": {"2024-01-01": "bull"}})
    assert out.shape == weights.shape


def test_liquidity_bucketization_matches_training():
    buckets = bhr._bucketize_liquidity(pd.Series([1, 2, 3, 4, 5, 6]), 3)
    assert set(buckets.astype(str)) == {"low", "mid", "high"}


def test_disabled_is_identity():
    panel, weights = _panel_and_weights()
    overlay = bhr.ConformalGateOverlay(
        StubPredictor([0.0] * len(panel)),
        ["feature"],
        width_ref=1.0,
    )
    out = overlay.apply(weights, panel, {"gmm_regime_labels": {}})
    assert out.equals(weights)


def test_end_to_end_real_predictor():
    x_train = pd.DataFrame({"feature": np.linspace(-2, 2, 80)})
    y_train = x_train["feature"] * 0.3
    x_calib = pd.DataFrame({"feature": np.linspace(-1, 1, 40)})
    y_calib = x_calib["feature"] * 0.3
    groups = pd.DataFrame({"regime": ["bull"] * 40, "liquidity_bucket": ["high"] * 40})
    model = ConformalTrendPredictor(alpha=0.2, min_group_size=5)
    model.fit(x_train, y_train, x_calib, y_calib, groups)
    panel, weights = _panel_and_weights()
    panel = panel.assign(feature=np.linspace(-1, 1, len(panel)), adv_vnd=np.linspace(1, 6, len(panel)))
    overlay = bhr.ConformalGateOverlay(model, ["feature"], width_ref=1.0)
    out = overlay.apply(weights, panel, {"gmm_regime_labels": {}})
    assert out.shape == weights.shape


def test_scenario_absent_when_disabled():
    scenarios = bhr.build_scenario_overlays(1_000_000, conformal_overlay=None)
    assert set(scenarios) == {"Baseline", "Hybrid"}


def test_scenario_present_when_enabled():
    overlay = bhr.ConformalGateOverlay(StubPredictor([0.0]), ["feature"], width_ref=1.0)
    scenarios = bhr.build_scenario_overlays(1_000_000, conformal_overlay=overlay)
    assert "Conformal" in scenarios
    conformal_stack = scenarios["Conformal"]
    risk_idx = next(i for i, item in enumerate(conformal_stack) if isinstance(item, RiskSizingOverlay))
    assert conformal_stack[risk_idx + 1] is overlay


def test_pit_embargo_assertion():
    with pytest.raises(ValueError, match="pit_embargo exceeds fold test start"):
        bhr.assert_fast_global_embargo_safe(
            datetime(2024, 1, 5, tzinfo=timezone.utc),
            np.array(pd.to_datetime(["2024-01-02", "2024-01-03"])),
        )


def test_run_all_folds_refactor_is_noop(monkeypatch):
    def fake_run_single_fold(**kwargs):
        fid = kwargs["fold_id"]
        return {
            "Baseline": {
                "annualized_sharpe": 0.5 + fid,
                "max_drawdown": -0.1,
                "total_return": 0.2,
                "n_days": 10,
            },
            "Hybrid": {
                "annualized_sharpe": 0.6 + fid,
                "max_drawdown": -0.09,
                "total_return": 0.25,
                "n_days": 10,
            },
        }

    monkeypatch.setattr(bhr, "run_single_fold", fake_run_single_fold)
    fold_specs = [
        {
            "fold_id": idx,
            "train_idx": np.array([0]),
            "test_dates": np.array(pd.to_datetime([f"2024-01-0{idx+1}"])),
            "ts_index": pd.DatetimeIndex(pd.to_datetime([f"2024-01-0{idx+1}"])),
            "feat_df": pd.DataFrame(),
            "tickers": ["AAA"],
            "capital": 1.0,
            "config": {},
            "output_tag": "",
            "dynamic_schedule": None,
            "precomputed_lag_cols": None,
            "pred_lag_df": None,
            "close_pivot_full": None,
            "model_type": "lightgbm",
            "top_k": 1,
            "concentrated_hysteresis": 0,
        }
        for idx in range(2)
    ]
    agg = bhr.aggregate_fold_results(bhr.run_all_folds(fold_specs, 2, workers=1))
    assert agg["Baseline"]["per_fold_sharpe"] == pytest.approx([0.5, 1.5])
    assert agg["Hybrid"]["per_fold_sharpe"] == pytest.approx([0.6, 1.6])


def test_sweep_reuses_baseline_hybrid():
    fold_specs = [{"fold_id": 1, "conformal_cfg": {}}]

    def fake_run_all_folds(specs, total, workers=1):
        mode = specs[0].get("conformal_cfg", {}).get("mode")
        return [{
            "Baseline": {
                "annualized_sharpe": 1.0,
                "max_drawdown": -0.1,
                "total_return": 0.1,
                "n_days": 10,
            },
            "Hybrid": {
                "annualized_sharpe": 1.2,
                "max_drawdown": -0.09,
                "total_return": 0.12,
                "n_days": 10,
            },
            "Conformal": {
                "annualized_sharpe": 1.3 if mode == "size" else 1.4,
                "max_drawdown": -0.08,
                "total_return": 0.14,
                "n_days": 10,
            },
        }]

    result = sweep.sweep_from_fold_runner(fold_specs, 1, fake_run_all_folds)
    baseline_rows = [row for row in result["rows"] if row["scenario"] == "Baseline"]
    hybrid_rows = [row for row in result["rows"] if row["scenario"] == "Hybrid"]
    assert len({row["mean_sharpe"] for row in baseline_rows}) == 1
    assert len({row["mean_sharpe"] for row in hybrid_rows}) == 1


def test_sweep_output_schema():
    fold_specs = [{"fold_id": 1, "conformal_cfg": {}}]

    def fake_run_all_folds(specs, total, workers=1):
        return [{
            "Baseline": {
                "annualized_sharpe": 1.0,
                "max_drawdown": -0.1,
                "total_return": 0.1,
                "n_days": 10,
            },
            "Hybrid": {
                "annualized_sharpe": 1.2,
                "max_drawdown": -0.09,
                "total_return": 0.12,
                "n_days": 10,
            },
            "Conformal": {
                "annualized_sharpe": 1.4,
                "max_drawdown": -0.08,
                "total_return": 0.14,
                "n_days": 10,
            },
        }]

    result = sweep.sweep_from_fold_runner(fold_specs, 1, fake_run_all_folds)
    assert {"conformal_alpha", "conf_floor", "mode", "scenario", "per_fold_sharpe"}.issubset(result["rows"][0])
    assert "per_fold_sharpe" in result["nested"]["grid"][0]["aggregated"]["Conformal"]


def test_paired_delta_sign():
    stats = sweep.paired_stats([1.3, 1.4, 1.5, 1.6], [1.0, 1.1, 1.2, 1.3])
    assert stats["median_delta"] > 0
    assert stats["sign_test_p"] <= 0.125
