#!/usr/bin/env python3
"""
OMEGA_QUANT Multi-Horizon Ensemble Backtest

Parameterized version of v2.4 multi-horizon backtest with configurable
horizons, optional PIT-safe dynamic universe, and selectable parallel backend.
"""

from __future__ import annotations

import argparse
import gc
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy import stats

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from omega.quant.backtest_engine import BacktestEngine
from omega.quant.evolution.genetic_alpha import enforce_t_minus_1_lag

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_HORIZONS = [15, 30, 40]
DEFAULT_DATA_PATH = _REPO_ROOT / "data" / "market_2015_now.parquet"
DEFAULT_OUTPUT_DIR = Path("data/backtest_multihorizon_ensemble_results")
DEFAULT_STATE_DIR = "data/backtest_multihorizon_ensemble_evolution"

TRAIN_END = pd.Timestamp("2022-06-30")
VAL_START = pd.Timestamp("2022-08-01")
VAL_END = pd.Timestamp("2024-06-30")
TEST_START = pd.Timestamp("2024-08-01")

CAPITAL = 10_000_000_000.0
BOARD_LOT = 100
MAX_WEIGHT = 0.05
DAILY_TURNOVER_CAP = 0.0119


def parse_horizons(raw: str | Sequence[int] | Sequence[str]) -> list[int]:
    if isinstance(raw, (list, tuple)):
        values = [int(value) for value in raw]
    else:
        parts = [part.strip() for part in str(raw).split(",") if part.strip()]
        if not parts:
            raise argparse.ArgumentTypeError("--horizons requires at least one positive integer")
        try:
            values = [int(part) for part in parts]
        except ValueError as exc:
            raise argparse.ArgumentTypeError("--horizons must be a comma-separated list of integers") from exc

    if any(value < 1 for value in values):
        raise argparse.ArgumentTypeError("--horizons values must be >= 1")
    return sorted(dict.fromkeys(values))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi-horizon ensemble backtest")
    parser.add_argument("--horizons", type=parse_horizons, default=list(DEFAULT_HORIZONS))
    parser.add_argument("--dynamic-universe", action="store_true")
    parser.add_argument("--symbol-count", type=int, default=30)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--parallel-backend",
        choices=("runner", "joblib"),
        default="runner",
        help="runner=ParallelBacktestRunner, joblib=threaded alpha signal ensemble",
    )
    parser.add_argument("--data-path", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--state-dir", default=DEFAULT_STATE_DIR)
    return parser


def resolve_workers(requested_workers: int) -> int:
    if requested_workers == 0:
        return min(os.cpu_count() or 1, 4)
    return max(1, requested_workers)


def load_market_data(data_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(str(data_path))
    df["date"] = pd.to_datetime(df["date"])
    ohlcv_cols = ["open", "high", "low", "close", "volume"]
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    df[ohlcv_cols] = df.groupby("ticker")[ohlcv_cols].ffill(limit=3)
    df = df.dropna(subset=["close", "volume"])
    df = df[(df["close"] > 0) & (df["volume"] > 0)]
    df["adv_60"] = df.groupby("ticker")["volume"].transform(
        lambda values: values.rolling(60, min_periods=20).mean()
    )
    return df.dropna(subset=["adv_60"])


def split_periods(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train_df = df[df["date"] <= TRAIN_END].copy()
    val_df = df[(df["date"] >= VAL_START) & (df["date"] <= VAL_END)].copy()
    test_df = df[df["date"] >= TEST_START].copy()
    return train_df, val_df, test_df


def get_pit_universe(period_df: pd.DataFrame, top_n: int) -> list[str]:
    if "adv_60" not in period_df.columns:
        period_df = period_df.sort_values(["ticker", "date"]).copy()
        period_df["adv_60"] = period_df.groupby("ticker")["volume"].transform(
            lambda values: values.rolling(60, min_periods=1).mean()
        )
    last_date = period_df["date"].max()
    recent = period_df[period_df["date"] >= last_date - pd.Timedelta(days=90)]
    return (
        recent.groupby("ticker")["adv_60"]
        .mean()
        .sort_values(ascending=False)
        .head(top_n)
        .index.tolist()
    )


def build_dynamic_universe_schedule(
    full_df: pd.DataFrame,
    symbol_count: int,
    lookback_days: int = 252,
    rebalance_days: int = 21,
    min_history_days: int = 60,
    start_date: pd.Timestamp | None = None,
    end_date: pd.Timestamp | None = None,
) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    try:
        from scripts.phase35_data_loader import DynamicUniverseSelector
    except ImportError:
        from phase35_data_loader import DynamicUniverseSelector

    selector = DynamicUniverseSelector(
        lookback_days=lookback_days,
        rebalance_days=rebalance_days,
        top_n=symbol_count,
        min_history_days=min_history_days,
    )
    return selector.build_dynamic_universe_schedule(
        full_df,
        start_date=start_date,
        end_date=end_date,
    )


def apply_dynamic_universe_schedule(
    period_df: pd.DataFrame,
    schedule: dict[str, list[str]],
) -> pd.DataFrame:
    if not schedule:
        return period_df.copy()

    ordered = sorted((pd.Timestamp(date_str), symbols) for date_str, symbols in schedule.items())
    slices: list[pd.DataFrame] = []
    for index, (effective_date, symbols) in enumerate(ordered):
        next_date = ordered[index + 1][0] if index + 1 < len(ordered) else None
        mask = period_df["date"] >= effective_date
        if next_date is not None:
            mask &= period_df["date"] < next_date
        mask &= period_df["ticker"].isin(symbols)
        if mask.any():
            slices.append(period_df.loc[mask])

    if not slices:
        return period_df.iloc[0:0].copy()
    return pd.concat(slices, axis=0).sort_values(["ticker", "date"]).reset_index(drop=True)


def select_period_universe(
    full_df: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    symbol_count: int,
    dynamic_universe: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    period_df = full_df[(full_df["date"] >= start_date) & (full_df["date"] <= end_date)].copy()
    if period_df.empty:
        return period_df, {
            "mode": "dynamic" if dynamic_universe else "static",
            "symbol_count": 0,
            "selected_symbols": [],
            "start_date": str(start_date.date()),
            "end_date": str(end_date.date()),
        }

    if not dynamic_universe:
        history_df = full_df[
            (full_df["date"] >= start_date - pd.Timedelta(days=90))
            & (full_df["date"] < start_date)
        ].copy()
        fallback_used = False
        if history_df.empty:
            train_df = full_df[full_df["date"] <= TRAIN_END].copy()
            train_start = train_df["date"].min()
            if pd.isna(train_start):
                train_start = period_df["date"].min()
            history_df = train_df[
                (train_df["date"] >= train_start)
                & (train_df["date"] < train_start + pd.Timedelta(days=90))
            ].copy()
            fallback_used = True

        universe = get_pit_universe(history_df, top_n=symbol_count) if not history_df.empty else []
        filtered = period_df[period_df["ticker"].isin(universe)].copy()
        return filtered, {
            "mode": "static",
            "symbol_count": len(universe),
            "selected_symbols": sorted(universe),
            "start_date": str(start_date.date()),
            "end_date": str(end_date.date()),
            "selection_source_start": str(history_df["date"].min().date()) if not history_df.empty else None,
            "selection_source_end": str(history_df["date"].max().date()) if not history_df.empty else None,
            "history_fallback_to_train_start": fallback_used,
        }

    schedule, evidence = build_dynamic_universe_schedule(
        full_df,
        symbol_count=symbol_count,
        start_date=start_date,
        end_date=end_date,
    )
    filtered = apply_dynamic_universe_schedule(period_df, schedule)
    if filtered.empty:
        logger.warning("Dynamic universe schedule empty for period. Falling back to static PIT universe.")
        fallback_df, fallback_meta = select_period_universe(
            full_df,
            start_date,
            end_date,
            symbol_count,
            dynamic_universe=False,
        )
        fallback_meta["mode"] = "dynamic_fallback_static"
        fallback_meta["schedule_size"] = len(schedule)
        fallback_meta["evidence_count"] = len(evidence)
        return fallback_df, fallback_meta

    return filtered, {
        "mode": "dynamic",
        "start_date": str(start_date.date()),
        "end_date": str(end_date.date()),
        "schedule_size": len(schedule),
        "evidence_count": len(evidence),
        "first_rebalance": min(schedule) if schedule else None,
        "last_rebalance": max(schedule) if schedule else None,
    }


def build_panel(period_df: pd.DataFrame) -> pd.DataFrame:
    panel = period_df.set_index(["date", "ticker"])[["open", "high", "low", "close", "volume"]].sort_index()
    panel.index.names = ["date", "symbol"]
    panel["returns"] = panel.groupby(level="symbol")["close"].pct_change()
    return panel.dropna(subset=["returns"])


def prepare_panels(
    df: pd.DataFrame,
    symbol_count: int,
    dynamic_universe: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    train_start = df["date"].min()
    test_end = df["date"].max()
    train_df, train_meta = select_period_universe(df, train_start, TRAIN_END, symbol_count, dynamic_universe)
    val_df, val_meta = select_period_universe(df, VAL_START, VAL_END, symbol_count, dynamic_universe)
    test_df, test_meta = select_period_universe(df, TEST_START, test_end, symbol_count, dynamic_universe)

    return (
        build_panel(train_df),
        build_panel(val_df),
        build_panel(test_df),
        {"train": train_meta, "val": val_meta, "test": test_meta},
    )


def build_multi_horizon_config(horizons: Sequence[int], state_dir: str):
    from omega.quant.evolution.multi_horizon_evolution import MultiHorizonConfig

    return MultiHorizonConfig(
        horizons=list(horizons),
        population_size=100,
        generations=15,
        max_depth=5,
        ic_threshold=0.03,
        min_hit_rate=0.51,
        corr_threshold=0.5,
        max_alphas_per_horizon=3,
        max_total_alphas=10,
        state_dir=state_dir,
    )


def run_multi_horizon_evolution(
    train_panel: pd.DataFrame,
    val_panel: pd.DataFrame,
    horizons: Sequence[int],
    state_dir: str,
):
    from omega.quant.evolution.multi_horizon_evolution import MultiHorizonEvolution

    mh_config = build_multi_horizon_config(horizons, state_dir=state_dir)
    mh_evo = MultiHorizonEvolution(config=mh_config)
    start = time.time()
    final_alphas, summary = mh_evo.run(train_panel, val_panel)
    return final_alphas, summary, time.time() - start


def extract_alpha_horizon(expression: str, default_horizon: int) -> int:
    if expression.startswith("H") and "d:" in expression:
        try:
            return int(expression.split("d:", 1)[0][1:])
        except ValueError:
            return default_horizon
    return default_horizon


def ensure_forward_returns(panel: pd.DataFrame, horizons: Iterable[int]) -> pd.DataFrame:
    enriched = panel.copy()
    unique_horizons = sorted(dict.fromkeys(int(horizon) for horizon in horizons))
    for horizon in unique_horizons:
        column = f"fwd_ret_{horizon}"
        if column not in enriched.columns:
            enriched[column] = enriched.groupby(level="symbol")["close"].pct_change(horizon).shift(-horizon)
    return enriched


def apply_fdr_filter(final_alphas: list[Any], val_panel: pd.DataFrame, horizons: Sequence[int]) -> list[Any]:
    if len(final_alphas) <= 1:
        return final_alphas

    from statsmodels.stats.multitest import multipletests

    val_with_targets = ensure_forward_returns(val_panel, horizons)
    p_values: list[float] = []
    default_horizon = horizons[0]
    for alpha in final_alphas:
        try:
            horizon = extract_alpha_horizon(alpha.expression, default_horizon)
            target_col = f"fwd_ret_{horizon}"
            val_h = val_with_targets.dropna(subset=[target_col])
            signal = enforce_t_minus_1_lag(alpha.genome.evaluate_vectorized(val_h))
            target = val_h[target_col]
            common_index = signal.index.intersection(target.index)
            _, p_value = stats.spearmanr(
                signal.loc[common_index].values,
                target.loc[common_index].values,
                nan_policy="omit",
            )
            p_values.append(p_value if not np.isnan(p_value) else 1.0)
        except Exception:
            p_values.append(1.0)

    rejected, _, _, _ = multipletests(p_values, alpha=0.15, method="fdr_bh")
    survivors = [alpha for alpha, keep in zip(final_alphas, rejected) if keep]
    return survivors or final_alphas


def apply_profit_factor_gate(final_alphas: list[Any], val_panel: pd.DataFrame, horizons: Sequence[int]) -> list[Any]:
    if not final_alphas:
        return final_alphas

    val_with_targets = ensure_forward_returns(val_panel, horizons)
    default_horizon = horizons[0]
    survivors: list[Any] = []
    for alpha in final_alphas:
        try:
            horizon = extract_alpha_horizon(alpha.expression, default_horizon)
            target_col = f"fwd_ret_{horizon}"
            val_h = val_with_targets.dropna(subset=[target_col])
            signal = enforce_t_minus_1_lag(alpha.genome.evaluate_vectorized(val_h))
            target = val_h[target_col]
            common_index = signal.index.intersection(target.index)
            aligned_ret = target.loc[common_index] * np.sign(signal.loc[common_index])
            gains = aligned_ret[aligned_ret > 0].sum()
            losses = abs(aligned_ret[aligned_ret < 0].sum())
            profit_factor = gains / losses if losses > 0 else 999.0
            if profit_factor >= 1.20:
                survivors.append(alpha)
        except Exception:
            survivors.append(alpha)
    return survivors or final_alphas


def evaluate_alpha_contribution(
    alpha: Any,
    panel: pd.DataFrame,
    price_index: pd.Index,
    symbols: Sequence[str],
) -> pd.DataFrame | None:
    try:
        signal = enforce_t_minus_1_lag(alpha.genome.evaluate_vectorized(panel))
    except Exception:
        return None

    if not isinstance(signal, pd.Series) or signal.std() <= 1e-8:
        return None

    if not isinstance(signal.index, pd.MultiIndex):
        return None

    unstacked = signal.unstack(level="symbol").reindex(index=price_index, columns=list(symbols))
    ranked = unstacked.rank(axis=1, pct=True)
    row_sums = ranked.sum(axis=1).replace(0, np.nan)
    normalized = ranked.div(row_sums, axis=0).fillna(0.0)
    ic_weight = max(abs(float(alpha.test_ic)), 0.01)
    return normalized * ic_weight


def build_combined_weights(
    final_alphas: Sequence[Any],
    test_panel: pd.DataFrame,
    workers: int,
    parallel_backend: str,
) -> tuple[pd.DataFrame, int]:
    test_prices = test_panel["close"].unstack(level="symbol").dropna(axis=1, how="all").ffill()
    symbols = list(test_prices.columns)
    eval_panel = test_panel[test_panel.index.get_level_values("symbol").isin(symbols)]
    combined = pd.DataFrame(0.0, index=test_prices.index, columns=symbols)

    if parallel_backend == "joblib" and workers > 1 and len(final_alphas) > 1:
        try:
            contributions = Parallel(
                n_jobs=workers,
                backend="threading",
                batch_size=1,
                verbose=0,
            )(
                delayed(evaluate_alpha_contribution)(alpha, eval_panel, test_prices.index, symbols)
                for alpha in final_alphas
            )
        except Exception as exc:
            logger.warning("Joblib ensemble evaluation failed (%s). Falling back to sequential execution.", exc)
            contributions = [
                evaluate_alpha_contribution(alpha, eval_panel, test_prices.index, symbols)
                for alpha in final_alphas
            ]
    else:
        contributions = [
            evaluate_alpha_contribution(alpha, eval_panel, test_prices.index, symbols)
            for alpha in final_alphas
        ]

    alpha_contributions = 0
    for contribution in contributions:
        if contribution is None:
            continue
        combined = combined.add(contribution, fill_value=0.0)
        alpha_contributions += 1

    if alpha_contributions == 0:
        raise RuntimeError("No alpha contributions available for ensemble")

    row_sums = combined.sum(axis=1).replace(0, 1.0)
    combined = combined.div(row_sums, axis=0)
    return combined, alpha_contributions


def apply_weight_constraints(weights: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    constrained = weights.copy()
    constrained = constrained.clip(upper=MAX_WEIGHT)
    row_sums = constrained.sum(axis=1).replace(0, 1.0)
    constrained = constrained.div(row_sums, axis=0)

    for row_idx in range(len(constrained)):
        for symbol in constrained.columns:
            weight = constrained.iat[row_idx, constrained.columns.get_loc(symbol)]
            if weight <= 0:
                continue
            price = prices.iat[min(row_idx, len(prices) - 1), prices.columns.get_loc(symbol)]
            if price <= 0:
                continue
            shares = int((weight * CAPITAL) / price / BOARD_LOT) * BOARD_LOT
            constrained.iat[row_idx, constrained.columns.get_loc(symbol)] = (shares * price) / CAPITAL
        row_sum = constrained.iloc[row_idx].sum()
        if row_sum > 0:
            constrained.iloc[row_idx] = constrained.iloc[row_idx] / row_sum

    for row_idx in range(1, len(constrained)):
        change = (constrained.iloc[row_idx] - constrained.iloc[row_idx - 1]).abs().sum()
        if change <= DAILY_TURNOVER_CAP:
            continue
        scale = DAILY_TURNOVER_CAP / change
        constrained.iloc[row_idx] = constrained.iloc[row_idx - 1] + (
            constrained.iloc[row_idx] - constrained.iloc[row_idx - 1]
        ) * scale
        row_sum = constrained.iloc[row_idx].sum()
        if row_sum > 0:
            constrained.iloc[row_idx] = constrained.iloc[row_idx] / row_sum

    return constrained


def prepare_backtest_inputs(test_panel: pd.DataFrame, combined_weights: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    prices = test_panel["close"].unstack(level="symbol").dropna(axis=1, how="all").ffill()
    valid = combined_weights.sum(axis=1) > 0
    weights = combined_weights.loc[valid]
    prices = prices.loc[weights.index]
    common_cols = weights.columns.intersection(prices.columns)
    return prices[common_cols], weights[common_cols]


def estimate_average_slippage(
    raw_test_panel: pd.DataFrame,
    common_cols: Sequence[str],
    combined_weights: pd.DataFrame,
) -> float:
    test_df = raw_test_panel.reset_index() if isinstance(raw_test_panel.index, pd.MultiIndex) else raw_test_panel.copy()
    if "symbol" in test_df.columns and "ticker" not in test_df.columns:
        test_df = test_df.rename(columns={"symbol": "ticker"})
    test_adv = test_df.groupby("ticker")["volume"].mean().sort_values(ascending=False)
    top30 = test_adv.head(30).index.tolist()
    top30_weight = combined_weights[[col for col in common_cols if col in top30]].sum(axis=1).mean()
    return float(5.0 * top30_weight + 10.0 * (1 - top30_weight))


def run_portfolio_backtest(
    prices: pd.DataFrame,
    weights: pd.DataFrame,
    avg_slippage: float,
    workers: int,
    parallel_backend: str,
):
    if parallel_backend == "runner":
        from omega.quant.backtest.parallel import ParallelBacktestRunner

        runner = ParallelBacktestRunner(
            num_workers=workers,
            initial_capital=CAPITAL,
            fee_rate=0.0015,
            tax_rate=0.001,
            slippage_bps=avg_slippage,
        )
        return runner.run(prices, weights)

    engine = BacktestEngine(
        initial_capital=CAPITAL,
        fee_rate=0.0015,
        tax_rate=0.001,
        slippage_bps=avg_slippage,
    )
    return engine.run(prices, weights)


def run_walk_forward_summary(
    prices: pd.DataFrame,
    weights: pd.DataFrame,
    avg_slippage: float,
    workers: int,
    parallel_backend: str,
) -> list[dict[str, float | str]]:
    wf_results: list[dict[str, float | str]] = []
    current_start = prices.index[0]
    end_date = prices.index[-1]
    while current_start + pd.DateOffset(months=12) <= end_date + pd.DateOffset(days=30):
        window_end = current_start + pd.DateOffset(months=12)
        mask = (prices.index >= current_start) & (prices.index < window_end)
        window_prices = prices.loc[mask]
        window_weights = weights.loc[mask]
        if len(window_prices) >= 20:
            window_result = run_portfolio_backtest(
                window_prices,
                window_weights,
                avg_slippage=avg_slippage,
                workers=max(1, min(workers, 2)) if parallel_backend == "runner" else 1,
                parallel_backend=parallel_backend,
            )
            wf_results.append(
                {
                    "start": str(current_start.date()),
                    "end": str(window_end.date()),
                    "return": float(window_result.metrics["total_return"]),
                    "sharpe": float(window_result.metrics["sharpe"]),
                    "max_dd": float(window_result.metrics["max_drawdown"]),
                }
            )
        current_start += pd.DateOffset(months=6)
    return wf_results


def compute_drawdown_status(bt_result: Any) -> str:
    drawdown_limit = -0.15
    if bt_result.metrics["max_drawdown"] >= drawdown_limit:
        return "OK"
    equity = bt_result.equity_curve
    drawdown = (equity - equity.expanding().max()) / equity.expanding().max()
    breach_date = drawdown[drawdown < drawdown_limit].index[0] if (drawdown < drawdown_limit).any() else None
    if breach_date is None:
        return "BREACHED"
    return f"BREACHED (halt @ {breach_date.date()})"


def save_results(output_dir: Path, summary: dict[str, Any], bt_result: Any) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "backtest_multihorizon_ensemble_results.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, default=str)
    bt_result.equity_curve.to_csv(output_dir / "equity_curve.csv")


def run_backtest(args: argparse.Namespace) -> dict[str, Any]:
    workers = resolve_workers(args.workers)
    logger.info("=" * 70)
    logger.info("MULTI-HORIZON ENSEMBLE BACKTEST")
    logger.info("=" * 70)
    logger.info(
        "Config: horizons=%s dynamic_universe=%s symbol_count=%d workers=%d backend=%s",
        args.horizons,
        args.dynamic_universe,
        args.symbol_count,
        workers,
        args.parallel_backend,
    )

    df = load_market_data(args.data_path)
    train_panel, val_panel, test_panel, universe_meta = prepare_panels(
        df,
        symbol_count=args.symbol_count,
        dynamic_universe=args.dynamic_universe,
    )
    logger.info(
        "Panels: train=%d, val=%d, test=%d",
        len(train_panel),
        len(val_panel),
        len(test_panel),
    )

    final_alphas, evo_summary, evo_time = run_multi_horizon_evolution(
        train_panel,
        val_panel,
        horizons=args.horizons,
        state_dir=args.state_dir,
    )
    final_alphas = apply_fdr_filter(final_alphas, val_panel, args.horizons)
    final_alphas = apply_profit_factor_gate(final_alphas, val_panel, args.horizons)
    if not final_alphas:
        raise SystemExit("No alphas survived multi-horizon ensemble gates")

    combined_weights, alpha_contributions = build_combined_weights(
        final_alphas,
        test_panel,
        workers=workers,
        parallel_backend=args.parallel_backend,
    )

    test_prices = test_panel["close"].unstack(level="symbol").dropna(axis=1, how="all").ffill()
    combined_weights = apply_weight_constraints(combined_weights, test_prices)
    prices, weights = prepare_backtest_inputs(test_panel, combined_weights)
    avg_slippage = estimate_average_slippage(test_panel, prices.columns, weights)

    bt_start = time.time()
    bt_result = run_portfolio_backtest(
        prices,
        weights,
        avg_slippage=avg_slippage,
        workers=workers,
        parallel_backend=args.parallel_backend,
    )
    bt_time = time.time() - bt_start
    dd_status = compute_drawdown_status(bt_result)
    wf_results = run_walk_forward_summary(
        prices,
        weights,
        avg_slippage=avg_slippage,
        workers=workers,
        parallel_backend=args.parallel_backend,
    )

    metrics = bt_result.metrics
    calmar = (bt_result.returns.mean() * 252) / abs(metrics["max_drawdown"]) if metrics["max_drawdown"] != 0 else 0.0
    avg_turnover = weights.diff().abs().sum(axis=1).mean()

    print()
    print("=" * 70)
    print("  OMEGA_QUANT MULTI-HORIZON ENSEMBLE")
    print(f"  Horizons:        {', '.join(f'{h}d' for h in args.horizons)}")
    print("=" * 70)
    print(f"  Period:          {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"  Capital:         10B VND | Symbols: {len(prices.columns)}")
    print(f"  Universe:        {'dynamic' if args.dynamic_universe else 'static'}")
    print(f"  Active Alphas:   {len(final_alphas)}")
    print(f"  Alpha Used:      {alpha_contributions}")
    print(f"  Total Return:    {metrics['total_return'] * 100:.2f}%")
    print(f"  Sharpe Ratio:    {metrics['sharpe']:.4f}")
    print(f"  Sortino Ratio:   {metrics['sortino']:.4f}")
    print(f"  Calmar Ratio:    {calmar:.4f}")
    print(f"  Max Drawdown:    {metrics['max_drawdown'] * 100:.2f}%")
    print(f"  Volatility:      {metrics['volatility'] * 100:.2f}%")
    print(f"  Win Rate:        {metrics['win_rate'] * 100:.1f}%")
    print(f"  Avg Turnover:    {avg_turnover * 100:.2f}%/day")
    print(f"  Slippage:        {avg_slippage:.1f} bps")
    print(f"  DD Limit -15%:   {dd_status}")
    if wf_results:
        print(f"  WF Avg Sharpe:   {np.mean([row['sharpe'] for row in wf_results]):.4f}")
        print(f"  WF Avg Return:   {np.mean([row['return'] for row in wf_results]) * 100:.2f}%")
    print(f"  Evolution:       {evo_time:.1f}s | Backtest: {bt_time:.1f}s")
    print(f"  Backend:         {args.parallel_backend} | Workers: {workers}")
    print("=" * 70)
    print()

    summary = {
        "version": "multihorizon-ensemble",
        "timestamp": datetime.utcnow().isoformat(),
        "strategy": "multi_horizon_ensemble",
        "horizons": list(args.horizons),
        "dynamic_universe": bool(args.dynamic_universe),
        "symbol_count": int(args.symbol_count),
        "parallel_backend": args.parallel_backend,
        "workers": int(workers),
        "evolution": evo_summary,
        "universe": universe_meta,
        "ensemble": {
            "n_alphas": len(final_alphas),
            "alpha_contributions": alpha_contributions,
        },
        "metrics": {key: float(value) for key, value in metrics.items()},
        "metrics_extra": {
            "calmar": float(calmar),
            "avg_turnover": float(avg_turnover),
            "avg_slippage": float(avg_slippage),
        },
        "walk_forward": wf_results,
        "dd_breaker": {"limit": -0.15, "status": dd_status},
        "alphas": [
            {"expr": alpha.expression[:80], "ic": alpha.test_ic, "hit": alpha.hit_rate}
            for alpha in final_alphas
        ],
    }
    save_results(args.output_dir, summary, bt_result)
    gc.collect()
    return summary


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.symbol_count < 1:
        raise SystemExit("--symbol-count must be >= 1")
    run_backtest(args)


if __name__ == "__main__":
    main()
