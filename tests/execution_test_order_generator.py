"""
OMEGA_QUANT Execution Engine Tests (Layer 03)
Phase 4.3: Order Generator Tests

Tests for OrderGenerator with position sizing, board-lot rounding,
compliance checks, and batching.

Author: QA Engineer (Role 17)
Date: 2026-05-18
Version: 1.0.0
"""

import pytest
from omega.execution import (
    PositionSizingConfig,
    OrderGenerator,
    BrokerOrder,
    OrderSide,
    OrderType,
)


class TestOrderGenerator:
    """Tests for OrderGenerator class."""
    
    @pytest.fixture
    def default_generator(self):
        """Create a default OrderGenerator."""
        return OrderGenerator()
    
    def test_round_to_board_lot(self, default_generator):
        """Test board-lot rounding logic."""
        # Standard rounding (board lot = 100)
        assert default_generator._round_to_board_lot(100) == 100
        assert default_generator._round_to_board_lot(149) == 100
        assert default_generator._round_to_board_lot(150) == 200
        assert default_generator._round_to_board_lot(201) == 200
        assert default_generator._round_to_board_lot(0) == 0
        
        # Less than board lot size
        assert default_generator._round_to_board_lot(50) == 0
        assert default_generator._round_to_board_lot(50, allow_odd_lot=True) == 50
    
    def test_generate_orders_portfolio_rebalance(self, default_generator):
        """Test generating rebalance orders from target/current portfolio."""
        target = {
            "VNM": {"quantity": 1000},
            "HPG": {"quantity": 500},
            "VIC": {"quantity": 0}
        }
        current = {
            "VNM": {"quantity": 500},
            "HPG": {"quantity": 800},
            "VIC": {"quantity": 200}
        }
        
        orders = default_generator.generate_orders(target, current)
        
        # Should generate:
        # VNM: BUY 500
        # HPG: SELL 300
        # VIC: SELL 200
        assert len(orders) == 3
        
        vnm_order = next(o for o in orders if o["symbol"] == "VNM")
        assert vnm_order["side"] == "BUY"
        assert vnm_order["quantity"] == 500
        
        hpg_order = next(o for o in orders if o["symbol"] == "HPG")
        assert hpg_order["side"] == "SELL"
        assert hpg_order["quantity"] == 300
        
        vic_order = next(o for o in orders if o["symbol"] == "VIC")
        assert vic_order["side"] == "SELL"
        assert vic_order["quantity"] == 200

    def test_generate_orders_preserves_odd_lot_liquidation_to_zero(self, default_generator):
        """Liquidation to zero may emit odd-lot sell without up-rounding."""
        target = {"VIC": {"quantity": 0}}
        current = {"VIC": {"quantity": 75}}

        orders = default_generator.generate_orders(target, current)

        assert orders == [{
            "symbol": "VIC",
            "quantity": 75,
            "order_type": "MARKET",
            "time_in_force": "DAY",
            "price": None,
            "side": "SELL",
            "allow_odd_lot": True,
        }]
    
    def test_convert_signal_to_order(self, default_generator):
        """Test converting single alpha signal to BrokerOrder."""
        # Target weight 5%, portfolio value 1B VND, price 50000 (VND_FULL)
        # Target notional = 50M VND
        # Target qty = 50M / 50000 = 1000 shares
        order = default_generator.convert_signal_to_order(
            symbol="VNM",
            signal_weight=0.05,
            portfolio_value=1_000_000_000.0,
            current_price=50000.0,  # VND_FULL: 50,000 VND
            current_position=0
        )
        
        assert order is not None
        assert order.symbol == "VNM"
        assert order.side == OrderSide.BUY
        assert order.quantity == 1000
        
        # Target quantity = 1000, current = 800 => BUY 200
        order_adjust = default_generator.convert_signal_to_order(
            symbol="VNM",
            signal_weight=0.05,
            portfolio_value=1_000_000_000.0,
            current_price=50000.0,  # VND_FULL
            current_position=800
        )
        
        assert order_adjust is not None
        assert order_adjust.side == OrderSide.BUY
        assert order_adjust.quantity == 200
    
    def test_batch_orders(self, default_generator):
        """Test order batching grouping by side."""
        orders = [
            BrokerOrder("VNM", OrderSide.BUY, 100, OrderType.MARKET),
            BrokerOrder("HPG", OrderSide.SELL, 200, OrderType.MARKET),
            BrokerOrder("VIC", OrderSide.BUY, 300, OrderType.MARKET),
        ]
        
        batches = default_generator.batch_orders(orders)
        
        assert len(batches) == 2
        # BUY batch
        assert len(batches[0]) == 2
        assert all(o.side == OrderSide.BUY for o in batches[0])
        # SELL batch
        assert len(batches[1]) == 1
        assert batches[1][0].symbol == "HPG"
    
    def test_validate_compliance(self, default_generator):
        """Test compliance checks."""
        # 1. Valid order (price in VND_FULL)
        order = BrokerOrder("VNM", OrderSide.BUY, 500, OrderType.MARKET)
        is_valid, msg = default_generator.validate_compliance(
            order=order,
            current_price=50000.0,  # VND_FULL: 50,000 VND
            adv=10000,
            portfolio_value=1_000_000_000.0
        )
        assert is_valid is True
        
        # 2. Position weight exceeds limit (max 5%)
        # Order value = 2000 * 50000 = 100M VND (10% of 1B)
        big_order = BrokerOrder("VNM", OrderSide.BUY, 2000, OrderType.MARKET)
        is_valid, msg = default_generator.validate_compliance(
            order=big_order,
            current_price=50000.0,  # VND_FULL: 50,000 VND
            adv=10000,
            portfolio_value=1_000_000_000.0
        )
        assert is_valid is False
        assert "exceeds limit" in msg
        
        # 3. Exceeds 20% of ADV
        low_adv_order = BrokerOrder("VNM", OrderSide.BUY, 500, OrderType.MARKET)
        is_valid, msg = default_generator.validate_compliance(
            order=low_adv_order,
            current_price=50000.0,  # VND_FULL
            adv=1000,  # ADV = 1000, 20% = 200. Order qty = 500.
            portfolio_value=1_000_000_000.0
        )
        assert is_valid is False
        assert "exceeds 20% of ADV" in msg
