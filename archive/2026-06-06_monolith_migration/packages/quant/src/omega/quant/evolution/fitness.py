"""
Fitness Evaluator for Genetic Programming Alpha Discovery - OMEGA_QUANT Phase 3.4
Sharpe Ratio, Turnover Penalty, Complexity Penalty, Combined Fitness Calculation.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional


class FitnessEvaluator:
    """
    Evaluate fitness of evolved alpha signals.

    Fitness = Sharpe Ratio - 0.1 * Turnover - 0.01 * TreeDepth

    This penalizes high-turnover and complex strategies while rewarding risk-adjusted returns.
    """

    def __init__(self, risk_free_rate: float = 0.0, complexity_weight: float = 0.01):
        """
        Args:
            risk_free_rate: Annualized risk-free rate (default 0.0)
            complexity_weight: Penalty weight for tree depth (default 0.01)
        """
        self.rf = risk_free_rate
        self.complexity_weight = complexity_weight

    def calculate_turnover(self, positions: pd.Series) -> float:
        """
        Calculate average daily turnover.
        """
        if len(positions) < 2:
            return 0.0
        diff = positions.diff().abs()
        return float(diff.mean())

    def calculate_sharpe(self, returns: pd.Series) -> float:
        """
        Calculate annualized Sharpe ratio.
        """
        valid = returns.dropna()
        if valid.empty:
            return 0.0

        excess_returns = valid - self.rf
        std = excess_returns.std(ddof=1)

        if std == 0.0 or np.isnan(std):
            return 0.0

        sharpe = (excess_returns.mean() / std) * np.sqrt(252)
        return float(sharpe)

    def evaluate(self, signal: pd.Series, forward_returns: pd.Series, tree_depth: int = 0) -> float:
        """
        Evaluate combined fitness: Sharpe - 0.1 * Turnover - 0.01 * TreeDepth
        """
        # MANDATORY PIT GUARD: Ensure signal is shifted (T-1)
        # Even if genetic_alpha.py shifts it, we shift here for defense-in-depth
        safe_signal = signal.shift(1).fillna(0.0)

        # Align indices
        aligned = pd.DataFrame({
            'signal': safe_signal,
            'returns': forward_returns
        }).dropna()

        if len(aligned) < 2:
            return -999.0

        signal_clean = aligned['signal']
        returns_clean = aligned['returns']

        # Calculate positions from signals
        positions = np.sign(signal_clean)

        # Strategy returns = positions * forward returns
        strat_returns = positions * returns_clean

        # Calculate metrics
        sharpe = self.calculate_sharpe(strat_returns)
        turnover = self.calculate_turnover(positions)

        # Combined fitness with complexity penalty
        complexity_penalty = self.complexity_weight * tree_depth
        fitness = sharpe - 0.1 * turnover - complexity_penalty

        # Handle edge cases
        if np.isnan(fitness) or np.isinf(fitness):
            return -999.0

        return float(fitness)

    def evaluate_batch(self, signals: pd.DataFrame, forward_returns: pd.Series, tree_depths: Optional[pd.Series] = None) -> pd.Series:
        """
        Evaluate fitness for multiple signals without loops.
        """
        # MANDATORY PIT GUARD
        safe_signals = signals.shift(1).fillna(0.0)
        
        # Calculate positions
        positions = np.sign(safe_signals)
        
        # Strategy returns (broadcasted)
        strat_returns = positions.mul(forward_returns, axis=0)
        
        # Annualized Sharpe (vectorized across columns)
        excess_returns = strat_returns - self.rf
        mean_ret = excess_returns.mean()
        std_ret = excess_returns.std(ddof=1)
        sharpe = (mean_ret / std_ret.replace(0, np.nan)) * np.sqrt(252)
        sharpe = sharpe.fillna(0.0)
        
        # Turnover (vectorized across columns)
        turnover = positions.diff().abs().mean()
        
        # Tree depths
        depths = tree_depths if tree_depths is not None else pd.Series(0, index=signals.columns)
        
        # Combined fitness
        fitness = sharpe - 0.1 * turnover - (self.complexity_weight * depths)
        
        # Handle failures (NaN signal/returns alignment)
        valid_mask = (signals.count() >= 2)
        fitness[~valid_mask] = -999.0
        
        return fitness.fillna(-999.0)
