"""Risk/Sizing Overlay for Phase35 Walk-Forward Backtest.

GATE: BASELINE_RISK_SIZING_OPTIMIZATION_20260616
GATE: REGIME_CONDITIONAL_SIZING_20260616
GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616

Research-only, opt-in, default-off risk/sizing overlay that sits on top of
the trusted dynamic baseline.  Three independent features:

1. **Inverse-volatility sizing** (``inverse_vol_sizing``):
   Replace equal-weight within the selected top-N positions with
   1 / realized_vol weights (trailing window, PIT-safe).

2. **Confidence scaling** (``confidence_scaling``):
   Scale total gross exposure by rolling signal IC strength (train-only
   trailing window, PIT-safe).

3. **Regime-conditional sizing** (``regime_sizing``):
   Two modes supported:

   a) **Heuristic mode** (``regime_sizing_mode='heuristic'``, default):
      Detect market regime from trailing PIT-safe market proxy data and
      scale exposure in Bear regime.  Regimes:
      - Bear: market_proxy < MA(ma_window)
      - Neutral: market_proxy >= MA and rolling_vol > vol threshold
      - Bull: market_proxy >= MA and rolling_vol <= vol threshold

   b) **HMM mode** (``regime_sizing_mode='hmm'``):
      Fit a custom 3-state Gaussian HMM (pure NumPy, no hmmlearn) on
      trailing PIT-safe market returns using Baum-Welch (EM) with
      scaling for numerical stability.  States are mapped by sorting
      emission means (lowest = Bear).  Exposure is scaled by
      ``scale = 1.0 - p_bear * (1.0 - regime_sizing_scale)``
      where ``p_bear`` is the posterior probability of the Bear state.

   An auto-optimization mode (``regime_sizing_auto_optimize``) grid-searches
   the scale parameter on train data to maximize Sharpe ratio.

Neither feature adds alpha — they only modify position sizing and gross
exposure based on PIT-safe trailing statistics.

PIT Safety
----------
All inputs use ONLY data available at or before the current decision date:
- Realized vol: trailing window of lagged daily returns (T-1 and earlier)
- Rolling IC: trailing window of per-date cross-sectional IC between
  lagged signal and lagged forward returns (T-1 and earlier)
- HMM regime: fitted on trailing returns strictly before current date
- No current-bar data, no forward returns, no OOS labels

SOD Boundary
------------
Research-only, opt-in, default-off.  Does NOT change live/default behavior.
Any promotion to live requires strict OOS evidence beating the trusted
dynamic baseline and Tier 3 audit approval.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GATE: BASELINE_RISK_SIZING_OPTIMIZATION_20260616
# ---------------------------------------------------------------------------
RISK_SIZING_OVERLAY_GATE_ID = "BASELINE_RISK_SIZING_OPTIMIZATION_20260616"

# ---------------------------------------------------------------------------
# GATE: REGIME_CONDITIONAL_SIZING_20260616
# Research-only opt-in regime-conditional sizing.
# Detects regimes from PIT-safe trailing market proxy, scales exposure
# in Bear regime.  Never uses current-bar data or OOS labels.
# Default off, no live/default promotion.
# ---------------------------------------------------------------------------
REGIME_CONDITIONAL_SIZING_GATE_ID = "REGIME_CONDITIONAL_SIZING_20260616"

# ---------------------------------------------------------------------------
# SimpleGaussianHMM — pure Python/NumPy 3-state HMM with Baum-Welch (EM)
# No hmmlearn dependency (broken on Python 3.14.4).
# GATE: REGIME_CONDITIONAL_SIZING_20260616
# ---------------------------------------------------------------------------


class SimpleGaussianHMM:
    """Pure-NumPy Gaussian Hidden Markov Model with Baum-Welch (EM).

    Implements a K-state HMM with univariate Gaussian emissions.  Uses
    scaling (normalization) in the forward-backward pass for numerical
    stability with long observation sequences.

    Parameters
    ----------
    n_states : int
        Number of hidden states (default 3).
    max_iter : int
        Maximum EM iterations (default 30).
    tol : float
        Convergence tolerance on log-likelihood delta (default 1e-4).
    random_state : int or None
        Seed for reproducible initialization (default 42).

    Attributes (after fit)
    ----------------------
    pi_ : ndarray of shape (K,)
        Initial state distribution.
    A_ : ndarray of shape (K, K)
        State transition matrix.
    mu_ : ndarray of shape (K,)
        Emission means per state.
    sigma2_ : ndarray of shape (K,)
        Emission variances per state.
    n_iter_ : int
        Number of EM iterations completed.
    log_likelihood_ : float
        Final log-likelihood.
    """

    def __init__(
        self,
        n_states: int = 3,
        max_iter: int = 30,
        tol: float = 1e-4,
        random_state: int | None = 42,
    ):
        self.n_states = n_states
        self.max_iter = max_iter
        self.tol = tol
        self.random_state = random_state
        # Model parameters (set during fit)
        self.pi_: np.ndarray | None = None
        self.A_: np.ndarray | None = None
        self.mu_: np.ndarray | None = None
        self.sigma2_: np.ndarray | None = None
        self.n_iter_: int = 0
        self.log_likelihood_: float = -np.inf

    # ------------------------------------------------------------------
    # Emission probability: P(x_t | state=k)
    # ------------------------------------------------------------------
    @staticmethod
    def _gaussian_log_pdf(x: np.ndarray, mu: float, sigma2: float) -> np.ndarray:
        """Log-density of univariate Gaussian for array x."""
        sigma2_safe = max(sigma2, 1e-300)
        return -0.5 * (np.log(2 * np.pi * sigma2_safe) + (x - mu) ** 2 / sigma2_safe)

    def _compute_log_emission(self, X: np.ndarray) -> np.ndarray:
        """Compute log B[t, k] = log P(x_t | state=k) for all t, k.

        Parameters
        ----------
        X : ndarray of shape (T,)

        Returns
        -------
        log_B : ndarray of shape (T, K)
        """
        T = len(X)
        K = self.n_states
        log_B = np.zeros((T, K))
        for k in range(K):
            log_B[:, k] = self._gaussian_log_pdf(X, self.mu_[k], self.sigma2_[k])
        return log_B

    def _compute_emission(self, X: np.ndarray) -> np.ndarray:
        """Compute B[t, k] = P(x_t | state=k) with floor for stability."""
        log_B = self._compute_log_emission(X)
        # Clip to prevent underflow before exp
        log_B = np.clip(log_B, -500, 500)
        return np.exp(log_B)

    # ------------------------------------------------------------------
    # Forward pass with scaling
    # ------------------------------------------------------------------
    def _forward(self, B: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Scaled forward algorithm.

        Parameters
        ----------
        B : ndarray of shape (T, K)
            Emission probabilities.

        Returns
        -------
        alpha_hat : ndarray of shape (T, K)
            Scaled forward variables.
        c : ndarray of shape (T,)
            Scale factors (1 / sum of alpha at each step).
        """
        T, K = B.shape
        alpha_hat = np.zeros((T, K))
        c = np.zeros(T)

        # Initialization
        alpha_hat[0] = self.pi_ * B[0]
        s = alpha_hat[0].sum()
        if s < 1e-300:
            s = 1e-300
        c[0] = 1.0 / s
        alpha_hat[0] *= c[0]

        # Induction
        for t in range(1, T):
            alpha_hat[t] = (alpha_hat[t - 1] @ self.A_) * B[t]
            s = alpha_hat[t].sum()
            if s < 1e-300:
                s = 1e-300
            c[t] = 1.0 / s
            alpha_hat[t] *= c[t]

        return alpha_hat, c

    # ------------------------------------------------------------------
    # Backward pass with scaling
    # ------------------------------------------------------------------
    def _backward(self, B: np.ndarray, c: np.ndarray) -> np.ndarray:
        """Scaled backward algorithm.

        Parameters
        ----------
        B : ndarray of shape (T, K)
            Emission probabilities.
        c : ndarray of shape (T,)
            Scale factors from forward pass.

        Returns
        -------
        beta_hat : ndarray of shape (T, K)
            Scaled backward variables.
        """
        T, K = B.shape
        beta_hat = np.zeros((T, K))
        beta_hat[T - 1] = c[T - 1]

        for t in range(T - 2, -1, -1):
            beta_hat[t] = self.A_ @ (B[t + 1] * beta_hat[t + 1])
            beta_hat[t] *= c[t]

        return beta_hat

    # ------------------------------------------------------------------
    # fit(X, init_params) — Baum-Welch EM with optional warm start
    # ------------------------------------------------------------------
    def fit(self, X: np.ndarray, init_params: dict | None = None) -> "SimpleGaussianHMM":
        """Fit HMM parameters using Baum-Welch (EM) algorithm.

        Parameters
        ----------
        X : ndarray of shape (T,)
            1-D observation sequence (e.g. daily market returns).
        init_params : dict or None
            Optional warm-start parameters.  If provided, must contain
            one or more of ``pi``, ``A``, ``mu``, ``sigma2``.  Missing
            keys fall back to the default quantile/random initialization.

        Returns
        -------
        self
        """
        X = np.asarray(X, dtype=np.float64).ravel()
        T = len(X)
        K = self.n_states

        if T < K + 2:
            raise ValueError(
                f"Need at least {K + 2} observations, got {T}"
            )

        rng = np.random.RandomState(self.random_state)

        if init_params is not None:
            # Warm-start: use provided parameters where available
            if "mu" in init_params and init_params["mu"] is not None:
                self.mu_ = np.asarray(init_params["mu"], dtype=np.float64).copy()
            else:
                quantiles = np.linspace(10, 90, K)
                self.mu_ = np.percentile(X, quantiles).copy()

            if "sigma2" in init_params and init_params["sigma2"] is not None:
                self.sigma2_ = np.asarray(init_params["sigma2"], dtype=np.float64).copy()
                self.sigma2_ = np.clip(self.sigma2_, 1e-10, None)
            else:
                data_var = max(np.var(X), 1e-10)
                self.sigma2_ = np.full(K, data_var * 0.5)
                self.sigma2_ *= (1.0 + rng.randn(K) * 0.1)
                self.sigma2_ = np.clip(self.sigma2_, 1e-10, None)

            if "pi" in init_params and init_params["pi"] is not None:
                self.pi_ = np.asarray(init_params["pi"], dtype=np.float64).copy()
                pi_sum = self.pi_.sum()
                if pi_sum > 1e-300:
                    self.pi_ /= pi_sum
            else:
                self.pi_ = np.full(K, 1.0 / K)

            if "A" in init_params and init_params["A"] is not None:
                self.A_ = np.asarray(init_params["A"], dtype=np.float64).copy()
                row_sums = self.A_.sum(axis=1, keepdims=True)
                row_sums = np.maximum(row_sums, 1e-300)
                self.A_ /= row_sums
            else:
                self.A_ = np.full((K, K), 1.0 / K)
                np.fill_diagonal(self.A_, 0.8)
                self.A_ /= self.A_.sum(axis=1, keepdims=True)
        else:
            # Default initialization from quantiles
            quantiles = np.linspace(10, 90, K)
            self.mu_ = np.percentile(X, quantiles).copy()
            data_var = max(np.var(X), 1e-10)
            self.sigma2_ = np.full(K, data_var * 0.5)
            self.sigma2_ *= (1.0 + rng.randn(K) * 0.1)
            self.sigma2_ = np.clip(self.sigma2_, 1e-10, None)
            self.pi_ = np.full(K, 1.0 / K)
            self.A_ = np.full((K, K), 1.0 / K)
            np.fill_diagonal(self.A_, 0.8)
            self.A_ /= self.A_.sum(axis=1, keepdims=True)

        prev_ll = -np.inf

        for iteration in range(self.max_iter):
            # E-step: compute posteriors
            B = self._compute_emission(X)
            alpha_hat, c = self._forward(B)
            beta_hat = self._backward(B, c)

            # Log-likelihood from scale factors
            ll = -np.sum(np.log(np.maximum(c, 1e-300)))

            # Check convergence
            if abs(ll - prev_ll) < self.tol:
                self.n_iter_ = iteration + 1
                self.log_likelihood_ = ll
                break
            prev_ll = ll

            # Posterior: gamma[t, k] = P(z_t = k | X)
            gamma = alpha_hat * beta_hat
            gamma_sum = gamma.sum(axis=1, keepdims=True)
            gamma_sum = np.maximum(gamma_sum, 1e-300)
            gamma = gamma / gamma_sum

            # Xi: xi[t, i, j] = P(z_t = i, z_{t+1} = j | X)
            # We compute summed xi for M-step
            xi_sum = np.zeros((K, K))
            for t in range(T - 1):
                # Numerator: alpha_hat[t,i] * A[i,j] * B[t+1,j] * beta_hat[t+1,j]
                numer = (
                    alpha_hat[t, :, np.newaxis]
                    * self.A_
                    * B[t + 1, np.newaxis, :]
                    * beta_hat[t + 1, np.newaxis, :]
                )
                s = numer.sum()
                if s > 1e-300:
                    xi_sum += numer / s

            # M-step: re-estimate parameters
            # Initial state distribution
            self.pi_ = gamma[0].copy()
            pi_sum = self.pi_.sum()
            if pi_sum > 1e-300:
                self.pi_ /= pi_sum

            # Transition matrix
            gamma_sum_trans = gamma[:-1].sum(axis=0)  # sum over t=0..T-2
            for i in range(K):
                denom = gamma_sum_trans[i]
                if denom > 1e-300:
                    self.A_[i] = xi_sum[i] / denom
                else:
                    self.A_[i] = 1.0 / K
            # Normalize rows
            row_sums = self.A_.sum(axis=1, keepdims=True)
            row_sums = np.maximum(row_sums, 1e-300)
            self.A_ /= row_sums

            # Emission means and variances
            gamma_total = gamma.sum(axis=0)
            for k in range(K):
                if gamma_total[k] > 1e-300:
                    self.mu_[k] = np.sum(gamma[:, k] * X) / gamma_total[k]
                    diff = X - self.mu_[k]
                    self.sigma2_[k] = (
                        np.sum(gamma[:, k] * diff * diff) / gamma_total[k]
                    )
                    self.sigma2_[k] = max(self.sigma2_[k], 1e-10)

        else:
            self.n_iter_ = self.max_iter
            self.log_likelihood_ = prev_ll

        return self

    # ------------------------------------------------------------------
    # predict_proba(X) — posterior state probabilities
    # ------------------------------------------------------------------
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Compute posterior state probabilities for each observation.

        Parameters
        ----------
        X : ndarray of shape (T,)
            Observation sequence.

        Returns
        -------
        gamma : ndarray of shape (T, K)
            Posterior probability of each state at each time step.
            Columns are ordered by original state index (0, 1, 2, ...).
        """
        if self.pi_ is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = np.asarray(X, dtype=np.float64).ravel()
        B = self._compute_emission(X)
        alpha_hat, c = self._forward(B)
        beta_hat = self._backward(B, c)

        gamma = alpha_hat * beta_hat
        gamma_sum = gamma.sum(axis=1, keepdims=True)
        gamma_sum = np.maximum(gamma_sum, 1e-300)
        gamma = gamma / gamma_sum
        return gamma

    # ------------------------------------------------------------------
    # get_params() — extract fitted parameters as a dict
    # ------------------------------------------------------------------
    def get_params(self) -> dict:
        """Extract fitted HMM parameters as a plain dict.

        Returns
        -------
        dict
            Keys: ``pi``, ``A``, ``mu``, ``sigma2``.  Values are NumPy
            arrays (copies).  Returns ``None`` for any parameter that
            has not been fitted yet.
        """
        return {
            "pi": self.pi_.copy() if self.pi_ is not None else None,
            "A": self.A_.copy() if self.A_ is not None else None,
            "mu": self.mu_.copy() if self.mu_ is not None else None,
            "sigma2": self.sigma2_.copy() if self.sigma2_ is not None else None,
        }


# ---------------------------------------------------------------------------
# RiskSizingConfig
# ---------------------------------------------------------------------------


@dataclass
class RiskSizingConfig:
    """Configuration for the risk/sizing overlay.

    All features are opt-in, default-off.

    Parameters
    ----------
    inverse_vol_sizing : bool
        If True, weight positions by 1/realized_vol instead of equal-weight.
    inverse_vol_window : int
        Trailing window (days) for realized volatility estimation.
    inverse_vol_floor : float
        Minimum weight fraction (prevents degenerate zero-vol weights).
    confidence_scaling : bool
        If True, scale total gross exposure by rolling signal quality.
    confidence_window : int
        Trailing window (days) for rolling IC estimation.
    confidence_min_ic : float
        Minimum absolute IC for full exposure.  Below this, scale down.
    confidence_max_scale : float
        Maximum exposure scale (cap upside leverage).
    confidence_min_scale : float
        Minimum exposure scale (never fully de-risk to zero).
    regime_sizing : bool
        If True, detect market regime and scale exposure in Bear regime.
        GATE: REGIME_CONDITIONAL_SIZING_20260616.
    regime_sizing_scale : float
        Exposure scale applied in Bear regime (default 0.5).
    regime_ma_window : int
        Moving-average window for market proxy trend detection (default 200).
    regime_vol_window : int
        Rolling std window for market proxy volatility (default 20).
    regime_vol_median_window : int
        Rolling median window for adaptive vol threshold (default 60).
    regime_sizing_window : int
        Trailing window (days) for HMM fitting on market returns (default 200).
        GATE: REGIME_CONDITIONAL_SIZING_20260616 — Hướng 3 HMM path.
    regime_sizing_mode : str
        Regime detection mode: 'heuristic' (MA/vol, default) or 'hmm'
        (3-state Gaussian HMM with Baum-Welch EM).
        GATE: REGIME_CONDITIONAL_SIZING_20260616.
    regime_sizing_auto_optimize : bool
        If True, grid-search regime_sizing_scale on train data to maximize
        Sharpe ratio.  Overrides regime_sizing_scale when enabled.
        GATE: REGIME_CONDITIONAL_SIZING_20260616.
    regime_refit_stride : int
        Refit HMM only every ``regime_refit_stride`` days during walk-forward
        OOS evaluation.  Between refits, cached HMM parameters are used for
        forward-backward inference only (``refit=False``).  Must be >= 1.
        GATE: REGIME_CONDITIONAL_SIZING_20260616.
    """

    inverse_vol_sizing: bool = False
    inverse_vol_window: int = 20
    inverse_vol_floor: float = 0.3
    confidence_scaling: bool = False
    confidence_window: int = 60
    confidence_min_ic: float = 0.01
    confidence_max_scale: float = 1.2
    confidence_min_scale: float = 0.3
    regime_sizing: bool = False
    regime_sizing_scale: float = 0.5
    regime_ma_window: int = 200
    regime_vol_window: int = 20
    regime_vol_median_window: int = 60
    regime_sizing_window: int = 200
    regime_sizing_mode: str = "heuristic"
    regime_sizing_auto_optimize: bool = False
    regime_refit_stride: int = 5

    @property
    def enabled(self) -> bool:
        return (
            self.inverse_vol_sizing
            or self.confidence_scaling
            or self.regime_sizing
        )


def compute_inverse_vol_weights(
    prices_wide: pd.DataFrame,
    tickers: List[str],
    window: int = 20,
    floor: float = 0.3,
) -> pd.Series:
    """Compute inverse-volatility weights for a single rebalance date.

    PIT-safe: uses ONLY trailing prices (no current bar).

    Parameters
    ----------
    prices_wide : pd.DataFrame
        Wide-format close prices, index=date, columns=tickers.
        Must include at least ``window + 1`` rows of trailing data.
    tickers : list of str
        Ticker symbols to compute weights for.
    window : int
        Trailing window for realized vol (default 20).
    floor : float
        Minimum weight fraction before renormalization (default 0.3).

    Returns
    -------
    pd.Series
        Inverse-vol weights summing to 1.0 for the given tickers.
        If insufficient data, returns equal-weight.
    """
    if len(prices_wide) < window + 1:
        return pd.Series(1.0 / max(len(tickers), 1), index=tickers)

    trailing = prices_wide.iloc[-(window + 1):]
    rets = trailing.pct_change().dropna()

    if len(rets) < max(5, window // 2):
        return pd.Series(1.0 / max(len(tickers), 1), index=tickers)

    vols = rets[tickers].std()
    # Replace zero vol with a small positive value (treat as very stable → high weight)
    min_nonzero_vol = vols[vols > 0].min() if (vols > 0).any() else 1e-9
    vols = vols.replace(0, min_nonzero_vol * 0.1)
    vols = vols.dropna()

    if vols.empty:
        return pd.Series(1.0 / max(len(tickers), 1), index=tickers)

    inv_vols = 1.0 / vols
    # Reindex to requested tickers (fill missing with equal weight)
    inv_vols = inv_vols.reindex(tickers, fill_value=inv_vols.mean() if not inv_vols.empty else 1.0)
    # Apply floor: no position gets less than floor * mean weight
    mean_inv = inv_vols.mean()
    inv_vols = inv_vols.clip(lower=floor * mean_inv)
    # Renormalize to sum to 1
    weights = inv_vols / inv_vols.sum()
    return weights


def compute_confidence_scale(
    signal_wide: pd.DataFrame,
    return_wide: pd.DataFrame,
    window: int = 60,
    min_ic: float = 0.01,
    max_scale: float = 1.2,
    min_scale: float = 0.3,
) -> float:
    """Compute confidence scaling factor from trailing signal IC.

    PIT-safe: uses ONLY trailing cross-sectional IC (lagged signal vs
    lagged forward returns).  No current-bar or forward data.

    Parameters
    ----------
    signal_wide : pd.DataFrame
        Wide-format lagged signal, index=date, columns=tickers.
    return_wide : pd.DataFrame
        Wide-format lagged forward returns, index=date, columns=tickers.
    window : int
        Trailing window for IC estimation (default 60).
    min_ic : float
        Minimum |IC| for full exposure (default 0.01).
    max_scale : float
        Maximum scale factor (default 1.2).
    min_scale : float
        Minimum scale factor (default 0.3).

    Returns
    -------
    float
        Confidence scale factor in [min_scale, max_scale].
    """
    if len(signal_wide) < max(10, window // 2):
        return 1.0  # Insufficient data → no scaling

    # Use the last `window` dates
    sig = signal_wide.iloc[-window:]
    ret = return_wide.iloc[-window:]

    # Per-date cross-sectional IC
    daily_ics = []
    common_dates = sig.index.intersection(ret.index)
    for dt in common_dates:
        s = sig.loc[dt].dropna()
        r = ret.loc[dt].dropna()
        common = s.index.intersection(r.index)
        if len(common) < 5:
            continue
        try:
            ic, _ = spearmanr(s[common].values, r[common].values)
            if not np.isnan(ic):
                daily_ics.append(ic)
        except Exception:
            continue

    if len(daily_ics) < 5:
        return 1.0

    mean_ic = float(np.mean(daily_ics))
    abs_mean_ic = abs(mean_ic)

    # Scale: linear ramp from min_scale at IC=0 to 1.0 at IC=min_ic
    # Above min_ic, scale up toward max_scale proportionally
    if abs_mean_ic < 1e-9:
        return min_scale
    if abs_mean_ic <= min_ic:
        # Linear ramp: min_scale + (1.0 - min_scale) * (abs_mean_ic / min_ic)
        return min_scale + (1.0 - min_scale) * (abs_mean_ic / min_ic)
    # Above min_ic: scale up proportionally, capped at max_scale
    overshoot = abs_mean_ic / min_ic
    return float(min(max_scale, overshoot))


def detect_market_regime(
    close_wide: pd.DataFrame,
    dt,
    ma_window: int = 200,
    vol_window: int = 20,
    vol_median_window: int = 60,
) -> str:
    """Detect market regime for a single date using PIT-safe trailing data.

    PIT-safe: uses ONLY data with dates strictly before ``dt``.

    Parameters
    ----------
    close_wide : pd.DataFrame
        Wide-format close prices, index=date, columns=tickers.
    dt : date-like
        The decision date. Only data with index < dt is used.
    ma_window : int
        Moving-average window for trend detection (default 200).
    vol_window : int
        Rolling std window for volatility (default 20).
    vol_median_window : int
        Rolling median window for adaptive vol threshold (default 60).

    Returns
    -------
    str
        One of 'bear', 'neutral', 'bull', or 'unknown' when insufficient data.

    Regime Logic
    ------------
    - ``market_proxy``: mean close across active universe per date.
    - ``ma_value``: trailing MA of market_proxy (last ``ma_window`` values
      including the most recent pre-``dt`` bar).
    - ``rolling_vol``: trailing std of market_proxy daily returns over
      ``vol_window`` bars.
    - ``vol_threshold``: trailing median of rolling_vol series over
      ``vol_median_window`` bars.

    - Bear: market_proxy < ma_value
    - Neutral: market_proxy >= ma_value AND rolling_vol > vol_threshold
    - Bull: market_proxy >= ma_value AND rolling_vol <= vol_threshold
    """
    trailing_idx = close_wide.index[close_wide.index < dt]

    # Need at least ma_window + 1 dates to compute MA and returns
    min_required = max(ma_window, vol_window + vol_median_window) + 1
    if len(trailing_idx) < min_required:
        return "unknown"

    # Market proxy: mean close across all tickers per date
    market_proxy = close_wide.loc[trailing_idx].mean(axis=1)

    # Current market proxy value (most recent bar before dt)
    mp_current = float(market_proxy.iloc[-1])

    # Moving average of market proxy
    ma_value = float(market_proxy.iloc[-ma_window:].mean())

    # Daily returns of market proxy
    mp_returns = market_proxy.pct_change().dropna()

    # Rolling vol: std of returns over trailing vol_window
    if len(mp_returns) < vol_window + 1:
        return "unknown"
    trailing_vols = mp_returns.rolling(window=vol_window).std().dropna()

    if trailing_vols.empty:
        return "unknown"

    current_vol = float(trailing_vols.iloc[-1])

    # Adaptive threshold: median of rolling vol over trailing window
    n_med = min(vol_median_window, len(trailing_vols))
    vol_threshold = float(trailing_vols.iloc[-n_med:].median())

    # Regime classification
    if mp_current < ma_value:
        return "bear"
    if current_vol > vol_threshold:
        return "neutral"
    return "bull"


# ---------------------------------------------------------------------------
# HMM-based regime detection — GATE: REGIME_CONDITIONAL_SIZING_20260616
# Hướng 3: Regime-Conditional Sizing with custom 3-state HMM
# ---------------------------------------------------------------------------

def compute_hmm_regime_scale(
    close_wide: pd.DataFrame,
    dt,
    regime_window: int = 200,
    regime_scale: float = 0.5,
    init_params: dict | None = None,
    refit: bool = True,
) -> tuple[float, Dict[str, float], dict]:
    """Compute exposure scale for a single date using HMM regime detection.

    PIT-safe: fits 3-state Gaussian HMM on trailing market returns strictly
    before ``dt``.  States are mapped by sorting emission means (lowest = Bear).
    Scale = 1.0 - p_bear * (1.0 - regime_scale), where p_bear is the
    posterior probability of the Bear state for the most recent observation.

    Parameters
    ----------
    close_wide : pd.DataFrame
        Wide-format close prices, index=date, columns=tickers.
    dt : date-like
        The decision date. Only data with index < dt is used.
    regime_window : int
        Trailing window (days) for HMM fitting (default 200).
    regime_scale : float
        Exposure scale in full Bear regime (default 0.5).
    init_params : dict or None
        Warm-start parameters (``pi``, ``A``, ``mu``, ``sigma2``) for
        Baum-Welch EM.  Used both when ``refit=True`` (as initial values)
        and when ``refit=False`` (for forward-backward inference only).
    refit : bool
        If True (default), fit HMM (optionally warm-started from
        ``init_params``) and return updated parameters.
        If False, use ``init_params`` (emission means, transition matrix,
        etc.) to perform only forward-backward (``predict_proba``) and
        return current scale without retraining.

    Returns
    -------
    scale : float
        Exposure scale factor in [regime_scale, 1.0].
    evidence : dict
        Diagnostic evidence with state probabilities and emission means.
    hmm_params : dict
        Fitted (or carried-forward) HMM parameters.  Empty dict when
        data is insufficient or an exception occurred.
    """
    trailing_idx = close_wide.index[close_wide.index < dt]

    # Need enough data to fit HMM
    min_required = max(regime_window, 30) + 1
    if len(trailing_idx) < min_required:
        return 1.0, {"insufficient_data": True, "n_trailing": len(trailing_idx)}, {}

    # Market proxy: mean close across universe per date
    market_proxy = close_wide.loc[trailing_idx].mean(axis=1)
    mp_returns = market_proxy.pct_change().dropna()

    if len(mp_returns) < max(regime_window, 20):
        return 1.0, {"insufficient_returns": True, "n_returns": len(mp_returns)}, {}

    # Take trailing window of returns for HMM fitting
    trailing_returns = mp_returns.iloc[-regime_window:].values

    # Remove any NaN/inf
    mask = np.isfinite(trailing_returns)
    trailing_returns = trailing_returns[mask]

    if len(trailing_returns) < 20:
        return 1.0, {"insufficient_clean_returns": True}, {}

    try:
        hmm = SimpleGaussianHMM(n_states=3, max_iter=30, tol=1e-4, random_state=42)

        if refit:
            # Fit HMM (warm-started from init_params if available)
            hmm.fit(trailing_returns, init_params=init_params)
        else:
            # Inference-only: load parameters from init_params, skip fit
            if init_params is None:
                return 1.0, {"refit_false_no_init_params": True}, {}
            # Restore parameters directly (no EM iterations)
            if init_params.get("pi") is not None:
                hmm.pi_ = np.asarray(init_params["pi"], dtype=np.float64).copy()
            else:
                hmm.pi_ = np.full(hmm.n_states, 1.0 / hmm.n_states)
            if init_params.get("A") is not None:
                hmm.A_ = np.asarray(init_params["A"], dtype=np.float64).copy()
            if init_params.get("mu") is not None:
                hmm.mu_ = np.asarray(init_params["mu"], dtype=np.float64).copy()
            if init_params.get("sigma2") is not None:
                hmm.sigma2_ = np.asarray(init_params["sigma2"], dtype=np.float64).copy()

        # Get posterior probabilities for ALL observations, take the last one
        gamma = hmm.predict_proba(trailing_returns)
        last_gamma = gamma[-1]  # shape (3,)

        # Map states by sorting emission means: lowest mean → Bear
        sorted_state_indices = np.argsort(hmm.mu_)
        # sorted_state_indices[0] = Bear (lowest mean)
        # sorted_state_indices[1] = Neutral
        # sorted_state_indices[2] = Bull (highest mean)

        bear_idx = sorted_state_indices[0]
        p_bear = float(last_gamma[bear_idx])

        # Scale: linear interpolation between full exposure and bear scale
        scale = 1.0 - p_bear * (1.0 - regime_scale)
        scale = float(np.clip(scale, regime_scale, 1.0))

        evidence = {
            "insufficient_data": False,
            "p_bear": round(p_bear, 4),
            "p_neutral": round(float(last_gamma[sorted_state_indices[1]]), 4),
            "p_bull": round(float(last_gamma[sorted_state_indices[2]]), 4),
            "mu_bear": round(float(hmm.mu_[bear_idx]), 6),
            "mu_neutral": round(float(hmm.mu_[sorted_state_indices[1]]), 6),
            "mu_bull": round(float(hmm.mu_[sorted_state_indices[2]]), 6),
            "n_iter": hmm.n_iter_,
            "refit": refit,
            "regime_scale": regime_scale,
            "scale_applied": round(scale, 4),
        }
        hmm_params = hmm.get_params()
        return scale, evidence, hmm_params

    except Exception as exc:
        logger.warning(f"HMM regime detection failed: {exc}, using scale=1.0")
        return 1.0, {"hmm_exception": str(exc)}, {}


def auto_optimize_regime_scale(
    train_df: pd.DataFrame,
    regime_window: int = 200,
    regime_mode: str = "heuristic",
    scale_grid: Optional[List[float]] = None,
    ma_window: int = 200,
    vol_window: int = 20,
    vol_median_window: int = 60,
) -> tuple[float, Dict[str, object]]:
    """Grid-search regime_sizing_scale on train data to maximize Sharpe ratio.

    PIT-safe: for each candidate scale, simulates applying regime-conditional
    sizing on the training set using only trailing data at each date.
    Selects the scale that maximizes the Sharpe ratio of daily portfolio
    returns (mean / std).

    Parameters
    ----------
    train_df : pd.DataFrame
        Training data with 'date', 'ticker', 'close' columns.
    regime_window : int
        HMM trailing window (default 200).
    regime_mode : str
        'heuristic' or 'hmm'.
    scale_grid : list of float, optional
        Candidate scale values. Default [0.0, 0.2, 0.4, 0.6, 0.8, 1.0].
    ma_window : int
        Heuristic mode MA window (default 200).
    vol_window : int
        Heuristic mode vol window (default 20).
    vol_median_window : int
        Heuristic mode vol median window (default 60).

    Returns
    -------
    best_scale : float
        Scale that maximizes Sharpe on train data.
    evidence : dict
        Grid search results with per-scale Sharpe values.
    """
    if scale_grid is None:
        scale_grid = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]

    evidence: Dict[str, object] = {
        "scale_grid": list(scale_grid),
        "regime_mode": regime_mode,
        "regime_window": regime_window,
        "grid_results": {},
        "best_scale": 1.0,
        "best_sharpe": -np.inf,
    }

    work = train_df[["date", "ticker", "close"]].copy()
    work = work.sort_values(["date", "ticker"])
    close_wide = work.pivot(index="date", columns="ticker", values="close")

    sorted_dates = sorted(work["date"].unique())
    if len(sorted_dates) < 2:
        evidence["note"] = "insufficient_dates"
        return 1.0, evidence

    # Compute daily market returns for Sharpe calculation
    market_proxy = close_wide.mean(axis=1)
    market_returns = market_proxy.pct_change().dropna()

    # Precompute scale indicators for all dates to avoid redundant HMM fits / regime detection
    precomputed_indicators = []
    for dt in sorted_dates:
        if dt not in market_returns.index:
            continue

        daily_ret = float(market_returns.loc[dt])
        if not np.isfinite(daily_ret):
            continue

        if regime_mode == "hmm":
            # Call compute_hmm_regime_scale with a dummy scale of 0.5.
            # We can retrieve the actual p_bear from the returned evidence dict.
            _, evidence_hmm, _ = compute_hmm_regime_scale(
                close_wide, dt,
                regime_window=regime_window,
                regime_scale=0.5,
            )
            # If HMM succeeded, we extract p_bear, otherwise fallback to 0.0 (no bear probability)
            p_bear = 0.0
            if (
                evidence_hmm
                and not evidence_hmm.get("insufficient_data")
                and not evidence_hmm.get("insufficient_returns")
                and not evidence_hmm.get("insufficient_clean_returns")
                and not evidence_hmm.get("hmm_exception")
            ):
                p_bear = float(evidence_hmm.get("p_bear", 0.0))
            precomputed_indicators.append((daily_ret, "hmm", p_bear))
        else:
            regime = detect_market_regime(
                close_wide, dt,
                ma_window=ma_window,
                vol_window=vol_window,
                vol_median_window=vol_median_window,
            )
            precomputed_indicators.append((daily_ret, "heuristic", regime))

    # For each candidate scale, compute Sharpe on train dates
    for candidate_scale in scale_grid:
        daily_scaled_returns = []

        for daily_ret, mode, value in precomputed_indicators:
            if mode == "hmm":
                p_bear = value
                # Compute scale dynamically using p_bear and the current candidate scale
                scale = 1.0 - p_bear * (1.0 - candidate_scale)
                scale = float(np.clip(scale, candidate_scale, 1.0))
            else:
                regime = value
                if regime == "bear":
                    scale = candidate_scale
                else:
                    scale = 1.0

            daily_scaled_returns.append(daily_ret * scale)

        if len(daily_scaled_returns) < 5:
            evidence["grid_results"][str(candidate_scale)] = {
                "sharpe": 0.0,
                "n_days": len(daily_scaled_returns),
            }
            continue

        ret_arr = np.array(daily_scaled_returns)
        mean_ret = float(np.mean(ret_arr))
        std_ret = float(np.std(ret_arr))
        sharpe = mean_ret / std_ret if std_ret > 1e-9 else 0.0

        evidence["grid_results"][str(candidate_scale)] = {
            "sharpe": round(sharpe, 6),
            "n_days": len(daily_scaled_returns),
            "mean_return": round(mean_ret, 8),
            "std_return": round(std_ret, 8),
        }

        if sharpe > evidence["best_sharpe"]:
            evidence["best_sharpe"] = round(sharpe, 6)
            evidence["best_scale"] = float(candidate_scale)

    best_scale = float(evidence["best_scale"])
    logger.info(
        f"[RegimeAutoOpt] Best scale={best_scale:.2f}, "
        f"Sharpe={evidence['best_sharpe']:.4f}, mode={regime_mode}"
    )
    return best_scale, evidence


def apply_risk_sizing_overlay(
    test_df: pd.DataFrame,
    portfolio_signal: pd.Series,
    config: RiskSizingConfig,
) -> tuple[pd.Series, Dict[str, object]]:
    """Apply risk/sizing overlay to portfolio signal on test data.

    PIT-safe: all inputs use trailing data only.

    Parameters
    ----------
    test_df : pd.DataFrame
        Test data with 'date', 'ticker', 'close' columns.
    portfolio_signal : pd.Series
        Per-row portfolio weight series (same index as test_df).
    config : RiskSizingConfig
        Overlay configuration.

    Returns
    -------
    modified_signal : pd.Series
        Portfolio signal after risk/sizing overlay.
    evidence : dict
        JSON-serializable evidence dict.
    """
    evidence: Dict[str, object] = {
        "gate": RISK_SIZING_OVERLAY_GATE_ID,
        "inverse_vol_sizing": config.inverse_vol_sizing,
        "confidence_scaling": config.confidence_scaling,
        "regime_sizing": config.regime_sizing,
        "inverse_vol_window": config.inverse_vol_window,
        "confidence_window": config.confidence_window,
        "n_rebalances_with_ivol": 0,
        "n_rebalances_with_confidence": 0,
        "n_rebalances_with_regime": 0,
        "avg_confidence_scale": 1.0,
        "confidence_scales": [],
        "regime_counts": {"bear": 0, "neutral": 0, "bull": 0, "unknown": 0},
        "regime_bear_scale": config.regime_sizing_scale,
        "regime_sizing_mode": getattr(config, "regime_sizing_mode", "heuristic"),
        "regime_sizing_window": getattr(config, "regime_sizing_window", 200),
        "regime_sizing_auto_optimize": getattr(config, "regime_sizing_auto_optimize", False),
        "regime_gate": REGIME_CONDITIONAL_SIZING_GATE_ID,
        "pit_safe": True,
        "no_current_bar_use": True,
        "no_oos_label_use": True,
    }

    if not config.enabled:
        evidence["note"] = "overlay_disabled_no_change"
        # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
        evidence["hmm_p_bear"] = {"dates": [], "values": []}
        return portfolio_signal.copy(), evidence

    modified = portfolio_signal.copy()
    work = test_df[["date", "ticker", "close"]].copy()
    work = work.sort_values(["date", "ticker"])

    # Build wide close prices for vol estimation
    close_wide = work.pivot(index="date", columns="ticker", values="close")

    sorted_dates = sorted(work["date"].unique())
    confidence_scales: List[float] = []
    n_ivol = 0
    n_regime_applied = 0

    # GATE: REGIME_CONDITIONAL_SIZING_20260616 — HMM parameter cache for stride
    _hmm_params_cache: dict = {}
    _regime_refit_stride = max(1, getattr(config, "regime_refit_stride", 5))
    _hmm_day_idx = 0  # counts HMM-eligible dates

    # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616 — collect daily p_bear
    _hmm_p_bear_dates: List[str] = []
    _hmm_p_bear_values: List[float] = []

    for i, dt in enumerate(sorted_dates):
        dt_mask = test_df["date"] == dt
        if not dt_mask.any():
            continue

        day_tickers = test_df.loc[dt_mask, "ticker"].unique().tolist()
        if not day_tickers:
            continue

        # --- Inverse-vol sizing ---
        if config.inverse_vol_sizing:
            # Use trailing close prices (up to but NOT including current date)
            trailing_idx = close_wide.index[close_wide.index < dt]
            if len(trailing_idx) >= config.inverse_vol_window + 1:
                trailing_prices = close_wide.loc[
                    trailing_idx[-(config.inverse_vol_window + 1):]
                ]
                avail_tickers = [
                    t for t in day_tickers if t in trailing_prices.columns
                ]
                if avail_tickers:
                    ivol_weights = compute_inverse_vol_weights(
                        trailing_prices,
                        avail_tickers,
                        window=config.inverse_vol_window,
                        floor=config.inverse_vol_floor,
                    )
                    # Apply: scale each ticker's signal by ivol_weight / equal_weight
                    n_tickers = len(avail_tickers)
                    eq_weight = 1.0 / max(n_tickers, 1)
                    for ticker in avail_tickers:
                        t_mask = dt_mask & (test_df["ticker"] == ticker)
                        scale = float(ivol_weights.get(ticker, eq_weight)) / eq_weight
                        modified.loc[t_mask] *= scale
                    n_ivol += 1

        # --- Confidence scaling ---
        if config.confidence_scaling:
            # Use trailing signal and return data for IC estimation
            trailing_idx = close_wide.index[close_wide.index < dt]
            if len(trailing_idx) >= max(10, config.confidence_window // 2):
                n_trail = min(config.confidence_window, len(trailing_idx))
                trailing_dates = trailing_idx[-n_trail:]
                trailing_returns = close_wide.loc[trailing_dates].pct_change().dropna()
                # Use the signal values from the portfolio_signal itself
                # (which is already T-1 lagged by upstream compute_alphas)
                sig_wide = (
                    pd.DataFrame({
                        "date": test_df["date"],
                        "ticker": test_df["ticker"],
                        "signal": modified,
                    })
                    .pivot(index="date", columns="ticker", values="signal")
                )
                sig_trailing = sig_wide.loc[
                    sig_wide.index.isin(trailing_dates)
                ]
                if not sig_trailing.empty and not trailing_returns.empty:
                    conf_scale = compute_confidence_scale(
                        sig_trailing,
                        trailing_returns,
                        window=config.confidence_window,
                        min_ic=config.confidence_min_ic,
                        max_scale=config.confidence_max_scale,
                        min_scale=config.confidence_min_scale,
                    )
                    # Apply confidence scale to all tickers on this date
                    modified.loc[dt_mask] *= conf_scale
                    confidence_scales.append(conf_scale)

        # --- Regime-conditional sizing ---
        # GATE: REGIME_CONDITIONAL_SIZING_20260616
        if config.regime_sizing:
            regime_mode = getattr(config, "regime_sizing_mode", "heuristic")

            if regime_mode == "hmm":
                # HMM-based regime detection (Hướng 3) with stride caching
                # GATE: REGIME_CONDITIONAL_SIZING_20260616
                _do_refit = (
                    _hmm_day_idx % _regime_refit_stride == 0
                    or not _hmm_params_cache
                )
                hmm_scale, hmm_ev, _new_params = compute_hmm_regime_scale(
                    close_wide,
                    dt,
                    regime_window=getattr(config, "regime_sizing_window", 200),
                    regime_scale=config.regime_sizing_scale,
                    init_params=_hmm_params_cache if _hmm_params_cache else None,
                    refit=_do_refit,
                )
                # Update cache if refit succeeded and returned params
                if _do_refit and _new_params:
                    _hmm_params_cache = _new_params
                elif not _do_refit and _new_params:
                    # Inference-only still returns current params
                    _hmm_params_cache = _new_params
                _hmm_day_idx += 1
                regime_counts = evidence["regime_counts"]
                # Classify by dominant state for counting
                if hmm_ev.get("insufficient_data") or hmm_ev.get("insufficient_returns") or hmm_ev.get("insufficient_clean_returns") or hmm_ev.get("hmm_exception"):
                    regime_counts["unknown"] = regime_counts.get("unknown", 0) + 1
                else:
                    p_bear = hmm_ev.get("p_bear", 0.0)
                    if p_bear > 0.5:
                        regime_counts["bear"] = regime_counts.get("bear", 0) + 1
                    elif hmm_ev.get("p_bull", 0.0) > 0.5:
                        regime_counts["bull"] = regime_counts.get("bull", 0) + 1
                    else:
                        regime_counts["neutral"] = regime_counts.get("neutral", 0) + 1

                modified.loc[dt_mask] *= hmm_scale
                if hmm_scale < 1.0:
                    n_regime_applied += 1
                evidence.setdefault("hmm_scales", []).append(round(hmm_scale, 4))
                # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
                # Collect daily p_bear for adaptive drawdown re-entry
                _p_bear_val = hmm_ev.get("p_bear", 0.0) if not (
                    hmm_ev.get("insufficient_data")
                    or hmm_ev.get("insufficient_returns")
                    or hmm_ev.get("insufficient_clean_returns")
                    or hmm_ev.get("hmm_exception")
                ) else 0.0
                _hmm_p_bear_dates.append(str(dt)[:10])
                _hmm_p_bear_values.append(float(_p_bear_val))
            else:
                # Heuristic mode (original MA/vol)
                regime = detect_market_regime(
                    close_wide,
                    dt,
                    ma_window=config.regime_ma_window,
                    vol_window=config.regime_vol_window,
                    vol_median_window=config.regime_vol_median_window,
                )
                regime_counts = evidence["regime_counts"]
                if regime in regime_counts:
                    regime_counts[regime] += 1
                else:
                    regime_counts[regime] = regime_counts.get(regime, 0) + 1

                if regime == "bear":
                    modified.loc[dt_mask] *= config.regime_sizing_scale
                    n_regime_applied += 1

    evidence["n_rebalances_with_ivol"] = n_ivol
    evidence["n_rebalances_with_confidence"] = len(confidence_scales)
    evidence["n_rebalances_with_regime"] = n_regime_applied
    evidence["regime_refit_stride"] = _regime_refit_stride
    evidence["hmm_total_steps"] = _hmm_day_idx
    # GATE: STAGE6_3_DRAWDOWN_ADAPTIVE_RE_ENTRY_20260616
    # Emit daily HMM bear probabilities for adaptive drawdown re-entry.
    # Only populated when regime_sizing is enabled and mode is 'hmm'.
    evidence["hmm_p_bear"] = {
        "dates": _hmm_p_bear_dates,
        "values": [round(v, 4) for v in _hmm_p_bear_values],
    }
    if confidence_scales:
        evidence["avg_confidence_scale"] = float(np.mean(confidence_scales))
        evidence["confidence_scales"] = [round(s, 4) for s in confidence_scales[:20]]

    return modified, evidence
