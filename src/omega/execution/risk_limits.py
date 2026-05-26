import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class RiskLimitsConfig:
    """
    Risk Limits Configuration for V21_QUANT
    
    Phase 3.2.1: Individual Scale (2B-5B) Configuration
    - max_notional_value_per_trade: 500M (25% of 2B capital for high-alpha concentration)
    - max_adv_percentage: 0.40 (Micro-Scale for Individual Investors)
    - max_concentration: 0.25 (High-Alpha Concentration for 10-15 stocks)
    - alert_drawdown_threshold: 0.10 (10% drawdown alert)
    """
    max_notional_value_per_trade: float = 500_000_000  # Phase 3.2.1: 25% of 2B capital
    max_adv_percentage: float = 0.40  # Phase 3.2.1: Micro-Scale (40% ADV for Individual)
    max_total_notional_value: float = 2_000_000_000  # Max total daily volume (should scale with capital)
    max_volatility_percentile: float = 0.90  # Strictly skip top 10% volatile stocks to prevent "đu đỉnh"


class RiskGuard:
    """
    Real-time Risk Limits Guard.
    Checks and clamps order sizes based on configured risk limits before execution.
    """
    RAW_PRICE_THRESHOLD = 1_000.0
    VND_PRICE_SCALE = 1_000.0
    
    def __init__(self, config: RiskLimitsConfig = None):
        self.config = config or RiskLimitsConfig()
        self.daily_notional_sum = 0.0

    def _as_price_vnd(self, current_price: float) -> float:
        price = float(current_price)
        if 0 < price < self.RAW_PRICE_THRESHOLD:
            return price * self.VND_PRICE_SCALE
        return price

    def _apply_board_lot_rounding(self, quantity: int) -> int:
        return (abs(int(quantity)) // 100) * 100

    def _adv_to_shares(self, adv: float, current_price_vnd: float, adv_unit: str) -> float:
        """
        Convert ADV to shares based on unit type.
        
        P0-03 FIX: current_price_vnd is already scaled by _as_price_vnd (price * 1000),
        so ADV in VND can be directly divided by current_price_vnd to get shares.
        """
        adv_value = float(adv or 0.0)
        if adv_value <= 0 or current_price_vnd <= 0:
            return 0.0

        normalized_unit = adv_unit.lower()
        if normalized_unit in {"shares", "share", "volume", "qty", "quantity"}:
            return adv_value
        if normalized_unit in {"vnd", "value", "notional", "notional_vnd", "adv_value_vnd"}:
            # P0-03: current_price_vnd already includes 1000x scale, so direct division is correct
            return adv_value / current_price_vnd

        raise ValueError(f"Unsupported ADV unit: {adv_unit}")

    def reset_daily_limits(self):
        """Resets the cumulative daily counters."""
        self.daily_notional_sum = 0.0

    def check_and_clamp(
        self,
        order: Dict[str, Any],
        current_price: float,
        adv: float,
        volatility: float = None,
        vol_threshold: float = None,
        adv_unit: str = "vnd", # P0 FIX: Default to 'vnd' to match SystemOrchestrator contract
    ) -> Dict[str, Any]:
        """
        Validates an order against risk limits and returns the clamped order if it exceeds limits.
        If an order is completely rejected, returns an empty dictionary.

        adv_unit="shares" means ADV is average traded shares.
        adv_unit="vnd" means ADV is average traded notional value and is converted to shares.
        """
        qty = order.get("quantity", 0)
        symbol = order.get("symbol", "")
        current_price_vnd = self._as_price_vnd(current_price)
        
        if qty == 0 or current_price_vnd == 0:
            return {}

        # Check 0: Adaptive Volatility Filter (Only for NEW BUYS)
        if qty > 0 and volatility is not None and vol_threshold is not None:
            if volatility > vol_threshold:
                logging.warning(f"Risk Guard: {symbol} rejected due to high volatility ({volatility:.4f} > {vol_threshold:.4f})")
                return {}

        abs_qty = abs(qty)
        notional_value = abs_qty * current_price_vnd

        # Check 1: Max Notional Value Per Trade
        if notional_value > self.config.max_notional_value_per_trade:
            logging.warning(f"Risk Guard: {symbol} order size {abs_qty} exceeds max notional value. Clamping.")
            max_qty_notional = int(self.config.max_notional_value_per_trade / current_price_vnd)
            abs_qty = min(abs_qty, max_qty_notional)
            
        # Check 2: Max ADV Percentage
        adv_shares = self._adv_to_shares(adv, current_price_vnd, adv_unit)
        max_qty_adv = int(adv_shares * self.config.max_adv_percentage)
        if abs_qty > max_qty_adv:
            logging.warning(f"Risk Guard: {symbol} order size {abs_qty} exceeds max ADV %. Clamping to {max_qty_adv}.")
            abs_qty = min(abs_qty, max_qty_adv)

        # Check 3: Max Total Daily Notional Value
        notional_after_clamp = abs_qty * current_price_vnd
        if self.daily_notional_sum + notional_after_clamp > self.config.max_total_notional_value:
            logging.warning(f"Risk Guard: Total daily limit reached. Clamping {symbol}.")
            remaining_limit = max(0.0, self.config.max_total_notional_value - self.daily_notional_sum)
            abs_qty = int(remaining_limit / current_price_vnd)
            notional_after_clamp = abs_qty * current_price_vnd

        # Round down to nearest board lot (100)
        abs_qty = self._apply_board_lot_rounding(abs_qty)

        if abs_qty == 0:
            logging.warning(f"Risk Guard: {symbol} order clamped to 0. Rejecting order.")
            return {}

        # Update daily counter only for the executable, board-lot-rounded order.
        self.daily_notional_sum += abs_qty * current_price_vnd

        # Restore original sign
        final_qty = abs_qty if qty > 0 else -abs_qty
        
        clamped_order = order.copy()
        clamped_order["quantity"] = final_qty
        return clamped_order
