"""
test_circuit_breaker_sre.py - Phase 7.3 SRE Integration Tests
==============================================================
Verifies that CircuitBreaker correctly wires to the KillSwitch singleton:
  - Every breach path activates the kill-switch with the correct reason string
  - Registered callbacks are executed on activation
  - Metrics/events are dumped to disk on activation
  - No-breach paths do NOT activate the kill-switch
  - apply_halt() zeroes positions without touching the kill-switch

Coverage target: 100% of circuit_breaker.py lines added/modified in Phase 7.3.

Author: DevOps Engineer (Role 11)
Date: 2026-05-20
Phase: 7.3 Circuit Breaker & Kill-Switch Integration
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from omega.core.sre.kill_switch import _reset_kill_switch_for_testing
from omega.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prices(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


def _portfolio_df(values: list[float], col: str = "portfolio_value") -> pd.DataFrame:
    return pd.DataFrame({col: values})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_ks():
    """Reset the KillSwitch singleton before every test (LIVE-04: guarded)."""
    _reset_kill_switch_for_testing(auth_token="OMEGA_TEST")
    yield
    _reset_kill_switch_for_testing(auth_token="OMEGA_TEST")


@pytest.fixture()
def dump_dir(tmp_path: Path) -> Path:
    return tmp_path / "omega_dump"


@pytest.fixture()
def breaker() -> CircuitBreaker:
    return CircuitBreaker()


# ---------------------------------------------------------------------------
# check_market_circuit_breaker — single-day drop breach
# ---------------------------------------------------------------------------

class TestMarketBreakerSingleDayDrop:
    def test_breach_activates_kill_switch(self, dump_dir: Path):
        """Single-day drop > 7% must activate the kill-switch."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            # Drop of ~10% on day 2
            prices = _prices([100.0, 90.0])
            triggered, reason = breaker.check_market_circuit_breaker(prices)

        assert triggered is True
        assert "Single-day drop" in reason
        mock_ks.activate.assert_called_once()
        call_reason = mock_ks.activate.call_args.kwargs["reason"]
        assert "Single-day drop" in call_reason

    def test_no_breach_does_not_activate(self):
        """Normal market movement must NOT activate the kill-switch."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            prices = _prices([100.0, 101.0, 102.0])
            triggered, _ = breaker.check_market_circuit_breaker(prices)

        assert triggered is False
        mock_ks.activate.assert_not_called()

    def test_insufficient_data_no_activation(self):
        """Single-element series must return False without activating."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            triggered, reason = breaker.check_market_circuit_breaker(_prices([100.0]))

        assert triggered is False
        assert reason == "Insufficient data"
        mock_ks.activate.assert_not_called()


# ---------------------------------------------------------------------------
# check_market_circuit_breaker — 5-day drop breach
# ---------------------------------------------------------------------------

class TestMarketBreakerFiveDayDrop:
    def test_five_day_breach_activates_kill_switch(self):
        """5-day cumulative drop > 15% must activate the kill-switch."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            # iloc[-1]/iloc[-5] = 80/96 = -16.67%, no single day > 7%
            prices = _prices([100.0, 96.0, 92.0, 88.0, 84.0, 80.0])
            triggered, reason = breaker.check_market_circuit_breaker(prices)

        assert triggered is True
        assert "5-day drop" in reason
        mock_ks.activate.assert_called_once()
        call_reason = mock_ks.activate.call_args.kwargs["reason"]
        assert "5-day drop" in call_reason

    def test_five_day_no_breach(self):
        """5-day drop within limit must NOT activate."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            prices = _prices([100.0, 99.0, 98.0, 97.0, 96.0, 95.0])  # ~5% drop
            triggered, _ = breaker.check_market_circuit_breaker(prices)

        assert triggered is False
        mock_ks.activate.assert_not_called()

    def test_fewer_than_five_days_skips_five_day_check(self):
        """With only 4 data points the 5-day check is skipped."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            prices = _prices([100.0, 99.0, 98.0, 97.0])
            triggered, _ = breaker.check_market_circuit_breaker(prices)

        assert triggered is False
        mock_ks.activate.assert_not_called()


# ---------------------------------------------------------------------------
# check_asset_circuit_breaker
# ---------------------------------------------------------------------------

class TestAssetBreaker:
    def test_breach_activates_kill_switch(self):
        """Asset drop > 7% must activate the kill-switch."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            prices = _prices([100.0, 90.0])  # -10%
            triggered, reason = breaker.check_asset_circuit_breaker(prices, "VNM")

        assert triggered is True
        assert "VNM" in reason
        mock_ks.activate.assert_called_once()
        call_reason = mock_ks.activate.call_args.kwargs["reason"]
        assert "VNM" in call_reason

    def test_no_breach_does_not_activate(self):
        """Asset within limit must NOT activate."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            prices = _prices([100.0, 98.0])  # -2%
            triggered, _ = breaker.check_asset_circuit_breaker(prices, "VNM")

        assert triggered is False
        mock_ks.activate.assert_not_called()

    def test_insufficient_data_no_activation(self):
        """Single-element series must return False without activating."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            triggered, reason = breaker.check_asset_circuit_breaker(
                _prices([100.0]), "VNM"
            )

        assert triggered is False
        assert reason == "Insufficient data"
        mock_ks.activate.assert_not_called()


# ---------------------------------------------------------------------------
# check_status — drawdown breach
# ---------------------------------------------------------------------------

class TestCheckStatusDrawdown:
    def test_drawdown_breach_activates_kill_switch(self):
        """Drawdown > 20% must activate the kill-switch."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            # Peak 100, drops to 75 → 25% drawdown
            df = _portfolio_df([100.0, 98.0, 95.0, 90.0, 80.0, 75.0])
            result = breaker.check_status(df)

        assert result["triggered"] is True
        assert "Drawdown" in result["reason"]
        mock_ks.activate.assert_called_once()
        call_reason = mock_ks.activate.call_args.kwargs["reason"]
        assert "Drawdown" in call_reason

    def test_drawdown_no_breach(self):
        """Drawdown within limit must NOT activate."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            df = _portfolio_df([100.0, 99.0, 98.0, 97.0])  # ~3% drawdown
            result = breaker.check_status(df)

        assert result["triggered"] is False
        mock_ks.activate.assert_not_called()

    def test_uses_value_column_fallback(self):
        """check_status must also work with a 'value' column."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            df = _portfolio_df([100.0, 98.0, 95.0, 90.0, 80.0, 75.0], col="value")
            result = breaker.check_status(df)

        assert result["triggered"] is True
        mock_ks.activate.assert_called_once()

    def test_no_value_column_returns_not_triggered(self):
        """DataFrame with no recognised value column must return not-triggered."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            df = pd.DataFrame({"price": [100.0, 75.0]})
            result = breaker.check_status(df)

        assert result["triggered"] is False
        mock_ks.activate.assert_not_called()

    def test_insufficient_rows_returns_not_triggered(self):
        """Single-row DataFrame must return not-triggered."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            df = _portfolio_df([100.0])
            result = breaker.check_status(df)

        assert result["triggered"] is False
        mock_ks.activate.assert_not_called()


# ---------------------------------------------------------------------------
# check_status — volatility breach
# ---------------------------------------------------------------------------

class TestCheckStatusVolatility:
    def test_volatility_breach_activates_kill_switch(self):
        """Volatility > 3% threshold must activate the kill-switch."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            # Use a tight drawdown config so only volatility fires
            cfg = CircuitBreakerConfig(
                max_drawdown_pct=0.99,   # effectively disabled
                volatility_threshold=0.01,
            )
            breaker = CircuitBreaker(config=cfg)
            # Alternating values produce high daily volatility
            df = _portfolio_df([100.0, 105.0, 98.0, 106.0, 97.0, 107.0])
            result = breaker.check_status(df)

        assert result["triggered"] is True
        assert "Volatility" in result["reason"]
        mock_ks.activate.assert_called_once()
        call_reason = mock_ks.activate.call_args.kwargs["reason"]
        assert "Volatility" in call_reason

    def test_all_checks_pass_returns_clean(self):
        """Stable portfolio must return triggered=False, no kill-switch call."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            df = _portfolio_df([100.0, 100.1, 100.2, 100.3])
            result = breaker.check_status(df)

        assert result["triggered"] is False
        assert result["reason"] == "All checks passed"
        mock_ks.activate.assert_not_called()


# ---------------------------------------------------------------------------
# apply_halt — must NOT touch kill-switch
# ---------------------------------------------------------------------------

class TestApplyHalt:
    def test_apply_halt_does_not_activate_kill_switch(self):
        """apply_halt() is a pure transform — must never call kill-switch."""
        with patch(
            "omega.risk.circuit_breaker.get_kill_switch"
        ) as mock_get_ks:
            mock_ks = MagicMock()
            mock_get_ks.return_value = mock_ks

            breaker = CircuitBreaker()
            positions = pd.DataFrame({"symbol": ["VNM", "HPG"], "target_weight": [0.5, 0.5]})
            result = breaker.apply_halt(positions)

        assert (result["target_weight"] == 0.0).all()
        mock_ks.activate.assert_not_called()

    def test_apply_halt_weight_column(self):
        """apply_halt() also handles 'weight' column."""
        breaker = CircuitBreaker()
        positions = pd.DataFrame({"symbol": ["VNM"], "weight": [0.8]})
        result = breaker.apply_halt(positions)
        assert result["weight"].iloc[0] == 0.0

    def test_apply_halt_no_weight_column(self):
        """apply_halt() returns copy unchanged when no weight column present."""
        breaker = CircuitBreaker()
        positions = pd.DataFrame({"symbol": ["VNM"], "qty": [100]})
        result = breaker.apply_halt(positions)
        assert result["qty"].iloc[0] == 100


# ---------------------------------------------------------------------------
# compute_max_drawdown — edge cases
# ---------------------------------------------------------------------------

class TestComputeMaxDrawdown:
    def test_single_value_returns_zero(self):
        breaker = CircuitBreaker()
        assert breaker.compute_max_drawdown(_prices([100.0])) == 0.0

    def test_no_drawdown(self):
        breaker = CircuitBreaker()
        assert breaker.compute_max_drawdown(_prices([100.0, 101.0, 102.0])) == 0.0

    def test_known_drawdown(self):
        breaker = CircuitBreaker()
        # Peak 100, trough 80 → 20% drawdown
        dd = breaker.compute_max_drawdown(_prices([100.0, 90.0, 80.0]))
        assert abs(dd - 0.20) < 1e-9


# ---------------------------------------------------------------------------
# Integration: real KillSwitch singleton — callbacks + state dump
# ---------------------------------------------------------------------------

class TestKillSwitchIntegration:
    """End-to-end: real KillSwitch (no mock) — verify callbacks fire and dump lands."""

    def test_breach_fires_registered_callback(self, dump_dir: Path):
        """Callback registered on the singleton must be called when breaker fires."""
        import omega.core.sre.kill_switch as ks_module

        ks = ks_module.get_kill_switch(dump_dir=str(dump_dir))
        fired = []
        ks.register_callback(lambda: fired.append(True))

        breaker = CircuitBreaker()
        prices = _prices([100.0, 90.0])  # -10% single-day breach
        triggered, _ = breaker.check_market_circuit_breaker(prices)

        assert triggered is True
        assert ks.is_activated is True
        assert fired == [True]

    def test_breach_dumps_kill_switch_event_json(self, dump_dir: Path):
        """kill_switch_event.json must be written to dump_dir on activation."""
        import omega.core.sre.kill_switch as ks_module

        ks = ks_module.get_kill_switch(dump_dir=str(dump_dir))

        breaker = CircuitBreaker()
        prices = _prices([100.0, 90.0])
        breaker.check_market_circuit_breaker(prices)

        event_path = dump_dir / "kill_switch_event.json"
        assert event_path.exists(), "kill_switch_event.json not written"

        event = json.loads(event_path.read_text(encoding="utf-8"))
        assert "activation_id" in event
        assert "Single-day drop" in event["reason"]

    def test_breach_dumps_metrics_snapshot_when_collector_registered(
        self, dump_dir: Path
    ):
        """metrics_snapshot.json must be written when a collector is registered."""
        import omega.core.sre.kill_switch as ks_module

        ks = ks_module.get_kill_switch(dump_dir=str(dump_dir))

        mock_collector = MagicMock()
        mock_collector.snapshot.return_value = {"equity": 1_000_000, "positions": 5}
        ks.register_metrics_collector(mock_collector)

        breaker = CircuitBreaker()
        df = _portfolio_df([100.0, 98.0, 95.0, 90.0, 80.0, 75.0])
        result = breaker.check_status(df)

        assert result["triggered"] is True
        metrics_path = dump_dir / "metrics_snapshot.json"
        assert metrics_path.exists(), "metrics_snapshot.json not written"

        snapshot = json.loads(metrics_path.read_text(encoding="utf-8"))
        assert snapshot["equity"] == 1_000_000

    def test_idempotent_activation_callbacks_fire_once(self, dump_dir: Path):
        """Multiple breaches must not fire callbacks more than once."""
        import omega.core.sre.kill_switch as ks_module

        ks = ks_module.get_kill_switch(dump_dir=str(dump_dir))
        fired = []
        ks.register_callback(lambda: fired.append(True))

        breaker = CircuitBreaker()
        prices = _prices([100.0, 90.0])

        # Trigger twice — second call must be a no-op
        breaker.check_market_circuit_breaker(prices)
        breaker.check_market_circuit_breaker(prices)

        assert len(fired) == 1

    def test_asset_breach_dumps_event(self, dump_dir: Path):
        """Asset-level breach must also produce kill_switch_event.json."""
        import omega.core.sre.kill_switch as ks_module

        ks = ks_module.get_kill_switch(dump_dir=str(dump_dir))

        breaker = CircuitBreaker()
        prices = _prices([100.0, 88.0])  # -12%
        triggered, _ = breaker.check_asset_circuit_breaker(prices, "HPG")

        assert triggered is True
        event_path = dump_dir / "kill_switch_event.json"
        assert event_path.exists()
        event = json.loads(event_path.read_text(encoding="utf-8"))
        assert "HPG" in event["reason"]
