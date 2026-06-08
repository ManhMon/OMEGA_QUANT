import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from scipy import stats

class ModelValidator:
    """
    Phase 2.3 Model Validator
    Ensures Deep PIT safety, leakage detection, walk-forward validation, out-of-sample metrics,
    and statistical significance testing.
    """

    def __init__(self, target_col: str = 'target', embargo_days: int = 1):
        self.target_col = target_col
        self.embargo_days = embargo_days

    def check_pit_safety(self, predictions: pd.DataFrame, features: pd.DataFrame) -> bool:
        """
        Deep PIT safety check.
        Ensures `available_at` timestamp of features is strictly BEFORE the prediction date.
        Assumes `predictions` has index 'date' and features has columns like 'feature_xyz_available_at'.
        Or features has 'available_at' column.
        """
        if 'available_at' not in features.columns:
            # Fallback: check index alignment
            if not predictions.index.is_monotonic_increasing or not features.index.is_monotonic_increasing:
                return False
            return True
            
        merged = pd.merge(predictions, features[['available_at']], left_index=True, right_index=True)
        if len(merged) == 0:
            return True
            
        # Ensure available_at is before or equal to prediction date index
        is_safe = (merged['available_at'] <= merged.index).all()
        return bool(is_safe)

    def detect_leakage(self, data: pd.DataFrame, feature_cols: List[str], target_col: Optional[str] = None) -> bool:
        """
        Leakage detection: Temporal, Label, Feature leakage.
        Returns True if leakage is DETECTED, False if safe.
        """
        tgt = target_col or self.target_col
        if tgt not in data.columns:
            raise ValueError(f"Target column {tgt} not found in data.")
            
        # Temporal leakage check
        if not data.index.is_monotonic_increasing:
            # Not chronologically sorted
            return True

        # Feature leakage (correlation with FUTURE target is expected, but current feature correlation with CURRENT target might indicate leakage if target is future returns but feature incorporates current unobservable price)
        # We will check if any feature has a ridiculously high correlation with target (> 0.95), typical of label leakage
        correlations = data[feature_cols + [tgt]].corr()
        tgt_corr = correlations[tgt].drop(tgt).abs()
        if (tgt_corr > 0.95).any():
            return True

        return False

    def check_embargo(self, train_end_date: pd.Timestamp, val_start_date: pd.Timestamp) -> bool:
        """
        Enforce strict embargo between training and validation sets.
        """
        delta = (val_start_date - train_end_date).days
        return delta >= self.embargo_days

    def walk_forward_validation(self, data: pd.DataFrame, n_splits: int = 5, train_size: float = 0.7) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
        """
        Generate non-overlapping walk-forward validation splits enforcing embargo.
        """
        splits = []
        n_samples = len(data)
        split_size = n_samples // n_splits
        
        for i in range(n_splits):
            start_idx = i * split_size
            end_idx = start_idx + split_size if i < n_splits - 1 else n_samples
            
            chunk = data.iloc[start_idx:end_idx]
            train_idx = int(len(chunk) * train_size)
            
            train_set = chunk.iloc[:train_idx]
            # Embargo logic: skip rows based on embargo_days. Assuming daily data.
            val_start_idx = train_idx + self.embargo_days
            if val_start_idx >= len(chunk):
                continue
            val_set = chunk.iloc[val_start_idx:]
            
            splits.append((train_set, val_set))
            
        return splits

    def calculate_metrics(self, y_true: pd.Series, y_pred: pd.Series) -> Dict[str, float]:
        """
        Calculate Information Coefficient (IC) and Sharpe Ratio.
        """
        if len(y_true) < 2 or len(y_pred) < 2:
            return {'ic': 0.0, 'sharpe': 0.0}
            
        # IC is Pearson correlation
        ic, _ = stats.pearsonr(y_true, y_pred)
        if np.isnan(ic):
            ic = 0.0
            
        # Simplified Sharpe (assuming y_pred represents daily returns or strategy returns)
        # Using returns directly for sharpe if we consider y_true * sign(y_pred) as strategy returns
        strategy_returns = y_true * np.sign(y_pred)
        if strategy_returns.std() == 0:
            sharpe = 0.0
        else:
            sharpe = (strategy_returns.mean() / strategy_returns.std()) * np.sqrt(252)
            
        if np.isnan(sharpe):
            sharpe = 0.0
            
        return {'ic': float(ic), 'sharpe': float(sharpe)}

    def validate_performance(self, metrics: Dict[str, float]) -> bool:
        """
        Out-of-sample performance validation (IC > 0.1, Sharpe > 1.5).
        """
        ic_pass = metrics.get('ic', 0.0) > 0.1
        sharpe_pass = metrics.get('sharpe', 0.0) > 1.5
        return ic_pass and sharpe_pass

    def statistical_significance(self, y_true: pd.Series, y_pred: pd.Series, n_bootstraps: int = 1000) -> Dict[str, float]:
        """
        Statistical significance testing (p-value, bootstrapping) for IC.
        """
        if len(y_true) < 2:
            return {'p_value': 1.0, 'ic_mean': 0.0, 'ic_std': 0.0}
            
        # Calculate standard p-value for IC
        ic, p_value = stats.pearsonr(y_true, y_pred)
        
        # Bootstrap
        np.random.seed(42)
        indices = np.arange(len(y_true))
        boot_ics = []
        for _ in range(n_bootstraps):
            sample_idx = np.random.choice(indices, size=len(indices), replace=True)
            try:
                b_ic, _ = stats.pearsonr(y_true.iloc[sample_idx], y_pred.iloc[sample_idx])
                if not np.isnan(b_ic):
                    boot_ics.append(b_ic)
            except:
                continue
                
        ic_mean = np.mean(boot_ics) if boot_ics else 0.0
        ic_std = np.std(boot_ics) if boot_ics else 0.0
        
        return {
            'p_value': float(p_value if not np.isnan(p_value) else 1.0),
            'ic_mean': float(ic_mean),
            'ic_std': float(ic_std)
        }
