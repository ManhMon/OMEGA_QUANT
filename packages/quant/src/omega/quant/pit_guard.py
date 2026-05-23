import pandas as pd
import numpy as np
from typing import Optional, List, Dict, Any


def validate_temporal_shift(df: pd.DataFrame, as_of_col: str, available_at_col: str) -> bool:
    """Enforce as_of <= available_at."""
    if df.empty:
        return True
    if as_of_col not in df.columns or available_at_col not in df.columns:
        raise KeyError("Missing required columns")
        
    violations = df[df[as_of_col] > df[available_at_col]]
    if not violations.empty:
        raise ValueError(f"Temporal leak: {len(violations)} rows have as_of > available_at")
    return True

def detect_lookahead_leakage(features: pd.DataFrame, labels: pd.DataFrame, lag_days: int) -> bool:
    """
    Detect T+0 lookahead leakage by verifying temporal alignment.

    Returns True if leakage detected.
    Leakage condition: any row where features.index - labels.index == 0 (explicit T+0).
    """
    if features.empty or labels.empty:
        return False

    # Pairwise check across aligned positions; covers equal and duplicate indices.
    n = min(len(features.index), len(labels.index))
    f_idx = features.index[:n]
    l_idx = labels.index[:n]

    try:
        delta = f_idx - l_idx
        return bool((delta == pd.Timedelta(0)).any())
    except TypeError:
        # Non-datetime index fallback
        return bool((f_idx == l_idx).any())

def enforce_t_minus_1_lag(df: pd.DataFrame, lag_days: int = 1) -> pd.DataFrame:
    """Shift features by lag_days to enforce T-lag."""
    if lag_days <= 0:
        raise ValueError("lag_days must be > 0 to enforce PIT")
    if df.empty:
        return df.copy()
    return df.shift(lag_days)


# Additional PITGuard methods for comprehensive testing
class PITGuard:
    """Point-In-Time safety guard for OMEGA_QUANT.
    
    Validates temporal integrity and prevents look-ahead bias.
    """
    
    def __init__(self):
        """Initialize PIT Guard."""
        self.check_history = []
    
    def validate_pit_safety(
        self,
        df: pd.DataFrame,
        as_of_col: str = 'as_of',
        available_at_col: str = 'available_at'
    ) -> bool:
        """
        Validate PIT safety of a DataFrame.
        
        Args:
            df: DataFrame to validate
            as_of_col: Column name for as_of timestamp
            available_at_col: Column name for available_at timestamp
        
        Returns:
            True if PIT safe, False otherwise
        """
        try:
            return validate_temporal_shift(df, as_of_col, available_at_col)
        except ValueError:
            # Temporal leak detected
            return False
    
    def find_violations(
        self,
        df: pd.DataFrame,
        as_of_col: str = 'as_of',
        available_at_col: str = 'available_at'
    ) -> pd.DataFrame:
        """
        Find rows with PIT violations.
        
        Args:
            df: DataFrame to check
            as_of_col: Column name for as_of timestamp
            available_at_col: Column name for available_at timestamp
        
        Returns:
            DataFrame containing only rows with violations (as_of > available_at)
        """
        if df.empty:
            return pd.DataFrame()
        if as_of_col not in df.columns or available_at_col not in df.columns:
            return pd.DataFrame()
        
        violations = df[df[as_of_col] > df[available_at_col]]
        return violations
    
    def detect_lookahead(
        self,
        features: pd.DataFrame,
        labels: pd.DataFrame,
        lag_days: int = 1
    ) -> bool:
        """
        Detect lookahead leakage between features and labels.
        
        Args:
            features: Feature DataFrame
            labels: Label DataFrame
            lag_days: Expected lag in days
        
        Returns:
            True if lookahead detected, False otherwise
        """
        return detect_lookahead_leakage(features, labels, lag_days)
    
    def enforce_lag(
        self,
        df: pd.DataFrame,
        lag_days: int = 1
    ) -> pd.DataFrame:
        """
        Enforce T-lag on DataFrame.
        
        Args:
            df: Input DataFrame
            lag_days: Number of days to lag
        
        Returns:
            Lagged DataFrame
        """
        return enforce_t_minus_1_lag(df, lag_days)
    
    def check_feature_names(self, features: pd.DataFrame) -> List[str]:
        """
        Check feature names for potential lookahead indicators.
        
        Args:
            features: DataFrame with feature columns
        
        Returns:
            List of warning messages for suspicious feature names
        """
        warnings = []
        suspicious_keywords = ['future', 'forward', 'next', 'tomorrow', 'target', 'label']
        
        for col in features.columns:
            col_lower = str(col).lower()
            for keyword in suspicious_keywords:
                if keyword in col_lower:
                    warnings.append(f"Feature '{col}' contains suspicious keyword '{keyword}'")
        
        return warnings
    
    def check_timestamp_consistency(self, data: pd.DataFrame) -> List[str]:
        """
        Check for timestamp inconsistencies (gaps, out-of-order).
        
        Args:
            data: DataFrame with 'as_of' column
        
        Returns:
            List of issue descriptions
        """
        issues = []
        
        if 'as_of' not in data.columns:
            issues.append("Missing 'as_of' column")
            return issues
        
        if len(data) < 2:
            return issues
        
        # Check for monotonicity
        as_of_values = pd.to_datetime(data['as_of'])
        if not as_of_values.is_monotonic_increasing:
            issues.append("Timestamps are not monotonically increasing")
        
        # Check for gaps (more than 7 days)
        deltas = as_of_values.diff()
        large_gaps = deltas[deltas > pd.Timedelta(days=7)]
        if len(large_gaps) > 0:
            issues.append(f"Found {len(large_gaps)} gaps larger than 7 days")
        
        return issues
    
    def validate_timestamps(self, data: pd.DataFrame) -> bool:
        """
        Validate that all timestamps are properly formatted and consistent.
        
        Args:
            data: DataFrame with date/timestamp columns
        
        Returns:
            True if valid, False otherwise
        """
        try:
            if 'date' in data.columns:
                pd.to_datetime(data['date'])
            
            if 'as_of' in data.columns:
                pd.to_datetime(data['as_of'])
            
            if 'available_at' in data.columns:
                pd.to_datetime(data['available_at'])
            
            # Check PIT constraint if both columns exist
            if 'as_of' in data.columns and 'available_at' in data.columns:
                violations = data[pd.to_datetime(data['as_of']) > pd.to_datetime(data['available_at'])]
                if len(violations) > 0:
                    return False
            
            return True
        except Exception:
            return False
    
    def check_freshness(
        self,
        data: pd.DataFrame,
        max_age_hours: int = 24
    ) -> bool:
        """
        Check if data is fresh (within max_age_hours).
        
        Args:
            data: DataFrame with 'date' or 'as_of' column
            max_age_hours: Maximum age in hours
        
        Returns:
            True if data is fresh, False otherwise
        """
        from datetime import datetime, timedelta
        
        if 'date' in data.columns:
            latest_date = pd.to_datetime(data['date']).max()
        elif 'as_of' in data.columns:
            latest_date = pd.to_datetime(data['as_of']).max()
        else:
            return False
        
        now = datetime.now()
        age = now - latest_date.to_pydatetime()
        
        return age <= timedelta(hours=max_age_hours)
    
    def compute_lag_statistics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Compute statistics about data lag (as_of to available_at).
        
        Args:
            data: DataFrame with 'as_of' and 'available_at' columns
        
        Returns:
            Dictionary with lag statistics
        """
        if 'as_of' not in data.columns or 'available_at' not in data.columns:
            return {}
        
        as_of = pd.to_datetime(data['as_of'])
        available_at = pd.to_datetime(data['available_at'])
        
        lag_hours = (available_at - as_of).dt.total_seconds() / 3600  # hours
        lag_days = (available_at - as_of).dt.total_seconds() / 86400  # days
        
        stats = {
            'mean_lag_hours': float(lag_hours.mean()),
            'median_lag_hours': float(lag_hours.median()),
            'min_lag_hours': float(lag_hours.min()),
            'max_lag_hours': float(lag_hours.max()),
            'std_lag_hours': float(lag_hours.std()),
            'mean_lag_days': float(lag_days.mean()),
            'median_lag_days': float(lag_days.median()),
            'min_lag_days': float(lag_days.min()),
            'max_lag_days': float(lag_days.max()),
            'std_lag_days': float(lag_days.std())
        }
        
        return stats
    
    def generate_report(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate a PIT safety report for the data.
        
        Args:
            data: DataFrame to analyze
        
        Returns:
            Dictionary with report data
        """
        # Overall PIT safety status
        pit_safe = True
        total_violations = 0
        
        report = {
            'total_rows': len(data),
            'timestamp_valid': False,
            'pit_safe': False,
            'violations': 0,
            'lag_statistics': {},
            'timestamp_issues': []
        }
        
        # Timestamp validation
        report['timestamp_valid'] = self.validate_timestamps(data)
        if not report['timestamp_valid']:
            pit_safe = False
        
        # PIT safety check
        if self.validate_pit_safety(data):
            report['pit_safe'] = True
        else:
            violations = self.find_violations(data)
            total_violations = len(violations)
            report['violations'] = total_violations
            report['pit_safe'] = False
            pit_safe = False
        
        # Lag statistics
        lag_stats = self.compute_lag_statistics(data)
        if lag_stats:
            report['lag_statistics'] = lag_stats
        
        # Timestamp consistency
        issues = self.check_timestamp_consistency(data)
        if issues:
            report['timestamp_issues'] = issues
            pit_safe = False
        
        # Update final pit_safe status
        report['pit_safe'] = pit_safe
        
        return report
    
    def record_check(
        self,
        check_name: str,
        passed: bool,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Record a PIT safety check for audit trail.
        
        Args:
            check_name: Name of the check
            passed: Whether the check passed
            metadata: Additional metadata about the check
        """
        from datetime import datetime
        
        record = {
            'timestamp': datetime.now().isoformat(),
            'check_name': check_name,
            'passed': passed,
            'metadata': metadata
        }
        
        self.check_history.append(record)
    
    def get_check_history(self) -> List[Dict[str, Any]]:
        """
        Get the history of PIT safety checks.
        
        Returns:
            List of check records
        """
        return self.check_history
    
    def get_audit_trail(self) -> List[Dict[str, Any]]:
        """
        Get the audit trail of all PIT safety checks.
        
        Alias for get_check_history() for compatibility.
        
        Returns:
            List of check records with timestamps and results
        """
        return self.get_check_history()
