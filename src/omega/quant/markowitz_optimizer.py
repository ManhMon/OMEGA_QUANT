"""Markowitz portfolio optimization for Layer 02 strategy logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy.optimize import minimize


def _ordered_assets(expected_returns: Dict[str, float]) -> List[str]:
    return sorted(expected_returns.keys())


@dataclass
class MarkowitzOptimizer:
    """Mean-variance optimizer with practical long-only constraints."""

    risk_aversion: float = 1.0
    max_weight: float = 0.2
    min_weight: float = 0.0

    def optimize(
        self,
        expected_returns: Dict[str, float],
        cov_matrix: np.ndarray,
        sectors: Optional[Dict[str, str]] = None,
        sector_caps: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """Return mean-variance optimal weights."""
        assets = _ordered_assets(expected_returns)
        mu = np.array([float(expected_returns[a]) for a in assets], dtype=float)
        cov = np.asarray(cov_matrix, dtype=float)

        n = len(assets)
        if cov.shape != (n, n):
            raise ValueError(f"cov_matrix shape {cov.shape} does not match n_assets={n}")

        bounds = [(self.min_weight, self.max_weight)] * n
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        constraints.extend(self._sector_constraints(assets, sectors, sector_caps))

        def objective(w: np.ndarray) -> float:
            return -(float(mu @ w) - 0.5 * float(self.risk_aversion) * float(w @ cov @ w))

        x0 = np.full(n, 1.0 / n)
        res = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints)
        if not res.success:
            raise ValueError(f"Optimization failed: {res.message}")
        return {a: float(res.x[i]) for i, a in enumerate(assets)}

    def min_variance(
        self,
        cov_matrix: np.ndarray,
        constraints: Optional[dict] = None,
        assets: Optional[Sequence[str]] = None,
    ) -> Dict[str, float]:
        """Return minimum variance weights.

        Args:
            cov_matrix: Covariance matrix.
            constraints: Optional dict with keys `sectors`, `sector_caps`.
            assets: Asset ordering aligned with covariance matrix.
        """
        cov = np.asarray(cov_matrix, dtype=float)
        n = cov.shape[0]
        if cov.shape[0] != cov.shape[1]:
            raise ValueError("cov_matrix must be square")

        assets_list = list(assets) if assets is not None else [f"asset_{i}" for i in range(n)]
        if len(assets_list) != n:
            raise ValueError("assets length must match cov_matrix dimension")

        sectors = (constraints or {}).get("sectors")
        sector_caps = (constraints or {}).get("sector_caps")

        bounds = [(self.min_weight, self.max_weight)] * n
        cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        cons.extend(self._sector_constraints(assets_list, sectors, sector_caps))

        def objective(w: np.ndarray) -> float:
            return float(w @ cov @ w)

        x0 = np.full(n, 1.0 / n)
        res = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=cons)
        if not res.success:
            raise ValueError(f"Min-variance optimization failed: {res.message}")
        return {a: float(res.x[i]) for i, a in enumerate(assets_list)}

    def max_sharpe(
        self,
        expected_returns: Dict[str, float],
        cov_matrix: np.ndarray,
        sectors: Optional[Dict[str, str]] = None,
        sector_caps: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """Return max Sharpe ratio weights (rf = 0)."""
        assets = _ordered_assets(expected_returns)
        mu = np.array([float(expected_returns[a]) for a in assets], dtype=float)
        cov = np.asarray(cov_matrix, dtype=float)
        n = len(assets)
        if cov.shape != (n, n):
            raise ValueError(f"cov_matrix shape {cov.shape} does not match n_assets={n}")

        bounds = [(self.min_weight, self.max_weight)] * n
        cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        cons.extend(self._sector_constraints(assets, sectors, sector_caps))

        def neg_sharpe(w: np.ndarray) -> float:
            ret = float(mu @ w)
            var = float(w @ cov @ w)
            vol = np.sqrt(max(var, 1e-12))
            return -(ret / vol)

        x0 = np.full(n, 1.0 / n)
        res = minimize(neg_sharpe, x0, method="SLSQP", bounds=bounds, constraints=cons)
        if not res.success:
            raise ValueError(f"Max-Sharpe optimization failed: {res.message}")
        return {a: float(res.x[i]) for i, a in enumerate(assets)}

    @staticmethod
    def _sector_constraints(
        assets: Sequence[str],
        sectors: Optional[Dict[str, str]],
        sector_caps: Optional[Dict[str, float]],
    ) -> List[dict]:
        if not sectors or not sector_caps:
            return []

        constraints: List[dict] = []
        for sector, cap in sector_caps.items():
            idx = [i for i, a in enumerate(assets) if sectors.get(a) == sector]
            if not idx:
                continue
            constraints.append(
                {
                    "type": "ineq",
                    "fun": lambda w, idx=idx, cap=float(cap): cap - float(np.sum(w[idx])),
                }
            )
        return constraints
