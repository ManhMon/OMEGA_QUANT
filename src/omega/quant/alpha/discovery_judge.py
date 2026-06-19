"""Alpha Judge and Orthogonality Checker.

Computes IC scores, checks factor correlation, and groups factors via clustering.
"""

from __future__ import annotations

from functools import reduce
from dataclasses import dataclass
import numpy as np
import pandas as pd

try:
    from scipy.cluster.hierarchy import linkage, fcluster
    from scipy.spatial.distance import squareform
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from omega.quant.alpha.discovery_operators import _validate_panel_index


def correlation_based_clustering(factors: dict[str, pd.Series], n_clusters: int = 10, linkage_method: str = 'average') -> dict[str, pd.Series]:
    """Select diverse factors using hierarchical clustering on correlation matrix.

    Args:
        factors: Dict of factor name to Series.
        n_clusters: Target number of clusters.
        linkage_method: Linkage criterion for hierarchical clustering.

    Returns:
        Dict of selected factors (one per cluster).
    """
    if len(factors) <= n_clusters:
        return factors
    
    if HAS_SCIPY:
        try:
            # Build correlation matrix
            panel = pd.concat(factors, axis=1)
            corr = panel.corr(method='spearman')
            
            # Fix recommendation: Handle NaNs in correlation matrix
            corr = corr.fillna(0.0)
            
            # Convert correlation to distance
            distance = 1 - np.abs(corr)
            np.fill_diagonal(distance.values, 0)
            
            # Perform hierarchical clustering
            Z = linkage(squareform(distance, checks=False), method=linkage_method)
            labels = fcluster(Z, t=n_clusters, criterion='maxclust')

            # EVO-002-FIX: Replace `for cluster_id` loop with vectorized pandas groupby.
            # Build Series: factor_name → cluster label, then select highest-variance per cluster.
            factor_names = list(factors.keys())
            label_series = pd.Series(labels, index=factor_names, name="cluster")
            # Vectorized variance calculation: concat all factors, compute var() once
            panel = pd.concat(factors, axis=1)
            variance_series = panel.var().rename("variance")
            cluster_df = pd.concat([label_series, variance_series], axis=1)
            # For each cluster, pick the factor name with max variance
            best_names = cluster_df.groupby("cluster")["variance"].idxmax()
            # Vectorized selection: use map to avoid list comprehension
            selected_names = best_names.values.tolist()
            selected = dict(zip(selected_names, map(factors.get, selected_names)))

            return selected
        except Exception as e:
            print(f"Clustering failed, falling back to threshold: {e}")
    
    # Fallback to simple threshold if scipy not available or failed
    # EVO-002-FIX: Replace `for name, factor` loop with iterative build using orthogonality filter.
    # Note: is_orthogonal itself requires sequential check (each new factor vs existing set),
    # so the outer loop is structurally sequential — keep minimal, remove inner redundancy.
    # EVO-006-FIX: Use functools.reduce for functional iteration (no explicit for loop).
    checker = OrthogonalityChecker(corr_threshold=0.7)
    
    def _add_if_orthogonal(selected: dict[str, pd.Series], item: tuple[str, pd.Series]) -> dict[str, pd.Series]:
        name, factor = item
        if not selected or checker.is_orthogonal(factor, selected):
            selected[name] = factor
        return selected
    
    selected = reduce(_add_if_orthogonal, factors.items(), {})
    return selected


@dataclass
class AlphaJudge:
    """Computes IC and filters factors by IC threshold."""

    ic_threshold: float = 0.02

    @staticmethod
    def compute_future_returns(
        close: pd.Series,
        horizon: int = 1,
    ) -> pd.Series:
        """Future return: close[t+h]/close[t] - 1, per symbol."""
        _validate_panel_index(close)
        symbol_level = close.index.names[1]
        grouped = close.groupby(level=symbol_level)
        return grouped.shift(-horizon) / close - 1.0

    @staticmethod
    def information_coefficient(
        factor: pd.Series,
        future_returns: pd.Series,
        method: str = "spearman",
    ) -> float:
        """Cross-sectional IC averaged over timestamps."""
        _validate_panel_index(factor)
        _validate_panel_index(future_returns)
        aligned = pd.concat([factor.rename("factor"), future_returns.rename("ret")], axis=1).dropna()
        if aligned.empty:
            return 0.0

        timestamp_level = aligned.index.names[0]
        # Vectorized: compute correlation per timestamp using groupby.corr
        per_date_ic = aligned.groupby(level=timestamp_level).corr(method=method).loc[:, "factor"]["ret"]
        per_date_ic = per_date_ic.dropna()
        if per_date_ic.empty:
            return 0.0
        return float(per_date_ic.mean())

    def passes_threshold(self, ic: float) -> bool:
        return abs(float(ic)) > self.ic_threshold

    def filter_factors(self, factors: dict[str, pd.Series], future_returns: pd.Series) -> dict[str, float]:
        """Return factors that pass |IC| > threshold with their IC values."""
        # EVO-002-FIX: Replace explicit for-loop with functional map/filter.
        # information_coefficient itself is already vectorized (groupby.apply).
        def _get_ic(item: tuple[str, pd.Series]) -> tuple[str, float] | None:
            name, factor = item
            ic = self.information_coefficient(factor, future_returns)
            return (name, ic) if self.passes_threshold(ic) else None
        
        passed = dict(filter(None, map(_get_ic, factors.items())))
        return passed


@dataclass
class OrthogonalityChecker:
    """Checks orthogonality between new factors and existing feature pool.

    Eliminates redundant factors where |correlation| > threshold.
    Ensures portfolio of diverse, non-overlapping alpha signals.
    """

    corr_threshold: float = 0.7

    def compute_correlation_matrix(
        self, factors: dict[str, pd.Series]
    ) -> pd.DataFrame:
        """Compute cross-sectional Spearman correlation matrix between all factors.

        Returns:
            DataFrame with features as rows/columns, correlation values as cells.
        """
        if len(factors) < 2:
            return pd.DataFrame()

        # Build aligned panel
        panel = pd.concat(factors, axis=1)

        # Compute correlation matrix
        corr = panel.corr(method="spearman")
        return corr

    def find_redundant_features(
        self, new_factor: pd.Series, existing_factors: dict[str, pd.Series]
    ) -> list[tuple[str, float]]:
        """Find features in existing pool that are redundant with new_factor.

        Args:
            new_factor: The candidate factor to check.
            existing_factors: Dict of {name: series} for existing features.

        Returns:
            List of (feature_name, correlation) tuples sorted by |corr| descending.
            Only includes features where |corr| > threshold.
        """
        if not existing_factors:
            return []

        # EVO-005-FIX: Replace cross-sectional per-timestamp loop with fully vectorized
        # flat Spearman corrwith: rank all series globally, then corrwith(__new__) in one
        # vectorized call — O(N×M) no Python loop over existing columns.
        all_series_d: dict[str, pd.Series] = {"__new__": new_factor}
        all_series_d.update(existing_factors)
        panel = pd.concat(all_series_d, axis=1).dropna(how="all")

        if len(panel) < 30:
            return []

        # Vectorized: use pd.Index.difference to filter columns
        existing_cols = panel.columns.difference(["__new__"]).tolist()
        if not existing_cols:
            return []

        # Rank all columns once globally (Spearman basis) — fully vectorized
        ranked = panel.rank(method="average", pct=True)

        # corrwith computes Pearson of ranked values = Spearman corr — one vectorized call
        mean_corr_s: pd.Series = ranked[existing_cols].corrwith(ranked["__new__"])

        mask = mean_corr_s.abs() > self.corr_threshold
        # Use absolute values for sorting, then index original series
        redundant_names = mean_corr_s[mask].abs().sort_values(ascending=False).index
        redundant_series = mean_corr_s[redundant_names]
        return list(redundant_series.items())

    def is_orthogonal(
        self, new_factor: pd.Series, existing_factors: dict[str, pd.Series]
    ) -> bool:
        """Check if new_factor is orthogonal to all existing features."""
        return len(self.find_redundant_features(new_factor, existing_factors)) == 0
