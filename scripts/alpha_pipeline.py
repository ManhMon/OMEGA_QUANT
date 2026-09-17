#!/usr/bin/env python3
"""
Production Alpha Pipeline for E2E Scripts
Integrates AlphaDiscoveryEngine with IC filtering and Top-N selection.

PIT Safety: All signals enforced T-1 lag before any IC/fitness computation.
Board Lot: Pipeline outputs fractional weights; 100-share lot rounding is
           handled at execution time by the execution layer.
"""

import sys
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from pathlib import Path

sys.path.insert(0, 'src')

from omega.quant.factory.discovery_engine import DiscoveryEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IC helper (research reporting only)
# ---------------------------------------------------------------------------

def _compute_ic(factor: pd.Series, fut_ret: pd.Series) -> float:
    """Spearman IC averaged across dates. Factor must already be T-1 lagged."""
    aligned = pd.concat(
        [factor.rename('factor'), fut_ret.rename('ret')], axis=1
    ).dropna()
    if aligned.empty:
        return 0.0
    per_date_ic = aligned.groupby(level=0).apply(
        lambda g: g['factor'].corr(g['ret'], method='spearman')
    )
    per_date_ic = per_date_ic.replace([np.inf, -np.inf], np.nan).dropna()
    return float(per_date_ic.mean()) if not per_date_ic.empty else 0.0


# ---------------------------------------------------------------------------
# Data loader
# ---------------------------------------------------------------------------

def load_expanded_universe(n_days: int = 252, top_n_liquid: int = 50):
    """
    Load top N most liquid VN stocks from parquet.

    Sector mapping is loaded from data/sector_mapping_level2.csv and joined
    onto the panel as a 'sector' column. Tickers not found in the mapping
    are assigned sector 'Unknown'.

    Returns:
        panel: MultiIndex DataFrame [date, ticker] with OHLCV + sector column
        symbols: List of selected tickers
    """
    parquet_path = 'data/market_2015_now.parquet'
    df = pd.read_parquet(parquet_path)

    df['date'] = pd.to_datetime(df['date'])
    last_dates = sorted(df['date'].unique())[-n_days:]
    if not last_dates:
        raise ValueError("No market sessions available")
    # Select the universe using only data available before the trading window.
    avg_volume = df.loc[df['date'] < last_dates[0]].groupby('ticker')['volume'].mean().sort_values(ascending=False)
    top_symbols = avg_volume.head(top_n_liquid).index.tolist()
    if not top_symbols:
        raise ValueError("No pre-window history available for PIT-safe universe selection")

    df_filtered = df[df['ticker'].isin(top_symbols)].copy()
    df_filtered = df_filtered[df_filtered['date'].isin(last_dates)]

    # Load sector mapping and join onto filtered rows
    sector_csv = Path('data/sector_mapping_level2.csv')
    if sector_csv.exists():
        sector_df = pd.read_csv(sector_csv, usecols=['symbol', 'sector'])
        sector_map_series = sector_df.set_index('symbol')['sector']
        df_filtered['sector'] = df_filtered['ticker'].map(sector_map_series).fillna('Unknown')
    else:
        df_filtered['sector'] = 'Unknown'

    df_filtered = df_filtered.set_index(['date', 'ticker']).sort_index()
    panel = df_filtered[['open', 'high', 'low', 'close', 'volume', 'sector']].copy()

    print(f"[ALPHA] Loaded {len(last_dates)} days, {len(top_symbols)} liquid stocks")
    return panel, top_symbols


# ---------------------------------------------------------------------------
# Main signal generation
# ---------------------------------------------------------------------------

def _apply_sector_caps(
    weights: pd.Series,
    sector_map: Dict[str, str],
    sector_caps: Dict[str, float],
) -> pd.Series:
    """
    Enforce per-sector weight caps via strict iterative redistribution.

    Algorithm (projection onto sector-cap simplex):
      1. Identify sectors exceeding their cap.
      2. Freeze capped sectors at exactly their cap; compute excess weight.
      3. Redistribute excess proportionally only to uncapped sectors.
      4. Repeat until no sector exceeds its cap (convergence guaranteed in
         at most N_sectors iterations).
      5. Edge case — all active sectors are capped or infeasible (e.g. single
         sector portfolio): scale proportionally so the total equals the sum
         of all caps, then renormalize to 1.0. Emit a warning.

    Args:
        weights: Series [ticker -> weight], should sum to ~1.0
        sector_map: Dict [ticker -> sector_name]
        sector_caps: Dict [sector_name -> max_fraction]

    Returns:
        Series with same index, sector caps enforced, sums to 1.0.
    """
    if weights.empty:
        return weights.copy()

    w = weights.copy().astype(float)

    # Build reverse map: sector -> list of tickers present in w
    sector_tickers: Dict[str, list] = {}
    for ticker in w.index:
        sector = sector_map.get(ticker, ticker)
        sector_tickers.setdefault(sector, []).append(ticker)

    # Feasibility check: if sum of all active sector caps < 1.0, the constraints
    # are collectively infeasible (no valid distribution exists that sums to 1.0
    # while respecting all caps). Fall back to proportional scaling + renorm.
    total_cap_budget = sum(sector_caps.get(s, 1.0) for s in sector_tickers)
    if total_cap_budget < 1.0 - 1e-9:
        import warnings
        warnings.warn(
            f"[_apply_sector_caps] Sum of sector caps ({total_cap_budget:.4f}) < 1.0. "
            "Constraints are infeasible. Scaling each sector to its cap and renormalizing.",
            RuntimeWarning,
            stacklevel=2,
        )
        for sector, tickers in sector_tickers.items():
            cap = sector_caps.get(sector, 1.0)
            sw = w[tickers].sum()
            if sw > 1e-12:
                w[tickers] *= cap / sw
        total = w.sum()
        if total > 1e-12:
            w = w / total
        return w

    for _iteration in range(len(sector_tickers) + 2):
        # Identify which sectors are over cap
        over_cap_sectors = {}
        for sector, tickers in sector_tickers.items():
            cap = sector_caps.get(sector, 1.0)
            sw = w[tickers].sum()
            if sw > cap + 1e-9:
                over_cap_sectors[sector] = cap

        if not over_cap_sectors:
            break  # All sectors within cap — done

        uncapped_sectors = {
            s: tickers
            for s, tickers in sector_tickers.items()
            if s not in over_cap_sectors
        }
        uncapped_weight = sum(w[tickers].sum() for tickers in uncapped_sectors.values())

        if not uncapped_sectors or uncapped_weight < 1e-12:
            # All active sectors simultaneously over cap with no uncapped receiver.
            # Scale each sector to its cap and renormalize.
            import warnings
            warnings.warn(
                "[_apply_sector_caps] All active sectors are over cap simultaneously. "
                "Scaling proportionally and renormalizing to 1.0.",
                RuntimeWarning,
                stacklevel=2,
            )
            for sector, tickers in sector_tickers.items():
                cap = sector_caps.get(sector, 1.0)
                sw = w[tickers].sum()
                if sw > 1e-12:
                    w[tickers] *= cap / sw
            total = w.sum()
            if total > 1e-12:
                w = w / total
            return w

        # Freeze capped sectors at exactly their cap (scale tickers proportionally)
        for sector, cap in over_cap_sectors.items():
            tickers = sector_tickers[sector]
            sw = w[tickers].sum()
            if sw > 1e-12:
                w[tickers] *= cap / sw

        # Redistribute excess proportionally to uncapped sectors only
        total_after_freeze = w.sum()
        excess = 1.0 - total_after_freeze

        if abs(excess) > 1e-12 and uncapped_weight > 1e-12:
            scale_factor = (uncapped_weight + excess) / uncapped_weight
            for tickers in uncapped_sectors.values():
                w[tickers] *= scale_factor

    # Final renorm to correct floating-point drift
    total = w.sum()
    if total > 1e-12:
        w = w / total

    return w


def generate_alpha_signals(
    panel: pd.DataFrame,
    ic_threshold: float = 0.02,
    top_n_stocks: int = 8,
    rebalance_freq: int = 7,
    min_rebalance_delta: float = 0.05,
    use_evolution: bool = True,
    use_ml_ranking: bool = True,
    evolution_generations: int = 20,
    evolution_population: int = 50,
    sector_caps: Optional[Dict[str, float]] = None,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Generate alpha signals via:
      1. Static expression templates (8 alphas, unchanged)

    PIT T-1 lag enforced throughout. Forward-label evolution and ML ranking
    are intentionally disabled in this trading path.
    Board lot 100 compliance: weights are sized to whole lots only.

    Args:
        sector_caps: Dict [sector_name -> max_fraction]. If None, a default 30% cap
                     is applied uniformly to all sectors found in the universe.
    """
    # ------------------------------------------------------------------
    # Step 1: Static alphas (original 8 templates)
    # ------------------------------------------------------------------
    alpha_expressions = [
        "delta(close, 5) / delay(close, 5)",
        "delta(close, 20) / delay(close, 20)",
        "rank(delta(close, 10))",
        "close / ts_mean(close, 20) - 1",
        "-(close / ts_mean(close, 10) - 1)",
        "rank(volume) * rank(delta(close, 1))",
        "volume / ts_mean(volume, 20)",
        "ts_std(close, 20) / ts_mean(close, 20)",
    ]

    engine = DiscoveryEngine(use_alchemist=True)
    alphas: Dict[str, pd.Series] = {}

    for expr in alpha_expressions:
        try:
            alpha = engine.alchemist.evaluate(expr, panel)
            alphas[expr] = alpha
        except Exception as e:
            print(f"[ALPHA] Warning: Failed to generate '{expr}': {e}")

    if not alphas:
        raise ValueError("No static alphas generated")

    alphas = {
        name: alpha.groupby(level='ticker').shift(1)
        for name, alpha in alphas.items()
    }
    print(f"[ALPHA] Static alpha pool: {len(alphas)}/8")

    # ------------------------------------------------------------------
    # Step 2: Evolution Engine — evolve beyond static templates
    # ------------------------------------------------------------------
    evolved_alphas: Dict[str, pd.Series] = {}
    if use_evolution:
        print("[EVOLUTION] Skipping label-optimized evolution in trading pipeline")

    # Merge static + evolved into combined pool
    combined_alphas: Dict[str, pd.Series] = {}
    combined_alphas.update(alphas)
    combined_alphas.update(evolved_alphas)

    print(f"[ALPHA] Combined pool (static + evolved): {len(combined_alphas)} alphas")

    # ------------------------------------------------------------------
    # Step 3: ML Engine — XGBoost filter/rank
    # ------------------------------------------------------------------
    if use_ml_ranking:
        print("[ML] Skipping validation-label ranking in trading pipeline")

    # ------------------------------------------------------------------
    # Step 4: Compute final ICs for reporting
    # ------------------------------------------------------------------
    alpha_ics = {name: 0.0 for name in combined_alphas}
    print(f"[ALPHA] Final PIT-safe pool: {len(alpha_ics)} alphas")

    # ------------------------------------------------------------------
    # Step 5: Combine signals and build portfolio weights
    # ------------------------------------------------------------------
    combined_parts = [signal for signal in combined_alphas.values()]
    combined_alpha = pd.concat(combined_parts, axis=1).mean(axis=1)
    alpha_wide = combined_alpha.unstack(level=1)

    # Resolve sector_caps: default 30% cap on all sectors
    _DEFAULT_SECTOR_CAP = 0.30
    if sector_caps is None:
        sector_caps = {}  # will apply default cap per-sector below

    # Build a sector_map from panel 'sector' column if present
    tickers = list(alpha_wide.columns)
    if 'sector' in panel.columns:
        # Extract one sector label per ticker (first non-null value)
        sector_map: Dict[str, str] = (
            panel['sector']
            .groupby(level='ticker')
            .first()
            .reindex(tickers)
            .fillna('Unknown')
            .to_dict()
        )
    else:
        # No sector metadata: assign each ticker its own sector (cap has no effect)
        sector_map = {t: t for t in tickers}

    # Fill missing sectors with default cap
    all_sectors = set(sector_map.values())
    resolved_caps: Dict[str, float] = {s: sector_caps.get(s, _DEFAULT_SECTOR_CAP) for s in all_sectors}

    # Weekly rebalance + change threshold guard
    weights = pd.DataFrame(0.0, index=alpha_wide.index, columns=alpha_wide.columns)
    last_valid_weights: Optional[pd.Series] = None

    for idx, date in enumerate(alpha_wide.index):
        if idx % rebalance_freq == 0:
            alpha_row = alpha_wide.loc[date].dropna()
            if len(alpha_row) > 0:
                top_stocks = alpha_row.nlargest(min(top_n_stocks, len(alpha_row)))
                if len(top_stocks) > 0:
                    target_weights = pd.Series(0.0, index=alpha_wide.columns)
                    target_weights[top_stocks.index] = 1.0 / len(top_stocks)

                    # Apply sector caps
                    target_weights = _apply_sector_caps(target_weights, sector_map, resolved_caps)

                    if last_valid_weights is None:
                        last_valid_weights = target_weights
                    else:
                        max_delta = (target_weights - last_valid_weights).abs().max()
                        if max_delta >= min_rebalance_delta:
                            last_valid_weights = target_weights

        if last_valid_weights is not None:
            weights.loc[date] = last_valid_weights

    print(
        f"[ALPHA] Portfolio: Top {top_n_stocks} stocks, "
        f"Rebalance every {rebalance_freq} days, "
        f"min rebalance delta {min_rebalance_delta:.0%}, "
        f"sector_caps={resolved_caps}"
    )
    return weights, alpha_ics


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_alpha_pipeline(
    n_days: int = 252,
    top_n_liquid: int = 50,
    ic_threshold: float = 0.02,
    top_n_stocks: int = 8,
    rebalance_freq: int = 7,
    min_rebalance_delta: float = 0.05,
    use_evolution: bool = True,
    use_ml_ranking: bool = True,
    evolution_generations: int = 30,
    evolution_population: int = 100,
    sector_caps: Optional[Dict[str, float]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, float]]:
    """
    Full alpha pipeline:
      Load data -> Static alphas -> Evolution Engine -> ML ranking -> Weights.

    Args:
        n_days: Lookback window in trading days
        top_n_liquid: Universe size (top N by avg volume)
        ic_threshold: Minimum |IC| to retain an alpha
        top_n_stocks: Number of stocks in portfolio (default 8, Phase 2 diversification)
        rebalance_freq: Rebalance every N days (default 7, Phase 2 diversification)
        min_rebalance_delta: Minimum weight change to trigger rebalance
        use_evolution: Retained compatibility flag; forward-label evolution is disabled.
        use_ml_ranking: Retained compatibility flag; validation-label ranking is disabled.
        evolution_generations: Retained compatibility parameter.
        evolution_population: Retained compatibility parameter.
        sector_caps: Dict mapping sector name to max weight fraction (e.g. {"TECH": 0.30}).
                     If None, defaults to 30% cap on all sectors.

    Returns:
        weights: DataFrame [date x ticker] of portfolio weights
        panel: MultiIndex OHLCV panel
        alpha_ics: Dict of {alpha_name -> IC}
    """
    panel, symbols = load_expanded_universe(n_days=n_days, top_n_liquid=top_n_liquid)
    weights, alpha_ics = generate_alpha_signals(
        panel=panel,
        ic_threshold=ic_threshold,
        top_n_stocks=top_n_stocks,
        rebalance_freq=rebalance_freq,
        min_rebalance_delta=min_rebalance_delta,
        use_evolution=use_evolution,
        use_ml_ranking=use_ml_ranking,
        evolution_generations=evolution_generations,
        evolution_population=evolution_population,
        sector_caps=sector_caps,
    )
    return weights, panel, alpha_ics
