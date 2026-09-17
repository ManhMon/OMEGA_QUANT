"""
Alpha Metadata Registry

Version: v21.38-Modular
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-06-10

This module contains metadata for all alpha factors in the
Ultimate Alpha Arsenal.
"""


def get_alpha_metadata() -> dict:
    """
    Return metadata for all alphas in the ultimate arsenal (130+ alphas).

    Returns:
        Dictionary with alpha names as keys and metadata as values
    """
    return {
        # MOMENTUM (17)
        "alpha_roc_5": {
            "category": "Momentum",
            "description": "5-day Rate of Change",
            "source": "momentum",
        },
        "alpha_roc_10": {
            "category": "Momentum",
            "description": "10-day Rate of Change",
            "source": "momentum",
        },
        "alpha_roc_20": {
            "category": "Momentum",
            "description": "20-day Rate of Change",
            "source": "momentum",
        },
        "alpha_roc_60": {
            "category": "Momentum",
            "description": "60-day Rate of Change",
            "source": "momentum",
        },
        "alpha_roc_120": {
            "category": "Momentum",
            "description": "120-day Rate of Change",
            "source": "momentum",
        },
        "alpha_roc_252": {
            "category": "Momentum",
            "description": "252-day Rate of Change",
            "source": "momentum",
        },
        "alpha_rsi_7": {
            "category": "Momentum",
            "description": "7-day RSI",
            "source": "momentum",
        },
        "alpha_rsi_14": {
            "category": "Momentum",
            "description": "14-day RSI",
            "source": "momentum",
        },
        "alpha_rsi_21": {
            "category": "Momentum",
            "description": "21-day RSI",
            "source": "momentum",
        },
        "alpha_rsi_28": {
            "category": "Momentum",
            "description": "28-day RSI",
            "source": "momentum",
        },
        "alpha_ret_5d": {
            "category": "Momentum",
            "description": "5-day return",
            "source": "momentum",
        },
        "alpha_ret_20d": {
            "category": "Momentum",
            "description": "20-day return",
            "source": "momentum",
        },
        "alpha_ret_60d": {
            "category": "Momentum",
            "description": "60-day return",
            "source": "momentum",
        },
        "alpha_ret_120d": {
            "category": "Momentum",
            "description": "120-day return",
            "source": "momentum",
        },
        "alpha_mom_5_20": {
            "category": "Momentum",
            "description": "Momentum acceleration (5d-20d)",
            "source": "momentum",
        },
        "alpha_mom_20_60": {
            "category": "Momentum",
            "description": "Momentum acceleration (20d-60d)",
            "source": "momentum",
        },
        "alpha_mom_60_120": {
            "category": "Momentum",
            "description": "Momentum acceleration (60d-120d)",
            "source": "momentum",
        },
        # VOLATILITY (11)
        "alpha_atr_14_norm": {
            "category": "Volatility",
            "description": "Normalized ATR (14d)",
            "source": "volatility",
        },
        "alpha_hist_vol_10": {
            "category": "Volatility",
            "description": "Historical volatility (10d)",
            "source": "volatility",
        },
        "alpha_hist_vol_20": {
            "category": "Volatility",
            "description": "Historical volatility (20d)",
            "source": "volatility",
        },
        "alpha_hist_vol_60": {
            "category": "Volatility",
            "description": "Historical volatility (60d)",
            "source": "volatility",
        },
        "alpha_downside_vol_20": {
            "category": "Volatility",
            "description": "Downside volatility (20d)",
            "source": "volatility",
        },
        "alpha_downside_vol_60": {
            "category": "Volatility",
            "description": "Downside volatility (60d)",
            "source": "volatility",
        },
        "alpha_parkinson_vol_10": {
            "category": "Volatility",
            "description": "Parkinson volatility (10d)",
            "source": "volatility",
        },
        "alpha_parkinson_vol_20": {
            "category": "Volatility",
            "description": "Parkinson volatility (20d)",
            "source": "volatility",
        },
        "alpha_parkinson_vol_60": {
            "category": "Volatility",
            "description": "Parkinson volatility (60d)",
            "source": "volatility",
        },
        "alpha_garman_klass_vol_20": {
            "category": "Volatility",
            "description": "Garman-Klass volatility (20d)",
            "source": "volatility",
        },
        "alpha_yang_zhang_vol_20": {
            "category": "Volatility",
            "description": "Yang-Zhang volatility (20d)",
            "source": "volatility",
        },
        # LIQUIDITY (16)
        "alpha_vol_ma_ratio_5_20": {
            "category": "Liquidity",
            "description": "Volume MA ratio (5d/20d)",
            "source": "liquidity",
        },
        "alpha_vol_ma_ratio_10_60": {
            "category": "Liquidity",
            "description": "Volume MA ratio (10d/60d)",
            "source": "liquidity",
        },
        "alpha_illiquidity_amihud_20": {
            "category": "Liquidity",
            "description": "Amihud illiquidity (20d)",
            "source": "liquidity",
        },
        "alpha_illiquidity_amihud_60": {
            "category": "Liquidity",
            "description": "Amihud illiquidity (60d)",
            "source": "liquidity",
        },
        "alpha_adv_20d": {
            "category": "Liquidity",
            "description": "Average Daily Value (20d)",
            "source": "liquidity",
        },
        "alpha_adv_60d": {
            "category": "Liquidity",
            "description": "Average Daily Value (60d)",
            "source": "liquidity",
        },
        "alpha_zero_trade_freq_20": {
            "category": "Liquidity",
            "description": "Zero-volume day frequency (20d)",
            "source": "liquidity",
        },
        "alpha_zero_trade_freq_60": {
            "category": "Liquidity",
            "description": "Zero-volume day frequency (60d)",
            "source": "liquidity",
        },
        "alpha_obv_change_20": {
            "category": "Liquidity",
            "description": "OBV change (20d)",
            "source": "liquidity",
        },
        "alpha_liquidity_quality": {
            "category": "Liquidity",
            "description": "Liquidity quality score",
            "source": "liquidity",
        },
        "alpha_vn_amihud_liq_reversal": {
            "category": "Liquidity",
            "description": "VN Amihud liquidity reversal (zscore)",
            "source": "vn_specific",
        },
        "alpha_vn_illiq_regime_penalty": {
            "category": "Liquidity",
            "description": "VN illiquidity regime penalty (60d/20d)",
            "source": "vn_specific",
        },
        "alpha_vn_volume_shock_reversal": {
            "category": "Liquidity",
            "description": "VN volume shock reversal (zscore)",
            "source": "vn_specific",
        },
        "alpha_vn_turnover_exhaustion": {
            "category": "Liquidity",
            "description": "VN turnover exhaustion (zscore)",
            "source": "vn_specific",
        },
        # TREND (13)
        "alpha_dist_ma_5": {
            "category": "Trend",
            "description": "Distance to MA (5d)",
            "source": "trend",
        },
        "alpha_dist_ma_10": {
            "category": "Trend",
            "description": "Distance to MA (10d)",
            "source": "trend",
        },
        "alpha_dist_ma_20": {
            "category": "Trend",
            "description": "Distance to MA (20d)",
            "source": "trend",
        },
        "alpha_dist_ma_50": {
            "category": "Trend",
            "description": "Distance to MA (50d)",
            "source": "trend",
        },
        "alpha_dist_ma_60": {
            "category": "Trend",
            "description": "Distance to MA (60d)",
            "source": "trend",
        },
        "alpha_dist_ma_100": {
            "category": "Trend",
            "description": "Distance to MA (100d)",
            "source": "trend",
        },
        "alpha_dist_ma_200": {
            "category": "Trend",
            "description": "Distance to MA (200d)",
            "source": "trend",
        },
        "alpha_dist_high_60": {
            "category": "Trend",
            "description": "Distance to 60d high",
            "source": "trend",
        },
        "alpha_dist_high_120": {
            "category": "Trend",
            "description": "Distance to 120d high",
            "source": "trend",
        },
        "alpha_dist_high_252": {
            "category": "Trend",
            "description": "Distance to 252d high",
            "source": "trend",
        },
        "alpha_dist_low_60": {
            "category": "Trend",
            "description": "Distance to 60d low",
            "source": "trend",
        },
        "alpha_dist_low_120": {
            "category": "Trend",
            "description": "Distance to 120d low",
            "source": "trend",
        },
        "alpha_dist_low_252": {
            "category": "Trend",
            "description": "Distance to 252d low",
            "source": "trend",
        },
        # PRICE ACTION (6)
        "alpha_body_size": {
            "category": "Price Action",
            "description": "Candlestick body size",
            "source": "price_action",
        },
        "alpha_upper_shadow": {
            "category": "Price Action",
            "description": "Upper shadow size",
            "source": "price_action",
        },
        "alpha_lower_shadow": {
            "category": "Price Action",
            "description": "Lower shadow size",
            "source": "price_action",
        },
        "alpha_gap_return": {
            "category": "Price Action",
            "description": "Overnight gap return",
            "source": "price_action",
        },
        "alpha_candle_range": {
            "category": "Price Action",
            "description": "Candle range (high-low)",
            "source": "price_action",
        },
        "alpha_wick_ratio": {
            "category": "Price Action",
            "description": "Wick to body ratio",
            "source": "price_action",
        },
        # MEAN REVERSION (15)
        "alpha_bb_dist_10": {
            "category": "Mean Reversion",
            "description": "Bollinger distance (10d)",
            "source": "mean_reversion",
        },
        "alpha_bb_dist_20": {
            "category": "Mean Reversion",
            "description": "Bollinger distance (20d)",
            "source": "mean_reversion",
        },
        "alpha_bb_dist_40": {
            "category": "Mean Reversion",
            "description": "Bollinger distance (40d)",
            "source": "mean_reversion",
        },
        "alpha_bb_dist_60": {
            "category": "Mean Reversion",
            "description": "Bollinger distance (60d)",
            "source": "mean_reversion",
        },
        "alpha_bb_dist_120": {
            "category": "Mean Reversion",
            "description": "Bollinger distance (120d)",
            "source": "mean_reversion",
        },
        "alpha_rsi_crossover_5_20": {
            "category": "Mean Reversion",
            "description": "RSI crossover (5d-20d)",
            "source": "mean_reversion",
        },
        "alpha_rsi_crossover_20_120": {
            "category": "Mean Reversion",
            "description": "RSI crossover (20d-120d)",
            "source": "mean_reversion",
        },
        "alpha_rsi_crossover_60_120": {
            "category": "Mean Reversion",
            "description": "RSI crossover (60d-120d)",
            "source": "mean_reversion",
        },
        "alpha_rsi_divergence": {
            "category": "Mean Reversion",
            "description": "RSI-price divergence",
            "source": "mean_reversion",
        },
        "alpha_vn_bollinger_snapback": {
            "category": "Mean Reversion",
            "description": "VN Bollinger snapback (quadratic BB penalty)",
            "source": "vn_specific",
        },
        "alpha_vn_rsi_divergence_reversal": {
            "category": "Mean Reversion",
            "description": "VN RSI divergence reversal (enhanced)",
            "source": "vn_specific",
        },
        "alpha_vn_sector_neutral_residual_reversion": {
            "category": "Mean Reversion",
            "description": "VN sector-neutral residual reversion",
            "source": "vn_specific",
        },
        "alpha_vn_close_location_reversion": {
            "category": "Mean Reversion",
            "description": "VN close location value reversion",
            "source": "vn_specific",
        },
        # MONEY FLOW (7)
        "alpha_vol_momentum_5": {
            "category": "Money Flow",
            "description": "Volume momentum (5d)",
            "source": "money_flow",
        },
        "alpha_vol_momentum_10": {
            "category": "Money Flow",
            "description": "Volume momentum (10d)",
            "source": "money_flow",
        },
        "alpha_vol_momentum_20": {
            "category": "Money Flow",
            "description": "Volume momentum (20d)",
            "source": "money_flow",
        },
        "alpha_price_acceleration": {
            "category": "Money Flow",
            "description": "Price acceleration",
            "source": "money_flow",
        },
        "alpha_sector_rel_momentum_20": {
            "category": "Money Flow",
            "description": "Sector-relative momentum (20d)",
            "source": "money_flow",
        },
        "alpha_sector_rel_momentum_60": {
            "category": "Money Flow",
            "description": "Sector-relative momentum (60d)",
            "source": "money_flow",
        },
        # VN-SPECIFIC (16+)
        "alpha_limit_lock_streak": {
            "category": "VN-Specific",
            "description": "Limit lock streak",
            "source": "vn_specific",
        },
        "alpha_t2_momentum_adj": {
            "category": "VN-Specific",
            "description": "T+2 momentum adjustment",
            "source": "vn_specific",
        },
        "alpha_penny_trap_score": {
            "category": "VN-Specific",
            "description": "Penny trap risk score",
            "source": "vn_specific",
        },
        "alpha_smart_money_lite": {
            "category": "VN-Specific",
            "description": "Smart money flow (CMF + volume-price)",
            "source": "vn_specific",
        },
        "alpha_vn_foreign_flow_persistence": {
            "category": "VN-Specific",
            "description": "VN foreign net flow continuation signal",
            "source": "vn_specific",
        },
        "alpha_vn_foreign_absorption_reversal": {
            "category": "VN-Specific",
            "description": "VN foreign absorption reversal (zscore)",
            "source": "vn_specific",
        },
        "alpha_vn_foreign_room_squeeze": {
            "category": "VN-Specific",
            "description": "VN foreign room availability squeeze signal",
            "source": "vn_specific",
        },
        "alpha_vn_limit_lock_continuation": {
            "category": "VN-Specific",
            "description": "VN limit lock continuation signal",
            "source": "vn_specific",
        },
        # CORRELATION (3)
        "alpha_stock_sector_corr": {
            "category": "Correlation",
            "description": "Stock vs sector correlation (20d)",
            "source": "correlation",
        },
        "alpha_market_correlation": {
            "category": "Correlation",
            "description": "Stock vs VN-Index correlation (20d)",
            "source": "correlation",
        },
        "alpha_pair_correlation": {
            "category": "Correlation",
            "description": "Rolling correlation with market (20d)",
            "source": "correlation",
        },
        # VOLUME PROFILE (4)
        "alpha_vwap_distance": {
            "category": "Volume Profile",
            "description": "Distance from VWAP",
            "source": "volume_profile",
        },
        "alpha_twap_deviation": {
            "category": "Volume Profile",
            "description": "Deviation from TWAP baseline",
            "source": "volume_profile",
        },
        "alpha_close_vwap_ratio": {
            "category": "Volume Profile",
            "description": "Close/VWAP ratio",
            "source": "volume_profile",
        },
        "alpha_volume_weighted_return": {
            "category": "Volume Profile",
            "description": "Volume-weighted returns (20d)",
            "source": "volume_profile",
        },
        # MOMENTUM EXTENSIONS (4)
        "alpha_turtle_traders": {
            "category": "Momentum Extensions",
            "description": "Turtle trading rules signal",
            "source": "momentum_extensions",
        },
        "alpha_inertia": {
            "category": "Momentum Extensions",
            "description": "Price inertia score (20d)",
            "source": "momentum_extensions",
        },
        "alpha_relative_strength": {
            "category": "Momentum Extensions",
            "description": "RS vs universe (20d)",
            "source": "momentum_extensions",
        },
        "alpha_acceleration_index": {
            "category": "Momentum Extensions",
            "description": "Acceleration/deceleration index",
            "source": "momentum_extensions",
        },
        # CROSS-SECTIONAL (2)
        "alpha_cross_sectional_zscore": {
            "category": "Cross-Sectional",
            "description": "Cross-sectional zscore",
            "source": "cross_sectional",
        },
        "alpha_relative_strength_universe": {
            "category": "Cross-Sectional",
            "description": "Stock vs universe rank (20d)",
            "source": "cross_sectional",
        },
        # ADDITIONAL ALPHAS (35)
        "alpha_vn_t2_momentum_diff": {
            "category": "VN-Specific",
            "description": "T+2 momentum diff",
            "source": "vn_specific",
        },
        "alpha_vn_penny_trap_risk": {
            "category": "VN-Specific",
            "description": "Penny stock trap risk",
            "source": "vn_specific",
        },
        "alpha_vn_limit_unlock_exhaustion": {
            "category": "VN-Specific",
            "description": "Limit lock unlock exhaustion",
            "source": "vn_specific",
        },
        "alpha_vn_t2_settlement_supply_overhang": {
            "category": "VN-Specific",
            "description": "T+2 settlement supply overhang",
            "source": "vn_specific",
        },
        "alpha_vn_t2_cash_recycling_bounce": {
            "category": "VN-Specific",
            "description": "T+2 cash recycling bounce",
            "source": "vn_specific",
        },
        "alpha_vn_001_post_settlement_momentum": {
            "category": "VN-Specific",
            "description": "VN post settlement momentum",
            "source": "vn_specific",
        },
        "alpha_vn_002_limit_band_reversion": {
            "category": "VN-Specific",
            "description": "VN limit band reversion",
            "source": "vn_specific",
        },
        "alpha_vn_003_foreign_flow_divergence": {
            "category": "VN-Specific",
            "description": "VN foreign flow divergence",
            "source": "vn_specific",
        },
        "alpha_vn_004_intraday_persistence": {
            "category": "VN-Specific",
            "description": "VN intraday persistence",
            "source": "vn_specific",
        },
        "alpha_vn_005_liquidity_adjusted_reversal": {
            "category": "VN-Specific",
            "description": "VN liquidity adjusted reversal",
            "source": "vn_specific",
        },
        "alpha_zscore": {
            "category": "Mean Reversion",
            "description": "Z-score of price deviation",
            "source": "mean_reversion",
        },
        "alpha_percentile_rank": {
            "category": "Mean Reversion",
            "description": "Percentile rank of returns",
            "source": "mean_reversion",
        },
        "alpha_consecutive_up_days": {
            "category": "Mean Reversion",
            "description": "Number of consecutive up days",
            "source": "mean_reversion",
        },
        "alpha_liquidity_quality_score": {
            "category": "Liquidity",
            "description": "Composite liquidity quality",
            "source": "liquidity",
        },
        "alpha_vwap_deviation": {
            "category": "Liquidity",
            "description": "VWAP deviation",
            "source": "liquidity",
        },
        "alpha_price_impact": {
            "category": "Liquidity",
            "description": "Price impact of volume",
            "source": "liquidity",
        },
        "alpha_absorption": {
            "category": "Liquidity",
            "description": "Liquidity absorption ratio",
            "source": "liquidity",
        },
        "alpha_order_imbalance": {
            "category": "Liquidity",
            "description": "Order flow imbalance proxy",
            "source": "liquidity",
        },
        "alpha_foreign_persistence": {
            "category": "Liquidity",
            "description": "Foreign net flow persistence",
            "source": "liquidity",
        },
        "alpha_roll_effective_spread_20": {
            "category": "Liquidity",
            "description": "Roll 20-day effective spread",
            "source": "liquidity",
        },
        "alpha_daily_vpin_toxicity_20": {
            "category": "Liquidity",
            "description": "VPIN volume toxicity proxy",
            "source": "liquidity",
        },
        "alpha_range_impact_stress_20": {
            "category": "Liquidity",
            "description": "Range impact stress index",
            "source": "liquidity",
        },
        "alpha_liquidity_drought_acceleration_20_60": {
            "category": "Liquidity",
            "description": "Liquidity drought acceleration",
            "source": "liquidity",
        },
        "alpha_l2_depth_imbalance_5": {
            "category": "Liquidity",
            "description": "L2 depth imbalance (5d)",
            "source": "liquidity",
        },
        "alpha_p34_volatility_compression_5": {
            "category": "Microstructure",
            "description": "P3.4 volatility compression",
            "source": "microstructure",
        },
        "alpha_p34_volume_clock_acceleration_10": {
            "category": "Microstructure",
            "description": "P3.4 volume clock accel",
            "source": "microstructure",
        },
        "alpha_p34_kyle_lambda_20": {
            "category": "Microstructure",
            "description": "P3.4 Kyle's lambda proxy",
            "source": "microstructure",
        },
        "alpha_p34_tick_signed_volume_imbalance_5": {
            "category": "Microstructure",
            "description": "P3.4 tick volume imbalance",
            "source": "microstructure",
        },
        "alpha_p34_close_auction_drift_10": {
            "category": "Microstructure",
            "description": "P3.4 close auction drift",
            "source": "microstructure",
        },
        "alpha_p34_liquidity_provision_ratio_10": {
            "category": "Microstructure",
            "description": "P3.4 liquidity provision",
            "source": "microstructure",
        },
        "alpha_p34_micro_momentum_5_20": {
            "category": "Microstructure",
            "description": "P3.4 micro momentum",
            "source": "microstructure",
        },
        "mom_10d": {
            "category": "Momentum",
            "description": "10-day momentum primitive",
            "source": "primitives",
        },
        "mom_3d": {
            "category": "Momentum",
            "description": "3-day momentum primitive",
            "source": "primitives",
        },
        "mom_1d": {
            "category": "Momentum",
            "description": "1-day momentum primitive",
            "source": "primitives",
        },
        "rsi_10": {
            "category": "Momentum",
            "description": "10-day RSI primitive",
            "source": "primitives",
        },
    }
