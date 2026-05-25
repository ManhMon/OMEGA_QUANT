import pytest
from datetime import datetime, timezone, timedelta
from omega.quant.pnl_monitor import PnLSlippageMonitor

def test_pnl_monitor_basic_trades_and_slippage():
    # 2B VND base
    monitor = PnLSlippageMonitor(initial_equity=2_000_000_000.0, max_slippage_alert_threshold=10.0)
    ts1 = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    ts2 = ts1 + timedelta(minutes=5)
    
    # Buy 1000 shares VNM at fill=80.1 benchmark=80.0 (VN price unit scaled)
    # Buy slippage = (80.1 - 80) / 80 * 10000 = 12.5 bps > 10.0 alert!
    r1 = monitor.record_trade("VNM", 1000, 80.1, 80.0, ts1)
    assert abs(r1.slippage_bps - 12.5) < 1e-5
    assert r1.alert_triggered
    assert r1.notional_vnd == 1000 * 80.1 * 1000.0
    
    # Sell 500 shares VNM at fill=81.0 benchmark=81.1
    # Sell slippage = (81.1 - 81.0) / 81.1 * 10000 = 12.33 bps > 10.0 alert!
    r2 = monitor.record_trade("VNM", -500, 81.0, 81.1, ts2)
    assert abs(r2.slippage_bps - 12.3304) < 1e-2
    assert r2.alert_triggered
    
    # Validate positions and cash
    assert monitor._positions["VNM"] == 500
    assert monitor._average_costs["VNM"] == 80.1
    
    summary = monitor.get_summary()
    assert summary["cash"] == 2_000_000_000.0 - (1000 * 80.1 * 1000.0) + (500 * 81.0 * 1000.0)
    assert summary["realized_pnl"] == 500 * (81.0 - 80.1) * 1000.0
    assert summary["total_trades"] == 2
    assert summary["total_alerts"] == 2

def test_pnl_monitor_snapshot():
    monitor = PnLSlippageMonitor(initial_equity=100_000_000.0)
    ts = datetime(2026, 5, 19, 11, 0, 0, tzinfo=timezone.utc)
    
    # Mock position
    monitor.set_portfolio_state(
        positions={"HPG": 100},
        average_costs={"HPG": 30.0},
        cash=97_000_000.0,
        realized_pnl=0.0,
        timestamp=ts
    )
    
    # Compute snapshot when current market price is 31.0
    # Unrealized = 100 * (31 - 30) * 1000 = 100,000
    # Portfolio value = 97M + (100 * 31 * 1000) = 100.1M
    # Total P&L = 100.1M - 100M = 100,000
    snap = monitor.compute_pnl_snapshot({"HPG": 31.0}, ts)
    assert snap.unrealized_pnl == 100_000.0
    assert snap.total_pnl == 100_000.0
    assert snap.portfolio_value == 100_100_000.0

def test_pnl_monitor_pit_violation():
    monitor = PnLSlippageMonitor()
    ts = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    
    monitor.record_trade("HPG", 100, 30.0, 30.0, ts)
    
    # Moving backwards raises ValueError
    with pytest.raises(ValueError, match="PIT violation"):
        monitor.record_trade("HPG", 100, 30.0, 30.0, ts - timedelta(seconds=1))


def test_pnl_monitor_oversell_rejected_before_state_mutation():
    """P2.6 regression: oversell must be rejected BEFORE slippage_records is mutated."""
    monitor = PnLSlippageMonitor(initial_equity=10_000_000.0)
    ts1 = datetime(2026, 5, 25, 9, 0, 0, tzinfo=timezone.utc)
    ts2 = ts1 + timedelta(minutes=1)

    # Buy 10 shares
    monitor.record_trade("VNM", 10, 50.0, 50.0, ts1)
    assert len(monitor.slippage_records) == 1
    assert monitor._positions["VNM"] == 10

    # Attempt to sell 15 (oversell — Vietnam prohibits short selling)
    with pytest.raises(ValueError, match="Oversell rejected"):
        monitor.record_trade("VNM", -15, 50.0, 50.0, ts2)

    # State must be unchanged: no new record appended, position intact, timestamp not advanced
    assert len(monitor.slippage_records) == 1
    assert monitor._positions["VNM"] == 10
    assert monitor._get_latest_time() == ts1


def test_pnl_monitor_exact_liquidation_to_zero():
    """P2.6 regression: selling entire position must close it cleanly."""
    monitor = PnLSlippageMonitor(initial_equity=10_000_000.0)
    ts1 = datetime(2026, 5, 25, 9, 0, 0, tzinfo=timezone.utc)
    ts2 = ts1 + timedelta(minutes=1)

    monitor.record_trade("VNM", 10, 50.0, 50.0, ts1)
    monitor.record_trade("VNM", -10, 55.0, 55.0, ts2)

    assert "VNM" not in monitor._positions
    assert "VNM" not in monitor._average_costs
    assert len(monitor.slippage_records) == 2
    # Realized P&L: 10 * (55 - 50) * 1000 = 50,000
    assert monitor._realized_pnl == pytest.approx(50_000.0)


def test_pnl_monitor_partial_sell():
    """P2.6 regression: partial sell reduces position and realizes correct P&L."""
    monitor = PnLSlippageMonitor(initial_equity=10_000_000.0)
    ts1 = datetime(2026, 5, 25, 9, 0, 0, tzinfo=timezone.utc)
    ts2 = ts1 + timedelta(minutes=1)

    monitor.record_trade("VNM", 100, 40.0, 40.0, ts1)
    monitor.record_trade("VNM", -30, 45.0, 45.0, ts2)

    assert monitor._positions["VNM"] == 70
    assert monitor._average_costs["VNM"] == pytest.approx(40.0)
    # Realized P&L: 30 * (45 - 40) * 1000 = 150,000
    assert monitor._realized_pnl == pytest.approx(150_000.0)


def test_pnl_monitor_oversell_from_zero_position_rejected():
    """P2.6 regression: selling when no position exists must be rejected without mutation."""
    monitor = PnLSlippageMonitor(initial_equity=10_000_000.0)
    ts = datetime(2026, 5, 25, 9, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="Oversell rejected"):
        monitor.record_trade("VNM", -1, 50.0, 50.0, ts)

    assert len(monitor.slippage_records) == 0
    assert monitor._get_latest_time() is None


def test_pnl_monitor_set_portfolio_state_repeated_calls():
    """P2.7 regression: repeated set_portfolio_state() calls must be monotonic."""
    monitor = PnLSlippageMonitor()
    ts1 = datetime(2026, 5, 25, 9, 0, 0, tzinfo=timezone.utc)
    ts2 = ts1 + timedelta(minutes=5)

    monitor.set_portfolio_state({"VNM": 100}, {"VNM": 50.0}, 5_000_000.0, 0.0, ts1)
    # Same timestamp is allowed (equal, not backwards)
    monitor.set_portfolio_state({"VNM": 100}, {"VNM": 50.0}, 5_000_000.0, 0.0, ts1)
    # Forward timestamp is allowed
    monitor.set_portfolio_state({"VNM": 200}, {"VNM": 51.0}, 4_000_000.0, 1000.0, ts2)
    assert monitor._positions["VNM"] == 200

    # Backwards timestamp must raise
    with pytest.raises(ValueError, match="PIT violation"):
        monitor.set_portfolio_state({"VNM": 50}, {"VNM": 49.0}, 6_000_000.0, 0.0, ts1 - timedelta(seconds=1))
