"""Integration test: verify Self-Evolving Engine modules wire correctly.

Runs a thin sanity pass that exercises every evolution module on a small
synthetic dataset (no real market data, no I/O). Each step prints PASS or
FAIL and the script exits 0 only if every step passes.

Steps
-----
1. Imports: load all evolution modules.
2. Synthesize tiny panel (500 rows x 5 symbols) with PIT-safe T-1 features.
3. Mini evolution: GP with pop=20, gen=5 (smoke-test, no IC requirement).
4. Drift detection: feed metrics, ensure 2-of-3 voting executes.
5. Alpha bridge: register two alphas (T+3, T+5), validate embargo.
6. Continuous learning: champion vs challenger comparison.
"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path
from typing import Callable, List, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
QUANT_SRC = ROOT / "packages" / "quant" / "src"
if str(QUANT_SRC) not in sys.path:
    sys.path.insert(0, str(QUANT_SRC))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

RESULTS: List[Tuple[str, bool, str]] = []


def _run_step(name: str, fn: Callable[[], None]) -> bool:
    try:
        fn()
        RESULTS.append((name, True, ""))
        print(f"[PASS] {name}")
        return True
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc(limit=2)
        RESULTS.append((name, False, f"{exc}\n{tb}"))
        print(f"[FAIL] {name}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Step 1: Imports
# ---------------------------------------------------------------------------
def step_imports() -> None:
    global ge_mod, fit_mod, drift_mod, cl_mod, bridge_mod
    from omega.quant.evolution import genetic_engine as ge_mod  # noqa: F401
    from omega.quant.evolution import fitness as fit_mod  # noqa: F401
    from omega.quant.evolution import drift_detector as drift_mod  # noqa: F401
    from omega.quant.evolution import continuous_learning as cl_mod  # noqa: F401
    from omega.quant.evolution import alpha_to_execution_bridge as bridge_mod  # noqa: F401
    # Reference attributes to make sure modules expose expected API surfaces.
    assert hasattr(ge_mod, "GeneticEngine")
    assert hasattr(ge_mod, "GPConfig")
    assert hasattr(fit_mod, "FitnessEvaluator")
    assert hasattr(drift_mod, "DriftDetectorEnsemble")
    assert hasattr(cl_mod, "ContinuousLearningEngine")
    assert hasattr(bridge_mod, "AlphaToExecutionBridge")


# ---------------------------------------------------------------------------
# Step 2: Synthetic dataset
# ---------------------------------------------------------------------------
def _make_synthetic_panel(n_dates: int = 100, n_tickers: int = 5, seed: int = 7) -> pd.DataFrame:
    """Build a small (500 rows) PIT-safe panel for the integration smoke test."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-02", periods=n_dates)
    tickers = [f"SYN{i}" for i in range(n_tickers)]

    rows = []
    for tk in tickers:
        # Geometric brownian-ish close series
        ret = rng.normal(0.0005, 0.02, size=n_dates)
        close = 100.0 * np.exp(np.cumsum(ret))
        open_ = close * (1 + rng.normal(0, 0.005, size=n_dates))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.005, size=n_dates)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.005, size=n_dates)))
        volume = np.abs(rng.normal(1_000_000, 200_000, size=n_dates))
        rows.append(pd.DataFrame({
            "ticker": tk,
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }))
    df = pd.concat(rows, ignore_index=True)

    # Per-ticker T-1 lagged features
    def _per_tk(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("date").copy()
        c = g["close"]
        feats = pd.DataFrame({
            "open": g["open"],
            "high": g["high"],
            "low": g["low"],
            "close": c,
            "volume": g["volume"],
            "returns_1d": c.pct_change(1),
            "returns_5d": c.pct_change(5),
            "vol_ratio": g["volume"] / (g["volume"].rolling(20, min_periods=5).mean() + 1e-9),
            "hl_range": (g["high"] - g["low"]) / (c + 1e-9),
            "oc_range": (c - g["open"]) / (g["open"] + 1e-9),
        }, index=g.index)
        target = c.pct_change(1).shift(-1)
        feats = feats.shift(1)
        feats["target_fwd1d"] = target
        feats["ticker"] = g["ticker"].values
        feats["date"] = g["date"].values
        return feats

    panel = df.groupby("ticker", group_keys=False, sort=False).apply(_per_tk)
    panel = panel.dropna()
    panel = panel.sort_values(["date", "ticker"]).reset_index(drop=True)
    return panel


def step_synthetic_data() -> None:
    global SYN_PANEL
    SYN_PANEL = _make_synthetic_panel(n_dates=120, n_tickers=5)
    assert len(SYN_PANEL) >= 400, f"expected >=400 rows, got {len(SYN_PANEL)}"
    assert {"open", "close", "target_fwd1d", "ticker", "date"}.issubset(SYN_PANEL.columns)


# ---------------------------------------------------------------------------
# Step 3: Mini evolution
# ---------------------------------------------------------------------------
def step_mini_evolution() -> None:
    cfg = ge_mod.GPConfig(
        population_size=20,
        generations=5,
        max_depth=3,
        tournament_size=3,
        crossover_rate=0.7,
        mutation_rate=0.3,
        elitism_count=1,
        hall_of_fame_size=5,
        diversity_threshold=0.7,
        min_observations=50,
        n_jobs=1,
    )
    feature_names = [
        "open", "high", "low", "close", "volume",
        "returns_1d", "returns_5d", "vol_ratio", "hl_range", "oc_range",
    ]
    feats = {n: SYN_PANEL[n].to_numpy(dtype="float64", copy=False) for n in feature_names}
    target = SYN_PANEL["target_fwd1d"].to_numpy(dtype="float64", copy=False)

    engine = ge_mod.GeneticEngine(cfg)
    engine.evolve(feats, target)

    assert len(engine.population) == cfg.population_size
    assert len(engine.history) == cfg.generations
    # Hall of Fame may be empty if every individual is rejected (variance guard);
    # smoke-test only requires the algorithm completed without raising.
    assert isinstance(engine.hall_of_fame, list)


# ---------------------------------------------------------------------------
# Step 4: Drift detection
# ---------------------------------------------------------------------------
def step_drift_detection() -> None:
    cfg = drift_mod.DriftDetectorConfig(
        sharpe_drop_threshold=0.30,
        ic_drop_threshold=0.20,
        turnover_spike_threshold=0.50,
        lookback_window_days=30,
    )
    det = drift_mod.DriftDetectorEnsemble(cfg)
    base_ts = pd.Timestamp("2026-05-01")
    # Healthy baseline metrics
    for i in range(5):
        det.record_metrics(base_ts + pd.Timedelta(days=i), sharpe=1.5, ic=0.10, turnover=0.20)
    # Now record a clearly-degraded sample and check ensemble voting.
    bad = det.check_drift(current_sharpe=0.5, current_ic=0.02, current_turnover=0.45)
    assert isinstance(bad, dict)
    assert "drift_detected" in bad
    assert bad["drift_detected"] is True, f"expected drift True, got {bad}"
    # Healthy sample should not trigger
    ok = det.check_drift(current_sharpe=1.45, current_ic=0.095, current_turnover=0.21)
    assert ok["drift_detected"] is False, f"expected drift False, got {ok}"


# ---------------------------------------------------------------------------
# Step 5: Alpha-to-execution bridge
# ---------------------------------------------------------------------------
def step_alpha_bridge() -> None:
    cfg = bridge_mod.AlphaBridgeConfig()
    bridge = bridge_mod.AlphaToExecutionBridge(cfg)
    train_end = pd.Timestamp("2026-05-01")

    ok3 = bridge.register_alpha(
        alpha_id="alpha_t3",
        formula="rank(returns_5d)",
        horizon=3,
        train_end_date=train_end,
        ic=0.08,
        sharpe=1.2,
    )
    ok5 = bridge.register_alpha(
        alpha_id="alpha_t5",
        formula="ts_mean(close, 10)",
        horizon=5,
        train_end_date=train_end,
        ic=0.07,
        sharpe=1.0,
    )
    assert ok3 and ok5
    assert "alpha_t3" in bridge.active_alphas
    assert "alpha_t5" in bridge.active_alphas

    # Embargo before window: must be False.
    assert bridge.validate_embargo("alpha_t3", train_end + pd.Timedelta(days=1)) is False
    # Embargo after window: must be True.
    assert bridge.validate_embargo("alpha_t3", train_end + pd.Timedelta(days=4)) is True
    assert bridge.validate_embargo("alpha_t5", train_end + pd.Timedelta(days=6)) is True

    # Convert simple synthetic signals to weights
    signals = {
        "alpha_t3": pd.Series({"AAA": 0.5, "BBB": -0.2, "CCC": 0.9, "DDD": -0.7, "EEE": 0.1}),
        "alpha_t5": pd.Series({"AAA": 0.3, "BBB": 0.0, "CCC": 0.8, "DDD": -0.5, "EEE": 0.2}),
    }
    weights = bridge.convert_signals_to_weights(signals, train_end + pd.Timedelta(days=10))
    assert isinstance(weights, dict)
    if weights:
        for w in weights.values():
            assert cfg.min_alpha_weight <= w <= cfg.max_alpha_weight, f"weight {w} out of bounds"


# ---------------------------------------------------------------------------
# Step 6: Continuous learning (champion vs challenger)
# ---------------------------------------------------------------------------
def step_continuous_learning() -> None:
    cfg = cl_mod.ContinuousLearningConfig(
        retraining_interval_days=7,
        min_ic_improvement=0.05,
        min_absolute_ic=0.05,
        sharpe_tolerance=0.95,
    )
    eng = cl_mod.ContinuousLearningEngine(cfg)

    # Synthetic predictions vs actuals (positively correlated).
    rng = np.random.default_rng(42)
    actuals = pd.Series(rng.normal(0, 1, 200))
    preds = actuals * 0.5 + rng.normal(0, 0.5, 200)
    metrics_champion = eng.evaluate_model(preds, actuals, model_name="champion")
    assert {"ic", "sharpe"}.issubset(metrics_champion.keys())

    # A challenger that is clearly better
    preds_better = actuals * 0.9 + rng.normal(0, 0.3, 200)
    metrics_challenger = eng.evaluate_model(preds_better, actuals, model_name="challenger")
    promoted, reason = eng.champion_vs_challenger(metrics_champion, metrics_challenger)
    assert isinstance(promoted, bool) and isinstance(reason, str)

    # should_retrain on a fresh engine must be True.
    assert eng.should_retrain(pd.Timestamp("2026-05-15")) is True


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main() -> int:
    print("=== Self-Evolving Engine Integration Test ===")
    steps = [
        ("imports", step_imports),
        ("synthetic_data", step_synthetic_data),
        ("mini_evolution", step_mini_evolution),
        ("drift_detection", step_drift_detection),
        ("alpha_bridge", step_alpha_bridge),
        ("continuous_learning", step_continuous_learning),
    ]
    all_ok = True
    for name, fn in steps:
        ok = _run_step(name, fn)
        all_ok = all_ok and ok

    print("\n=== Summary ===")
    for name, ok, err in RESULTS:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok and err:
            for line in err.strip().splitlines()[:6]:
                print(f"    | {line}")

    print("\nResult:", "ALL PASS" if all_ok else "FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
