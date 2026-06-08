"""Phase 4 LSTM Alpha tests."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_PATH = REPO_ROOT / "src/omega/quant/models/lstm_alpha.py"
_spec = importlib.util.spec_from_file_location("_lstm", str(_PATH))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_lstm"] = _mod
_spec.loader.exec_module(_mod)

LSTMAlphaConfig = _mod.LSTMAlphaConfig
LSTMAlpha = _mod.LSTMAlpha
build_sequences = _mod.build_sequences


def _toy_panel(n_tickers: int = 3, n_days: int = 200, n_features: int = 4, seed: int = 0):
    rng = np.random.default_rng(seed)
    rows = []
    for t in range(n_tickers):
        for d in range(n_days):
            row = {"ticker": f"T{t}", "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=d)}
            for f in range(n_features):
                row[f"f{f}"] = float(rng.normal())
            rows.append(row)
    return pd.DataFrame(rows)


def test_build_sequences_shape():
    df = _toy_panel()
    feat_names = [f"f{i}" for i in range(4)]
    X, idx = build_sequences(df, feat_names, lookback=10)
    # 3 tickers * (200 - 10) = 570
    assert X.shape == (570, 10, 4)
    assert idx.shape == (570,)
    assert idx.min() >= 0


def test_build_sequences_strict_pit():
    """Sequence at idx j must contain rows j-lookback..j-1 only, no j itself."""
    df = _toy_panel(n_tickers=1, n_days=20)
    feat_names = [f"f{i}" for i in range(4)]
    df_sorted = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    feats = df_sorted[feat_names].to_numpy(dtype=np.float32)
    X, idx = build_sequences(df, feat_names, lookback=5)
    # First sequence should equal feats[0:5], target row is at position 5
    assert idx[0] == 5
    np.testing.assert_array_equal(X[0], feats[0:5])


def test_build_sequences_skips_short_history():
    """Tickers with <= lookback bars are dropped entirely."""
    df = _toy_panel(n_tickers=2, n_days=10)
    feat_names = [f"f{i}" for i in range(4)]
    X, idx = build_sequences(df, feat_names, lookback=10)
    # Each ticker has exactly 10 bars; lookback 10 means need >10 rows -> 0
    assert X.shape == (0, 10, 4)
    assert idx.shape == (0,)


def test_lstm_fit_predict_shapes():
    cfg = LSTMAlphaConfig(lookback=20, n_features=8, hidden_size=16, epochs=2,
                           batch_size=64, min_train_samples=32)
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 20, 8)).astype(np.float32)
    y = rng.normal(size=(200,)).astype(np.float32)
    m = LSTMAlpha(cfg).fit(X, y)
    pred = m.predict(X[:50])
    assert pred.shape == (50,)
    assert np.isfinite(pred).all()


def test_lstm_skips_when_train_too_small():
    cfg = LSTMAlphaConfig(lookback=20, n_features=8, hidden_size=16, epochs=2,
                           batch_size=64, min_train_samples=500)
    rng = np.random.default_rng(0)
    X = rng.normal(size=(50, 20, 8)).astype(np.float32)
    y = rng.normal(size=(50,)).astype(np.float32)
    m = LSTMAlpha(cfg).fit(X, y)
    pred = m.predict(X)
    # Skipped fit -> zeros
    np.testing.assert_array_equal(pred, np.zeros(50))


def test_lstm_determinism():
    """Same seed, same data -> identical predictions."""
    cfg = LSTMAlphaConfig(lookback=10, n_features=4, hidden_size=8, epochs=2,
                           batch_size=64, seed=123, min_train_samples=32)
    rng = np.random.default_rng(0)
    X = rng.normal(size=(150, 10, 4)).astype(np.float32)
    y = rng.normal(size=(150,)).astype(np.float32)
    m1 = LSTMAlpha(cfg).fit(X, y)
    p1 = m1.predict(X[:30])
    m2 = LSTMAlpha(cfg).fit(X, y)
    p2 = m2.predict(X[:30])
    np.testing.assert_allclose(p1, p2, rtol=1e-5, atol=1e-6)


def test_lstm_signal_recovery():
    """Construct a target that is a simple function of the last bar of feat 0;
    LSTM should achieve positive corr with target on held-out data."""
    rng = np.random.default_rng(42)
    n, T, F = 800, 12, 4
    X = rng.normal(size=(n, T, F)).astype(np.float32)
    # Target = last bar of feature 0 + small noise
    y = X[:, -1, 0] + 0.2 * rng.normal(size=n).astype(np.float32)
    cfg = LSTMAlphaConfig(lookback=T, n_features=F, hidden_size=16, epochs=8,
                           batch_size=128, min_train_samples=64)
    m = LSTMAlpha(cfg).fit(X[:600], y[:600])
    p = m.predict(X[600:])
    corr = float(np.corrcoef(p, y[600:])[0, 1])
    assert corr > 0.3, f"LSTM should learn the signal, got corr={corr:.3f}"


def test_lstm_shape_validation():
    cfg = LSTMAlphaConfig(lookback=20, n_features=8, hidden_size=16, epochs=1,
                           batch_size=32, min_train_samples=32)
    X_bad = np.zeros((100, 30, 8), dtype=np.float32)  # wrong T
    y = np.zeros(100, dtype=np.float32)
    with pytest.raises(ValueError, match="Shape mismatch"):
        LSTMAlpha(cfg).fit(X_bad, y)
