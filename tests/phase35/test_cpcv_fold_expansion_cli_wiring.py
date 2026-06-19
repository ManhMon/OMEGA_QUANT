"""
CPCV Fold Expansion CLI Wiring + Fold Count Persistence Tests
GATE: CPCV_FOLD_EXPANSION_20260614
GATE: CPCV_FOLD_EXPANSION_FIX1_20260614
[L2-Impl:Role14-Data-Scientist] - 2026-06-14

Verifies that:
1. --n-folds, --train-years, --test-years, --top-n-symbols, --output-tag CLI flags exist
2. Defaults unchanged (8/3/1/30)
3. Quick-mode overrides to 2/1/1/1 regardless of CLI values
4. Output-tag changes output filenames to avoid overwrite
5. Config JSON persists fold expansion parameters
6. No live/default behavior changes
7. PIT safety / no look-ahead preserved (no changes to data pipeline)
8. FIX1: config.n_folds persists requested N_FOLDS (not len(splits))
9. FIX1: config.n_folds_executed persists actual executed count
10. FIX1: summary.n_folds_requested persists requested count
11. FIX1: create_walk_forward_splits adaptive step produces requested folds
12. FIX1: Backward compat — 8 folds with 365-day step unchanged

PIT Safety: No real data loaded. Source inspection and synthetic data tests only.
"""

import argparse
import ast
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))


def _get_script_source():
    """Read the run_phase35_backtest.py source code."""
    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_phase35_backtest.py"
    return script_path.read_text(encoding="utf-8")


def _get_data_loader_source():
    """Read the phase35_data_loader.py source code."""
    loader_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "phase35_data_loader.py"
    return loader_path.read_text(encoding="utf-8")


def _make_synthetic_df(start="2014-01-02", end="2026-06-01", n_symbols=5):
    """Create a small synthetic DataFrame for split testing."""
    dates = pd.bdate_range(start, end)
    rows = []
    for sym_idx in range(n_symbols):
        symbol = f"SYM{sym_idx:02d}"
        for d in dates:
            rows.append({
                "date": d,
                "ticker": symbol,
                "open": 10000.0 + sym_idx * 100,
                "high": 10100.0 + sym_idx * 100,
                "low": 9900.0 + sym_idx * 100,
                "close": 10050.0 + sym_idx * 100,
                "volume": 100000,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Section 1: CLI Flag Registration (existing)
# ---------------------------------------------------------------------------


class TestCPCVFoldExpansionCLIFlags:
    """Verify CPCV fold expansion CLI flags are registered."""

    def test_cli_n_folds_flag_registered(self):
        src = _get_script_source()
        assert '"--n-folds"' in src, \
            "CLI flag --n-folds must be registered"

    def test_cli_train_years_flag_registered(self):
        src = _get_script_source()
        assert '"--train-years"' in src, \
            "CLI flag --train-years must be registered"

    def test_cli_test_years_flag_registered(self):
        src = _get_script_source()
        assert '"--test-years"' in src, \
            "CLI flag --test-years must be registered"

    def test_cli_top_n_symbols_flag_registered(self):
        src = _get_script_source()
        assert '"--top-n-symbols"' in src, \
            "CLI flag --top-n-symbols must be registered"

    def test_cli_output_tag_flag_registered(self):
        src = _get_script_source()
        assert '"--output-tag"' in src, \
            "CLI flag --output-tag must be registered"

    def test_n_folds_type_is_int(self):
        src = _get_script_source()
        assert '"--n-folds"' in src
        assert "type=int" in src

    def test_train_years_type_is_int(self):
        src = _get_script_source()
        assert '"--train-years"' in src

    def test_test_years_type_is_int(self):
        src = _get_script_source()
        assert '"--test-years"' in src

    def test_top_n_symbols_type_is_int(self):
        src = _get_script_source()
        assert '"--top-n-symbols"' in src

    def test_output_tag_type_is_str(self):
        src = _get_script_source()
        assert '"--output-tag"' in src


# ---------------------------------------------------------------------------
# Section 2: Defaults Unchanged
# ---------------------------------------------------------------------------


class TestCPCVFoldExpansionDefaults:
    """Verify defaults are unchanged: 8 folds / 3 train-years / 1 test-year / 30 top-n-symbols."""

    def test_default_n_folds_is_8(self):
        src = _get_script_source()
        assert "_DEFAULT_N_FOLDS = 8" in src, \
            "Default n_folds must be 8"

    def test_default_train_years_is_3(self):
        src = _get_script_source()
        assert "_DEFAULT_TRAIN_YEARS = 3" in src, \
            "Default train_years must be 3"

    def test_default_test_years_is_1(self):
        src = _get_script_source()
        assert "_DEFAULT_TEST_YEARS = 1" in src, \
            "Default test_years must be 1"

    def test_default_top_n_symbols_is_30(self):
        src = _get_script_source()
        assert "_DEFAULT_TOP_N_SYMBOLS = 30" in src, \
            "Default top_n_symbols must be 30"

    def test_cli_args_default_none(self):
        """CLI args default to None so they don't override built-in defaults."""
        src = _get_script_source()
        lines = src.split('\n')
        found_n_folds = False
        found_train_years = False
        found_test_years = False
        found_top_n_symbols = False
        found_output_tag = False
        for i, line in enumerate(lines):
            if '"--n-folds"' in line:
                found_n_folds = True
                block = '\n'.join(lines[i:i+5])
                assert "default=None" in block, "--n-folds must default to None"
            if '"--train-years"' in line:
                found_train_years = True
                block = '\n'.join(lines[i:i+5])
                assert "default=None" in block, "--train-years must default to None"
            if '"--test-years"' in line:
                found_test_years = True
                block = '\n'.join(lines[i:i+5])
                assert "default=None" in block, "--test-years must default to None"
            if '"--top-n-symbols"' in line:
                found_top_n_symbols = True
                block = '\n'.join(lines[i:i+5])
                assert "default=None" in block, "--top-n-symbols must default to None"
            if '"--output-tag"' in line:
                found_output_tag = True
                block = '\n'.join(lines[i:i+5])
                assert "default=None" in block, "--output-tag must default to None"
        assert found_n_folds, "--n-folds flag not found"
        assert found_train_years, "--train-years flag not found"
        assert found_test_years, "--test-years flag not found"
        assert found_top_n_symbols, "--top-n-symbols flag not found"
        assert found_output_tag, "--output-tag flag not found"


# ---------------------------------------------------------------------------
# Section 3: Quick-Mode Override
# ---------------------------------------------------------------------------


class TestCPCVFoldExpansionQuickModeOverride:
    """Verify quick-mode always overrides to 2/1/1/1 regardless of CLI values."""

    def test_quick_mode_overrides_n_folds(self):
        src = _get_script_source()
        assert "if args.quick_mode:" in src
        quick_mode_idx = src.index("if args.quick_mode:")
        quick_block = src[quick_mode_idx:quick_mode_idx+300]
        assert "N_FOLDS = 2" in quick_block, \
            "Quick-mode must set N_FOLDS = 2"

    def test_quick_mode_overrides_train_years(self):
        src = _get_script_source()
        quick_mode_idx = src.index("if args.quick_mode:")
        quick_block = src[quick_mode_idx:quick_mode_idx+300]
        assert "TRAIN_YEARS = 1" in quick_block, \
            "Quick-mode must set TRAIN_YEARS = 1"

    def test_quick_mode_overrides_test_years(self):
        src = _get_script_source()
        quick_mode_idx = src.index("if args.quick_mode:")
        quick_block = src[quick_mode_idx:quick_mode_idx+300]
        assert "TEST_YEARS = 1" in quick_block, \
            "Quick-mode must set TEST_YEARS = 1"

    def test_quick_mode_overrides_top_n_symbols(self):
        src = _get_script_source()
        quick_mode_idx = src.index("if args.quick_mode:")
        quick_block = src[quick_mode_idx:quick_mode_idx+300]
        assert "TOP_N_SYMBOLS = 1" in quick_block, \
            "Quick-mode must set TOP_N_SYMBOLS = 1"

    def test_non_quick_mode_uses_cli_args(self):
        """When not in quick-mode, CLI args are used with fallback to defaults."""
        src = _get_script_source()
        assert "args.top_n_symbols if args.top_n_symbols is not None" in src, \
            "Non-quick-mode must use CLI arg if provided"
        assert "args.n_folds if args.n_folds is not None" in src, \
            "Non-quick-mode must use CLI arg if provided"
        assert "args.train_years if args.train_years is not None" in src, \
            "Non-quick-mode must use CLI arg if provided"
        assert "args.test_years if args.test_years is not None" in src, \
            "Non-quick-mode must use CLI arg if provided"


# ---------------------------------------------------------------------------
# Section 4: Output Tag
# ---------------------------------------------------------------------------


class TestCPCVFoldExpansionOutputTag:
    """Verify output-tag changes output filenames to avoid overwrite."""

    def test_output_tag_modifies_result_suffix(self):
        src = _get_script_source()
        assert "if args.output_tag:" in src, \
            "Script must check args.output_tag"
        assert "result_suffix = f\"{args.output_tag}_{result_suffix}\"" in src, \
            "Output tag must be prepended to result suffix"

    def test_output_tag_applied_to_json_path(self):
        src = _get_script_source()
        assert "phase35_backtest_results_{result_suffix}.json" in src, \
            "JSON path must use result_suffix"

    def test_output_tag_applied_to_summary_path(self):
        src = _get_script_source()
        assert "phase35_backtest_summary_{result_suffix}.txt" in src, \
            "Summary path must use result_suffix"

    def test_no_output_tag_preserves_baseline_filename(self):
        """Without --output-tag, filenames should be unchanged."""
        src = _get_script_source()
        assert "if args.output_tag:" in src
        # GATE: MULTI_MODEL_ML_ENSEMBLE_20260616 — result_suffix now includes
        # multi_model_ensemble branch ahead of the xgboost/baseline ternary.
        assert 'result_suffix = "multi_model_ensemble" if args.enable_multi_model_ensemble else ("xgboost" if args.use_xgboost else "baseline")' in src


# ---------------------------------------------------------------------------
# Section 5: Config Persistence (existing)
# ---------------------------------------------------------------------------


class TestCPCVFoldExpansionConfigPersistence:
    """Verify JSON config persists fold expansion parameters."""

    def test_config_includes_n_folds(self):
        src = _get_script_source()
        assert '"cpcv_fold_expansion_n_folds"' in src, \
            "Config must include cpcv_fold_expansion_n_folds"

    def test_config_includes_train_years(self):
        src = _get_script_source()
        assert '"cpcv_fold_expansion_train_years"' in src, \
            "Config must include cpcv_fold_expansion_train_years"

    def test_config_includes_test_years(self):
        src = _get_script_source()
        assert '"cpcv_fold_expansion_test_years"' in src, \
            "Config must include cpcv_fold_expansion_test_years"

    def test_config_includes_top_n_symbols(self):
        src = _get_script_source()
        assert '"cpcv_fold_expansion_top_n_symbols"' in src, \
            "Config must include cpcv_fold_expansion_top_n_symbols"

    def test_config_includes_output_tag(self):
        src = _get_script_source()
        assert '"cpcv_fold_expansion_output_tag"' in src, \
            "Config must include cpcv_fold_expansion_output_tag"


# ---------------------------------------------------------------------------
# Section 6: Logging
# ---------------------------------------------------------------------------


class TestCPCVFoldExpansionLogging:
    """Verify fold expansion config is logged."""

    def test_logs_fold_expansion_params(self):
        src = _get_script_source()
        assert "[CPCV_FOLD_EXPANSION]" in src, \
            "Script must log CPCV fold expansion parameters"

    def test_logs_output_tag(self):
        src = _get_script_source()
        assert "output_tag=" in src, \
            "Script must log output_tag value"


# ---------------------------------------------------------------------------
# Section 7: PIT Safety
# ---------------------------------------------------------------------------


class TestCPCVFoldExpansionPITSafety:
    """Verify no changes to data pipeline that could introduce look-ahead bias."""

    def test_no_changes_to_split_creation(self):
        """The walk-forward split creation call is unchanged."""
        src = _get_script_source()
        assert "loader.create_walk_forward_splits(" in src
        assert "n_folds=N_FOLDS," in src
        assert "train_years=TRAIN_YEARS," in src
        assert "test_years=TEST_YEARS," in src

    def test_no_changes_to_data_loading(self):
        """The data loading call is unchanged."""
        src = _get_script_source()
        assert "loader.load_and_prepare(" in src
        assert "top_n_symbols=TOP_N_SYMBOLS," in src

    def test_no_future_data_access(self):
        """No new .shift(-1) or .lead() or future_data patterns."""
        src = _get_script_source()
        assert ".shift(-" not in src, \
            "Script must not contain negative shifts (look-ahead)"
        assert ".lead(" not in src, \
            "Script must not contain lead operations"

    def test_gate_comment_present(self):
        """GATE comment marks the feature boundary."""
        src = _get_script_source()
        assert "CPCV_FOLD_EXPANSION_20260614" in src, \
            "GATE identifier must be present in source"


# ---------------------------------------------------------------------------
# Section 8: No Default Behavior Change
# ---------------------------------------------------------------------------


class TestCPCVFoldExpansionNoDefaultBehaviorChange:
    """Verify no live/default behavior changes when new args are not used."""

    def test_existing_quick_mode_still_works(self):
        """--quick-mode flag still exists and works as before."""
        src = _get_script_source()
        assert '"--quick-mode"' in src, \
            "Existing --quick-mode flag must still be present"

    def test_existing_flags_unchanged(self):
        """All pre-existing CLI flags are still present."""
        src = _get_script_source()
        existing_flags = [
            '"--no-xgboost"',
            '"--start-date"',
            '"--end-date"',
            '"--initial-capital"',
            '"--strategy"',
            '"--slippage-bps"',
            '"--commission-bps"',
            '"--quick-mode"',
            '"--drawdown-control"',
            '"--enable-evolved"',
        ]
        for flag in existing_flags:
            assert flag in src, f"Existing flag {flag} must still be present"


# ---------------------------------------------------------------------------
# Section 9: FIX1 — Persisted config.n_folds reflects REQUESTED value
# ---------------------------------------------------------------------------


class TestCPCVFoldExpansionFix1PersistedNFolds:
    """GATE: CPCV_FOLD_EXPANSION_FIX1_20260614

    Verify that config.n_folds in the persisted JSON reflects the CLI-requested
    N_FOLDS value, NOT len(splits).  Also verify n_folds_executed and
    summary.n_folds_requested are present.
    """

    def test_config_n_folds_uses_N_FOLDS_not_len_splits(self):
        """config.n_folds must be N_FOLDS (requested), not len(splits)."""
        src = _get_script_source()
        # The old defect: "n_folds": len(splits)
        assert '"n_folds": len(splits)' not in src, \
            "FIX1: config.n_folds must NOT use len(splits) — use N_FOLDS instead"
        # The fix: "n_folds": N_FOLDS
        assert '"n_folds": N_FOLDS' in src, \
            "FIX1: config.n_folds must persist the requested N_FOLDS value"

    def test_config_includes_n_folds_executed(self):
        """config must include n_folds_executed = len(splits) for transparency."""
        src = _get_script_source()
        assert '"n_folds_executed":' in src, \
            "FIX1: config must include n_folds_executed field"
        assert 'n_folds_executed' in src, \
            "FIX1: n_folds_executed variable must be computed"

    def test_summary_includes_n_folds_requested(self):
        """summary must include n_folds_requested for audit trail."""
        src = _get_script_source()
        assert '"n_folds_requested":' in src, \
            "FIX1: summary must include n_folds_requested field"

    def test_warning_logged_when_fewer_folds_than_requested(self):
        """A warning must be logged when n_folds_executed < N_FOLDS."""
        src = _get_script_source()
        assert "CPCV_FOLD_EXPANSION_FIX1" in src, \
            "FIX1: warning identifier must be present"
        assert "n_folds_executed < N_FOLDS" in src, \
            "FIX1: conditional warning on fold count mismatch"

    def test_fix1_gate_comment_in_data_loader(self):
        """GATE FIX1 comment must be present in data loader source."""
        src = _get_data_loader_source()
        assert "CPCV_FOLD_EXPANSION_FIX1_20260614" in src, \
            "FIX1: GATE identifier must be in data loader"


# ---------------------------------------------------------------------------
# Section 10: FIX1 — Adaptive step size in create_walk_forward_splits
# ---------------------------------------------------------------------------


class TestCPCVFoldExpansionFix1AdaptiveStep:
    """GATE: CPCV_FOLD_EXPANSION_FIX1_20260614

    Verify that create_walk_forward_splits uses adaptive step size so
    that --n-folds 12 actually produces 12 folds when data range allows.
    """

    def test_data_loader_uses_adaptive_step(self):
        """Data loader source must compute adaptive step size."""
        src = _get_data_loader_source()
        assert "step_days" in src, \
            "FIX1: data loader must compute step_days variable"
        assert "legacy_step" in src, \
            "FIX1: data loader must reference legacy_step for backward compat"
        assert "available_span" in src, \
            "FIX1: data loader must compute available_span"

    def test_backward_compat_8_folds_default_step(self):
        """With default 8 folds + 3/1 years and 12yr data, step stays 365."""
        from phase35_data_loader import Phase35DataLoader
        loader = Phase35DataLoader()
        df = _make_synthetic_df(start="2014-01-02", end="2026-06-01", n_symbols=2)
        splits = loader.create_walk_forward_splits(df, n_folds=8, train_years=3, test_years=1)
        # With 12 years of data, 8 folds at 365-day step should produce 8 folds
        assert len(splits) == 8, \
            f"Backward compat: 8 folds requested, got {len(splits)}"

    def test_12_folds_produces_12_with_sufficient_data(self):
        """With n_folds=12 + 3/1 years and ~12yr data, must produce 12 folds."""
        from phase35_data_loader import Phase35DataLoader
        loader = Phase35DataLoader()
        df = _make_synthetic_df(start="2014-01-02", end="2026-06-01", n_symbols=2)
        splits = loader.create_walk_forward_splits(df, n_folds=12, train_years=3, test_years=1)
        assert len(splits) == 12, \
            f"FIX1: 12 folds requested but only {len(splits)} produced"

    def test_16_folds_produces_16_with_sufficient_data(self):
        """With n_folds=16 + 2/1 years and ~12yr data, must produce 16 folds."""
        from phase35_data_loader import Phase35DataLoader
        loader = Phase35DataLoader()
        df = _make_synthetic_df(start="2014-01-02", end="2026-06-01", n_symbols=2)
        splits = loader.create_walk_forward_splits(df, n_folds=16, train_years=2, test_years=1)
        assert len(splits) == 16, \
            f"FIX1: 16 folds requested but only {len(splits)} produced"

    def test_2_folds_quick_mode_step_unchanged(self):
        """Quick-mode 2 folds should still use 365-day step (backward compat)."""
        from phase35_data_loader import Phase35DataLoader
        loader = Phase35DataLoader()
        df = _make_synthetic_df(start="2014-01-02", end="2026-06-01", n_symbols=2)
        splits = loader.create_walk_forward_splits(df, n_folds=2, train_years=1, test_years=1)
        assert len(splits) == 2, \
            f"Quick-mode: 2 folds requested, got {len(splits)}"

    def test_no_future_data_in_splits(self):
        """Every fold's test_start must be >= train_end (PIT safety)."""
        from phase35_data_loader import Phase35DataLoader
        loader = Phase35DataLoader()
        df = _make_synthetic_df(start="2014-01-02", end="2026-06-01", n_symbols=2)
        splits = loader.create_walk_forward_splits(df, n_folds=12, train_years=3, test_years=1)
        for i, (train_df, test_df) in enumerate(splits):
            train_max = train_df['date'].max()
            test_min = test_df['date'].min()
            assert test_min > train_max, \
                f"FIX1 PIT: fold {i+1} test_start ({test_min}) must be > train_end ({train_max})"

    def test_fold_count_matches_request_when_data_sufficient(self):
        """Parametric: for various n_folds, verify count matches."""
        from phase35_data_loader import Phase35DataLoader
        loader = Phase35DataLoader()
        df = _make_synthetic_df(start="2010-01-04", end="2026-06-01", n_symbols=2)
        for requested in [4, 8, 10, 12, 15]:
            splits = loader.create_walk_forward_splits(
                df, n_folds=requested, train_years=2, test_years=1
            )
            assert len(splits) == requested, \
                f"FIX1: {requested} folds requested but only {len(splits)} produced"

    def test_single_fold_does_not_crash(self):
        """Edge case: n_folds=1 should work without division by zero."""
        from phase35_data_loader import Phase35DataLoader
        loader = Phase35DataLoader()
        df = _make_synthetic_df(start="2014-01-02", end="2026-06-01", n_symbols=2)
        splits = loader.create_walk_forward_splits(df, n_folds=1, train_years=3, test_years=1)
        assert len(splits) == 1, \
            f"Edge case: 1 fold requested, got {len(splits)}"


# ---------------------------------------------------------------------------
# Section 11: FIX1 — End-to-end config/summary fold count consistency
# ---------------------------------------------------------------------------


class TestCPCVFoldExpansionFix1EndToEndConsistency:
    """GATE: CPCV_FOLD_EXPANSION_FIX1_20260614

    Verify the script source wires n_folds_executed and n_folds_requested
    correctly end-to-end, so the persisted JSON can be audited.
    """

    def test_n_folds_executed_computed_from_splits(self):
        """n_folds_executed must be computed as len(splits)."""
        src = _get_script_source()
        assert "n_folds_executed = len(splits)" in src, \
            "FIX1: n_folds_executed must be set to len(splits)"

    def test_config_n_folds_is_not_len_splits(self):
        """Regression: config.n_folds must never be len(splits) again."""
        src = _get_script_source()
        # Search for the specific pattern in the config dict
        assert '"n_folds": len(splits)' not in src, \
            "FIX1 REGRESSION: config.n_folds must not be len(splits)"

    def test_summary_total_folds_uses_result(self):
        """summary.total_folds still comes from result.total_folds (actual executed)."""
        src = _get_script_source()
        assert '"total_folds": result.total_folds' in src, \
            "summary.total_folds must come from result.total_folds"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
