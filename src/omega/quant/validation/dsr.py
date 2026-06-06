"""
Deflated Sharpe Ratio (DSR)
============================

Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio: Correcting
for Selection Bias, Backtest Overfitting, and Non-Normality."

Why DSR matters
---------------
The vanilla Sharpe ratio assumes:
  1. Returns are i.i.d. Gaussian.
  2. Only ONE strategy was ever tested (no multiple-comparisons).

In practice both fail:
  - Returns have skew and excess kurtosis → SR variance is wrong.
  - Quants try N strategies → max(SR) is biased upward by sqrt(log N).

DSR returns the probability that the OBSERVED Sharpe is genuinely
above a given benchmark (default 0), AFTER deflating for:
  - non-normal moments (skew, kurtosis),
  - the number of independent trials N (selection bias),
  - the variance of trial Sharpes (search intensity).

Key formulas (Bailey & Lopez de Prado 2014):

  σ(SR̂) = sqrt( (1 - γ3·SR + (γ4 - 1)/4 · SR²) / (T - 1) )       (1)

  E[max{SRₙ}] ≈ V[{SRₙ}]^0.5 · ((1-γ)·Z⁻¹(1 - 1/N)
                + γ·Z⁻¹(1 - 1/(N·e)))                              (2)
  where γ ≈ 0.5772 (Euler-Mascheroni).

  DSR = Φ( (SR̂ - E[max]) / σ(SR̂) )                                (3)

Inputs:
  returns : 1-D array of strategy excess returns (per bar)
  n_trials: count of strategies tried during search (≥ 1)
  trial_sharpes: optional iterable of all trial Sharpes; if provided,
      V[{SRₙ}] is computed empirically. Otherwise we assume V=1 (worst
      case, conservative).

Output:
  DSRResult dataclass with sr, sr_annualized, sr_std, expected_max_sr,
  dsr (probability ≥ 0..1), and verdict (passes 0.95 threshold).

Version: 1.0.0 (Phase 3.2, OMEGA next-gen).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import e, log, sqrt
from typing import Optional, Sequence

import numpy as np
from scipy.stats import norm, skew

__all__ = ["DSRResult", "deflated_sharpe_ratio", "annualized_sharpe", "fold_level_dsr"]

EULER = 0.5772156649015329


@dataclass
class DSRResult:
    """Container for DSR diagnostics."""

    sr: float                    # raw (per-bar) Sharpe of returns
    sr_annualized: float         # annualized Sharpe (sqrt(periods/yr) scaled)
    sr_std: float                # σ(SR̂) per Bailey-LdP eq.(1)
    expected_max_sr: float       # E[max{SRₙ}] selection-bias term
    dsr: float                   # P(true SR > 0 | observations), in [0, 1]
    n_obs: int                   # T
    n_trials: int                # N
    skew: float                  # γ3
    kurtosis: float              # γ4 (non-excess; normal = 3)
    pass_threshold: bool         # dsr >= 0.95


def annualized_sharpe(returns: np.ndarray, periods_per_year: int = 252) -> float:
    """Annualize per-bar Sharpe by sqrt(periods_per_year). Caller must
    pass per-bar excess returns. Bias-corrected std (ddof=1).

    Uses the same near-zero std tolerance as deflated_sharpe_ratio to
    avoid catastrophic-cancellation blow-ups on near-constant series.
    """
    r = np.asarray(returns, dtype=float)
    if len(r) < 2:
        return 0.0
    std = float(np.std(r, ddof=1))
    if std < 1e-12 * max(abs(float(np.mean(r))), 1.0):
        return 0.0
    return float(np.mean(r) / std * sqrt(periods_per_year))


def _expected_max_sharpe(n_trials: int, trial_sr_var: float) -> float:
    """E[max{SRₙ}] under the assumption that trial Sharpes are i.i.d.
    with variance trial_sr_var. Closed form via extreme-value approx."""
    if n_trials <= 1:
        return 0.0
    sigma = sqrt(trial_sr_var) if trial_sr_var > 0 else 1.0
    # Bailey & LdP 2014, eq. (4) — Maximum Sharpe Ratio approximation
    z1 = norm.ppf(1.0 - 1.0 / n_trials)
    z2 = norm.ppf(1.0 - 1.0 / (n_trials * e))
    return sigma * ((1.0 - EULER) * z1 + EULER * z2)


def deflated_sharpe_ratio(
    returns: Sequence[float],
    n_trials: int = 1,
    trial_sharpes: Optional[Sequence[float]] = None,
    sr_benchmark: float = 0.0,
    periods_per_year: int = 252,
    benchmark_is_annualized: bool = False,
) -> DSRResult:
    """
    Compute the Deflated Sharpe Ratio.

    Args:
        returns: 1-D array of strategy excess returns (per bar).
        n_trials: number of strategies / hyperparameter configs tried
            during research. ≥ 1. Larger N deflates DSR more (correct).
        trial_sharpes: optional iterable of all trial Sharpes; if given,
            V[{SRₙ}] is computed empirically. Default V=1 (conservative).
        sr_benchmark: SR null hypothesis. By default interpreted as
            PER-BAR SR (matches Bailey-LdP formulas). Pass
            `benchmark_is_annualized=True` if you want to specify the
            benchmark in annualized SR units (1.0 = institutional grade).
            Internally converts via /sqrt(periods_per_year).
        periods_per_year: 252 for daily, 12 for monthly, etc. Used for
            annualized SR output and benchmark conversion.
        benchmark_is_annualized: if True, treat `sr_benchmark` as
            annualized SR and divide by sqrt(periods_per_year) before
            applying the test.

    Returns:
        DSRResult dataclass.
    """
    r = np.asarray(returns, dtype=float)
    T = len(r)
    if T < 2:
        return DSRResult(0, 0, 0, 0, 0.0, T, n_trials, 0, 3, False)

    std = float(np.std(r, ddof=1))
    # Treat near-zero std as degenerate (constant returns).
    # Floating point ops on identical values can produce 1e-19 std.
    if std < 1e-12 * max(abs(float(np.mean(r))), 1.0):
        return DSRResult(0, 0, 0, 0, 0.0, T, n_trials, 0, 3, False)

    sr = float(np.mean(r) / std)  # per-bar Sharpe (NOT annualized)
    sr_ann = sr * sqrt(periods_per_year)

    g3 = float(skew(r, bias=False))
    # Pearson kurtosis (non-excess: normal = 3); scipy returns excess,
    # so add 3.
    from scipy.stats import kurtosis as _kurt
    g4 = float(_kurt(r, fisher=False, bias=False))

    # σ(SR̂) — Bailey & LdP eq. (1)
    sr_var = (1 - g3 * sr + (g4 - 1) / 4.0 * sr * sr) / (T - 1)
    sr_std = sqrt(max(sr_var, 0.0))

    # E[max{SRₙ}]
    if trial_sharpes is not None and len(list(trial_sharpes)) > 1:
        trial_var = float(np.var(list(trial_sharpes), ddof=1))
    else:
        trial_var = 1.0  # conservative default
    e_max_sr = _expected_max_sharpe(n_trials, trial_var)

    # Convert annualized benchmark to per-bar units for eq.(3).
    bench_per_bar = (
        sr_benchmark / sqrt(periods_per_year)
        if benchmark_is_annualized
        else sr_benchmark
    )

    # DSR — eq. (3): Φ((SR - E[max] - benchmark) / σ(SR))
    if sr_std == 0:
        dsr = 1.0 if sr > e_max_sr + bench_per_bar else 0.0
    else:
        z = (sr - e_max_sr - bench_per_bar) / sr_std
        dsr = float(norm.cdf(z))

    return DSRResult(
        sr=sr,
        sr_annualized=sr_ann,
        sr_std=sr_std,
        expected_max_sr=e_max_sr,
        dsr=dsr,
        n_obs=T,
        n_trials=n_trials,
        skew=g3,
        kurtosis=g4,
        pass_threshold=dsr >= 0.95,
    )


def fold_level_dsr(
    fold_sharpes: Sequence[float],
    n_trials: int = 1,
    sr_benchmark: float = 0.0,
    bars_per_fold: int = 252,
    periods_per_year: int = 252,
    benchmark_is_annualized: bool = False,
) -> DSRResult:
    """Phase 3.9: DSR computed at FOLD level instead of pooled bars.

    Why this exists
    ---------------
    With CPCV(N=10, k=2) we generate 45 folds whose test windows OVERLAP
    on the calendar timeline. Pooling all daily returns into one long
    array and running ``deflated_sharpe_ratio`` overstates the effective
    sample size (ESS): 11_142 daily obs that come from a calendar of
    only ~1260 days = 9x over-sampling. Bailey-LdP eq.(1) assumes IID
    bar-level returns, so its sigma(SR_hat) understates uncertainty.

    Fold-level DSR fixes this by treating each fold's per-bar Sharpe as
    one IID observation. There are exactly N_folds samples, no
    over-sampling. Skew / kurtosis are computed over fold Sharpes, not
    over daily returns. Selection bias term still uses ``n_trials``
    (number of alpha hyper-parameters searched).

    Args:
        fold_sharpes: 1-D array of per-fold per-bar Sharpe ratios. Each
            element is ``mean(fold_returns) / std(fold_returns)``.
        n_trials: alpha grid size (or any other tuned hyper-parameter
            count). Same semantics as ``deflated_sharpe_ratio``.
        sr_benchmark: SR null hypothesis. Per-bar by default.
        bars_per_fold: average bars per fold; used to convert per-bar
            fold Sharpe back to annualized for reporting (default 252,
            i.e. assume each fold is roughly one trading year).
        periods_per_year: for annualised reporting.
        benchmark_is_annualized: if True, divide ``sr_benchmark`` by
            ``sqrt(periods_per_year)`` before applying.

    Returns:
        ``DSRResult`` with ``sr`` = mean fold Sharpe (per-bar), ``sr_std``
        = standard error of that mean using fold-level moments, ``dsr``
        = Phi((sr - E[max] - bench) / sr_std). ``n_obs`` is the number of
        FOLDS (not bars), ``skew`` / ``kurtosis`` are computed over fold
        Sharpes.
    """
    fs = np.asarray(list(fold_sharpes), dtype=float)
    fs = fs[np.isfinite(fs)]
    n_folds = len(fs)
    if n_folds < 2:
        return DSRResult(0, 0, 0, 0, 0.0, n_folds, n_trials, 0, 3, False)

    sr_mean = float(np.mean(fs))
    sr_var_sample = float(np.var(fs, ddof=1))
    sr_std_emp = sqrt(sr_var_sample) if sr_var_sample > 0 else 0.0
    # Treat near-zero spread (catastrophic cancellation) as degenerate.
    eps = 1e-12 * max(abs(sr_mean), 1.0)
    if sr_std_emp <= eps:
        bench_per_bar = (
            sr_benchmark / sqrt(periods_per_year)
            if benchmark_is_annualized
            else sr_benchmark
        )
        return DSRResult(
            sr=sr_mean,
            sr_annualized=sr_mean * sqrt(periods_per_year),
            sr_std=0.0,
            expected_max_sr=0.0,
            dsr=1.0 if sr_mean > bench_per_bar else 0.0,
            n_obs=n_folds,
            n_trials=n_trials,
            skew=0.0,
            kurtosis=3.0,
            pass_threshold=False,
        )

    g3 = float(skew(fs, bias=False))
    from scipy.stats import kurtosis as _kurt
    g4 = float(_kurt(fs, fisher=False, bias=False))

    # Bailey-LdP eq.(1) at fold level: T = n_folds, sr = sr_mean.
    # Numerator term uses fold-level skew / kurtosis, not bar-level.
    sr_var_estim = (
        1 - g3 * sr_mean + (g4 - 1) / 4.0 * sr_mean * sr_mean
    ) / (n_folds - 1)
    sr_std = sqrt(max(sr_var_estim, 0.0))

    # Selection bias term: variance of trial Sharpes is the spread
    # across folds (already empirical V).
    e_max_sr = _expected_max_sharpe(n_trials, sr_var_sample)

    bench_per_bar = (
        sr_benchmark / sqrt(periods_per_year)
        if benchmark_is_annualized
        else sr_benchmark
    )

    if sr_std == 0:
        dsr = 1.0 if sr_mean > e_max_sr + bench_per_bar else 0.0
    else:
        z = (sr_mean - e_max_sr - bench_per_bar) / sr_std
        dsr = float(norm.cdf(z))

    return DSRResult(
        sr=sr_mean,
        sr_annualized=sr_mean * sqrt(periods_per_year),
        sr_std=sr_std,
        expected_max_sr=e_max_sr,
        dsr=dsr,
        n_obs=n_folds,
        n_trials=n_trials,
        skew=g3,
        kurtosis=g4,
        pass_threshold=dsr >= 0.95,
    )
