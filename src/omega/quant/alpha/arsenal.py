"""
Alpha Arsenal - Main Orchestration with Lazy Loading

Version: v21.38-Modular
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-06-10

This module contains the main compute_ultimate_alphas function that
orchestrates all alpha computations with lazy loading to optimize
cold-import time.
"""

import logging
import pandas as pd
import numpy as np
from typing import Optional, List

# Import primitives and helpers (always needed)
from .primitives import compute_rsi, compute_returns

# Import memory management (always needed)
try:
    from omega.core.memory.resource_monitor import (
        limit_memory,
        assert_memory_safe,
    )
except ImportError:
    from .helpers import limit_memory, assert_memory_safe

# Configure logging
logger = logging.getLogger(__name__)


@limit_memory(threshold_percent=85.0)
def compute_ultimate_alphas(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    alpha_groups: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Compute ALL ultimate alpha factors with PIT safety and lazy loading.

    This is the master function that consolidates alphas from modular
    sub-modules. It implements lazy loading to only import and compute
    requested alpha groups, optimizing cold-import time and memory usage.

    Args:
        df: Input DataFrame with OHLCV data
        symbol_col: Symbol column name (default 'ticker')
        alpha_groups: Optional list of groups to compute.
                      If None, computes all.

    Returns:
        DataFrame with original data + 130+ alpha columns
    """
    df_out = df.copy()
    required_cols = [
        "date",
        symbol_col,
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    if df_out.empty or "date" not in df_out.columns:
        logger.warning("Empty or invalid DataFrame. Returning empty result.")
        return pd.DataFrame()

    missing_cols = [col for col in required_cols if col not in df_out.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    logger.info(
        "Computing ultimate alpha arsenal (130+ alphas) "
        "with PIT safety and lazy loading..."
    )

    all_groups = [
        "momentum",
        "volatility",
        "liquidity",
        "trend",
        "price_action",
        "mean_reversion",
        "money_flow",
        "vn_specific",
        "correlation",
        "volume_profile",
        "momentum_ext",
        "cross_sectional",
        "microstructure",
        "phase34_microstructure",
        "hybrid_regime",
        "hybrid_regime_v2",
    ]
    groups_to_compute = (
        alpha_groups if alpha_groups is not None else all_groups
    )

    alphas_dict = {}
    assert_memory_safe(85.0, context="compute_ultimate_alphas main loop")

    # ========== MOMENTUM ALPHAS ==========
    if "momentum" in groups_to_compute:
        logger.info("Computing momentum alphas...")
        from . import momentum

        alphas_dict["alpha_roc_5"] = momentum.compute_roc(
            df_out, period=5, symbol_col=symbol_col
        )
        alphas_dict["alpha_roc_10"] = momentum.compute_roc(
            df_out, period=10, symbol_col=symbol_col
        )
        alphas_dict["alpha_roc_20"] = momentum.compute_roc(
            df_out, period=20, symbol_col=symbol_col
        )
        alphas_dict["alpha_roc_60"] = momentum.compute_roc(
            df_out, period=60, symbol_col=symbol_col
        )
        alphas_dict["alpha_roc_120"] = momentum.compute_roc(
            df_out, period=120, symbol_col=symbol_col
        )
        alphas_dict["alpha_roc_252"] = momentum.compute_roc(
            df_out, period=252, symbol_col=symbol_col
        )

        alphas_dict["alpha_rsi_7"] = compute_rsi(
            df_out, period=7, symbol_col=symbol_col
        )
        alphas_dict["alpha_rsi_14"] = compute_rsi(
            df_out, period=14, symbol_col=symbol_col
        )
        alphas_dict["alpha_rsi_21"] = compute_rsi(
            df_out, period=21, symbol_col=symbol_col
        )
        alphas_dict["alpha_rsi_28"] = compute_rsi(
            df_out, period=28, symbol_col=symbol_col
        )

        alphas_dict["alpha_ret_5d"] = compute_returns(
            df_out, period=5, symbol_col=symbol_col
        )
        alphas_dict["alpha_ret_20d"] = compute_returns(
            df_out, period=20, symbol_col=symbol_col
        )
        alphas_dict["alpha_ret_60d"] = compute_returns(
            df_out, period=60, symbol_col=symbol_col
        )
        alphas_dict["alpha_ret_120d"] = compute_returns(
            df_out, period=120, symbol_col=symbol_col
        )

        alphas_dict["alpha_mom_5_20"] = momentum.compute_momentum_acceleration(
            df_out, 5, 20, symbol_col=symbol_col
        )
        alphas_dict["alpha_mom_20_60"] = (
            momentum.compute_momentum_acceleration(
                df_out, 20, 60, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_mom_60_120"] = (
            momentum.compute_momentum_acceleration(
                df_out, 60, 120, symbol_col=symbol_col
            )
        )

    # ========== VOLATILITY ALPHAS ==========
    if "volatility" in groups_to_compute:
        logger.info("Computing volatility alphas...")
        from . import volatility

        alphas_dict["alpha_atr_14_norm"] = volatility.compute_atr_normalized(
            df_out, period=14, symbol_col=symbol_col
        )
        alphas_dict["alpha_hist_vol_10"] = (
            volatility.compute_historical_volatility(
                df_out, period=10, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_hist_vol_20"] = (
            volatility.compute_historical_volatility(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_hist_vol_60"] = (
            volatility.compute_historical_volatility(
                df_out, period=60, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_downside_vol_20"] = (
            volatility.compute_downside_volatility(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_downside_vol_60"] = (
            volatility.compute_downside_volatility(
                df_out, period=60, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_parkinson_vol_10"] = (
            volatility.compute_parkinson_volatility(
                df_out, period=10, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_parkinson_vol_20"] = (
            volatility.compute_parkinson_volatility(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_parkinson_vol_60"] = (
            volatility.compute_parkinson_volatility(
                df_out, period=60, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_garman_klass_vol_20"] = (
            volatility.compute_garman_klass_volatility(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_yang_zhang_vol_20"] = (
            volatility.compute_yang_zhang_volatility(
                df_out, period=20, symbol_col=symbol_col
            )
        )

    # ========== LIQUIDITY ALPHAS ==========
    if "liquidity" in groups_to_compute:
        logger.info("Computing liquidity alphas...")
        from . import liquidity

        alphas_dict["alpha_vol_ma_ratio_5_20"] = (
            liquidity.compute_volume_ma_ratio(
                df_out, short_period=5, long_period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vol_ma_ratio_10_60"] = (
            liquidity.compute_volume_ma_ratio(
                df_out, short_period=10, long_period=60, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_illiquidity_amihud_20"] = (
            liquidity.compute_illiquidity_amihud(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_illiquidity_amihud_60"] = (
            liquidity.compute_illiquidity_amihud(
                df_out, period=60, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_adv_20d"] = liquidity.compute_adv(
            df_out, period=20, symbol_col=symbol_col
        )
        alphas_dict["alpha_adv_60d"] = liquidity.compute_adv(
            df_out, period=60, symbol_col=symbol_col
        )
        alphas_dict["alpha_zero_trade_freq_20"] = (
            liquidity.compute_zero_trade_frequency(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_zero_trade_freq_60"] = (
            liquidity.compute_zero_trade_frequency(
                df_out, period=60, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_obv_change_20"] = liquidity.compute_obv_change(
            df_out, period=20, symbol_col=symbol_col
        )
        alphas_dict["alpha_liquidity_quality"] = (
            liquidity.compute_liquidity_quality_score(
                df_out, period=20, symbol_col=symbol_col
            )
        )

    # ========== TREND ALPHAS ==========
    if "trend" in groups_to_compute:
        logger.info("Computing trend alphas...")
        from . import trend

        alphas_dict["alpha_dist_ma_5"] = trend.compute_distance_to_ma(
            df_out, period=5, symbol_col=symbol_col
        )
        alphas_dict["alpha_dist_ma_10"] = trend.compute_distance_to_ma(
            df_out, period=10, symbol_col=symbol_col
        )
        alphas_dict["alpha_dist_ma_20"] = trend.compute_distance_to_ma(
            df_out, period=20, symbol_col=symbol_col
        )
        alphas_dict["alpha_dist_ma_50"] = trend.compute_distance_to_ma(
            df_out, period=50, symbol_col=symbol_col
        )
        alphas_dict["alpha_dist_ma_60"] = trend.compute_distance_to_ma(
            df_out, period=60, symbol_col=symbol_col
        )
        alphas_dict["alpha_dist_ma_100"] = trend.compute_distance_to_ma(
            df_out, period=100, symbol_col=symbol_col
        )
        alphas_dict["alpha_dist_ma_200"] = trend.compute_distance_to_ma(
            df_out, period=200, symbol_col=symbol_col
        )
        alphas_dict["alpha_dist_high_60"] = trend.compute_distance_to_high(
            df_out, period=60, symbol_col=symbol_col
        )
        alphas_dict["alpha_dist_high_120"] = trend.compute_distance_to_high(
            df_out, period=120, symbol_col=symbol_col
        )
        alphas_dict["alpha_dist_high_252"] = trend.compute_distance_to_high(
            df_out, period=252, symbol_col=symbol_col
        )
        alphas_dict["alpha_dist_low_60"] = trend.compute_distance_to_low(
            df_out, period=60, symbol_col=symbol_col
        )
        alphas_dict["alpha_dist_low_120"] = trend.compute_distance_to_low(
            df_out, period=120, symbol_col=symbol_col
        )
        alphas_dict["alpha_dist_low_252"] = trend.compute_distance_to_low(
            df_out, period=252, symbol_col=symbol_col
        )

    # ========== PRICE ACTION ALPHAS ==========
    if "price_action" in groups_to_compute:
        logger.info("Computing price action alphas...")
        from . import price_action

        alphas_dict["alpha_body_size"] = price_action.compute_body_size(
            df_out, symbol_col=symbol_col
        )
        alphas_dict["alpha_upper_shadow"] = price_action.compute_upper_shadow(
            df_out, symbol_col=symbol_col
        )
        alphas_dict["alpha_lower_shadow"] = price_action.compute_lower_shadow(
            df_out, symbol_col=symbol_col
        )
        alphas_dict["alpha_gap_return"] = price_action.compute_gap_return(
            df_out, symbol_col=symbol_col
        )
        alphas_dict["alpha_candle_range"] = price_action.compute_candle_range(
            df_out, symbol_col=symbol_col
        )
        alphas_dict["alpha_wick_ratio"] = price_action.compute_wick_ratio(
            df_out, symbol_col=symbol_col
        )

    # ========== MEAN REVERSION ALPHAS ==========
    if "mean_reversion" in groups_to_compute:
        logger.info("Computing mean reversion alphas...")
        from . import mean_reversion
        from . import vn_specific

        alphas_dict["alpha_bb_dist_10"] = (
            mean_reversion.compute_bollinger_distance(
                df_out, period=10, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_bb_dist_20"] = (
            mean_reversion.compute_bollinger_distance(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_bb_dist_40"] = (
            mean_reversion.compute_bollinger_distance(
                df_out, period=40, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_bb_dist_60"] = (
            mean_reversion.compute_bollinger_distance(
                df_out, period=60, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_bb_dist_120"] = (
            mean_reversion.compute_bollinger_distance(
                df_out, period=120, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_rsi_crossover_5_20"] = (
            mean_reversion.compute_rsi_crossover(
                df_out, short_period=5, long_period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_rsi_crossover_20_120"] = (
            mean_reversion.compute_rsi_crossover(
                df_out, short_period=20, long_period=120, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_rsi_crossover_60_120"] = (
            mean_reversion.compute_rsi_crossover(
                df_out, short_period=60, long_period=120, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_rsi_divergence"] = (
            mean_reversion.compute_rsi_divergence(
                df_out, period=14, symbol_col=symbol_col
            )
        )

        # BATCH 8: Mean Reversion Extensions
        alphas_dict["alpha_zscore"] = mean_reversion.compute_zscore(
            df_out, period=20, symbol_col=symbol_col
        )
        alphas_dict["alpha_percentile_rank"] = (
            mean_reversion.compute_percentile_rank(
                df_out, period=60, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_consecutive_up_days"] = (
            mean_reversion.compute_consecutive_up_days(
                df_out, symbol_col=symbol_col
            )
        )

    # ========== MONEY FLOW ALPHAS ==========
    if "money_flow" in groups_to_compute:
        logger.info("Computing money flow alphas...")
        from . import money_flow

        alphas_dict["alpha_vol_momentum_5"] = (
            money_flow.compute_volume_momentum(
                df_out, period=5, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vol_momentum_10"] = (
            money_flow.compute_volume_momentum(
                df_out, period=10, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vol_momentum_20"] = (
            money_flow.compute_volume_momentum(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_price_acceleration"] = (
            money_flow.compute_price_acceleration(
                df_out, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_sector_rel_momentum_20"] = (
            money_flow.compute_sector_relative_momentum(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_sector_rel_momentum_60"] = (
            money_flow.compute_sector_relative_momentum(
                df_out, period=60, symbol_col=symbol_col
            )
        )

    # ========== VN-SPECIFIC ALPHAS ==========
    if "vn_specific" in groups_to_compute:
        logger.info("Computing VN-specific alphas...")
        from . import vn_specific

        # BATCH 1: VN-Specific Liquidity Alphas
        alphas_dict["alpha_vn_amihud_liq_reversal"] = (
            vn_specific.compute_vn_amihud_liquidity_reversal(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_illiq_regime_penalty"] = (
            vn_specific.compute_vn_illiq_regime_penalty(
                df_out, period=60, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_volume_shock_reversal"] = (
            vn_specific.compute_vn_volume_shock_reversal(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_turnover_exhaustion"] = (
            vn_specific.compute_vn_turnover_exhaustion(
                df_out, period=20, symbol_col=symbol_col
            )
        )

        # BATCH 2: Advanced Mean Reversion Alphas
        alphas_dict["alpha_vn_bollinger_snapback"] = (
            vn_specific.compute_vn_bollinger_snapback(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_rsi_divergence_reversal"] = (
            vn_specific.compute_vn_rsi_divergence_reversal(
                df_out, period=14, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_sector_neutral_residual_reversion"] = (
            vn_specific.compute_vn_sector_neutral_residual_reversion(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_close_location_reversion"] = (
            vn_specific.compute_vn_close_location_reversion(
                df_out, period=20, symbol_col=symbol_col
            )
        )

        # BATCH 3: Microstructure & Foreign Flows
        alphas_dict["alpha_vn_foreign_flow_persistence"] = (
            vn_specific.compute_vn_foreign_flow_persistence(
                df_out, period=5, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_foreign_absorption_reversal"] = (
            vn_specific.compute_vn_foreign_absorption_reversal(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_foreign_room_squeeze"] = (
            vn_specific.compute_vn_foreign_room_squeeze(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_limit_lock_continuation"] = (
            vn_specific.compute_vn_limit_lock_continuation(
                df_out, period=5, exchange="HOSE", symbol_col=symbol_col
            )
        )

        # Core VN-specific functions
        alphas_dict["alpha_limit_lock_streak"] = (
            vn_specific.compute_limit_lock_streak(
                df_out, exchange="HOSE", symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_t2_momentum_adj"] = (
            vn_specific.compute_t2_momentum_adjustment(
                df_out, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_penny_trap_score"] = (
            vn_specific.compute_penny_trap_score(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_smart_money_lite"] = (
            vn_specific.compute_smart_money_lite(
                df_out, period=20, symbol_col=symbol_col
            )
        )

        # RESCUE P3 WEEK 1: 3 Missing Alphas from week1_alphas.py
        from . import liquidity

        alphas_dict["alpha_vn_t2_momentum_diff"] = (
            vn_specific.alpha_vn_t2_momentum_diff(
                df_out, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_penny_trap_risk"] = (
            vn_specific.alpha_vn_penny_trap_risk(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_liquidity_quality_score"] = (
            liquidity.alpha_liquidity_quality_score(
                df_out, period=20, symbol_col=symbol_col
            )
        )

        # BATCH 4: VN T+2 Settlement & Limit Mechanics (3)
        alphas_dict["alpha_vn_limit_unlock_exhaustion"] = (
            vn_specific.alpha_vn_limit_unlock_exhaustion(
                df_out, period=5, exchange="HOSE", symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_t2_settlement_supply_overhang"] = (
            vn_specific.alpha_vn_t2_settlement_supply_overhang(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_t2_cash_recycling_bounce"] = (
            vn_specific.alpha_vn_t2_cash_recycling_bounce(
                df_out, period=20, symbol_col=symbol_col
            )
        )

        # PHASE 3.4 ROUND 1: VN Microstructure Alphas (2)
        alphas_dict["alpha_vn_001_post_settlement_momentum"] = (
            vn_specific.alpha_vn_001_post_settlement_momentum(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_002_limit_band_reversion"] = (
            vn_specific.alpha_vn_002_limit_band_reversion(
                df_out, period=20, exchange="HOSE", symbol_col=symbol_col
            )
        )

        # PHASE 3.4 ROUND 2: VN Microstructure Alphas (3)
        alphas_dict["alpha_vn_003_foreign_flow_divergence"] = (
            vn_specific.alpha_vn_003_foreign_flow_divergence(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_004_intraday_persistence"] = (
            vn_specific.alpha_vn_004_intraday_persistence(
                df_out, period=5, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_vn_005_liquidity_adjusted_reversal"] = (
            vn_specific.alpha_vn_005_liquidity_adjusted_reversal(
                df_out, period=20, symbol_col=symbol_col
            )
        )

    # ========== CORRELATION ALPHAS ==========
    if "correlation" in groups_to_compute:
        logger.info("Computing correlation alphas...")
        from . import correlation

        alphas_dict["alpha_stock_sector_corr"] = (
            correlation.compute_stock_sector_correlation(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_market_correlation"] = (
            correlation.compute_market_correlation(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_pair_correlation"] = (
            correlation.compute_pair_correlation(
                df_out, period=20, symbol_col=symbol_col
            )
        )

    # ========== VOLUME PROFILE ALPHAS ==========
    if "volume_profile" in groups_to_compute:
        logger.info("Computing volume profile alphas...")
        from . import volume_profile

        alphas_dict["alpha_vwap_distance"] = (
            volume_profile.compute_vwap_distance(df_out, symbol_col=symbol_col)
        )
        alphas_dict["alpha_twap_deviation"] = (
            volume_profile.compute_twap_deviation(
                df_out, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_close_vwap_ratio"] = (
            volume_profile.compute_close_vwap_ratio(
                df_out, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_volume_weighted_return"] = (
            volume_profile.compute_volume_weighted_return(
                df_out, period=20, symbol_col=symbol_col
            )
        )

    # ========== MOMENTUM EXTENSIONS ==========
    if "momentum_ext" in groups_to_compute:
        logger.info("Computing momentum extension alphas...")
        from . import momentum_extensions

        alphas_dict["alpha_turtle_traders"] = (
            momentum_extensions.compute_turtle_traders(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_inertia"] = momentum_extensions.compute_inertia(
            df_out, period=20, symbol_col=symbol_col
        )
        alphas_dict["alpha_relative_strength"] = (
            momentum_extensions.compute_relative_strength(
                df_out, period=20, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_acceleration_index"] = (
            momentum_extensions.compute_acceleration_index(
                df_out, symbol_col=symbol_col
            )
        )

    # ========== CROSS-SECTIONAL ALPHAS ==========
    if "cross_sectional" in groups_to_compute:
        logger.info("Computing cross-sectional alphas...")
        from . import cross_sectional

        alphas_dict["alpha_cross_sectional_zscore"] = (
            cross_sectional.compute_cross_sectional_zscore(
                df_out, symbol_col=symbol_col
            )
        )
        alphas_dict["alpha_relative_strength_universe"] = (
            cross_sectional.compute_relative_strength_universe(
                df_out, period=20, symbol_col=symbol_col
            )
        )

    # ========== MARKET MICROSTRUCTURE ALPHAS ==========
    if "microstructure" in groups_to_compute:
        logger.info("Computing Batch 10 market microstructure alphas...")
        try:
            from omega.quant.strategy.market_microstructure import (
                MICROSTRUCTURE_ALPHA_COLUMNS,
                compute_microstructure_alphas,
            )

            if compute_microstructure_alphas is not None:
                df_microstructure = compute_microstructure_alphas(
                    df_out,
                    symbol_col=symbol_col,
                    date_col="date",
                    open_col="open",
                    high_col="high",
                    low_col="low",
                    close_col="close",
                    volume_col="volume",
                    foreign_buy_col=(
                        "foreign_buy_value"
                        if "foreign_buy_value" in df_out.columns
                        else None
                    ),
                    foreign_sell_col=(
                        "foreign_sell_value"
                        if "foreign_sell_value" in df_out.columns
                        else None
                    ),
                )

                missing_microstructure_cols = [
                    col
                    for col in MICROSTRUCTURE_ALPHA_COLUMNS
                    if col not in df_microstructure.columns
                ]
                if missing_microstructure_cols:
                    raise ValueError(
                        "Missing required market microstructure alpha "
                        f"columns: {missing_microstructure_cols}"
                    )

                microstructure_cols = [
                    c
                    for c in df_microstructure.columns
                    if c.startswith("alpha_") and c not in alphas_dict
                ]
                for col in microstructure_cols:
                    alphas_dict[col] = df_microstructure[col]
                logger.info(
                    f"   Added {len(microstructure_cols)} "
                    "microstructure alphas"
                )
        except Exception as e:
            logger.error(
                f"Failed to compute market microstructure alphas: {e}"
            )
            raise

    # ========== PHASE 3.4 MICROSTRUCTURE ALPHAS ==========
    if "phase34_microstructure" in groups_to_compute:
        logger.info("Computing Phase 3.4 microstructure alphas (T+3/T+5)...")
        try:
            from omega.quant.alpha.phase34 import (
                PHASE34_ALPHA_COLUMNS,
                compute_phase34_microstructure_alphas,
            )

            if compute_phase34_microstructure_alphas is not None:
                df_phase34 = compute_phase34_microstructure_alphas(
                    df_out,
                    symbol_col=symbol_col,
                    date_col="date",
                    open_col="open",
                    high_col="high",
                    low_col="low",
                    close_col="close",
                    volume_col="volume",
                )

                missing_p34_cols = [
                    col
                    for col in PHASE34_ALPHA_COLUMNS
                    if col not in df_phase34.columns
                ]
                if missing_p34_cols:
                    raise ValueError(
                        "Missing required Phase 3.4 alpha columns: "
                        f"{missing_p34_cols}"
                    )

                p34_cols = [
                    c
                    for c in df_phase34.columns
                    if c.startswith("alpha_p34_") and c not in alphas_dict
                ]
                for col in p34_cols:
                    alphas_dict[col] = df_phase34[col]
                logger.info(
                    f"   Added {len(p34_cols)} "
                    "Phase 3.4 microstructure alphas"
                )
        except Exception as e:
            logger.error(
                f"Failed to compute Phase 3.4 microstructure alphas: {e}"
            )
            raise

    # ========== HYBRID REGIME ALPHAS (v1) ==========
    if "hybrid_regime" in groups_to_compute:
        logger.info("Computing hybrid regime alphas (v1)...")
        try:
            from .hybrid_regime_alpha import (
                compute_all_hybrid_regime_alphas,
                HYBRID_REGIME_ALPHA_COLUMNS,
            )

            hr_signals = compute_all_hybrid_regime_alphas(
                df_out, symbol_col=symbol_col
            )
            for name, series in hr_signals.items():
                alphas_dict[name] = series
            logger.info(
                f"   Added {len(hr_signals)} hybrid regime v1 alphas"
            )
        except Exception as e:
            logger.warning(f"Failed to compute hybrid regime v1 alphas: {e}")

    # ========== HYBRID REGIME V2 ALPHAS ==========
    if "hybrid_regime_v2" in groups_to_compute:
        logger.info("Computing hybrid regime v2 expansion alphas...")
        try:
            from .hybrid_regime_alpha import (
                compute_all_hybrid_regime_v2_alphas,
                HYBRID_REGIME_V2_COLUMNS,
            )

            hr_v2_signals = compute_all_hybrid_regime_v2_alphas(
                df_out, symbol_col=symbol_col
            )
            for name, series in hr_v2_signals.items():
                alphas_dict[name] = series
            logger.info(
                f"   Added {len(hr_v2_signals)} hybrid regime v2 alphas"
            )
        except Exception as e:
            logger.warning(
                f"Failed to compute hybrid regime v2 alphas: {e}"
            )

    # Concatenate all alpha columns to df_out in a single operation
    if alphas_dict:
        df_out = pd.concat(
            [df_out, pd.DataFrame(alphas_dict, index=df_out.index)], axis=1
        )

    # Final sanitization
    alpha_cols = [col for col in df_out.columns if col.startswith("alpha_")]
    df_out[alpha_cols] = df_out[alpha_cols].replace([np.inf, -np.inf], np.nan)

    # ========== PROMOTED ALPHAS ==========
    try:
        from omega.quant.alpha.promoted import compute_promoted_alphas

        logger.info(
            "Computing promoted alphas via compute_promoted_alphas()..."
        )
        df_promoted = compute_promoted_alphas(df_out)
        promoted_cols = [
            c for c in df_promoted.columns if c not in df_out.columns
        ]
        if promoted_cols:
            df_out = pd.concat([df_out, df_promoted[promoted_cols]], axis=1)
        logger.info(f"   Added {len(promoted_cols)} promoted alphas")
    except Exception as e:
        logger.warning(f"Failed to compute promoted alphas: {e}")

    # Reorder columns to match baseline exactly for parity verification
    expected_cols = [
        "date",
        symbol_col,
        "open",
        "high",
        "low",
        "close",
        "volume",
        "sector",
        "alpha_roc_5",
        "alpha_roc_10",
        "alpha_roc_20",
        "alpha_roc_60",
        "alpha_roc_120",
        "alpha_roc_252",
        "alpha_rsi_7",
        "alpha_rsi_14",
        "alpha_rsi_21",
        "alpha_rsi_28",
        "alpha_ret_5d",
        "alpha_ret_20d",
        "alpha_ret_60d",
        "alpha_ret_120d",
        "alpha_mom_5_20",
        "alpha_mom_20_60",
        "alpha_mom_60_120",
        "alpha_atr_14_norm",
        "alpha_hist_vol_10",
        "alpha_hist_vol_20",
        "alpha_hist_vol_60",
        "alpha_downside_vol_20",
        "alpha_downside_vol_60",
        "alpha_parkinson_vol_10",
        "alpha_parkinson_vol_20",
        "alpha_parkinson_vol_60",
        "alpha_garman_klass_vol_20",
        "alpha_yang_zhang_vol_20",
        "alpha_vol_ma_ratio_5_20",
        "alpha_vol_ma_ratio_10_60",
        "alpha_illiquidity_amihud_20",
        "alpha_illiquidity_amihud_60",
        "alpha_adv_20d",
        "alpha_adv_60d",
        "alpha_zero_trade_freq_20",
        "alpha_zero_trade_freq_60",
        "alpha_obv_change_20",
        "alpha_liquidity_quality",
        "alpha_vn_amihud_liq_reversal",
        "alpha_vn_illiq_regime_penalty",
        "alpha_vn_volume_shock_reversal",
        "alpha_vn_turnover_exhaustion",
        "alpha_dist_ma_5",
        "alpha_dist_ma_10",
        "alpha_dist_ma_20",
        "alpha_dist_ma_50",
        "alpha_dist_ma_60",
        "alpha_dist_ma_100",
        "alpha_dist_ma_200",
        "alpha_dist_high_60",
        "alpha_dist_high_120",
        "alpha_dist_high_252",
        "alpha_dist_low_60",
        "alpha_dist_low_120",
        "alpha_dist_low_252",
        "alpha_body_size",
        "alpha_upper_shadow",
        "alpha_lower_shadow",
        "alpha_gap_return",
        "alpha_candle_range",
        "alpha_wick_ratio",
        "alpha_bb_dist_10",
        "alpha_bb_dist_20",
        "alpha_bb_dist_40",
        "alpha_bb_dist_60",
        "alpha_bb_dist_120",
        "alpha_rsi_crossover_5_20",
        "alpha_rsi_crossover_20_120",
        "alpha_rsi_crossover_60_120",
        "alpha_rsi_divergence",
        "alpha_vn_bollinger_snapback",
        "alpha_vn_rsi_divergence_reversal",
        "alpha_vn_sector_neutral_residual_reversion",
        "alpha_vn_close_location_reversion",
        "alpha_vol_momentum_5",
        "alpha_vol_momentum_10",
        "alpha_vol_momentum_20",
        "alpha_price_acceleration",
        "alpha_sector_rel_momentum_20",
        "alpha_sector_rel_momentum_60",
        "alpha_limit_lock_streak",
        "alpha_t2_momentum_adj",
        "alpha_penny_trap_score",
        "alpha_smart_money_lite",
        "alpha_vn_t2_momentum_diff",
        "alpha_vn_penny_trap_risk",
        "alpha_liquidity_quality_score",
        "alpha_vn_limit_unlock_exhaustion",
        "alpha_vn_t2_settlement_supply_overhang",
        "alpha_vn_t2_cash_recycling_bounce",
        "alpha_vn_001_post_settlement_momentum",
        "alpha_vn_002_limit_band_reversion",
        "alpha_vn_003_foreign_flow_divergence",
        "alpha_vn_004_intraday_persistence",
        "alpha_vn_005_liquidity_adjusted_reversal",
        "alpha_vn_foreign_flow_persistence",
        "alpha_vn_foreign_absorption_reversal",
        "alpha_vn_foreign_room_squeeze",
        "alpha_vn_limit_lock_continuation",
        "alpha_stock_sector_corr",
        "alpha_market_correlation",
        "alpha_pair_correlation",
        "alpha_vwap_distance",
        "alpha_twap_deviation",
        "alpha_close_vwap_ratio",
        "alpha_volume_weighted_return",
        "alpha_turtle_traders",
        "alpha_inertia",
        "alpha_relative_strength",
        "alpha_acceleration_index",
        "alpha_zscore",
        "alpha_percentile_rank",
        "alpha_consecutive_up_days",
        "alpha_cross_sectional_zscore",
        "alpha_relative_strength_universe",
        "alpha_vwap_deviation",
        "alpha_price_impact",
        "alpha_absorption",
        "alpha_order_imbalance",
        "alpha_foreign_persistence",
        "alpha_roll_effective_spread_20",
        "alpha_daily_vpin_toxicity_20",
        "alpha_range_impact_stress_20",
        "alpha_liquidity_drought_acceleration_20_60",
        "alpha_l2_depth_imbalance_5",
        "alpha_p34_volatility_compression_5",
        "alpha_p34_volume_clock_acceleration_10",
        "alpha_p34_kyle_lambda_20",
        "alpha_p34_tick_signed_volume_imbalance_5",
        "alpha_p34_close_auction_drift_10",
        "alpha_p34_liquidity_provision_ratio_10",
        "alpha_p34_micro_momentum_5_20",
        "mom_10d",
        "mom_3d",
        "mom_1d",
        "rsi_10",
    ]
    existing_expected = [c for c in expected_cols if c in df_out.columns]
    other_cols = [c for c in df_out.columns if c not in existing_expected]
    df_out = df_out[existing_expected + other_cols]

    total_generated = len(alpha_cols) + len(promoted_cols)
    logger.info(
        "Ultimate alpha arsenal computation complete. "
        f"Generated {total_generated} alphas."
    )

    return df_out
