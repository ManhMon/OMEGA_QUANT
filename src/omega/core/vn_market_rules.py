"""
Vietnam Market Rules - Centralized VN Market-Specific Rules
Consolidates all Vietnam market conventions: board lots, tick sizes, settlement cycles.

This module centralizes VN market rules scattered across:
- risk_manager.py (board lot rounding)
- execution scripts (tick size rounding)
- test files (inline rounding logic)

Author: OpenCode (AI Assistant)
Date: 2026-05-05
Status: OMEGA_QUANT Consolidation - Monolithic omega.core
Plan: docs/CONSOLIDATION_PLAN.md
"""

from typing import Dict, Tuple


class VnMarketRules:
    """
    Vietnam market-specific rules and conventions.

    Features:
    - Board lot rounding (100 shares minimum)
    - Tick size rounding (price-dependent)
    - Settlement cycle (T+2.5)
    - Trading hours and market sessions
    - Price limit rules (ceiling/floor)

    Usage:
        from omega.core.vn_market_rules import VnMarketRules

        # Round shares to board lot
        shares = VnMarketRules.round_board_lot(1234)  # Returns 1200

        # Round price to tick size
        price = VnMarketRules.round_price_tick(45678)  # Returns 45700

        # Get tick size for a price
        tick = VnMarketRules.get_tick_size(45678)  # Returns 100
    """

    # Board lot (minimum trading unit)
    BOARD_LOT = 100  # Minimum shares per order

    # Tick sizes (price-dependent)
    # Format: (price_range_start, price_range_end): tick_size
    TICK_SIZES = {
        (0, 10_000): 10,           # < 10,000 VND: 10 VND tick
        (10_000, 50_000): 50,      # 10,000 - 50,000 VND: 50 VND tick
        (50_000, 100_000): 100,    # 50,000 - 100,000 VND: 100 VND tick
        (100_000, 500_000): 500,   # 100,000 - 500,000 VND: 500 VND tick
        (500_000, float('inf')): 1000,  # >= 500,000 VND: 1,000 VND tick
    }

    # Settlement cycle
    SETTLEMENT_CYCLE = 'T+2.5'  # Vietnam T+2.5 effective settlement (T+1 shares, T+2 cash)
    SETTLEMENT_DAYS = 2

    # Trading sessions (Vietnam time, UTC+7)
    TRADING_SESSIONS = {
        'ATO': ('09:00', '09:15'),  # Opening auction (ATO)
        'CONTINUOUS_MORNING': ('09:15', '11:30'),  # Continuous morning session
        'LUNCH_BREAK': ('11:30', '13:00'),  # Lunch break
        'CONTINUOUS_AFTERNOON': ('13:00', '14:30'),  # Continuous afternoon session
        'ATC': ('14:30', '14:45'),  # Closing auction (ATC)
    }

    # Price limits (ceiling/floor)
    PRICE_LIMIT_PERCENT = 0.07  # +/-7% daily price limit
    REFERENCE_PRICE_LIMIT_PERCENT = 0.10  # +/-10% for stocks without reference price

    # Exchanges
    EXCHANGES = ['HOSE', 'HNX', 'UPCOM']

    @classmethod
    def round_board_lot(cls, shares: float) -> int:
        """
        Round shares to nearest board lot (100 shares).

        Args:
            shares: Number of shares (can be float)

        Returns:
            Rounded shares (multiple of 100)

        Examples:
            >>> VnMarketRules.round_board_lot(1234)
            1200
            >>> VnMarketRules.round_board_lot(1250)
            1300
            >>> VnMarketRules.round_board_lot(50)
            100
        """
        if shares <= 0:
            return 0

        # Round to nearest board lot
        rounded = round(shares / cls.BOARD_LOT) * cls.BOARD_LOT

        # Ensure at least one board lot
        if rounded == 0 and shares > 0:
            rounded = cls.BOARD_LOT

        return int(rounded)

    @classmethod
    def round_price_tick(cls, price: float) -> float:
        """
        Round price to nearest tick size based on price level.

        Args:
            price: Price in VND

        Returns:
            Rounded price to nearest tick

        Examples:
            >>> VnMarketRules.round_price_tick(9_876)
            9_880
            >>> VnMarketRules.round_price_tick(45_678)
            45_700
            >>> VnMarketRules.round_price_tick(123_456)
            123_500
        """
        if price <= 0:
            return 0.0

        # Find appropriate tick size
        tick_size = cls.get_tick_size(price)

        # Round to nearest tick
        rounded = round(price / tick_size) * tick_size

        return float(rounded)

    @classmethod
    def get_tick_size(cls, price: float) -> float:
        """
        Get tick size for a given price level.

        Args:
            price: Price in VND

        Returns:
            Tick size in VND

        Examples:
            >>> VnMarketRules.get_tick_size(5_000)
            10
            >>> VnMarketRules.get_tick_size(45_000)
            100
            >>> VnMarketRules.get_tick_size(600_000)
            1000
        """
        for (low, high), tick in cls.TICK_SIZES.items():
            if low <= price < high:
                return float(tick)

        # Default to largest tick size
        return 1000.0

    @classmethod
    def calculate_price_limits(cls, reference_price: float) -> Tuple[float, float]:
        """
        Calculate ceiling and floor prices based on reference price.

        Args:
            reference_price: Reference price (previous close or adjusted price)

        Returns:
            Tuple of (floor_price, ceiling_price)

        Examples:
            >>> VnMarketRules.calculate_price_limits(100_000)
            (93000.0, 107000.0)
        """
        if reference_price <= 0:
            raise ValueError("Reference price must be positive")

        # Calculate raw limits
        floor_raw = reference_price * (1 - cls.PRICE_LIMIT_PERCENT)
        ceiling_raw = reference_price * (1 + cls.PRICE_LIMIT_PERCENT)

        # Round to tick sizes
        floor_price = cls.round_price_tick(floor_raw)
        ceiling_price = cls.round_price_tick(ceiling_raw)

        return (floor_price, ceiling_price)

    @classmethod
    def is_valid_order_size(cls, shares: int) -> bool:
        """
        Check if order size is valid (multiple of board lot).

        Args:
            shares: Number of shares

        Returns:
            True if valid, False otherwise

        Examples:
            >>> VnMarketRules.is_valid_order_size(100)
            True
            >>> VnMarketRules.is_valid_order_size(150)
            False
            >>> VnMarketRules.is_valid_order_size(1000)
            True
        """
        if shares <= 0:
            return False

        return shares % cls.BOARD_LOT == 0

    @classmethod
    def is_valid_price(cls, price: float, reference_price: float = None) -> bool:
        """
        Check if price is valid (matches tick size and within limits).

        Args:
            price: Price to validate
            reference_price: Reference price for limit check (optional)

        Returns:
            True if valid, False otherwise
        """
        if price <= 0:
            return False

        # Check tick size
        tick_size = cls.get_tick_size(price)
        if abs(price - cls.round_price_tick(price)) > 1e-6:
            return False

        # Check price limits if reference price provided
        if reference_price is not None:
            floor, ceiling = cls.calculate_price_limits(reference_price)
            if price < floor or price > ceiling:
                return False

        return True

    @classmethod
    def get_exchange_info(cls, exchange: str) -> Dict:
        """
        Get information about a specific exchange.

        Args:
            exchange: Exchange code ('HOSE', 'HNX', 'UPCOM')

        Returns:
            Dictionary with exchange information
        """
        exchange_info = {
            'HOSE': {
                'name': 'Ho Chi Minh Stock Exchange',
                'description': 'Main board for large-cap stocks',
                'typical_liquidity': 'high',
                'listing_requirements': 'strict'
            },
            'HNX': {
                'name': 'Hanoi Stock Exchange',
                'description': 'Second board for mid-cap stocks',
                'typical_liquidity': 'medium',
                'listing_requirements': 'moderate'
            },
            'UPCOM': {
                'name': 'Unlisted Public Company Market',
                'description': 'OTC market for smaller companies',
                'typical_liquidity': 'low',
                'listing_requirements': 'relaxed'
            }
        }

        if exchange not in exchange_info:
            raise ValueError(f"Unknown exchange: {exchange}. Valid exchanges: {cls.EXCHANGES}")

        return exchange_info[exchange]

    @classmethod
    def get_market_rules_summary(cls) -> str:
        """
        Get a human-readable summary of VN market rules.

        Returns:
            Formatted string with market rules
        """
        summary = "=== Vietnam Market Rules ===\n"
        summary += f"Board Lot: {cls.BOARD_LOT} shares\n"
        summary += f"Settlement Cycle: {cls.SETTLEMENT_CYCLE} ({cls.SETTLEMENT_DAYS} days)\n"
        summary += f"Price Limit: +/-{cls.PRICE_LIMIT_PERCENT * 100:.0f}%\n"
        summary += "\nTick Sizes:\n"
        for (low, high), tick in sorted(cls.TICK_SIZES.items()):
            if high == float('inf'):
                summary += f"  >= {low:,} VND: {tick:,} VND\n"
            else:
                summary += f"  {low:,} - {high:,} VND: {tick:,} VND\n"
        summary += f"\nExchanges: {', '.join(cls.EXCHANGES)}\n"

        return summary
