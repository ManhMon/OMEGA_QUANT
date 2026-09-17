import pytest
from datetime import datetime, timezone, timedelta
from omega.quant.monitoring.pnl_monitor import PnLSlippageMonitor

def test_pnl_monitor_basic_trades_and_slippage():
    # 2B VND base, price_scale=1.0 (VND_FULL default)
    monitor = PnLSlippageMonitor(initial_equity=2_000_000_000.0, max_slippage_alert_threshold=10.0)
    ts1 = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    ts2 = ts1 + timedelta(minutes=5)
    
    # Buy 1000 shares VNM at fill=80100 benchmark=80000 (VND_FULL)
    # Buy slippage = (80100 - 80000) / 80000 * 10000 = 12.5 bps > 10.0 alert!
    r1 = monitor.record_trade("VNM", 1000, 80100.0, 80000.0, ts1)
    assert abs(r1.slippage_bps - 12.5) < 1e-5
    assert r1.alert_triggered
    assert r1.notional_vnd == 1000 * 80100.0 * 1.0  # VND_FULL: no *1000
    
    # Sell 500 shares VNM at fill=81000 benchmark=81100 (VND_FULL)
    # Sell slippage = (81100 - 81000) / 81100 * 10000 = 12.33 bps > 10.0 alert!
    r2 = monitor.record_trade("VNM", -500, 81000.0, 81100.0, ts2)
    assert abs(r2.slippage_bps - 12.3304) < 1e-2
    assert r2.alert_triggered
    
    # Validate positions and cash
    assert monitor._positions["VNM"] == 500
    assert monitor._average_costs["VNM"] == 80100.0
    
    summary = monitor.get_summary()
    assert summary["cash"] == 2_000_000_000.0 - (1000 * 80100.0 * 1.0) + (500 * 81000.0 * 1.0)
    assert summary["realized_pnl"] == 500 * (81000.0 - 80100.0) * 1.0
    assert summary["total_trades"] == 2
    assert summary["total_alerts"] == 2

def test_pnl_monitor_snapshot():
    monitor = PnLSlippageMonitor(initial_equity=100_000_000.0)
    ts = datetime(2026, 5, 19, 11, 0, 0, tzinfo=timezone.utc)
    
    # Mock position (VND_FULL prices)
    monitor.set_portfolio_state(
        positions={"HPG": 100},
        average_costs={"HPG": 30000.0},  # VND_FULL: 30,000 VND
        cash=97_000_000.0,
        realized_pnl=0.0,
        timestamp=ts
    )
    
    # Compute snapshot when current market price is 31000 (VND_FULL)
    # Unrealized = 100 * (31000 - 30000) * 1.0 = 100,000
    # Portfolio value = 97M + (100 * 31000 * 1.0) = 100.1M
    # Total P&L = 100.1M - 100M = 100,000
    snap = monitor.compute_pnl_snapshot({"HPG": 31000.0}, ts)
    assert snap.unrealized_pnl == 100_000.0
    assert snap.total_pnl == 100_000.0
    assert snap.portfolio_value == 100_100_000.0

def test_pnl_monitor_pit_violation():
    monitor = PnLSlippageMonitor()
    ts = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    
    monitor.record_trade("HPG", 100, 30000.0, 30000.0, ts)
    
    # Moving backwards raises ValueError
    with pytest.raises(ValueError, match="PIT violation"):
        monitor.record_trade("HPG", 100, 30000.0, 30000.0, ts - timedelta(seconds=1))
