"""
VN Transaction Cost Model - V21 Institutional
VN-specific transaction cost estimation including limit-lock, foreign room, and settlement costs.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import math


@dataclass
class TransactionCostConfig:
    """Configuration for VN transaction cost model."""
    # Slippage by exchange and liquidity
    hose_liquid_bps: float = 15.0      # VCB, HPG, FPT
    hose_illiquid_bps: float = 50.0    # Other HOSE stocks
    hnx_bps: float = 80.0              # HNX stocks
    upcom_bps: float = 150.0           # UPCOM stocks
    
    # Limit-lock impact
    limit_lock_bps: float = 200.0      # Cost when limit-locked
    
    # Foreign room cost
    foreign_room_cost_bps: float = 30.0  # When room is exhausted
    
    # T+2.5 settlement opportunity cost
    settlement_cost_bps: float = 5.0   # Daily opportunity cost
    
    # ADV participation limits
    max_participation_pct: float = 0.10  # 10% of ADV
    liquidity_cost_multiplier: float = 2.0  # Cost multiplier for high participation

    # BUG-P2-004 FIX: Liquidity thresholds moved from hardcoded constants to config.
    liquid_adv_threshold_vnd: float = 50e9   # ADV >= 50B VND → liquid
    illiquid_adv_threshold_vnd: float = 10e9  # ADV < 10B VND → illiquid

    # BUG-P2-005 FIX: VN-specific taxes and fees as first-class cost components.
    # Sell tax: 0.1% of sell value (STT - thuế chuyển nhượng chứng khoán)
    sell_tax_bps: float = 10.0         # 0.1% applied to SELL trades only
    # Brokerage fee: 0.15% both sides
    brokerage_fee_bps: float = 15.0    # Both buy and sell


class VNTransactionCostModel:
    """
    VN-specific transaction cost estimation.
    
    VN Market Specifics:
    - Price bands: HOSE 7%, HNX 10%, UPCOM 15%
    - T+2.5 settlement gap
    - Foreign ownership limits
    - Board-lot: 100 shares minimum
    """
    
    def __init__(self, config: TransactionCostConfig = None):
        self.config = config or TransactionCostConfig()

    def _as_price_vnd(self, price: Optional[float]) -> Optional[float]:
        if price is None:
            return None
        return float(price)
        
    def get_exchange(self, symbol: str, exchange_label: Optional[str] = None) -> str:
        """Determine exchange for a symbol.
        
        BUG-P1-003 FIX: Accept an explicit PIT exchange_label from the data warehouse.
        If not provided, attempt to classify from the symbol name conventions.
        Unknown symbols are returned as 'UNKNOWN' (fail closed) instead of defaulting to UPCOM.
        """
        # Accept explicit PIT label first
        if exchange_label is not None:
            normalized = exchange_label.upper()
            if normalized in ('HOSE', 'HNX', 'UPCOM'):
                return normalized
        
        # VN30 stocks are on HOSE (deduplicated list)
        vn30 = ['VCB', 'HPG', 'FPT', 'VIC', 'MSN', 'MWG', 'VNM', 'SAB', 'VHM', 'GAS', 
                'BID', 'VPB', 'ACB', 'TCB', 'MBB', 'HDB', 'STB', 'VIB', 'CTG', 'TPB',
                'NVB', 'BFC', 'SHB', 'BVB', 'VRE', 'TPH']
        
        if symbol in vn30:
            return 'HOSE'
        # BUG-P1-003 FIX: Return UNKNOWN instead of defaulting to UPCOM for unrecognized symbols.
        return 'UNKNOWN'
    
    def get_liquidity_category(self, symbol: str, adv: float) -> str:
        """Determine liquidity category for a symbol.
        
        BUG-P2-004 FIX: Thresholds now read from config instead of hardcoded.
        """
        if adv > self.config.liquid_adv_threshold_vnd:
            return 'liquid'
        elif adv < self.config.illiquid_adv_threshold_vnd:
            return 'illiquid'
        else:
            return 'medium'
    
    def estimate_limit_lock_prob(self, symbol: str, price: float, 
                                  high: Optional[float] = None, low: Optional[float] = None,
                                  exchange_label: Optional[str] = None) -> float:
        """
        Estimate probability of limit-lock based on price movement.
        
        HOSE: 7% limit
        HNX: 10% limit
        UPCOM: 15% limit
        UNKNOWN: treat conservatively as UPCOM (14.8%)
        
        BUG-P1-009 FIX: Returns 0.0 if high/low are not provided (pre-trade, unknowable).
        The hard execution blocker is implemented in is_price_band_blocked().
        """
        if high is None or low is None:
            return 0.0
        
        exchange = self.get_exchange(symbol, exchange_label)
        
        if exchange == 'HOSE':
            limit_pct = 0.07  # Updated to official 7.0%
        elif exchange == 'HNX':
            limit_pct = 0.10  # Updated to official 10.0%
        else:  # UPCOM or UNKNOWN
            limit_pct = 0.15  # Updated to official 15.0%
        
        price = self._as_price_vnd(price)
        high = self._as_price_vnd(high)
        low = self._as_price_vnd(low)

        price_range = high - low
        if price_range == 0:
            return 0.0
        
        movement_ratio = price_range / (price * limit_pct)
        
        k = 5.0
        threshold = 1.0
        prob = 1.0 / (1.0 + math.exp(-k * (movement_ratio - threshold)))
        
        return min(prob, 1.0)

    def is_price_band_blocked(self, symbol: str, ref_price: float, order_price: float,
                               exchange_label: Optional[str] = None,
                               is_suspended: bool = False) -> bool:
        """
        BUG-P1-009 FIX: Hard execution blocker for VN price bands and suspensions.
        
        Returns True if the order MUST be blocked (impossible execution).
        - Suspended symbols: always blocked.
        - Price outside exchange band: blocked.
        
        Args:
            symbol: Stock ticker.
            ref_price: Reference price for band calculation (prior close or ceiling/floor).
            order_price: Proposed execution price.
            exchange_label: PIT exchange label from data warehouse.
            is_suspended: True if symbol is halted/suspended.
        """
        if is_suspended:
            return True  # Hard block: cannot trade suspended symbols
        
        exchange = self.get_exchange(symbol, exchange_label)
        if exchange == 'HOSE':
            band = 0.07
        elif exchange == 'HNX':
            band = 0.10
        elif exchange == 'UPCOM':
            band = 0.15
        else:
            # UNKNOWN exchange: fail closed, block the trade
            return True
        
        ref = self._as_price_vnd(ref_price)
        order = self._as_price_vnd(order_price)
        if ref <= 0:
            return True  # Cannot determine band without valid reference price
        
        ceiling = ref * (1 + band)
        floor = ref * (1 - band)
        return not (floor <= order <= ceiling)
    
    def estimate_foreign_room_cost(self, symbol: str, order_size: float, 
                                    adv: float) -> float:
        """
        Estimate cost from foreign room exhaustion.
        
        BUG-P2-006 NOTE: This returns 0.0 because no PIT foreign-room ownership data
        contract is available. Production must supply foreign_room_pct per symbol per date.
        Until PIT data is wired in, this is explicitly documented as a known gap (NOT silently 0).
        """
        # KNOWN GAP (BUG-P2-006): No PIT foreign-room data available.
        # Do not claim this models foreign room. It is explicitly excluded.
        return 0.0
    
    def estimate_cost(self, symbol: str, order_size: float, price: float,
                      adv_value_vnd: float, high: Optional[float] = None,
                      low: Optional[float] = None, side: str = 'buy',
                      exchange_label: Optional[str] = None) -> Dict[str, float]:
        """
        Estimate total transaction cost for an order.
        
        Args:
            symbol: Stock symbol
            order_size: Order quantity (shares)
            price: Current price (VND)
            adv_value_vnd: Average daily value in VND notional (NOT share volume).
                           BUG-P2-003 FIX: Parameter renamed from 'adv' to 'adv_value_vnd'
                           to enforce the correct unit. Participation cost = (order_size * price) / adv_value_vnd.
            high: High price for limit-lock estimation - Optional (None = pre-trade unknown)
            low: Low price for limit-lock estimation - Optional (None = pre-trade unknown)
            side: 'buy' or 'sell' - used for side-aware VN taxes (BUG-P2-005 FIX)
            exchange_label: PIT exchange label from data warehouse (BUG-P1-003 FIX)
        
        Returns:
            Dict with cost breakdown in basis points
        """
        price_vnd = self._as_price_vnd(price)
        high_vnd = self._as_price_vnd(high) if high is not None else None
        low_vnd = self._as_price_vnd(low) if low is not None else None

        exchange = self.get_exchange(symbol, exchange_label)
        liquidity = self.get_liquidity_category(symbol, adv_value_vnd)
        
        # Base slippage - UNKNOWN exchange gets UPCOM (most conservative) rate
        if exchange == 'HOSE':
            if liquidity == 'liquid':
                slippage_bps = self.config.hose_liquid_bps
            else:
                slippage_bps = self.config.hose_illiquid_bps
        elif exchange == 'HNX':
            slippage_bps = self.config.hnx_bps
        else:  # UPCOM or UNKNOWN
            slippage_bps = self.config.upcom_bps
        
        # Limit-lock cost (only if high/low provided = post-trade analysis)
        limit_lock_prob = self.estimate_limit_lock_prob(symbol, price_vnd, high_vnd, low_vnd, exchange_label)
        limit_lock_cost_bps = limit_lock_prob * self.config.limit_lock_bps
        
        # BUG-P2-003 FIX: Participation cost uses VND notional ADV (adv_value_vnd).
        participation_rate = (order_size * price_vnd) / adv_value_vnd if adv_value_vnd > 0 else 0.0
        max_participation = max(self.config.max_participation_pct, 1e-12)
        participation_cost_bps = (participation_rate / max_participation) * slippage_bps
        participation_cost_bps = min(participation_cost_bps, self.config.liquidity_cost_multiplier * slippage_bps)
        
        # Foreign room cost (documented gap)
        foreign_room_cost_bps = self.estimate_foreign_room_cost(symbol, order_size, adv_value_vnd)
        
        # T+2.5 settlement opportunity cost (daily)
        settlement_cost_bps = self.config.settlement_cost_bps
        
        # BUG-P2-005 FIX: VN sell tax (STT) is side-aware: only on SELL trades.
        sell_tax_bps = self.config.sell_tax_bps if side.lower() == 'sell' else 0.0
        # Brokerage fee applies both sides
        brokerage_fee_bps = self.config.brokerage_fee_bps
        
        # Total cost
        total_cost_bps = (slippage_bps + limit_lock_cost_bps + 
                         foreign_room_cost_bps + participation_cost_bps + 
                         settlement_cost_bps + sell_tax_bps + brokerage_fee_bps)
        
        return {
            'total_cost_bps': total_cost_bps,
            'slippage_bps': slippage_bps,
            'limit_lock_cost_bps': limit_lock_cost_bps,
            'foreign_room_cost_bps': foreign_room_cost_bps,
            'participation_cost_bps': participation_cost_bps,
            'settlement_cost_bps': settlement_cost_bps,
            'sell_tax_bps': sell_tax_bps,
            'brokerage_fee_bps': brokerage_fee_bps,
            'limit_lock_prob': limit_lock_prob,
            'participation_rate': participation_rate,
            'exchange': exchange
        }
    
    def estimate_order_cost(self, symbol: str, order_size: float, price: float,
                           adv_value_vnd: float, high: float = None, low: float = None,
                           side: str = 'buy', exchange_label: Optional[str] = None) -> float:
        """
        Estimate total cost in VND for an order.
        """
        price_vnd = self._as_price_vnd(price)
        costs = self.estimate_cost(symbol, order_size, price, adv_value_vnd, high, low, side, exchange_label)
        total_cost_vnd = (costs['total_cost_bps'] / 10000) * order_size * price_vnd
        return total_cost_vnd
    
    def round_to_tick(self, price: float) -> float:
        """
        Round price to VN tick size (Unit: 1000 VND).
        
        Rules (Unit: 1000 VND):
        - Price < 10.0: Tick 0.1
        - 10.0 <= Price <= 50.0: Tick 0.5
        - Price > 50.0: Tick 1.0
        """
        if price <= 0:
            return price
            
        if price < 10.0:
            tick = 0.1
        elif price <= 50.0:
            tick = 0.5
        else:
            tick = 1.0
            
        return round(price / tick) * tick

    def get_exchange_limits(self) -> Dict[str, float]:
        """Get limit-lock thresholds by exchange."""
        return {
            'HOSE': 0.07,   # Official 7.0%
            'HNX': 0.10,    # Official 10.0%
            'UPCOM': 0.15   # Official 15.0%
        }
