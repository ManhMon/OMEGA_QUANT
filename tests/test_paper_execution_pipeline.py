"""
OMEGA_QUANT Paper Execution Pipeline Tests
Gate: SIMULATED_TRADING_INTEGRATION_20260619

Tests for:
- Order diff computation (new positions, adjustments, removals)
- Signal and position loading
- Pipeline execution through LiveTradingPipeline
- Dashboard update correctness
- End-to-end orchestration

Author: Backend Engineer (Role 09)
Date: 2026-06-19
"""

import json
import pytest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone

# Ensure repo src is on path for imports
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.run_paper_execution_pipeline import (
    compute_order_diffs,
    OrderDiff,
    _build_risk_exposures,
    load_latest_signal,
    load_current_positions,
    execute_diffs,
    update_dashboard,
    save_execution_results,
    run_paper_execution_pipeline,
    build_pipeline,
    BOARD_LOT,
    DEFAULT_CAPITAL,
)
from omega.execution.broker_gateway import OrderSide
from omega.quant.risk.realtime_risk import RealtimeRiskGuard, RiskLimits, RiskVerdict


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

SAMPLE_SIGNAL = {
    "date": "2026-06-19",
    "gate": "SIMULATED_TRADING_INTEGRATION_20260619",
    "capital": 2_000_000_000.0,
    "total_exposure": 0.30,
    "regime": {"state": "SIDEWAYS", "confidence": 0.7, "exposure": 0.8},
    "positions": {
        "VNM": {"weight": 0.10, "shares": 2000, "price": 80000.0, "value_vnd": 160_000_000.0},
        "FPT": {"weight": 0.08, "shares": 1500, "price": 100000.0, "value_vnd": 150_000_000.0},
        "HPG": {"weight": 0.05, "shares": 3000, "price": 30000.0, "value_vnd": 90_000_000.0},
    },
    "alpha_sources": {"total_signal_candidates": 10},
    "hrp_weights": {},
}

CURRENT_POSITIONS = {
    "VNM": {
        "symbol": "VNM",
        "shares": 1000,
        "avg_price": 78000.0,
        "current_price": 80000.0,
        "value": 80_000_000.0,
        "weight": 0.04,
        "pnl": 0.0,
        "pnl_pct": 0.0,
    },
    "SSI": {
        "symbol": "SSI",
        "shares": 2000,
        "avg_price": 25000.0,
        "current_price": 25000.0,
        "value": 50_000_000.0,
        "weight": 0.025,
        "pnl": 0.0,
        "pnl_pct": 0.0,
    },
}


# ------------------------------------------------------------------ #
# compute_order_diffs tests
# ------------------------------------------------------------------ #

class TestComputeOrderDiffs:
    """Tests for order diff computation logic."""

    def test_new_position_generates_buy(self):
        """Position in signal but not in current portfolio generates BUY."""
        signal = {
            "positions": {
                "FPT": {"weight": 0.10, "shares": 500, "price": 100000.0, "value_vnd": 50_000_000.0},
            }
        }
        diffs = compute_order_diffs(signal, {})
        assert len(diffs) == 1
        assert diffs[0].symbol == "FPT"
        assert diffs[0].side == "BUY"
        assert diffs[0].quantity == 500
        assert diffs[0].price == 100000.0

    def test_existing_position_increase(self):
        """Target > current generates BUY for the delta."""
        signal = SAMPLE_SIGNAL
        diffs = compute_order_diffs(signal, CURRENT_POSITIONS)

        vnm_diff = next((d for d in diffs if d.symbol == "VNM"), None)
        assert vnm_diff is not None
        assert vnm_diff.side == "BUY"
        assert vnm_diff.quantity == 1000  # 2000 - 1000

    def test_existing_position_removal_generates_sell(self):
        """Position in current but not in signal generates SELL."""
        signal = {"positions": {}}
        diffs = compute_order_diffs(signal, CURRENT_POSITIONS)

        ssi_diff = next((d for d in diffs if d.symbol == "SSI"), None)
        assert ssi_diff is not None
        assert ssi_diff.side == "SELL"
        assert ssi_diff.quantity == 2000

    def test_no_change_no_diff(self):
        """When current matches target, no diff is generated."""
        positions = {
            "VNM": {"weight": 0.10, "shares": 1000, "price": 80000.0, "value_vnd": 80_000_000.0},
        }
        current = {
            "VNM": {"symbol": "VNM", "shares": 1000, "current_price": 80000.0, "weight": 0.10},
        }
        diffs = compute_order_diffs({"positions": positions}, current)
        assert len(diffs) == 0

    def test_board_lot_rounding(self):
        """Quantities are rounded down to nearest board lot (100)."""
        signal = {
            "positions": {
                "XYZ": {"weight": 0.05, "shares": 250, "price": 50000.0, "value_vnd": 12_500_000.0},
            }
        }
        diffs = compute_order_diffs(signal, {})
        assert len(diffs) == 1
        assert diffs[0].quantity == 200  # 250 rounded to 200

    def test_sub_lot_quantity_excluded(self):
        """Quantities below one board lot (100) are excluded."""
        signal = {
            "positions": {
                "TINY": {"weight": 0.01, "shares": 50, "price": 20000.0, "value_vnd": 1_000_000.0},
            }
        }
        diffs = compute_order_diffs(signal, {})
        assert len(diffs) == 0

    def test_zero_price_skipped(self):
        """Symbols with zero price are skipped with warning."""
        signal = {
            "positions": {
                "BAD": {"weight": 0.05, "shares": 500, "price": 0.0, "value_vnd": 0.0},
            }
        }
        diffs = compute_order_diffs(signal, {})
        assert len(diffs) == 0

    def test_multiple_diffs_sorted(self):
        """Multiple diffs are returned sorted by symbol."""
        signal = {
            "positions": {
                "ZZZ": {"weight": 0.05, "shares": 300, "price": 10000.0, "value_vnd": 3_000_000.0},
                "AAA": {"weight": 0.03, "shares": 200, "price": 20000.0, "value_vnd": 4_000_000.0},
            }
        }
        diffs = compute_order_diffs(signal, {})
        assert len(diffs) == 2
        assert diffs[0].symbol == "AAA"
        assert diffs[1].symbol == "ZZZ"


class TestRiskExposureBuild:
    def test_prefers_shares_times_current_price_over_weight(self):
        exposures = _build_risk_exposures(CURRENT_POSITIONS, DEFAULT_CAPITAL)

        assert exposures == {
            "VNM": 80_000_000.0,
            "SSI": 50_000_000.0,
        }

    def test_falls_back_to_absolute_position_value(self):
        current_positions = {
            "VCG": {"shares": 7700, "current_price": 20800.0},
        }

        exposures = _build_risk_exposures(current_positions, DEFAULT_CAPITAL)

        assert exposures == {"VCG": 160_160_000.0}

    def test_falls_back_to_avg_price_before_weight_or_value(self):
        current_positions = {
            "VCI": {"shares": 1000, "avg_price": 35_500.0, "weight": 0.10, "value": 999.0},
        }

        exposures = _build_risk_exposures(current_positions, DEFAULT_CAPITAL)

        assert exposures == {"VCI": 35_500_000.0}

    def test_falls_back_to_weight_when_share_price_unavailable(self):
        current_positions = {
            "BID": {"shares": 1000, "weight": 0.03, "value": 1_000_000.0},
        }

        exposures = _build_risk_exposures(current_positions, DEFAULT_CAPITAL)

        assert exposures == {"BID": 0.03 * DEFAULT_CAPITAL}


class TestRealtimeRiskGuardSellBehavior:
    def test_sell_large_notional_bypasses_max_notional_check(self):
        guard = RealtimeRiskGuard(RiskLimits(max_notional_currency=50_000_000.0))
        guard.set_portfolio_state(
            total_equity=1_000_000_000.0,
            exposures={"VNM": 200_000_000.0},
        )

        verdict = guard.check_order(
            symbol="VNM",
            quantity=1_000,
            price=100_000.0,
            adv_20d=1_000_000,
            side=OrderSide.SELL,
        )

        assert verdict == RiskVerdict.PASS

    def test_sell_existing_large_holding_bypasses_concentration_rejection(self):
        guard = RealtimeRiskGuard(RiskLimits(max_concentration_pct=0.20))
        guard.set_portfolio_state(
            total_equity=1_000_000_000.0,
            exposures={"VNM": 400_000_000.0},
        )

        verdict = guard.check_order(
            symbol="VNM",
            quantity=1_000,
            price=100_000.0,
            adv_20d=1_000_000,
            side=OrderSide.SELL,
        )

        assert verdict == RiskVerdict.PASS

    def test_sell_beyond_existing_holding_is_rejected(self):
        guard = RealtimeRiskGuard(RiskLimits(max_concentration_pct=0.20))
        guard.set_portfolio_state(
            total_equity=1_000_000_000.0,
            exposures={"VNM": 50_000_000.0},
        )

        verdict = guard.check_order(
            symbol="VNM",
            quantity=1_000,
            price=100_000.0,
            adv_20d=1_000_000,
            side=OrderSide.SELL,
        )

        assert verdict == RiskVerdict.FAIL_CONCENTRATION

    def test_sell_tolerance_allows_small_rounding_gap(self):
        guard = RealtimeRiskGuard(RiskLimits(max_concentration_pct=0.20))
        guard.set_portfolio_state(
            total_equity=1_000_000_000.0,
            exposures={"VNM": 99_950_000.0},
        )

        verdict = guard.check_order(
            symbol="VNM",
            quantity=1_000,
            price=100_000.0,
            adv_20d=1_000_000,
            side=OrderSide.SELL,
        )

        assert verdict == RiskVerdict.PASS

    def test_buy_still_rejects_new_concentration_violation(self):
        guard = RealtimeRiskGuard(RiskLimits(max_concentration_pct=0.20))
        guard.set_portfolio_state(
            total_equity=1_000_000_000.0,
            exposures={"VNM": 150_000_000.0},
        )

        verdict = guard.check_order(
            symbol="VNM",
            quantity=1_000,
            price=100_000.0,
            adv_20d=1_000_000,
            side=OrderSide.BUY,
        )

        assert verdict == RiskVerdict.FAIL_CONCENTRATION


# ------------------------------------------------------------------ #
# execute_diffs tests (mocked pipeline)
# ------------------------------------------------------------------ #

class TestExecuteDiffs:
    """Tests for diff execution through mocked LiveTradingPipeline."""

    @pytest.fixture
    def mock_pipeline(self):
        pipeline = MagicMock()
        from omega.execution.live_trading_pipeline import PipelineState

        mock_result = MagicMock()
        mock_result.state = PipelineState.COMPLETED
        mock_result.order_id = "ORD_TEST_001"
        mock_result.error = None
        mock_result.execution_orders = []
        pipeline.submit_order.return_value = mock_result
        return pipeline

    def test_all_diffs_submitted(self, mock_pipeline):
        """Every diff in the list is submitted through the pipeline."""
        diffs = [
            OrderDiff(symbol="VNM", side="BUY", quantity=1000, price=80000.0, target_weight=0.10, current_weight=0.04),
            OrderDiff(symbol="SSI", side="SELL", quantity=2000, price=25000.0, target_weight=0.0, current_weight=0.025),
        ]
        results = execute_diffs(mock_pipeline, diffs)
        assert len(results) == 2
        assert mock_pipeline.submit_order.call_count == 2

    def test_result_records_pipeline_state(self, mock_pipeline):
        """Each result records the pipeline state correctly."""
        diffs = [
            OrderDiff(symbol="FPT", side="BUY", quantity=500, price=100000.0, target_weight=0.08, current_weight=0.0),
        ]
        results = execute_diffs(mock_pipeline, diffs)
        assert results[0]["pipeline_state"] == "COMPLETED"
        assert results[0]["order_id"] == "ORD_TEST_001"

    def test_failed_pipeline_records_error(self, mock_pipeline):
        """Failed pipeline submissions are recorded with error message."""
        from omega.execution.live_trading_pipeline import PipelineState

        fail_result = MagicMock()
        fail_result.state = PipelineState.FAILED
        fail_result.order_id = ""
        fail_result.error = "Risk rejected: FAIL_ADV"
        fail_result.execution_orders = []
        mock_pipeline.submit_order.return_value = fail_result

        diffs = [
            OrderDiff(symbol="VNM", side="BUY", quantity=100000, price=80000.0, target_weight=0.50, current_weight=0.0),
        ]
        results = execute_diffs(mock_pipeline, diffs)
        assert results[0]["pipeline_state"] == "FAILED"
        assert "FAIL_ADV" in results[0]["error"]

    def test_empty_diffs_no_calls(self, mock_pipeline):
        """Empty diff list means no pipeline calls."""
        results = execute_diffs(mock_pipeline, [])
        assert len(results) == 0
        mock_pipeline.submit_order.assert_not_called()


# ------------------------------------------------------------------ #
# Dashboard update tests
# ------------------------------------------------------------------ #

class TestUpdateDashboard:
    """Tests for dashboard file update logic."""

    def test_risk_status_written(self, tmp_path):
        """risk_status.json is created with correct structure."""
        signal = SAMPLE_SIGNAL
        results = [
            {"symbol": "VNM", "side": "BUY", "quantity": 1000, "price": 80000.0,
             "pipeline_state": "COMPLETED", "order_id": "ORD_001", "error": None,
             "target_weight": 0.10, "current_weight": 0.04},
        ]
        update_dashboard(signal, results, session_dir=tmp_path)

        risk_file = tmp_path / "risk_status.json"
        assert risk_file.exists()
        data = json.loads(risk_file.read_text())
        assert data["gate"] == "SIMULATED_TRADING_INTEGRATION_20260619"
        assert len(data["trades"]) == 1
        assert data["trades"][0]["symbol"] == "VNM"

    def test_pnl_latest_written(self, tmp_path):
        """pnl_latest.json is created with correct totals."""
        signal = SAMPLE_SIGNAL
        results = [
            {"symbol": "VNM", "side": "BUY", "quantity": 1000, "price": 80000.0,
             "pipeline_state": "COMPLETED", "order_id": "ORD_001", "error": None,
             "target_weight": 0.10, "current_weight": 0.04},
        ]
        update_dashboard(signal, results, session_dir=tmp_path)

        pnl_file = tmp_path / "pnl_latest.json"
        assert pnl_file.exists()
        data = json.loads(pnl_file.read_text())
        assert data["num_trades_executed"] == 1
        assert data["total_value"] == 2_000_000_000.0

    def test_failed_orders_not_in_trades(self, tmp_path):
        """Failed pipeline results are excluded from trades list."""
        signal = SAMPLE_SIGNAL
        results = [
            {"symbol": "VNM", "side": "BUY", "quantity": 1000, "price": 80000.0,
             "pipeline_state": "COMPLETED", "order_id": "ORD_001", "error": None,
             "target_weight": 0.10, "current_weight": 0.04},
            {"symbol": "FPT", "side": "BUY", "quantity": 500, "price": 100000.0,
             "pipeline_state": "FAILED", "order_id": "", "error": "Risk rejected",
             "target_weight": 0.08, "current_weight": 0.0},
        ]
        update_dashboard(signal, results, session_dir=tmp_path)

        data = json.loads((tmp_path / "risk_status.json").read_text())
        assert len(data["trades"]) == 1
        assert data["execution_summary"]["completed"] == 1
        assert data["execution_summary"]["failed"] == 1

    def test_update_dashboard_resolves_session_dir_dynamically(self, tmp_path):
        """update_dashboard resolves SESSION_DIR at runtime (not at import time)."""
        signal = SAMPLE_SIGNAL
        results = [
            {"symbol": "VNM", "side": "BUY", "quantity": 1000, "price": 80000.0,
             "pipeline_state": "COMPLETED", "order_id": "ORD_DYN", "error": None,
             "target_weight": 0.10, "current_weight": 0.04},
        ]
        
        with patch("scripts.run_paper_execution_pipeline.SESSION_DIR", tmp_path):
            update_dashboard(signal, results)

        # Verify files written to tmp_path
        assert (tmp_path / "risk_status.json").exists()
        assert (tmp_path / "pnl_latest.json").exists()
        
        # Verify content is correct
        risk_data = json.loads((tmp_path / "risk_status.json").read_text())
        assert risk_data["gate"] == "SIMULATED_TRADING_INTEGRATION_20260619"
        assert len(risk_data["trades"]) == 1


# ------------------------------------------------------------------ #
# save_execution_results tests
# ------------------------------------------------------------------ #

class TestSaveExecutionResults:
    """Tests for result file persistence."""

    def test_results_saved(self, tmp_path):
        """Execution results are saved to the expected path."""
        signal = {"date": "2026-06-19"}
        results = [
            {"symbol": "VNM", "pipeline_state": "COMPLETED", "order_id": "ORD_001"},
        ]
        diffs = [OrderDiff("VNM", "BUY", 1000, 80000.0, 0.10, 0.04)]

        path = save_execution_results(results, signal, diffs, session_dir=tmp_path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["total_diffs"] == 1
        assert data["completed"] == 1
        assert data["gate"] == "SIMULATED_TRADING_INTEGRATION_20260619"

    def test_results_saved_to_patched_session_dir(self, tmp_path):
        """save_execution_results resolves SESSION_DIR dynamically (not at import time)."""
        signal = {"date": "2026-06-20"}
        results = [
            {"symbol": "FPT", "pipeline_state": "COMPLETED", "order_id": "ORD_002"},
        ]
        diffs = [OrderDiff("FPT", "BUY", 500, 100000.0, 0.08, 0.0)]

        with patch("scripts.run_paper_execution_pipeline.SESSION_DIR", tmp_path):
            path = save_execution_results(results, signal, diffs)

        assert path.exists()
        assert path.parent == tmp_path
        data = json.loads(path.read_text())
        assert data["total_diffs"] == 1
        assert data["completed"] == 1


# ------------------------------------------------------------------ #
# End-to-end orchestration tests
# ------------------------------------------------------------------ #

class TestRunPaperExecutionPipeline:
    """Integration tests for the full pipeline orchestrator."""

    @pytest.fixture(autouse=True)
    def _reset_ks(self):
        """Reset global kill switch for each test."""
        from omega.core.sre.kill_switch import _reset_kill_switch_for_testing
        _reset_kill_switch_for_testing(auth_token="OMEGA_TEST")
        yield
        _reset_kill_switch_for_testing(auth_token="OMEGA_TEST")

    def test_no_signal_returns_error(self):
        """Pipeline returns error when no signal is available."""
        with patch("scripts.run_paper_execution_pipeline.load_latest_signal", return_value=None):
            result = run_paper_execution_pipeline()
            assert "error" in result
            assert result["total_diffs"] == 0

    def test_no_diffs_returns_zero(self):
        """Pipeline returns zero counts when positions already match targets."""
        signal = {"date": "2026-06-19", "positions": {}, "capital": 2_000_000_000.0}
        result = run_paper_execution_pipeline(signal=signal, current_positions={})
        assert result["total_diffs"] == 0

    def test_dry_run_returns_diffs_without_execution(self):
        """Dry run computes diffs but does not execute through pipeline."""
        result = run_paper_execution_pipeline(
            signal=SAMPLE_SIGNAL,
            current_positions=CURRENT_POSITIONS,
            dry_run=True,
        )
        assert result["dry_run"] is True
        assert result["total_diffs"] > 0
        assert "diffs" in result

    def test_full_pipeline_executes(self, tmp_path):
        """Full pipeline executes diffs, updates dashboard, saves results."""
        real_session_dir = _REPO_ROOT / ".ly_state" / "session"
        real_risk_status = real_session_dir / "risk_status.json"
        real_pnl_latest = real_session_dir / "pnl_latest.json"
        
        # Snapshot real dashboard files before test
        real_risk_before = real_risk_status.read_text() if real_risk_status.exists() else None
        real_pnl_before = real_pnl_latest.read_text() if real_pnl_latest.exists() else None
        
        with patch("scripts.run_paper_execution_pipeline.SESSION_DIR", tmp_path):
            with patch("scripts.run_paper_execution_pipeline.build_pipeline") as mock_build:
                # Create a mock pipeline
                from omega.execution.live_trading_pipeline import PipelineState
                mock_pipeline = MagicMock()
                mock_result = MagicMock()
                mock_result.state = PipelineState.COMPLETED
                mock_result.order_id = "ORD_E2E"
                mock_result.error = None
                mock_result.execution_orders = []
                mock_pipeline.submit_order.return_value = mock_result
                mock_build.return_value = mock_pipeline

                result = run_paper_execution_pipeline(
                    signal=SAMPLE_SIGNAL,
                    current_positions=CURRENT_POSITIONS,
                )

        assert result["total_diffs"] > 0
        assert result["total_executed"] == result["total_diffs"]
        assert result["completed"] == result["total_executed"]
        assert result["failed"] == 0
        
        # Verify files written to tmp_path (test isolation)
        assert (tmp_path / "risk_status.json").exists(), "risk_status.json should be in tmp_path"
        assert (tmp_path / "pnl_latest.json").exists(), "pnl_latest.json should be in tmp_path"
        
        # Verify real dashboard files were NOT modified
        real_risk_after = real_risk_status.read_text() if real_risk_status.exists() else None
        real_pnl_after = real_pnl_latest.read_text() if real_pnl_latest.exists() else None
        assert real_risk_before == real_risk_after, "Real risk_status.json should not be modified by test"
        assert real_pnl_before == real_pnl_after, "Real pnl_latest.json should not be modified by test"

    def test_build_pipeline_receives_current_positions_and_capital(self):
        with patch("scripts.run_paper_execution_pipeline.build_pipeline") as mock_build:
            mock_pipeline = MagicMock()
            mock_build.return_value = mock_pipeline

            run_paper_execution_pipeline(
                signal=SAMPLE_SIGNAL,
                current_positions=CURRENT_POSITIONS,
            )

        mock_build.assert_called_once_with(
            current_positions=CURRENT_POSITIONS,
            capital=SAMPLE_SIGNAL["capital"],
        )

    def test_pipeline_handles_all_failures(self, tmp_path):
        """Pipeline handles case where all orders fail."""
        real_session_dir = _REPO_ROOT / ".ly_state" / "session"
        real_risk_status = real_session_dir / "risk_status.json"
        real_pnl_latest = real_session_dir / "pnl_latest.json"
        
        # Snapshot real dashboard files before test
        real_risk_before = real_risk_status.read_text() if real_risk_status.exists() else None
        real_pnl_before = real_pnl_latest.read_text() if real_pnl_latest.exists() else None
        
        with patch("scripts.run_paper_execution_pipeline.SESSION_DIR", tmp_path):
            with patch("scripts.run_paper_execution_pipeline.build_pipeline") as mock_build:
                from omega.execution.live_trading_pipeline import PipelineState
                mock_pipeline = MagicMock()
                mock_result = MagicMock()
                mock_result.state = PipelineState.FAILED
                mock_result.order_id = ""
                mock_result.error = "Risk rejected"
                mock_result.execution_orders = []
                mock_pipeline.submit_order.return_value = mock_result
                mock_build.return_value = mock_pipeline

                result = run_paper_execution_pipeline(
                    signal=SAMPLE_SIGNAL,
                    current_positions=CURRENT_POSITIONS,
                )

        assert result["total_diffs"] > 0
        assert result["failed"] == result["total_executed"]
        
        # Verify files written to tmp_path (test isolation)
        assert (tmp_path / "risk_status.json").exists(), "risk_status.json should be in tmp_path"
        assert (tmp_path / "pnl_latest.json").exists(), "pnl_latest.json should be in tmp_path"
        
        # Verify real dashboard files were NOT modified
        real_risk_after = real_risk_status.read_text() if real_risk_status.exists() else None
        real_pnl_after = real_pnl_latest.read_text() if real_pnl_latest.exists() else None
        assert real_risk_before == real_risk_after, "Real risk_status.json should not be modified by test"
        assert real_pnl_before == real_pnl_after, "Real pnl_latest.json should not be modified by test"


# ------------------------------------------------------------------ #
# SSIBrokerGateway integration in LiveExecutionBridge
# ------------------------------------------------------------------ #

class TestLiveBridgeSSIGateway:
    """Tests for SSIBrokerGateway support in LiveExecutionBridge."""

    def test_paper_mode_uses_paper_engine(self):
        """Paper trading config creates PaperTradingEngine."""
        from omega.quant.execution.live_bridge import LiveExecutionBridge, BrokerConfig
        from omega.execution.broker_gateway import PaperTradingEngine

        config = BrokerConfig(
            broker_name="TEST",
            api_key="K", api_secret="S",
            account_id="A", base_url="http://test",
            paper_trading=True,
        )
        bridge = LiveExecutionBridge(config)
        assert isinstance(bridge._broker, PaperTradingEngine)
        assert bridge._broker_type == "PAPER"

    def test_live_mode_uses_ssi_gateway(self):
        """Non-paper config creates SSIBrokerGateway."""
        from omega.quant.execution.live_bridge import LiveExecutionBridge, BrokerConfig
        from omega.execution.order_router import SSIBrokerGateway

        config = BrokerConfig(
            broker_name="SSI",
            api_key="TEST_KEY",
            api_secret="TEST_SECRET",
            account_id="TEST_ACCT",
            base_url="https://api.ssi.test",
            paper_trading=False,
        )
        bridge = LiveExecutionBridge(config)
        assert isinstance(bridge._broker, SSIBrokerGateway)
        assert bridge._broker_type == "SSI"

    def test_ssi_gateway_with_custom_credentials(self):
        """Live mode accepts pre-built BrokerCredentials."""
        from omega.quant.execution.live_bridge import LiveExecutionBridge, BrokerConfig
        from omega.execution.broker_gateway import BrokerCredentials
        from omega.execution.order_router import SSIBrokerGateway

        creds = BrokerCredentials(
            broker_name="SSI",
            api_key="CUSTOM_KEY",
            api_secret="CUSTOM_SECRET",
            account_id="CUSTOM_ACCT",
            base_url="https://custom.ssi.test",
        )
        config = BrokerConfig(
            broker_name="SSI",
            api_key="", api_secret="",
            account_id="", base_url="",
            paper_trading=False,
            credentials=creds,
        )
        bridge = LiveExecutionBridge(config)
        assert isinstance(bridge._broker, SSIBrokerGateway)
        assert bridge._broker.credentials.api_key == "CUSTOM_KEY"

    def test_ssi_gateway_submit_order(self):
        """SSIBrokerGateway submits orders through LiveExecutionBridge."""
        from omega.quant.execution.live_bridge import LiveExecutionBridge, BrokerConfig, ExecutionState
        from omega.execution.broker_gateway import OrderSide, OrderType

        config = BrokerConfig(
            broker_name="SSI",
            api_key="TEST_KEY",
            api_secret="TEST_SECRET",
            account_id="TEST_ACCT",
            base_url="https://api.ssi.test",
            paper_trading=False,
        )
        bridge = LiveExecutionBridge(config)

        order = bridge.submit_order(
            symbol="VNM",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            current_price=80000.0,
        )

        # SSI gateway returns SUBMITTED (not immediately FILLED like paper)
        assert order.state == ExecutionState.SUBMITTED
        assert order.broker_order_id is not None
        assert order.broker_order_id.startswith("SSI_")

    def test_paper_engine_submit_order(self):
        """PaperTradingEngine submits orders with immediate fill."""
        from omega.quant.execution.live_bridge import LiveExecutionBridge, BrokerConfig, ExecutionState
        from omega.execution.broker_gateway import OrderSide, OrderType

        config = BrokerConfig(
            broker_name="PAPER",
            api_key="K", api_secret="S",
            account_id="A", base_url="paper://localhost",
            paper_trading=True,
        )
        bridge = LiveExecutionBridge(config)

        order = bridge.submit_order(
            symbol="FPT",
            side=OrderSide.BUY,
            quantity=500,
            order_type=OrderType.MARKET,
            current_price=100000.0,
        )

        assert order.state == ExecutionState.FILLED
        assert order.filled_quantity == 500
        assert order.average_fill_price == 100000.0
