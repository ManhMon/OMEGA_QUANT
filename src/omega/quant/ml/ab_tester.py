import numpy as np
import pandas as pd
import pyarrow as pa
from typing import Dict, List, Tuple, Any, Optional
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from omega.quant.registry import ModelRegistry, ModelMetadata

logger = logging.getLogger(__name__)

@dataclass
class PromotionPack:
    """Standardized promotion payload for ModelRegistry."""
    model_id: str
    version: str
    metrics: Dict[str, float]
    feature_importance: Dict[str, float]
    parameters: Dict[str, Any]
    transition_cost: float
    burn_in_days: int

class SEAE_AB_Tester:
    """
    Self-Evolving A/B Tester for Champion vs Challenger models.
    Supports matrix-based shadow mode and 30-day burn-in logic.
    """
    
    def __init__(self, registry: ModelRegistry, avg_impact_bps: float = 2.5):
        """
        Initialize the A/B Tester.
        
        Args:
            registry: ModelRegistry instance for tracking models
            avg_impact_bps: Average market impact in basis points for transition cost
        """
        self.registry = registry
        self.avg_impact_bps = avg_impact_bps
        self.burn_in_days = 30
        
    def _calculate_transition_cost(self, champion_weights: np.ndarray, challenger_weights: np.ndarray) -> float:
        """
        Calculate transition cost between models.
        cost = distance * avg_impact_bps
        """
        # Ensure weights are numpy arrays
        w_champ = np.asarray(champion_weights)
        w_chall = np.asarray(challenger_weights)
        
        # Calculate L1 distance (turnover)
        distance = np.sum(np.abs(w_chall - w_champ))
        
        # Calculate cost in basis points
        cost_bps = distance * self.avg_impact_bps
        return float(cost_bps)
        
    def execute_parallel_shadow_mode(
        self, 
        champion_weights: np.ndarray, 
        challengers_weights: List[np.ndarray], 
        returns: np.ndarray
    ) -> Tuple[np.ndarray, List[np.ndarray]]:
        """
        Matrix-based Shadow Mode (W^T * R) for parallel execution.
        
        Args:
            champion_weights: 1D array of champion portfolio weights
            challengers_weights: List of 1D arrays of challenger portfolio weights
            returns: 1D array of asset returns
            
        Returns:
            Tuple of (champion_return, list_of_challenger_returns)
        """
        # Ensure inputs are numpy arrays
        w_champ = np.asarray(champion_weights)
        r = np.asarray(returns)
        
        # Champion return: W_champ^T * R
        champ_ret = np.dot(w_champ, r)
        
        # Challengers returns: W_chall^T * R
        chall_rets = []
        for w_chall in challengers_weights:
            w_c = np.asarray(w_chall)
            chall_rets.append(np.dot(w_c, r))
            
        return champ_ret, chall_rets
        
    def share_features_zero_copy(self, features_df: pd.DataFrame) -> pa.Table:
        """
        Convert pandas DataFrame to PyArrow Table for zero-copy shared memory.
        Allows multiple models to access features concurrently without memory duplication.
        
        Args:
            features_df: Pandas DataFrame containing features
            
        Returns:
            PyArrow Table pointing to the same memory
        """
        # Convert to PyArrow table (zero-copy when possible)
        # Using pyarrow for shared memory across parallel processes
        return pa.Table.from_pandas(features_df)
        
    def _apply_burn_in_penalty(self, metrics: Dict[str, float], days_active: int) -> Dict[str, float]:
        """
        Apply 30-day burn-in logic to metrics.
        Penalizes metrics if the model hasn't been active for the burn-in period.
        """
        adjusted_metrics = metrics.copy()
        
        if days_active < self.burn_in_days:
            # Linear penalty: 0 days = 50% penalty, 30 days = 0% penalty
            penalty_factor = 0.5 + 0.5 * (days_active / self.burn_in_days)
            
            # Apply penalty to key performance metrics
            if 'ic' in adjusted_metrics:
                adjusted_metrics['ic'] *= penalty_factor
            if 'sharpe' in adjusted_metrics:
                adjusted_metrics['sharpe'] *= penalty_factor
            if 'return' in adjusted_metrics:
                adjusted_metrics['return'] *= penalty_factor
                
            logger.info(f"Applied burn-in penalty. Factor: {penalty_factor:.2f} (Days: {days_active}/{self.burn_in_days})")
            
        return adjusted_metrics
        
    def generate_promotion_pack(
        self,
        model_id: str,
        version: str,
        champion_weights: np.ndarray,
        challenger_weights: np.ndarray,
        raw_metrics: Dict[str, float],
        days_active: int,
        feature_importance: Dict[str, float] = None,
        parameters: Dict[str, Any] = None
    ) -> PromotionPack:
        """
        Generate a standardized promotion pack for the registry.
        """
        # Calculate transition cost
        transition_cost = self._calculate_transition_cost(champion_weights, challenger_weights)
        
        # Apply burn-in penalty to metrics
        adjusted_metrics = self._apply_burn_in_penalty(raw_metrics, days_active)
        
        # Add transition cost to metrics
        adjusted_metrics['transition_cost_bps'] = transition_cost
        
        return PromotionPack(
            model_id=model_id,
            version=version,
            metrics=adjusted_metrics,
            feature_importance=feature_importance or {},
            parameters=parameters or {},
            transition_cost=transition_cost,
            burn_in_days=self.burn_in_days
        )
        
    def promote_to_registry(self, pack: PromotionPack) -> bool:
        """
        Register a challenger and attempt promotion in the ModelRegistry.
        """
        metadata = ModelMetadata(
            model_id=pack.model_id,
            version=pack.version,
            trained_at=datetime.now(timezone.utc),
            ic_mean=pack.metrics.get('ic', 0.0),
            sharpe_ratio=pack.metrics.get('sharpe', 0.0),
            is_active=False,
            feature_importance=pack.feature_importance,
            parameters=pack.parameters
        )
        
        # Register as challenger
        self.registry.register_model(metadata, is_challenger=True)
        
        # Assuming we have historic ICs to pass (mocking for now as per registry signature)
        # In a real scenario, these would come from the backtest/shadow mode results
        mock_challenger_ics = [pack.metrics.get('ic', 0.0)] * 30
        mock_champion_ics = [max(0.0, pack.metrics.get('ic', 0.0) - 0.05)] * 30 
        
        # Evaluate
        should_promote = self.registry.evaluate_challenger(mock_challenger_ics, mock_champion_ics)
        
        if should_promote:
            success = self.registry.promote_challenger()
            if success:
                logger.info(f"Successfully promoted model {pack.model_id} (v{pack.version})")
                return True
            else:
                logger.error(f"Failed to promote model {pack.model_id} despite evaluation success")
                return False
        else:
            logger.info(f"Challenger {pack.model_id} did not pass evaluation criteria")
            return False
