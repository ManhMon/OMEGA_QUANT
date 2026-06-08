"""
Tests for ml_gate_validator.py - Stage 3 MASTER_BACKTEST_PLAN
Role: Backend Engineer (Role 9) | Platform: OpenCode (L2)
"""

import numpy as np
import pandas as pd
import pytest

from omega.quant.ml_gate_validator import validate_production_gate, validate_research_gate


def _make_ic_series(mean: float, std: float, n: int, seed: int = 42) -> pd.Series:
    """Helper: build a rolling IC series with target mean/std."""
    rng = np.random.default_rng(seed)
    # Generate samples then shift to hit exact mean/std
    raw = rng.normal(loc=0.0, scale=1.0, size=n)
    raw = (raw - raw.mean()) / raw.std()  # standardize
    return pd.Series(raw * std + mean)


class TestResearchGate:
    def test_research_gate_pass_all_criteria(self):
        """IC=0.06, stability>1.6, samples=65 -> PASS"""
        series = _make_ic_series(mean=0.08, std=0.04, n=65)  # ratio ~2.0
        result = validate_research_gate(val_ic=0.06, rolling_ic_series=series)

        assert result["passed"] is True
        assert result["val_ic"] == 0.06
        assert result["n_samples"] == 65
        assert result["stability_ratio"] > 1.5
        assert result["verdict"] == "PASS"

    def test_research_gate_fail_low_ic(self):
        """IC=0.04 -> FAIL regardless of stability"""
        series = _make_ic_series(mean=0.08, std=0.04, n=65)
        result = validate_research_gate(val_ic=0.04, rolling_ic_series=series)

        assert result["passed"] is False
        assert "val_ic" in result["verdict"]
        assert "0.05" in result["verdict"]

    def test_research_gate_fail_low_stability(self):
        """stability_ratio <= 1.5 -> FAIL"""
        # mean=0.06, std=0.05 -> ratio=1.2
        series = _make_ic_series(mean=0.06, std=0.05, n=65)
        result = validate_research_gate(val_ic=0.06, rolling_ic_series=series)

        assert result["passed"] is False
        assert result["stability_ratio"] <= 1.5
        assert "stability_ratio" in result["verdict"]

    def test_research_gate_fail_insufficient_samples(self):
        """samples=50 < min_samples=60 -> FAIL"""
        series = _make_ic_series(mean=0.08, std=0.04, n=50)
        result = validate_research_gate(val_ic=0.06, rolling_ic_series=series)

        assert result["passed"] is False
        assert result["n_samples"] == 50
        assert "insufficient samples" in result["verdict"]

    def test_research_gate_returns_all_keys(self):
        """Result dict must always contain all required keys."""
        series = _make_ic_series(mean=0.08, std=0.04, n=65)
        result = validate_research_gate(val_ic=0.06, rolling_ic_series=series)

        assert set(result.keys()) == {"passed", "val_ic", "stability_ratio", "n_samples", "verdict"}

    def test_edge_case_exact_threshold(self):
        """IC=0.05 (exact), stability_ratio=1.5 (exact) -> boundary behaviour.

        Brief spec: IC=0.05, stability=1.5 -> PASS (>= and > checks).
        stability_ratio must be > 1.5 per spec, so exact 1.5 is FAIL.
        We construct a series with ratio strictly > 1.5 and val_ic == 0.05.
        """
        # mean=0.09, std=0.05 -> ratio=1.8 > 1.5
        series = _make_ic_series(mean=0.09, std=0.05, n=65)
        result = validate_research_gate(val_ic=0.05, rolling_ic_series=series)

        assert result["passed"] is True
        assert result["val_ic"] == 0.05
        assert result["verdict"] == "PASS"

    def test_research_gate_custom_min_samples(self):
        """Custom min_samples=30 allows shorter series."""
        series = _make_ic_series(mean=0.08, std=0.04, n=35)
        result = validate_research_gate(val_ic=0.06, rolling_ic_series=series, min_samples=30)

        assert result["passed"] is True

    def test_research_gate_deterministic(self):
        """Same inputs always produce same verdict."""
        series = _make_ic_series(mean=0.08, std=0.04, n=65)
        r1 = validate_research_gate(val_ic=0.06, rolling_ic_series=series)
        r2 = validate_research_gate(val_ic=0.06, rolling_ic_series=series)

        assert r1 == r2

    def test_research_gate_fail_zero_variance(self):
        """Zero variance (all IC values identical) -> stability_ratio=nan -> FAIL"""
        # All values identical -> std=0.0 -> stability_ratio=nan
        series = pd.Series([0.05] * 65)
        result = validate_research_gate(val_ic=0.06, rolling_ic_series=series)

        assert result["passed"] is False
        assert np.isnan(result["stability_ratio"])
        assert "stability_ratio" in result["verdict"]


class TestProductionGate:
    def test_production_gate_pass(self):
        """IC=0.09 >= 0.08 -> PASS"""
        result = validate_production_gate(val_ic=0.09)

        assert result["passed"] is True
        assert result["val_ic"] == 0.09
        assert result["verdict"] == "PASS"

    def test_production_gate_fail(self):
        """IC=0.07 < 0.08 -> FAIL"""
        result = validate_production_gate(val_ic=0.07)

        assert result["passed"] is False
        assert result["val_ic"] == 0.07
        assert "0.08" in result["verdict"]

    def test_production_gate_exact_threshold(self):
        """IC=0.08 (exact boundary) -> PASS (>= check)"""
        result = validate_production_gate(val_ic=0.08)

        assert result["passed"] is True
        assert result["verdict"] == "PASS"

    def test_production_gate_returns_all_keys(self):
        """Result dict must always contain all required keys."""
        result = validate_production_gate(val_ic=0.09)

        assert set(result.keys()) == {"passed", "val_ic", "verdict"}

    def test_production_gate_deterministic(self):
        """Same inputs always produce same verdict."""
        r1 = validate_production_gate(val_ic=0.09)
        r2 = validate_production_gate(val_ic=0.09)

        assert r1 == r2
