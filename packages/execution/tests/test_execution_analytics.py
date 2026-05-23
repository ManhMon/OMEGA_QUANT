"""
OMEGA_QUANT Execution Engine Tests (Layer 03)
Phase 4.3: Execution Analytics Tests

Tests for ExecutionAnalytics including slippage, fill rate, market impact,
execution cost, and P&L attribution.

Author: QA Engineer (Role 17)
Date: 2026-05-18
Version: 1.0.0
"""

import pytest
import time

from omega.execution import (
    ExecutionAnalytics,
    ExecutionMetrics,
)


class TestExecutionAnalytics:
    """Tests for ExecutionAnalytics class."""
    
    @pytest.fixture
    def analytics(self):
        """Create ExecutionAnalytics."""
        return ExecutionAnalytics()
    
    def test_calculate_slippage_buy(self, analytics):
        """Test slippage calculation for BUY order."""
        # Executed at 50.5, reference at 50.0
        # Slippage = (50.5 - 50.0) / 50.0 * 10000 = 100 bps
        slippage = analytics.calculate_slippage(
            symbol="VNM",
            side="BUY",
            execution_price=50.5,
            reference_price=50.0
        )
        assert slippage == 100.0
    
    def test_calculate_slippage_sell(self, analytics):
        """Test slippage calculation for SELL order."""
        # Executed at 49.5, reference at 50.0
        # Slippage = (50.0 - 49.5) / 50.0 * 10000 = 100 bps
        slippage = analytics.calculate_slippage(
            symbol="VNM",
            side="SELL",
            execution_price=49.5,
            reference_price=50.0
        )
        assert slippage == 100.0
    
    def test_calculate_fill_rate(self, analytics):
        """Test fill rate calculation."""
        assert analytics.calculate_fill_rate(1000, 1000) == 1.0
        assert analytics.calculate_fill_rate(1000, 500) == 0.5
        assert analytics.calculate_fill_rate(1000, 0) == 0.0
        assert analytics.calculate_fill_rate(0, 0) == 0.0
    
    def test_calculate_market_impact(self, analytics):
        """Test market impact estimation."""
        # 1000 shares, ADV 10000, volatility 2%
        impact = analytics.calculate_market_impact(
            order_size=1000,
            avg_daily_volume=10000,
            volatility=0.02
        )
        # Participation = 0.1, impact should be > 0
        assert impact > 0
        assert impact < 10  # Reasonable range
    
    def test_calculate_execution_cost(self, analytics):
        """Test total execution cost calculation."""
        cost = analytics.calculate_execution_cost(
            slippage_bps=50.0,
            market_impact_bps=30.0,
            commission_bps=15.0
        )
        assert cost == 95.0
    
    def test_record_execution(self, analytics):
        """Test recording a complete execution."""
        metrics = analytics.record_execution(
            symbol="VNM",
            side="BUY",
            quantity=1000,
            target_price=50.0,
            execution_price=50.2,
            filled_quantity=1000,
            latency_ms=150.0,
            avg_daily_volume=100000,
            volatility=0.02,
            commission_rate=0.0015
        )
        
        assert isinstance(metrics, ExecutionMetrics)
        assert metrics.symbol == "VNM"
        assert metrics.side == "BUY"
        assert metrics.quantity == 1000
        assert metrics.slippage_bps == pytest.approx(40.0, abs=0.01)  # (50.2 - 50.0) / 50.0 * 10000
        assert metrics.fill_rate == 1.0
        assert metrics.latency_ms == 150.0
        assert metrics.execution_cost_bps > 0
    
    def test_get_summary_statistics(self, analytics):
        """Test aggregate execution statistics."""
        # Record multiple executions
        for i in range(3):
            analytics.record_execution(
                symbol="VNM",
                side="BUY",
                quantity=1000,
                target_price=50.0,
                execution_price=50.1 + i * 0.05,
                filled_quantity=1000,
                latency_ms=100.0 + i * 10,
                avg_daily_volume=100000,
                volatility=0.02
            )
        
        stats = analytics.get_summary_statistics()
        
        assert stats["total_executions"] == 3
        assert stats["average_slippage_bps"] > 0
        assert stats["average_fill_rate"] == 1.0
        assert stats["average_latency_ms"] > 0
    
    def test_get_by_symbol_statistics(self, analytics):
        """Test execution statistics grouped by symbol."""
        # Record VNM trades
        analytics.record_execution(
            symbol="VNM",
            side="BUY",
            quantity=1000,
            target_price=50.0,
            execution_price=50.1,
            filled_quantity=1000,
            latency_ms=100.0,
            avg_daily_volume=100000,
            volatility=0.02
        )
        
        # Record HPG trades
        analytics.record_execution(
            symbol="HPG",
            side="SELL",
            quantity=500,
            target_price=25.0,
            execution_price=24.9,
            filled_quantity=500,
            latency_ms=80.0,
            avg_daily_volume=50000,
            volatility=0.015
        )
        
        stats = analytics.get_by_symbol_statistics()
        
        assert "VNM" in stats
        assert "HPG" in stats
        assert stats["VNM"]["executions"] == 1
        assert stats["HPG"]["executions"] == 1
    
    def test_get_by_side_statistics(self, analytics):
        """Test execution statistics grouped by side."""
        analytics.record_execution(
            symbol="VNM",
            side="BUY",
            quantity=1000,
            target_price=50.0,
            execution_price=50.1,
            filled_quantity=1000,
            latency_ms=100.0,
            avg_daily_volume=100000,
            volatility=0.02
        )
        
        analytics.record_execution(
            symbol="HPG",
            side="SELL",
            quantity=500,
            target_price=25.0,
            execution_price=24.9,
            filled_quantity=500,
            latency_ms=80.0,
            avg_daily_volume=50000,
            volatility=0.015
        )
        
        stats = analytics.get_by_side_statistics()
        
        assert "BUY" in stats
        assert "SELL" in stats
        assert stats["BUY"]["executions"] == 1
        assert stats["SELL"]["executions"] == 1
    
    def test_calculate_pnl_attribution(self, analytics):
        """Test P&L attribution (alpha vs execution cost)."""
        # Alpha P&L = 100,000 VND
        # Execution cost = 50 bps on 10M VND = 5,000 VND
        attribution = analytics.calculate_pnl_attribution(
            alpha_pnl=100_000.0,
            execution_cost_bps=50.0,
            notional_value=10_000_000.0
        )
        
        assert attribution["alpha_pnl_vnd"] == 100_000.0
        assert attribution["execution_cost_vnd"] == pytest.approx(50_000.0, abs=1.0)  # 10M * (50 bps / 10000) = 50,000 VND
        assert attribution["net_pnl_vnd"] == pytest.approx(50_000.0, abs=1.0)  # 100,000 - 50,000
        assert attribution["execution_cost_ratio"] == pytest.approx(0.5, abs=0.01)  # 50%

    def test_validate_benchmark_price_envelope_rejections(self, analytics):
        """Benchmark validation must reject envelopes with future timestamps or missing fields."""
        future_ts = time.time() + 3600.0
        
        # 1. Reject future timestamp
        with pytest.raises(ValueError, match="PIT Safety violation"):
            analytics.calculate_slippage(
                symbol="VNM",
                side="BUY",
                execution_price=50.0,
                reference_price={"price": 50.0, "timestamp": future_ts, "provenance": "future-feed"}
            )
            
        # 2. Reject missing envelope fields
        with pytest.raises(ValueError, match="envelope must include"):
            analytics.calculate_slippage(
                symbol="VNM",
                side="BUY",
                execution_price=50.0,
                reference_price={"price": 50.0, "provenance": "incomplete-feed"}
            )
            
        # 3. Accept valid envelope
        slippage = analytics.calculate_slippage(
            symbol="VNM",
            side="BUY",
            execution_price=50.2,
            reference_price={"price": 50.0, "timestamp": time.time(), "provenance": "broker-feed"}
        )
        assert slippage == pytest.approx(40.0, abs=0.1)  # 40 bps
