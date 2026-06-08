"""
Regime Service
Wraps regime_detector_hmm.py for market regime detection.
"""
import sys
from pathlib import Path
from typing import Dict, Optional, List
import pandas as pd
import numpy as np
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from omega.quant.regime_detector_hmm import RegimeDetectorHMM, HMMRegimeConfig

logger = logging.getLogger(__name__)


class RegimeService:
    """Service for market regime detection"""
    
    def __init__(self, n_components: int = 3):
        self.config = HMMRegimeConfig(n_components=n_components)
        self.detector = RegimeDetectorHMM(self.config)
        self.is_fitted = False
    
    def fit(
        self,
        features_df: pd.DataFrame,
        target_returns: Optional[pd.Series] = None
    ) -> bool:
        """
        Fit regime detector on historical data
        
        Args:
            features_df: DataFrame with columns ['returns', 'volatility', 'volume_change']
            target_returns: Optional returns for regime mapping
            
        Returns:
            True if fitting successful
        """
        # Input validation
        if features_df is None:
            logger.error("features_df is None")
            return False
        
        if features_df.empty:
            logger.error("features_df is empty")
            return False
        
        # Check minimum sample size
        MIN_SAMPLES = 100
        if len(features_df) < MIN_SAMPLES:
            logger.error(f"Insufficient samples: {len(features_df)} < {MIN_SAMPLES}")
            return False
        
        # Check required columns
        required_columns = ['returns', 'volatility', 'volume_change']
        missing_columns = [col for col in required_columns if col not in features_df.columns]
        if missing_columns:
            logger.error(f"Missing required columns: {missing_columns}")
            return False
        
        try:
            self.detector.fit(features_df, target_returns)
            self.is_fitted = True
            logger.info(f"Regime detector fitted successfully on {len(features_df)} samples")
            return True
        except Exception as e:
            logger.error(f"Regime fitting failed: {e}")
            self.is_fitted = False
            return False
    
    def predict_current_regime(self, features_df: pd.DataFrame) -> str:
        """
        Predict current market regime
        
        Args:
            features_df: DataFrame with current features (single row)
            
        Returns:
            Regime label ('Bull', 'Sideways', 'Bear')
        """
        if not self.is_fitted:
            logger.warning("Regime detector not fitted, defaulting to Sideways")
            return 'Sideways'
        
        try:
            regime = self.detector.predict_regime(features_df)
            return regime
        except Exception as e:
            logger.error(f"Regime prediction failed: {e}")
            return 'Sideways'
    
    def get_dampening_factor(self, regime: str) -> float:
        """
        Get dampening factor for regime
        
        Args:
            regime: Regime label
            
        Returns:
            Dampening factor (1.0 for Bull/Sideways, 0.3 for Bear)
        """
        return self.detector.get_dampening_factor(regime)
    
    def get_regime_mapping(self) -> Dict[int, str]:
        """Get mapping from state ID to regime label"""
        return self.detector.regime_map if self.is_fitted else {}
    
    def compute_regime_statistics(
        self,
        features_df: pd.DataFrame,
        returns: pd.Series
    ) -> Optional[Dict]:
        """
        Compute statistics for each regime
        
        Args:
            features_df: Historical features
            returns: Historical returns
            
        Returns:
            Dict with regime statistics
        """
        if not self.is_fitted:
            return None
        
        try:
            # Predict regimes for all historical data
            X = features_df[self.config.features].values
            X_scaled = (X - self.detector.feature_means_) / self.detector.feature_stds_
            states = self.detector.model.predict(X_scaled)
            
            df_regimes = pd.DataFrame({
                'state': states,
                'returns': returns.values
            })
            df_regimes['regime'] = df_regimes['state'].map(self.detector.regime_map).fillna('Unknown')
            
            # Group by regime to compute statistics in a single vectorized aggregation
            agg_df = df_regimes.groupby('regime')['returns'].agg(
                count='count',
                mean='mean',
                std='std'
            ).reindex(['Bull', 'Sideways', 'Bear']).fillna(0.0)
            
            # Vectorized arithmetic
            total_count = len(df_regimes) if len(df_regimes) > 0 else 1
            agg_df['frequency'] = agg_df['count'] / total_count
            std_mask = agg_df['std'] > 0
            agg_df['sharpe'] = 0.0
            agg_df.loc[std_mask, 'sharpe'] = (agg_df.loc[std_mask, 'mean'] / agg_df.loc[std_mask, 'std']) * np.sqrt(252)
            
            # Convert to the structured dict expected by callers
            stats = {
                regime: {
                    "count": int(data['count']),
                    "frequency": float(data['frequency']),
                    "mean_return": float(data['mean']),
                    "std_return": float(data['std']),
                    "sharpe": float(data['sharpe'])
                }
                for regime, data in agg_df.to_dict('index').items()
            }
            
            return stats
        except Exception as e:
            logger.error(f"Regime statistics failed: {e}")
            return None
    
    def get_regime_timeline(
        self,
        features_df: pd.DataFrame
    ) -> Optional[List[Dict]]:
        """
        Get regime timeline for visualization
        
        Args:
            features_df: Historical features with datetime index
            
        Returns:
            List of dicts with date and regime
        """
        if not self.is_fitted:
            return None
        
        try:
            X = features_df[self.config.features].values
            X_scaled = (X - self.detector.feature_means_) / self.detector.feature_stds_
            states = self.detector.model.predict(X_scaled)
            
            df_timeline = pd.DataFrame({
                "date": features_df.index,
                "state_id": states
            })
            df_timeline["regime"] = df_timeline["state_id"].map(self.detector.regime_map).fillna('Unknown')
            df_timeline["state_id"] = df_timeline["state_id"].astype(int)
            
            return df_timeline.to_dict('records')
        except Exception as e:
            logger.error(f"Regime timeline failed: {e}")
            return None
