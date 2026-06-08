"""
OMEGA_QUANT Execution Engine Tests (Layer 03)
Phase 4.3: Order Book Analyzer Tests

Tests for OrderBookAnalyzer including OBI, VWMP, pressure, slippage,
liquidity assessment, and timing optimization.

Author: QA Engineer (Role 17)
Date: 2026-05-18
Version: 1.0.0
"""

import pytest
from omega.execution import (
    OrderBookAnalyzer,
    MarketDepth,
    OrderBookSnapshot,
)


class TestOrderBookAnalyzer:
    """Tests for OrderBookAnalyzer class."""
    
    @pytest.fixture
    def analyzer(self):
        """Create OrderBookAnalyzer."""
        return OrderBookAnalyzer()
    
    @pytest.fixture
    def mock_order_book(self):
        """Mock bid and ask levels."""
        bids = [
            {"price": 49.8, "volume": 1000},
            {"price": 49.7, "volume": 1500},
            {"price": 49.6, "volume": 2000},
        ]
        asks = [
            {"price": 50.2, "volume": 1200},
            {"price": 50.3, "volume": 1800},
            {"price": 50.4, "volume": 2500},
        ]
        return bids, asks
    
    def test_compute_obi(self, analyzer, mock_order_book):
        """Test Order Book Imbalance calculation."""
        bids, asks = mock_order_book
        
        # bid_volume = 4500, ask_volume = 5500
        # OBI = (4500 - 5500) / 10000 = -0.10
        obi = analyzer.compute_obi(bids, asks)
        assert abs(obi - (-0.10)) < 1e-5
        
        # Test empty book handles gracefully
        assert analyzer.compute_obi([], []) == 0.0
    
    def test_compute_vwmp(self, analyzer, mock_order_book):
        """Test Volume-Weighted Mid Price calculation."""
        bids, asks = mock_order_book
        
        vwmp = analyzer.compute_vwmp(bids, asks)
        # bid_price_vol = 49.8*1000 + 49.7*1500 + 49.6*2000 = 223550
        # ask_price_vol = 50.2*1200 + 50.3*1800 + 50.4*2500 = 276780
        # total_price_vol = 500330
        # total_vol = 10000
        # VWMP = 50.033
        assert abs(vwmp - 50.033) < 1e-5
        
        assert analyzer.compute_vwmp([], []) == 0.0
    
    def test_get_pressure(self, analyzer, mock_order_book):
        """Test market pressure direction detection."""
        bids, asks = mock_order_book
        # OBI = -0.10 => NEUTRAL
        assert analyzer.get_pressure(bids, asks) == 'NEUTRAL'
        
        # BUY pressure: bid volume > ask volume
        buy_bids = [{"price": 49.8, "volume": 8000}]
        buy_asks = [{"price": 50.2, "volume": 2000}]
        # OBI = (8000 - 2000) / 10000 = 0.60
        assert analyzer.get_pressure(buy_bids, buy_asks) == 'BUY'
        
        # SELL pressure: ask volume > bid volume
        sell_bids = [{"price": 49.8, "volume": 2000}]
        sell_asks = [{"price": 50.2, "volume": 8000}]
        # OBI = (2000 - 8000) / 10000 = -0.60
        assert analyzer.get_pressure(sell_bids, sell_asks) == 'SELL'
    
    def test_assess_liquidity(self, analyzer, mock_order_book):
        """Test liquidity assessment for order sizing."""
        bids, asks = mock_order_book
        
        # BUY order of 100 shares
        # asks depth = 5500 shares. 100 shares is way below depth => EXCELLENT liquidity
        liq = analyzer.assess_liquidity(bids, asks, 100)
        assert liq["rating"] == "EXCELLENT"
        assert liq["can_execute_immediately"] is True
        
        # BUY order of 6000 shares
        # asks depth = 5500 shares. 6000 shares exceeds asks => POOR liquidity
        liq_poor = analyzer.assess_liquidity(bids, asks, 6000)
        assert liq_poor["rating"] == "POOR"
        assert liq_poor["can_execute_immediately"] is False
    
    def test_estimate_slippage(self, analyzer):
        """Test slippage estimation."""
        # 1. Normal order size, low ADV
        slippage = analyzer.estimate_slippage(
            order_size=1000,
            avg_daily_volume=10000,  # 10% of ADV => Volume factor = 4.0
            market_depth={"spread_bps": 2.0}
        )
        # Expected = 1.5 * 4.0 + 2.0 * 0.5 = 7.0 bps
        assert slippage == 7.0
        
        # 2. Minimum slippage floor
        slippage_min = analyzer.estimate_slippage(
            order_size=10,
            avg_daily_volume=100000,
            market_depth={"spread_bps": 0.5}
        )
        assert slippage_min >= 0.5
    
    def test_optimize_timing(self, analyzer):
        """Test timing optimization recommendations."""
        # Stable midday execution
        rec = analyzer.optimize_timing("11:30", market_volatility=0.015)
        assert rec["timing"] == "STABLE"
        assert rec["estimated_slippage_factor"] == 1.0
        
        # Volatile close execution
        rec_close = analyzer.optimize_timing("14:15", market_volatility=0.03)
        assert rec_close["timing"] == "VOLATILE"
        assert rec_close["volatility_rating"] == "HIGH"
        assert rec_close["estimated_slippage_factor"] > 1.0
