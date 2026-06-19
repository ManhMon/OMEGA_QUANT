"""
Position Sizer - V21 Institutional
Converts signals into position weights using Risk Parity, Kelly Criterion, and Markowitz Optimization.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np


@dataclass
class PositionConfig:
    """Configuration for position sizing."""
    method: str = "risk_parity"         # "risk_parity" | "equal_weight" | "kelly" | "markowitz"
    use_markowitz: bool = False         # Enable Markowitz optimization
    kelly_fraction: float = 0.25        # Fractional Kelly (conservative)
    max_position: float = 0.15          # Max weight per stock
    min_position: float = 0.01          # Min weight per stock
    cash_reserve: float = 0.05          # Cash buffer (5%)
    gross_exposure_cap: float = 0.95    # Max gross exposure
    risk_aversion: float = 1.0          # Risk aversion for Markowitz (higher = more conservative)
    markowitz_mode: str = "max_sharpe" # "max_sharpe" | "min_variance" | "mean_variance"


@dataclass
class TargetPortfolio:
    """Target portfolio output."""
    weights: Dict[str, float]           # symbol -> weight
    shares: Dict[str, int]              # symbol -> shares (board lot)
    cash_weight: float
    metadata: Dict

    def get_symbol_weights(self) -> Dict[str, float]:
        """Helper for RiskManager compatibility."""
        return self.weights

    def get_sector_weights(self) -> Dict[str, float]:
        """Helper for RiskManager compatibility."""
        return self.metadata.get("sector_weights", {})

    def get_order_sizes(self) -> Dict[str, float]:
        """Helper for RiskManager compatibility."""
        return {s: abs(v) for s, v in self.shares.items()}

    def get_adv_data(self) -> Dict[str, float]:
        """Helper for RiskManager compatibility."""
        return self.metadata.get("adv_data", {})

    def get_returns_data(self) -> Dict[str, List[float]]:
        """Helper for RiskManager compatibility."""
        return self.metadata.get("returns_data", {})

    def get_equity_curve(self) -> List[float]:
        """Helper for RiskManager compatibility."""
        return self.metadata.get("equity_curve", [])


class PositionSizer:
    """Converts signals to portfolio weights.

    Methods:
    - Risk Parity: Weight inversely proportional to volatility
    - Alpha Risk Parity: Weight proportional to max(score,0) * (1/volatility)
    - Fractional Kelly: Based on win-rate and payoff ratio
    - Equal Weight: Simple equal allocation
    """

    def __init__(self, config: Optional[PositionConfig] = None):
        self.config = config or PositionConfig()

    def _risk_parity_weights(
        self,
        symbols: List[str],
        volatilities: Dict[str, float]
    ) -> Dict[str, float]:
        """Compute risk parity weights (1/volatility).

        Args:
            symbols: List of symbols
            volatilities: Volatility per symbol

        Returns:
            Normalized weights
        """
        inv_vols = {}
        for sym in symbols:
            vol = volatilities.get(sym, 1.0)
            inv_vols[sym] = 1.0 / max(vol, 1e-10)

        total = sum(inv_vols.values())
        if total == 0:
            return {s: 1.0 / len(symbols) for s in symbols}

        return {s: v / total for s, v in inv_vols.items()}

    def _kelly_weights(
        self,
        symbols: List[str],
        win_rates: Dict[str, float],
        payoff_ratios: Dict[str, float]
    ) -> Dict[str, float]:
        """Compute fractional Kelly weights.

        Args:
            symbols: List of symbols
            win_rates: Win probability per symbol
            payoff_ratios: Avg win / avg loss per symbol

        Returns:
            Normalized weights
        """
        kelly_fractions = {}
        for sym in symbols:
            p = win_rates.get(sym, 0.5)
            b = payoff_ratios.get(sym, 1.0)
            # Kelly formula: f = (p*b - (1-p)) / b
            kelly = (p * b - (1 - p)) / max(b, 1e-10)
            # Apply fractional Kelly (conservative)
            kelly_fractions[sym] = max(0.0, kelly * self.config.kelly_fraction)

        total = sum(kelly_fractions.values())
        if total == 0:
            return {s: 1.0 / len(symbols) for s in symbols}

        return {s: v / total for s, v in kelly_fractions.items()}

    def _apply_constraints(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Apply position constraints (min/max, gross exposure cap).

        Args:
            weights: Raw weights

        Returns:
            Constrained weights
        """
        # Apply min/max
        constrained = {
            s: min(self.config.max_position, max(self.config.min_position, w))
            for s, w in weights.items()
        }

        # Apply gross exposure cap
        total = sum(constrained.values())
        if total > self.config.gross_exposure_cap:
            scale = self.config.gross_exposure_cap / total
            constrained = {s: w * scale for s, w in constrained.items()}

        return constrained

    def build_from_weights(
        self,
        symbols: List[str],
        weights: Dict[str, float],
        *,
        capital: float,
        prices: Dict[str, float],
        skip_constraints: bool = False,
    ) -> TargetPortfolio:
        """Build TargetPortfolio from provided weights (apply cash reserve & board-lot rounding)."""
        if not symbols:
            return TargetPortfolio(weights={}, shares={}, cash_weight=1.0, metadata={})

        # Apply constraints (skip if already handled by optimizer)
        if not skip_constraints:
            weights = self._apply_constraints(weights)

        # Reserve cash buffer
        investable = 1.0 - self.config.cash_reserve
        weights = {s: weights.get(s, 0.0) * investable for s in symbols}
        cash_weight = 1.0 - sum(weights.values())

        shares: Dict[str, int] = {}
        board_lot = 100
        for sym in symbols:
            price = float(prices.get(sym, 0.0))
            if price <= 0:
                shares[sym] = 0
                continue
            allocation = float(capital) * float(weights.get(sym, 0.0))
            raw_shares = int(allocation / price)
            shares[sym] = (raw_shares // board_lot) * board_lot

        return TargetPortfolio(
            weights=weights,
            shares=shares,
            cash_weight=cash_weight,
            metadata={
                "method": self.config.method,
                "n_positions": len(symbols),
                "gross_exposure": sum(weights.values()),
            },
        )

    def compute(
        self,
        symbols: List[str],
        scores: Dict[str, float],
        volatilities: Dict[str, float],
        capital: float,
        prices: Dict[str, float],
        win_rates: Optional[Dict[str, float]] = None,
        payoff_ratios: Optional[Dict[str, float]] = None,
        returns_history: Optional[Dict[str, np.ndarray]] = None,
        sectors: Optional[Dict[str, str]] = None,
        sector_caps: Optional[Dict[str, float]] = None,
    ) -> TargetPortfolio:
        """Compute target portfolio.

        Args:
            symbols: Selected universe
            scores: Ensemble AI scores
            volatilities: Realized volatilities
            capital: Total capital (VND)
            prices: Current prices per symbol
            win_rates: Historical win rates (for Kelly)
            payoff_ratios: Historical payoff ratios (for Kelly)
            returns_history: Raw historical returns for covariance estimation
            sectors: Symbol to sector mapping
            sector_caps: Sector name to max weight mapping

        Returns:
            TargetPortfolio with weights and shares
        """
        if not symbols:
            return TargetPortfolio(weights={}, shares={}, cash_weight=1.0, metadata={})

        # Institutional Mode: Markowitz Optimization
        if self.config.use_markowitz and returns_history:
            from omega.quant.portfolio.covariance import CovarianceEstimator
            from omega.quant.portfolio.markowitz import MarkowitzOptimizer

            # 1. Estimate robust covariance
            estimator = CovarianceEstimator()
            cov_matrix = estimator.fit(returns_history)

            # 2. Optimize
            optimizer = MarkowitzOptimizer(
                risk_aversion=self.config.risk_aversion,
                max_weight=self.config.max_position,
                min_weight=self.config.min_position
            )

            # Order assets for optimizer
            assets = sorted(symbols)
            
            if self.config.markowitz_mode == "max_sharpe":
                weights = optimizer.max_sharpe(scores, cov_matrix, sectors, sector_caps)
            elif self.config.markowitz_mode == "min_variance":
                weights = optimizer.min_variance(cov_matrix, assets=assets, constraints={"sectors": sectors, "sector_caps": sector_caps})
            else:
                weights = optimizer.optimize(scores, cov_matrix, sectors, sector_caps)

            return self.build_from_weights(symbols, weights, capital=capital, prices=prices, skip_constraints=True)

        # Legacy methods
        elif self.config.method == "risk_parity":
            weights = self._risk_parity_weights(symbols, volatilities)
        elif self.config.method == "alpha_risk_parity":
            # Combine alpha strength with risk parity
            raw: Dict[str, float] = {}
            for sym in symbols:
                alpha = max(0.0, float(scores.get(sym, 0.0)))
                vol = float(volatilities.get(sym, 1.0))
                raw[sym] = alpha * (1.0 / max(vol, 1e-10))
            sraw = sum(raw.values())
            weights = {s: (raw[s] / sraw if sraw > 0 else 1.0 / len(symbols)) for s in symbols}
        elif self.config.method == "kelly" and win_rates and payoff_ratios:
            weights = self._kelly_weights(symbols, win_rates, payoff_ratios)
        else:
            # Equal weight fallback
            weights = {s: 1.0 / len(symbols) for s in symbols}

        return self.build_from_weights(symbols, weights, capital=capital, prices=prices)

