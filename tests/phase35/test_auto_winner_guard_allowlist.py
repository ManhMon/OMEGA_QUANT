"""
Automated Alpha OOS Winner Guard Allowlist Tests
GATE: AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615
[L2-Impl:Role14-Data-Scientist] - 2026-06-15

Verifies that:
  1. Default off — allowlist extension disabled unless explicitly enabled
  2. CLI wiring — --enable-auto-winner-guard-allowlist flag works
  3. Allowlist extension — auto bundle names extend winner guard when enabled
  4. Evidence persistence — new evidence fields populated correctly
  5. Fallback filter — filter_fallback_by_winner_guard also extends allowlist
  6. No behavior change when disabled — backward compatible

PIT Safety: No real data loaded. Synthetic data tests and source inspection only.
"""

import argparse
import json
import os
import re
import sys
import types
from pathlib import Path

import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts')))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_phase35_source():
    """Read phase35.py source."""
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "src" / "omega" / "quant" / "alpha" / "phase35.py"
    )
    return path.read_text(encoding="utf-8")


def _get_run_script_source():
    """Read run_phase35_backtest.py source."""
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "scripts" / "run_phase35_backtest.py"
    )
    return path.read_text(encoding="utf-8")


def _make_engine(**kwargs):
    """Create a Phase35WalkForwardEngine with a dummy alpha module."""
    from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
    dummy_module = types.ModuleType("dummy_alpha")
    dummy_module.PHASE34_ALPHA_COLUMNS = []
    dummy_module.compute_phase34_microstructure_alphas = lambda df, **kw: df
    return Phase35WalkForwardEngine(alpha_module=dummy_module, **kwargs)


AUTO_BUNDLE_NAMES = [
    "auto_rsi_14",
    "auto_mr_zscore_20",
    "auto_mom_ret_60",
    "auto_mom_ret_20",
    "auto_vol_std_ratio_10_30",
]

BASE_FORMULAIC_ALLOWLIST = [
    "alpha_fml052_close_zscore_mr_20",
    "alpha_fml012_mean_rev_rank_10",
    "alpha_fml045_liq_turnover_5",
    "alpha_fml067_vol_price_diverge_10",
    "alpha_fml006_vp_corr_10",
]


# ---------------------------------------------------------------------------
# Tests: Default Off
# ---------------------------------------------------------------------------

class TestDefaultOff:
    """Verify allowlist extension is disabled by default."""

    def test_engine_default_auto_allowlist_disabled(self):
        """Phase35 engine should have auto winner guard allowlist off."""
        engine = _make_engine()
        assert engine.enable_auto_winner_guard_allowlist is False

    def test_engine_explicit_false(self):
        """Explicit False should be accepted."""
        engine = _make_engine(enable_auto_winner_guard_allowlist=False)
        assert engine.enable_auto_winner_guard_allowlist is False

    def test_engine_must_be_bool(self):
        """Non-bool value should raise ValueError."""
        with pytest.raises(ValueError, match="enable_auto_winner_guard_allowlist"):
            _make_engine(enable_auto_winner_guard_allowlist="yes")

    def test_engine_must_be_bool_int_rejected(self):
        """Integer value should raise ValueError."""
        with pytest.raises(ValueError, match="enable_auto_winner_guard_allowlist"):
            _make_engine(enable_auto_winner_guard_allowlist=1)


# ---------------------------------------------------------------------------
# Tests: Allowlist Extension Logic
# ---------------------------------------------------------------------------

class TestAllowlistExtension:
    """Verify allowlist extends winner guard when enabled."""

    def test_guard_disabled_allowlist_still_passed_through(self):
        """When formulaic_winner_guard=False, all candidates pass through."""
        engine = _make_engine(
            formulaic_winner_guard=False,
            enable_auto_winner_guard_allowlist=True,
            enable_automated_oos_bundle=True,
        )
        candidates = AUTO_BUNDLE_NAMES + ["alpha_p34_close_auction_drift_10"]
        val_ics = {a: 0.05 for a in candidates}
        result, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        assert result == candidates
        assert evidence["guard_enabled"] is False
        assert evidence["auto_winner_guard_allowlist_enabled"] is True

    def test_guard_enabled_no_auto_allowlist_blocks_auto(self):
        """Without auto allowlist, auto alphas are blocked by winner guard."""
        engine = _make_engine(
            formulaic_winner_guard=True,
            enable_auto_winner_guard_allowlist=False,
            enable_automated_oos_bundle=True,
        )
        candidates = ["auto_rsi_14", "auto_mr_zscore_20"] + BASE_FORMULAIC_ALLOWLIST[:2]
        val_ics = {a: 0.05 for a in candidates}
        result, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        # Auto alphas should be excluded
        assert "auto_rsi_14" not in result
        assert "auto_mr_zscore_20" not in result
        # Base allowlist members should pass
        for al in BASE_FORMULAIC_ALLOWLIST[:2]:
            assert al in result
        assert "auto_rsi_14" in evidence["excluded_alphas"]

    def test_guard_enabled_auto_allowlist_passes_auto(self):
        """With auto allowlist enabled, auto alphas pass the winner guard."""
        engine = _make_engine(
            formulaic_winner_guard=True,
            enable_auto_winner_guard_allowlist=True,
            enable_automated_oos_bundle=True,
        )
        candidates = AUTO_BUNDLE_NAMES + BASE_FORMULAIC_ALLOWLIST[:2]
        val_ics = {a: 0.05 for a in candidates}
        result, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        # All auto alphas should now pass
        for auto_name in AUTO_BUNDLE_NAMES:
            assert auto_name in result, (
                f"{auto_name} should be in post_guard_alphas"
            )
        # Base allowlist members should also pass
        for al in BASE_FORMULAIC_ALLOWLIST[:2]:
            assert al in result
        # No excluded alphas
        assert len(evidence["excluded_alphas"]) == 0

    def test_auto_allowlist_without_oos_bundle_no_extension(self):
        """Auto allowlist requires OOS bundle to be enabled."""
        engine = _make_engine(
            formulaic_winner_guard=True,
            enable_auto_winner_guard_allowlist=True,
            enable_automated_oos_bundle=False,
        )
        candidates = ["auto_rsi_14"] + BASE_FORMULAIC_ALLOWLIST[:2]
        val_ics = {a: 0.05 for a in candidates}
        result, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        # Without OOS bundle, auto allowlist should NOT extend
        assert "auto_rsi_14" not in result
        assert evidence["auto_winner_guard_allowlist_names"] == []

    def test_effective_allowlist_contains_all_names(self):
        """Evidence allowlist should contain base + auto names when enabled."""
        engine = _make_engine(
            formulaic_winner_guard=True,
            enable_auto_winner_guard_allowlist=True,
            enable_automated_oos_bundle=True,
        )
        candidates = AUTO_BUNDLE_NAMES + BASE_FORMULAIC_ALLOWLIST
        val_ics = {a: 0.05 for a in candidates}
        _, evidence = engine.apply_formulaic_winner_guard(candidates, val_ics)
        effective = evidence["allowlist"]
        for name in BASE_FORMULAIC_ALLOWLIST:
            assert name in effective
        for name in AUTO_BUNDLE_NAMES:
            assert name in effective
        assert evidence["base_allowlist"] == BASE_FORMULAIC_ALLOWLIST
        assert evidence["auto_winner_guard_allowlist_names"] == AUTO_BUNDLE_NAMES

    def test_min_val_ic_still_applies_to_auto(self):
        """Auto alphas must still meet min_val_ic threshold."""
        engine = _make_engine(
            formulaic_winner_guard=True,
            enable_auto_winner_guard_allowlist=True,
            enable_automated_oos_bundle=True,
            formulaic_winner_min_val_ic=0.02,
        )
        candidates = ["auto_rsi_14", "auto_mr_zscore_20"] + BASE_FORMULAIC_ALLOWLIST[:2]
        val_ics = {
            "auto_rsi_14": 0.05,       # passes
            "auto_mr_zscore_20": 0.01,  # fails (< 0.02)
        }
        for al in BASE_FORMULAIC_ALLOWLIST[:2]:
            val_ics[al] = 0.05
        result, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        assert "auto_rsi_14" in result
        assert "auto_mr_zscore_20" in evidence["excluded_alphas"]


# ---------------------------------------------------------------------------
# Tests: Fallback Filter Extension
# ---------------------------------------------------------------------------

class TestFallbackFilterExtension:
    """Verify filter_fallback_by_winner_guard also extends allowlist."""

    def test_fallback_filter_blocks_auto_by_default(self):
        """Without auto allowlist, auto alphas excluded from fallback."""
        engine = _make_engine(
            formulaic_winner_guard=True,
            enable_auto_winner_guard_allowlist=False,
            enable_automated_oos_bundle=True,
        )
        fallback = ["auto_rsi_14", "auto_mr_zscore_20", "alpha_fml052_close_zscore_mr_20"]
        val_ics = {a: 0.05 for a in fallback}
        filtered, excluded = engine.filter_fallback_by_winner_guard(
            fallback, val_ics
        )
        assert "auto_rsi_14" not in filtered
        assert "auto_rsi_14" in excluded

    def test_fallback_filter_passes_auto_with_allowlist(self):
        """With auto allowlist, auto alphas pass fallback filter."""
        engine = _make_engine(
            formulaic_winner_guard=True,
            enable_auto_winner_guard_allowlist=True,
            enable_automated_oos_bundle=True,
        )
        fallback = AUTO_BUNDLE_NAMES + ["alpha_fml052_close_zscore_mr_20"]
        val_ics = {a: 0.05 for a in fallback}
        filtered, excluded = engine.filter_fallback_by_winner_guard(
            fallback, val_ics
        )
        for name in AUTO_BUNDLE_NAMES:
            assert name in filtered, (
                f"{name} should pass fallback filter with allowlist"
            )
        assert "alpha_fml052_close_zscore_mr_20" in filtered
        assert len(excluded) == 0

    def test_fallback_filter_guard_disabled_passes_all(self):
        """When guard disabled, all fallback alphas pass through."""
        engine = _make_engine(
            formulaic_winner_guard=False,
            enable_auto_winner_guard_allowlist=True,
            enable_automated_oos_bundle=True,
        )
        fallback = AUTO_BUNDLE_NAMES + ["random_alpha"]
        val_ics = {a: 0.05 for a in fallback}
        filtered, excluded = engine.filter_fallback_by_winner_guard(
            fallback, val_ics
        )
        assert filtered == fallback
        assert excluded == []


# ---------------------------------------------------------------------------
# Tests: Evidence Fields
# ---------------------------------------------------------------------------

class TestEvidenceFields:
    """Verify new evidence fields are correctly populated."""

    def test_evidence_has_auto_allowlist_fields(self):
        """Evidence dict must have auto_winner_guard_allowlist_* keys."""
        engine = _make_engine(
            formulaic_winner_guard=True,
            enable_auto_winner_guard_allowlist=True,
            enable_automated_oos_bundle=True,
        )
        candidates = AUTO_BUNDLE_NAMES + BASE_FORMULAIC_ALLOWLIST
        val_ics = {a: 0.05 for a in candidates}
        _, evidence = engine.apply_formulaic_winner_guard(candidates, val_ics)
        assert "auto_winner_guard_allowlist_enabled" in evidence
        assert evidence["auto_winner_guard_allowlist_enabled"] is True
        assert "auto_winner_guard_allowlist_names" in evidence
        assert evidence["auto_winner_guard_allowlist_names"] == AUTO_BUNDLE_NAMES
        assert "base_allowlist" in evidence
        assert evidence["base_allowlist"] == BASE_FORMULAIC_ALLOWLIST

    def test_evidence_auto_disabled_fields(self):
        """When auto allowlist disabled, names should be empty."""
        engine = _make_engine(
            formulaic_winner_guard=True,
            enable_auto_winner_guard_allowlist=False,
            enable_automated_oos_bundle=True,
        )
        candidates = BASE_FORMULAIC_ALLOWLIST
        val_ics = {a: 0.05 for a in candidates}
        _, evidence = engine.apply_formulaic_winner_guard(candidates, val_ics)
        assert evidence["auto_winner_guard_allowlist_enabled"] is False
        assert evidence["auto_winner_guard_allowlist_names"] == []
        assert evidence["base_allowlist"] == BASE_FORMULAIC_ALLOWLIST

    def test_evidence_is_json_serializable(self):
        """Evidence dict must be JSON-serializable."""
        engine = _make_engine(
            formulaic_winner_guard=True,
            enable_auto_winner_guard_allowlist=True,
            enable_automated_oos_bundle=True,
        )
        candidates = AUTO_BUNDLE_NAMES + BASE_FORMULAIC_ALLOWLIST
        val_ics = {a: 0.05 for a in candidates}
        _, evidence = engine.apply_formulaic_winner_guard(candidates, val_ics)
        json_str = json.dumps(evidence)
        round_trip = json.loads(json_str)
        assert round_trip["auto_winner_guard_allowlist_enabled"] is True
        assert round_trip["auto_winner_guard_allowlist_names"] == AUTO_BUNDLE_NAMES

    def test_fold_metrics_winner_guard_evidence_carries_fields(self):
        """FoldMetrics winner_guard_evidence should carry auto allowlist fields."""
        from omega.quant.alpha.phase35 import FoldMetrics
        evidence = {
            "gate": "FORMULAIC_WINNER_SELECTION_GUARD_20260614",
            "guard_enabled": True,
            "auto_winner_guard_allowlist_enabled": True,
            "auto_winner_guard_allowlist_names": AUTO_BUNDLE_NAMES,
            "base_allowlist": BASE_FORMULAIC_ALLOWLIST,
            "allowlist": BASE_FORMULAIC_ALLOWLIST + AUTO_BUNDLE_NAMES,
            "pre_guard_alphas": AUTO_BUNDLE_NAMES,
            "post_guard_alphas": AUTO_BUNDLE_NAMES,
            "excluded_alphas": [],
            "val_ics_used": {},
            "min_val_ic": 0.0,
            "fallback_used": False,
            "no_guard_candidates": False,
            "pit_safe": True,
        }
        fm = FoldMetrics(
            fold_id=0, train_start="2022-01-01", train_end="2022-06-30",
            test_start="2022-07-01", test_end="2022-09-30",
            winner_guard_evidence=evidence,
        )
        assert fm.winner_guard_evidence["auto_winner_guard_allowlist_enabled"] is True
        assert fm.winner_guard_evidence["auto_winner_guard_allowlist_names"] == AUTO_BUNDLE_NAMES
        # Verify JSON-serializable
        json_str = json.dumps(fm.winner_guard_evidence)
        assert len(json_str) > 0


# ---------------------------------------------------------------------------
# Tests: CLI Wiring
# ---------------------------------------------------------------------------

class TestCLIWiring:
    """Verify CLI flag is properly defined."""

    def test_cli_has_enable_flag(self):
        """run_phase35_backtest.py should have --enable-auto-winner-guard-allowlist."""
        source = _get_run_script_source()
        assert "--enable-auto-winner-guard-allowlist" in source

    def test_cli_has_gate_reference(self):
        """run_phase35_backtest.py should reference the gate ID."""
        source = _get_run_script_source()
        assert "AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615" in source

    def test_cli_wires_to_engine(self):
        """run_phase35_backtest.py should pass flag to engine."""
        source = _get_run_script_source()
        assert "enable_auto_winner_guard_allowlist" in source

    def test_cli_logs_config(self):
        """run_phase35_backtest.py should log the flag."""
        source = _get_run_script_source()
        assert "Auto Winner Guard Allowlist" in source

    def test_cli_persists_in_config_output(self):
        """run_phase35_backtest.py should persist flag in config output."""
        source = _get_run_script_source()
        assert '"enable_auto_winner_guard_allowlist"' in source

    def test_cli_help_text_mentions_auto_alphas(self):
        """CLI help should mention auto bundle alpha names."""
        source = _get_run_script_source()
        assert "auto_rsi_14" in source


# ---------------------------------------------------------------------------
# Tests: Source Inspection
# ---------------------------------------------------------------------------

class TestSourceInspection:
    """Verify source code patterns for the allowlist gate."""

    def test_gate_id_constant_exists(self):
        """phase35.py should define AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_GATE_ID."""
        from omega.quant.alpha.phase35 import (
            AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_GATE_ID,
        )
        assert AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_GATE_ID == (
            "AUTOMATED_ALPHA_OOS_WINNER_GUARD_ALLOWLIST_20260615"
        )

    def test_phase35_has_allowlist_param(self):
        """phase35.py constructor should accept enable_auto_winner_guard_allowlist."""
        source = _get_phase35_source()
        assert "enable_auto_winner_guard_allowlist" in source

    def test_phase35_apply_formulaic_winner_guard_uses_effective_allowlist(self):
        """apply_formulaic_winner_guard should build effective allowlist."""
        source = _get_phase35_source()
        assert "_effective_allowlist" in source
        assert "_auto_allowlist_names" in source

    def test_phase35_filter_fallback_uses_effective_allowlist(self):
        """filter_fallback_by_winner_guard should use effective allowlist."""
        source = _get_phase35_source()
        # The filter function should reference enable_auto_winner_guard_allowlist
        assert source.count("enable_auto_winner_guard_allowlist") >= 3

    def test_no_live_promotion(self):
        """phase35.py should not promote auto allowlist to live."""
        source = _get_phase35_source()
        assert "opt-in" in source.lower() or "default disabled" in source.lower()


# ---------------------------------------------------------------------------
# Tests: Serialize Fold Details
# ---------------------------------------------------------------------------

class TestSerializeFoldDetails:
    """Verify serialize_fold_details includes winner guard evidence with auto allowlist."""

    def test_serialize_includes_auto_allowlist_evidence(self):
        """serialize_fold_details must include winner_guard_evidence with auto fields."""
        from omega.quant.alpha.phase35 import FoldMetrics
        from run_phase35_backtest import serialize_fold_details

        evidence = {
            "gate": "FORMULAIC_WINNER_SELECTION_GUARD_20260614",
            "guard_enabled": True,
            "auto_winner_guard_allowlist_enabled": True,
            "auto_winner_guard_allowlist_names": AUTO_BUNDLE_NAMES,
            "base_allowlist": BASE_FORMULAIC_ALLOWLIST,
            "allowlist": BASE_FORMULAIC_ALLOWLIST + AUTO_BUNDLE_NAMES,
            "pre_guard_alphas": AUTO_BUNDLE_NAMES + BASE_FORMULAIC_ALLOWLIST,
            "post_guard_alphas": AUTO_BUNDLE_NAMES + BASE_FORMULAIC_ALLOWLIST,
            "excluded_alphas": [],
            "val_ics_used": {a: 0.05 for a in AUTO_BUNDLE_NAMES},
            "min_val_ic": 0.0,
            "fallback_used": False,
            "no_guard_candidates": False,
            "pit_safe": True,
        }
        fm = FoldMetrics(
            fold_id=1, train_start="2022-01-01", train_end="2022-12-31",
            test_start="2023-01-01", test_end="2023-06-30",
            winner_guard_evidence=evidence,
        )
        result = serialize_fold_details(fm)
        assert "winner_guard_evidence" in result
        wg = result["winner_guard_evidence"]
        assert wg["auto_winner_guard_allowlist_enabled"] is True
        assert wg["auto_winner_guard_allowlist_names"] == AUTO_BUNDLE_NAMES
        assert wg["base_allowlist"] == BASE_FORMULAIC_ALLOWLIST
        for name in AUTO_BUNDLE_NAMES:
            assert name in wg["post_guard_alphas"]
        # Verify JSON round-trip
        json_str = json.dumps(result)
        round_trip = json.loads(json_str)
        assert round_trip["winner_guard_evidence"]["auto_winner_guard_allowlist_enabled"] is True


# ---------------------------------------------------------------------------
# Tests: Backward Compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Verify no behavior change when flag is not set."""

    def test_existing_behavior_preserved_default(self):
        """Default engine behavior should be identical to pre-gate behavior."""
        engine = _make_engine(
            formulaic_winner_guard=True,
        )
        candidates = BASE_FORMULAIC_ALLOWLIST + ["random_alpha"]
        val_ics = {a: 0.05 for a in candidates}
        result, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        # Base allowlist members pass, random excluded
        for al in BASE_FORMULAIC_ALLOWLIST:
            assert al in result
        assert "random_alpha" in evidence["excluded_alphas"]

    def test_existing_behavior_preserved_explicit_false(self):
        """Explicit False should preserve original behavior."""
        engine = _make_engine(
            formulaic_winner_guard=True,
            enable_auto_winner_guard_allowlist=False,
        )
        candidates = AUTO_BUNDLE_NAMES + BASE_FORMULAIC_ALLOWLIST
        val_ics = {a: 0.05 for a in candidates}
        result, evidence = engine.apply_formulaic_winner_guard(
            candidates, val_ics
        )
        for name in AUTO_BUNDLE_NAMES:
            assert name not in result
            assert name in evidence["excluded_alphas"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
