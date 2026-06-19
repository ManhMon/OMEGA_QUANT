"""
GATE: DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615
CLI XGBoost Default-Off and Opt-In Tests

[L2-Impl:Role14-DataScientist] - 2026-06-15

Verifies that the Phase 3.5 backtest CLI argument logic:
  1. Defaults to use_xgboost=False (XGBoost disabled)
  2. --enable-xgboost opt-in sets use_xgboost=True
  3. --no-xgboost backward-compat flag still accepted (no-op, default-off)
  4. Help text mentions opt-in research mode and attribution evidence
  5. Combined flags: --enable-xgboost takes precedence

Evidence (E2E A/B, 12-fold walk-forward, 30 symbols, 2015-2026):
  Source: data/phase35_results/phase35_backtest_results_full_e2e_default_clean_v3_wg_fix2_xgboost.json
  Source: data/phase35_results/phase35_backtest_results_full_e2e_default_clean_v3_wg_no_xgb_baseline.json

  XGB ON:  PortfolioIC 0.0157, RawIC 0.0049, CSIC 0.0000
  XGB OFF: PortfolioIC 0.0344, RawIC 0.0200, CSIC 0.0216

  XGBoost degrades all IC metrics — default must be OFF.

PIT Safety: Tests use argparse namespace only; no real data loaded.
"""

import sys
import os
import unittest
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))


# ---------------------------------------------------------------------------
# Helper: Build the parser directly (mirrors run_phase35_backtest.py argparse)
# This avoids importing main() which triggers data loading.
# We replicate only the XGBoost-related flag definitions and the
# use_xgboost derivation logic.
# ---------------------------------------------------------------------------

def _build_xgboost_parser():
    """
    Build a minimal argparse parser that mirrors the XGBoost-related
    flags from scripts/run_phase35_backtest.py.
    """
    parser = argparse.ArgumentParser(
        description="Run Phase 3.5 walk-forward backtest"
    )
    # GATE: DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615
    parser.add_argument(
        "--enable-xgboost",
        action="store_true",
        help=(
            "GATE DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615: "
            "Opt-in to XGBoost research signal path. "
            "XGBoost is DISABLED by default because E2E A/B evidence showed "
            "it degrades signal quality (PortfolioIC 0.0157 vs 0.0344 baseline). "
            "Use this flag only for research experimentation."
        ),
    )
    parser.add_argument(
        "--no-xgboost",
        action="store_true",
        help=(
            "DEPRECATED (no-op). XGBoost is now disabled by default per "
            "GATE DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615. "
            "This flag is preserved for backward compatibility and has no effect."
        ),
    )
    return parser


def _parse_and_derive(argv):
    """Parse argv and apply the use_xgboost derivation logic."""
    parser = _build_xgboost_parser()
    args = parser.parse_args(argv)
    # GATE: DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615
    # Same derivation as in run_phase35_backtest.py
    args.use_xgboost = args.enable_xgboost
    return args


def _get_help_text():
    """Return the help text from the parser."""
    parser = _build_xgboost_parser()
    return parser.format_help()


def _get_action_help(flag_name):
    """Return the help string for a specific flag."""
    parser = _build_xgboost_parser()
    for action in parser._actions:
        if flag_name in action.option_strings:
            return action.help
    return None


# ---------------------------------------------------------------------------
# Tests: Default-off behavior
# ---------------------------------------------------------------------------

class TestXGBoostDefaultOff(unittest.TestCase):
    """GATE: DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615 — default must be OFF."""

    def test_no_flags_means_use_xgboost_false(self):
        """With no XGBoost-related flags, use_xgboost must be False."""
        args = _parse_and_derive([])
        self.assertFalse(
            args.use_xgboost,
            "Default use_xgboost must be False per GATE "
            "DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615"
        )

    def test_enable_xgboost_default_is_false(self):
        """The enable_xgboost attribute must default to False."""
        args = _parse_and_derive([])
        self.assertFalse(args.enable_xgboost)

    def test_no_xgboost_default_is_false(self):
        """The no_xgboost attribute must default to False."""
        args = _parse_and_derive([])
        self.assertFalse(args.no_xgboost)


# ---------------------------------------------------------------------------
# Tests: Opt-in behavior
# ---------------------------------------------------------------------------

class TestXGBoostOptIn(unittest.TestCase):
    """GATE: DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615 — --enable-xgboost opt-in."""

    def test_enable_xgboost_flag_sets_use_xgboost_true(self):
        """--enable-xgboost must set use_xgboost=True."""
        args = _parse_and_derive(['--enable-xgboost'])
        self.assertTrue(
            args.use_xgboost,
            "--enable-xgboost must set use_xgboost=True"
        )

    def test_enable_xgboost_sets_enable_attribute(self):
        """--enable-xgboost must set enable_xgboost=True."""
        args = _parse_and_derive(['--enable-xgboost'])
        self.assertTrue(args.enable_xgboost)


# ---------------------------------------------------------------------------
# Tests: Backward compatibility
# ---------------------------------------------------------------------------

class TestXGBoostBackwardCompat(unittest.TestCase):
    """GATE: DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615 — --no-xgboost compat."""

    def test_no_xgboost_flag_accepted(self):
        """--no-xgboost must be accepted without error (backward compat)."""
        args = _parse_and_derive(['--no-xgboost'])
        self.assertTrue(args.no_xgboost, "--no-xgboost flag must be parseable")

    def test_no_xgboost_flag_means_use_xgboost_false(self):
        """--no-xgboost alone must result in use_xgboost=False."""
        args = _parse_and_derive(['--no-xgboost'])
        self.assertFalse(
            args.use_xgboost,
            "--no-xgboost must result in use_xgboost=False (deprecated no-op)"
        )

    def test_no_xgboost_and_enable_xgboost_together(self):
        """If both --no-xgboost and --enable-xgboost are set, enable wins (opt-in)."""
        args = _parse_and_derive(['--no-xgboost', '--enable-xgboost'])
        self.assertTrue(
            args.use_xgboost,
            "--enable-xgboost must take precedence over deprecated --no-xgboost"
        )


# ---------------------------------------------------------------------------
# Tests: Help text includes evidence attribution
# ---------------------------------------------------------------------------

class TestXGBoostHelpText(unittest.TestCase):
    """GATE: DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615 — help text must cite opt-in."""

    def test_help_mentions_enable_xgboost(self):
        """Help text must include --enable-xgboost."""
        help_text = _get_help_text()
        self.assertIn("--enable-xgboost", help_text)

    def test_help_mentions_no_xgboost(self):
        """Help text must include --no-xgboost (backward compat)."""
        help_text = _get_help_text()
        self.assertIn("--no-xgboost", help_text)

    def test_enable_xgboost_help_mentions_research(self):
        """--enable-xgboost help must mention 'research' mode."""
        help_str = _get_action_help('--enable-xgboost')
        self.assertIsNotNone(help_str)
        self.assertIn(
            "research",
            help_str.lower(),
            "--enable-xgboost help must mention 'research' mode"
        )

    def test_enable_xgboost_help_mentions_disabled_by_default(self):
        """--enable-xgboost help must state XGBoost is DISABLED by default."""
        help_str = _get_action_help('--enable-xgboost')
        self.assertIsNotNone(help_str)
        self.assertIn(
            "DISABLED by default",
            help_str,
            "--enable-xgboost help must state XGBoost is DISABLED by default"
        )

    def test_enable_xgboost_help_mentions_evidence(self):
        """--enable-xgboost help must reference the gate name."""
        help_str = _get_action_help('--enable-xgboost')
        self.assertIsNotNone(help_str)
        self.assertIn(
            "DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615",
            help_str,
            "--enable-xgboost help must cite the gate"
        )

    def test_no_xgboost_help_mentions_deprecated(self):
        """--no-xgboost help must mention DEPRECATED."""
        help_str = _get_action_help('--no-xgboost')
        self.assertIsNotNone(help_str)
        self.assertIn(
            "DEPRECATED",
            help_str,
            "--no-xgboost help must state it is DEPRECATED"
        )

    def test_no_xgboost_help_mentions_backward_compat(self):
        """--no-xgboost help must mention backward compatibility."""
        help_str = _get_action_help('--no-xgboost')
        self.assertIsNotNone(help_str)
        self.assertIn(
            "backward compatibility",
            help_str.lower(),
            "--no-xgboost help must mention backward compatibility"
        )


# ---------------------------------------------------------------------------
# Tests: Verify script file contains gate logic (integration check)
# ---------------------------------------------------------------------------

class TestScriptFileContainsGate(unittest.TestCase):
    """Verify the actual script file has the gate implementation."""

    def _read_script(self):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'scripts',
            'run_phase35_backtest.py'
        )
        with open(script_path, 'r') as f:
            return f.read()

    def test_script_has_enable_xgboost_flag(self):
        """Script must define --enable-xgboost flag."""
        src = self._read_script()
        self.assertIn('--enable-xgboost', src)

    def test_script_has_gate_citation(self):
        """Script must cite the gate name."""
        src = self._read_script()
        self.assertIn('DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615', src)

    def test_script_derives_use_xgboost_from_enable(self):
        """Script must set use_xgboost from enable_xgboost (not from no_xgboost)."""
        src = self._read_script()
        self.assertIn('args.use_xgboost = args.enable_xgboost', src)

    def test_script_has_no_xgboost_backward_compat(self):
        """Script must still define --no-xgboost for backward compat."""
        src = self._read_script()
        self.assertIn('--no-xgboost', src)

    def test_script_has_evidence_metrics_in_comments(self):
        """Script must cite the evidence metrics in comments."""
        src = self._read_script()
        self.assertIn('PortfolioIC 0.0157', src)
        self.assertIn('PortfolioIC 0.0344', src)


if __name__ == '__main__':
    unittest.main()
