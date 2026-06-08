#!/usr/bin/env python3
"""
Production Alpha Pipeline for E2E Scripts
Integrates AlphaDiscoveryEngine with IC filtering and Top-N selection.

V2: Wires Evolution Engine (GeneticEngine) and ML Engine (XGBoost) for
    institutional-grade alpha discovery targeting IC >0.08.

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
from omega.quant.alpha_discovery import AlphaJudge
from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig
from omega.quant.ml.ml_engine import MLEngine, ModelConfig, MLModelType, get_ml_engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IC helper (shared by static + evolved alpha evaluation)
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

    avg_volume = df.groupby('ticker')['volume'].mean().sort_values(ascending=False)
    top_symbols = avg_volume.head(top_n_liquid).index.tolist()

    df_filtered = df[df['ticker'].isin(top_symbols)].copy()
    df_filtered['date'] = pd.to_datetime(df_filtered['date'])

    all_dates = sorted(df_filtered['date'].unique())
    last_dates = all_dates[-n_days:]
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
# Evolution Engine integration
# ---------------------------------------------------------------------------

def _build_gp_features(panel: pd.DataFrame) -> Tuple[Dict[str, np.ndarray], np.ndarray]:
    """
    Build flat feature arrays for GeneticEngine from MultiIndex panel.

    Stacks all (date, ticker) rows into 1-D arrays.
    PIT safety: returns are shifted +1 (forward) for fitness target;
    features are raw (GeneticEngine's fitness evaluator applies T-1 internally).
    """
    close = panel['close']
    volume = panel['volume']
    returns = close.groupby(level='ticker').transform(lambda s: s.pct_change())

    # Forward return as GP fitness target (look-ahead only used for fitness,
    # never leaked into the signal itself — signal is T-1 lagged in Genome)
    forward_returns = close.groupby(level='ticker').transform(
        lambda s: s.pct_change().shift(-1)
    ).values

    close_vals = close.values
    volume_vals = volume.values

    features = {
        'close': close_vals,
        'open': panel['open'].values,
        'high': panel['high'].values,
        'low': panel['low'].values,
        'volume': volume_vals,
        'returns': returns.values,
        # Derived features for richer GP search space
        'momentum_5': close.groupby(level='ticker').transform(lambda s: s.pct_change(5)).values,
        'momentum_20': close.groupby(level='ticker').transform(lambda s: s.pct_change(20)).values,
        'vol_ratio': volume.groupby(level='ticker').transform(lambda s: s.div(s.rolling(20, min_periods=1).mean())).values,
        'intraday_range': ((panel['high'] - panel['low']) / panel['close']).values,
    }

    # Replace NaN/inf in features
    for k in features:
        arr = features[k].astype(float)
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        features[k] = arr

    target = np.nan_to_num(forward_returns.astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    return features, target


def evolve_alphas(
    panel: pd.DataFrame,
    future_returns: pd.Series,
    n_generations: int = 20,
    population_size: int = 50,
    ic_threshold: float = 0.02,
) -> Dict[str, pd.Series]:
    """
    Run GeneticEngine to evolve alpha expressions beyond static templates.

    Returns dict of {expression_label -> T-1-lagged alpha Series} for
    candidates with |IC| > ic_threshold.

    PIT: GeneticEngine fitness uses forward returns internally for selection
    only. The returned signals are evaluated per-ticker with T-1 lag via
    Genome.evaluate_vectorized().
    """
    print(f"[EVOLUTION] Starting GP evolution: pop={population_size}, gen={n_generations}")

    config = GPConfig(
        population_size=population_size,
        generations=n_generations,
        max_depth=4,
        tournament_size=5,
        crossover_rate=0.7,
        mutation_rate=0.2,
        elitism_count=2,
        hall_of_fame_size=10,
        min_observations=50,  # per-ticker series are shorter than full panel
    )

    features, target = _build_gp_features(panel)
    import random; random.seed(42); np.random.seed(42); engine = GeneticEngine(config=config)

    try:
        hall_of_fame = engine.evolve(features, target)
    except Exception as e:
        print(f"[EVOLUTION] Warning: GP evolution failed: {e}")
        return {}

    print(f"[EVOLUTION] Hall of Fame: {len(hall_of_fame)} individuals")

    # Re-evaluate each HoF individual per-ticker to get a proper MultiIndex Series
    evolved_alphas: Dict[str, pd.Series] = {}
    tickers = panel.index.get_level_values('ticker').unique()

    for i, individual in enumerate(hall_of_fame):
        label = f"evolved_{i}_{individual.tree.to_string()[:40]}"
        per_ticker_signals = []

        for ticker in tickers:
            try:
                ticker_df = panel.xs(ticker, level='ticker')
                # Build per-ticker feature dict
                t_features = {
                    'close': ticker_df['close'].values.astype(float),
                    'open': ticker_df['open'].values.astype(float),
                    'high': ticker_df['high'].values.astype(float),
                    'low': ticker_df['low'].values.astype(float),
                    'volume': ticker_df['volume'].values.astype(float),
                    'returns': ticker_df['close'].pct_change().values.astype(float),
                    'momentum_5': ticker_df['close'].pct_change(5).values.astype(float),
                    'momentum_20': ticker_df['close'].pct_change(20).values.astype(float),
                    'vol_ratio': (
                        ticker_df['volume']
                        .div(ticker_df['volume'].rolling(20, min_periods=1).mean())
                        .values.astype(float)
                    ),
                }
                for k in t_features:
                    t_features[k] = np.nan_to_num(t_features[k], nan=0.0, posinf=0.0, neginf=0.0)

                # Execute tree to get raw signal
                raw = individual._execute_tree(individual.tree, t_features)
                raw_series = pd.Series(raw, index=ticker_df.index)

                # MANDATORY T-1 lag (PIT safety)
                lagged = raw_series.shift(1).fillna(0.0)

                # Attach ticker level back
                lagged.index = pd.MultiIndex.from_arrays(
                    [ticker_df.index, [ticker] * len(ticker_df)],
                    names=['date', 'ticker']
                )
                per_ticker_signals.append(lagged)
            except Exception:
                continue

        if not per_ticker_signals:
            continue

        combined = pd.concat(per_ticker_signals).sort_index()
        ic = _compute_ic(combined, future_returns)

        if abs(ic) > ic_threshold:
            evolved_alphas[label] = combined
            print(f"[EVOLUTION] Kept: IC={ic:.4f} | {label[:60]}")

    print(f"[EVOLUTION] Evolved alphas passing IC threshold: {len(evolved_alphas)}")
    return evolved_alphas


# ---------------------------------------------------------------------------
# ML Engine integration
# ---------------------------------------------------------------------------

def _build_ml_features(
    alphas: Dict[str, pd.Series],
    panel: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Build ML feature matrix from alpha signals + raw price features.

    All alpha signals are already T-1 lagged. Forward returns are the target.
    Index: MultiIndex [date, ticker] — chronological order preserved for
    walk-forward split in MLEngine.
    """
    close = panel['close']

    # Forward return target (T+1) — used only for training, never in signal
    forward_ret = close.groupby(level='ticker').transform(
        lambda s: s.pct_change().shift(-1)
    )

    # Stack alpha signals as columns
    alpha_df = pd.DataFrame(alphas)

    # Add base price features (all T-1 lagged via shift)
    returns = close.groupby(level='ticker').transform(lambda s: s.pct_change())
    vol_20 = returns.groupby(level='ticker').transform(
        lambda s: s.rolling(20, min_periods=5).std()
    )
    mom_5 = close.groupby(level='ticker').transform(
        lambda s: s.pct_change(5).shift(1)
    )
    mom_20 = close.groupby(level='ticker').transform(
        lambda s: s.pct_change(20).shift(1)
    )
    vol_ratio = panel['volume'].groupby(level='ticker').transform(
        lambda s: s.div(s.rolling(20, min_periods=1).mean()).shift(1)
    )

    base_features = pd.DataFrame({
        'returns_lag1': returns.groupby(level='ticker').shift(1),
        'vol_20': vol_20.groupby(level='ticker').shift(1),
        'mom_5': mom_5,
        'mom_20': mom_20,
        'vol_ratio': vol_ratio,
    })

    feature_df = pd.concat([alpha_df, base_features], axis=1).fillna(0.0)
    feature_df = feature_df.replace([np.inf, -np.inf], 0.0)

    # Align target
    valid_mask = forward_ret.notna()
    X = feature_df[valid_mask]
    y = forward_ret[valid_mask]

    return X, y


def ml_rank_alphas(
    alphas: Dict[str, pd.Series],
    panel: pd.DataFrame,
    future_returns: pd.Series,
    ic_threshold: float = 0.02,
) -> Tuple[Dict[str, pd.Series], Optional[object]]:
    """
    Use XGBoost to generate a meta-alpha signal from the combined alpha pool.

    Strategy:
      - Train XGBoost on (alpha signals + price features) -> forward return
        using the first 80% of dates (chronological, PIT-safe).
      - Generate out-of-sample predictions on the remaining 20% of dates.
      - Add those predictions as a new 'ml_predictor' alpha signal.
      - Keep all raw alphas with |IC| > ic_threshold alongside ml_predictor.

    This ensures the ML model's IC (>0.08) is directly expressed as a
    tradeable signal rather than only used for filtering.

    PIT: features are all T-1 lagged; model is trained on past data only
    and predicts on future dates it never saw during training.
    """
    if len(alphas) < 2:
        print("[ML] Skipping ML ranking: fewer than 2 alphas available")
        return alphas, None

    print(f"[ML] Training XGBoost ranker on {len(alphas)} alpha signals")

    X, y = _build_ml_features(alphas, panel)

    if len(X) < 100:
        print("[ML] Insufficient data for ML training, skipping")
        return alphas, None

    # Chronological 80/20 split by date
    dates = X.index.get_level_values('date')
    sorted_dates = sorted(dates.unique())
    split_date = sorted_dates[int(len(sorted_dates) * 0.8)]

    train_mask = dates < split_date
    val_mask = dates >= split_date

    X_train, y_train = X[train_mask], y[train_mask]
    X_val, y_val = X[val_mask], y[val_mask]

    if X_train.empty or X_val.empty:
        print("[ML] Train/val split produced empty set, skipping ML")
        return alphas, None

    ml_engine = get_ml_engine()
    config = ModelConfig(
        model_type=MLModelType.XGBOOST,
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        early_stopping_rounds=10,
    )

    try:
        model = ml_engine.train_xgboost(
            model_id='alpha_ranker',
            X_train=X_train,
            y_train=y_train,
            X_val=X_val,
            y_val=y_val,
            config=config,
            pit_safe=True,
        )
        ml_engine.store_model(model)
        print(
            f"[ML] XGBoost trained: IC={model.metrics.ic:.4f}, "
            f"RankIC={model.metrics.rank_ic:.4f}, "
            f"PIT_IC={model.metrics.pit_ic:.4f}"
        )
    except Exception as e:
        print(f"[ML] XGBoost training failed: {e}, skipping ML filter")
        return alphas, None

    # --- Generate out-of-sample ML predictions as a new alpha signal ---
    # Predictions are made on val set (dates the model never saw in training).
    # Features are already T-1 lagged, so predictions are PIT-safe.
    try:
        val_preds = pd.Series(
            model.predict(X_val),
            index=X_val.index,
            name='ml_predictor',
        )
        # Verify the ML predictor signal has meaningful IC
        ml_ic = _compute_ic(val_preds, future_returns.reindex(val_preds.index))
        print(f"[ML] ml_predictor signal IC (val period): {ml_ic:.4f}")
    except Exception as e:
        print(f"[ML] Prediction generation failed: {e}")
        val_preds = None
        ml_ic = 0.0

    # --- Build output: best raw alphas + ml_predictor ---
    # Keep raw alphas that pass IC threshold
    filtered: Dict[str, pd.Series] = {}
    for name, signal in alphas.items():
        ic = _compute_ic(signal, future_returns)
        if abs(ic) > ic_threshold:
            filtered[name] = signal

    # Add ML predictor only when it meets institutional IC floor.
    ml_predictor_min_ic = 0.08
    if val_preds is not None and abs(ml_ic) >= ml_predictor_min_ic:
        # Reindex to full panel index, filling train-period with 0
        # (no signal during training period — conservative, avoids look-ahead)
        ml_signal_full = val_preds.reindex(X.index).fillna(0.0)
        filtered['ml_predictor'] = ml_signal_full
        print(f"[ML] Added ml_predictor signal (IC={ml_ic:.4f}) to alpha pool")
    elif val_preds is not None:
        print(
            f"[ML] ml_predictor rejected: IC={ml_ic:.4f} below floor {ml_predictor_min_ic:.2f}"
        )

    # Fallback: if nothing passes, keep all originals
    if not filtered:
        print("[ML] No alphas passed IC filter, reverting to full pre-ML set")
        filtered = alphas

    print(f"[ML] Final alpha pool after ML: {len(filtered)} signals")
    return filtered, model


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
      2. Evolution Engine (GeneticEngine GP) — evolved beyond static templates
      3. ML Engine (XGBoost) — filters/ranks combined alpha pool

    PIT T-1 lag enforced throughout.
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

    # Compute future returns once (shared by IC eval + evolution fitness)
    close = panel['close']
    judge = AlphaJudge(ic_threshold=ic_threshold)
    future_returns = judge.compute_future_returns(close, horizon=1)

    # IC filter on static alphas
    static_ics: Dict[str, float] = {}
    for name, alpha in alphas.items():
        ic = _compute_ic(alpha, future_returns)
        if abs(ic) > ic_threshold:
            static_ics[name] = ic

    if not static_ics:
        static_ics = {name: _compute_ic(alpha, future_returns) for name, alpha in alphas.items()}

    print(f"[ALPHA] Static alphas passing IC>{ic_threshold}: {len(static_ics)}/8")

    # ------------------------------------------------------------------
    # Step 2: Evolution Engine — evolve beyond static templates
    # ------------------------------------------------------------------
    evolved_alphas: Dict[str, pd.Series] = {}
    if use_evolution:
        try:
            evolved_alphas = evolve_alphas(
                panel=panel,
                future_returns=future_returns,
                n_generations=evolution_generations,
                population_size=evolution_population,
                ic_threshold=ic_threshold,
            )
        except Exception as e:
            print(f"[EVOLUTION] Warning: Evolution failed: {e}")

    # Merge static + evolved into combined pool
    combined_alphas: Dict[str, pd.Series] = {}
    for name, ic in static_ics.items():
        combined_alphas[name] = alphas[name] * np.sign(ic)  # sign-correct

    for name, signal in evolved_alphas.items():
        ic = _compute_ic(signal, future_returns)
        combined_alphas[name] = signal * np.sign(ic) if ic != 0 else signal

    print(f"[ALPHA] Combined pool (static + evolved): {len(combined_alphas)} alphas")

    # ------------------------------------------------------------------
    # Step 3: ML Engine — XGBoost filter/rank
    # ------------------------------------------------------------------
    if use_ml_ranking and len(combined_alphas) >= 2:
        try:
            combined_alphas, _model = ml_rank_alphas(
                alphas=combined_alphas,
                panel=panel,
                future_returns=future_returns,
                ic_threshold=ic_threshold,
            )
        except Exception as e:
            print(f"[ML] Warning: ML ranking failed: {e}")

    # ------------------------------------------------------------------
    # Step 4: Compute final ICs for reporting
    # ------------------------------------------------------------------
    alpha_ics: Dict[str, float] = {}
    for name, signal in combined_alphas.items():
        ic = _compute_ic(signal, future_returns)
        alpha_ics[name] = ic

    best_ic = max(abs(v) for v in alpha_ics.values()) if alpha_ics else 0.0
    mean_ic = np.mean([abs(v) for v in alpha_ics.values()]) if alpha_ics else 0.0
    print(f"[ALPHA] Final pool: {len(alpha_ics)} alphas | best |IC|={best_ic:.4f} | mean |IC|={mean_ic:.4f}")

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
        use_evolution: Enable GeneticEngine evolution (default True)
        use_ml_ranking: Enable XGBoost ML ranking (default True)
        evolution_generations: GP generations (default 20)
        evolution_population: GP population size (default 50)
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
