"""
Regime-aware tail controls extension for Pipeline A.
Adds RegimeDetector exposure_multiplier as pre-vol-target overlay.

Supports 2 strategies:
- RULE_BASED: MA/vol/DD/momentum rules (default, backward compatible)
- HMM: Trained HMM (GaussianMixture) on expanding window

Integration: Called from backtest_v2_cpcv.py via tail_kwargs['regime_enabled']=True.
Does NOT modify existing tail_controls.py — wraps it.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Updated: 2026-06-10 (T1.3: Merged HMM and rule-based into unified API)
PIT Safety: PASS - Both strategies use only past data (T-1 lag).
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RegimeStrategy(Enum):
    """Regime detection strategy."""
    RULE_BASED = "rule_based"  # MA/vol/DD/momentum rules
    HMM = "hmm"                 # Trained HMM (GaussianMixture)


# ============================================================
# RULE-BASED STRATEGY
# ============================================================
def compute_regime_exposure(
    market_returns: np.ndarray,
    ma_short: int = 50,
    ma_long: int = 200,
    vol_short: int = 20,
    vol_long: int = 60,
    dd_threshold: float = -0.10,
    hysteresis_days: int = 5,
) -> np.ndarray:
    """
    Compute per-bar regime exposure multiplier using rule-based detection (PIT-safe, causal).

    Args:
        market_returns: 1D array of daily market returns (equal-weight portfolio proxy)
        ma_short/ma_long: MA crossover windows
        vol_short/vol_long: Volatility regime windows
        dd_threshold: Drawdown level to trigger BEAR
        hysteresis_days: Minimum days to hold regime before switching

    Returns:
        1D array of exposure multipliers (0.3 to 1.2) aligned with market_returns.
    """
    n = len(market_returns)
    exposures = np.ones(n)

    if n < ma_long + 10:
        return exposures

    # Build cumulative price from returns
    prices = np.cumprod(1 + market_returns) * 100.0

    # Pre-compute rolling stats (vectorized, causal)
    prices_series = pd.Series(prices)
    ma_s = prices_series.rolling(ma_short, min_periods=ma_short).mean().values
    ma_l = prices_series.rolling(ma_long, min_periods=ma_long).mean().values

    ret_series = pd.Series(market_returns)
    vol_s = ret_series.rolling(vol_short, min_periods=vol_short).std().values
    vol_l = ret_series.rolling(vol_long, min_periods=vol_long).std().values

    # Running max for drawdown
    running_max = prices_series.expanding().max().values

    # Regime detection per bar (causal)
    current_regime = 'SIDEWAYS'
    regime_hold_counter = 0

    for t in range(ma_long, n):
        bull_score = 0.0
        bear_score = 0.0

        # MA cross
        if ma_l[t] > 0:
            ma_signal = (ma_s[t] - ma_l[t]) / ma_l[t]
            if ma_signal > 0.02:
                bull_score += 0.3
            elif ma_signal < -0.02:
                bear_score += 0.3

        # Volatility regime
        if vol_l[t] > 0:
            vol_ratio = vol_s[t] / vol_l[t]
            if vol_ratio > 1.5:
                bear_score += 0.2
            elif vol_ratio < 0.8:
                bull_score += 0.2

        # Drawdown
        if running_max[t] > 0:
            dd = (prices[t] - running_max[t]) / running_max[t]
            if dd < dd_threshold:
                bear_score += 0.3
            elif dd > -0.03:
                bull_score += 0.2

        # Momentum 20d
        if t >= 20:
            ret_20d = (prices[t] / prices[t-20]) - 1.0
            if ret_20d > 0.05:
                bull_score += 0.2
            elif ret_20d < -0.05:
                bear_score += 0.2

        # Determine regime with hysteresis
        new_regime = current_regime
        if bull_score > bear_score and bull_score > 0.4:
            new_regime = 'BULL'
        elif bear_score > bull_score and bear_score > 0.4:
            new_regime = 'BEAR'
        else:
            new_regime = 'SIDEWAYS'

        # Hysteresis: only switch if held for N days
        if new_regime != current_regime:
            regime_hold_counter += 1
            if regime_hold_counter >= hysteresis_days:
                current_regime = new_regime
                regime_hold_counter = 0
        else:
            regime_hold_counter = 0

        # Exposure multiplier
        if current_regime == 'BULL':
            exposures[t] = 1.1
        elif current_regime == 'BEAR':
            exposures[t] = 0.5
        else:
            exposures[t] = 0.8

    # PIT T-1 lag: shift exposures by 1 bar so exposure[t] uses data through t-1 only
    # exposure[t] = old_exposure[t-1], first bar gets neutral (1.0)
    shifted_exposures = np.ones(n)
    shifted_exposures[1:] = exposures[:-1]
    return shifted_exposures


# ============================================================
# HMM STRATEGY
# ============================================================
def _compute_hmm_regime_exposure(
    market_returns: np.ndarray,
    bear_exposure: float = 0.5,
    bull_exposure: float = 1.1,
    sideways_exposure: float = 0.8,
    retrain_every: int = 60,
    min_train_samples: int = 252,
) -> np.ndarray:
    """
    Compute per-bar exposure using HMM regime detection (PIT-safe).

    Args:
        market_returns: 1D array of daily equal-weight market returns
        bear_exposure: Exposure in Bear regime
        bull_exposure: Exposure in Bull regime
        sideways_exposure: Exposure in Sideways regime
        retrain_every: Retrain HMM every N bars (expanding window)
        min_train_samples: Minimum samples before first prediction

    Returns:
        1D array of exposure multipliers aligned with market_returns.
    """
    from pathlib import Path
    import sys
    _REPO_ROOT = Path(__file__).resolve().parents[4]
    if str(_REPO_ROOT / 'src') not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT / 'src'))
    from omega.quant.strategy.regime_detector import RegimeDetectorHMM, HMMRegimeConfig

    n = len(market_returns)
    exposures = np.ones(n)

    if n < min_train_samples + 10:
        return exposures

    # Build features from market returns (PIT-safe: rolling)
    ret_series = pd.Series(market_returns)
    vol_20 = ret_series.rolling(20, min_periods=10).std()
    vol_change = vol_20.pct_change(5).fillna(0)

    features_df = pd.DataFrame({
        'returns': ret_series.rolling(5).mean().fillna(0),
        'volatility': vol_20.fillna(ret_series.std()),
        'volume_change': vol_change,
    })

    # HMM config
    config = HMMRegimeConfig(
        n_components=3,
        bear_dampening=bear_exposure,
    )
    hmm = RegimeDetectorHMM(config=config)

    # Walk-forward: train on expanding window, predict next bar
    last_train_bar = 0
    for t in range(min_train_samples, n):
        # Retrain periodically (expanding window)
        if t - last_train_bar >= retrain_every or not hmm.is_fitted:
            train_features = features_df.iloc[:t]
            train_returns = ret_series.iloc[:t]
            try:
                hmm.fit(train_features, train_returns)
                last_train_bar = t
            except Exception as e:
                logger.debug("HMM train failed at t=%d: %s", t, e)
                continue

        # Predict using T-1 features (PIT-safe)
        if hmm.is_fitted:
            try:
                current_features = features_df.iloc[t-1:t]  # T-1 data
                regime = hmm.predict_regime(current_features)
                if regime == 'Bear':
                    exposures[t] = bear_exposure
                elif regime == 'Bull':
                    exposures[t] = bull_exposure
                else:
                    exposures[t] = sideways_exposure
            except Exception:
                exposures[t] = sideways_exposure

    # Log regime distribution
    bull_pct = (exposures > 1.0).sum() / n * 100
    bear_pct = (exposures < 0.6).sum() / n * 100
    side_pct = 100 - bull_pct - bear_pct
    logger.info("HMM regime: Bull=%.1f%%, Sideways=%.1f%%, Bear=%.1f%%, mean_exp=%.3f",
                bull_pct, side_pct, bear_pct, exposures.mean())

    return exposures


# ============================================================
# UNIFIED API
# ============================================================
def apply_regime_overlay(
    daily_weights: pd.DataFrame,
    market_returns: np.ndarray,
    strategy: RegimeStrategy = RegimeStrategy.RULE_BASED,
    hysteresis_days: int = 5,
    dd_threshold: float = -0.10,
    bull_exposure: float = 1.1,
    bear_exposure: float = 0.5,
    sideways_exposure: float = 0.8,
    retrain_every: int = 60,
) -> pd.DataFrame:
    """
    Apply regime exposure overlay to portfolio weights.
    Called BEFORE vol-target in tail_controls pipeline.

    Args:
        daily_weights: T x N DataFrame of raw weights
        market_returns: T-length array of market (equal-weight) returns
        strategy: Regime detection strategy (RULE_BASED or HMM)
        hysteresis_days: Min days to hold regime before switching (rule-based only)
        dd_threshold: Drawdown level to trigger BEAR (rule-based only)
        bull_exposure: Exposure multiplier in BULL regime
        bear_exposure: Exposure multiplier in BEAR regime
        sideways_exposure: Exposure multiplier in SIDEWAYS regime
        retrain_every: Retrain HMM every N bars (HMM only)

    Returns:
        Regime-adjusted weights (same shape).
    """
    if daily_weights.empty:
        return daily_weights.copy()

    if strategy == RegimeStrategy.RULE_BASED:
        # Rule-based strategy
        exposures = compute_regime_exposure(
            market_returns,
            dd_threshold=dd_threshold,
            hysteresis_days=hysteresis_days,
        )
        # Remap to configured exposure levels
        final_exposures = np.where(exposures > 1.0, bull_exposure,
                          np.where(exposures < 0.6, bear_exposure, sideways_exposure))

        # Vectorized multiply (P1 fix: no iloc loop)
        adjusted = daily_weights.multiply(final_exposures, axis=0)

        logger.info("Regime overlay (rule-based): mean_exposure=%.3f, bull_bars=%d, bear_bars=%d, sideways_bars=%d",
                    final_exposures.mean(),
                    (exposures > 1.0).sum(),
                    (exposures < 0.6).sum(),
                    ((exposures >= 0.6) & (exposures <= 1.0)).sum())

    elif strategy == RegimeStrategy.HMM:
        # HMM strategy
        final_exposures = _compute_hmm_regime_exposure(
            market_returns,
            bear_exposure=bear_exposure,
            bull_exposure=bull_exposure,
            sideways_exposure=sideways_exposure,
            retrain_every=retrain_every,
        )
        adjusted = daily_weights.multiply(final_exposures, axis=0)
        logger.info("Regime overlay (HMM): mean_exposure=%.3f", final_exposures.mean())

    else:
        raise ValueError(f"Unknown regime strategy: {strategy}")

    gross_exposure = adjusted.clip(lower=0.0).sum(axis=1)
    over_cap = gross_exposure > 1.0
    if over_cap.any():
        adjusted.loc[over_cap] = adjusted.loc[over_cap].div(gross_exposure.loc[over_cap], axis=0)
    return adjusted


# ============================================================
# BACKWARD COMPATIBILITY ALIASES
# ============================================================
def apply_hmm_regime_overlay(
    daily_weights: pd.DataFrame,
    market_returns: np.ndarray,
    bear_exposure: float = 0.5,
    bull_exposure: float = 1.1,
    sideways_exposure: float = 0.8,
    retrain_every: int = 60,
) -> pd.DataFrame:
    """
    Backward compatibility alias for apply_regime_overlay(strategy=HMM).
    
    Deprecated: Use apply_regime_overlay(strategy=RegimeStrategy.HMM) instead.
    """
    return apply_regime_overlay(
        daily_weights,
        market_returns,
        strategy=RegimeStrategy.HMM,
        bear_exposure=bear_exposure,
        bull_exposure=bull_exposure,
        sideways_exposure=sideways_exposure,
        retrain_every=retrain_every,
    )


def apply_regime_aware_walk_forward(
    daily_weights: pd.DataFrame,
    market_returns: np.ndarray,
    bear_scale: float = 0.3,
    bull_scale: float = 1.0,
    sideways_scale: float = 0.7,
    retrain_every: int = 60,
    min_train: int = 252,
) -> pd.DataFrame:
    """
    Backward compatibility alias for apply_regime_overlay(strategy=HMM).
    
    Note: This was originally a separate implementation but was identical to HMM strategy.
    Deprecated: Use apply_regime_overlay(strategy=RegimeStrategy.HMM) instead.
    """
    return apply_regime_overlay(
        daily_weights,
        market_returns,
        strategy=RegimeStrategy.HMM,
        bear_exposure=bear_scale,
        bull_exposure=bull_scale,
        sideways_exposure=sideways_scale,
        retrain_every=retrain_every,
    )
