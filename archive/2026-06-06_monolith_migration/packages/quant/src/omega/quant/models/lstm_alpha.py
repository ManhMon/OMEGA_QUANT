"""Phase 4 LSTM Alpha Engine.

Deterministic LSTM regression model for cross-sectional alpha prediction.
Designed to be a drop-in companion to Phase 3.11's Ridge baseline:

    pred_lstm = LSTMAlpha.fit(X_tr_seq, y_tr).predict(X_te_seq)
    pred_ensemble = 0.5 * (pred_ridge + pred_lstm)

Input shape: (N, T_lookback, F_features)
Output: scalar per (N,) sample

PIT discipline:
- Sequence built from features at t-T_lookback..t-1 (caller's responsibility).
- Train/test split is done OUTSIDE this class (we just .fit and .predict).
- z-score / scaling is also caller's responsibility (so train-only stats stay
  outside).

Determinism:
- torch.manual_seed(seed)
- torch.use_deterministic_algorithms(True)
- DataLoader generator seeded
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset, TensorDataset

__all__ = ["LSTMAlphaConfig", "LSTMAlpha", "build_sequences"]


@dataclass
class LSTMAlphaConfig:
    """Phase 4 hyper-parameters (locked by spec)."""
    lookback: int = 60          # T -- bars of history per sample
    n_features: int = 114       # F -- Phase 3.11 alpha count
    hidden_size: int = 64       # LSTM hidden state
    dropout: float = 0.2
    num_layers: int = 1
    lr: float = 1e-3
    weight_decay: float = 1e-5
    epochs: int = 8
    batch_size: int = 512
    seed: int = 42
    n_threads: int = 4          # avoid oversubscription with pandas
    early_stop_patience: int = 2
    min_train_samples: int = 256  # safety: skip training if fold too small
    loss: str = "mse"           # 'mse' (default, regression) or 'ic' (Phase 6: -Pearson(pred, y))


class _LSTMRegressor(nn.Module):
    """Single-layer LSTM -> mean-pool -> linear head -> scalar."""
    def __init__(self, n_features: int, hidden_size: int, num_layers: int,
                 dropout: float):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_features,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_size, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (N, T, F)
        out, _ = self.lstm(x)         # (N, T, H)
        last = out[:, -1, :]          # (N, H) -- final-step state
        y = self.head(last)           # (N, 1)
        return y.squeeze(-1)          # (N,)


class LSTMAlpha:
    """Wrapper with sklearn-like fit/predict API, deterministic by default."""

    def __init__(self, cfg: LSTMAlphaConfig | None = None):
        self.cfg = cfg or LSTMAlphaConfig()
        self.model: _LSTMRegressor | None = None
        self._fitted: bool = False

    # ------------------------------------------------------------------
    # determinism
    # ------------------------------------------------------------------
    def _set_determinism(self) -> None:
        torch.manual_seed(self.cfg.seed)
        np.random.seed(self.cfg.seed)
        torch.set_num_threads(self.cfg.n_threads)
        # use_deterministic_algorithms requires CUBLAS env on GPU; safe on CPU.
        try:
            torch.use_deterministic_algorithms(True, warn_only=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def fit(self, X_seq: np.ndarray, y: np.ndarray,
            val_X: np.ndarray | None = None, val_y: np.ndarray | None = None) -> "LSTMAlpha":
        """Train on (N, T, F) sequences. Optional validation for early stop."""
        if X_seq.ndim != 3:
            raise ValueError(f"X_seq must be 3-D, got {X_seq.shape}")
        N, T, F = X_seq.shape
        if N < self.cfg.min_train_samples:
            # Silently skip; predict() will return zeros with same dtype.
            self._fitted = False
            return self
        if T != self.cfg.lookback or F != self.cfg.n_features:
            raise ValueError(
                f"Shape mismatch: got (T={T}, F={F}), cfg expects "
                f"(T={self.cfg.lookback}, F={self.cfg.n_features})"
            )
        self._set_determinism()

        device = torch.device("cpu")
        self.model = _LSTMRegressor(
            n_features=F,
            hidden_size=self.cfg.hidden_size,
            num_layers=self.cfg.num_layers,
            dropout=self.cfg.dropout,
        ).to(device)

        X_tensor = torch.from_numpy(X_seq.astype(np.float32))
        y_tensor = torch.from_numpy(y.astype(np.float32))
        ds = TensorDataset(X_tensor, y_tensor)
        gen = torch.Generator().manual_seed(self.cfg.seed)
        loader = DataLoader(
            ds, batch_size=self.cfg.batch_size, shuffle=True,
            generator=gen, num_workers=0, drop_last=False,
        )

        opt = torch.optim.AdamW(
            self.model.parameters(), lr=self.cfg.lr,
            weight_decay=self.cfg.weight_decay,
        )
        if self.cfg.loss == "ic":
            # Phase 6: directional IC loss = -Pearson(pred, target).
            # Forces the model to maximize positive correlation; without
            # this, MSE on z-scored targets can converge to a sign-flipped
            # solution (Phase 4/5 exhibited median IC ~ -0.02 to -0.04).
            def _ic_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
                p = pred - pred.mean()
                t = target - target.mean()
                num = (p * t).sum()
                den = torch.sqrt((p * p).sum() * (t * t).sum() + 1e-12)
                return -num / (den + 1e-12)
            loss_fn = _ic_loss
        else:
            loss_fn = nn.MSELoss()

        best_val = float("inf")
        bad_epochs = 0
        for epoch in range(self.cfg.epochs):
            self.model.train()
            for xb, yb in loader:
                opt.zero_grad()
                pred = self.model(xb)
                loss = loss_fn(pred, yb)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                opt.step()
            # Early stop on validation if provided
            if val_X is not None and val_y is not None:
                vloss = self._eval_loss(val_X, val_y)
                if vloss < best_val - 1e-6:
                    best_val = vloss
                    bad_epochs = 0
                else:
                    bad_epochs += 1
                    if bad_epochs >= self.cfg.early_stop_patience:
                        break
        self._fitted = True
        return self

    def _eval_loss(self, X_seq: np.ndarray, y: np.ndarray) -> float:
        self.model.eval()
        with torch.no_grad():
            pred = self.model(torch.from_numpy(X_seq.astype(np.float32)))
            return float(((pred.numpy() - y.astype(np.float32)) ** 2).mean())

    def predict(self, X_seq: np.ndarray) -> np.ndarray:
        if not self._fitted or self.model is None:
            return np.zeros(len(X_seq), dtype=np.float32)
        self.model.eval()
        with torch.no_grad():
            out = self.model(torch.from_numpy(X_seq.astype(np.float32)))
        return out.numpy().astype(np.float64)


# ---------------------------------------------------------------------
# Sequence builder
# ---------------------------------------------------------------------
def build_sequences(
    feat_df,                       # pandas.DataFrame with columns: ticker, date, <features...>
    feat_names: Sequence[str],
    lookback: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Build (N, T, F) sequences and a position index aligned with feat_df rows.

    For each row r in feat_df with ticker=t, we collect the last `lookback`
    rows of the SAME ticker ending at row r-1 (strict PIT: bar t does not
    see its own features in the sequence).

    Returns:
        X_seq: (N_valid, lookback, F)
        idx:   integer positions in feat_df that correspond to rows in X_seq
               (rows without enough history are skipped)
    """
    import pandas as pd
    df = feat_df[["ticker", "date"] + list(feat_names)].copy()
    df["_pos"] = np.arange(len(df))
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    feats = df[list(feat_names)].to_numpy(dtype=np.float32)
    tickers = df["ticker"].to_numpy()
    pos = df["_pos"].to_numpy()

    seqs: list[np.ndarray] = []
    keep: list[int] = []
    # Ticker boundaries
    ticker_change = np.r_[0, np.where(tickers[1:] != tickers[:-1])[0] + 1, len(tickers)]
    for i in range(len(ticker_change) - 1):
        a, b = ticker_change[i], ticker_change[i + 1]
        if b - a <= lookback:
            continue
        # For each row j in [a+lookback, b), sequence is feats[j-lookback:j]
        for j in range(a + lookback, b):
            seqs.append(feats[j - lookback:j])
            keep.append(int(pos[j]))
    if not seqs:
        return np.empty((0, lookback, len(feat_names)), dtype=np.float32), np.empty(0, dtype=np.int64)
    X_seq = np.stack(seqs, axis=0)
    idx = np.asarray(keep, dtype=np.int64)
    return X_seq, idx
