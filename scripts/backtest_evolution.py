"""Backtest the Self-Evolving Engine on historical Vietnamese market data.

Validates that GP alpha discovery (genetic programming) adds value vs a
baseline momentum_20 alpha on data from 2015-2026.

Design
------
* Load market data from data/market_2015_now.parquet.
* Compute 10 PIT-safe features (open, high, low, close, volume, returns_1d,
  returns_5d, vol_ratio, hl_range, oc_range) - all features use prior-day
  values via .shift(1) per ticker, so signals at date D only see data <= D-1.
* Walk-forward backtest with yearly rebalance (2017-2026):
    - Train GP on every bar before year Y.
    - Take the top 5 evolved alphas from the Hall of Fame.
    - Generate equal-weight ensemble signals on year Y.
    - Compare against a momentum_20 baseline.
* Compute IC, Sharpe, Turnover and Max Drawdown per year.
* Print a summary table and save data/backtest/evolution_backtest_results.json.

PIT safety
----------
- All features lagged T-1 per ticker (groupby).
- Forward returns for IC/Sharpe lookahead are returns_1d at date D+1, but the
  signal at D only uses information up to D-1; we never train on test years.
- Yearly chronological split: train uses [:Y-1], test uses [Y].

Run:
    python scripts/backtest_evolution.py
"""

from __future__ import annotations

import json
import logging
import random
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

# Phase 6 P1 fix (codex audit 019e77a3): set seeds at module load so
# joblib parallel population evaluation is deterministic. The previous
# comment in train_gp() claimed this was already done; in fact no seed
# call existed. Set BOTH stdlib `random` (used by GeneticEngine for
# tree generation / crossover / mutation / tournament) and numpy.random
# (used in feature transforms).
random.seed(42)
np.random.seed(42)

# --- Path wiring ------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
QUANT_SRC = ROOT / "packages" / "quant" / "src"
if str(QUANT_SRC) not in sys.path:
    sys.path.insert(0, str(QUANT_SRC))

from omega.quant.evolution.genetic_engine import (  # noqa: E402
    GeneticEngine,
    GPConfig,
    GPIndividual,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backtest_evolution")

DATA_PATH = ROOT / "data" / "market_2015_now.parquet"
OUT_DIR = ROOT / "data" / "backtest"
OUT_PATH = OUT_DIR / "evolution_backtest_results.json"

FEATURE_NAMES: List[str] = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "returns_1d",
    "returns_5d",
    "vol_ratio",
    "hl_range",
    "oc_range",
]

TRAIN_START_YEAR = 2015
TEST_YEARS = list(range(2017, 2027))  # 2017..2026 inclusive
TOP_K_ALPHAS = 5


# ---------------------------------------------------------------------------
# Feature engineering (PIT safe, vectorized)
# ---------------------------------------------------------------------------
def _per_ticker_features(g: pd.DataFrame) -> pd.DataFrame:
    """Compute T-1 lagged features for one ticker (chronological)."""
    g = g.sort_values("date").copy()
    close = g["close"].astype("float64")
    open_ = g["open"].astype("float64")
    high = g["high"].astype("float64")
    low = g["low"].astype("float64")
    volume = g["volume"].astype("float64")

    # Raw daily returns and rolling stats are computed on raw series, then
    # the entire feature block is lagged by 1 bar so signals at D only
    # see information up to D-1 (T-1 PIT enforcement).
    returns_1d_raw = close.pct_change(1)
    returns_5d_raw = close.pct_change(5)
    vol_ma20 = volume.rolling(20, min_periods=5).mean()
    vol_ratio_raw = volume / (vol_ma20 + 1e-9)
    hl_range_raw = (high - low) / (close + 1e-9)
    oc_range_raw = (close - open_) / (open_ + 1e-9)

    feats = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "returns_1d": returns_1d_raw,
        "returns_5d": returns_5d_raw,
        "vol_ratio": vol_ratio_raw,
        "hl_range": hl_range_raw,
        "oc_range": oc_range_raw,
    }, index=g.index)

    # Forward 1-day return target (close-to-close); kept *unshifted* on
    # purpose. We will only use feats (T-1 lagged) to predict target_fwd1d.
    target_fwd1d = close.pct_change(1).shift(-1)

    # Apply T-1 lag to all features (defense-in-depth against lookahead).
    feats = feats.shift(1)

    out = feats.copy()
    out["target_fwd1d"] = target_fwd1d
    out["ticker"] = g["ticker"].values
    out["date"] = g["date"].values
    return out


def build_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized per-ticker feature build."""
    logger.info("Building features (T-1 lagged) for %d rows...", len(df))
    panel = df.groupby("ticker", group_keys=False, sort=False).apply(_per_ticker_features)
    panel = panel.dropna(subset=FEATURE_NAMES + ["target_fwd1d"])
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel.sort_values(["date", "ticker"]).reset_index(drop=True)
    logger.info("Panel shape: %s", panel.shape)
    return panel


def features_dict(panel: pd.DataFrame) -> Dict[str, np.ndarray]:
    """Convert feature columns to {name: ndarray} for GeneticEngine."""
    return {name: panel[name].to_numpy(dtype="float64", copy=False) for name in FEATURE_NAMES}


# ---------------------------------------------------------------------------
# Signal evaluation utilities
# ---------------------------------------------------------------------------
def _zscore_per_day(signal: pd.Series, dates: pd.Series) -> pd.Series:
    """Cross-sectional z-score per day (vectorized via groupby+transform)."""
    grp = signal.groupby(dates)
    mean = grp.transform("mean")
    std = grp.transform("std").replace(0.0, np.nan)
    z = (signal - mean) / std
    return z.fillna(0.0)


def execute_individual(ind: GPIndividual, feats: Dict[str, np.ndarray]) -> np.ndarray:
    """Run one evolved tree against a feature dict (numpy)."""
    arr = ind._execute_tree(ind.tree, feats)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    return arr


def ensemble_signal(
    panel: pd.DataFrame,
    individuals: List[GPIndividual],
) -> pd.Series:
    """Equal-weight ensemble of evolved alphas with cross-sectional z-score."""
    if not individuals:
        return pd.Series(0.0, index=panel.index)
    feats = features_dict(panel)
    n = len(panel)
    acc = np.zeros(n, dtype="float64")
    used = 0
    for ind in individuals:
        try:
            sig = execute_individual(ind, feats)
            if np.std(sig) < 1e-9:
                continue
            sig_s = pd.Series(sig, index=panel.index)
            sig_s = _zscore_per_day(sig_s, panel["date"])
            acc = acc + sig_s.to_numpy(copy=False)
            used += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("alpha execution failed: %s", exc)
            continue
    if used == 0:
        return pd.Series(0.0, index=panel.index)
    return pd.Series(acc / used, index=panel.index)


def baseline_momentum_20(panel: pd.DataFrame) -> pd.Series:
    """Baseline alpha: 20-day price momentum, T-1 lagged, cross-sectional z.

    Note (Phase 6 audit): an older multiseed pipeline produced JSON files
    referencing baseline_inverse_vol / baseline_mean_reversion /
    baseline_equal_weight. That code was removed in the 2026-05-30
    rewrite of this script and is not re-added here on purpose. To
    benchmark against more baselines, add them as separate functions and
    extend the dict written by save_results().
    """
    # close is already T-1 lagged in `panel`. Build 20d return on lagged close
    # via groupby ticker.
    close = panel["close"].astype("float64")
    by_ticker = panel.groupby("ticker", sort=False)
    mom20 = close / by_ticker["close"].shift(20) - 1.0
    z = _zscore_per_day(mom20.fillna(0.0), panel["date"])
    return z


# ---------------------------------------------------------------------------
# Performance metrics (vectorized)
# ---------------------------------------------------------------------------
def compute_metrics(
    panel: pd.DataFrame,
    signal: pd.Series,
) -> Dict[str, float]:
    """Compute IC (per-day Spearman avg), Sharpe, Turnover, Max Drawdown."""
    df = pd.DataFrame({
        "date": panel["date"].values,
        "ticker": panel["ticker"].values,
        "signal": signal.to_numpy(),
        "target": panel["target_fwd1d"].to_numpy(),
    }).dropna()

    if df.empty:
        return {"ic": 0.0, "sharpe": 0.0, "turnover": 0.0, "max_drawdown": 0.0, "n_obs": 0}

    # Cross-sectional Spearman IC per day, then average
    def _ic_one_day(group: pd.DataFrame) -> float:
        if len(group) < 5:
            return np.nan
        s = group["signal"].rank(method="average")
        t = group["target"].rank(method="average")
        if s.std(ddof=0) == 0 or t.std(ddof=0) == 0:
            return np.nan
        return float(np.corrcoef(s, t)[0, 1])

    daily_ic = df.groupby("date", sort=True).apply(_ic_one_day)
    daily_ic = daily_ic.dropna()
    ic_mean = float(daily_ic.mean()) if not daily_ic.empty else 0.0

    # Long-short equal-weighted portfolio: top quintile minus bottom quintile.
    df = df.sort_values(["date", "signal"])
    df["q"] = df.groupby("date")["signal"].transform(
        lambda x: pd.qcut(x, q=5, labels=False, duplicates="drop")
        if x.nunique() >= 5 else pd.Series(np.nan, index=x.index)
    )
    df = df.dropna(subset=["q"])
    if df.empty:
        return {"ic": ic_mean, "sharpe": 0.0, "turnover": 0.0, "max_drawdown": 0.0, "n_obs": int(len(daily_ic))}

    long_mask = df["q"] == df["q"].max()
    short_mask = df["q"] == 0
    long_ret = df.loc[long_mask].groupby("date")["target"].mean()
    short_ret = df.loc[short_mask].groupby("date")["target"].mean()
    ls_ret = (long_ret - short_ret).dropna()

    if ls_ret.empty or ls_ret.std(ddof=1) == 0:
        sharpe = 0.0
    else:
        sharpe = float(ls_ret.mean() / (ls_ret.std(ddof=1) + 1e-12) * np.sqrt(252))

    # Turnover: average daily change of long-portfolio constituents.
    long_sets = df.loc[long_mask].groupby("date")["ticker"].apply(set)
    turnover_vals: List[float] = []
    prev: set = set()
    for _, cur in long_sets.items():
        if prev:
            denom = max(len(cur), 1)
            turnover_vals.append(len(cur.symmetric_difference(prev)) / (2.0 * denom))
        prev = cur
    turnover = float(np.mean(turnover_vals)) if turnover_vals else 0.0

    # Max drawdown of the long-short equity curve
    eq = (1.0 + ls_ret).cumprod()
    if eq.empty:
        mdd = 0.0
    else:
        roll_max = eq.cummax()
        dd = eq / roll_max - 1.0
        mdd = float(dd.min())

    return {
        "ic": ic_mean,
        "sharpe": sharpe,
        "turnover": turnover,
        "max_drawdown": mdd,
        "n_obs": int(len(ls_ret)),
    }


# ---------------------------------------------------------------------------
# Walk-forward driver
# ---------------------------------------------------------------------------
def train_gp(panel_train: pd.DataFrame) -> List[GPIndividual]:
    """Run a fast GP cycle on training panel and return Hall of Fame top K."""
    cfg = GPConfig(
        population_size=100,
        generations=20,
        max_depth=4,
        tournament_size=4,
        crossover_rate=0.7,
        mutation_rate=0.25,
        elitism_count=2,
        hall_of_fame_size=10,
        diversity_threshold=0.7,
        min_observations=500,
        # Phase 6 (codex audit 019e77a3): seeds are set at module load
        # in this script (random.seed(42); np.random.seed(42)) -- see
        # the top of the file. With prefer='threads', joblib workers
        # share the parent process random state, so the n_jobs=10
        # path is deterministic given the same population_size and
        # generations.
        n_jobs=10,
    )
    feats = features_dict(panel_train)
    target = panel_train["target_fwd1d"].to_numpy(dtype="float64", copy=False)
    engine = GeneticEngine(cfg)
    engine.evolve(feats, target)
    hof = engine.hall_of_fame[:TOP_K_ALPHAS]
    return hof


def walk_forward(panel: pd.DataFrame) -> List[Dict]:
    """Run yearly walk-forward backtest from 2017..2026."""
    panel["year"] = panel["date"].dt.year
    results: List[Dict] = []

    for year in TEST_YEARS:
        train_mask = panel["year"] < year
        test_mask = panel["year"] == year
        train = panel.loc[train_mask].copy()
        test = panel.loc[test_mask].copy()
        if train.empty or test.empty:
            logger.warning("Year %s skipped (train=%d test=%d).", year, len(train), len(test))
            continue
        if train["date"].max() >= test["date"].min():
            raise RuntimeError(
                f"PIT violation for year {year}: train.max={train['date'].max()} >= test.min={test['date'].min()}"
            )

        logger.info(
            "=== Year %s | train_rows=%d (%s -> %s) | test_rows=%d (%s -> %s)",
            year,
            len(train),
            train["date"].min().date(),
            train["date"].max().date(),
            len(test),
            test["date"].min().date(),
            test["date"].max().date(),
        )

        try:
            hof = train_gp(train)
        except Exception as exc:  # noqa: BLE001
            logger.error("GP training failed for %s: %s", year, exc)
            hof = []

        gp_signal = ensemble_signal(test, hof)
        gp_metrics = compute_metrics(test, gp_signal)

        base_signal = baseline_momentum_20(test)
        base_metrics = compute_metrics(test, base_signal)

        results.append({
            "year": year,
            "n_alphas": len(hof),
            "alphas": [ind.tree.to_string() for ind in hof],
            "gp": gp_metrics,
            "baseline_momentum_20": base_metrics,
        })

        logger.info(
            "Year %s GP IC=%.4f Sharpe=%.3f Turn=%.3f MDD=%.3f | Base IC=%.4f Sharpe=%.3f",
            year,
            gp_metrics["ic"],
            gp_metrics["sharpe"],
            gp_metrics["turnover"],
            gp_metrics["max_drawdown"],
            base_metrics["ic"],
            base_metrics["sharpe"],
        )

    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def print_summary(results: List[Dict]) -> None:
    if not results:
        print("(no results)")
        return
    header = (
        f"{'Year':<6}{'IC_GP':>9}{'IC_Base':>10}{'Sharpe_GP':>11}"
        f"{'Sharpe_Base':>13}{'Turn_GP':>10}{'MDD_GP':>10}{'#Alpha':>8}"
    )
    print("\n" + "=" * len(header))
    print(header)
    print("=" * len(header))
    for row in results:
        gp = row["gp"]
        bs = row["baseline_momentum_20"]
        print(
            f"{row['year']:<6}"
            f"{gp['ic']:>9.4f}"
            f"{bs['ic']:>10.4f}"
            f"{gp['sharpe']:>11.3f}"
            f"{bs['sharpe']:>13.3f}"
            f"{gp['turnover']:>10.3f}"
            f"{gp['max_drawdown']:>10.3f}"
            f"{row['n_alphas']:>8d}"
        )
    # Aggregate
    gp_ic = np.mean([r["gp"]["ic"] for r in results])
    bs_ic = np.mean([r["baseline_momentum_20"]["ic"] for r in results])
    gp_sh = np.mean([r["gp"]["sharpe"] for r in results])
    bs_sh = np.mean([r["baseline_momentum_20"]["sharpe"] for r in results])
    print("-" * len(header))
    print(
        f"{'AVG':<6}{gp_ic:>9.4f}{bs_ic:>10.4f}{gp_sh:>11.3f}{bs_sh:>13.3f}"
    )
    print("=" * len(header) + "\n")


def save_results(results: List[Dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "1.0",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "feature_names": FEATURE_NAMES,
        "top_k_alphas": TOP_K_ALPHAS,
        "test_years": TEST_YEARS,
        "results": results,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info("Saved %s", OUT_PATH)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    if not DATA_PATH.exists():
        logger.error("Market data not found: %s", DATA_PATH)
        return 2

    df = pd.read_parquet(DATA_PATH, columns=["ticker", "date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["close", "open", "high", "low", "volume"])
    df = df[df["volume"] > 0]
    df = df[df["date"].dt.year >= TRAIN_START_YEAR]
    logger.info("Loaded market data: %s (rows=%d, tickers=%d)", DATA_PATH, len(df), df["ticker"].nunique())

    panel = build_panel(df)
    results = walk_forward(panel)
    print_summary(results)
    save_results(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
