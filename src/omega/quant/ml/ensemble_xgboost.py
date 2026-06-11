"""
XGBoost Alpha Ensemble Module (Phase 11 - OMEGA_QUANT)
Layer 02: Strategy Logic

ML-based Alpha Ensemble using XGBoost Ranker.

Key Features:
- PIT-Safe regime features with shift(1)
- Fixed cutoff and embargo to prevent leakage
- Winsorization persistence between train/predict
- Ensemble ranking for alpha discovery

# Adapted from: archive/V21_QUANT_FINAL_20260509/src/v21_system/layer_02_strategy_logic/alpha_ensemble_xgboost.py
"""

import xgboost as xgb
import pandas as pd
import numpy as np
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class XGBoostAlphaEnsemble:
    """
    ML-based Alpha Ensemble using XGBoost Ranker.

    PIT Safety:
    - Regime features use shift(1)
    - Fixed train cutoff + embargo
    - No future leakage in feature engineering
    """

    def __init__(self, model_path: Optional[str] = None, min_ic_threshold: float = 0.15):
        self.model = xgb.XGBRanker(
            objective='rank:pairwise',
            n_estimators=300,
            learning_rate=0.03,
            max_depth=5,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            tree_method='hist'
        )
        self.is_trained = False
        self.feature_cols = []
        self._winsor_lower: Optional[pd.Series] = None
        self._winsor_upper: Optional[pd.Series] = None
        self.min_ic_threshold = min_ic_threshold

    def _prepare_regime_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate regime features with strict PIT compliance (shift(1)).
        """
        df = df.copy()
        mkt_prices = df.unstack(level='symbol')['close'].ffill()
        index_proxy = mkt_prices.mean(axis=1)

        # PIT-safe: shift(1) after rolling calculations
        mkt_vol = index_proxy.pct_change().rolling(20).std().shift(1)
        mkt_ret = index_proxy.pct_change(20).shift(1)

        # Map back to multi-index
        df['mkt_vol_20d'] = mkt_vol.reindex(df.index.get_level_values('date')).values
        df['mkt_ret_20d'] = mkt_ret.reindex(df.index.get_level_values('date')).values

        # Fill NaNs consistently
        df['mkt_vol_20d'] = df['mkt_vol_20d'].ffill().fillna(0)
        df['mkt_ret_20d'] = df['mkt_ret_20d'].ffill().fillna(0)

        return df

    def train(self, df: pd.DataFrame, alpha_cols: List[str], cutoff_date: str = '2022-12-31', embargo_days: int = 5):
        """
        Train with regime-aware features, fixed cutoff date, and embargo.

        Args:
            df: MultiIndex DataFrame with levels ['date', 'symbol']
            alpha_cols: List of alpha feature columns
            cutoff_date: Training cutoff date (inclusive with embargo adjustment)
            embargo_days: Embargo period to avoid leakage
        """
        df = df.copy()

        # Target calculation (forward return)
        df['target_fwd_ret'] = df.groupby(level='symbol')['close'].transform(lambda x: x.pct_change(5).shift(-5))

        def get_relevance_labels(group):
            if len(group) < 5:
                return pd.Series(0, index=group.index)
            return pd.qcut(group, 5, labels=False, duplicates='drop')

        df['target_relevance'] = df.groupby(level='date')['target_fwd_ret'].transform(get_relevance_labels)

        # Prepare PIT-safe regime features
        df = self._prepare_regime_features(df)
        self.feature_cols = alpha_cols + ['mkt_vol_20d', 'mkt_ret_20d']

        # Filter valid data
        train_data = df.dropna(subset=['target_relevance'] + self.feature_cols).copy()
        train_data['target_relevance'] = train_data['target_relevance'].astype(int)

        # Fixed cutoff + embargo split
        cutoff_ts = pd.Timestamp(cutoff_date)
        embargo_ts = cutoff_ts - pd.Timedelta(days=embargo_days)

        train_df = train_data[train_data.index.get_level_values('date') <= embargo_ts].sort_index(level='date')

        if train_df.empty:
            logger.error(f"Training data is empty before {embargo_ts}")
            return

        groups = train_df.groupby(level='date').size().values
        X = train_df[self.feature_cols]
        y = train_df['target_relevance']

        # Data cleaning
        X = X.replace([np.inf, -np.inf], np.nan).fillna(0)

        # Persist winsorization boundaries
        self._winsor_lower = X.quantile(0.01)
        self._winsor_upper = X.quantile(0.99)
        X = X.clip(lower=self._winsor_lower, upper=self._winsor_upper, axis=1)

        self.model.fit(X, y, group=groups)
        self.is_trained = True
        logger.info(f"XGBoost ensemble trained. Cutoff: {cutoff_date}, Embargo: {embargo_days}d")

    def compute_ic(self, predictions: pd.Series, returns: pd.Series) -> float:
        aligned = pd.DataFrame({'pred': predictions, 'ret': returns}).dropna()
        if len(aligned) < 3:
            return 0.0
        ic = aligned['pred'].corr(aligned['ret'], method='spearman')
        return ic if not pd.isna(ic) else 0.0

    def predict(self, df: pd.DataFrame, alpha_cols: List[str]) -> pd.Series:
        """
        Predict alpha scores.

        Args:
            df: MultiIndex DataFrame with levels ['date', 'symbol']
            alpha_cols: List of alpha feature columns

        Returns:
            Series of predicted ranking scores
        """
        if not self.is_trained:
            return df[alpha_cols].mean(axis=1)

        # Ensure identical feature engineering at inference
        df = self._prepare_regime_features(df)

        X_pred = df[self.feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0)
        if self._winsor_lower is not None and self._winsor_upper is not None:
            X_pred = X_pred.clip(lower=self._winsor_lower, upper=self._winsor_upper, axis=1)

        preds = self.model.predict(X_pred)
        return pd.Series(preds, index=df.index)

    def run(self, df: pd.DataFrame, alpha_cols: List[str], cutoff_date: str = '2022-12-31', embargo_days: int = 5) -> pd.Series:
        self.train(df, alpha_cols, cutoff_date, embargo_days)
        preds = self.predict(df, alpha_cols)

        df_copy = df.copy()
        df_copy['target_fwd_ret'] = df_copy.groupby(level='symbol')['close'].transform(lambda x: x.pct_change(5).shift(-5))
        
        # PIT-safe out-of-sample IC gating to prevent look-ahead and training data leakage
        cutoff_ts = pd.Timestamp(cutoff_date)
        oos_mask = df_copy.index.get_level_values('date') > cutoff_ts
        oos_preds = preds[oos_mask]
        oos_returns = df_copy.loc[oos_mask, 'target_fwd_ret']
        
        ic = self.compute_ic(oos_preds, oos_returns)

        if ic < self.min_ic_threshold:
            logger.warning(f"OOS IC {ic:.4f} < {self.min_ic_threshold}: rejecting ensemble")
            return pd.Series(0.0, index=preds.index)

        return preds


def get_ml_alpha_scores(df: pd.DataFrame, min_ic_threshold: float = 0.15) -> pd.DataFrame:
    """
    Convenience wrapper to train ensemble, evaluate PIT IC gate, and add final alpha score.
    """
    alpha_cols = [f'alpha_{i:02d}' for i in range(1, 21)]
    ensemble = XGBoostAlphaEnsemble(min_ic_threshold=min_ic_threshold)
    ensemble.train(df, alpha_cols, embargo_days=5)
    df = df.copy()
    
    # We call run() to enforce OOS IC gating instead of predict() directly
    cutoff_date = (df.index.get_level_values('date').max() - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
    preds = ensemble.run(df, alpha_cols, cutoff_date=cutoff_date)
    df['final_alpha_score'] = preds
    return df

