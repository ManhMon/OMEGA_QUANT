"""
OMEGA_QUANT Hierarchical Risk Parity (HRP) Portfolio Weighting
Replaces IC-weighted combination with risk-optimal allocation.

Benefits over IC-weight:
- Diversification across correlated signals
- No need for covariance matrix inversion (robust to noise)
- Naturally reduces concentration risk

Reference: Lopez de Prado (2016) "Building Diversified Portfolios that Outperform OOS"

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - Uses only past returns for covariance estimation.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class HRPWeighter:
    """
    Hierarchical Risk Parity for multi-signal portfolio weighting.
    Can be applied at two levels:
    1. Signal level: weight across multiple alpha signals
    2. Asset level: weight across symbols within a signal
    """

    def __init__(self, lookback: int = 60, min_periods: int = 20):
        self.lookback = lookback
        self.min_periods = min_periods

    def _get_cluster_var(self, cov: pd.DataFrame, cluster_items: List[str]) -> float:
        """Compute variance of an equal-weight portfolio of cluster items."""
        cov_slice = cov.loc[cluster_items, cluster_items]
        n = len(cluster_items)
        w = np.ones(n) / n
        return float(w @ cov_slice.values @ w)

    def _get_quasi_diag(self, link: np.ndarray) -> List[int]:
        """Sort clustered items by distance (quasi-diagonalization)."""
        link = link.astype(int)
        sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
        num_items = link[-1, 3]

        while sort_ix.max() >= num_items:
            sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
            df0 = sort_ix[sort_ix >= num_items]
            i = df0.index
            j = df0.values - num_items
            sort_ix[i] = link[j, 0]
            df1 = pd.Series(link[j, 1], index=i + 1)
            sort_ix = pd.concat([sort_ix, df1])
            sort_ix = sort_ix.sort_index()
            sort_ix.index = range(sort_ix.shape[0])

        return sort_ix.tolist()

    def _get_rec_bipart(self, cov: pd.DataFrame, sort_ix: List[int], items: List[str]) -> pd.Series:
        """Recursive bisection for HRP weights."""
        w = pd.Series(1.0, index=items)
        cluster_items = [items[i] for i in sort_ix]

        # Recursive bisection
        clusters = [cluster_items]
        while len(clusters) > 0:
            new_clusters = []
            for cluster in clusters:
                if len(cluster) <= 1:
                    continue
                mid = len(cluster) // 2
                left = cluster[:mid]
                right = cluster[mid:]

                # Allocate by inverse variance
                left_var = self._get_cluster_var(cov, left)
                right_var = self._get_cluster_var(cov, right)

                alloc = 1.0 - left_var / (left_var + right_var) if (left_var + right_var) > 0 else 0.5

                w[left] *= alloc
                w[right] *= (1 - alloc)

                if len(left) > 1:
                    new_clusters.append(left)
                if len(right) > 1:
                    new_clusters.append(right)

            clusters = new_clusters

        return w

    def compute_signal_weights(self, signal_returns: pd.DataFrame) -> pd.Series:
        """
        Compute HRP weights across multiple signals.

        Args:
            signal_returns: DataFrame (dates x signal_names) of daily signal returns

        Returns:
            Series of weights per signal (sums to 1).
        """
        if signal_returns.shape[1] <= 1:
            return pd.Series(1.0, index=signal_returns.columns)

        # Use recent data only
        recent = signal_returns.iloc[-self.lookback:]
        if len(recent) < self.min_periods:
            # Equal weight fallback
            n = signal_returns.shape[1]
            return pd.Series(1.0 / n, index=signal_returns.columns)

        # Correlation and covariance
        corr = recent.corr()
        cov = recent.cov()

        # Handle NaN
        corr = corr.fillna(0)
        cov = cov.fillna(0)
        np.fill_diagonal(corr.values, 1.0)

        # Distance matrix
        dist = ((1 - corr) / 2.0) ** 0.5

        # Hierarchical clustering
        try:
            from scipy.cluster.hierarchy import linkage
            from scipy.spatial.distance import squareform

            dist_condensed = squareform(dist.values, checks=False)
            link = linkage(dist_condensed, method='single')

            # Quasi-diagonalization
            sort_ix = self._get_quasi_diag(link)

            # Recursive bisection
            items = list(signal_returns.columns)
            weights = self._get_rec_bipart(cov, sort_ix, items)

        except Exception as e:
            logger.debug("HRP clustering failed: %s. Using inverse-vol.", e)
            # Fallback: inverse volatility
            vols = recent.std()
            inv_vol = 1.0 / vols.replace(0, 1.0)
            weights = inv_vol / inv_vol.sum()

        # Normalize
        weights = weights / weights.sum()
        return weights

    def compute_asset_weights(
        self,
        prices: pd.DataFrame,
        signal_weights: pd.Series,
        signal_exposures: Dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """
        Combine signal-level HRP weights with per-signal asset exposures.

        Args:
            prices: Asset prices (dates x symbols)
            signal_weights: HRP weights per signal
            signal_exposures: Dict of signal_name -> DataFrame (dates x symbols) of raw weights

        Returns:
            Combined weights (dates x symbols)
        """
        combined = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        for signal_name, exposure in signal_exposures.items():
            if signal_name in signal_weights.index:
                w = signal_weights[signal_name]
                # Align
                common_dates = combined.index.intersection(exposure.index)
                common_cols = combined.columns.intersection(exposure.columns)
                combined.loc[common_dates, common_cols] += exposure.loc[common_dates, common_cols] * w

        # Normalize rows
        row_sums = combined.sum(axis=1).replace(0, 1.0)
        combined = combined.div(row_sums, axis=0)

        return combined
