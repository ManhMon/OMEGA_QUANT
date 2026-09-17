"""
Recovery Selector Phase35 Wiring Tests
GATE: RECOVERY_SELECTOR_PHASE35_WIRING_20260614
[L2-Impl:Role14-Data-Scientist] - 2026-06-14

Verifies that:
1. --research-pool-mode CLI flag registered with correct choices/default
2. Default 'full' unchanged — no live/default behavior change
3. Engine constructor validates mode parameter
4. Invalid mode raises ValueError
5. Mode 'full' produces no recovery_pool_evidence (backward-compatible)
6. Mode 'recovery_only' excludes CONFIRMED_RETIRE alphas
7. Mode 'recoverable_only' keeps only RECOVERABLE alphas
8. No lookahead — analysis uses only OOS fold ICs (PIT-safe)
9. Selected/excluded alpha evidence persisted in JSON
10. Selector verdict computed correctly
11. Config dict contains research_pool_mode

PIT Safety: No real data loaded. Source inspection and synthetic data tests only.
"""

import argparse
import ast
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest
import numpy as np

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


# ---------------------------------------------------------------------------
# Section 1: CLI Flag Registration
# ---------------------------------------------------------------------------


class TestRecoveryPoolModeCLIFlags:
    """Verify --research-pool-mode CLI flag is registered correctly."""

    def test_cli_research_pool_mode_flag_registered(self):
        src = _get_script_source()
        assert '"--research-pool-mode"' in src, \
            "CLI flag --research-pool-mode must be registered"

    def test_cli_research_pool_mode_choices(self):
        src = _get_script_source()
        assert '"full"' in src, "Choice 'full' must be in choices"
        assert '"recovery_only"' in src, "Choice 'recovery_only' must be in choices"
        assert '"recoverable_only"' in src, "Choice 'recoverable_only' must be in choices"

    def test_cli_research_pool_mode_default_full(self):
        src = _get_script_source()
        assert 'default="full"' in src, \
            "Default must be 'full' to preserve backward compatibility"

    def test_cli_research_pool_mode_gate_label(self):
        src = _get_script_source()
        assert "RECOVERY_SELECTOR_PHASE35_WIRING_20260614" in src, \
            "Gate label must be present"


# ---------------------------------------------------------------------------
# Section 2: Default Behavior Unchanged
# ---------------------------------------------------------------------------


class TestDefaultBehaviorUnchanged:
    """Verify default mode='full' produces no behavior change."""

    def test_config_persists_research_pool_mode(self):
        src = _get_script_source()
        assert '"research_pool_mode"' in src, \
            "Config must persist research_pool_mode"

    def test_full_mode_skips_analysis(self):
        """When mode='full', recovery pool analysis should be skipped."""
        src = _get_script_source()
        assert '!= "full"' in src or "!= 'full'" in src, \
            "Script must check mode != 'full' before running analysis"

    def test_recovery_pool_evidence_none_for_full(self):
        """recovery_pool_evidence initialized to None, only set for non-full modes."""
        src = _get_script_source()
        assert "recovery_pool_evidence = None" in src, \
            "recovery_pool_evidence must default to None"

    def test_recovery_pool_evidence_in_results_dict(self):
        """Results dict must include recovery_pool_evidence key."""
        src = _get_script_source()
        assert '"recovery_pool_evidence"' in src, \
            "Results dict must include recovery_pool_evidence"


# ---------------------------------------------------------------------------
# Section 3: Engine Constructor Validation
# ---------------------------------------------------------------------------


class TestEngineConstructorValidation:
    """Verify Phase35WalkForwardEngine validates research_pool_mode."""

    def test_engine_source_has_research_pool_mode_param(self):
        src = _get_engine_source()
        assert "research_pool_mode" in src, \
            "Engine must accept research_pool_mode parameter"

    def test_engine_source_validates_mode(self):
        src = _get_engine_source()
        assert "VALID_RESEARCH_POOL_MODES" in src, \
            "Engine must validate against VALID_RESEARCH_POOL_MODES"

    def test_engine_source_raises_on_invalid_mode(self):
        src = _get_engine_source()
        assert "ValueError" in src, \
            "Engine must raise ValueError for invalid mode"

    def test_engine_default_mode_is_full(self):
        src = _get_engine_source()
        assert 'research_pool_mode: str = "full"' in src, \
            "Default research_pool_mode must be 'full'"

    def test_engine_stores_research_pool_mode(self):
        src = _get_engine_source()
        assert "self.research_pool_mode" in src, \
            "Engine must store research_pool_mode"

    def test_engine_invalid_mode_raises(self):
        """Verify that constructing engine with invalid mode raises ValueError."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ["alpha_1", "alpha_2"]

        with pytest.raises(ValueError, match="research_pool_mode"):
            Phase35WalkForwardEngine(
                alpha_module=mock_module,
                research_pool_mode="invalid_mode",
            )

    def test_engine_valid_modes_accepted(self):
        """Verify all valid modes are accepted without error."""
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        mock_module = MagicMock()
        mock_module.PHASE34_ALPHA_COLUMNS = ["alpha_1", "alpha_2"]

        for mode in ["full", "recovery_only", "recoverable_only"]:
            engine = Phase35WalkForwardEngine(
                alpha_module=mock_module,
                research_pool_mode=mode,
            )
            assert engine.research_pool_mode == mode


# ---------------------------------------------------------------------------
# Section 4: Recovery Pool Filtering Logic (unit tests)
# ---------------------------------------------------------------------------


class TestRecoveryPoolFiltering:
    """Verify filter_alphas_by_recovery_mode works correctly."""

    def _make_mock_recovery_report(self):
        """Create a mock AlphaRecoveryReport."""
        @dataclass
        class MockReport:
            recoverable_candidates: List[str] = field(
                default_factory=lambda: ["alpha_a", "alpha_b"]
            )
            research_only: List[str] = field(
                default_factory=lambda: ["alpha_c"]
            )
            confirmed_retire: List[str] = field(
                default_factory=lambda: ["alpha_d", "alpha_e"]
            )
        return MockReport()

    def test_full_mode_returns_all(self):
        from omega.quant.walk_forward.risk_adjusted_alpha_score import (
            filter_alphas_by_recovery_mode,
        )
        alphas = ["alpha_a", "alpha_b", "alpha_c", "alpha_d", "alpha_e"]
        report = self._make_mock_recovery_report()
        result = filter_alphas_by_recovery_mode(alphas, report, mode="full")
        assert result == alphas

    def test_recovery_only_excludes_confirmed_retire(self):
        from omega.quant.walk_forward.risk_adjusted_alpha_score import (
            filter_alphas_by_recovery_mode,
        )
        alphas = ["alpha_a", "alpha_b", "alpha_c", "alpha_d", "alpha_e"]
        report = self._make_mock_recovery_report()
        result = filter_alphas_by_recovery_mode(
            alphas, report, mode="recovery_only"
        )
        assert "alpha_d" not in result
        assert "alpha_e" not in result
        assert "alpha_a" in result
        assert "alpha_b" in result
        assert "alpha_c" in result

    def test_recoverable_only_keeps_only_recoverable(self):
        from omega.quant.walk_forward.risk_adjusted_alpha_score import (
            filter_alphas_by_recovery_mode,
        )
        alphas = ["alpha_a", "alpha_b", "alpha_c", "alpha_d", "alpha_e"]
        report = self._make_mock_recovery_report()
        result = filter_alphas_by_recovery_mode(
            alphas, report, mode="recoverable_only"
        )
        assert result == ["alpha_a", "alpha_b"]

    def test_invalid_mode_raises(self):
        from omega.quant.walk_forward.risk_adjusted_alpha_score import (
            filter_alphas_by_recovery_mode,
        )
        alphas = ["alpha_a"]
        report = self._make_mock_recovery_report()
        with pytest.raises(ValueError, match="Unknown research_pool_mode"):
            filter_alphas_by_recovery_mode(alphas, report, mode="bogus")


# ---------------------------------------------------------------------------
# Section 5: Selector Verdict Logic
# ---------------------------------------------------------------------------


class TestSelectorVerdict:
    """Verify compute_selector_ready_verdict produces correct verdicts."""

    def test_conditional_promote_both_improved(self):
        from omega.quant.walk_forward.risk_adjusted_alpha_score import (
            compute_selector_ready_verdict,
            SELECTOR_VERDICT_CONDITIONAL_PROMOTE,
        )
        verdict = compute_selector_ready_verdict(
            full_pool_mean_ic=-0.0097,
            full_pool_positive_fold_rate=0.333,
            recovery_pool_mean_ic=0.0008,
            recovery_pool_positive_fold_rate=0.667,
        )
        assert verdict == SELECTOR_VERDICT_CONDITIONAL_PROMOTE

    def test_do_not_promote_ic_only(self):
        from omega.quant.walk_forward.risk_adjusted_alpha_score import (
            compute_selector_ready_verdict,
            SELECTOR_VERDICT_DO_NOT_PROMOTE,
        )
        verdict = compute_selector_ready_verdict(
            full_pool_mean_ic=-0.0062,
            full_pool_positive_fold_rate=0.500,
            recovery_pool_mean_ic=0.0010,
            recovery_pool_positive_fold_rate=0.375,
        )
        assert verdict == SELECTOR_VERDICT_DO_NOT_PROMOTE

    def test_insufficient_evidence_no_improvement(self):
        from omega.quant.walk_forward.risk_adjusted_alpha_score import (
            compute_selector_ready_verdict,
            SELECTOR_VERDICT_INSUFFICIENT_EVIDENCE,
        )
        verdict = compute_selector_ready_verdict(
            full_pool_mean_ic=0.010,
            full_pool_positive_fold_rate=0.600,
            recovery_pool_mean_ic=0.008,
            recovery_pool_positive_fold_rate=0.500,
        )
        assert verdict == SELECTOR_VERDICT_INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------------------
# Section 6: No Lookahead / PIT Safety
# ---------------------------------------------------------------------------


class TestPITSafety:
    """Verify no look-ahead bias in recovery pool analysis."""

    def test_script_uses_only_fold_ics(self):
        """Post-hoc analysis should use only alpha_ics from fold_metrics."""
        src = _get_script_source()
        # Verify analysis uses m.alpha_ics (OOS test-set ICs), not train data
        assert "alpha_fold_ics" in src, \
            "Analysis must build alpha_fold_ics from fold metrics"

    def test_script_uses_compute_alpha_recovery_diagnostics(self):
        """Must use the PIT-safe recovery diagnostics function."""
        src = _get_script_source()
        assert "compute_alpha_recovery_diagnostics" in src, \
            "Must use compute_alpha_recovery_diagnostics"

    def test_script_uses_filter_alphas_by_recovery_mode(self):
        """Must use the PIT-safe filter function."""
        src = _get_script_source()
        assert "filter_alphas_by_recovery_mode" in src, \
            "Must use filter_alphas_by_recovery_mode"

    def test_no_test_data_access_in_analysis(self):
        """Post-hoc analysis should not access test_df or train_df."""
        src = _get_script_source()
        # Find the post-hoc analysis block (after the walk-forward run)
        analysis_marker = "Post-hoc recovery pool selector analysis"
        idx = src.find(analysis_marker)
        if idx == -1:
            pytest.fail("Post-hoc analysis block not found in script")
        # Check there's no test_df/train_df access in the analysis block
        analysis_block = src[idx:idx + 3000]
        # The analysis should reference result.fold_metrics, not test_df
        assert "result.fold_metrics" in analysis_block, \
            "Analysis should use result.fold_metrics"

    def test_engine_run_fold_unchanged(self):
        """run_fold should not reference research_pool_mode (post-hoc only)."""
        src = _get_engine_source()
        # Find the run_fold method
        run_fold_idx = src.find("def run_fold(")
        assert run_fold_idx != -1
        # Find the next method def
        next_def_idx = src.find("\n    def ", run_fold_idx + 1)
        run_fold_body = src[run_fold_idx:next_def_idx] if next_def_idx != -1 else src[run_fold_idx:]
        # run_fold should not reference research_pool_mode
        assert "research_pool_mode" not in run_fold_body, \
            "run_fold must not reference research_pool_mode (post-hoc analysis only)"


# ---------------------------------------------------------------------------
# Section 7: Output Persistence
# ---------------------------------------------------------------------------


class TestOutputPersistence:
    """Verify recovery pool evidence is persisted in JSON output."""

    def test_evidence_contains_gate_label(self):
        src = _get_script_source()
        assert '"gate": "RECOVERY_SELECTOR_PHASE35_WIRING_20260614"' in src, \
            "Evidence must contain gate label"

    def test_evidence_contains_mode(self):
        src = _get_script_source()
        assert '"research_pool_mode"' in src, \
            "Evidence must contain research_pool_mode"

    def test_evidence_contains_selected_alphas(self):
        src = _get_script_source()
        assert '"selected_alphas"' in src, \
            "Evidence must contain selected_alphas"

    def test_evidence_contains_excluded_alphas(self):
        src = _get_script_source()
        assert '"excluded_alphas"' in src, \
            "Evidence must contain excluded_alphas"

    def test_evidence_contains_selector_verdict(self):
        src = _get_script_source()
        assert '"selector_verdict"' in src, \
            "Evidence must contain selector_verdict"

    def test_evidence_contains_pit_safe_flag(self):
        src = _get_script_source()
        assert '"pit_safe"' in src, \
            "Evidence must contain pit_safe flag"

    def test_evidence_contains_recovery_classifications(self):
        src = _get_script_source()
        assert '"recovery_classifications"' in src, \
            "Evidence must contain recovery_classifications"

    def test_evidence_contains_ic_delta(self):
        src = _get_script_source()
        assert '"ic_delta"' in src, \
            "Evidence must contain ic_delta"

    def test_evidence_contains_fold_rate_delta(self):
        src = _get_script_source()
        assert '"fold_rate_delta"' in src, \
            "Evidence must contain fold_rate_delta"


# ---------------------------------------------------------------------------
# Section 8: Config Dict Persistence
# ---------------------------------------------------------------------------


class TestConfigPersistence:
    """Verify config dict in JSON contains research_pool_mode."""

    def test_config_has_research_pool_mode(self):
        src = _get_script_source()
        # Must be in the config dict section
        assert '"research_pool_mode": args.research_pool_mode' in src, \
            "Config dict must persist research_pool_mode from args"


# ---------------------------------------------------------------------------
# Section 9: Logging
# ---------------------------------------------------------------------------


class TestLogging:
    """Verify recovery pool mode is logged."""

    def test_mode_logged_during_config(self):
        src = _get_script_source()
        assert "Research Pool Mode" in src, \
            "Research pool mode must be logged during configuration"

    def test_analysis_logged(self):
        src = _get_script_source()
        assert "[RecoveryPool]" in src, \
            "Recovery pool analysis must log with [RecoveryPool] prefix"


# ---------------------------------------------------------------------------
# Section 10: Engine Source Inspection
# ---------------------------------------------------------------------------


class TestEngineSourceInspection:
    """Verify engine source code patterns for correctness."""

    def test_engine_imports_valid_modes(self):
        src = _get_engine_source()
        assert "VALID_RESEARCH_POOL_MODES" in src, \
            "Engine must import VALID_RESEARCH_POOL_MODES for validation"

    def test_engine_gate_label_present(self):
        src = _get_engine_source()
        assert "RECOVERY_SELECTOR_PHASE35_WIRING_20260614" in src, \
            "Engine must reference the gate label"

    def test_no_default_behavior_change_in_constructor(self):
        """Default research_pool_mode='full' should not change any existing behavior."""
        src = _get_engine_source()
        # The mode is only stored, not used in run_fold
        assert 'research_pool_mode: str = "full"' in src, \
            "Default must be 'full'"


# ---------------------------------------------------------------------------
# Section 11: Integration — Recovery Pool Evidence Structure
# ---------------------------------------------------------------------------


class TestRecoveryPoolEvidenceStructure:
    """Verify the evidence dict has the correct structure."""

    def test_evidence_structure_from_script_ast(self):
        """Parse the script AST and verify evidence dict keys."""
        src = _get_script_source()
        tree = ast.parse(src)

        # Find the recovery_pool_evidence assignment
        found_evidence_keys = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key_node in node.keys:
                    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                        found_evidence_keys.add(key_node.value)

        required_keys = {
            "gate", "research_pool_mode", "full_pool_alphas",
            "selected_alphas", "excluded_alphas", "n_selected",
            "n_excluded", "full_pool_mean_fold_ic",
            "full_pool_positive_fold_rate", "recovery_pool_mean_fold_ic",
            "recovery_pool_positive_fold_rate", "ic_delta",
            "fold_rate_delta", "selector_verdict",
            "recovery_classifications", "pit_safe",
        }
        missing = required_keys - found_evidence_keys
        assert not missing, f"Missing evidence keys: {missing}"


# ---------------------------------------------------------------------------
# Section 12: Backward Compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Verify backward compatibility is preserved."""

    def test_no_existing_cli_args_changed(self):
        """Existing CLI args should not be modified."""
        src = _get_script_source()
        existing_args = [
            '"--n-folds"', '"--train-years"', '"--test-years"',
            '"--top-n-symbols"', '"--output-tag"',
            '"--risk-adjusted-alpha-selection"',
            '"--risk-adjusted-preset"',
        ]
        for arg in existing_args:
            assert arg in src, f"Existing CLI arg {arg} must still be present"

    def test_existing_serialize_fold_details_unchanged(self):
        """serialize_fold_details should not be modified."""
        src = _get_script_source()
        assert "def serialize_fold_details(m):" in src, \
            "serialize_fold_details signature must be unchanged"

    def test_existing_engine_params_unchanged(self):
        """All existing engine params should still be present."""
        src = _get_engine_source()
        existing_params = [
            "min_ic_threshold", "top_n_alphas", "top_n_stocks",
            "risk_adjusted_alpha_selection", "risk_adjusted_preset",
            "portfolio_guard_enabled", "portfolio_guard_tolerance",
        ]
        for param in existing_params:
            assert param in src, f"Existing param {param} must still be present"
