#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Advanced ML Metrics for OMEGA_QUANT Model Registry
- IC Decay Half-life
- Marginal Sharpe Contribution
- Market Regime Stability (Bull/Bear/Sideways using VN-Index Volatility)

Author: ML Engineer (Role 16)
Date: 2026-05-24
"""

import numpy as np
import pandas as pd
from typing import Dict, Any

class AdvancedMetricsEngine:
    @staticmethod
    def compute_ic_decay(daily_ics: list[float]) -> float:
        """Estimate the half-life of Information Coefficient (IC) in days."""
        if len(daily_ics) < 10:
            return 0.0
        
        # Simple exponential decay fit
        y = np.array(daily_ics)
        x = np.arange(len(y))
        
        # log(y) = log(A) - lambda * x
        # Ensure positive for log
        y_safe = np.maximum(y, 1e-6)
        try:
            coeffs = np.polyfit(x, np.log(y_safe), 1)
            decay_lambda = -coeffs[0]
            if decay_lambda <= 0:
                return float('inf') # Stable
            half_life = np.log(2) / decay_lambda
            return min(float(half_life), 365.0)
        except Exception:
            return 0.0

    @staticmethod
    def identify_market_regime(returns: pd.Series) -> str:
        """
        Identify market regime based on 20-day returns and volatility.
        """
        if len(returns) < 20:
            return "UNKNOWN"
            
        ret_20d = returns.sum()
        vol_20d = returns.std() * np.sqrt(252) # Annualized
        
        if ret_20d > 0.05 and vol_20d < 0.15:
            return "BULL"
        elif ret_20d < -0.05:
            return "BEAR"
        elif vol_20d > 0.25:
            return "HIGH_VOL"
        else:
            return "SIDEWAYS"

    @staticmethod
    def evaluate_model_regime_stability(model_returns_by_regime: Dict[str, list[float]]) -> float:
        """
        Calculate stability score across different market regimes.
        1.0 means perfectly stable performance regardless of regime.
        """
        sharpes = []
        for regime, rets in model_returns_by_regime.items():
            if len(rets) > 5:
                mean_ret = np.mean(rets)
                std_ret = np.std(rets)
                if std_ret > 0:
                    sharpes.append(mean_ret / std_ret)
                    
        if not sharpes:
            return 0.0
            
        # Coefficient of variation of Sharpe across regimes
        cv = np.std(sharpes) / (np.mean(sharpes) + 1e-6)
        stability = max(0.0, 1.0 - cv)
        return float(stability)