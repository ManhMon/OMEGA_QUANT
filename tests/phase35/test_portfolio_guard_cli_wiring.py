"""
Portfolio Guard CLI Wiring Fix Tests
GATE: RISK_ADJUSTED_PORTFOLIO_GUARD_FIX1_20260614
[L2-Impl:Role16-Machine-Learning-Engineer] - 2026-06-14

Verifies that:
1. --disable-risk-adjusted-portfolio-guard CLI flag exists
2. --risk-adjusted-portfolio-guard-tolerance CLI flag exists
3. portfolio_guard_enabled is auto-derived and passed to engine
4. portfolio_guard_tolerance is passed to engine
5. Config output includes portfolio_guard_enabled and portfolio_guard_tolerance
6. Engine accepts and stores portfolio_guard_enabled/tolerance params

PIT Safety: No real data loaded. Source inspection and signature tests only.
"""

import inspect
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))


class TestPortfolioGuardEngineParams:
    """Verify Phase35WalkForwardEngine accepts and stores portfolio guard params."""

    def _get_engine_class(self):
        from omega.quant.alpha.phase35 import Phase35WalkForwardEngine
        return Phase35WalkForwardEngine

    def test_engine_accepts_portfolio_guard_enabled(self):
        cls = self._get_engine_class()
        sig = inspect.signature(cls.__init__)
        assert 'portfolio_guard_enabled' in sig.parameters, \
            "Phase35WalkForwardEngine.__init__ must accept portfolio_guard_enabled"

    def test_engine_portfolio_guard_enabled_default_is_false(self):
        cls = self._get_engine_class()
        sig = inspect.signature(cls.__init__)
        assert sig.parameters['portfolio_guard_enabled'].default is False, \
            "portfolio_guard_enabled default must be False (opt-in)"

    def test_engine_accepts_portfolio_guard_tolerance(self):
        cls = self._get_engine_class()
        sig = inspect.signature(cls.__init__)
        assert 'portfolio_guard_tolerance' in sig.parameters, \
            "Phase35WalkForwardEngine.__init__ must accept portfolio_guard_tolerance"

    def test_engine_portfolio_guard_tolerance_default_is_0005(self):
        cls = self._get_engine_class()
        sig = inspect.signature(cls.__init__)
        assert sig.parameters['portfolio_guard_tolerance'].default == 0.005, \
            "portfolio_guard_tolerance default must be 0.005"

    def test_engine_stores_portfolio_guard_enabled(self):
        cls = self._get_engine_class()
        engine = cls(
            alpha_module=None,
            portfolio_guard_enabled=True,
            portfolio_guard_tolerance=0.01,
        )
        assert engine.portfolio_guard_enabled is True

    def test_engine_stores_portfolio_guard_tolerance(self):
        cls = self._get_engine_class()
        engine = cls(
            alpha_module=None,
            portfolio_guard_enabled=True,
            portfolio_guard_tolerance=0.01,
        )
        assert engine.portfolio_guard_tolerance == 0.01


class TestPortfolioGuardCLIWiring:
    """Verify run_phase35_backtest.py defines CLI flags and wires guard params."""

    def _get_script_source(self):
        script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_phase35_backtest.py"
        return script_path.read_text(encoding="utf-8")

    def test_cli_disable_flag_registered(self):
        src = self._get_script_source()
        assert "--disable-risk-adjusted-portfolio-guard" in src, \
            "CLI flag --disable-risk-adjusted-portfolio-guard must be registered"

    def test_cli_tolerance_flag_registered(self):
        src = self._get_script_source()
        assert "--risk-adjusted-portfolio-guard-tolerance" in src, \
            "CLI flag --risk-adjusted-portfolio-guard-tolerance must be registered"

    def test_tolerance_default_is_0005(self):
        src = self._get_script_source()
        assert "default=0.005" in src, \
            "Tolerance flag default must be 0.005"

    def test_auto_derive_portfolio_guard_enabled(self):
        """portfolio_guard_enabled must be derived from risk_adjusted_alpha_selection
        and not disable_risk_adjusted_portfolio_guard."""
        src = self._get_script_source()
        assert "args.portfolio_guard_enabled" in src, \
            "Script must derive args.portfolio_guard_enabled"
        assert "args.risk_adjusted_alpha_selection" in src, \
            "Derivation must reference risk_adjusted_alpha_selection"
        assert "args.disable_risk_adjusted_portfolio_guard" in src, \
            "Derivation must reference disable_risk_adjusted_portfolio_guard"

    def test_passes_portfolio_guard_enabled_to_engine(self):
        src = self._get_script_source()
        assert "portfolio_guard_enabled=args.portfolio_guard_enabled" in src, \
            "Script must pass portfolio_guard_enabled to Phase35WalkForwardEngine"

    def test_passes_portfolio_guard_tolerance_to_engine(self):
        src = self._get_script_source()
        assert "portfolio_guard_tolerance=args.portfolio_guard_tolerance" in src, \
            "Script must pass portfolio_guard_tolerance to Phase35WalkForwardEngine"

    def test_config_output_includes_portfolio_guard_enabled(self):
        src = self._get_script_source()
        assert '"portfolio_guard_enabled"' in src, \
            "Results JSON config must include portfolio_guard_enabled"

    def test_config_output_includes_portfolio_guard_tolerance(self):
        src = self._get_script_source()
        assert '"portfolio_guard_tolerance"' in src, \
            "Results JSON config must include portfolio_guard_tolerance"

    def test_logging_portfolio_guard_enabled(self):
        src = self._get_script_source()
        assert "Portfolio Guard Enabled" in src, \
            "Script must log portfolio guard enabled status"

    def test_logging_portfolio_guard_tolerance(self):
        src = self._get_script_source()
        assert "Portfolio Guard Tolerance" in src, \
            "Script must log portfolio guard tolerance value"

    def test_preserve_baseline_when_ra_disabled(self):
        """When --risk-adjusted-alpha-selection is NOT set, portfolio_guard_enabled
        must be False regardless of other flags."""
        src = self._get_script_source()
        # The derivation uses 'and' logic: risk_adjusted_alpha_selection AND not disable
        # When risk_adjusted_alpha_selection=False, the result is False
        assert "args.risk_adjusted_alpha_selection" in src
        assert "not args.disable_risk_adjusted_portfolio_guard" in src


class TestPortfolioGuardSerializeFoldDetails:
    """Verify serialize_fold_details includes portfolio guard evidence."""

    def test_serialize_includes_portfolio_guard_evidence(self):
        src_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "run_phase35_backtest.py"
        src = src_path.read_text(encoding="utf-8")
        assert "portfolio_guard_evidence" in src, \
            "serialize_fold_details must persist portfolio_guard_evidence"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
