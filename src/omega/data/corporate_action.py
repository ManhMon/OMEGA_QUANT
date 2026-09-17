"""
V21 Core Intelligence - Corporate Action Adjustment Module
Version: v21.0

Backward Price Adjustment for Vietnam Stock Market
Supports: Dividends, Stock Splits, Rights Issues
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
import copy
import logging
from typing import Any, Dict, List, Optional

import pandas as pd


logger = logging.getLogger(__name__)


def _default_helper_provenance(ex_date: str, provenance: Dict[str, Any]) -> Dict[str, Any]:
    ex_timestamp = pd.Timestamp(ex_date, tz="UTC")
    announced_at = provenance.get("announced_at")
    if announced_at is None:
        announced_at = (ex_timestamp - pd.Timedelta(days=7)).to_pydatetime()
    ingested_at = provenance.get("ingested_at", announced_at)
    available_at = provenance.get("available_at", announced_at)
    source = provenance.get("source", "HELPER_DEFAULT")
    return {
        **provenance,
        "announced_at": announced_at,
        "ingested_at": ingested_at,
        "available_at": available_at,
        "source": source,
    }


def _coerce_utc_timestamp(value: Optional[datetime | str], field_name: str) -> Optional[datetime]:
    if value is None:
        return None
    timestamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return timestamp.astimezone(UTC)


@dataclass(init=False)
class CorporateAction:
    """Represents a single corporate action event with PIT provenance."""

    symbol: str
    ex_date: str
    action_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    announced_at: Optional[datetime] = None
    ingested_at: Optional[datetime] = None
    available_at: Optional[datetime] = None
    source: Optional[str] = None
    quarantine_reason: Optional[str] = None

    def __init__(
        self,
        symbol: str,
        ex_date: str,
        action_type: str,
        announced_at: Optional[datetime | str] = None,
        ingested_at: Optional[datetime | str] = None,
        available_at: Optional[datetime | str] = None,
        source: Optional[str] = None,
        **params: Any,
    ):
        self.symbol = symbol
        self.ex_date = ex_date
        self.action_type = action_type
        self.params = params
        self.announced_at = _coerce_utc_timestamp(announced_at, "announced_at")
        self.ingested_at = _coerce_utc_timestamp(ingested_at, "ingested_at")
        self.available_at = _coerce_utc_timestamp(available_at, "available_at")
        self.source = source
        self.quarantine_reason = None
        self._validate_provenance()

    def _validate_provenance(self) -> None:
        if not self.announced_at or not self.ingested_at or not self.available_at or not self.source:
            self.quarantine_reason = (
                "missing availability provenance: announced_at, ingested_at, available_at, source required"
            )
            logger.warning(
                "Quarantining corporate action %s %s %s: %s",
                self.symbol,
                self.ex_date,
                self.action_type,
                self.quarantine_reason,
            )
            return

        expected_available_at = max(self.announced_at, self.ingested_at)
        if self.available_at != expected_available_at:
            raise ValueError("available_at must equal max(announced_at, ingested_at)")
        if self.available_at < self.announced_at:
            raise ValueError("available_at must be >= announced_at")

    @property
    def is_quarantined(self) -> bool:
        return self.quarantine_reason is not None

    def is_available_at(self, as_of_time: datetime) -> bool:
        if self.is_quarantined or self.available_at is None:
            return False
        if as_of_time.tzinfo is None or as_of_time.utcoffset() is None:
            raise ValueError("as_of_time must be timezone-aware UTC")
        return self.available_at <= as_of_time.astimezone(UTC)

    def __repr__(self):
        return (
            f"CorporateAction({self.symbol}, {self.ex_date}, {self.action_type}, {self.params}, "
            f"announced_at={self.announced_at}, ingested_at={self.ingested_at}, "
            f"available_at={self.available_at}, source={self.source!r})"
        )


class CorporateActionAdjuster:
    """
    Applies backward adjustment to price data for corporate actions.
    Preserves recent prices and adjusts historical prices.
    """
    
    def __init__(self):
        self.actions: List[CorporateAction] = []
    
    def add_action(self, action: CorporateAction):
        """Add a corporate action to the adjustment queue."""
        self.actions.append(action)
    
    def add_actions(self, actions: List[CorporateAction]):
        """Add multiple corporate actions."""
        self.actions.extend(actions)
    
    def clear_actions(self):
        """Clear all corporate actions."""
        self.actions = []
    
    def calculate_adjustment_factor(self, action: CorporateAction, close_price: float) -> float:
        """
        Calculate adjustment factor for a single corporate action.
        
        Args:
            action: Corporate action event
            close_price: Close price on day before ex-date
        
        Returns:
            Adjustment factor to multiply historical prices
        """
        if action.action_type == 'dividend':
            return self._dividend_adjustment_factor(action, close_price)
        elif action.action_type == 'split':
            return self._split_adjustment_factor(action)
        elif action.action_type == 'rights':
            return self._rights_adjustment_factor(action, close_price)
        else:
            raise ValueError(f"Unknown action type: {action.action_type}")
    
    def _dividend_adjustment_factor(self, action: CorporateAction, close_price: float) -> float:
        """
        Dividend adjustment factor.
        
        Formula: factor = (Close - Dividend) / Close
        
        Args:
            action: Dividend action with 'dividend_amount' in VND
            close_price: Close price before ex-date
        
        Returns:
            Adjustment factor (< 1.0)
        """
        dividend_amount = action.params.get('dividend_amount', 0.0)
        if close_price <= 0:
            raise ValueError(f"Invalid close price: {close_price}")
        
        factor = (close_price - dividend_amount) / close_price
        
        # Sanity check: factor should be positive and < 1
        if factor <= 0 or factor >= 1:
            raise ValueError(
                f"Invalid dividend adjustment factor: {factor}. "
                f"Close: {close_price}, Dividend: {dividend_amount}"
            )
        
        return factor
    
    def _split_adjustment_factor(self, action: CorporateAction) -> float:
        """
        Stock split adjustment factor.
        
        Formula: factor = 1 / split_ratio
        
        Args:
            action: Split action with 'split_ratio' (e.g., 2.0 for 2:1 split)
        
        Returns:
            Adjustment factor (< 1.0 for normal splits)
        """
        split_ratio = action.params.get('split_ratio', 1.0)
        if split_ratio <= 0:
            raise ValueError(f"Invalid split ratio: {split_ratio}")
        
        factor = 1.0 / split_ratio
        return factor
    
    def _rights_adjustment_factor(self, action: CorporateAction, close_price: float) -> float:
        """
        Rights issue adjustment factor.
        
        Formula: factor = (Close + Rights_Ratio * Rights_Price) / (Close + Rights_Ratio * Close)
        
        Args:
            action: Rights action with 'rights_ratio' and 'rights_price'
            close_price: Close price before ex-date
        
        Returns:
            Adjustment factor
        """
        rights_ratio = action.params.get('rights_ratio', 0.0)
        rights_price = action.params.get('rights_price', 0.0)
        
        if close_price <= 0:
            raise ValueError(f"Invalid close price: {close_price}")
        
        numerator = close_price + rights_ratio * rights_price
        denominator = close_price + rights_ratio * close_price
        
        if denominator <= 0:
            raise ValueError(f"Invalid rights adjustment denominator: {denominator}")
        
        factor = numerator / denominator
        return factor
    
    def apply_adjustments(self, data: Dict, price_fields: Optional[List[str]] = None) -> Dict:
        """
        Apply backward adjustment to CleanDataFrame.
        
        Args:
            data: CleanDataFrame dict with structure:
                {
                    "index": {"symbol": [...], "timestamp": [...]},
                    "type": "CleanDataFrame",
                    "data": {symbol: {timestamp: {fields...}}}
                }
            price_fields: List of price fields to adjust (default: ["open", "high", "low", "close"])
        
        Returns:
            Adjusted CleanDataFrame (new copy)
        """
        if not self.actions:
            return data
        
        if price_fields is None:
            price_fields = ["open", "high", "low", "close"]
        
        # Deep copy to avoid mutating original
        adjusted_data = copy.deepcopy(data)
        
        # Group actions by symbol
        actions_by_symbol = {}
        for action in self.actions:
            if action.symbol not in actions_by_symbol:
                actions_by_symbol[action.symbol] = []
            actions_by_symbol[action.symbol].append(action)
        
        # Sort actions by ex_date (descending) for backward adjustment
        for symbol in actions_by_symbol:
            actions_by_symbol[symbol].sort(key=lambda a: a.ex_date, reverse=True)
        
        # Apply adjustments symbol by symbol
        for symbol, symbol_actions in actions_by_symbol.items():
            if symbol not in adjusted_data["data"]:
                continue
            
            symbol_data = adjusted_data["data"][symbol]
            timestamps = sorted([ts for ts in symbol_data.keys() if symbol_data[ts] is not None])
            
            if not timestamps:
                continue
            
            # Process each action (from most recent to oldest)
            for action in symbol_actions:
                # Find ex-date index
                ex_date_idx = None
                for i, ts in enumerate(timestamps):
                    if ts >= action.ex_date:
                        ex_date_idx = i
                        break
                
                if ex_date_idx is None or ex_date_idx == 0:
                    # Action is before data range or at first timestamp
                    continue
                
                # Get close price on day before ex-date
                prev_ts = timestamps[ex_date_idx - 1]
                prev_data = symbol_data[prev_ts]
                
                if prev_data is None or "close" not in prev_data:
                    continue
                
                close_price = prev_data["close"]
                
                # Calculate adjustment factor
                try:
                    factor = self.calculate_adjustment_factor(action, close_price)
                except ValueError as e:
                    # Skip invalid adjustments
                    print(f"Warning: Skipping adjustment for {symbol} on {action.ex_date}: {e}")
                    continue
                
                # Apply factor to all timestamps before ex-date
                for i in range(ex_date_idx):
                    ts = timestamps[i]
                    ts_data = symbol_data[ts]
                    
                    if ts_data is None:
                        continue
                    
                    for field in price_fields:
                        if field in ts_data and ts_data[field] is not None:
                            ts_data[field] = ts_data[field] * factor
                    
                    # Adjust volume for splits (inverse ratio)
                    if action.action_type == 'split' and 'volume' in ts_data and ts_data['volume'] is not None:
                        split_ratio = action.params.get('split_ratio', 1.0)
                        ts_data['volume'] = ts_data['volume'] * split_ratio
        
        return adjusted_data


def create_dividend_action(symbol: str, ex_date: str, dividend_amount: float, **provenance: Any) -> CorporateAction:
    """Helper to create dividend action."""
    return CorporateAction(
        symbol,
        ex_date,
        'dividend',
        dividend_amount=dividend_amount,
        **_default_helper_provenance(ex_date, provenance),
    )


def create_split_action(symbol: str, ex_date: str, split_ratio: float, **provenance: Any) -> CorporateAction:
    """Helper to create split action."""
    return CorporateAction(
        symbol,
        ex_date,
        'split',
        split_ratio=split_ratio,
        **_default_helper_provenance(ex_date, provenance),
    )


def create_rights_action(
    symbol: str,
    ex_date: str,
    rights_ratio: float,
    rights_price: float,
    **provenance: Any,
) -> CorporateAction:
    """Helper to create rights issue action."""
    return CorporateAction(
        symbol,
        ex_date,
        'rights',
        rights_ratio=rights_ratio,
        rights_price=rights_price,
        **_default_helper_provenance(ex_date, provenance),
    )
