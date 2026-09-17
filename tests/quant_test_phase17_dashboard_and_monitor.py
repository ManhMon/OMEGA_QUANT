import pytest
import os
import json
import logging
from datetime import datetime, UTC, timedelta, timezone
from unittest.mock import patch, MagicMock

from omega.quant.monitoring.dashboard import DashboardManager, ProductionMonitor, SystemState

logger = logging.getLogger(__name__)

def test_dashboard_manager_empty():
    manager = DashboardManager()
    current_time = datetime.now(timezone.utc)
    
    var_95, cvar_95 = manager.calculate_var_cvar(0.95, current_time)
    assert var_95 == 0.0
    assert cvar_95 == 0.0
    
    beta = manager.calculate_portfolio_beta(current_time)
    assert beta == 0.0
    
    max_dd, curr_dd = manager.calculate_drawdowns(current_time)
    assert max_dd == 0.0
    assert curr_dd == 0.0
    
    sharpe = manager.calculate_sharpe_ratio(current_time)
    assert sharpe == 0.0

def test_dashboard_manager_math_calculations():
    manager = DashboardManager()
    start_time = datetime(2026, 5, 1, 9, 0, 0, tzinfo=timezone.utc)
    
    # 1. Add chronological daily returns
    # Portfolio returns: [-0.01, -0.02, 0.03, 0.01, -0.015, 0.02, -0.01, -0.03, 0.04, 0.02]
    # Benchmark returns: [-0.005, -0.01, 0.015, 0.005, -0.008, 0.01, -0.005, -0.015, 0.02, 0.01] (approx Beta ~ 2.0)
    p_returns = [-0.01, -0.02, 0.03, 0.01, -0.015, 0.02, -0.01, -0.03, 0.04, 0.02]
    b_returns = [-0.005, -0.01, 0.015, 0.005, -0.008, 0.01, -0.005, -0.015, 0.02, 0.01]
    
    for i, (p_ret, b_ret) in enumerate(zip(p_returns, b_returns)):
        ts = start_time + timedelta(days=i)
        manager.add_daily_return(ts, p_ret)
        manager.add_benchmark_return(ts, b_ret)
        
    current_time = start_time + timedelta(days=9)
    
    # 2. Test VaR and CVaR (95% and 99%)
    var_95, cvar_95 = manager.calculate_var_cvar(0.95, current_time)
    var_99, cvar_99 = manager.calculate_var_cvar(0.99, current_time)
    
    # Percentile 95% = 5% worst return. 
    # Returns sorted: [-0.03, -0.02, -0.015, -0.01, -0.01, 0.01, 0.02, 0.02, 0.03, 0.04]
    # With 10 returns, 5th percentile is between index 0 and 1.
    assert var_95 > 0.0
    assert cvar_95 >= var_95
    assert var_99 >= var_95
    assert cvar_99 >= var_99
    
    # 3. Test Portfolio Beta
    beta = manager.calculate_portfolio_beta(current_time)
    assert 1.8 < beta < 2.2
    
    # 4. Test Drawdown
    max_dd, curr_dd = manager.calculate_drawdowns(current_time)
    # Cumulative returns of portfolio:
    # 0.0 -> -0.01 -> -0.03 -> 0.0 -> 0.01 -> -0.005 -> 0.015 -> 0.005 -> -0.025 -> 0.015 -> 0.035
    # Peaks: 0.0 -> 0.0 -> 0.0 -> 0.0 -> 0.01 -> 0.01 -> 0.015 -> 0.015 -> 0.015 -> 0.015 -> 0.035
    # Drawdowns: 0.0 -> 0.01 -> 0.03 -> 0.0 -> 0.0 -> 0.015 -> 0.0 -> 0.01 -> 0.04 -> 0.0 -> 0.0
    assert abs(max_dd - 0.04) < 1e-5
    assert curr_dd == 0.0
    
    # 5. Sharpe ratio
    sharpe = manager.calculate_sharpe_ratio(current_time)
    assert isinstance(sharpe, float)

def test_pit_safety_lookahead():
    # Verify chronological filtering works.
    # If current_time is limited to T=5, returns after T=5 must not be included.
    manager = DashboardManager()
    start_time = datetime(2026, 5, 1, 9, 0, 0, tzinfo=timezone.utc)
    
    p_returns = [-0.01, -0.02, 0.03, 0.01, -0.015, 0.02, -0.01, -0.03, 0.04, 0.02]
    for i, p_ret in enumerate(p_returns):
        ts = start_time + timedelta(days=i)
        manager.add_daily_return(ts, p_ret)
        
    # At day 4 (index 4) (May 5th)
    current_time_pit = start_time + timedelta(days=4)
    df_pit = manager._get_returns_up_to(current_time_pit)
    
    # Returns should only contain May 1 to May 5 (5 returns)
    assert len(df_pit) == 5
    assert list(df_pit["return"].values) == [-0.01, -0.02, 0.03, 0.01, -0.015]

def test_production_monitor_circuit_breakers_and_export():
    manager = DashboardManager()
    start_time = datetime(2026, 5, 1, 9, 0, 0, tzinfo=timezone.utc)
    
    # Setup monitor
    # Breach thresholds: VaR 95% > 0.02, Max Drawdown > 0.035, Max Consecutive Losses > 3
    monitor = ProductionMonitor(
        dashboard_manager=manager,
        var_breach_threshold=0.02,
        max_drawdown_threshold=0.035,
        max_consecutive_losses=3,
        slack_webhook_url="https://hooks.slack.com/services/test/webhook"
    )
    
    # Safe period returns
    p_returns = [-0.005, -0.008, 0.01, 0.005]
    for i, p_ret in enumerate(p_returns):
        ts = start_time + timedelta(days=i)
        manager.add_daily_return(ts, p_ret)
        
    current_time = start_time + timedelta(days=3)
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response
        
        state = monitor.evaluate_circuit_breakers(current_time)
        assert state == SystemState.RUNNING
        
        # Verify JSON snapshot exported
        assert os.path.exists(monitor.export_path)
        with open(monitor.export_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data["system_state"] == "RUNNING"
            assert data["breached"] is False
            
    # Trigger Drawdown breach
    # Cumulative return goes down: -0.005 -> -0.013 -> -0.003 -> 0.002 -> -0.04 -> -0.05
    # Max drawdown will exceed 0.035
    manager.add_daily_return(start_time + timedelta(days=4), -0.042)
    manager.add_daily_return(start_time + timedelta(days=5), -0.01)
    
    current_time = start_time + timedelta(days=5)
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response
        
        state = monitor.evaluate_circuit_breakers(current_time)
        assert state == SystemState.EMERGENCY_STOP
        
        # Check Slack webhook called
        mock_urlopen.assert_called_once()
        
        # Verify JSON state updated
        with open(monitor.export_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data["system_state"] == "EMERGENCY_STOP"
            assert data["breached"] is True
            assert any("Max Drawdown" in r for r in data["breached_reasons"])

def test_slack_alert_cooldown():
    manager = DashboardManager()
    monitor = ProductionMonitor(
        dashboard_manager=manager,
        var_breach_threshold=0.01,
        max_drawdown_threshold=0.01,
        max_consecutive_losses=2,
        slack_webhook_url="https://hooks.slack.com/services/test/webhook",
        alert_cooldown_seconds=60.0
    )
    
    current_time = datetime(2026, 5, 1, 9, 0, 0, tzinfo=timezone.utc)
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value = mock_response
        
        # First alert - goes through
        monitor.send_slack_alert("Emergency alert!", current_time)
        assert mock_urlopen.call_count == 1
        
        # Second alert within 30 seconds - throttled
        monitor.send_slack_alert("Throttled alert!", current_time + timedelta(seconds=30))
        assert mock_urlopen.call_count == 1
        
        # Third alert after 65 seconds - goes through
        monitor.send_slack_alert("New alert after cooldown!", current_time + timedelta(seconds=65))
        assert mock_urlopen.call_count == 2
