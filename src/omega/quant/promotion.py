import datetime
from typing import Dict, Any, List

class PromotionGate:
    def __init__(self):
        self.models: Dict[str, Dict[str, Any]] = {}
        self.valid_tiers = ["Paper", "Shadow", "Production"]

    def evaluate_model(self, metrics: Dict[str, float], criteria: Dict[str, float]) -> bool:
        """
        Check IC/Sharpe/MDD thresholds.
        """
        # IC and Sharpe should be >= criteria
        if 'IC' in criteria and metrics.get('IC', -float('inf')) < criteria['IC']:
            return False
        if 'Sharpe' in criteria and metrics.get('Sharpe', -float('inf')) < criteria['Sharpe']:
            return False
        # MDD should be <= criteria (assuming positive MDD means max drawdown magnitude)
        if 'MDD' in criteria and metrics.get('MDD', float('inf')) > criteria['MDD']:
            return False
            
        return True

    def apply_embargo(self, model_date: datetime.datetime, current_date: datetime.datetime, horizon: int) -> bool:
        """
        Enforce strict embargo period (T+horizon+1).
        """
        embargo_end = model_date + datetime.timedelta(days=horizon + 1)
        return current_date >= embargo_end

    def promote_to_tier(self, model_id: str, tier: str, current_date: datetime.datetime, available_at: datetime.datetime, horizon: int) -> bool:
        """
        Transition through Shadow -> Production. Enforce PIT: strict embargo validation and available_at checks.
        """
        if tier not in self.valid_tiers:
            raise ValueError(f"Invalid tier: {tier}")
            
        # Enforce PIT: available_at check
        if current_date < available_at:
            return False
            
        # Enforce strict embargo
        if not self.apply_embargo(available_at, current_date, horizon):
            return False
            
        if model_id not in self.models:
            self.models[model_id] = {"tier": "Paper"}
            
        current_tier = self.models[model_id]["tier"]
        
        # Valid transitions: Paper -> Shadow -> Production
        if current_tier == "Paper" and tier == "Shadow":
            self.models[model_id]["tier"] = tier
            return True
        elif current_tier == "Shadow" and tier == "Production":
            self.models[model_id]["tier"] = tier
            return True
        elif current_tier == tier:
            return True
            
        return False
