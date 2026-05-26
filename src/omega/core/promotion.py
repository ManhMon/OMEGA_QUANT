import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from datetime import timedelta

class PromotionGate:
    """
    Phase 2.3 Promotion Gate
    Enforces strict institutional safety rules for model promotion:
    - Unified embargo period (T+horizon models)
    - Non-overlapping validation windows
    - Out-of-sample minimum performance thresholds
    - Fail-closed approach
    """
    def __init__(self):
        pass

    def calculate_required_embargo(self, max_horizon: int) -> int:
        """
        Calculate required embargo period based on max_horizon.
        Rule: embargo = max_horizon + 1 days.
        """
        return max_horizon + 1

    def verify_embargo(self, train_end_date: pd.Timestamp, val_start_date: pd.Timestamp, max_horizon: int) -> bool:
        """
        Verify embargo period.
        """
        if pd.isna(train_end_date) or pd.isna(val_start_date):
            return False
            
        required_days = self.calculate_required_embargo(max_horizon)
        actual_days = (val_start_date - train_end_date).days
        return actual_days >= required_days

    def verify_non_overlapping_windows(self, validation_windows: List[Tuple[Any, Any]]) -> bool:
        """
        Verify that a list of validation windows (start, end) do not overlap.
        windows should be list of (start_date, end_date)
        """
        if not validation_windows:
            return False # Fail closed if no windows
            
        try:
            # Parse and check for NaT/None
            parsed_windows = []
            for start, end in validation_windows:
                start_ts = pd.to_datetime(start)
                end_ts = pd.to_datetime(end)
                if pd.isna(start_ts) or pd.isna(end_ts) or start_ts >= end_ts:
                    return False
                parsed_windows.append((start_ts, end_ts))
    
            # Sort by start date
            sorted_windows = sorted(parsed_windows, key=lambda x: x[0])
            
            for i in range(len(sorted_windows) - 1):
                current_end = sorted_windows[i][1]
                next_start = sorted_windows[i+1][0]
                if current_end > next_start:
                    return False
                    
            return True
        except Exception:
            return False

    def verify_performance(self, metrics: Dict[str, float]) -> bool:
        """
        Verify minimum out-of-sample performance thresholds.
        IC > 0.1, Sharpe > 1.5.
        """
        if not metrics:
            return False
            
        ic = metrics.get('ic', 0.0)
        sharpe = metrics.get('sharpe', 0.0)
        
        if pd.isna(ic) or pd.isna(sharpe):
            return False
            
        return ic > 0.1 and sharpe > 1.5

    def evaluate_promotion(self, metadata: Dict[str, Any]) -> bool:
        """
        Evaluate if a model version is eligible for promotion.
        Metadata is expected to have:
        - max_horizon: int (e.g., 3 for T+3)
        - train_end_date: str or Timestamp
        - val_start_date: str or Timestamp
        - metrics: Dict with 'ic' and 'sharpe'
        - validation_windows: Optional[List[tuple]] (start, end) strings or Timestamps
        
        Fails closed on any missing data or parsing error.
        """
        try:
            # Check required keys
            required_keys = ['max_horizon', 'train_end_date', 'val_start_date', 'metrics']
            if not all(k in metadata for k in required_keys):
                return False
                
            # Parse dates
            train_end = pd.to_datetime(metadata['train_end_date'])
            val_start = pd.to_datetime(metadata['val_start_date'])
            max_horizon = int(metadata['max_horizon'])
            
            # Verify embargo
            if not self.verify_embargo(train_end, val_start, max_horizon):
                return False
                
            # Verify performance
            if not self.verify_performance(metadata['metrics']):
                return False
                
            # Verify non-overlapping windows if provided
            windows_data = metadata.get('validation_windows')
            if windows_data is not None:
                if not self.verify_non_overlapping_windows(windows_data):
                    return False
                    
            return True
            
        except Exception:
            # Fail closed on any exception
            return False
