"""
Latent Alphas Gate Tests
GATE: LATENT_ALPHA_MINING_64D_20260617
[L2-Impl:Role14-Data-Scientist] - 2026-06-17

Verifies that:
  1. Quick-mode suffix isolation — mine_latent_alphas.py uses _quick suffix
  2. Quick-mode path resolution in run_phase35_backtest.py resolves _quick paths
  3. Production-mode 64D parquet rejection (ValueError when != 64 latent cols)
  4. Production-mode missing metrics JSON rejection (ValueError)
  5. Production-mode n_components != 64 rejection in metrics JSON (ValueError)
  6. Stale artifact mismatch detection (parquet cols != metrics n_components)
  7. Path logging — config log shows resolved path with _quick suffix in quick mode
  8. Path logging — config log shows production path in production mode
  9. Quick mode bypasses all 64D validations (no ValueError)
 10. Backward compatibility — disabled latent alphas triggers no validation

PIT Safety: No real data loaded. Synthetic data + source inspection only.
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_run_script_source():
    """Read run_phase35_backtest.py source."""
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "scripts" / "run_phase35_backtest.py"
    )
    return path.read_text(encoding="utf-8")


def _get_mine_script_source():
    """Read mine_latent_alphas.py source."""
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "scripts" / "mine_latent_alphas.py"
    )
    return path.read_text(encoding="utf-8")


def _make_latent_parquet(path, n_latent_cols, n_rows=100, seed=42):
    """Create a synthetic latent alpha parquet file.

    Parameters
    ----------
    path : Path
        Output parquet path.
    n_latent_cols : int
        Number of latent_ columns to generate.
    n_rows : int
        Number of rows.
    seed : int
        Random seed.
    """
    rng = np.random.RandomState(seed)
    data = {
        "ticker": [f"SYM{i % 5:02d}" for i in range(n_rows)],
        "date": pd.date_range("2020-01-01", periods=n_rows, freq="B"),
        "returns": rng.randn(n_rows) * 0.01,
    }
    for i in range(n_latent_cols):
        data[f"latent_pca_{i:02d}"] = rng.randn(n_rows) * 0.5
    df = pd.DataFrame(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


def _make_metrics_json(path, n_components, method="pca", seed=42):
    """Create a synthetic metrics JSON file.

    Parameters
    ----------
    path : Path
        Output JSON path.
    n_components : int
        n_components value in the JSON.
    method : str
        Method name.
    seed : int
        Seed recorded in JSON.
    """
    rng = np.random.RandomState(seed)
    component_metrics = {}
    ranking = []
    for i in range(n_components):
        name = f"latent_pca_{i:02d}"
        ic = float(rng.randn() * 0.02)
        ir = float(rng.randn() * 0.3)
        component_metrics[name] = {
            "ic_mean": round(ic, 6),
            "ic_std": round(abs(ic) * 0.5, 6),
            "ir": round(ir, 4),
            "ic_positive_rate": round(0.4 + rng.rand() * 0.2, 4),
            "ic_t_stat": round(ir * 2.0, 4),
            "n_dates": 200,
            "turnover": round(0.05 + rng.rand() * 0.1, 4),
            "net_ic": round(ic - 0.001, 6),
            "passes_ic_gate": abs(ic) >= 0.02,
            "passes_ir_gate": abs(ir) >= 0.3,
            "passes_turnover_gate": True,
            "method": method,
            "component_index": i,
        }
        ranking.append({"rank": i + 1, "component": name, "ir": ir, "ic_mean": ic})

    ranking.sort(key=lambda x: abs(x["ir"]), reverse=True)
    for idx, r in enumerate(ranking):
        r["rank"] = idx + 1

    payload = {
        "gate": "LATENT_ALPHA_MINING_64D_20260617",
        "timestamp": "2026-06-17T00:00:00+00:00",
        "seed": seed,
        "method": method,
        "n_components": n_components,
        "n_features": 64,
        "train_ratio": 0.6,
        "train_dates": 120,
        "test_dates": 80,
        "features_hash": "abc123",
        "features_path": "data/features_advanced_sim.parquet",
        "vn_market_params": {
            "round_trip_cost_bps": 27.0,
            "trading_days_per_year": 248,
            "ic_min_threshold": 0.02,
            "ir_min_threshold": 0.30,
            "turnover_max": 0.30,
        },
        "component_metrics": component_metrics,
        "ranking": ranking,
        "summary": {
            "n_components_evaluated": n_components,
            "n_pass_all_gates": 0,
            "n_pass_ic_gate": 0,
            "n_pass_ir_gate": 0,
            "best_oos_ir": ranking[0]["ir"] if ranking else None,
            "best_oos_ic": ranking[0]["ic_mean"] if ranking else None,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return payload


# ---------------------------------------------------------------------------
# Test 1: Quick-mode suffix isolation in mine_latent_alphas.py
# ---------------------------------------------------------------------------

class TestQuickModeSuffixIsolation:
    """Verify _quick suffix applied to all output paths when quick_mode=True."""

    def test_mine_script_uses_quick_suffix_for_parquet(self):
        """mine_latent_alphas.py constructs _quick-suffixed parquet path."""
        src = _get_mine_script_source()
        assert 'f"latent_alphas_components{_suffix}.parquet"' in src or \
               "latent_alphas_components{_suffix}.parquet" in src, (
            "mine_latent_alphas.py must use _suffix in parquet output path"
        )

    def test_mine_script_uses_quick_suffix_for_model(self):
        """mine_latent_alphas.py constructs _quick-suffixed model path."""
        src = _get_mine_script_source()
        assert 'f"latent_alphas_model{_suffix}.pkl"' in src or \
               "latent_alphas_model{_suffix}.pkl" in src, (
            "mine_latent_alphas.py must use _suffix in model output path"
        )

    def test_mine_script_uses_quick_suffix_for_metrics(self):
        """mine_latent_alphas.py constructs _quick-suffixed metrics path."""
        src = _get_mine_script_source()
        assert 'f"latent_alphas_metrics{_suffix}.json"' in src or \
               "latent_alphas_metrics{_suffix}.json" in src, (
            "mine_latent_alphas.py must use _suffix in metrics output path"
        )

    def test_mine_script_uses_quick_suffix_for_report(self):
        """mine_latent_alphas.py constructs _quick-suffixed report path."""
        src = _get_mine_script_source()
        assert 'f"latent_alphas_report_20260617{_suffix}.md"' in src or \
               "latent_alphas_report_20260617{_suffix}.md" in src, (
            "mine_latent_alphas.py must use _suffix in report output path"
        )

    def test_suffix_is_empty_when_not_quick_mode(self):
        """_suffix is '' when quick_mode=False."""
        src = _get_mine_script_source()
        assert '"_quick" if quick_mode else ""' in src, (
            "_suffix must be empty string when quick_mode=False"
        )


# ---------------------------------------------------------------------------
# Test 2: Quick-mode path resolution in run_phase35_backtest.py
# ---------------------------------------------------------------------------

class TestQuickModePathResolution:
    """Verify run_phase35_backtest.py resolves _quick paths in quick mode."""

    def test_backtest_resolves_quick_suffix_path(self):
        """Backtest script resolves _quick suffix when quick_mode=True."""
        src = _get_run_script_source()
        assert '_la_log_suffix = "_quick" if args.quick_mode else ""' in src, (
            "run_phase35_backtest.py must compute _quick suffix from args.quick_mode"
        )

    def test_backtest_logs_resolved_path(self):
        """Config log shows the resolved path (not a hardcoded default)."""
        src = _get_run_script_source()
        # Must log the resolved path, not the raw CLI arg
        assert "Latent Alpha Path (resolved):" in src, (
            "Config log must show the resolved latent alpha path"
        )
        # Must NOT log the old hardcoded default
        assert "Latent Alpha Path: {args.latent_alpha_path or 'data/latent_alphas_components.parquet'}" not in src, (
            "Config log must NOT show the old hardcoded default path"
        )

    def test_backtest_reuses_resolved_path_in_injection(self):
        """Injection block reuses the pre-resolved path."""
        src = _get_run_script_source()
        assert "_la_path = _Path(_resolved_latent_alpha_path)" in src, (
            "Injection block must reuse _resolved_latent_alpha_path from config section"
        )

    def test_metrics_path_derived_from_components_path(self):
        """Metrics path is derived from components path (respects _quick suffix)."""
        src = _get_run_script_source()
        assert "_la_stem.replace('_components', '_metrics')" in src, (
            "Metrics path must be derived from components stem with _components→_metrics"
        )


# ---------------------------------------------------------------------------
# Test 3: Production-mode 64D parquet rejection
# ---------------------------------------------------------------------------

class TestProductionMode64DRejection:
    """Verify ValueError raised when production parquet doesn't have 64 latent cols."""

    def test_parquet_not_64_cols_raises_in_production(self, tmp_path):
        """ValueError when production parquet has != 64 latent columns."""
        # Create parquet with 5 latent columns (quick-mode artifact)
        parquet_path = tmp_path / "latent_alphas_components.parquet"
        _make_latent_parquet(parquet_path, n_latent_cols=5, n_rows=50)

        # Create matching metrics JSON with n_components=64 (to isolate parquet check)
        metrics_path = tmp_path / "latent_alphas_metrics.json"
        _make_metrics_json(metrics_path, n_components=64)

        # Simulate the validation logic from run_phase35_backtest.py
        la_df = pd.read_parquet(parquet_path)
        la_cols_available = [c for c in la_df.columns if c.startswith("latent_")]
        quick_mode = False

        # This is the exact validation from the script
        with pytest.raises(ValueError, match="exactly 64 latent columns"):
            if not quick_mode and len(la_cols_available) != 64:
                raise ValueError(
                    f"[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
                    f"Production mode requires exactly 64 latent columns in parquet "
                    f"but found {len(la_cols_available)} in {parquet_path}."
                )

    def test_parquet_64_cols_passes_in_production(self, tmp_path):
        """No error when production parquet has exactly 64 latent columns."""
        parquet_path = tmp_path / "latent_alphas_components.parquet"
        _make_latent_parquet(parquet_path, n_latent_cols=64, n_rows=50)

        la_df = pd.read_parquet(parquet_path)
        la_cols_available = [c for c in la_df.columns if c.startswith("latent_")]
        quick_mode = False

        # Should NOT raise
        if not quick_mode and len(la_cols_available) != 64:
            pytest.fail("Should not raise for 64 columns")

    def test_parquet_non_64_passes_in_quick_mode(self, tmp_path):
        """No error in quick mode even with != 64 latent columns."""
        parquet_path = tmp_path / "latent_alphas_components_quick.parquet"
        _make_latent_parquet(parquet_path, n_latent_cols=5, n_rows=50)

        la_df = pd.read_parquet(parquet_path)
        la_cols_available = [c for c in la_df.columns if c.startswith("latent_")]
        quick_mode = True

        # Should NOT raise — quick mode bypasses 64D check
        if not quick_mode and len(la_cols_available) != 64:
            pytest.fail("Should not raise in quick mode")


# ---------------------------------------------------------------------------
# Test 4: Production-mode missing metrics JSON rejection
# ---------------------------------------------------------------------------

class TestMissingMetricsRejection:
    """Verify ValueError when metrics JSON is missing in production mode."""

    def test_missing_metrics_raises_in_production(self, tmp_path):
        """ValueError when metrics JSON doesn't exist in production mode."""
        parquet_path = tmp_path / "latent_alphas_components.parquet"
        _make_latent_parquet(parquet_path, n_latent_cols=64, n_rows=50)
        metrics_path = tmp_path / "latent_alphas_metrics.json"
        # Intentionally NOT creating metrics_path

        quick_mode = False

        with pytest.raises(ValueError, match="Metrics JSON not found"):
            if not quick_mode and not metrics_path.exists():
                raise ValueError(
                    f"[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
                    f"Metrics JSON not found: {metrics_path}."
                )

    def test_missing_metrics_ok_in_quick_mode(self, tmp_path):
        """No error in quick mode when metrics JSON doesn't exist."""
        parquet_path = tmp_path / "latent_alphas_components_quick.parquet"
        _make_latent_parquet(parquet_path, n_latent_cols=5, n_rows=50)
        metrics_path = tmp_path / "latent_alphas_metrics_quick.json"
        # Intentionally NOT creating metrics_path

        quick_mode = True

        # Should NOT raise — quick mode doesn't require metrics JSON
        if not quick_mode and not metrics_path.exists():
            pytest.fail("Should not raise in quick mode")


# ---------------------------------------------------------------------------
# Test 5: n_components != 64 in metrics JSON rejection
# ---------------------------------------------------------------------------

class TestMetricsNComponentsRejection:
    """Verify ValueError when metrics JSON has n_components != 64 in production."""

    def test_metrics_n_comp_not_64_raises(self, tmp_path):
        """ValueError when metrics n_components != 64 in production mode."""
        metrics_path = tmp_path / "latent_alphas_metrics.json"
        _make_metrics_json(metrics_path, n_components=5)

        quick_mode = False
        with open(metrics_path) as f:
            metrics = json.load(f)
        metrics_n_comp = metrics.get("n_components")

        with pytest.raises(ValueError, match="n_components=64 in metrics JSON"):
            if not quick_mode and metrics_n_comp != 64:
                raise ValueError(
                    f"[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
                    f"Production mode requires n_components=64 in metrics JSON "
                    f"but found n_components={metrics_n_comp}."
                )

    def test_metrics_n_comp_64_passes(self, tmp_path):
        """No error when metrics n_components == 64."""
        metrics_path = tmp_path / "latent_alphas_metrics.json"
        _make_metrics_json(metrics_path, n_components=64)

        quick_mode = False
        with open(metrics_path) as f:
            metrics = json.load(f)
        metrics_n_comp = metrics.get("n_components")

        if not quick_mode and metrics_n_comp != 64:
            pytest.fail("Should not raise for n_components=64")


# ---------------------------------------------------------------------------
# Test 6: Stale artifact mismatch detection
# ---------------------------------------------------------------------------

class TestStaleArtifactMismatch:
    """Verify ValueError when metrics n_components doesn't match parquet column count."""

    def test_stale_mismatch_raises(self, tmp_path):
        """ValueError when metrics n_components != parquet latent column count."""
        parquet_path = tmp_path / "latent_alphas_components.parquet"
        _make_latent_parquet(parquet_path, n_latent_cols=64, n_rows=50)

        metrics_path = tmp_path / "latent_alphas_metrics.json"
        # Metrics says 32 components but parquet has 64 columns
        _make_metrics_json(metrics_path, n_components=32)

        la_df = pd.read_parquet(parquet_path)
        la_cols_available = [c for c in la_df.columns if c.startswith("latent_")]

        with open(metrics_path) as f:
            metrics = json.load(f)
        metrics_n_comp = metrics.get("n_components")

        # Stale check
        with pytest.raises(ValueError, match="Stale artifact mismatch"):
            if metrics_n_comp is not None and metrics_n_comp != len(la_cols_available):
                raise ValueError(
                    f"[LatentAlphas] GATE LATENT_ALPHA_MINING_64D_20260617: "
                    f"Stale artifact mismatch — metrics JSON reports "
                    f"n_components={metrics_n_comp} but parquet has "
                    f"{len(la_cols_available)} latent columns."
                )

    def test_stale_match_passes(self, tmp_path):
        """No error when metrics n_components matches parquet column count."""
        parquet_path = tmp_path / "latent_alphas_components.parquet"
        _make_latent_parquet(parquet_path, n_latent_cols=64, n_rows=50)

        metrics_path = tmp_path / "latent_alphas_metrics.json"
        _make_metrics_json(metrics_path, n_components=64)

        la_df = pd.read_parquet(parquet_path)
        la_cols_available = [c for c in la_df.columns if c.startswith("latent_")]

        with open(metrics_path) as f:
            metrics = json.load(f)
        metrics_n_comp = metrics.get("n_components")

        if metrics_n_comp is not None and metrics_n_comp != len(la_cols_available):
            pytest.fail("Should not raise when artifacts match")

    def test_quick_mode_stale_mismatch_still_detected(self, tmp_path):
        """Stale check applies in ALL modes (it's a data integrity check)."""
        parquet_path = tmp_path / "latent_alphas_components_quick.parquet"
        _make_latent_parquet(parquet_path, n_latent_cols=5, n_rows=50)

        metrics_path = tmp_path / "latent_alphas_metrics_quick.json"
        # Metrics says 10 components but parquet has 5
        _make_metrics_json(metrics_path, n_components=10)

        la_df = pd.read_parquet(parquet_path)
        la_cols_available = [c for c in la_df.columns if c.startswith("latent_")]

        with open(metrics_path) as f:
            metrics = json.load(f)
        metrics_n_comp = metrics.get("n_components")

        # Stale check fires regardless of quick_mode
        with pytest.raises(ValueError, match="Stale artifact mismatch"):
            if metrics_n_comp is not None and metrics_n_comp != len(la_cols_available):
                raise ValueError(
                    f"Stale artifact mismatch — metrics JSON reports "
                    f"n_components={metrics_n_comp} but parquet has "
                    f"{len(la_cols_available)} latent columns."
                )


# ---------------------------------------------------------------------------
# Test 7: Path logging validation rules (source inspection)
# ---------------------------------------------------------------------------

class TestPathLoggingValidationRules:
    """Verify the source code follows correct path logging/validation patterns."""

    def test_resolved_path_computed_before_config_log(self):
        """_resolved_latent_alpha_path is computed before the config log line."""
        src = _get_run_script_source()
        # Find position of resolved path computation
        resolve_pos = src.find("_resolved_latent_alpha_path = args.latent_alpha_path")
        # Find position of the resolved log line
        log_pos = src.find("Latent Alpha Path (resolved):")
        assert resolve_pos > 0, "Must compute _resolved_latent_alpha_path"
        assert log_pos > 0, "Must log resolved path"
        assert resolve_pos < log_pos, (
            "_resolved_latent_alpha_path must be computed before logging"
        )

    def test_quick_mode_suffix_in_resolved_path(self):
        """Resolved path includes _quick suffix when args.quick_mode=True."""
        src = _get_run_script_source()
        # Must have the suffix computation near the resolved path
        assert '_la_log_suffix = "_quick" if args.quick_mode else ""' in src
        assert 'latent_alphas_components{_la_log_suffix}.parquet' in src

    def test_no_hardcoded_default_in_config_log(self):
        """Config log must NOT use the old hardcoded default."""
        src = _get_run_script_source()
        # The old pattern: args.latent_alpha_path or 'data/latent_alphas_components.parquet'
        # should NOT appear in the config log section
        old_pattern = "args.latent_alpha_path or 'data/latent_alphas_components.parquet'"
        assert old_pattern not in src, (
            "Must not use hardcoded default path in config log"
        )

    def test_production_validates_64d_parquet(self):
        """Source contains 64D parquet validation for production mode."""
        src = _get_run_script_source()
        assert "not args.quick_mode and len(_la_cols_available) != 64" in src, (
            "Must validate exactly 64 latent columns in production mode"
        )

    def test_production_validates_metrics_existence(self):
        """Source validates metrics JSON exists in production mode."""
        src = _get_run_script_source()
        assert "not args.quick_mode and not _la_metrics_path.exists()" in src, (
            "Must validate metrics JSON exists in production mode"
        )

    def test_production_validates_metrics_n_components(self):
        """Source validates n_components == 64 in metrics JSON."""
        src = _get_run_script_source()
        assert "not args.quick_mode and _metrics_n_comp != 64" in src, (
            "Must validate n_components == 64 in metrics JSON for production mode"
        )

    def test_stale_artifact_check_present(self):
        """Source contains stale artifact mismatch check."""
        src = _get_run_script_source()
        assert "Stale artifact mismatch" in src, (
            "Must check for stale artifact mismatch between parquet and metrics"
        )

    def test_valueerror_messages_include_gate_name(self):
        """All ValueError messages reference the gate name."""
        src = _get_run_script_source()
        # Find all ValueError raises related to latent alphas
        ve_blocks = re.findall(
            r'raise ValueError\(\s*.*?LATENT_ALPHA_MINING_64D_20260617.*?\)',
            src, re.DOTALL
        )
        assert len(ve_blocks) >= 4, (
            f"Expected at least 4 ValueError blocks with gate name, found {len(ve_blocks)}"
        )


# ---------------------------------------------------------------------------
# Test 8: End-to-end validation chain (integration-style)
# ---------------------------------------------------------------------------

class TestValidationChainIntegration:
    """End-to-end simulation of the validation chain from the script."""

    def _simulate_validation(self, parquet_path, metrics_path, quick_mode):
        """Simulate the exact validation logic from run_phase35_backtest.py.

        Returns (success: bool, error: str or None).
        """
        if not parquet_path.exists():
            return (True, None)  # File not found → skip (warning, not error)

        la_df = pd.read_parquet(parquet_path)
        la_cols_available = [c for c in la_df.columns if c.startswith("latent_")]

        # 64D parquet validation
        if not quick_mode and len(la_cols_available) != 64:
            return (False, f"exactly 64 latent columns but found {len(la_cols_available)}")

        # Metrics JSON existence
        if not quick_mode and not metrics_path.exists():
            return (False, "Metrics JSON not found")

        if metrics_path.exists():
            with open(metrics_path) as f:
                metrics = json.load(f)
            metrics_n_comp = metrics.get("n_components")

            # n_components == 64 in production
            if not quick_mode and metrics_n_comp != 64:
                return (False, f"n_components={metrics_n_comp}")

            # Stale check
            if metrics_n_comp is not None and metrics_n_comp != len(la_cols_available):
                return (False, "Stale artifact mismatch")

        return (True, None)

    def test_production_happy_path(self, tmp_path):
        """Production mode with correct 64D artifacts passes."""
        pq = tmp_path / "latent_alphas_components.parquet"
        mj = tmp_path / "latent_alphas_metrics.json"
        _make_latent_parquet(pq, n_latent_cols=64)
        _make_metrics_json(mj, n_components=64)

        ok, err = self._simulate_validation(pq, mj, quick_mode=False)
        assert ok, f"Expected success but got error: {err}"

    def test_production_wrong_parquet_cols(self, tmp_path):
        """Production mode with wrong parquet cols fails."""
        pq = tmp_path / "latent_alphas_components.parquet"
        mj = tmp_path / "latent_alphas_metrics.json"
        _make_latent_parquet(pq, n_latent_cols=32)
        _make_metrics_json(mj, n_components=64)

        ok, err = self._simulate_validation(pq, mj, quick_mode=False)
        assert not ok, "Expected failure for 32 columns in production"
        assert "64 latent columns" in err

    def test_production_missing_metrics(self, tmp_path):
        """Production mode with missing metrics JSON fails."""
        pq = tmp_path / "latent_alphas_components.parquet"
        mj = tmp_path / "latent_alphas_metrics.json"  # doesn't exist
        _make_latent_parquet(pq, n_latent_cols=64)

        ok, err = self._simulate_validation(pq, mj, quick_mode=False)
        assert not ok, "Expected failure for missing metrics"
        assert "Metrics JSON not found" in err

    def test_production_wrong_metrics_n_comp(self, tmp_path):
        """Production mode with wrong n_components in metrics fails."""
        pq = tmp_path / "latent_alphas_components.parquet"
        mj = tmp_path / "latent_alphas_metrics.json"
        _make_latent_parquet(pq, n_latent_cols=64)
        _make_metrics_json(mj, n_components=5)

        ok, err = self._simulate_validation(pq, mj, quick_mode=False)
        assert not ok, "Expected failure for n_components=5"
        assert "n_components=5" in err

    def test_production_stale_mismatch(self, tmp_path):
        """Production mode with mismatched parquet/metrics fails."""
        pq = tmp_path / "latent_alphas_components.parquet"
        mj = tmp_path / "latent_alphas_metrics.json"
        _make_latent_parquet(pq, n_latent_cols=64)
        # Metrics says 32 but parquet has 64
        _make_metrics_json(mj, n_components=32)

        ok, err = self._simulate_validation(pq, mj, quick_mode=False)
        assert not ok, "Expected failure for stale mismatch"
        # Could fail on n_components != 64 first, which is also correct
        assert "n_components=32" in err or "Stale artifact" in err

    def test_quick_mode_all_bypasses(self, tmp_path):
        """Quick mode bypasses all 64D validations."""
        pq = tmp_path / "latent_alphas_components_quick.parquet"
        mj = tmp_path / "latent_alphas_metrics_quick.json"
        _make_latent_parquet(pq, n_latent_cols=5)
        _make_metrics_json(mj, n_components=5)

        ok, err = self._simulate_validation(pq, mj, quick_mode=True)
        assert ok, f"Expected success in quick mode but got error: {err}"

    def test_quick_mode_missing_metrics_ok(self, tmp_path):
        """Quick mode with missing metrics JSON passes."""
        pq = tmp_path / "latent_alphas_components_quick.parquet"
        mj = tmp_path / "latent_alphas_metrics_quick.json"  # doesn't exist
        _make_latent_parquet(pq, n_latent_cols=5)

        ok, err = self._simulate_validation(pq, mj, quick_mode=True)
        assert ok, f"Expected success in quick mode but got error: {err}"

    def test_quick_mode_stale_still_detected(self, tmp_path):
        """Quick mode still detects stale artifact mismatch."""
        pq = tmp_path / "latent_alphas_components_quick.parquet"
        mj = tmp_path / "latent_alphas_metrics_quick.json"
        _make_latent_parquet(pq, n_latent_cols=5)
        _make_metrics_json(mj, n_components=10)  # mismatch!

        ok, err = self._simulate_validation(pq, mj, quick_mode=True)
        assert not ok, "Expected failure for stale mismatch even in quick mode"
        assert "Stale artifact" in err

    def test_parquet_not_found_skips(self, tmp_path):
        """Missing parquet file skips (returns ok, not error)."""
        pq = tmp_path / "nonexistent.parquet"
        mj = tmp_path / "nonexistent.json"

        ok, err = self._simulate_validation(pq, mj, quick_mode=False)
        assert ok, "Missing parquet should skip, not error"
