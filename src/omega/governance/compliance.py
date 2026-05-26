"""
Compliance Checker - OMEGA_QUANT Phase 8.
PIT safety, retention, and basic policy checks.
"""

import pandas as pd
from typing import Dict, Any, List

class ComplianceChecker:
    """Checks compliance rules for data and model outputs."""
    
    def check_pit_safety(self, features: pd.Series, labels: pd.Series) -> Dict[str, Any]:
        """
        Check Point-in-Time safety (no lookahead bias).
        
        Rule: features at T should not use labels/data from T+1 onward.
        """
        if len(features) != len(labels):
            return {"passed": False, "reason": "Length mismatch"}
            
        # If perfectly aligned with future labels -> potential leakage
        corr = features.corr(labels)
        
        if abs(corr) > 0.95:
            return {
                "passed": False,
                "reason": f"Potential lookahead leakage: high correlation ({corr:.4f})"
            }
            
        return {"passed": True, "reason": "PIT safety check passed"}
    
    def check_data_retention(self, data_age_days: int, max_retention_days: int = 365) -> Dict[str, Any]:
        """Check data retention policy compliance."""
        if data_age_days > max_retention_days:
            return {
                "passed": False,
                "reason": f"Data age {data_age_days} exceeds policy {max_retention_days}"
            }
            
        return {"passed": True, "reason": "Retention policy satisfied"}
