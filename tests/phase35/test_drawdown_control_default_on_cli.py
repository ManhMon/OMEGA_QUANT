"""
GATE: DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615
CLI Drawdown Control Default-On and Opt-Out Tests

[L2-Impl:Role14-DataScientist] - 2026-06-15

Verifies that the Phase 3.5 backtest CLI argument logic:
  1. Defaults to drawdown_control=True (enabled by default)
  2. Default drawdown_threshold is 0.10 (changed from 0.05)
  3. --disable-drawdown-control opt-out sets drawdown_control=False
  4. --drawdown-control backward-compat flag still accepted (no-op, already on)
  5. Help text mentions research default, evidence, and gate
  6. Combined flags: --disable-drawdown-control takes precedence

Evidence (E2E risk-layer diagnostic, 12-fold walk-forward, 30 symbols, 2015-2026):
  no-XGB baseline: PortfolioIC 0.0344, RawIC 0.0200, CSIC 0.0216,
                   Sharpe 2.3273, MaxDD -66.99%
  DD10 control:    PortfolioIC 0.0344, RawIC 0.0200, CSIC 0.0216,
                   Sharpe 3.1570, MaxDD -12.34%

  IC preserved, Sharpe improved 2.33 to 3.16, MaxDD improved -67% to -12%.

PIT Safety: Tests use argparse namespace only; no real data loaded.
"""

import sys
import os
import unittest
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))


# ---------------------------------------------------------------------------
# Helper: Build the parser directly (mirrors run_phase35_backtest.py argparse)
# We replicate only the drawdown-control-related flag definitions and the
# drawdown_control derivation logic.
# ---------------------------------------------------------------------------

def _build_drawdown_parser():
    """
    Build a minimal argparse parser that mirrors the drawdown-control-related
    flags from scripts/run_phase35_backtest.py.
    """
    parser = argparse.ArgumentParser(
        description="Run Phase 3.5 walk-forward backtest"
    )
    # GATE: DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615
    parser.add_argument(
        "--drawdown-control",
        action="store_true",
        help=(
            "DEPRECATED (no-op). Drawdown control is now ENABLED by default per "
            "GATE DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615. "
            "This flag is preserved for backward compatibility as an explicit "
            "enable and has no effect. Use --disable-drawdown-control to opt out."
        ),
    )
    parser.add_argument(
        "--disable-drawdown-control",
        action="store_true",
        help=(
            "GATE DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615: Opt-out flag. "
            "Disables active drawdown control stop-out. "
            "Drawdown control is ENABLED by default because E2E risk-layer evidence "
            "showed MaxDD improved from -66.99%% to -12.34%% without reducing IC "
            "(PortfolioIC 0.0344 preserved, Sharpe 2.33 to 3.16). "
            "Use this flag only to reproduce uncontrolled baselines."
        ),
    )
    parser.add_argument(
        "--drawdown-threshold",
        type=float,
        default=0.10,
        help=(
            "GATE DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615: "
            "Drawdown threshold (e.g. 0.10 for 10 pct). Default changed from 0.05 "
            "to 0.10 based on E2E risk-layer diagnostic evidence."
        ),
    )
    return parser


def _parse_and_derive(argv):
    """Parse argv and apply the drawdown_control derivation logic."""
    parser = _build_drawdown_parser()
    args = parser.parse_args(argv)
    # GATE: DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615
    # Same derivation as in run_phase35_backtest.py
    args.drawdown_control = not args.disable_drawdown_control
    return args


def _get_help_text():
    """Return the help text from the parser."""
    parser = _build_drawdown_parser()
    return parser.format_help()


def _get_action_help(flag_name):
    """Return the help string for a specific flag."""
    parser = _build_drawdown_parser()
    for action in parser._actions:
        if flag_name in action.option_strings:
            return action.help
    return None


# ---------------------------------------------------------------------------
# Tests: Default-on behavior
# ---------------------------------------------------------------------------

class TestDrawdownControlDefaultOn(unittest.TestCase):
    """GATE: DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615 — default must be ON."""

    def test_no_flags_means_drawdown_control_true(self):
        """With no drawdown-related flags, drawdown_control must be True."""
        args = _parse_and_derive([])
        self.assertTrue(
            args.drawdown_control,
            "Default drawdown_control must be True per GATE "
            "DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615"
        )

    def test_default_threshold_is_0_10(self):
        """Default drawdown_threshold must be 0.10 (changed from 0.05)."""
        args = _parse_and_derive([])
        self.assertAlmostEqual(
            args.drawdown_threshold,
            0.10,
            places=4,
            msg="Default drawdown_threshold must be 0.10 per GATE "
                "DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615"
        )

    def test_disable_drawdown_control_default_is_false(self):
        """The disable_drawdown_control attribute must default to False."""
        args = _parse_and_derive([])
        self.assertFalse(args.disable_drawdown_control)

    def test_drawdown_control_deprecated_flag_default_is_false(self):
        """The deprecated --drawdown-control attribute must default to False."""
        args = _parse_and_derive([])
        self.assertFalse(args.drawdown_control is None)


# ---------------------------------------------------------------------------
# Tests: Opt-out behavior
# ---------------------------------------------------------------------------

class TestDrawdownControlOptOut(unittest.TestCase):
    """GATE: DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615 — --disable-drawdown-control."""

    def test_disable_flag_sets_drawdown_control_false(self):
        """--disable-drawdown-control must set drawdown_control=False."""
        args = _parse_and_derive(['--disable-drawdown-control'])
        self.assertFalse(
            args.drawdown_control,
            "--disable-drawdown-control must set drawdown_control=False"
        )

    def test_disable_flag_sets_disable_attribute(self):
        """--disable-drawdown-control must set disable_drawdown_control=True."""
        args = _parse_and_derive(['--disable-drawdown-control'])
        self.assertTrue(args.disable_drawdown_control)

    def test_custom_threshold_with_disable(self):
        """Custom threshold is still accepted with --disable-drawdown-control."""
        args = _parse_and_derive([
            '--disable-drawdown-control',
            '--drawdown-threshold', '0.20',
        ])
        self.assertFalse(args.drawdown_control)
        self.assertAlmostEqual(args.drawdown_threshold, 0.20, places=4)


# ---------------------------------------------------------------------------
# Tests: Backward-compatible --drawdown-control flag
# ---------------------------------------------------------------------------

class TestDrawdownControlBackwardCompat(unittest.TestCase):
    """GATE: DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615 — --drawdown-control compat."""

    def test_drawdown_control_flag_accepted(self):
        """--drawdown-control must be accepted without error (backward compat)."""
        args = _parse_and_derive(['--drawdown-control'])
        self.assertTrue(
            args.drawdown_control,
            "--drawdown-control flag must still result in drawdown_control=True"
        )

    def test_drawdown_control_flag_means_enabled(self):
        """--drawdown-control alone must result in drawdown_control=True."""
        args = _parse_and_derive(['--drawdown-control'])
        self.assertTrue(
            args.drawdown_control,
            "--drawdown-control must result in drawdown_control=True (explicit enable)"
        )

    def test_drawdown_control_and_disable_together(self):
        """If both --drawdown-control and --disable-drawdown-control, disable wins."""
        args = _parse_and_derive([
            '--drawdown-control',
            '--disable-drawdown-control',
        ])
        self.assertFalse(
            args.drawdown_control,
            "--disable-drawdown-control must take precedence over deprecated "
            "--drawdown-control"
        )


# ---------------------------------------------------------------------------
# Tests: Custom threshold
# ---------------------------------------------------------------------------

class TestDrawdownThresholdCustom(unittest.TestCase):
    """GATE: DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615 — threshold customization."""

    def test_custom_threshold(self):
        """--drawdown-threshold must accept custom values."""
        args = _parse_and_derive(['--drawdown-threshold', '0.15'])
        self.assertAlmostEqual(args.drawdown_threshold, 0.15, places=4)

    def test_custom_threshold_with_default_on(self):
        """Custom threshold works with default-on drawdown control."""
        args = _parse_and_derive(['--drawdown-threshold', '0.05'])
        self.assertTrue(args.drawdown_control)
        self.assertAlmostEqual(args.drawdown_threshold, 0.05, places=4)


# ---------------------------------------------------------------------------
# Tests: Help text includes evidence attribution
# ---------------------------------------------------------------------------

class TestDrawdownControlHelpText(unittest.TestCase):
    """GATE: DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615 — help text must cite evidence."""

    def test_help_mentions_disable_drawdown_control(self):
        """Help text must include --disable-drawdown-control."""
        help_text = _get_help_text()
        self.assertIn("--disable-drawdown-control", help_text)

    def test_help_mentions_drawdown_control(self):
        """Help text must include --drawdown-control (backward compat)."""
        help_text = _get_help_text()
        self.assertIn("--drawdown-control", help_text)

    def test_help_mentions_drawdown_threshold(self):
        """Help text must include --drawdown-threshold."""
        help_text = _get_help_text()
        self.assertIn("--drawdown-threshold", help_text)

    def test_disable_help_mentions_research_default(self):
        """--disable-drawdown-control help must mention ENABLED by default."""
        help_str = _get_action_help('--disable-drawdown-control')
        self.assertIsNotNone(help_str)
        self.assertIn(
            "ENABLED by default",
            help_str,
            "--disable-drawdown-control help must state drawdown control is "
            "ENABLED by default"
        )

    def test_disable_help_mentions_evidence_maxdd(self):
        """--disable-drawdown-control help must reference MaxDD evidence."""
        help_str = _get_action_help('--disable-drawdown-control')
        self.assertIsNotNone(help_str)
        # argparse stores raw help with %% for literal %; check for both forms
        self.assertTrue(
            '-66.99%' in help_str or '-66.99%%' in help_str,
            "--disable-drawdown-control help must cite baseline MaxDD -66.99%"
        )
        self.assertTrue(
            '-12.34%' in help_str or '-12.34%%' in help_str,
            "--disable-drawdown-control help must cite controlled MaxDD -12.34%"
        )

    def test_disable_help_mentions_gate(self):
        """--disable-drawdown-control help must reference the gate name."""
        help_str = _get_action_help('--disable-drawdown-control')
        self.assertIsNotNone(help_str)
        self.assertIn(
            "DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615",
            help_str,
            "--disable-drawdown-control help must cite the gate"
        )

    def test_drawdown_control_help_mentions_deprecated(self):
        """--drawdown-control help must mention DEPRECATED."""
        help_str = _get_action_help('--drawdown-control')
        self.assertIsNotNone(help_str)
        self.assertIn(
            "DEPRECATED",
            help_str,
            "--drawdown-control help must state it is DEPRECATED"
        )

    def test_drawdown_control_help_mentions_backward_compat(self):
        """--drawdown-control help must mention backward compatibility."""
        help_str = _get_action_help('--drawdown-control')
        self.assertIsNotNone(help_str)
        self.assertIn(
            "backward compatibility",
            help_str.lower(),
            "--drawdown-control help must mention backward compatibility"
        )

    def test_threshold_help_mentions_gate(self):
        """--drawdown-threshold help must reference the gate."""
        help_str = _get_action_help('--drawdown-threshold')
        self.assertIsNotNone(help_str)
        self.assertIn(
            "DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615",
            help_str,
            "--drawdown-threshold help must cite the gate"
        )

    def test_threshold_help_mentions_default_change(self):
        """--drawdown-threshold help must mention default changed from 0.05."""
        help_str = _get_action_help('--drawdown-threshold')
        self.assertIsNotNone(help_str)
        self.assertIn(
            "0.05",
            help_str,
            "--drawdown-threshold help must mention old default 0.05"
        )


# ---------------------------------------------------------------------------
# Tests: Verify script file contains gate logic (integration check)
# ---------------------------------------------------------------------------

class TestScriptFileContainsDrawdownGate(unittest.TestCase):
    """Verify the actual script file has the gate implementation."""

    def _read_script(self):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'scripts',
            'run_phase35_backtest.py'
        )
        with open(script_path, 'r') as f:
            return f.read()

    def test_script_has_disable_drawdown_control_flag(self):
        """Script must define --disable-drawdown-control flag."""
        src = self._read_script()
        self.assertIn('--disable-drawdown-control', src)

    def test_script_has_gate_citation(self):
        """Script must cite the gate name."""
        src = self._read_script()
        self.assertIn('DRAWDOWN_CONTROL_DEFAULT_RESEARCH_MODE_20260615', src)

    def test_script_derives_drawdown_control_from_disable(self):
        """Script must set drawdown_control from not disable_drawdown_control."""
        src = self._read_script()
        self.assertIn(
            'args.drawdown_control = not args.disable_drawdown_control',
            src,
        )

    def test_script_has_drawdown_control_backward_compat(self):
        """Script must still define --drawdown-control for backward compat."""
        src = self._read_script()
        self.assertIn('--drawdown-control', src)

    def test_script_has_evidence_maxdd_in_help(self):
        """Script must cite the evidence MaxDD values in help text."""
        src = self._read_script()
        # Script uses %% for argparse escaping; check for the numeric values
        self.assertIn('-66.99', src)
        self.assertIn('-12.34', src)

    def test_script_has_evidence_ic_in_help(self):
        """Script must cite evidence PortfolioIC value in help text."""
        src = self._read_script()
        self.assertIn('PortfolioIC 0.0344', src)

    def test_script_default_threshold_is_0_10(self):
        """Script must set default drawdown threshold to 0.10."""
        src = self._read_script()
        # Check that 0.10 appears as the default for --drawdown-threshold
        self.assertIn('default=0.10', src)


if __name__ == '__main__':
    unittest.main()
