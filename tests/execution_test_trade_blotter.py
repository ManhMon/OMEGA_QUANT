"""
OMEGA_QUANT Execution Engine Tests (Layer 03)
Phase 4.3: Trade Blotter Tests

Tests for TradeBlotter including trade recording, persistence,
reconciliation, and summary statistics.

Author: QA Engineer (Role 17)
Date: 2026-05-18
Version: 1.0.0
"""

import pytest
import os
import json
import tempfile

from omega.execution import (
    TradeRecord,
    TradeBlotter,
)


class TestTradeBlotter:
    """Tests for TradeBlotter class."""
    
    @pytest.fixture
    def temp_blotter_path(self):
        """Create temporary file for blotter persistence."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            path = f.name
        yield path
        # Cleanup
        if os.path.exists(path):
            os.remove(path)
    
    def test_record_trade(self):
        """Test recording a single trade."""
        blotter = TradeBlotter()
        
        record = blotter.record_trade(
            broker_order_id="SSI_123456",
            client_order_id="CLI_001",
            symbol="VNM",
            side="BUY",
            quantity=100,
            price=50.0,
            commission_rate=0.0015
        )
        
        assert record.trade_id is not None
        assert record.symbol == "VNM"
        assert record.side == "BUY"
        assert record.quantity == 100
        assert record.price == 50.0
        # Notional = 100 * 50 * 1000 = 5,000,000 VND
        assert record.notional_value == 5_000_000.0
        # Commission = 5,000,000 * 0.0015 = 7,500 VND
        assert record.commission == 7_500.0
    
    def test_save_and_load_trades(self, temp_blotter_path):
        """Test persisting and loading trades."""
        # Record trades
        blotter1 = TradeBlotter(temp_blotter_path)
        blotter1.record_trade("SSI_001", "CLI_001", "VNM", "BUY", 100, 50.0)
        blotter1.record_trade("SSI_002", "CLI_002", "HPG", "SELL", 200, 25.0)
        
        # Load trades
        blotter2 = TradeBlotter(temp_blotter_path)
        assert len(blotter2.trades) == 2
        
        symbols = {t.symbol for t in blotter2.trades.values()}
        assert symbols == {"VNM", "HPG"}
    
    def test_reconcile_with_broker_success(self):
        """Test successful reconciliation with broker statement."""
        blotter = TradeBlotter()
        
        # Record local trades
        blotter.record_trade("SSI_001", "CLI_001", "VNM", "BUY", 100, 50.0)
        blotter.record_trade("SSI_002", "CLI_002", "HPG", "SELL", 200, 25.0)
        
        # Broker statement (matching)
        broker_trades = [
            {"broker_order_id": "SSI_001", "symbol": "VNM", "side": "BUY", "quantity": 100, "price": 50.0},
            {"broker_order_id": "SSI_002", "symbol": "HPG", "side": "SELL", "quantity": 200, "price": 25.0},
        ]
        
        recon = blotter.reconcile_with_broker(broker_trades)
        
        assert recon["success"] is True
        assert recon["matched_count"] == 2
        assert recon["missing_local_count"] == 0
        assert recon["missing_broker_count"] == 0
    
    def test_reconcile_with_broker_discrepancy(self):
        """Test reconciliation with price discrepancy."""
        blotter = TradeBlotter()
        
        # Record local trade
        blotter.record_trade("SSI_001", "CLI_001", "VNM", "BUY", 100, 50.0)
        
        # Broker statement with different price
        broker_trades = [
            {"broker_order_id": "SSI_001", "symbol": "VNM", "side": "BUY", "quantity": 100, "price": 50.5},
        ]
        
        recon = blotter.reconcile_with_broker(broker_trades)
        
        assert recon["success"] is False
        assert recon["discrepancies_count"] == 1
        assert "Price mismatch" in recon["discrepancies"][0]["errors"][0]
    
    def test_reconcile_with_broker_missing_local(self):
        """Test reconciliation with missing local trade."""
        blotter = TradeBlotter()
        
        # Record only one local trade
        blotter.record_trade("SSI_001", "CLI_001", "VNM", "BUY", 100, 50.0)
        
        # Broker statement has two trades
        broker_trades = [
            {"broker_order_id": "SSI_001", "symbol": "VNM", "side": "BUY", "quantity": 100, "price": 50.0},
            {"broker_order_id": "SSI_002", "symbol": "HPG", "side": "SELL", "quantity": 200, "price": 25.0},
        ]
        
        recon = blotter.reconcile_with_broker(broker_trades)
        
        assert recon["success"] is False
        assert recon["missing_local_count"] == 1
    
    def test_get_summary_stats(self):
        """Test aggregate trade statistics."""
        blotter = TradeBlotter()
        
        blotter.record_trade("SSI_001", "CLI_001", "VNM", "BUY", 100, 50.0)
        blotter.record_trade("SSI_002", "CLI_002", "VNM", "BUY", 200, 50.0)
        blotter.record_trade("SSI_003", "CLI_003", "HPG", "SELL", 300, 25.0)
        
        stats = blotter.get_summary_stats()
        
        assert stats["total_trades"] == 3
        # BUY value = (100 + 200) * 50 * 1000 = 15,000,000 VND
        assert stats["total_buy_value_vnd"] == 15_000_000.0
        # SELL value = 300 * 25 * 1000 = 7,500,000 VND
        assert stats["total_sell_value_vnd"] == 7_500_000.0
        assert stats["total_turnover_vnd"] == 22_500_000.0
        
        # By symbol stats
        assert "VNM" in stats["by_symbol"]
        assert stats["by_symbol"]["VNM"]["trades"] == 2
        assert stats["by_symbol"]["VNM"]["volume"] == 300
