"""Bayesian Online Change Point Detection (BOCPD).

Implements Adams & MacKay (2007) BOCPD with Normal-Inverse-Gamma conjugate
prior for Gaussian observations. Runs recursively on trailing portfolio
returns to detect distributional shifts in real time.

Gate: HYBRID_REGIME_DETECTION_20260619

PIT Safety: All computations use only trailing (past) returns.
No forward-looking data is accessed at any point.

Reference
---------
Adams, R.P. and MacKay, D.J.C. (2007).
"Bayesian Online Changepoint Detection."
arXiv:0710.3742 [stat.ML]
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BOCPDConfig:
    """Configuration for BOCPD with Normal-Inverse-Gamma observations.

    Parameters
    ----------
    hazard_rate : float
        1/expected_run_length. Higher = more frequent change points.
        Default 1/200 implies expected regime duration ~200 days.
    prior_mean : float
        Prior mean for the Gaussian observation model (mu_0).
    prior_var_scale : float
        Prior variance scaling factor (kappa_0). Larger = more diffuse prior.
    prior_alpha : float
        Shape parameter for Inverse-Gamma prior on variance (alpha_0).
    prior_beta : float
        Scale parameter for Inverse-Gamma prior on variance (beta_0).
    change_point_threshold : float
        Probability threshold to declare a change point (default 0.5).
    max_run_length : int
        Truncate run-length distribution beyond this for efficiency.
    trailing_window : int
        Number of trailing returns used for recursive update.
    """

    hazard_rate: float = 1.0 / 200.0
    prior_mean: float = 0.0
    prior_var_scale: float = 1.0
    prior_alpha: float = 2.0
    prior_beta: float = 1.0
    change_point_threshold: float = 0.5
    max_run_length: int = 500
    trailing_window: int = 252


@dataclass
class BOCPDState:
    """Internal state for recursive BOCPD updates.

    Attributes
    ----------
    run_length_probs : ndarray
        Probability mass function over run lengths, shape (T+1,).
    sufficient_stats : list of tuple
        (mu_n, kappa_n, alpha_n, beta_n) for each run length.
    time_step : int
        Current time step (number of observations ingested).
    change_point_probs : list of float
        History of P(change point at t) for each time step.
    """

    run_length_probs: np.ndarray = field(
        default_factory=lambda: np.array([1.0])
    )
    sufficient_stats: list = field(default_factory=list)
    time_step: int = 0
    change_point_probs: list = field(default_factory=list)


class BOCPDDetector:
    """Bayesian Online Change Point Detection for trailing returns.

    Uses a Normal-Inverse-Gamma (NIG) conjugate model so that the
    posterior for each run length can be updated in O(1) per step.

    PIT Safety
    ----------
    - ``update()`` only accepts a single new observation (the latest return).
    - ``fit_trailing()`` slices a window from a historical array, using only
      values at indices <= the current end of the window.
    - No future data is accessed.

    Usage
    -----
    >>> detector = BOCPDDetector()
    >>> for r in trailing_returns:
    ...     cp_prob, run_dist = detector.update(r)
    >>> detector.is_regime_change()
    True/False
    """

    def __init__(self, config: Optional[BOCPDConfig] = None):
        self.config = config or BOCPDConfig()
        self._state = self._init_state()

    def _init_state(self) -> BOCPDState:
        """Create a fresh BOCPD state (run length 0, prior-only)."""
        mu_0 = self.config.prior_mean
        kappa_0 = self.config.prior_var_scale
        alpha_0 = self.config.prior_alpha
        beta_0 = self.config.prior_beta

        state = BOCPDState(
            run_length_probs=np.array([1.0]),
            sufficient_stats=[(mu_0, kappa_0, alpha_0, beta_0)],
            time_step=0,
            change_point_probs=[],
        )
        return state

    def reset(self) -> None:
        """Reset detector to initial state."""
        self._state = self._init_state()

    def update(self, x_t: float) -> Tuple[float, np.ndarray]:
        """Process one new observation and return change-point probability.

        Parameters
        ----------
        x_t : float
            New observation (e.g., daily portfolio return).

        Returns
        -------
        cp_prob : float
            Probability that a change point occurred at this time step.
        run_dist : ndarray
            Current run-length distribution (truncated to max_run_length).
        """
        state = self._state
        cfg = self.config
        r_probs = state.run_length_probs
        stats = state.sufficient_stats

        # Number of possible run lengths (0 .. time_step)
        T = len(r_probs)

        # 1. Compute predictive probabilities under each run length
        pred_probs = np.zeros(T)
        for r in range(T):
            mu_n, kappa_n, alpha_n, beta_n = stats[r]
            # Student-t predictive: mean=mu_n, var=beta_n*(kappa_n+1)/(alpha_n*kappa_n)
            pred_var = beta_n * (kappa_n + 1.0) / (alpha_n * kappa_n + 1e-12)
            # Gaussian approximation of Student-t for numerical stability
            pred_probs[r] = _gaussian_pdf(x_t, mu_n, pred_var)

        # 2. Compute growth and change-point probabilities
        hazard = cfg.hazard_rate
        growth_probs = r_probs * pred_probs * (1.0 - hazard)
        cp_prob = np.sum(r_probs * pred_probs * hazard)

        # 3. New run-length distribution
        new_probs = np.empty(T + 1)
        new_probs[0] = cp_prob
        new_probs[1:] = growth_probs

        # Normalize
        total = np.sum(new_probs)
        if total > 0:
            new_probs /= total
        else:
            new_probs = np.ones(T + 1) / (T + 1)

        # 4. Update sufficient statistics for each run length
        new_stats = []
        # Run length 0: reset to prior
        new_stats.append(
            (cfg.prior_mean, cfg.prior_var_scale, cfg.prior_alpha, cfg.prior_beta)
        )
        # Run lengths 1..T: update NIG posterior
        for r in range(T):
            mu_n, kappa_n, alpha_n, beta_n = stats[r]
            kappa_new = kappa_n + 1.0
            mu_new = (kappa_n * mu_n + x_t) / kappa_new
            alpha_new = alpha_n + 0.5
            beta_new = beta_n + 0.5 * kappa_n * (x_t - mu_n) ** 2 / kappa_new
            new_stats.append((mu_new, kappa_new, alpha_new, beta_new))

        # 5. Truncate if exceeding max_run_length
        max_rl = cfg.max_run_length
        if len(new_probs) > max_rl + 1:
            new_probs = new_probs[: max_rl + 1]
            new_probs /= np.sum(new_probs)
            new_stats = new_stats[: max_rl + 1]

        # Update state — store normalized posterior P(r=0 | x_{1:t})
        state.run_length_probs = new_probs
        state.sufficient_stats = new_stats
        state.time_step += 1
        normalized_cp_prob = float(new_probs[0])
        state.change_point_probs.append(normalized_cp_prob)

        return normalized_cp_prob, new_probs.copy()

    def fit_trailing(self, returns: np.ndarray) -> Tuple[float, np.ndarray]:
        """Run BOCPD on a trailing window of returns.

        Parameters
        ----------
        returns : ndarray
            1D array of trailing returns (oldest first).

        Returns
        -------
        cp_prob : float
            Change-point probability at the last observation.
        run_dist : ndarray
            Run-length distribution at the last observation.
        """
        self.reset()
        window = returns[-self.config.trailing_window:]
        cp_prob = 0.0
        run_dist = np.array([1.0])
        for x_t in window:
            cp_prob, run_dist = self.update(float(x_t))
        return cp_prob, run_dist

    def is_regime_change(self) -> bool:
        """Check if the last observation triggered a change point."""
        if not self._state.change_point_probs:
            return False
        return self._state.change_point_probs[-1] >= self.config.change_point_threshold

    def get_change_point_history(self) -> np.ndarray:
        """Return full history of change-point probabilities."""
        return np.array(self._state.change_point_probs)

    def get_expected_run_length(self) -> float:
        """Return the expected current run length (E[r])."""
        probs = self._state.run_length_probs
        run_lengths = np.arange(len(probs))
        return float(np.sum(run_lengths * probs))

    def get_posterior_mean(self) -> float:
        """Return the posterior mean return, weighted by run-length probs.

        PIT Safety: Uses only the sufficient statistics from past observations.
        """
        probs = self._state.run_length_probs
        stats = self._state.sufficient_stats
        if len(stats) == 0:
            return 0.0
        weighted_mean = sum(p * s[0] for p, s in zip(probs, stats))
        return float(weighted_mean)

    def get_posterior_volatility(self) -> float:
        """Return the posterior std deviation, weighted by run-length probs.

        PIT Safety: Uses only the sufficient statistics from past observations.
        """
        probs = self._state.run_length_probs
        stats = self._state.sufficient_stats
        if len(stats) == 0:
            return 1.0
        weighted_var = 0.0
        for p, (mu_n, kappa_n, alpha_n, beta_n) in zip(probs, stats):
            if alpha_n > 1:
                var = beta_n / (alpha_n - 1.0)
            else:
                var = beta_n
            weighted_var += p * var
        return float(np.sqrt(max(weighted_var, 1e-12)))


def _gaussian_pdf(x: float, mu: float, var: float) -> float:
    """Evaluate Gaussian PDF at x given mean and variance."""
    if var <= 0:
        var = 1e-12
    diff = x - mu
    return float(np.exp(-0.5 * diff * diff / var) / np.sqrt(2.0 * np.pi * var))
