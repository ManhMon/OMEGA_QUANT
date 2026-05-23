"""
Portfolio Construction Engine - Institutional Grade

Implements advanced portfolio construction methods:
1. Equal Risk Contribution (ERC) - Risk budgeting
2. Risk Parity - Equal risk per asset
3. Factor Exposure Targeting - Multi-factor construction
4. Hierarchical Risk Parity (HRP) - Clustering-based construction
5. PIT-safe operations with T-1 lag enforcement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform

from src.portfolio.optimizer import OptimizationResult, OptimizationMethod


class ConstructionMethod(Enum):
    """Supported construction methods."""
    ERC = "equal_risk_contribution"
    RISK_PARITY = "risk_parity"
    FACTOR_TARGETING = "factor_targeting"
    HRP = "hierarchical_risk_parity"


class PortfolioConstructionEngine:
    """
    Institutional-grade portfolio construction engine.

    Features:
    - Equal Risk Contribution (ERC) budgeting
    - Risk Parity construction
    - Multi-factor exposure targeting
    - Hierarchical Risk Parity (HRP)
    - PIT safety (T-1 lag enforcement via build_portfolio_at_date)
    """

    def __init__(
        self,
        risk_free_rate: float = 0.05,
        max_iterations: int = 1000,
        tolerance: float = 1e-8,
    ):
        self.risk_free_rate = risk_free_rate
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    def _build_erc_portfolio(
        self,
        symbols: List[str],
        covariance_matrix: np.ndarray,
        max_position: float = 0.25,
        sector_map: Optional[Dict[str, str]] = None,
        max_sector: float = 0.40,
    ) -> OptimizationResult:
        n = len(symbols)
        cov = covariance_matrix

        def objective(w: np.ndarray) -> float:
            port_vol = np.sqrt(np.dot(w, np.dot(cov, w)))
            if port_vol < 1e-10:
                return 1e10
            mrc = np.dot(cov, w) / port_vol
            rc = w * mrc
            target_rc = port_vol / n
            return np.sum((rc - target_rc) ** 2)

        cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

        if sector_map:
            sectors = sorted(set(sector_map.values()))
            symbol_arr = np.array(symbols)
            for sector in sectors:
                sector_mask = np.array([sector_map.get(sym) == sector for sym in symbol_arr], dtype=float)
                if np.any(sector_mask):
                    cons.append(
                        {
                            "type": "ineq",
                            "fun": lambda w, m=sector_mask: max_sector - np.dot(w, m),
                        }
                    )

        bounds = [(0.0, max_position) for _ in range(n)]
        w0 = np.ones(n) / n

        result = minimize(
            objective,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"maxiter": self.max_iterations, "ftol": self.tolerance},
        )

        weights_array = result.x
        weights_dict = {symbols[i]: float(weights_array[i]) for i in range(n)}
        port_vol = np.sqrt(np.dot(weights_array, np.dot(cov, weights_array)))

        weights_sum = np.sum(weights_array)
        bounds_satisfied = bool(np.all((-1e-6 <= weights_array) & (weights_array <= max_position + 1e-6)))
        sum_constraint_satisfied = abs(weights_sum - 1.0) < 1e-3
        converged = result.success or (sum_constraint_satisfied and bounds_satisfied)

        return OptimizationResult(
            weights=weights_dict,
            expected_return=0.0,
            expected_volatility=float(port_vol),
            sharpe_ratio=0.0,
            method=OptimizationMethod.RISK_PARITY,
            converged=converged,
            message="ERC portfolio constructed successfully" if converged else result.message,
        )

    def _build_factor_targeted_portfolio(
        self,
        symbols: List[str],
        factor_exposures: pd.DataFrame,
        target_exposures: Dict[str, float],
        max_position: float = 0.25,
        expected_returns: Optional[Dict[str, float]] = None,
        covariance_matrix: Optional[np.ndarray] = None,
        sector_map: Optional[Dict[str, str]] = None,
        max_sector: float = 0.40,
    ) -> OptimizationResult:
        n = len(symbols)
        factor_matrix = factor_exposures.loc[symbols].values

        def objective(w: np.ndarray) -> float:
            current_exposures = np.dot(w, factor_matrix)
            targets = np.array([target_exposures.get(f, 0.0) for f in factor_exposures.columns])
            return np.sum((current_exposures - targets) ** 2)

        cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

        if sector_map:
            sectors = sorted(set(sector_map.values()))
            symbol_arr = np.array(symbols)
            for sector in sectors:
                sector_mask = np.array([sector_map.get(sym) == sector for sym in symbol_arr], dtype=float)
                if np.any(sector_mask):
                    cons.append(
                        {
                            "type": "ineq",
                            "fun": lambda w, m=sector_mask: max_sector - np.dot(w, m),
                        }
                    )

        bounds = [(0.0, max_position) for _ in range(n)]
        w0 = np.ones(n) / n

        result = minimize(
            objective,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"maxiter": self.max_iterations, "ftol": self.tolerance},
        )

        weights_array = result.x
        weights_dict = {symbols[i]: float(weights_array[i]) for i in range(n)}

        port_return = 0.0
        port_vol = 0.0
        sharpe = 0.0

        if expected_returns:
            mu = np.array([expected_returns.get(s, 0.0) for s in symbols])
            port_return = float(np.dot(weights_array, mu))

        if covariance_matrix is not None:
            port_vol = float(np.sqrt(np.dot(weights_array, np.dot(covariance_matrix, weights_array))))
            if port_vol > 0:
                sharpe = (port_return - self.risk_free_rate) / port_vol

        weights_sum = np.sum(weights_array)
        bounds_satisfied = bool(np.all((-1e-6 <= weights_array) & (weights_array <= max_position + 1e-6)))
        sum_constraint_satisfied = abs(weights_sum - 1.0) < 1e-3
        converged = result.success or (sum_constraint_satisfied and bounds_satisfied)

        return OptimizationResult(
            weights=weights_dict,
            expected_return=port_return,
            expected_volatility=port_vol,
            sharpe_ratio=sharpe,
            method=OptimizationMethod.MVO,
            converged=converged,
            message="Factor-targeted portfolio constructed" if converged else result.message,
        )

    def _get_cluster_variance(self, cov: np.ndarray, cluster: List[int]) -> float:
        sub_cov = cov[np.ix_(cluster, cluster)]
        inv_diag = 1.0 / np.diag(sub_cov)
        ivp = inv_diag / np.sum(inv_diag)
        return float(np.dot(ivp, np.dot(sub_cov, ivp)))

    def _build_linkage_clusters(self, linkage_matrix: np.ndarray, n_assets: int) -> Dict[int, List[int]]:
        clusters = {i: [i] for i in range(n_assets)}
        for i, row in enumerate(linkage_matrix):
            left, right = int(row[0]), int(row[1])
            clusters[n_assets + i] = clusters[left] + clusters[right]
        return clusters

    def _bisect_tree(self, cov: np.ndarray, linkage_matrix: np.ndarray, n_assets: int) -> np.ndarray:
        clusters = self._build_linkage_clusters(linkage_matrix, n_assets)
        root_id = n_assets + linkage_matrix.shape[0] - 1

        weights = np.ones(n_assets)

        def recurse(cluster_id: int) -> None:
            if cluster_id < n_assets:
                return

            row = linkage_matrix[cluster_id - n_assets]
            left_id, right_id = int(row[0]), int(row[1])

            left_cluster = clusters[left_id]
            right_cluster = clusters[right_id]

            left_var = self._get_cluster_variance(cov, left_cluster)
            right_var = self._get_cluster_variance(cov, right_cluster)

            denom = left_var + right_var
            alpha = 0.5 if denom <= 1e-12 else 1.0 - (left_var / denom)

            weights[left_cluster] *= alpha
            weights[right_cluster] *= (1.0 - alpha)

            recurse(left_id)
            recurse(right_id)

        recurse(root_id)
        return weights

    def _build_hrp_portfolio(
        self,
        symbols: List[str],
        covariance_matrix: np.ndarray,
        correlation_matrix: np.ndarray,
        max_position: float = 0.25,
        sector_map: Optional[Dict[str, str]] = None,
        max_sector: float = 0.40,
    ) -> OptimizationResult:
        n = len(symbols)

        distance_matrix = np.sqrt(0.5 * (1.0 - np.clip(correlation_matrix, -1.0, 1.0)))
        condensed_dist = squareform(distance_matrix, checks=False)
        linkage_matrix = linkage(condensed_dist, method="ward")

        hrp_weights = self._bisect_tree(covariance_matrix, linkage_matrix, n)
        hrp_weights = hrp_weights / np.sum(hrp_weights)

        def objective(w: np.ndarray) -> float:
            return float(np.sum((w - hrp_weights) ** 2))

        cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

        if sector_map:
            sectors = sorted(set(sector_map.values()))
            symbol_arr = np.array(symbols)
            sector_masks = []
            for sector in sectors:
                sector_mask = np.array([sector_map.get(sym) == sector for sym in symbol_arr], dtype=float)
                if np.any(sector_mask):
                    sector_masks.append(sector_mask.copy())
                    cons.append(
                        {
                            "type": "ineq",
                            "fun": lambda w, m=sector_mask.copy(): max_sector - np.dot(w, m),
                        }
                    )

        bounds = [(0.0, max_position) for _ in range(n)]

        result = minimize(
            objective,
            np.ones(n) / n,  # Equal weight initial guess
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"maxiter": self.max_iterations, "ftol": 1e-10},
        )

        weights = result.x
        weights = weights / np.sum(weights)
        weights_dict = {symbols[i]: float(weights[i]) for i in range(n)}

        port_vol = float(np.sqrt(np.dot(weights, np.dot(covariance_matrix, weights))))

        return OptimizationResult(
            weights=weights_dict,
            expected_return=0.0,
            expected_volatility=port_vol,
            sharpe_ratio=0.0,
            method=OptimizationMethod.RISK_PARITY,
            converged=bool(result.success),
            message="HRP portfolio constructed successfully" if result.success else result.message,
        )

    def build_portfolio_at_date(
        self,
        as_of_date: pd.Timestamp,
        symbols: List[str],
        returns_data: pd.DataFrame,
        method: str = "erc",
        lookback_days: int = 252,
        factor_exposures: Optional[pd.DataFrame] = None,
        target_exposures: Optional[Dict[str, float]] = None,
        expected_returns: Optional[Dict[str, float]] = None,
        max_position: float = 0.25,
        sector_map: Optional[Dict[str, str]] = None,
        max_sector: float = 0.40,
    ) -> OptimizationResult:
        cutoff_date = as_of_date - pd.Timedelta(days=1)
        start_date = cutoff_date - pd.Timedelta(days=lookback_days)
        historical_returns = returns_data.loc[start_date:cutoff_date, symbols]

        if as_of_date in historical_returns.index:
            raise ValueError("PIT violation: as_of_date data included in historical window")

        if len(historical_returns) < 30:
            raise ValueError(f"Insufficient data: only {len(historical_returns)} days available")

        cov = historical_returns.cov().values

        method_lower = method.lower()
        if method_lower in {"erc", "risk_parity"}:
            result = self._build_erc_portfolio(
                symbols,
                cov,
                max_position=max_position,
                sector_map=sector_map,
                max_sector=max_sector,
            )
        elif method_lower == "factor_targeting":
            if factor_exposures is None or target_exposures is None:
                raise ValueError("factor_exposures and target_exposures are required for factor_targeting")
            result = self._build_factor_targeted_portfolio(
                symbols,
                factor_exposures,
                target_exposures,
                max_position=max_position,
                expected_returns=expected_returns,
                covariance_matrix=cov,
                sector_map=sector_map,
                max_sector=max_sector,
            )
        elif method_lower == "hrp":
            corr = historical_returns.corr().values
            result = self._build_hrp_portfolio(
                symbols,
                cov,
                corr,
                max_position=max_position,
                sector_map=sector_map,
                max_sector=max_sector,
            )
        else:
            raise ValueError(f"Unknown method: {method}")

        result.message = f"{result.message} | T-1 lag applied (data cutoff: {cutoff_date.date()})"
        return result

    def validate_pit_safety(
        self,
        as_of_date: pd.Timestamp,
        construction_date: pd.Timestamp,
    ) -> bool:
        min_construction_date = as_of_date - pd.Timedelta(days=1)
        return construction_date <= min_construction_date
