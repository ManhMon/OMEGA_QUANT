# flake8: noqa
"""
Compatibility shim for neutralization.
Maps the legacy NeutralizationEngine to the canonical HierarchicalNeutralizer.
"""
from __future__ import annotations

import warnings

warnings.simplefilter('always', DeprecationWarning)
warnings.warn(
    "omega.quant.neutralization is deprecated; import from omega.quant.features.neutralization instead.",
    DeprecationWarning,
    stacklevel=2
)

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple

from omega.quant.features.neutralization import (
    HierarchicalNeutralizer,
    FactorNeutralizer as CanonicalFactorNeutralizer,
    winsorize as canonical_winsorize,
    market_neutralize as canonical_market_neutralize,
    factor_neutralize as canonical_factor_neutralize,
    neutralize_signal as canonical_neutralize_signal,
)

from omega.quant.neutralization_engine import (
    FactorReturns,
    RollingFactorNeutralizer,
)

__all__ = [
    "NeutralizationEngine",
    "NeutralizationValidator",
    "FactorNeutralizer",
    "FactorReturns",
    "RollingFactorNeutralizer",
]


class NeutralizationEngine:
    """
    Legacy NeutralizationEngine wrapper that delegates to HierarchicalNeutralizer.
    """

    def __init__(
        self,
        strategy: str = 'cross_sectional',
        min_bucket_size: int = 5,
        min_sector_size: int = 10,
        min_exchange_size: int = 3,
        winsorize_lower: float = 0.01,
        winsorize_upper: float = 0.99
    ):
        if strategy not in ['cross_sectional', 'factor']:
            raise ValueError(f"Invalid strategy: {strategy}. Must be 'cross_sectional' or 'factor'")
        self.strategy = strategy
        self.min_bucket_size = min_bucket_size
        self.min_sector_size = min_sector_size
        self.min_exchange_size = min_exchange_size
        self.winsorize_lower = winsorize_lower
        self.winsorize_upper = winsorize_upper

        self.neutralizer = HierarchicalNeutralizer(
            min_l4_size=min_bucket_size,
            min_l3_size=min_bucket_size,
            min_l2_size=min_sector_size,
            min_l1_size=min_exchange_size
        )
        self.neutralization_stats: Dict[str, int] = {}

    def _winsorize(self, series: pd.Series) -> pd.Series:
        return canonical_winsorize(
            series,
            method='percentile',
            lower_percentile=self.winsorize_lower * 100,
            upper_percentile=self.winsorize_upper * 100
        )

    def neutralize_cross_sectional(
        self,
        alpha: pd.Series,
        sector: pd.Series,
        price_bucket: pd.Series,
        exchange: Optional[pd.Series] = None
    ) -> Tuple[pd.Series, Dict[str, int]]:
        alpha_winsorized = self._winsorize(alpha)
        res, stats = self.neutralizer.neutralize_cross_section(
            alpha=alpha_winsorized,
            sector=sector,
            price_level=price_bucket,
            liquidity_bucket=None,
            exchange=exchange
        )
        old_stats = {
            'tier1_2d': stats.get('l3_buckets', 0),
            'tier2_sector': stats.get('l2_buckets', 0),
            'tier3_exchange': stats.get('l1_exchange', 0),
            'tier4_market': stats.get('l0_global', 0)
        }
        self.neutralization_stats = old_stats
        return res, old_stats

    def neutralize_factor(
        self,
        features: Dict[str, np.ndarray],
        market_returns: np.ndarray,
        smb_returns: np.ndarray,
        hml_returns: np.ndarray
    ) -> Dict[str, np.ndarray]:
        factors = pd.DataFrame({
            'market': market_returns,
            'smb': smb_returns,
            'hml': hml_returns
        })
        neutralized = {}
        for name, vals in features.items():
            res = canonical_factor_neutralize(pd.Series(vals), factors)
            neutralized[name] = res.values
        return neutralized

    def neutralize_batch(
        self,
        panel: pd.DataFrame,
        alpha_cols: List[str],
        sector_col: str = 'sector',
        price_bucket_col: str = 'price_bucket',
        exchange_col: str = 'exchange'
    ) -> pd.DataFrame:
        result = panel.copy()
        for col in alpha_cols:
            if col not in panel.columns:
                continue
            neutral_col = f'{col}_neutral'
            for date in panel.index.get_level_values('date').unique():
                date_data = panel.loc[date]
                exchange_data = date_data[exchange_col] if exchange_col in panel.columns else None
                vals, _ = self.neutralize_cross_sectional(
                    date_data[col],
                    date_data[sector_col],
                    date_data[price_bucket_col],
                    exchange_data
                )
                result.loc[date, neutral_col] = vals
        return result

    def compute_neutralization_quality(
        self,
        alpha: pd.Series,
        alpha_neutral: pd.Series,
        sector: pd.Series
    ) -> Dict[str, Any]:
        corr_raw = alpha.corr(sector.astype('category').cat.codes)
        corr_neutral = alpha_neutral.corr(sector.astype('category').cat.codes)
        ic_by_sector = {}
        for sector_label in sector.unique():
            mask = sector == sector_label
            if mask.sum() > 1:
                ic_by_sector[sector_label] = alpha_neutral[mask].corr(alpha[mask])
        return {
            'correlation_reduction': abs(corr_raw) - abs(corr_neutral),
            'ic_by_sector': ic_by_sector,
            'mean_ic': np.mean(list(ic_by_sector.values())) if ic_by_sector else np.nan,
            'signal_preservation': alpha_neutral.std() / (alpha.std() + 1e-9)
        }

    def get_neutralization_report(self) -> str:
        report = f"=== Neutralization Report ({self.strategy}) ===\n"
        report += f"Tier 1 (Sector × Price): {self.neutralization_stats.get('tier1_2d', 0)} buckets\n"
        report += f"Tier 2 (Sector-only): {self.neutralization_stats.get('tier2_sector', 0)} buckets\n"
        report += f"Tier 3 (Exchange-only): {self.neutralization_stats.get('tier3_exchange', 0)} buckets\n"
        report += f"Tier 4 (Market-wide): {self.neutralization_stats.get('tier4_market', 0)} buckets\n"
        return report

    def get_fallback_distribution(self) -> Dict[str, int]:
        return self.neutralizer.get_fallback_stats()


class NeutralizationValidator:
    """
    Legacy NeutralizationValidator compatibility wrapper.
    """

    @staticmethod
    def check_temporal_integrity(alpha: pd.Series, alpha_neutral: pd.Series) -> bool:
        if isinstance(alpha.index, pd.MultiIndex):
            for symbol in alpha.index.get_level_values('symbol').unique()[:10]:
                alpha_ts = alpha.loc[(slice(None), symbol), :]
                neutral_ts = alpha_neutral.loc[(slice(None), symbol), :]
                if len(alpha_ts) > 1:
                    corr = alpha_ts.corr(neutral_ts)
                    if corr < 0.3:
                        return False
        return True

    @staticmethod
    def check_no_nan_leakage(alpha: pd.Series, alpha_neutral: pd.Series) -> bool:
        return alpha.isna().equals(alpha_neutral.isna())


FactorNeutralizer = CanonicalFactorNeutralizer
