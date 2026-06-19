# flake8: noqa
"""
Ultimate Alpha Arsenal - Compatibility Shim Wrapper

Exposes the modularized package `omega.quant.alpha` to maintain
backward compatibility. This is a shim wrapper that delegates
calculation to the modular package.
"""
import warnings

warnings.simplefilter('always', DeprecationWarning)
warnings.warn(
    "omega.quant.ultimate_alpha_arsenal is deprecated; import from omega.quant.alpha.arsenal instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .alpha.cross_sectional import (
    compute_cross_sectional_zscore,
    compute_relative_strength_universe,
)
from .alpha.momentum_extensions import (
    compute_turtle_traders,
    compute_inertia,
    compute_relative_strength,
    compute_acceleration_index,
)
from .alpha.volume_profile import (
    compute_vwap_distance,
    compute_twap_deviation,
    compute_close_vwap_ratio,
    compute_volume_weighted_return,
)
from .alpha.correlation import (
    compute_stock_sector_correlation,
    compute_market_correlation,
    compute_pair_correlation,
)
from .alpha.vn_specific import (
    compute_limit_lock_streak,
    compute_t2_momentum_adjustment,
    compute_penny_trap_score,
    compute_smart_money_lite,
    compute_vn_amihud_liquidity_reversal,
    compute_vn_illiq_regime_penalty,
    compute_vn_volume_shock_reversal,
    compute_vn_turnover_exhaustion,
    compute_vn_bollinger_snapback,
    compute_vn_rsi_divergence_reversal,
    compute_vn_sector_neutral_residual_reversion,
    compute_vn_close_location_reversion,
    compute_vn_foreign_flow_persistence,
    compute_vn_foreign_absorption_reversal,
    compute_vn_foreign_room_squeeze,
    compute_vn_limit_lock_continuation,
    alpha_vn_limit_unlock_exhaustion,
    alpha_vn_t2_settlement_supply_overhang,
    alpha_vn_t2_cash_recycling_bounce,
    alpha_vn_001_post_settlement_momentum,
    alpha_vn_002_limit_band_reversion,
    alpha_vn_003_foreign_flow_divergence,
    alpha_vn_004_intraday_persistence,
    alpha_vn_005_liquidity_adjusted_reversal,
    alpha_vn_t2_momentum_diff,
    alpha_vn_penny_trap_risk,
)
from .alpha.money_flow import (
    compute_volume_momentum,
    compute_price_acceleration,
    compute_sector_relative_momentum,
)
from .alpha.mean_reversion import (
    compute_bollinger_distance,
    compute_rsi_crossover,
    compute_bb_distance_multi,
    compute_rsi_divergence,
    compute_zscore,
    compute_percentile_rank,
    compute_consecutive_up_days,
)
from .alpha.price_action import (
    compute_candle_range,
    compute_wick_ratio,
    compute_body_size,
    compute_upper_shadow,
    compute_lower_shadow,
    compute_gap_return,
)
from .alpha.trend import (
    compute_distance_to_ma,
    compute_distance_to_high,
    compute_distance_to_low,
    compute_ma_distance_multi,
)
from .alpha.liquidity import (
    compute_volume_ma_ratio,
    compute_illiquidity_amihud,
    compute_adv,
    compute_zero_trade_frequency,
    compute_obv_change,
    compute_liquidity_quality_score,
    alpha_liquidity_quality_score,
)
from .alpha.volatility import (
    compute_atr_normalized,
    compute_historical_volatility,
    compute_downside_volatility,
    compute_parkinson_volatility,
    compute_garman_klass_volatility,
    compute_yang_zhang_volatility,
)
from .alpha.momentum import (
    compute_roc,
    compute_momentum_acceleration,
)
from .alpha.primitives import (
    _safe_divide,
    _round_to_board_lot,
    compute_rsi,
    compute_returns,
)
from .alpha.metadata import get_alpha_metadata
from .alpha.arsenal import compute_ultimate_alphas
import warnings
import logging
import pandas as pd
import numpy as np
from typing import Optional, List

# Emit deprecation warning on import
warnings.warn(
    "ultimate_alpha_arsenal is deprecated; import from "
    "omega.quant.alpha instead. Note: The modular "
    "omega.quant.alpha package is now preferred.",
    DeprecationWarning,
    stacklevel=2,
)

# Import and expose the core orchestration API

# Import and expose resource monitoring
try:
    from omega.core.memory.resource_monitor import (
        limit_memory,
        assert_memory_safe,
    )
except ImportError:
    from .alpha.helpers import limit_memory, assert_memory_safe

# Import and expose helpers and primitives

# Import and expose momentum alphas

# Import and expose volatility alphas

# Import and expose liquidity alphas

# Import and expose trend alphas

# Import and expose price action alphas

# Import and expose mean reversion alphas

# Import and expose money flow alphas

# Import and expose VN-specific alphas

# Import and expose correlation-based alphas

# Import and expose volume profile alphas

# Import and expose momentum extensions

# Import and expose cross-sectional alphas

# Expose market microstructure alphas from parent package
try:
    from omega.quant.strategy.market_microstructure import (
        MICROSTRUCTURE_ALPHA_COLUMNS,
        compute_microstructure_alphas,
    )
except ImportError:
    compute_microstructure_alphas = None
    MICROSTRUCTURE_ALPHA_COLUMNS = ()

# Expose Phase 3.4 microstructure alphas from parent package
try:
    from omega.quant.alpha.phase34 import (
        PHASE34_ALPHA_COLUMNS,
        compute_phase34_microstructure_alphas,
        get_phase34_alpha_metadata,
    )
except ImportError:
    compute_phase34_microstructure_alphas = None
    PHASE34_ALPHA_COLUMNS = ()
    get_phase34_alpha_metadata = None
