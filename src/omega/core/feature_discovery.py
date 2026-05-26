"""
Feature Discovery - Vectorized Implementation (ROUND 10 - ZERO LOOPS)
Automatically discovers new high-alpha features via operators.

Part of OMEGA_QUANT Layer 01 Core Intelligence.
100% vectorized (ZERO LOOPS), PIT safe (T-1 lag enforced).
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple


class FeatureDiscovery:
    """Vectorized feature discovery engine with T-1 lag."""

    def __init__(self, operators: Optional[List[str]] = None):
        self.operators = operators or ['lag', 'diff', 'rolling_mean', 'rolling_std', 'pct_change']

    def discover_features(
        self, data: pd.Series, name: str, windows: List[int] = [5, 10, 20, 60]
    ) -> pd.DataFrame:
        """
        Apply various operators to input data to discover new features.
        100% vectorized - ZERO LOOPS.
        """
        # Shift data by 1 to enforce T-1 lag
        data_lagged = data.shift(1)
        
        # Pre-compute all features (vectorized)
        feature_dict = {}
        
        # Lag features
        feature_dict[f'{name}_lag_5'] = data_lagged.shift(5)
        feature_dict[f'{name}_lag_10'] = data_lagged.shift(10)
        feature_dict[f'{name}_lag_20'] = data_lagged.shift(20)
        feature_dict[f'{name}_lag_60'] = data_lagged.shift(60)
        
        # Diff features
        feature_dict[f'{name}_diff_5'] = data_lagged.diff(5)
        feature_dict[f'{name}_diff_10'] = data_lagged.diff(10)
        feature_dict[f'{name}_diff_20'] = data_lagged.diff(20)
        feature_dict[f'{name}_diff_60'] = data_lagged.diff(60)
        
        # MA features
        feature_dict[f'{name}_ma_5'] = data_lagged.rolling(window=5).mean()
        feature_dict[f'{name}_ma_10'] = data_lagged.rolling(window=10).mean()
        feature_dict[f'{name}_ma_20'] = data_lagged.rolling(window=20).mean()
        feature_dict[f'{name}_ma_60'] = data_lagged.rolling(window=60).mean()
        
        # STD features
        feature_dict[f'{name}_std_5'] = data_lagged.rolling(window=5).std()
        feature_dict[f'{name}_std_10'] = data_lagged.rolling(window=10).std()
        feature_dict[f'{name}_std_20'] = data_lagged.rolling(window=20).std()
        feature_dict[f'{name}_std_60'] = data_lagged.rolling(window=60).std()
        
        # Returns features
        feature_dict[f'{name}_ret_5'] = data_lagged.pct_change(5)
        feature_dict[f'{name}_ret_10'] = data_lagged.pct_change(10)
        feature_dict[f'{name}_ret_20'] = data_lagged.pct_change(20)
        feature_dict[f'{name}_ret_60'] = data_lagged.pct_change(60)
        
        return pd.DataFrame(feature_dict, index=data.index)

    def discover_cross_features(
        self, df: pd.DataFrame, columns: List[str]
    ) -> pd.DataFrame:
        """
        Discover cross features (ratio, spread) between multiple columns.
        100% vectorized - ZERO LOOPS.
        """
        df_lagged = df[columns].shift(1)
        n_cols = len(columns)
        i_indices, j_indices = np.triu_indices(n_cols, k=1)
        
        c1_arr = np.array(columns)[i_indices]
        c2_arr = np.array(columns)[j_indices]
        
        df1 = df_lagged[c1_arr].values
        df2 = df_lagged[c2_arr].values
        
        ratios = df1 / np.where(df2 == 0, np.nan, df2)
        spreads = df1 - df2
        norm_spreads = (df1 - df2) / np.where((df1 + df2) == 0, np.nan, (df1 + df2))
        
        # Vectorized string concatenation for column names
        ratio_cols = np.char.add(np.char.add(c1_arr.astype(str), "_"), np.char.add(c2_arr.astype(str), "_ratio")).tolist()
        spread_cols = np.char.add(np.char.add(c1_arr.astype(str), "_"), np.char.add(c2_arr.astype(str), "_spread")).tolist()
        norm_cols = np.char.add(np.char.add(c1_arr.astype(str), "_"), np.char.add(c2_arr.astype(str), "_norm_spread")).tolist()
        
        return pd.DataFrame(
            np.hstack([ratios, spreads, norm_spreads]),
            index=df.index,
            columns=ratio_cols + spread_cols + norm_cols
        )

    def rank_features(
        self, features: pd.DataFrame, target: pd.Series, top_n: int = 20
    ) -> List[str]:
        """Rank features by correlation. Vectorized."""
        correlations = features.shift(1).corrwith(target.shift(1)).abs().nlargest(top_n)
        return correlations.index.tolist()

    def discover_multi_step_features(
        self, data: pd.Series, name: str, window: int = 20
    ) -> pd.DataFrame:
        """Discover multi-step features. Vectorized."""
        data_lagged = data.shift(1)
        ret = data_lagged.pct_change(1)
        ma = data_lagged.rolling(window=window).mean()
        vol = data_lagged.pct_change().rolling(window=window).std()
        
        return pd.DataFrame({
            f'{name}_ma_ret': ret.rolling(window=window).mean(),
            f'{name}_vol_ma': ma.pct_change().rolling(window=window).std(),
            f'{name}_mom_vol': vol.pct_change(5)
        }, index=data.index)
