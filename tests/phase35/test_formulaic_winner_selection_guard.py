"""
Formulaic Winner Selection Guard Tests
GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614
[L2-Impl:Role14-Data-Scientist] - 2026-06-14

Verifies that:
1. Default disabled — no winner guard behavior change when flag not set
2. Guard enabled excludes bad legacy alphas from selection/fallback
3. Evidence persistence in JSON output (allowlist, excluded, selected, per-fold)
4. PIT/no lookahead — only uses current fold train/validation IC
5. CLI validation — flags registered, alias works, config persisted

PIT Safety: No real data loaded. Synthetic data tests and source inspection only.
"""

import ast
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))


def _get_script_source():
    """Read the run_phase35_backtest.py source code."""
    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_phase35_backtest.py"
    return script_path.read_text(encoding="utf-8")


def _get_engine_source():
    """Read the phase35.py engine source code."""
    engine_path = Path(__file__).resolve().parent.parent.parent / "src" / "omega" / "quant" / "alpha" / "phase35.py"
    return engine_path.read_text(encoding="utf-8")


def _make_mock_engine(winner_guard=False, allowlist=None, min_val_ic=0.0):
    """Create a Phase35WalkForwardEngine with mocked dependencies."""
    from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
    mock_module = MagicMock()
    mock_module.PHASE34_ALPHA_COLUMNS = ("alpha_p34_test_1", "alpha_p34_test_2")
    mock_module.compute_phase34_microstructure_alphas = MagicMock(
        return_value=pd.DataFrame()
    )
    with patch.dict("sys.modules", {
        "omega.quant.ml.gate_validator": MagicMock(),
        "omega.quant.ml.ensemble_xgboost": MagicMock(),
    }):
        mock_ra = MagicMock()
        mock_ra.PRESETS = {
            "balanced": {}, "alpha_recovery": {},
            "drawdown_guarded": {}, "ic_first_guarded": {},
        }
        mock_ra.VALID_RESEARCH_POOL_MODES = [
            "full", "recovery_only", "recoverable_only"
        ]
        mock_ra.get_preset_weights = MagicMock(return_value={})
        mock_ra.get_preset_rank_components = MagicMock(return_value={
            "primary_rank_components": [],
            "soft_penalty_components": [],
        })
        with patch.dict("sys.modules", {
            "omega.quant.walk_forward.risk_adjusted_alpha_score": mock_ra,
        }):
            engine = Phase35WalkForwardEngine(
                alpha_module=mock_module,
                formulaic_winner_guard=winner_guard,
                formulaic_winner_allowlist=allowlist,
                formulaic_winner_min_val_ic=min_val_ic,
            )
    return engine


# ---------------------------------------------------------------------------
# Section 1: CLI Flag Registration
# ---------------------------------------------------------------------------


class TestWinnerGuardCLIFlags:
    """Verify --formulaic-winner-guard and --winner-alpha-filter CLI flags."""

    def test_cli_formulaic_winner_guard_flag_registered(self):
        src = _get_script_source()
        assert '"--formulaic-winner-guard"' in src, \
            "CLI flag --formulaic-winner-guard must be registered"

    def test_cli_winner_alpha_filter_alias_registered(self):
        src = _get_script_source()
        assert '"--winner-alpha-filter"' in src, \
            "CLI flag --winner-alpha-filter (alias) must be registered"

    def test_cli_formulaic_winner_guard_is_store_true(self):
        """--formulaic-winner-guard must use action='store_true'."""
        src = _get_script_source()
        # Find the argparse registration block
        idx = src.find('"--formulaic-winner-guard"')
        block = src[idx:idx + 200]
        assert "store_true" in block, \
            "--formulaic-winner-guard must use store_true action"

    def test_cli_gate_label_present(self):
        src = _get_script_source()
        assert "FORMULAIC_WINNER_SELECTION_GUARD_20260614" in src, \
            "Gate label must be present in script"

    def test_cli_default_disabled(self):
        """Winner guard must be disabled by default."""
        src = _get_script_source()
        # store_true means default is False
        idx = src.find('"--formulaic-winner-guard"')
        block = src[idx:idx + 300]
        assert "store_true" in block, \
            "Default must be False (store_true action)"

    def test_cli_combined_flag_logic(self):
        """Script must combine --formulaic-winner-guard OR --winner-alpha-filter."""
        src = _get_script_source()
        assert "args.formulaic_winner_guard" in src, \
            "Script must compute combined formulaic_winner_guard flag"
        assert "args.winner_alpha_filter" in src, \
            "Script must reference winner_alpha_filter alias"

    def test_cli_engine_receives_winner_guard(self):
        """Engine constructor must receive formulaic_winner_guard."""
        src = _get_script_source()
        assert "formulaic_winner_guard=args.formulaic_winner_guard" in src, \
            "Engine must receive formulaic_winner_guard from args"

    def test_cli_config_persists_winner_guard(self):
        """Config dict must persist formulaic_winner_guard."""
        src = _get_script_source()
        assert '"formulaic_winner_guard": args.formulaic_winner_guard' in src, \
            "Config dict must persist formulaic_winner_guard"

    def test_cli_logs_winner_guard(self):
        """Script must log the winner guard config."""
        src = _get_script_source()
        assert "Formulaic Winner Guard" in src, \
            "Script must log the winner guard config"


# ---------------------------------------------------------------------------
# Section 2: Default Disabled — No Behavior Change
# ---------------------------------------------------------------------------


class TestDefaultDisabled:
    """Verify default disabled behavior — no change when guard is off."""

    def test_engine_default_no_guard(self):
        """Engine with no formulaic_winner_guard should have it disabled."""
        engine = _make_mock_engine(winner_guard=False)
        assert engine.formulaic_winner_guard is False

    def test_guard_off_returns_all_candidates(self):
        """When guard is off, apply_formulaic_winner_guard returns all candidates."""
        engine = _make_mock_engine(winner_guard=False)
        candidates = [
            "alpha_p34_test_1", "alpha_fml052_close_zscore_mr_20",
            "alpha_bad_legacy", "alpha_fml012_mean_rev_rank_10",
        ]
        val_ics = {
            "alpha_p34_test_1": 0.05,
            "alpha_fml052_close_zscore_mr_20": 0.02,
            "alpha_bad_legacy": -0.03,
            "alpha_fml012_mean_rev_rank_10": 0.01,
        }
        filtered, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        assert filtered == candidates, \
            "Guard off must return all candidates unchanged"
        assert evidence["guard_enabled"] is False

    def test_fallback_filter_off_returns_all(self):
        """When guard is off, filter_fallback_by_winner_guard returns all."""
        engine = _make_mock_engine(winner_guard=False)
        fallback = ["alpha_bad_legacy", "alpha_p34_test_1"]
        val_ics = {"alpha_bad_legacy": -0.03, "alpha_p34_test_1": 0.05}
        filtered, excluded = engine.filter_fallback_by_winner_guard(
            fallback, val_ics
        )
        assert filtered == fallback
        assert excluded == []


# ---------------------------------------------------------------------------
# Section 3: Guard Enabled — Excludes Bad Legacy Alphas
# ---------------------------------------------------------------------------


class TestGuardEnabledExcludesLegacy:
    """Verify guard excludes non-allowlist legacy alphas."""

    def test_excludes_non_allowlist_legacy_alphas(self):
        """Non-allowlist legacy alphas must be excluded when guard is on."""
        engine = _make_mock_engine(winner_guard=True)
        candidates = [
            "alpha_fml052_close_zscore_mr_20",
            "alpha_fml012_mean_rev_rank_10",
            "alpha_p34_bad_legacy_1",
            "alpha_p34_bad_legacy_2",
        ]
        val_ics = {
            "alpha_fml052_close_zscore_mr_20": 0.02,
            "alpha_fml012_mean_rev_rank_10": 0.01,
            "alpha_p34_bad_legacy_1": -0.03,
            "alpha_p34_bad_legacy_2": 0.04,
        }
        filtered, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        assert "alpha_p34_bad_legacy_1" not in filtered
        assert "alpha_p34_bad_legacy_2" not in filtered
        assert "alpha_fml052_close_zscore_mr_20" in filtered
        assert "alpha_fml012_mean_rev_rank_10" in filtered

    def test_excludes_allowlist_below_min_ic(self):
        """Allowlist alphas with val_ic below min threshold are excluded."""
        engine = _make_mock_engine(
            winner_guard=True, min_val_ic=0.015
        )
        candidates = [
            "alpha_fml052_close_zscore_mr_20",
            "alpha_fml012_mean_rev_rank_10",
        ]
        val_ics = {
            "alpha_fml052_close_zscore_mr_20": 0.02,
            "alpha_fml012_mean_rev_rank_10": 0.01,
        }
        filtered, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        assert "alpha_fml052_close_zscore_mr_20" in filtered
        assert "alpha_fml012_mean_rev_rank_10" not in filtered

    def test_graceful_fallback_when_all_excluded(self):
        """If all candidates excluded, uses allowlist-only fallback (FIX1).

        GATE: FORMULAIC_WINNER_SELECTION_GUARD_FIX1_20260614
        Guard-enabled post_guard_alphas must never contain non-allowlist
        legacy alphas.  When all candidates excluded, allowlist-only
        fallback ranked by val_ic is used where available.
        """
        engine = _make_mock_engine(winner_guard=True)
        candidates = ["alpha_bad_1", "alpha_bad_2"]
        val_ics = {"alpha_bad_1": -0.05, "alpha_bad_2": -0.03}
        filtered, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        # No non-allowlist legacy alpha may appear in filtered result
        allowlist_set = set(engine.formulaic_winner_allowlist)
        for alpha in filtered:
            assert alpha in allowlist_set, \
                f"Non-allowlist alpha '{alpha}' must not appear in guard-enabled post_guard pool"
        # Original legacy candidates must NOT be restored
        assert "alpha_bad_1" not in filtered
        assert "alpha_bad_2" not in filtered

    def test_all_excluded_no_allowlist_val_ic_marks_no_guard_candidates(self):
        """If all candidates excluded and no allowlist members have val_ic,
        mark fold as no_guard_candidates and return empty list (FIX1).

        GATE: FORMULAIC_WINNER_SELECTION_GUARD_FIX1_20260614
        """
        engine = _make_mock_engine(winner_guard=True)
        candidates = ["alpha_bad_1", "alpha_bad_2"]
        # val_ics has NO allowlist members at all
        val_ics = {"alpha_bad_1": -0.05, "alpha_bad_2": -0.03}
        filtered, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        # When no allowlist members have qualifying val_ic, result is empty
        assert filtered == [], \
            "Must return empty list when no allowlist members have qualifying val_ic"
        assert evidence["no_guard_candidates"] is True
        assert evidence["fallback_used"] is False

    def test_fallback_filter_excludes_legacy(self):
        """filter_fallback_by_winner_guard excludes non-allowlist from fallback."""
        engine = _make_mock_engine(winner_guard=True)
        fallback = [
            "alpha_p34_legacy_1",
            "alpha_fml045_liq_turnover_5",
            "alpha_p34_legacy_2",
        ]
        val_ics = {
            "alpha_p34_legacy_1": 0.02,
            "alpha_fml045_liq_turnover_5": 0.01,
            "alpha_p34_legacy_2": 0.03,
        }
        filtered, excluded = engine.filter_fallback_by_winner_guard(
            fallback, val_ics
        )
        assert "alpha_fml045_liq_turnover_5" in filtered
        assert "alpha_p34_legacy_1" in excluded
        assert "alpha_p34_legacy_2" in excluded

    def test_fallback_filter_graceful_when_all_excluded(self):
        """Fallback filter returns empty list when all excluded (FIX1).

        GATE: FORMULAIC_WINNER_SELECTION_GUARD_FIX1_20260614
        Non-allowlist legacy alphas must never be re-admitted into the
        fallback pool.  When all excluded, returns empty filtered list
        and all as excluded.
        """
        engine = _make_mock_engine(winner_guard=True)
        fallback = ["alpha_p34_legacy_1", "alpha_p34_legacy_2"]
        val_ics = {"alpha_p34_legacy_1": 0.02, "alpha_p34_legacy_2": 0.03}
        filtered, excluded = engine.filter_fallback_by_winner_guard(
            fallback, val_ics
        )
        # Empty filtered (no legacy re-admission)
        assert filtered == [], \
            "Must return empty list when all fallback excluded (no legacy re-admission)"
        # All legacy alphas should be in excluded
        assert set(excluded) == set(fallback)

    def test_custom_allowlist(self):
        """Custom allowlist is respected."""
        custom = ["alpha_custom_1", "alpha_custom_2"]
        engine = _make_mock_engine(
            winner_guard=True, allowlist=custom
        )
        candidates = [
            "alpha_custom_1", "alpha_fml052_close_zscore_mr_20"
        ]
        val_ics = {
            "alpha_custom_1": 0.02,
            "alpha_fml052_close_zscore_mr_20": 0.02,
        }
        filtered, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        assert "alpha_custom_1" in filtered
        assert "alpha_fml052_close_zscore_mr_20" not in filtered


# ---------------------------------------------------------------------------
# Section 4: Evidence Persistence
# ---------------------------------------------------------------------------


class TestEvidencePersistence:
    """Verify evidence dict is structured correctly for JSON persistence."""

    def test_evidence_has_gate_label(self):
        engine = _make_mock_engine(winner_guard=True)
        _, evidence = engine.apply_formulaic_winner_guard(
            ["alpha_fml052_close_zscore_mr_20"], {"alpha_fml052_close_zscore_mr_20": 0.02}
        )
        assert evidence["gate"] == "FORMULAIC_WINNER_SELECTION_GUARD_20260614"

    def test_evidence_has_guard_enabled(self):
        engine = _make_mock_engine(winner_guard=True)
        _, evidence = engine.apply_formulaic_winner_guard(
            ["alpha_fml052_close_zscore_mr_20"], {"alpha_fml052_close_zscore_mr_20": 0.02}
        )
        assert evidence["guard_enabled"] is True

    def test_evidence_has_allowlist(self):
        engine = _make_mock_engine(winner_guard=True)
        _, evidence = engine.apply_formulaic_winner_guard(
            ["alpha_fml052_close_zscore_mr_20"], {"alpha_fml052_close_zscore_mr_20": 0.02}
        )
        assert "allowlist" in evidence
        assert "alpha_fml052_close_zscore_mr_20" in evidence["allowlist"]

    def test_evidence_has_pre_post_guard_alphas(self):
        engine = _make_mock_engine(winner_guard=True)
        candidates = [
            "alpha_fml052_close_zscore_mr_20", "alpha_p34_legacy"
        ]
        val_ics = {
            "alpha_fml052_close_zscore_mr_20": 0.02,
            "alpha_p34_legacy": -0.01,
        }
        _, evidence = engine.apply_formulaic_winner_guard(candidates, val_ics)
        assert evidence["pre_guard_alphas"] == candidates
        assert "alpha_p34_legacy" in evidence["excluded_alphas"]

    def test_evidence_has_val_ics_used(self):
        engine = _make_mock_engine(winner_guard=True)
        candidates = ["alpha_fml052_close_zscore_mr_20"]
        val_ics = {"alpha_fml052_close_zscore_mr_20": 0.0164}
        _, evidence = engine.apply_formulaic_winner_guard(candidates, val_ics)
        assert "val_ics_used" in evidence
        assert abs(evidence["val_ics_used"]["alpha_fml052_close_zscore_mr_20"] - 0.0164) < 1e-4

    def test_evidence_has_min_val_ic(self):
        engine = _make_mock_engine(winner_guard=True, min_val_ic=0.005)
        _, evidence = engine.apply_formulaic_winner_guard(
            ["alpha_fml052_close_zscore_mr_20"], {"alpha_fml052_close_zscore_mr_20": 0.02}
        )
        assert evidence["min_val_ic"] == 0.005

    def test_evidence_has_pit_safe_flag(self):
        engine = _make_mock_engine(winner_guard=True)
        _, evidence = engine.apply_formulaic_winner_guard(
            ["alpha_fml052_close_zscore_mr_20"], {"alpha_fml052_close_zscore_mr_20": 0.02}
        )
        assert evidence["pit_safe"] is True

    def test_evidence_has_fallback_used(self):
        engine = _make_mock_engine(winner_guard=True)
        _, evidence = engine.apply_formulaic_winner_guard(
            ["alpha_fml052_close_zscore_mr_20"], {"alpha_fml052_close_zscore_mr_20": 0.02}
        )
        assert "fallback_used" in evidence

    def test_evidence_json_serializable(self):
        """Evidence dict must be JSON-serializable."""
        engine = _make_mock_engine(winner_guard=True)
        candidates = [
            "alpha_fml052_close_zscore_mr_20",
            "alpha_p34_legacy",
        ]
        val_ics = {
            "alpha_fml052_close_zscore_mr_20": 0.02,
            "alpha_p34_legacy": -0.03,
        }
        _, evidence = engine.apply_formulaic_winner_guard(candidates, val_ics)
        serialized = json.dumps(evidence)
        deserialized = json.loads(serialized)
        assert deserialized["gate"] == evidence["gate"]

    def test_fold_metrics_has_winner_guard_evidence_field(self):
        """FoldMetrics must have winner_guard_evidence field."""
        from omega.quant.alpha.phase35 import FoldMetrics
        m = FoldMetrics(
            fold_id=1, train_start="2020-01-01", train_end="2020-12-31",
            test_start="2021-01-01", test_end="2021-12-31",
        )
        assert hasattr(m, "winner_guard_evidence")
        assert m.winner_guard_evidence is None

    def test_serialize_fold_details_persists_winner_guard_evidence(self):
        """serialize_fold_details must persist winner_guard_evidence."""
        src = _get_script_source()
        assert '"winner_guard_evidence"' in src, \
            "serialize_fold_details must persist winner_guard_evidence"


# ---------------------------------------------------------------------------
# Section 5: PIT / No Lookahead Safety
# ---------------------------------------------------------------------------


class TestPITNoLookahead:
    """Verify no look-ahead bias in winner guard implementation."""

    def test_guard_uses_only_val_ics_argument(self):
        """apply_formulaic_winner_guard must use only the val_ics argument."""
        src = _get_engine_source()
        # Find the method body
        idx = src.find("def apply_formulaic_winner_guard(")
        assert idx != -1, "Method must exist"
        end_idx = src.find("\n    def ", idx + 1)
        body = src[idx:end_idx] if end_idx != -1 else src[idx:]
        # Should NOT access test_df, test data, or future fold results
        assert "test_df" not in body, \
            "Guard must not access test_df"
        assert "test_set" not in body, \
            "Guard must not access test set data"

    def test_run_fold_computes_val_ics_for_guard(self):
        """run_fold must compute validation ICs from val_actual for guard."""
        src = _get_engine_source()
        assert "_val_ics_for_guard" in src, \
            "run_fold must compute validation ICs for guard"

    def test_guard_val_ics_from_val_actual(self):
        """Guard validation ICs must come from val_actual (embargoed train subset)."""
        src = _get_engine_source()
        # Find the guard block in run_fold
        guard_idx = src.find("_val_ics_for_guard = self.compute_alpha_ics")
        assert guard_idx != -1, "Guard must compute ICs via compute_alpha_ics"
        # The next few lines should reference val_actual
        guard_block = src[guard_idx:guard_idx + 200]
        assert "val_actual" in guard_block, \
            "Guard ICs must be computed from val_actual"

    def test_no_future_fold_access_in_guard(self):
        """Guard must not access future fold data or aggregate stat reports."""
        src = _get_engine_source()
        idx = src.find("def apply_formulaic_winner_guard(")
        end_idx = src.find("\n    def ", idx + 1)
        body = src[idx:end_idx] if end_idx != -1 else src[idx:]
        # Should not access fold_metrics, run results, or aggregate stats
        assert "fold_metrics" not in body, \
            "Guard must not access fold_metrics (future data)"
        assert "avg_portfolio" not in body, \
            "Guard must not access aggregate portfolio stats"

    def test_engine_source_no_negative_shifts_in_guard(self):
        """Guard methods must not use negative shifts."""
        import re
        src = _get_engine_source()
        idx = src.find("def apply_formulaic_winner_guard(")
        end_idx = src.find("\n    def ", idx + 1)
        body = src[idx:end_idx] if end_idx != -1 else src[idx:]
        neg_shifts = re.findall(r'\.shift\s*\(\s*-\d', body)
        assert len(neg_shifts) == 0, \
            f"Guard must not use negative shifts: {neg_shifts}"


# ---------------------------------------------------------------------------
# Section 6: Engine Source Inspection
# ---------------------------------------------------------------------------


class TestEngineSourceInspection:
    """Verify engine source code structure for winner guard."""

    def test_gate_constant_defined(self):
        src = _get_engine_source()
        assert 'FORMULAIC_WINNER_GUARD_GATE_ID = "FORMULAIC_WINNER_SELECTION_GUARD_20260614"' in src, \
            "Gate constant must be defined"

    def test_default_allowlist_defined(self):
        src = _get_engine_source()
        assert "FORMULAIC_WINNER_DEFAULT_ALLOWLIST" in src, \
            "Default allowlist constant must be defined"

    def test_default_allowlist_contains_5_strong_alphas(self):
        from omega.quant.alpha.phase35 import FORMULAIC_WINNER_DEFAULT_ALLOWLIST
        assert len(FORMULAIC_WINNER_DEFAULT_ALLOWLIST) == 5
        assert "alpha_fml052_close_zscore_mr_20" in FORMULAIC_WINNER_DEFAULT_ALLOWLIST
        assert "alpha_fml012_mean_rev_rank_10" in FORMULAIC_WINNER_DEFAULT_ALLOWLIST
        assert "alpha_fml045_liq_turnover_5" in FORMULAIC_WINNER_DEFAULT_ALLOWLIST
        assert "alpha_fml067_vol_price_diverge_10" in FORMULAIC_WINNER_DEFAULT_ALLOWLIST
        assert "alpha_fml006_vp_corr_10" in FORMULAIC_WINNER_DEFAULT_ALLOWLIST

    def test_engine_validates_formulaic_winner_guard_type(self):
        src = _get_engine_source()
        assert "formulaic_winner_guard must be a boolean" in src, \
            "Engine must validate formulaic_winner_guard type"

    def test_engine_stores_formulaic_winner_guard(self):
        src = _get_engine_source()
        assert "self.formulaic_winner_guard" in src
        assert "self.formulaic_winner_allowlist" in src
        assert "self.formulaic_winner_min_val_ic" in src

    def test_engine_default_params(self):
        src = _get_engine_source()
        assert "formulaic_winner_guard: bool = False" in src
        assert "formulaic_winner_min_val_ic: float = 0.0" in src

    def test_foldmetrics_has_winner_guard_evidence(self):
        src = _get_engine_source()
        assert "winner_guard_evidence" in src, \
            "FoldMetrics must have winner_guard_evidence field"

    def test_filter_fallback_method_exists(self):
        src = _get_engine_source()
        assert "def filter_fallback_by_winner_guard(" in src, \
            "filter_fallback_by_winner_guard method must exist"


# ---------------------------------------------------------------------------
# Section 7: Constructor Validation
# ---------------------------------------------------------------------------


class TestConstructorValidation:
    """Verify engine constructor validates winner guard parameters."""

    def test_invalid_guard_type_raises(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ["alpha_1"]
        with pytest.raises(ValueError, match="formulaic_winner_guard"):
            Phase35WalkForwardEngine(
                alpha_module=mock_module,
                formulaic_winner_guard="yes",
            )

    def test_valid_guard_accepted(self):
        engine = _make_mock_engine(winner_guard=True)
        assert engine.formulaic_winner_guard is True

    def test_default_allowlist_used_when_none(self):
        from omega.quant.alpha.phase35 import FORMULAIC_WINNER_DEFAULT_ALLOWLIST
        engine = _make_mock_engine(winner_guard=True, allowlist=None)
        assert engine.formulaic_winner_allowlist == list(
            FORMULAIC_WINNER_DEFAULT_ALLOWLIST
        )

    def test_custom_allowlist_stored(self):
        custom = ["alpha_custom"]
        engine = _make_mock_engine(winner_guard=True, allowlist=custom)
        assert engine.formulaic_winner_allowlist == custom


# ---------------------------------------------------------------------------
# Section 8: Output Persistence in Script
# ---------------------------------------------------------------------------


class TestScriptOutputPersistence:
    """Verify the script persists winner guard evidence in JSON output."""

    def test_config_dict_has_winner_guard(self):
        src = _get_script_source()
        assert '"formulaic_winner_guard": args.formulaic_winner_guard' in src, \
            "Config dict must persist formulaic_winner_guard"

    def test_results_dict_includes_winner_guard_evidence(self):
        """Fold details serialization must include winner_guard_evidence."""
        src = _get_script_source()
        assert "winner_guard_evidence" in src, \
            "Script must reference winner_guard_evidence"

    def test_serialize_fold_details_handles_winner_guard(self):
        """serialize_fold_details must handle winner_guard_evidence."""
        src = _get_script_source()
        # Check that serialize_fold_details references winner_guard_evidence
        idx = src.find("def serialize_fold_details(m):")
        assert idx != -1
        next_def = src.find("\ndef ", idx + 1)
        body = src[idx:next_def] if next_def != -1 else src[idx:]
        assert "winner_guard_evidence" in body, \
            "serialize_fold_details must persist winner_guard_evidence"


# ---------------------------------------------------------------------------
# Section 9: Integration — Default Allowlist Coverage
# ---------------------------------------------------------------------------


class TestDefaultAllowlistCoverage:
    """Verify default allowlist matches the strong formulaic v3 candidates."""

    def test_allowlist_matches_v3_pruned(self):
        """Default allowlist should match v3_pruned formulaic alpha set."""
        from omega.quant.alpha.phase35 import FORMULAIC_WINNER_DEFAULT_ALLOWLIST
        from omega.quant.alpha.formulaic_alphas import FORMULAIC_ALPHA_SETS
        v3_cols = set(FORMULAIC_ALPHA_SETS["v3_pruned"])
        allowlist_set = set(FORMULAIC_WINNER_DEFAULT_ALLOWLIST)
        assert allowlist_set == v3_cols, \
            f"Allowlist {allowlist_set} must match v3_pruned {v3_cols}"

    def test_allowlist_all_start_with_alpha_fml(self):
        from omega.quant.alpha.phase35 import FORMULAIC_WINNER_DEFAULT_ALLOWLIST
        for name in FORMULAIC_WINNER_DEFAULT_ALLOWLIST:
            assert name.startswith("alpha_fml"), \
                f"Allowlist entry {name} must start with alpha_fml"


# ---------------------------------------------------------------------------
# Section 10: FIX1 Contract — No Non-Allowlist Legacy Re-admission
# GATE: FORMULAIC_WINNER_SELECTION_GUARD_FIX1_20260614
# ---------------------------------------------------------------------------


class TestFIX1NoLegacyReadmission:
    """Contract tests: guard-enabled post_guard/fallback pools never contain
    non-allowlist legacy alphas, including all-excluded cases."""

    def test_post_guard_pool_only_allowlist(self):
        """When guard enabled, every alpha in post_guard_alphas must be on allowlist."""
        engine = _make_mock_engine(winner_guard=True)
        candidates = [
            "alpha_fml052_close_zscore_mr_20",
            "alpha_fml012_mean_rev_rank_10",
            "alpha_legacy_bad_1",
            "alpha_legacy_bad_2",
            "alpha_legacy_positive_ic",
        ]
        val_ics = {
            "alpha_fml052_close_zscore_mr_20": 0.02,
            "alpha_fml012_mean_rev_rank_10": 0.01,
            "alpha_legacy_bad_1": -0.03,
            "alpha_legacy_bad_2": 0.04,
            "alpha_legacy_positive_ic": 0.05,
        }
        filtered, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        allowlist_set = set(engine.formulaic_winner_allowlist)
        for alpha in evidence["post_guard_alphas"]:
            assert alpha in allowlist_set, \
                f"post_guard_alphas contains non-allowlist alpha '{alpha}'"

    def test_all_excluded_allowlist_only_fallback_ranked_by_ic(self):
        """When all candidates excluded, allowlist-only fallback is ranked by val_ic."""
        engine = _make_mock_engine(winner_guard=True)
        candidates = ["alpha_legacy_1", "alpha_legacy_2"]
        # Give val_ics to some allowlist members so fallback has candidates
        val_ics = {
            "alpha_legacy_1": -0.05,
            "alpha_legacy_2": -0.03,
            "alpha_fml052_close_zscore_mr_20": 0.02,
            "alpha_fml045_liq_turnover_5": 0.04,
        }
        filtered, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        # No legacy alphas in result
        assert "alpha_legacy_1" not in filtered
        assert "alpha_legacy_2" not in filtered
        # Allowlist members with val_ic should be in fallback
        assert "alpha_fml052_close_zscore_mr_20" in filtered
        assert "alpha_fml045_liq_turnover_5" in filtered
        # Ranked by abs(IC) descending: fml045 (0.04) before fml052 (0.02)
        assert filtered.index("alpha_fml045_liq_turnover_5") < \
            filtered.index("alpha_fml052_close_zscore_mr_20")
        assert evidence["fallback_used"] is True
        assert evidence["no_guard_candidates"] is False

    def test_all_excluded_no_allowlist_ic_empty_result(self):
        """When all excluded and no allowlist has val_ic, result is empty."""
        engine = _make_mock_engine(winner_guard=True)
        candidates = ["alpha_legacy_1"]
        # val_ics has only legacy alpha, no allowlist members
        val_ics = {"alpha_legacy_1": -0.05}
        filtered, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        assert filtered == []
        assert evidence["no_guard_candidates"] is True
        assert evidence["fallback_used"] is False

    def test_fallback_filter_never_returns_non_allowlist(self):
        """filter_fallback_by_winner_guard never returns non-allowlist alphas."""
        engine = _make_mock_engine(winner_guard=True)
        fallback = [
            "alpha_legacy_a",
            "alpha_fml052_close_zscore_mr_20",
            "alpha_legacy_b",
            "alpha_fml006_vp_corr_10",
        ]
        val_ics = {
            "alpha_legacy_a": 0.02,
            "alpha_fml052_close_zscore_mr_20": 0.01,
            "alpha_legacy_b": 0.03,
            "alpha_fml006_vp_corr_10": 0.04,
        }
        filtered, excluded = engine.filter_fallback_by_winner_guard(
            fallback, val_ics
        )
        allowlist_set = set(engine.formulaic_winner_allowlist)
        for alpha in filtered:
            assert alpha in allowlist_set, \
                f"Fallback pool contains non-allowlist alpha '{alpha}'"
        assert "alpha_legacy_a" in excluded
        assert "alpha_legacy_b" in excluded

    def test_fallback_filter_all_excluded_returns_empty(self):
        """When all fallback excluded, returns empty (not originals)."""
        engine = _make_mock_engine(winner_guard=True)
        fallback = ["alpha_legacy_x", "alpha_legacy_y", "alpha_legacy_z"]
        val_ics = {
            "alpha_legacy_x": 0.01,
            "alpha_legacy_y": 0.02,
            "alpha_legacy_z": 0.03,
        }
        filtered, excluded = engine.filter_fallback_by_winner_guard(
            fallback, val_ics
        )
        assert filtered == [], \
            "Must return empty list — no legacy re-admission"
        assert set(excluded) == set(fallback)

    def test_evidence_has_no_guard_candidates_key(self):
        """Evidence dict must include no_guard_candidates key."""
        engine = _make_mock_engine(winner_guard=True)
        _, evidence = engine.apply_formulaic_winner_guard(
            ["alpha_fml052_close_zscore_mr_20"],
            {"alpha_fml052_close_zscore_mr_20": 0.02},
        )
        assert "no_guard_candidates" in evidence
        assert evidence["no_guard_candidates"] is False

    def test_guard_off_no_guard_candidates_false(self):
        """When guard off, no_guard_candidates must be False."""
        engine = _make_mock_engine(winner_guard=False)
        _, evidence = engine.apply_formulaic_winner_guard(
            ["alpha_legacy_1"], {"alpha_legacy_1": 0.05}
        )
        assert evidence["no_guard_candidates"] is False

    def test_min_val_ic_filter_on_allowlist_fallback(self):
        """Allowlist fallback respects min_val_ic threshold."""
        engine = _make_mock_engine(winner_guard=True, min_val_ic=0.03)
        candidates = ["alpha_legacy_1"]
        val_ics = {
            "alpha_legacy_1": -0.01,
            # fml052 has IC=0.02, below min_val_ic=0.03
            "alpha_fml052_close_zscore_mr_20": 0.02,
            # fml045 has IC=0.04, above threshold
            "alpha_fml045_liq_turnover_5": 0.04,
        }
        filtered, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        # fml052 below threshold, should not be in fallback
        assert "alpha_fml052_close_zscore_mr_20" not in filtered
        # fml045 above threshold, should be in fallback
        assert "alpha_fml045_liq_turnover_5" in filtered
        assert evidence["fallback_used"] is True

    def test_contract_no_legacy_in_any_guard_enabled_pool(self):
        """Comprehensive contract: for any combination of candidates and val_ics,
        when guard is enabled, post_guard_alphas contains ONLY allowlist members."""
        engine = _make_mock_engine(winner_guard=True)
        allowlist_set = set(engine.formulaic_winner_allowlist)

        # Scenario 1: mix of allowlist and legacy
        cands = list(allowlist_set) + ["legacy_a", "legacy_b"]
        ics = {a: 0.01 for a in cands}
        _, ev = engine.apply_formulaic_winner_guard(cands, ics)
        for a in ev["post_guard_alphas"]:
            assert a in allowlist_set, f"Contract violated: {a} not in allowlist"

        # Scenario 2: all legacy (triggers fallback path)
        cands2 = ["legacy_a", "legacy_b", "legacy_c"]
        ics2 = {"legacy_a": 0.01, "legacy_b": -0.02, "legacy_c": 0.05}
        _, ev2 = engine.apply_formulaic_winner_guard(cands2, ics2)
        for a in ev2["post_guard_alphas"]:
            assert a in allowlist_set, f"Contract violated: {a} not in allowlist"

        # Scenario 3: all legacy, no allowlist val_ic (no_guard_candidates)
        cands3 = ["legacy_only"]
        ics3 = {"legacy_only": 0.10}
        _, ev3 = engine.apply_formulaic_winner_guard(cands3, ics3)
        assert ev3["post_guard_alphas"] == []
        assert ev3["no_guard_candidates"] is True
