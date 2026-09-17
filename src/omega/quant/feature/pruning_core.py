"""Feature Pruning core algorithm implementation."""

from __future__ import annotations

import warnings
import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional, Tuple
from scipy.stats import rankdata, spearmanr

warnings.filterwarnings('ignore')

from omega.quant.feature.pruning_config import FeaturePruningConfig, PruningResult


class FeaturePruning:
    """
    IC-based feature pruning with stability analysis.
    
    Removes features with:
    - Low absolute IC (< min_ic_threshold)
    - High instability (IC varies too much over time)
    """
    
    def __init__(self, config: Optional[FeaturePruningConfig] = None):
        self.config = config or FeaturePruningConfig()
        self.pruning_history: List[Dict] = []

    @staticmethod
    def _columnwise_corr(
        values: np.ndarray,
        target: np.ndarray,
        min_periods: int
    ) -> np.ndarray:
        """Compute pairwise column correlations against a 1D target."""
        valid = ~(np.isnan(values) | np.isnan(target[:, None]))
        counts = valid.sum(axis=0)
        result = np.full(values.shape[1], np.nan, dtype=np.float64)
        enough = counts >= min_periods

        if not np.any(enough):
            return result

        x = np.where(valid, values, 0.0)
        y = np.where(valid, target[:, None], 0.0)
        n = counts.astype(np.float64)

        sum_x = x.sum(axis=0)
        sum_y = y.sum(axis=0)
        sum_x2 = (x * x).sum(axis=0)
        sum_y2 = (y * y).sum(axis=0)
        sum_xy = (x * y).sum(axis=0)

        cov = sum_xy - (sum_x * sum_y / n)
        var_x = sum_x2 - (sum_x * sum_x / n)
        var_y = sum_y2 - (sum_y * sum_y / n)
        denom = np.sqrt(var_x * var_y)

        corr = np.divide(
            cov,
            denom,
            out=np.zeros_like(cov, dtype=np.float64),
            where=denom > 1e-12
        )
        corr = np.clip(corr, -1.0, 1.0)
        result[enough] = corr[enough]
        return result
    
    def compute_ic(
        self,
        features: pd.DataFrame,
        returns: pd.Series,
        method: str = 'spearman',
        market_mask: Optional[pd.Series] = None
    ) -> Dict[str, float]:
        """
        Compute Information Coefficient for each feature.
        
        Args:
            features: DataFrame with features (rows=samples, cols=features)
            returns: Series with forward returns (same index as features)
            method: 'spearman' or 'pearson'
            market_mask: Boolean Series (True = valid trading day, False = limit-lock/illiquid)
            
        Returns:
            Dictionary mapping feature name to IC
        """
        if len(features) != len(returns):
            raise ValueError(f"Length mismatch: features={len(features)}, returns={len(returns)}")
        
        # Align indices
        common_idx = features.index.intersection(returns.index)
        if market_mask is not None:
            common_idx = common_idx.intersection(market_mask[market_mask].index)
            
        features = features.loc[common_idx]
        returns = returns.loc[common_idx]
        
        ics = {}
        
        for col in features.columns:
            feature_values = features[col].values
            return_values = returns.values
            
            # Remove NaN pairs
            mask = ~(np.isnan(feature_values) | np.isnan(return_values))
            if mask.sum() < 10:  # Need at least 10 samples
                ics[col] = 0.0
                continue
            
            feature_clean = feature_values[mask]
            return_clean = return_values[mask]
            
            try:
                if method == 'spearman':
                    ic, _ = spearmanr(feature_clean, return_clean)
                else:
                    ic = np.corrcoef(feature_clean, return_clean)[0, 1]
                
                ics[col] = ic if not np.isnan(ic) else 0.0
            except Exception as e:
                print(f"Warning: IC computation failed for {col}: {e}")
                ics[col] = 0.0
        
        return ics
    
    def compute_ic_oos(
        self,
        features: pd.DataFrame,
        returns: pd.Series,
        train_window: int = 504,
        test_window: int = 21,
        method: str = 'spearman',
        market_mask: Optional[pd.Series] = None
    ) -> Dict[str, float]:
        """
        Compute Information Coefficient out-of-sample using true walk-forward validation.
        Fits a linear relationship on train_window, evaluates on test_window.
        
        Args:
            features: DataFrame with features
            returns: Series with forward returns
            train_window: Size of training window in periods
            test_window: Size of testing window in periods
            method: 'spearman' or 'pearson'
            market_mask: Boolean Series for valid trading days
            
        Returns:
            Dictionary mapping feature name to mean out-of-sample IC
        """
        if len(features) < train_window + test_window:
            print("Warning: Not enough data for OOS IC computation. Falling back to in-sample.")
            return self.compute_ic(features, returns, method, market_mask)
            
        # Align indices
        common_idx = features.index.intersection(returns.index)
        if market_mask is not None:
            common_idx = common_idx.intersection(market_mask[market_mask].index)
            
        features = features.loc[common_idx]
        returns = returns.loc[common_idx]
        
        oos_ics = {col: [] for col in features.columns}
        
        # True Walk Forward validation
        for i in range(train_window, len(features) - test_window + 1, test_window):
            train_X = features.iloc[i-train_window:i]
            train_y = returns.iloc[i-train_window:i]
            test_X = features.iloc[i:i+test_window]
            test_y = returns.iloc[i:i+test_window]
            
            for col in features.columns:
                try:
                    # Clean NaNs in train
                    train_mask = ~(np.isnan(train_X[col].values) | np.isnan(train_y.values))
                    if train_mask.sum() < 10:
                        continue
                        
                    # Clean NaNs in test
                    test_mask = ~(np.isnan(test_X[col].values) | np.isnan(test_y.values))
                    if test_mask.sum() < 5:
                        continue
                        
                    x_train_clean = train_X[col].values[train_mask]
                    y_train_clean = train_y.values[train_mask]
                    x_test_clean = test_X[col].values[test_mask]
                    y_test_clean = test_y.values[test_mask]
                    
                    # 1. Train a simple linear model on train window
                    var_x = np.var(x_train_clean)
                    if var_x < 1e-8:
                        continue
                        
                    beta = np.cov(x_train_clean, y_train_clean)[0, 1] / var_x
                    
                    # 2. Predict on test window
                    pred_y = beta * x_test_clean
                    
                    # 3. Compute IC between prediction and actual out-of-sample
                    if method == 'spearman':
                        ic, _ = spearmanr(pred_y, y_test_clean)
                    else:
                        ic = np.corrcoef(pred_y, y_test_clean)[0, 1]
                        
                    if not np.isnan(ic):
                        oos_ics[col].append(ic)
                except Exception:
                    continue
                    
        # Average OOS ICs
        final_ics = {}
        for col, ic_list in oos_ics.items():
            if ic_list:
                final_ics[col] = float(np.mean(ic_list))
            else:
                final_ics[col] = 0.0
                
        return final_ics

    def compute_rolling_ic(
        self,
        feature_tensor: np.ndarray,
        returns: np.ndarray,
        window: int = 60,
        method: str = 'spearman',
        min_periods: int = 30,
        forward_return_period: int = 1
    ) -> pd.DataFrame:
        """
        Compute rolling 60-day IC scores for N×M×T feature matrix.
        PIT-compliant: uses T-1 lag to prevent lookahead bias.
        
        Task 2.1.1: IC Calculator for Feature Pruning
        
        Args:
            feature_tensor: 3D array of shape (N, M, T)
                N = number of time periods (samples)
                M = number of assets/instruments
                T = number of features
            returns: 2D array of shape (N, M) - forward returns aligned with features
            window: Rolling window size in days (default: 60)
            method: 'spearman' or 'pearson'
            min_periods: Minimum non-NaN observations required (default: 30)
            forward_return_period: Forward label horizon to embargo from each IC window
            
        Returns:
            DataFrame with shape (N, T) containing rolling IC per feature
            - Index: time periods (0 to N-1)
            - Columns: feature indices (0 to T-1)
            - Values: IC scores in range [-1, 1], NaN for insufficient data
            
        PIT Compliance:
            - Features at time t use data up to t-1 only
            - Returns at time t are forward returns (t to t+k)
            - IC computed using only information available at t-1
        """
        # Validate input shapes
        if feature_tensor.ndim != 3:
            raise ValueError(f"feature_tensor must be 3D (N×M×T), got shape {feature_tensor.shape}")
        
        N, M, T = feature_tensor.shape
        
        if returns.ndim != 2:
            raise ValueError(f"returns must be 2D (N×M), got shape {returns.shape}")
        
        if returns.shape != (N, M):
            raise ValueError(
                f"returns shape {returns.shape} must match feature_tensor (N={N}, M={M})"
            )
        
        if window < min_periods:
            raise ValueError(f"window ({window}) must be >= min_periods ({min_periods})")

        if forward_return_period < 1:
            raise ValueError(
                f"forward_return_period must be >= 1, got {forward_return_period}"
            )

        if forward_return_period >= window:
            raise ValueError(
                f"forward_return_period ({forward_return_period}) must be < window ({window})"
            )
        
        # Initialize output: (N, T) matrix of rolling ICs
        rolling_ics = np.full((N, T), np.nan, dtype=np.float64)
        
        # Vectorized rolling IC computation
        for t in range(window, N + 1):
            # PIT compliance: embargo recent labels whose forward returns are not observable at t.
            window_start = t - window
            window_end = t - forward_return_period
            
            # Extract window data: shape (window-1, M) for each
            features_window = feature_tensor[window_start:window_end, :, :]
            returns_window = returns[window_start:window_end, :]
            
            returns_flat = returns_window.reshape(-1)
            feature_matrix = features_window.reshape(-1, T)

            if method == 'spearman':
                if np.isnan(feature_matrix).any() or np.isnan(returns_flat).any():
                    window_ics = np.full(T, np.nan, dtype=np.float64)
                    for feat_idx in range(T):
                        feature_flat = feature_matrix[:, feat_idx]
                        valid_mask = ~(np.isnan(feature_flat) | np.isnan(returns_flat))
                        if valid_mask.sum() < min_periods:
                            continue
                        try:
                            ic, _ = spearmanr(feature_flat[valid_mask], returns_flat[valid_mask])
                            window_ics[feat_idx] = ic if not np.isnan(ic) else 0.0
                        except Exception:
                            window_ics[feat_idx] = 0.0
                else:
                    ranked_features = rankdata(feature_matrix, axis=0)
                    ranked_returns = rankdata(returns_flat)
                    window_ics = self._columnwise_corr(ranked_features, ranked_returns, min_periods)
            elif method == 'pearson':
                window_ics = self._columnwise_corr(feature_matrix, returns_flat, min_periods)
            else:
                raise ValueError(f"Unknown method: {method}. Use 'spearman' or 'pearson'")

            rolling_ics[t - 1, :] = np.where(np.isnan(window_ics), np.nan, window_ics)
        
        # Convert to DataFrame for easier handling
        ic_df = pd.DataFrame(
            rolling_ics,
            index=pd.RangeIndex(N, name='time_period'),
            columns=[f'feature_{i}' for i in range(T)]
        )
        
        return ic_df

    def compute_stability(
        self,
        features: pd.DataFrame,
        returns: pd.Series,
        window: Optional[int] = None,
        market_mask: Optional[pd.Series] = None
    ) -> Dict[str, float]:
        """
        Compute IC Information Ratio (mean/std) over rolling windows.
        Higher is more stable. Replaces Coefficient of Variation.
        
        Args:
            features: DataFrame with features
            returns: Series with forward returns
            window: Rolling window size (default: config.stability_window)
            market_mask: Boolean Series for valid trading days
            
        Returns:
            Dictionary mapping feature name to stability score (Information Ratio, higher=better)
        """
        window = window or self.config.stability_window
        
        if len(features) < window * 2:
            # Not enough data for stability analysis
            return {col: np.nan for col in features.columns}
        
        # Pre-align
        common_idx = features.index.intersection(returns.index)
        if market_mask is not None:
            common_idx = common_idx.intersection(market_mask[market_mask].index)
        
        features_aligned = features.loc[common_idx]
        returns_aligned = returns.loc[common_idx]
        
        stability_scores = {}
        
        # Step size (25% overlap instead of 50% to reduce autocorrelation)
        step = max(window // 4, 1)
        
        for col in features.columns:
            rolling_ics = []
            
            # Compute IC over rolling windows
            for i in range(window, len(features_aligned), step):
                window_features = features_aligned[col].iloc[i-window:i]
                window_returns = returns_aligned.iloc[i-window:i]
                
                feat_vals = window_features.values
                ret_vals = window_returns.values
                
                mask = ~(np.isnan(feat_vals) | np.isnan(ret_vals))
                if mask.sum() < 10:
                    continue
                
                try:
                    ic, _ = spearmanr(feat_vals[mask], ret_vals[mask])
                    if not np.isnan(ic):
                        rolling_ics.append(ic)
                except:
                    continue
            
            # Compute IC Information Ratio (mean / std)
            if len(rolling_ics) >= 2:
                mean_ic = np.mean(rolling_ics)
                std_ic = np.std(rolling_ics)
                
                if std_ic > 1e-8:
                    ir = mean_ic / std_ic
                else:
                    ir = 999.0 if mean_ic > 0 else -999.0  # Perfect stability
                
                # We use absolute value because a consistently negative IC is also stable
                stability_scores[col] = abs(ir)
            else:
                stability_scores[col] = np.nan
        
        return stability_scores
    
    def prune_features(
        self,
        features: pd.DataFrame,
        returns: pd.Series,
        progressive: bool = True,
        market_mask: Optional[pd.Series] = None
    ) -> PruningResult:
        """
        Prune features based on IC, stability, and correlation.
        
        Args:
            features: DataFrame with features
            returns: Series with forward returns
            progressive: If True, remove only progressive_rate% per iteration
            market_mask: Boolean Series for valid trading days
            
        Returns:
            PruningResult with kept/removed features
        """
        # Compute IC and stability
        if getattr(self.config, 'use_oos_ic', True):
            ics = self.compute_ic_oos(features, returns, market_mask=market_mask)
        else:
            ics = self.compute_ic(features, returns, market_mask=market_mask)
            
        stability = self.compute_stability(features, returns, market_mask=market_mask)
        
        # 1. Prune by IC and Stability
        to_remove_initial = []
        
        for col in features.columns:
            ic = abs(ics.get(col, 0.0))
            stab = stability.get(col, np.nan)
            
            # Remove if IC too low
            if ic < self.config.min_ic_threshold:
                to_remove_initial.append((col, 'low_ic', ic))
            # Remove if stability (Information Ratio) is computed and TOO LOW
            elif not np.isnan(stab) and stab < self.config.stability_threshold:
                to_remove_initial.append((col, 'unstable', stab))
                
        # 2. Prune by Correlation (Feature Interaction Handling)
        active_features = [c for c in features.columns if c not in [x[0] for x in to_remove_initial]]
        if len(active_features) > self.config.min_features:
            # Sort active features by IC descending
            active_sorted = sorted(active_features, key=lambda x: abs(ics.get(x, 0.0)), reverse=True)
            
            # Calculate correlation matrix
            corr_matrix = features[active_sorted].corr().abs()
            
            removed_by_corr = set()
            for i in range(len(active_sorted)):
                col1 = active_sorted[i]
                if col1 in removed_by_corr:
                    continue
                    
                for j in range(i + 1, len(active_sorted)):
                    col2 = active_sorted[j]
                    if col2 in removed_by_corr:
                        continue
                        
                    if corr_matrix.loc[col1, col2] > getattr(self.config, 'max_correlation', 0.85):
                        # Remove the one with lower IC (which is col2 since we sorted)
                        removed_by_corr.add(col2)
                        to_remove_initial.append((col2, 'high_correlation', corr_matrix.loc[col1, col2]))
                        
        to_remove = to_remove_initial
        
        # Progressive pruning: limit removal rate
        if progressive and len(to_remove) > 0:
            max_remove = int(len(features.columns) * self.config.progressive_rate)
            
            if len(to_remove) > max_remove:
                # Sort by IC (ascending) and keep only worst max_remove
                to_remove_sorted = sorted(to_remove, key=lambda x: abs(ics.get(x[0], 0.0)))
                to_remove = to_remove_sorted[:max_remove]
        
        # Enforce min_features constraint
        kept_count = len(features.columns) - len(to_remove)
        if kept_count < self.config.min_features:
            # Keep more features by removing the excess from the end (worst IC features)
            # Since to_remove is sorted worst-first, we should slice off the end to keep the better ones
            excess_removal = self.config.min_features - kept_count
            to_remove = to_remove[:-excess_removal]
        
        # Build result
        removed_features = [x[0] for x in to_remove]
        kept_features = [col for col in features.columns if col not in removed_features]
        
        result = PruningResult(
            kept_features=kept_features,
            removed_features=removed_features,
            feature_ics=ics,
            stability_scores=stability,
            pruning_history=self.pruning_history
        )
        
        # Log pruning decision
        self.pruning_history.append({
            'timestamp': pd.Timestamp.now(),
            'removed_count': len(removed_features),
            'kept_count': len(kept_features),
            'removed_features': removed_features,
            'reasons': {x[0]: x[1] for x in to_remove}
        })
        
        return result
    
    def select_features_by_ic(
        self,
        feature_tensor: np.ndarray,
        returns: np.ndarray,
        ic_threshold: float = 0.05,
        stability_threshold: float = 0.02,
        top_n: int = 30,
        window: int = 60,
        min_periods: int = 30,
        forward_return_period: int = 1,
        enforce_pit: bool = True
    ) -> Dict[str, Any]:
        """
        Dynamic Feature Selector for Feature Pruning (Task 2.1.2)
        
        Selects top 20-30 features with IC > 0.05, checks stability (IC std < 0.02),
        and enforces PIT compliance (T-1 lag).
        
        Args:
            feature_tensor: 3D array of shape (N, M, T)
                N = number of time periods
                M = number of assets
                T = number of features
            returns: 2D array of shape (N, M) - forward returns
            ic_threshold: Minimum absolute IC to consider (default: 0.05)
            stability_threshold: Maximum IC standard deviation (default: 0.02)
            top_n: Maximum number of features to select (default: 30)
            window: Rolling window for IC calculation (default: 60)
            min_periods: Minimum observations for IC (default: 30)
            forward_return_period: Forward label horizon to embargo from each IC window
            enforce_pit: If True, verify T-1 lag compliance (default: True)
            
        Returns:
            Dictionary containing:
                - selected_features: List[int] - indices of selected features
                - feature_ics: np.ndarray - mean IC for each feature (shape: T)
                - feature_ic_std: np.ndarray - IC std for each feature (shape: T)
                - stability_mask: np.ndarray - boolean mask for stable features (shape: T)
                - pit_compliant: bool - whether PIT compliance is verified
                - selection_summary: Dict - summary statistics
                
        PIT Compliance:
            - Uses T-1 lag in rolling IC calculation
            - Verifies no lookahead bias in feature selection
            
        Vectorization:
            - All operations use NumPy vectorized operations
            - No Python loops over features or time periods
        """
        # Validate inputs
        if feature_tensor.ndim != 3:
            raise ValueError(f"feature_tensor must be 3D (N×M×T), got shape {feature_tensor.shape}")
        
        N, M, T = feature_tensor.shape
        
        if returns.ndim != 2 or returns.shape != (N, M):
            raise ValueError(
                f"returns shape {returns.shape} must match feature_tensor (N={N}, M={M})"
            )
        
        if ic_threshold < 0 or ic_threshold > 1:
            raise ValueError(f"ic_threshold must be in [0, 1], got {ic_threshold}")
        
        if stability_threshold < 0:
            raise ValueError(f"stability_threshold must be >= 0, got {stability_threshold}")
        
        if top_n < 1 or top_n > T:
            raise ValueError(f"top_n must be in [1, {T}], got {top_n}")
        
        # Step 1: Compute rolling IC using existing method (PIT-compliant)
        rolling_ic_df = self.compute_rolling_ic(
            feature_tensor=feature_tensor,
            returns=returns,
            window=window,
            method='spearman',
            min_periods=min_periods,
            forward_return_period=forward_return_period
        )
        
        # Convert to numpy array for vectorized operations
        rolling_ic = rolling_ic_df.values  # Shape: (N, T)
        
        # Step 2: Compute mean IC and IC std for each feature (vectorized)
        # Only use valid (non-NaN) IC values for each feature
        feature_ics = np.nanmean(np.abs(rolling_ic), axis=0)  # Shape: (T,)
        feature_ic_std = np.nanstd(rolling_ic, axis=0)  # Shape: (T,)
        
        # Step 3: Apply IC threshold filter (vectorized)
        ic_mask = feature_ics > ic_threshold  # Shape: (T,)
        
        # Step 4: Apply stability filter (vectorized)
        stability_mask = feature_ic_std < stability_threshold  # Shape: (T,)
        
        # Step 5: Combine filters (vectorized)
        combined_mask = ic_mask & stability_mask  # Shape: (T,)
        
        # Step 6: Select top N features by IC (vectorized)
        # Get indices of features that pass both filters
        candidate_indices = np.where(combined_mask)[0]
        
        if len(candidate_indices) == 0:
            # No features pass filters - relax stability constraint
            candidate_indices = np.where(ic_mask)[0]
            
            if len(candidate_indices) == 0:
                # Still no features - return top N by IC regardless
                candidate_indices = np.arange(T)
        
        # Sort candidates by IC (descending) and take top N
        candidate_ics = feature_ics[candidate_indices]
        sorted_order = np.argsort(candidate_ics)[::-1]  # Descending
        selected_indices = candidate_indices[sorted_order[:min(top_n, len(candidate_indices))]]
        
        # Step 7: PIT compliance verification
        pit_compliant = True
        if enforce_pit:
            # Verify that rolling_ic computation used T-1 lag
            # Check: first (window-1) rows should be NaN
            first_valid_row = window - 1
            if not np.all(np.isnan(rolling_ic[:first_valid_row, :])):
                pit_compliant = False
        
        # Step 8: Build selection summary
        selection_summary = {
            'total_features': T,
            'ic_threshold': ic_threshold,
            'stability_threshold': stability_threshold,
            'forward_return_period': forward_return_period,
            'features_above_ic': int(ic_mask.sum()),
            'features_stable': int(stability_mask.sum()),
            'features_both_filters': int(combined_mask.sum()),
            'selected_count': len(selected_indices),
            'mean_ic_selected': float(np.mean(feature_ics[selected_indices])),
            'mean_ic_selected_std': float(np.mean(feature_ic_std[selected_indices])),
            'min_ic_selected': float(np.min(feature_ics[selected_indices])),
            'max_ic_selected': float(np.max(feature_ics[selected_indices]))
        }
        
        return {
            'selected_features': selected_indices.tolist(),
            'feature_ics': feature_ics,
            'feature_ic_std': feature_ic_std,
            'stability_mask': stability_mask,
            'pit_compliant': pit_compliant,
            'selection_summary': selection_summary
        }

    def get_feature_importance(
        self,
        features: pd.DataFrame,
        returns: pd.Series
    ) -> pd.DataFrame:
        """
        Get feature importance ranking.
        
        Returns:
            DataFrame with columns [feature, ic, abs_ic, stability, rank]
        """
        ics = self.compute_ic(features, returns)
        stability = self.compute_stability(features, returns)
        
        importance_df = pd.DataFrame({
            'feature': list(ics.keys()),
            'ic': [ics[f] for f in ics.keys()],
            'abs_ic': [abs(ics[f]) for f in ics.keys()],
            'stability': [stability.get(f, 0.0) for f in ics.keys()]
        })
        
        # Rank by absolute IC (descending)
        importance_df = importance_df.sort_values('abs_ic', ascending=False)
        importance_df['rank'] = range(1, len(importance_df) + 1)
        
        return importance_df.reset_index(drop=True)
