"""
V21 Core Intelligence - Corporate Action Adjustment Module
Version: v21.0

Backward Price Adjustment for Vietnam Stock Market
Supports: Dividends, Stock Splits, Rights Issues
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime
import copy


class CorporateAction:
    """
    Represents a single corporate action event.
    """
    
    def __init__(self, symbol: str, ex_date: str, action_type: str, **params):
        """
        Args:
            symbol: Stock symbol
            ex_date: Ex-date (YYYY-MM-DD or timestamp)
            action_type: 'dividend', 'split', 'rights'
            **params: Action-specific parameters
                - dividend: dividend_amount (VND per share)
                - split: split_ratio (e.g., 2.0 for 2:1 split)
                - rights: rights_ratio, rights_price
        """
        self.symbol = symbol
        self.ex_date = ex_date
        self.action_type = action_type
        self.params = params
    
    def __repr__(self):
        return f"CorporateAction({self.symbol}, {self.ex_date}, {self.action_type}, {self.params})"


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


def create_dividend_action(symbol: str, ex_date: str, dividend_amount: float) -> CorporateAction:
    """Helper to create dividend action."""
    return CorporateAction(symbol, ex_date, 'dividend', dividend_amount=dividend_amount)


def create_split_action(symbol: str, ex_date: str, split_ratio: float) -> CorporateAction:
    """Helper to create split action."""
    return CorporateAction(symbol, ex_date, 'split', split_ratio=split_ratio)


def create_rights_action(symbol: str, ex_date: str, rights_ratio: float, rights_price: float) -> CorporateAction:
    """Helper to create rights issue action."""
    return CorporateAction(symbol, ex_date, 'rights', rights_ratio=rights_ratio, rights_price=rights_price)
