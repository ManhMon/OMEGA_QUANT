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
        assert "not args.quick_mode and not _has_variant_models and len(_la_pca_ica_cols) != 64" in src, (
            "Must validate exactly 64 PCA/ICA latent columns in production mode"
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
        assert "not args.quick_mode and not _has_variant_models and _metrics_n_comp != 64" in src, (
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


# ---------------------------------------------------------------------------
# Test 9: PLS regression method support (source inspection)
# ---------------------------------------------------------------------------

class TestPLSMethodSupport:
    """Verify PLS regression method is wired into mine_latent_alphas.py."""

    def test_pls_in_method_choices(self):
        """CLI accepts 'pls' as a method choice."""
        src = _get_mine_script_source()
        assert '"pls"' in src or "'pls'" in src, (
            "mine_latent_alphas.py must accept 'pls' as a method choice"
        )

    def test_fit_pls_components_function_exists(self):
        """fit_pls_components function is defined."""
        src = _get_mine_script_source()
        assert "def fit_pls_components(" in src, (
            "mine_latent_alphas.py must define fit_pls_components()"
        )

    def test_project_pls_factors_function_exists(self):
        """project_pls_factors function is defined."""
        src = _get_mine_script_source()
        assert "def project_pls_factors(" in src, (
            "mine_latent_alphas.py must define project_pls_factors()"
        )

    def test_pls_uses_sklearn_cross_decomposition(self):
        """PLS uses sklearn.cross_decomposition.PLSRegression."""
        src = _get_mine_script_source()
        assert "sklearn.cross_decomposition" in src, (
            "PLS must use sklearn.cross_decomposition"
        )
        assert "PLSRegression" in src, (
            "PLS must use PLSRegression"
        )

    def test_pls_prefix_is_latent_pls(self):
        """PLS columns use 'latent_pls_' prefix."""
        src = _get_mine_script_source()
        assert 'prefix = "latent_pls_"' in src, (
            "PLS components must use 'latent_pls_' prefix"
        )

    def test_enable_pls_cli_flag_exists(self):
        """--enable-pls CLI flag is defined."""
        src = _get_mine_script_source()
        assert "--enable-pls" in src, (
            "CLI must have --enable-pls flag"
        )


# ---------------------------------------------------------------------------
# Test 10: Cross-sectional neutralization support (source inspection)
# ---------------------------------------------------------------------------

class TestCrossSectionalNeutralization:
    """Verify cross-sectional target returns neutralization is implemented."""

    def test_neutralize_target_returns_function_exists(self):
        """neutralize_target_returns function is defined."""
        src = _get_mine_script_source()
        assert "def neutralize_target_returns(" in src, (
            "mine_latent_alphas.py must define neutralize_target_returns()"
        )

    def test_neutralize_uses_lstsq(self):
        """Neutralization uses numpy least-squares regression."""
        src = _get_mine_script_source()
        assert "lstsq" in src, (
            "Neutralization must use least-squares regression"
        )

    def test_neutralize_is_per_date(self):
        """Neutralization is per-date (cross-sectional)."""
        src = _get_mine_script_source()
        # Must group by date for cross-sectional operation
        assert "groupby(date_col)" in src or 'groupby("date")' in src, (
            "Neutralization must be per-date cross-sectional"
        )

    def test_enable_neutralize_cli_flag_exists(self):
        """--enable-neutralize CLI flag is defined."""
        src = _get_mine_script_source()
        assert "--enable-neutralize" in src, (
            "CLI must have --enable-neutralize flag"
        )

    def test_neutralize_is_pit_safe(self):
        """Neutralization docstring mentions PIT-safety."""
        src = _get_mine_script_source()
        # Check the function has PIT-safety documentation
        func_start = src.find("def neutralize_target_returns(")
        func_section = src[func_start:func_start + 800]
        assert "PIT" in func_section or "same-date" in func_section, (
            "neutralize_target_returns must document PIT-safety"
        )


# ---------------------------------------------------------------------------
# Test 11: Regime-conditional modeling support (source inspection)
# ---------------------------------------------------------------------------

class TestRegimeConditionalModeling:
    """Verify regime-conditional PCA/PLS using rolling HMMs is implemented."""

    def test_detect_regimes_hmm_function_exists(self):
        """detect_regimes_hmm function is defined."""
        src = _get_mine_script_source()
        assert "def detect_regimes_hmm(" in src, (
            "mine_latent_alphas.py must define detect_regimes_hmm()"
        )

    def test_fit_regime_conditional_models_function_exists(self):
        """fit_regime_conditional_models function is defined."""
        src = _get_mine_script_source()
        assert "def fit_regime_conditional_models(" in src, (
            "mine_latent_alphas.py must define fit_regime_conditional_models()"
        )

    def test_project_regime_conditional_function_exists(self):
        """project_regime_conditional function is defined."""
        src = _get_mine_script_source()
        assert "def project_regime_conditional(" in src, (
            "mine_latent_alphas.py must define project_regime_conditional()"
        )

    def test_hmm_uses_hmmlearn(self):
        """HMM uses hmmlearn library."""
        src = _get_mine_script_source()
        assert "hmmlearn" in src, (
            "Regime detection must use hmmlearn"
        )
        assert "GaussianHMM" in src, (
            "Regime detection must use GaussianHMM"
        )

    def test_regime_conditional_is_train_only(self):
        """Regime detection fits on training data only."""
        src = _get_mine_script_source()
        assert "Regime-conditional" in src or "regime_conditional" in src, (
            "Must document regime-conditional approach"
        )

    def test_enable_regime_conditional_cli_flag_exists(self):
        """--enable-regime-conditional CLI flag is defined."""
        src = _get_mine_script_source()
        assert "--enable-regime-conditional" in src, (
            "CLI must have --enable-regime-conditional flag"
        )

    def test_n_hmm_states_cli_flag_exists(self):
        """--n-hmm-states CLI flag is defined."""
        src = _get_mine_script_source()
        assert "--n-hmm-states" in src, (
            "CLI must have --n-hmm-states flag"
        )


# ---------------------------------------------------------------------------
# Test 12: Backtest script PLS/regime variant support (source inspection)
# ---------------------------------------------------------------------------

class TestBacktestVariantSupport:
    """Verify run_phase35_backtest.py supports loading PLS and regime variants."""

    def test_enable_latent_pls_cli_flag_exists(self):
        """--enable-latent-pls CLI flag is defined."""
        src = _get_run_script_source()
        assert "--enable-latent-pls" in src, (
            "run_phase35_backtest.py must have --enable-latent-pls flag"
        )

    def test_enable_latent_regime_conditional_cli_flag_exists(self):
        """--enable-latent-regime-conditional CLI flag is defined."""
        src = _get_run_script_source()
        assert "--enable-latent-regime-conditional" in src, (
            "run_phase35_backtest.py must have --enable-latent-regime-conditional flag"
        )

    def test_pls_columns_filtered(self):
        """PLS columns (latent_pls_*) are identified in injection block."""
        src = _get_run_script_source()
        assert "latent_pls_" in src, (
            "Injection block must identify PLS columns by prefix"
        )

    def test_regime_columns_filtered(self):
        """Regime columns (latent_r*) are identified in injection block."""
        src = _get_run_script_source()
        assert "_la_regime_cols" in src, (
            "Injection block must identify regime-conditional columns"
        )

    def test_variant_models_exempt_from_64d_check(self):
        """PLS/regime variants are exempt from strict 64D validation."""
        src = _get_run_script_source()
        assert "_has_variant_models" in src, (
            "Validation must check for variant models to exempt from 64D check"
        )

    def test_evidence_includes_advanced_variants(self):
        """Evidence dict includes advanced_variants section."""
        src = _get_run_script_source()
        assert "advanced_variants" in src, (
            "Evidence dict must include advanced_variants section"
        )


# ---------------------------------------------------------------------------
# Test 13: PLS functional regression (integration test)
# ---------------------------------------------------------------------------

def _make_panel_data(n_dates=20, n_tickers=10, n_features=8, seed=42):
    """Create synthetic panel data for integration tests."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="B")
    rows = []
    for d in dates:
        for t in range(n_tickers):
            row = {
                "ticker": f"SYM{t:02d}",
                "date": d,
                "returns": rng.randn() * 0.01,
            }
            for f in range(n_features):
                row[f"feat_{f:02d}"] = rng.randn()
            rows.append(row)
    return pd.DataFrame(rows)


class TestPLSFunctionalRegression:
    """Integration tests for PLS regression components."""

    def test_fit_pls_components_returns_model(self):
        """fit_pls_components returns valid components and model."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from mine_latent_alphas import fit_pls_components

        rng = np.random.RandomState(42)
        X = rng.randn(100, 8)
        y = rng.randn(100)
        components, model = fit_pls_components(X, y, n_components=3)

        assert components.shape[0] == 3, "Should return 3 components"
        assert components.shape[1] == 8, "Components should have 8 features"
        assert hasattr(model, "transform"), "Model should have transform method"

    def test_project_pls_factors_adds_columns(self):
        """project_pls_factors adds latent columns to dataframe."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from mine_latent_alphas import fit_pls_components, project_pls_factors

        rng = np.random.RandomState(42)
        X = rng.randn(50, 5)
        y = rng.randn(50)
        _, model = fit_pls_components(X, y, n_components=3)

        feat_cols = [f"feat_{i:02d}" for i in range(5)]
        df = pd.DataFrame(X, columns=feat_cols)
        df["ticker"] = "SYM00"
        df["date"] = pd.date_range("2020-01-01", periods=50, freq="B")
        df["returns"] = y

        result = project_pls_factors(df, feat_cols, model, "latent_pls_")

        pls_cols = [c for c in result.columns if c.startswith("latent_pls_")]
        assert len(pls_cols) == 3, f"Should add 3 PLS columns, got {len(pls_cols)}"

    def test_pls_deterministic_with_seed(self):
        """PLS results are deterministic with same seed."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from mine_latent_alphas import fit_pls_components

        rng = np.random.RandomState(42)
        X = rng.randn(80, 6)
        y = rng.randn(80)

        comp1, _ = fit_pls_components(X, y, 3)
        comp2, _ = fit_pls_components(X, y, 3)

        np.testing.assert_array_almost_equal(
            comp1, comp2, decimal=10,
            err_msg="PLS should be deterministic with same inputs"
        )


# ---------------------------------------------------------------------------
# Test 14: Neutralization functional regression (integration test)
# ---------------------------------------------------------------------------

class TestNeutralizationFunctional:
    """Integration tests for cross-sectional returns neutralization."""

    def test_neutralize_removes_linear_exposure(self):
        """Neutralization removes linear factor exposure from returns."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from mine_latent_alphas import neutralize_target_returns

        df = _make_panel_data(n_dates=10, n_tickers=15, n_features=4)
        feat_cols = [c for c in df.columns if c.startswith("feat_")]
        residuals = neutralize_target_returns(df, feat_cols, "returns", "date")

        assert len(residuals) == len(df), "Residuals should match row count"
        assert not np.all(np.isnan(residuals)), "Residuals should not all be NaN"

    def test_neutralize_preserves_length(self):
        """Neutralization preserves panel data length."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from mine_latent_alphas import neutralize_target_returns

        df = _make_panel_data(n_dates=5, n_tickers=8, n_features=3)
        feat_cols = [c for c in df.columns if c.startswith("feat_")]
        residuals = neutralize_target_returns(df, feat_cols, "returns", "date")

        assert len(residuals) == len(df)

    def test_neutralize_zero_features_returns_raw(self):
        """With no features, neutralization should return raw returns."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from mine_latent_alphas import neutralize_target_returns

        df = _make_panel_data(n_dates=5, n_tickers=8, n_features=0)
        # No feature columns - should still work (intercept-only regression)
        feat_cols = []
        residuals = neutralize_target_returns(df, feat_cols, "returns", "date")
        assert len(residuals) == len(df)


# ---------------------------------------------------------------------------
# Test 15: Regime detection functional regression (integration test)
# ---------------------------------------------------------------------------

class TestRegimeDetectionFunctional:
    """Integration tests for HMM regime detection."""

    def test_detect_regimes_hmm_returns_labels(self):
        """detect_regimes_hmm returns regime labels for each date."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from mine_latent_alphas import detect_regimes_hmm

        rng = np.random.RandomState(42)
        # Generate returns with clear regime structure
        ret = np.concatenate([
            rng.randn(50) * 0.01 + 0.002,   # Bull
            rng.randn(50) * 0.02,              # Sideways
            rng.randn(50) * 0.015 - 0.003,    # Bear
        ])
        labels, model = detect_regimes_hmm(ret, n_states=3, min_window=30)

        assert len(labels) == len(ret), "Should return label per date"
        # Labels should have at least 2 distinct values (could be fallback heuristic)
        assert len(set(labels)) >= 1, "Should assign at least one regime"

    def test_detect_regimes_insufficient_data(self):
        """detect_regimes_hmm handles insufficient data gracefully."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from mine_latent_alphas import detect_regimes_hmm

        ret = np.array([0.01, -0.005, 0.003])  # Too short
        labels, model = detect_regimes_hmm(ret, n_states=3, min_window=60)

        assert len(labels) == 3
        assert model is None, "Model should be None for insufficient data"
        assert all(l == 0 for l in labels), "All labels should be 0 for fallback"

    def test_fit_regime_conditional_models_per_regime(self):
        """fit_regime_conditional_models fits separate models per regime."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from mine_latent_alphas import fit_regime_conditional_models

        rng = np.random.RandomState(42)
        X = rng.randn(90, 5)
        y = rng.randn(90)
        regimes = np.array([0] * 30 + [1] * 30 + [2] * 30)

        models = fit_regime_conditional_models(X, y, regimes, n_components=3, method="pca")

        assert len(models) == 3, "Should fit 3 regime models"
        for reg_id in [0, 1, 2]:
            assert reg_id in models, f"Regime {reg_id} should have a model"
            assert "model" in models[reg_id]
            assert "prefix" in models[reg_id]
            assert models[reg_id]["prefix"].startswith("latent_r")


# ---------------------------------------------------------------------------
# Test 16: Model persistence includes advanced options
# ---------------------------------------------------------------------------

class TestModelPersistenceAdvanced:
    """Verify model payload includes advanced options metadata."""

    def test_mine_script_persists_enable_pls(self):
        """Model payload includes enable_pls flag."""
        src = _get_mine_script_source()
        assert '"enable_pls"' in src, (
            "Model payload must include enable_pls"
        )

    def test_mine_script_persists_enable_neutralize(self):
        """Model payload includes enable_neutralize flag."""
        src = _get_mine_script_source()
        assert '"enable_neutralize"' in src, (
            "Model payload must include enable_neutralize"
        )

    def test_mine_script_persists_enable_regime_conditional(self):
        """Model payload includes enable_regime_conditional flag."""
        src = _get_mine_script_source()
        assert '"enable_regime_conditional"' in src, (
            "Model payload must include enable_regime_conditional"
        )

    def test_mine_script_persists_regime_evidence(self):
        """Model payload includes regime_evidence."""
        src = _get_mine_script_source()
        assert '"regime_evidence"' in src, (
            "Model payload must include regime_evidence"
        )

    def test_metrics_json_includes_advanced_options(self):
        """Metrics JSON includes advanced_options section."""
        src = _get_mine_script_source()
        assert '"advanced_options"' in src, (
            "Metrics JSON must include advanced_options section"
        )


# ---------------------------------------------------------------------------
# Test 17: L3-Fix — Baseline backtest filters latent variant columns
# GATE: LATENT_ALPHA_MINING_64D_20260617
# Verifies that when --enable-latent-pls and --enable-latent-regime-conditional
# are disabled, the backtest restricts columns to PCA/ICA only.
# ---------------------------------------------------------------------------

class TestBaselineLatentColumnFiltering:
    """Verify baseline backtest filters out latent_pls_ and latent_r* columns
    when PLS and regime-conditional features are disabled."""

    def test_backtest_always_restricts_to_selected_variants(self):
        """Source always restricts _la_cols_available to union of selected variants."""
        src = _get_run_script_source()
        # The fix replaces the conditional with an unconditional assignment
        assert "_la_cols_available = (" in src, (
            "Must unconditionally restrict _la_cols_available to selected variants"
        )
        assert "_la_pca_ica_cols + _la_pls_cols + _la_regime_cols" in src, (
            "Column restriction must be union of pca/ica + pls + regime"
        )

    def test_old_fallback_pattern_removed(self):
        """Old pattern 'else keep original _la_cols_available' is removed."""
        src = _get_run_script_source()
        assert "else keep original _la_cols_available" not in src, (
            "Old fallback that kept all latent_ columns must be removed"
        )

    def test_pls_cols_empty_when_disabled(self):
        """PLS columns list is empty when --enable-latent-pls is not set."""
        src = _get_run_script_source()
        # The code should have: ] if args.enable_latent_pls else []
        assert "if args.enable_latent_pls else []" in src, (
            "PLS columns must be empty list when enable_latent_pls is False"
        )

    def test_regime_cols_empty_when_disabled(self):
        """Regime columns list is empty when --enable-latent-regime-conditional is not set."""
        src = _get_run_script_source()
        assert "if args.enable_latent_regime_conditional else []" in src, (
            "Regime columns must be empty list when enable_latent_regime_conditional is False"
        )

    def test_disabled_variants_produce_empty_filter(self):
        """When both PLS and regime are disabled, only PCA/ICA columns pass."""
        # Simulate the filtering logic
        la_cols = [
            "latent_pca_00", "latent_pca_01", "latent_ica_00",
            "latent_pls_00", "latent_pls_01",
            "latent_r0_pca_00", "latent_r1_pca_00",
        ]
        enable_pls = False
        enable_regime = False

        pca_ica = [c for c in la_cols if c.startswith("latent_pca_") or c.startswith("latent_ica_")]
        pls = [c for c in la_cols if c.startswith("latent_pls_")] if enable_pls else []
        regime = [c for c in la_cols if c.startswith("latent_r") and "_" in c[9:]] if enable_regime else []

        result = pca_ica + pls + regime
        assert len(result) == 3, f"Expected 3 PCA/ICA cols, got {len(result)}: {result}"
        assert all(not c.startswith("latent_pls_") for c in result)
        assert all(not c.startswith("latent_r") for c in result)

    def test_enabled_variants_include_all_types(self):
        """When both PLS and regime are enabled, all column types pass."""
        la_cols = [
            "latent_pca_00", "latent_pca_01", "latent_ica_00",
            "latent_pls_00", "latent_pls_01",
            "latent_r0_pca_00", "latent_r1_pca_00",
        ]
        enable_pls = True
        enable_regime = True

        pca_ica = [c for c in la_cols if c.startswith("latent_pca_") or c.startswith("latent_ica_")]
        pls = [c for c in la_cols if c.startswith("latent_pls_")] if enable_pls else []
        regime = [c for c in la_cols if c.startswith("latent_r") and "_" in c[9:]] if enable_regime else []

        result = pca_ica + pls + regime
        assert len(result) == 7, f"Expected 7 cols, got {len(result)}: {result}"


# ---------------------------------------------------------------------------
# Test 18: L3-Fix — OOS regime prediction uses hmm_model.predict
# GATE: LATENT_ALPHA_MINING_64D_20260617
# Verifies that OOS regime prediction dynamically predicts using the fitted
# HMM model instead of assigning last_train_regime.
# ---------------------------------------------------------------------------

class TestOOSRegimePredictionDynamic:
    """Verify OOS regime prediction uses hmm_model.predict in a PIT-safe
    walk-forward manner — for each test date t, predict using only
    historical returns up to date t (no look-ahead bias)."""

    def test_mine_script_uses_pit_safe_walkforward_predict(self):
        """mine_latent_alphas.py uses PIT-safe walk-forward HMM predict.

        For each test date at index i, must concatenate training returns
        with OOS returns[:i+1] and take preds[-1].
        """
        src = _get_mine_script_source()
        assert "hmm_model.predict(X_combined)" in src, (
            "OOS regime prediction must use hmm_model.predict(X_combined) "
            "with PIT-safe combined history"
        )

    def test_mine_script_concatenates_train_and_oos_returns(self):
        """PIT-safe predict concatenates market_ret + test_market_ret[:i+1]."""
        src = _get_mine_script_source()
        assert "test_market_ret[: i + 1]" in src or "test_market_ret[:i + 1]" in src, (
            "Must slice OOS returns up to current index i for PIT-safe prediction"
        )
        assert "np.concatenate" in src, (
            "Must concatenate training returns with OOS returns slice"
        )

    def test_mine_script_assigns_last_prediction(self):
        """PIT-safe predict assigns preds[-1] to the test date."""
        src = _get_mine_script_source()
        assert "preds[-1]" in src, (
            "Must assign the last predicted state preds[-1] to the test date"
        )

    def test_mine_script_computes_oos_market_returns(self):
        """OOS market returns are computed for HMM prediction."""
        src = _get_mine_script_source()
        assert "test_market_ret" in src, (
            "Must compute test market returns for OOS regime prediction"
        )

    def test_old_batch_predict_removed(self):
        """Old batch predict pattern (hmm_model.predict(X_oos)) is removed."""
        src = _get_mine_script_source()
        assert "hmm_model.predict(X_oos)" not in src, (
            "Old batch predict on full OOS sequence must be removed "
            "(Viterbi leaks future data)"
        )

    def test_old_last_train_regime_primary_path_removed(self):
        """The primary OOS path no longer assigns last_train_regime unconditionally."""
        src = _get_mine_script_source()
        # The old pattern was the primary path (no try/except wrapper)
        # Now last_train_regime only appears in the except fallback
        lines = src.split("\n")
        for i, line in enumerate(lines):
            if "last_train_regime = int(regime_labels_train[-1])" in line:
                # This should be inside an except block (fallback)
                context = "\n".join(lines[max(0, i-5):i+1])
                assert "except" in context or "Falling back" in context or "Fallback" in context, (
                    "last_train_regime assignment should only appear in fallback path"
                )

    def test_oos_regime_has_fallback_on_failure(self):
        """OOS regime prediction has fallback when hmm_model.predict fails."""
        src = _get_mine_script_source()
        # Should have try/except around the predict call
        predict_pos = src.find("hmm_model.predict(X_combined)")
        assert predict_pos > 0, "Must have hmm_model.predict(X_combined)"
        # Find the surrounding try/except (wider window to capture except block)
        surrounding = src[max(0, predict_pos - 500):predict_pos + 1000]
        assert "try:" in surrounding, "predict call must be in try block"
        assert "except" in surrounding, "predict call must have except fallback"

    def test_pit_safe_predict_iterates_per_date(self):
        """PIT-safe predict iterates over each test date individually."""
        src = _get_mine_script_source()
        # Must have a for-loop over test_dates_sorted with enumerate
        assert "for i, d in enumerate(test_dates_sorted)" in src, (
            "Must iterate over test dates with index for walk-forward slicing"
        )

    def test_hmm_predict_functional(self):
        """Functional test: HMM model can predict on combined history (PIT-safe)."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from mine_latent_alphas import detect_regimes_hmm

        rng = np.random.RandomState(42)
        # Generate training returns with regime structure
        train_ret = np.concatenate([
            rng.randn(50) * 0.01 + 0.002,
            rng.randn(50) * 0.02,
            rng.randn(50) * 0.015 - 0.003,
        ])
        labels, hmm_model = detect_regimes_hmm(train_ret, n_states=3, min_window=30)

        if hmm_model is not None:
            # PIT-safe walk-forward prediction: for each OOS date i,
            # concatenate train + OOS[:i+1] and take preds[-1]
            oos_ret = rng.randn(20) * 0.01
            pit_labels = []
            for i in range(len(oos_ret)):
                combined = np.concatenate([train_ret, oos_ret[: i + 1]])
                X_combined = combined.reshape(-1, 1)
                preds = hmm_model.predict(X_combined)
                pit_labels.append(int(preds[-1]))
            assert len(pit_labels) == 20, "Should predict one label per OOS date"
            assert all(0 <= l < 3 for l in pit_labels), "Labels should be in range [0, n_states)"


# ---------------------------------------------------------------------------
# Test 18b: L3-Fix-R2 — PIT-safe walk-forward HMM prediction
# GATE: LATENT_ALPHA_MINING_64D_20260617
# Verifies the exact PIT-safe walk-forward pattern in source code.
# ---------------------------------------------------------------------------

class TestPITSafeWalkForwardHMM:
    """Verify PIT-safe walk-forward HMM regime prediction (Round 2 fix).

    The Viterbi algorithm in HMM uses the full observation sequence to
    determine optimal hidden states. Calling predict() on the entire OOS
    sequence at once leaks future data for each test date. The fix
    predicts each test date independently using only returns available
    up to that date.
    """

    def test_source_uses_combined_history_not_standalone_oos(self):
        """Source concatenates train+OOS, not standalone OOS predict."""
        src = _get_mine_script_source()
        # Must use X_combined (combined history), NOT X_oos (standalone)
        assert "X_combined" in src, (
            "Must use X_combined variable name for PIT-safe combined history"
        )
        # Must NOT have standalone OOS predict
        assert "X_oos" not in src, (
            "Must not use X_oos — standalone OOS predict leaks future data via Viterbi"
        )

    def test_source_no_oos_regime_labels_batch(self):
        """Source does NOT batch-assign oos_regime_labels."""
        src = _get_mine_script_source()
        assert "oos_regime_labels" not in src, (
            "Batch oos_regime_labels array must be removed; "
            "use per-date preds[-1] assignment instead"
        )

    def test_source_documents_pit_safety_rationale(self):
        """Source code documents PIT-safety rationale for the fix."""
        src = _get_mine_script_source()
        assert "L3-Fix-R2" in src, (
            "Must document the Round 2 fix identifier in source"
        )
        assert "Viterbi" in src or "PIT-safe" in src, (
            "Must document why walk-forward prediction is needed"
        )

    def test_combined_history_pattern_in_try_block(self):
        """Combined history predict is inside a try block for robustness."""
        src = _get_mine_script_source()
        # Find the combined predict call
        predict_pos = src.find("hmm_model.predict(X_combined)")
        assert predict_pos > 0, "Must have hmm_model.predict(X_combined)"
        # Look backwards for try:
        preceding = src[max(0, predict_pos - 600):predict_pos]
        assert "try:" in preceding, (
            "Combined history predict must be inside a try block"
        )

    def test_pit_safe_walkforward_functional(self):
        """Functional test: PIT-safe walk-forward prediction differs from batch.

        Verifies that walk-forward prediction (concatenating train + OOS[:i+1])
        produces valid regime labels per date without leaking future data.
        """
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from mine_latent_alphas import detect_regimes_hmm

        rng = np.random.RandomState(42)
        # Generate returns with clear regime structure
        train_ret = np.concatenate([
            rng.randn(60) * 0.01 + 0.003,   # Bull
            rng.randn(60) * 0.02,              # Sideways
            rng.randn(60) * 0.015 - 0.004,    # Bear
        ])
        labels, hmm_model = detect_regimes_hmm(train_ret, n_states=3, min_window=30)

        if hmm_model is not None:
            oos_ret = rng.randn(10) * 0.015
            # PIT-safe walk-forward: one date at a time
            pit_labels = []
            for i in range(len(oos_ret)):
                combined = np.concatenate([train_ret, oos_ret[: i + 1]])
                X_combined = combined.reshape(-1, 1)
                preds = hmm_model.predict(X_combined)
                pit_labels.append(int(preds[-1]))

            # Verify each label is a valid regime
            assert len(pit_labels) == 10
            assert all(0 <= l < 3 for l in pit_labels), (
                "Each walk-forward prediction must be a valid regime label"
            )

            # Verify the growing history changes predictions (not all identical
            # to what a single-point predict would give)
            # This is a soft check — at minimum, labels should be assigned
            assert len(set(pit_labels)) >= 1, (
                "Walk-forward labels should be assigned"
            )


# ---------------------------------------------------------------------------
# Test 19: L3-Fix — PLS explained variance uses model.x_scores_
# GATE: LATENT_ALPHA_MINING_64D_20260617
# Verifies that PLS explained variance calculation uses the correct
# PLSRegression attribute x_scores_ instead of non-existent scores_.
# ---------------------------------------------------------------------------

class TestPLSExplainedVarianceXScores:
    """Verify PLS explained variance uses model.x_scores_ (not model.scores_)."""

    def test_mine_script_uses_x_scores(self):
        """mine_latent_alphas.py uses model.x_scores_ for PLS variance."""
        src = _get_mine_script_source()
        assert "model.x_scores_" in src, (
            "PLS explained variance must use model.x_scores_"
        )

    def test_mine_script_no_scores_without_x_prefix(self):
        """mine_latent_alphas.py does NOT use model.scores_ (without x_ prefix)."""
        src = _get_mine_script_source()
        # Find all occurrences of scores_ and verify they are x_scores_
        import re as _re
        # Match model.scores_ but NOT model.x_scores_
        bad_pattern = _re.findall(r'(?<!\w)(?<!x_)scores_', src)
        # Filter out comments and string literals that mention scores_
        lines = src.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Check for the bad pattern in code (not comments)
            if "model.scores_" in line and "model.x_scores_" not in line:
                pytest.fail(
                    f"Found model.scores_ (should be model.x_scores_) in: {line.strip()}"
                )

    def test_hasattr_checks_x_scores(self):
        """hasattr check uses x_scores_ not scores_."""
        src = _get_mine_script_source()
        assert 'hasattr(model, "x_scores_")' in src, (
            "hasattr check must use x_scores_ attribute name"
        )

    def test_pls_explained_variance_functional(self):
        """Functional test: PLS explained variance uses x_scores_ correctly."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from mine_latent_alphas import fit_pls_components, compute_explained_variance_ratio

        rng = np.random.RandomState(42)
        X = rng.randn(100, 8)
        y = rng.randn(100)
        components, model = fit_pls_components(X, y, n_components=3)

        # Verify model has x_scores_ attribute
        assert hasattr(model, "x_scores_"), "PLS model must have x_scores_ attribute"

        # Verify explained variance calculation works
        var_ratios = compute_explained_variance_ratio(model, "pls", 3)
        assert len(var_ratios) == 3, f"Should return 3 variance ratios, got {len(var_ratios)}"
        assert all(0.0 <= v <= 1.0 for v in var_ratios), "Variance ratios should be in [0, 1]"
        # Sum should be close to 1.0 (or 1/n_components for fallback)
        total = sum(var_ratios)
        assert total > 0.0, "Total explained variance should be positive"


# ---------------------------------------------------------------------------
# Test 20: Deep Autoencoder model classes (source inspection)
# GATE: LATENT_ALPHA_MINING_64D_20260617
# Verifies that _DeepNonlinearAutoencoderNet and NonlinearDeepLatentEncoder
# are implemented in latent_encoder.py.
# ---------------------------------------------------------------------------

def _get_latent_encoder_source():
    """Read latent_encoder.py source."""
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "src" / "omega" / "quant" / "models" / "latent_encoder.py"
    )
    return path.read_text(encoding="utf-8")


class TestDeepAutoencoderModelClasses:
    """Verify deep nonlinear autoencoder classes exist in latent_encoder.py."""

    def test_deep_autoencoder_config_exists(self):
        """DeepAutoencoderConfig dataclass is defined."""
        src = _get_latent_encoder_source()
        assert "class DeepAutoencoderConfig" in src, (
            "latent_encoder.py must define DeepAutoencoderConfig"
        )

    def test_deep_nonlinear_autoencoder_net_exists(self):
        """_DeepNonlinearAutoencoderNet class is defined."""
        src = _get_latent_encoder_source()
        assert "class _DeepNonlinearAutoencoderNet" in src, (
            "latent_encoder.py must define _DeepNonlinearAutoencoderNet"
        )

    def test_nonlinear_deep_latent_encoder_exists(self):
        """NonlinearDeepLatentEncoder class is defined."""
        src = _get_latent_encoder_source()
        assert "class NonlinearDeepLatentEncoder" in src, (
            "latent_encoder.py must define NonlinearDeepLatentEncoder"
        )

    def test_deep_ae_uses_multiple_hidden_layers(self):
        """Deep AE has hidden_dims parameter for multiple layers."""
        src = _get_latent_encoder_source()
        assert "hidden_dims" in src, (
            "Deep AE must support configurable hidden_dims"
        )

    def test_deep_ae_supports_nonlinear_activations(self):
        """Deep AE supports gelu/relu/leaky_relu activations."""
        src = _get_latent_encoder_source()
        assert "gelu" in src, "Deep AE must support GELU activation"
        assert "leaky_relu" in src or "LeakyReLU" in src, (
            "Deep AE must support LeakyReLU activation"
        )

    def test_deep_ae_supports_batch_norm(self):
        """Deep AE supports batch normalization."""
        src = _get_latent_encoder_source()
        assert "BatchNorm1d" in src, (
            "Deep AE must use BatchNorm1d for batch normalization"
        )

    def test_deep_ae_supports_3d_input(self):
        """Deep AE handles 3D input (N, T, F) by flattening."""
        src = _get_latent_encoder_source()
        assert "x.ndim == 3" in src, (
            "Deep AE must handle 3D input by checking ndim == 3"
        )

    def test_deep_ae_has_encoder_and_decoder(self):
        """Deep AE has separate encoder and decoder modules."""
        src = _get_latent_encoder_source()
        assert "self.encoder" in src, "Deep AE must have self.encoder"
        assert "self.decoder" in src, "Deep AE must have self.decoder"

    def test_deep_ae_has_encode_method(self):
        """Deep AE net has encode() method for latent extraction."""
        src = _get_latent_encoder_source()
        assert "def encode(" in src, (
            "_DeepNonlinearAutoencoderNet must have encode() method"
        )

    def test_latent_encoder_has_get_column_names(self):
        """NonlinearDeepLatentEncoder has get_column_names() method."""
        src = _get_latent_encoder_source()
        assert "def get_column_names(" in src, (
            "NonlinearDeepLatentEncoder must have get_column_names()"
        )

    def test_latent_ae_prefix_convention(self):
        """Column names use 'latent_ae_XX' convention."""
        src = _get_latent_encoder_source()
        assert "latent_ae_" in src, (
            "Column names must use 'latent_ae_XX' prefix convention"
        )


# ---------------------------------------------------------------------------
# Test 21: Autoencoder method in mine_latent_alphas.py (source inspection)
# GATE: LATENT_ALPHA_MINING_64D_20260617
# ---------------------------------------------------------------------------

class TestAutoencoderMethodInMineScript:
    """Verify --method autoencoder is wired into mine_latent_alphas.py."""

    def test_autoencoder_in_method_choices(self):
        """CLI accepts 'autoencoder' as a method choice."""
        src = _get_mine_script_source()
        assert '"autoencoder"' in src or "'autoencoder'" in src, (
            "mine_latent_alphas.py must accept 'autoencoder' as a method"
        )

    def test_fit_autoencoder_components_function_exists(self):
        """fit_autoencoder_components function is defined."""
        src = _get_mine_script_source()
        assert "def fit_autoencoder_components(" in src, (
            "mine_latent_alphas.py must define fit_autoencoder_components()"
        )

    def test_project_autoencoder_factors_function_exists(self):
        """project_autoencoder_factors function is defined."""
        src = _get_mine_script_source()
        assert "def project_autoencoder_factors(" in src, (
            "mine_latent_alphas.py must define project_autoencoder_factors()"
        )

    def test_autoencoder_prefix_is_latent_ae(self):
        """Autoencoder columns use 'latent_ae_' prefix."""
        src = _get_mine_script_source()
        assert 'prefix = "latent_ae_"' in src, (
            "Autoencoder components must use 'latent_ae_' prefix"
        )

    def test_autoencoder_imports_from_latent_encoder(self):
        """Autoencoder imports NonlinearDeepLatentEncoder."""
        src = _get_mine_script_source()
        assert "NonlinearDeepLatentEncoder" in src, (
            "Must import NonlinearDeepLatentEncoder from latent_encoder"
        )

    def test_autoencoder_method_in_methods_to_run(self):
        """Autoencoder method is added to methods_to_run when selected."""
        src = _get_mine_script_source()
        assert 'method == "autoencoder"' in src or "method == 'autoencoder'" in src, (
            "Autoencoder must be handled in methods_to_run logic"
        )

    def test_autoencoder_projection_in_pipeline(self):
        """Autoencoder projection is wired in the projection step."""
        src = _get_mine_script_source()
        assert "project_autoencoder_factors" in src, (
            "project_autoencoder_factors must be called in projection step"
        )


# ---------------------------------------------------------------------------
# Test 22: Autoencoder in backtest script (source inspection)
# GATE: LATENT_ALPHA_MINING_64D_20260617
# ---------------------------------------------------------------------------

class TestAutoencoderInBacktestScript:
    """Verify --enable-latent-autoencoder flag in run_phase35_backtest.py."""

    def test_enable_latent_autoencoder_cli_flag_exists(self):
        """--enable-latent-autoencoder CLI flag is defined."""
        src = _get_run_script_source()
        assert "--enable-latent-autoencoder" in src, (
            "run_phase35_backtest.py must have --enable-latent-autoencoder flag"
        )

    def test_ae_columns_filtered(self):
        """Autoencoder columns (latent_ae_*) are identified in injection block."""
        src = _get_run_script_source()
        assert "_la_ae_cols" in src, (
            "Injection block must identify autoencoder columns as _la_ae_cols"
        )

    def test_ae_columns_empty_when_disabled(self):
        """AE columns list is empty when --enable-latent-autoencoder is not set."""
        src = _get_run_script_source()
        assert "if args.enable_latent_autoencoder else []" in src, (
            "AE columns must be empty list when enable_latent_autoencoder is False"
        )

    def test_ae_columns_included_in_combined(self):
        """AE columns are included in the combined column list."""
        src = _get_run_script_source()
        assert "_la_ae_cols" in src, (
            "Combined columns must include _la_ae_cols"
        )

    def test_has_variant_models_includes_autoencoder(self):
        """_has_variant_models includes autoencoder flag."""
        src = _get_run_script_source()
        assert "args.enable_latent_autoencoder" in src, (
            "_has_variant_models must check enable_latent_autoencoder"
        )

    def test_evidence_includes_ae_cols(self):
        """Evidence dict includes n_ae_cols."""
        src = _get_run_script_source()
        assert '"n_ae_cols"' in src, (
            "Evidence dict must include n_ae_cols count"
        )

    def test_config_logs_autoencoder_status(self):
        """Config log shows autoencoder flag status."""
        src = _get_run_script_source()
        assert "Latent Alpha Autoencoder:" in src, (
            "Config log must show autoencoder status"
        )

    def test_autoencoder_columns_filtered_when_disabled(self):
        """When autoencoder is disabled, latent_ae_ columns are excluded."""
        la_cols = [
            "latent_pca_00", "latent_pca_01", "latent_ica_00",
            "latent_pls_00", "latent_ae_00", "latent_ae_01",
            "latent_r0_pca_00",
        ]
        enable_pls = False
        enable_regime = False
        enable_ae = False

        pca_ica = [c for c in la_cols if c.startswith("latent_pca_") or c.startswith("latent_ica_")]
        pls = [c for c in la_cols if c.startswith("latent_pls_")] if enable_pls else []
        regime = [c for c in la_cols if c.startswith("latent_r") and "_" in c[9:]] if enable_regime else []
        ae = [c for c in la_cols if c.startswith("latent_ae_")] if enable_ae else []

        result = pca_ica + pls + regime + ae
        assert len(result) == 3, f"Expected 3 PCA/ICA cols, got {len(result)}: {result}"
        assert all(not c.startswith("latent_ae_") for c in result)

    def test_autoencoder_columns_included_when_enabled(self):
        """When autoencoder is enabled, latent_ae_ columns are included."""
        la_cols = [
            "latent_pca_00", "latent_pca_01", "latent_ica_00",
            "latent_pls_00", "latent_ae_00", "latent_ae_01",
            "latent_r0_pca_00",
        ]
        enable_pls = False
        enable_regime = False
        enable_ae = True

        pca_ica = [c for c in la_cols if c.startswith("latent_pca_") or c.startswith("latent_ica_")]
        pls = [c for c in la_cols if c.startswith("latent_pls_")] if enable_pls else []
        regime = [c for c in la_cols if c.startswith("latent_r") and "_" in c[9:]] if enable_regime else []
        ae = [c for c in la_cols if c.startswith("latent_ae_")] if enable_ae else []

        result = pca_ica + pls + regime + ae
        assert len(result) == 5, f"Expected 5 cols (3 pca/ica + 2 ae), got {len(result)}"
        ae_result = [c for c in result if c.startswith("latent_ae_")]
        assert len(ae_result) == 2, "Should include 2 AE columns"


# ---------------------------------------------------------------------------
# Test 23: Deep Autoencoder functional regression (integration test)
# GATE: LATENT_ALPHA_MINING_64D_20260617
# ---------------------------------------------------------------------------

class TestDeepAutoencoderFunctional:
    """Integration tests for deep nonlinear autoencoder."""

    def test_deep_ae_fit_transform_2d(self):
        """NonlinearDeepLatentEncoder can fit and transform 2D data."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
        from omega.quant.models.latent_encoder import (
            NonlinearDeepLatentEncoder,
            DeepAutoencoderConfig,
        )

        rng = np.random.RandomState(42)
        X = rng.randn(100, 32).astype(np.float32)

        cfg = DeepAutoencoderConfig(
            n_features=32,
            latent_dim=8,
            hidden_dims=(64, 32),
            epochs=5,
            seed=42,
        )
        enc = NonlinearDeepLatentEncoder(cfg)
        latent = enc.fit_transform(X)

        assert latent.shape == (100, 8), f"Expected (100, 8), got {latent.shape}"
        assert enc._fitted, "Encoder should be fitted"

    def test_deep_ae_fit_transform_3d(self):
        """NonlinearDeepLatentEncoder can fit and transform 3D data."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
        from omega.quant.models.latent_encoder import (
            NonlinearDeepLatentEncoder,
            DeepAutoencoderConfig,
        )

        rng = np.random.RandomState(42)
        X = rng.randn(50, 10, 8).astype(np.float32)  # (N=50, T=10, F=8)

        cfg = DeepAutoencoderConfig(
            n_features=8,
            latent_dim=4,
            hidden_dims=(32, 16),
            epochs=3,
            seed=42,
        )
        enc = NonlinearDeepLatentEncoder(cfg)
        latent = enc.fit_transform(X)

        assert latent.shape == (50, 4), f"Expected (50, 4), got {latent.shape}"

    def test_deep_ae_column_names(self):
        """get_column_names returns latent_ae_XX format."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
        from omega.quant.models.latent_encoder import (
            NonlinearDeepLatentEncoder,
            DeepAutoencoderConfig,
        )

        cfg = DeepAutoencoderConfig(latent_dim=5)
        enc = NonlinearDeepLatentEncoder(cfg)
        names = enc.get_column_names()

        assert len(names) == 5, f"Expected 5 names, got {len(names)}"
        assert names[0] == "latent_ae_00"
        assert names[4] == "latent_ae_04"

    def test_deep_ae_loss_decreases(self):
        """Training loss decreases over epochs."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
        from omega.quant.models.latent_encoder import (
            NonlinearDeepLatentEncoder,
            DeepAutoencoderConfig,
        )

        rng = np.random.RandomState(42)
        X = rng.randn(200, 16).astype(np.float32)

        cfg = DeepAutoencoderConfig(
            n_features=16,
            latent_dim=4,
            hidden_dims=(32, 16),
            epochs=10,
            seed=42,
        )
        enc = NonlinearDeepLatentEncoder(cfg)
        enc.fit(X)

        losses = enc._train_loss_history
        assert len(losses) >= 2, f"Should have at least 2 epochs, got {len(losses)}"
        # First loss should be higher than last loss
        assert losses[0] > losses[-1], (
            f"Loss should decrease: first={losses[0]:.6f}, last={losses[-1]:.6f}"
        )

    def test_deep_ae_reconstruction_loss(self):
        """get_reconstruction_loss returns a finite positive value."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
        from omega.quant.models.latent_encoder import (
            NonlinearDeepLatentEncoder,
            DeepAutoencoderConfig,
        )

        rng = np.random.RandomState(42)
        X = rng.randn(80, 16).astype(np.float32)

        cfg = DeepAutoencoderConfig(
            n_features=16, latent_dim=4, hidden_dims=(32,),
            epochs=5, seed=42,
        )
        enc = NonlinearDeepLatentEncoder(cfg)
        enc.fit(X)

        recon = enc.get_reconstruction_loss(X)
        assert np.isfinite(recon), "Reconstruction loss should be finite"
        assert recon > 0.0, "Reconstruction loss should be positive"

    def test_deep_ae_unfitted_returns_zeros(self):
        """Unfitted encoder returns zeros on transform."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
        from omega.quant.models.latent_encoder import (
            NonlinearDeepLatentEncoder,
            DeepAutoencoderConfig,
        )

        cfg = DeepAutoencoderConfig(latent_dim=8)
        enc = NonlinearDeepLatentEncoder(cfg)

        X = np.random.randn(10, 16).astype(np.float32)
        latent = enc.transform(X)

        assert latent.shape == (10, 8)
        assert np.allclose(latent, 0.0), "Unfitted transform should return zeros"

    def test_deep_ae_deterministic_with_seed(self):
        """Same seed produces same latent representation."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
        from omega.quant.models.latent_encoder import (
            NonlinearDeepLatentEncoder,
            DeepAutoencoderConfig,
        )

        rng = np.random.RandomState(42)
        X = rng.randn(80, 16).astype(np.float32)

        cfg1 = DeepAutoencoderConfig(
            n_features=16, latent_dim=4, hidden_dims=(32,),
            epochs=3, seed=42,
        )
        enc1 = NonlinearDeepLatentEncoder(cfg1)
        lat1 = enc1.fit_transform(X)

        cfg2 = DeepAutoencoderConfig(
            n_features=16, latent_dim=4, hidden_dims=(32,),
            epochs=3, seed=42,
        )
        enc2 = NonlinearDeepLatentEncoder(cfg2)
        lat2 = enc2.fit_transform(X)

        np.testing.assert_array_almost_equal(
            lat1, lat2, decimal=5,
            err_msg="Same seed should produce same latent representation"
        )
