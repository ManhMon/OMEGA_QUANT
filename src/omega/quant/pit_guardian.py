"""
PIT Guardian - Point-in-Time Safety Precondition (P0-1)

This module enforces 3-Timestamp PIT compliance BEFORE any pipeline execution:
- Feature Timestamp: When features were computed
- Decision Timestamp: When trading decision was made
- Execution Timestamp: When order was placed

All timestamps must satisfy: Feature < Decision <= Execution
This prevents look-ahead bias and ensures institutional-grade data integrity.

Usage:
    guardian = PITGuardian()
    assert guardian.verify_pit_compliance(feature_ts, decision_ts, execution_ts), "PIT violation"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd


@dataclass
class PITViolation:
    """Represents a Point-in-Time violation."""
    violation_type: str
    message: str
    feature_ts: Optional[datetime] = None
    decision_ts: Optional[datetime] = None
    execution_ts: Optional[datetime] = None
    severity: str = "CRITICAL"


class PITGuardian:
    """
    PIT Guardian enforces 3-Timestamp compliance as a precondition.
    
    This is the FIRST check that runs before any layer executes.
    If PIT is violated, the entire pipeline HALTS.
    """
    
    def __init__(self, settlement_delay_days: float = 2.5, embargo_bars: int = 3):
        """
        Initialize PIT Guardian.
        
        Args:
            settlement_delay_days: T+N settlement delay (default 2.5 for VN market)
            embargo_bars: Minimum bars between feature computation and decision
        """
        self.settlement_delay_days = settlement_delay_days
        self.embargo_bars = embargo_bars
        self.violations: List[PITViolation] = []
    
    def verify_pit_compliance(
        self,
        feature_ts: Optional[datetime] = None,
        decision_ts: Optional[datetime] = None,
        execution_ts: Optional[datetime] = None,
        data_dict: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Verify 3-Timestamp PIT compliance.
        
        Args:
            feature_ts: When features were computed (must be historical)
            decision_ts: When trading decision was made
            execution_ts: When order was placed
            data_dict: Optional dict with 'feature_ts', 'decision_ts', 'execution_ts' keys
            
        Returns:
            True if all PIT checks pass, False otherwise
        """
        self.violations.clear()
        
        # Extract timestamps from data_dict if provided
        if data_dict is not None:
            feature_ts = data_dict.get('feature_ts', feature_ts)
            decision_ts = data_dict.get('decision_ts', decision_ts)
            execution_ts = data_dict.get('execution_ts', execution_ts)
        
        # Convert to datetime if needed
        feature_ts = self._to_datetime(feature_ts)
        decision_ts = self._to_datetime(decision_ts)
        execution_ts = self._to_datetime(execution_ts)
        
        # P0-1 FIX: Fail-Closed - If ANY timestamp is None, this is CRITICAL
        missing_timestamps = []
        if feature_ts is None:
            missing_timestamps.append("feature_ts")
        if decision_ts is None:
            missing_timestamps.append("decision_ts")
        if execution_ts is None:
            missing_timestamps.append("execution_ts")
        
        if missing_timestamps:
            self.violations.append(PITViolation(
                violation_type="MISSING_TIMESTAMPS",
                message=f"Missing required timestamps: {', '.join(missing_timestamps)} - cannot verify PIT compliance",
                severity="CRITICAL"
            ))
            return False
        
        # Check 1: Feature timestamp must be before decision timestamp
        if feature_ts is not None and decision_ts is not None:
            if feature_ts >= decision_ts:
                self.violations.append(PITViolation(
                    violation_type="FEATURE_AFTER_DECISION",
                    message=f"Feature timestamp {feature_ts} >= Decision timestamp {decision_ts}",
                    feature_ts=feature_ts,
                    decision_ts=decision_ts,
                    severity="CRITICAL"
                ))
        
        # Check 2: Decision timestamp must be <= execution timestamp
        if decision_ts is not None and execution_ts is not None:
            if decision_ts > execution_ts:
                self.violations.append(PITViolation(
                    violation_type="DECISION_AFTER_EXECUTION",
                    message=f"Decision timestamp {decision_ts} > Execution timestamp {execution_ts}",
                    decision_ts=decision_ts,
                    execution_ts=execution_ts,
                    severity="CRITICAL"
                ))
        
        # Check 3: Embargo period between feature and decision
        # P0-1 FIX: Changed from WARNING to CRITICAL to block all leakage
        if feature_ts is not None and decision_ts is not None:
            time_delta = decision_ts - feature_ts
            min_embargo = timedelta(hours=self.embargo_bars)
            
            if time_delta < min_embargo:
                self.violations.append(PITViolation(
                    violation_type="EMBARGO_VIOLATION",
                    message=f"Insufficient embargo period: {time_delta} < {min_embargo}",
                    feature_ts=feature_ts,
                    decision_ts=decision_ts,
                    severity="CRITICAL"
                ))
        
        # Check 4: Settlement delay compliance
        # P0-1 FIX: Changed from WARNING to CRITICAL to block all leakage
        if execution_ts is not None and feature_ts is not None:
            settlement_delta = execution_ts - feature_ts
            min_settlement = timedelta(days=self.settlement_delay_days)
            
            if settlement_delta < min_settlement:
                self.violations.append(PITViolation(
                    violation_type="SETTLEMENT_VIOLATION",
                    message=f"Insufficient settlement delay: {settlement_delta} < {min_settlement}",
                    feature_ts=feature_ts,
                    execution_ts=execution_ts,
                    severity="CRITICAL"
                ))
        
        # Return True only if no CRITICAL violations
        critical_violations = [v for v in self.violations if v.severity == "CRITICAL"]
        return len(critical_violations) == 0
    
    def verify_dataframe(self, df: pd.DataFrame, timestamp_col: str = 'timestamp', symbol_col: str = 'symbol') -> bool:
        """
        Verify PIT compliance for a DataFrame with timestamps.
        
        ROUND 7 FIX: Handle panel data (multiple symbols per timestamp).
        For panel data, verify timestamps are sorted within each symbol group.
        
        Args:
            df: DataFrame with timestamp column (and optional symbol column for panel data)
            timestamp_col: Name of timestamp column
            symbol_col: Name of symbol column (for panel data, default 'symbol')
            
        Returns:
            True if all timestamps are PIT-compliant (sorted within each symbol group)
        """
        if df is None or len(df) == 0:
            return True
        
        if timestamp_col not in df.columns:
            self.violations.append(PITViolation(
                violation_type="MISSING_TIMESTAMP",
                message=f"Timestamp column '{timestamp_col}' not found in DataFrame",
                severity="CRITICAL"
            ))
            return False
        
        # ROUND 7 FIX: Detect panel data (multiple symbols per timestamp)
        has_symbol_col = symbol_col in df.columns
        
        if has_symbol_col:
            # Panel data: verify timestamps are sorted within each symbol group
            timestamps = pd.to_datetime(df[timestamp_col])
            
            # Check 1: Verify timestamps are sorted globally (required for PIT compliance)
            # For panel data sorted by ['timestamp', 'symbol'], timestamps should be monotonic_increasing
            if not timestamps.is_monotonic_increasing:
                self.violations.append(PITViolation(
                    violation_type="UNSORTED_TIMESTAMPS",
                    message=f"Timestamps in column '{timestamp_col}' are not sorted (panel data must be sorted by ['{timestamp_col}', '{symbol_col}'])",
                    severity="CRITICAL"
                ))
                return False
            
            # Check 2: Verify each symbol's timestamps are strictly increasing (no duplicates within symbol)
            for symbol, group in df.groupby(symbol_col):
                symbol_timestamps = pd.to_datetime(group[timestamp_col])
                
                if not symbol_timestamps.is_monotonic_increasing:
                    self.violations.append(PITViolation(
                        violation_type="UNSORTED_TIMESTAMPS",
                        message=f"Timestamps for symbol '{symbol}' are not sorted",
                        severity="CRITICAL"
                    ))
                    return False
                
                if symbol_timestamps.duplicated().any():
                    self.violations.append(PITViolation(
                        violation_type="DUPLICATE_TIMESTAMPS",
                        message=f"Duplicate timestamps found for symbol '{symbol}'",
                        severity="CRITICAL"
                    ))
                    return False
        else:
            # Single time series: verify timestamps are strictly increasing (no duplicates)
            timestamps = pd.to_datetime(df[timestamp_col])
            is_sorted = timestamps.is_monotonic_increasing
            
            if not is_sorted:
                self.violations.append(PITViolation(
                    violation_type="UNSORTED_TIMESTAMPS",
                    message=f"Timestamps in column '{timestamp_col}' are not sorted",
                    severity="CRITICAL"
                ))
                return False
            
            # Check for duplicate timestamps
            if timestamps.duplicated().any():
                self.violations.append(PITViolation(
                    violation_type="DUPLICATE_TIMESTAMPS",
                    message=f"Duplicate timestamps found in column '{timestamp_col}'",
                    severity="CRITICAL"
                ))
                return False
        
        return True
    
    def verify_feature_lag(
        self,
        feature_date: datetime,
        current_date: datetime,
        min_lag_days: int = 1
    ) -> bool:
        """
        Verify that features are lagged by at least min_lag_days.
        
        Args:
            feature_date: Date when features were computed
            current_date: Current date (decision/execution date)
            min_lag_days: Minimum lag in days (default 1 = T-1 features)
            
        Returns:
            True if feature_date < current_date - min_lag_days
        """
        feature_date = self._to_datetime(feature_date)
        current_date = self._to_datetime(current_date)
        
        if feature_date is None or current_date is None:
            self.violations.append(PITViolation(
                violation_type="MISSING_DATE",
                message="feature_date or current_date is None",
                severity="CRITICAL"
            ))
            return False
        
        min_feature_date = current_date - timedelta(days=min_lag_days)
        
        if feature_date >= min_feature_date:
            self.violations.append(PITViolation(
                violation_type="INSUFFICIENT_LAG",
                message=f"Feature date {feature_date} >= {min_feature_date} (current - {min_lag_days} days)",
                feature_ts=feature_date,
                decision_ts=current_date,
                severity="CRITICAL"
            ))
            return False
        
        return True

    def check_feature_availability(
        self,
        feature_date: datetime,
        current_date: datetime,
        min_lag_days: int = 1
    ) -> bool:
        """Alias for verify_feature_lag to satisfy contract."""
        return self.verify_feature_lag(feature_date, current_date, min_lag_days)

    def check_target_leakage(
        self,
        features: pd.DataFrame,
        targets: pd.Series,
        prediction_date: datetime
    ) -> bool:
        """
        Detect future information leakage in features.
        
        Verifies that no feature contains information from the target
        that would not be available at prediction time.
        
        Args:
            features: Feature DataFrame with DatetimeIndex
            targets: Target Series with DatetimeIndex
            prediction_date: Date for which predictions are made
            
        Returns:
            True if no target leakage detected, False otherwise
        """
        prediction_date = self._to_datetime(prediction_date)
        
        if prediction_date is None:
            self.violations.append(PITViolation(
                violation_type="MISSING_PREDICTION_DATE",
                message="prediction_date is None",
                severity="CRITICAL"
            ))
            return False
        
        # Check 1: All feature timestamps must be before prediction_date
        if hasattr(features, 'index') and isinstance(features.index, pd.DatetimeIndex):
            future_features = features[features.index >= prediction_date]
            if len(future_features) > 0:
                self.violations.append(PITViolation(
                    violation_type="FUTURE_FEATURES",
                    message=f"Found {len(future_features)} features with timestamps >= prediction_date",
                    decision_ts=prediction_date,
                    severity="CRITICAL"
                ))
                return False
        
        # Check 2: All target timestamps must be after or equal to prediction_date
        if hasattr(targets, 'index') and isinstance(targets.index, pd.DatetimeIndex):
            past_targets = targets[targets.index < prediction_date]
            if len(past_targets) > 0:
                self.violations.append(PITViolation(
                    violation_type="PAST_TARGETS",
                    message=f"Found {len(past_targets)} targets with timestamps < prediction_date (potential leakage)",
                    decision_ts=prediction_date,
                    severity="CRITICAL"
                ))
                return False
        
        return True
    
    def get_violations(self) -> List[PITViolation]:
        """Get all violations from last verification."""
        return self.violations
    
    def generate_report(self) -> str:
        """Get human-readable violation report."""
        if not self.violations:
            return "✅ PIT Guardian: All checks passed"
        
        report = ["❌ PIT Guardian: Violations detected\n"]
        for i, v in enumerate(self.violations, 1):
            report.append(f"{i}. [{v.severity}] {v.violation_type}: {v.message}")
        
        return "\n".join(report)
    
    def _to_datetime(self, ts: Any) -> Optional[datetime]:
        """Convert various timestamp formats to datetime."""
        if ts is None:
            return None
        
        if isinstance(ts, datetime):
            return ts
        
        if isinstance(ts, pd.Timestamp):
            return ts.to_pydatetime()
        
        if isinstance(ts, str):
            return pd.to_datetime(ts).to_pydatetime()
        
        return None
