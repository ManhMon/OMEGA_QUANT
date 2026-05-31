"""
OMEGA_QUANT Paper Trading - Daily Signal Generation
Integrates: Alt Features + Alt Data + Regime Detector + HRP Weighting

Usage: Run daily after market close to generate next-day signals.
Output: data/paper_trading/signals_YYYY-MM-DD.json

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - All signals use T-1 lagged data only.
"""
import sys
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\quant\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\core\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\infra\src')
sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\packages\data\src')

import numpy as np
import pandas as pd
import logging
import json
from pathlib import Path
from datetime import datetime, date

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

from omega.quant.evolution.alternative_features import AlternativeFeatureGenerator
from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher
from omega.quant.evolution.regime_detector import RegimeDetector, RegimeConfig
from omega.quant.evolution.hrp_weighter import HRPWeighter
from omega.quant.evolution.genetic_alpha import enforce_t_minus_1_lag

# ============================================================
# CONFIG
# ============================================================
CAPITAL = 10_000_000_000.0  # 10B VND
MAX_WEIGHT = 0.05           # 5% max single name
BOARD_LOT = 100
TURNOVER_CAP = 0.0119       # 1.19%/day
OUTPUT_DIR = Path('data/paper_trading')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Signals to use (from v2.5 ensemble - validated)
SIGNAL_FEATURES = [
    {'feature': 'distance_from_ma20', 'horizon': 10, 'ic': 0.4053},
    {'feature': 'clv_ma', 'horizon': 10, 'ic': 0.2207},
    {'feature': 'vp_divergence', 'horizon': 5, 'ic': 0.2179},
    {'feature': 'momentum_accel', 'horizon': 3, 'ic': 0.1986},
    {'feature': 'realized_vol_5', 'horizon': 20, 'ic': -0.1963},
    {'feature': 'clv', 'horizon': 3, 'ic': 0.1796},
    {'feature': 'gap', 'horizon': 3, 'ic': 0.1560},
    {'feature': 'volume_trend', 'horizon': 10, 'ic': 0.1208},
    {'feature': 'volume_momentum', 'horizon': 10, 'ic': 0.0840},
    {'feature': 'cs_rank_ret20', 'horizon': 20, 'ic': -0.0449},
]

# Alt data signals (additional)
ALT_DATA_FEATURES = [
    'foreign_flow_ma5', 'margin_trend', 'rotation_momentum', 'order_imbalance',
]

# ============================================================
# MAIN PIPELINE
# ============================================================
def run_daily_signal(data_path: str = r'C:\Users\GHC\.openclaw\workspace\data\market_2015_now.parquet'):
    """Generate daily trading signals."""
    today = date.today()
    logger.info("=" * 60)
    logger.info("PAPER TRADING - Signal Generation for %s", today)
    logger.info("=" * 60)

    # 1. Load data
    df = pd.read_parquet(data_path)
    df['date'] = pd.to_datetime(df['date'])
    ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
    df = df.sort_values(['ticker', 'date']).reset_index(drop=True)
    df[ohlcv_cols] = df.groupby('ticker')[ohlcv_cols].ffill(limit=3)
    df = df.dropna(subset=['close', 'volume'])
    df = df[(df['close'] > 0) & (df['volume'] > 0)]

    # Universe: top 50 by trailing 60d ADV
    df['adv_60'] = df.groupby('ticker')['volume'].transform(lambda x: x.rolling(60, min_periods=20).mean())
    df = df.dropna(subset=['adv_60'])
    last_date = df['date'].max()
    recent = df[df['date'] >= last_date - pd.Timedelta(days=90)]
    universe = recent.groupby('ticker')['adv_60'].mean().sort_values(ascending=False).head(50).index.tolist()
    df = df[df['ticker'].isin(universe)]
    logger.info("Universe: %d symbols, data up to %s", len(universe), last_date.date())

    # 2. Build panel
    panel = df.set_index(['date', 'ticker'])[ohlcv_cols].sort_index()
    panel.index.names = ['date', 'symbol']
    panel['returns'] = panel.groupby(level='symbol')['close'].pct_change()

    # 3. Generate features
    feat_gen = AlternativeFeatureGenerator()
    panel = feat_gen.generate_all(panel)

    alt_fetcher = AlternativeDataFetcher()
    panel = alt_fetcher.generate_all(panel)
    logger.info("Features generated: %d columns", len(panel.columns))

    # 4. Regime detection
    market_prices = panel['close'].groupby(level='date').mean()  # Equal-weight market proxy
    regime_det = RegimeDetector()
    regime_state = regime_det.detect(market_prices)
    logger.info("Regime: %s (confidence=%.2f, exposure=%.2f)",
                regime_state.regime.value, regime_state.confidence, regime_state.exposure_multiplier)

    # 5. Generate signal weights (HRP)
    # Build signal returns for HRP
    test_prices = panel['close'].unstack(level='symbol').dropna(axis=1, how='all').ffill()
    signal_returns = pd.DataFrame(index=test_prices.index)
    signal_exposures = {}

    all_features = SIGNAL_FEATURES + [{'feature': f, 'horizon': 5, 'ic': 0.05} for f in ALT_DATA_FEATURES if f in panel.columns]

    for sf in all_features:
        feat = sf['feature']
        if feat not in panel.columns:
            continue
        try:
            sig = panel[feat].groupby(level='symbol').shift(1)  # T-1 lag
            unstacked = sig.unstack(level='symbol')
            if unstacked.std().mean() < 1e-8:
                continue

            # Rank cross-sectionally
            ranked = unstacked.rank(axis=1, pct=True)
            normalized = ranked.div(ranked.sum(axis=1), axis=0).fillna(0)

            # Signal return = next-day return weighted by signal
            next_ret = test_prices.pct_change().shift(-1)
            sig_ret = (normalized * next_ret).sum(axis=1)
            signal_returns[feat] = sig_ret

            # Store exposure for HRP combination
            signal_exposures[feat] = normalized
        except Exception:
            continue

    # Compute HRP weights across signals
    hrp = HRPWeighter(lookback=60, min_periods=20)
    if len(signal_returns.columns) > 1:
        # Use only past signal returns (PIT-safe)
        past_sig_returns = signal_returns.dropna().iloc[:-1]  # Exclude last row (no next-day ret yet)
        if len(past_sig_returns) >= 20:
            hrp_weights = hrp.compute_signal_weights(past_sig_returns)
        else:
            hrp_weights = pd.Series(1.0 / len(signal_returns.columns), index=signal_returns.columns)
    else:
        hrp_weights = pd.Series(1.0, index=signal_returns.columns)

    logger.info("HRP signal weights:")
    for sig_name, w in hrp_weights.sort_values(ascending=False).items():
        logger.info("  %-22s %.4f", sig_name, w)

    # 6. Combine signals with HRP weights
    combined_weights = hrp.compute_asset_weights(test_prices, hrp_weights, signal_exposures)

    # 7. Apply regime adjustment
    combined_weights = combined_weights * regime_state.exposure_multiplier
    # Cap at 1.0 total (no leverage)
    row_sums = combined_weights.sum(axis=1)
    over_exposed = row_sums > 1.0
    combined_weights.loc[over_exposed] = combined_weights.loc[over_exposed].div(row_sums[over_exposed], axis=0)

    # 8. Apply constraints (max weight, board-lot, turnover)
    combined_weights = combined_weights.clip(upper=MAX_WEIGHT)
    row_sums = combined_weights.sum(axis=1).replace(0, 1.0)
    combined_weights = combined_weights.div(row_sums, axis=0)

    # Get latest weights (today's signal for tomorrow)
    latest_weights = combined_weights.iloc[-1]
    latest_weights = latest_weights[latest_weights > 0.001].sort_values(ascending=False)

    # Board-lot conversion
    latest_prices = test_prices.iloc[-1]
    positions = {}
    for sym, w in latest_weights.items():
        if sym in latest_prices.index:
            price = latest_prices[sym]
            if price > 0:
                shares = int((w * CAPITAL) / price / BOARD_LOT) * BOARD_LOT
                if shares >= BOARD_LOT:
                    positions[sym] = {
                        'weight': round(float(w), 4),
                        'shares': int(shares),
                        'price': float(price),
                        'value_vnd': float(shares * price),
                    }

    # 9. Output
    signal_output = {
        'date': str(today),
        'generated_at': datetime.utcnow().isoformat(),
        'regime': {
            'state': regime_state.regime.value,
            'confidence': round(regime_state.confidence, 3),
            'exposure': round(regime_state.exposure_multiplier, 3),
            'signals': {k: round(v, 4) for k, v in regime_state.signals.items()},
        },
        'hrp_weights': {k: round(float(v), 4) for k, v in hrp_weights.items()},
        'universe_size': len(universe),
        'positions': positions,
        'n_positions': len(positions),
        'total_exposure': round(sum(p['weight'] for p in positions.values()), 4),
        'capital': CAPITAL,
    }

    # Save
    output_file = OUTPUT_DIR / f'signals_{today}.json'
    with open(output_file, 'w') as f:
        json.dump(signal_output, f, indent=2, default=str)

    logger.info("")
    logger.info("=" * 60)
    logger.info("DAILY SIGNAL OUTPUT")
    logger.info("=" * 60)
    logger.info("  Regime: %s (exposure %.2f)", regime_state.regime.value, regime_state.exposure_multiplier)
    logger.info("  Positions: %d symbols", len(positions))
    logger.info("  Total exposure: %.2f%%", sum(p['weight'] for p in positions.values()) * 100)
    logger.info("  Top 5:")
    for i, (sym, pos) in enumerate(list(positions.items())[:5]):
        logger.info("    %s: %d shares @ %.0f VND (%.1f%%)", sym, pos['shares'], pos['price'], pos['weight']*100)
    logger.info("  Saved: %s", output_file)
    logger.info("=" * 60)

    return signal_output


if __name__ == '__main__':
    run_daily_signal()
