"""
Regime-Conditional Strategy Module
Layer 02: Strategy Logic

Implements a Gaussian Hidden Markov Model (HMM) from scratch using NumPy.
Detects market regimes (e.g., Bull, Bear, Sideways) and provides weights
for strategy/model adjustment.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
import warnings

# Suppress runtime warnings for division by zero in log space during EM
warnings.filterwarnings('ignore', category=RuntimeWarning)


@dataclass
class HMMConfig:
    """Configuration for Gaussian HMM"""
    n_components: int = 4  # Number of hidden states (Bull, Sideways, Bear, Volatile Sideways)
    n_iter: int = 100      # Maximum number of EM iterations
    tol: float = 1e-4      # Convergence tolerance for log-likelihood
    random_state: int = 42 # Seed for initialization
    features: List[str] = field(default_factory=lambda: ['volatility', 'trend'])


class GaussianHMM:
    """
    Gaussian Hidden Markov Model trained using the Baum-Welch (EM) algorithm.
    Implementation handles numerical stability using log-sum-exp trick where necessary
    or careful scaling.
    """

    def __init__(self, config: Optional[HMMConfig] = None):
        self.config = config or HMMConfig()
        self.n_components = self.config.n_components
        self.n_iter = self.config.n_iter
        self.tol = self.config.tol
        self.random_state = self.config.random_state
        self.features = self.config.features

        # Model parameters
        self.startprob_: Optional[np.ndarray] = None  # Shape (n_components,)
        self.transmat_: Optional[np.ndarray] = None   # Shape (n_components, n_components)
        self.means_: Optional[np.ndarray] = None      # Shape (n_components, n_features)
        self.covars_: Optional[np.ndarray] = None     # Shape (n_components, n_features, n_features)

        self.is_fitted = False

    def _init_params(self, X: np.ndarray):
        """Initialize parameters using simple heuristics (K-Means like or random)"""
        np.random.seed(self.random_state)
        n_samples, n_features = X.shape

        # Initialize start probabilities uniformly
        self.startprob_ = np.ones(self.n_components) / self.n_components

        # Initialize transition matrix (favoring self-transitions)
        self.transmat_ = np.ones((self.n_components, self.n_components)) * (1.0 - 0.8) / (self.n_components - 1)
        np.fill_diagonal(self.transmat_, 0.8)

        # Initialize means by randomly picking samples
        idx = np.random.choice(n_samples, self.n_components, replace=False)
        self.means_ = X[idx, :].copy()

        # Initialize covariances to the global covariance of the data
        global_cov = np.cov(X.T)
        if n_features == 1:
            global_cov = np.array([[global_cov]])
        self.covars_ = np.tile(global_cov, (self.n_components, 1, 1))

        # Add small regularization to diagonal to prevent singular matrices
        for i in range(self.n_components):
            self.covars_[i].flat[::n_features + 1] += 1e-6

    def _compute_log_likelihood(self, X: np.ndarray) -> np.ndarray:
        """
        Compute log-likelihood of each sample under each Gaussian component.
        Returns:
            log_prob: array of shape (n_samples, n_components)
        """
        n_samples, n_features = X.shape
        log_prob = np.zeros((n_samples, self.n_components))

        for i in range(self.n_components):
            cv = self.covars_[i].copy()
            mu = self.means_[i]

            # Add regularization for stability
            reg_strength = max(1e-6, 1e-4 * np.trace(cv) / n_features)
            cv += np.eye(n_features) * reg_strength

            try:
                # Use Cholesky decomposition for numerical stability
                L = np.linalg.cholesky(cv)
                diff = X - mu

                # Solve L * z = diff^T for z (more stable than computing inverse)
                z = np.linalg.solve(L, diff.T)  # Shape (n_features, n_samples)

                # Log determinant from Cholesky: log|cv| = 2 * sum(log(diag(L)))
                logdet = 2.0 * np.sum(np.log(np.diag(L)))

                # -0.5 * (k*log(2*pi) + log|cv| + ||z||^2)
                term1 = -0.5 * n_features * np.log(2 * np.pi)
                term2 = -0.5 * logdet
                term3 = -0.5 * np.sum(z ** 2, axis=0)  # Shape (n_samples,)

                log_prob[:, i] = term1 + term2 + term3

            except np.linalg.LinAlgError:
                # Cholesky failed: fallback to identity covariance
                diff = X - mu
                log_prob[:, i] = -0.5 * n_features * np.log(2 * np.pi) - 0.5 * np.sum(diff**2, axis=1)

        return log_prob

    def _forward(self, log_prob_matrix: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Forward pass of the Forward-Backward algorithm using log-sum-exp trick.
        Returns:
            log_alpha: shape (n_samples, n_components)
            log_likelihood: float
        """
        n_samples = log_prob_matrix.shape[0]
        log_alpha = np.zeros((n_samples, self.n_components))

        # Initialization (t=0)
        log_alpha[0] = np.log(np.maximum(self.startprob_, 1e-300)) + log_prob_matrix[0]

        # Pre-compute log transition matrix
        log_transmat = np.log(np.maximum(self.transmat_, 1e-300))

        # Recursion (t>0)
        for t in range(1, n_samples):
            for j in range(self.n_components):
                # log_alpha[t,j] = log(sum_i exp(log_alpha[t-1,i] + log(A[i,j]))) + log_prob[t,j]
                log_terms = log_alpha[t-1, :] + log_transmat[:, j]

                # Log-sum-exp trick
                max_log = np.max(log_terms)
                if max_log == -np.inf:
                    log_sum_exp = -np.inf
                else:
                    log_sum_exp = max_log + np.log(np.sum(np.exp(log_terms - max_log)))

                log_alpha[t, j] = log_sum_exp + log_prob_matrix[t, j]

        # Final log likelihood: log(sum_i exp(log_alpha[T-1, i]))
        last_terms = log_alpha[-1, :]
        max_last = np.max(last_terms)
        if max_last == -np.inf:
            log_likelihood = -np.inf
        else:
            log_likelihood = max_last + np.log(np.sum(np.exp(last_terms - max_last)))

        return log_alpha, log_likelihood

    def _backward(self, log_prob_matrix: np.ndarray) -> np.ndarray:
        """
        Backward pass of the Forward-Backward algorithm using log-sum-exp trick.
        Returns:
            log_beta: shape (n_samples, n_components)
        """
        n_samples = log_prob_matrix.shape[0]
        log_beta = np.zeros((n_samples, self.n_components))

        # Pre-compute log transition matrix
        log_transmat = np.log(np.maximum(self.transmat_, 1e-300))

        # Initialization at t=T-1
        log_beta[-1, :] = 0.0  # log(1.0)

        # Recursion
        for t in range(n_samples - 2, -1, -1):
            for i in range(self.n_components):
                # log_beta[t,i] = log(sum_j exp(log(A[i,j]) + log_prob[t+1,j] + log_beta[t+1,j]))
                log_terms = log_transmat[i, :] + log_prob_matrix[t+1, :] + log_beta[t+1, :]

                # Log-sum-exp trick
                max_log = np.max(log_terms)
                if max_log == -np.inf:
                    log_sum_exp = -np.inf
                else:
                    log_sum_exp = max_log + np.log(np.sum(np.exp(log_terms - max_log)))

                log_beta[t, i] = log_sum_exp

        return log_beta

    def _expectation(self, log_prob_matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        E-step: Compute responsibilities (gamma) and xi.
        """
        n_samples = log_prob_matrix.shape[0]
        log_alpha, log_likelihood = self._forward(log_prob_matrix)
        log_beta = self._backward(log_prob_matrix)

        # Gamma (responsibility of component i at time t)
        log_gamma = np.nan_to_num(log_alpha + log_beta, neginf=-1e10, posinf=1e10)

        # Normalize in log space (robust log-sum-exp)
        log_gamma_max = np.max(log_gamma, axis=1, keepdims=True)
        safe_max = np.where(np.isfinite(log_gamma_max), log_gamma_max, 0.0)
        exp_terms = np.exp(np.clip(log_gamma - safe_max, -700, 700))
        exp_terms = np.nan_to_num(exp_terms, nan=0.0, posinf=1e300, neginf=0.0)
        exp_sums = np.sum(exp_terms, axis=1, keepdims=True)
        exp_sums = np.where(~np.isfinite(exp_sums) | (exp_sums <= 0), 1e-300, exp_sums)
        log_gamma_norm = safe_max + np.log(exp_sums)
        log_gamma = log_gamma - log_gamma_norm
        gamma = np.exp(np.clip(log_gamma, -700, 700))
        gamma = np.nan_to_num(gamma, nan=0.0, posinf=1.0, neginf=0.0)
        gamma_sums = np.sum(gamma, axis=1, keepdims=True)
        gamma_sums = np.where(~np.isfinite(gamma_sums) | (gamma_sums <= 0), 1.0, gamma_sums)
        gamma = gamma / gamma_sums

        # Xi (probability of being in state i at t and state j at t+1)
        xi = np.zeros((n_samples - 1, self.n_components, self.n_components))

        for t in range(n_samples - 1):
            # Scale emissions for numerical stability
            emissions = np.exp(np.clip(log_prob_matrix[t+1] - np.max(log_prob_matrix[t+1]), -700, 700))
            emissions = np.nan_to_num(emissions, nan=0.0, posinf=1e300, neginf=0.0)

            for i in range(self.n_components):
                alpha_term = np.exp(np.clip(log_alpha[t, i], -700, 700))
                beta_term = np.exp(np.clip(log_beta[t+1, :], -700, 700))
                xi[t, i, :] = alpha_term * self.transmat_[i, :] * emissions * beta_term

            xi[t] = np.nan_to_num(xi[t], nan=0.0, posinf=0.0, neginf=0.0)
            # Normalize
            s = np.sum(xi[t])
            if np.isfinite(s) and s > 0:
                xi[t] /= s

        return gamma, xi, log_likelihood

    def _maximization(self, X: np.ndarray, gamma: np.ndarray, xi: np.ndarray):
        """
        M-step: Update model parameters.
        """
        n_samples, n_features = X.shape

        # Update start probabilities
        start = np.nan_to_num(gamma[0], nan=1.0 / self.n_components, posinf=1.0 / self.n_components, neginf=0.0)
        s0 = np.sum(start)
        self.startprob_ = start / s0 if s0 > 0 else np.ones(self.n_components) / self.n_components

        # Update transition matrix
        sum_xi = np.nan_to_num(np.sum(xi, axis=0), nan=0.0, posinf=0.0, neginf=0.0)
        sum_gamma_t = np.nan_to_num(np.sum(gamma[:-1], axis=0), nan=0.0, posinf=0.0, neginf=0.0)
        self.transmat_ = sum_xi / (sum_gamma_t[:, np.newaxis] + 1e-10)
        self.transmat_ = np.nan_to_num(self.transmat_, nan=0.0, posinf=0.0, neginf=0.0)

        # Normalize rows robustly
        row_sums = np.sum(self.transmat_, axis=1, keepdims=True)
        invalid_rows = ~np.isfinite(row_sums) | (row_sums <= 0)
        self.transmat_ = np.where(invalid_rows, 1.0 / self.n_components, self.transmat_ / np.where(row_sums <= 0, 1.0, row_sums))

        # Update means and covariances
        sum_gamma = np.nan_to_num(np.sum(gamma, axis=0), nan=0.0, posinf=0.0, neginf=0.0)

        for i in range(self.n_components):
            # Means
            weight = max(sum_gamma[i], 1e-10)
            weighted_sum = np.sum(np.nan_to_num(gamma[:, i:i+1], nan=0.0) * X, axis=0)
            candidate_mean = weighted_sum / weight

            # Keep previous mean if candidate is invalid
            if np.any(~np.isfinite(candidate_mean)):
                candidate_mean = self.means_[i]
            self.means_[i] = candidate_mean

            # Covariances
            diff = X - self.means_[i]
            covar = np.dot((np.nan_to_num(gamma[:, i:i+1], nan=0.0) * diff).T, diff) / weight
            covar = np.nan_to_num(covar, nan=0.0, posinf=0.0, neginf=0.0)

            # Stronger Regularization for VN Market
            reg_base = np.trace(covar) / n_features if np.isfinite(np.trace(covar)) else 1.0
            reg_strength = max(1e-6, 1e-4 * max(reg_base, 1e-6))
            covar_reg = covar + np.eye(n_features) * reg_strength

            # Keep previous covariance if invalid
            if np.any(~np.isfinite(covar_reg)):
                covar_reg = self.covars_[i]

            self.covars_[i] = covar_reg

    def fit(self, X: np.ndarray) -> 'GaussianHMM':
        """
        Train HMM parameters using Baum-Welch EM algorithm.

        Args:
            X: Input data matrix (n_samples, n_features)
        """
        # Ensure correct shape
        if len(X.shape) == 1:
            X = X.reshape(-1, 1)

        self._init_params(X)

        prev_log_likelihood = -np.inf

        for iter_idx in range(self.n_iter):
            # E-step
            log_prob_matrix = self._compute_log_likelihood(X)
            gamma, xi, log_likelihood = self._expectation(log_prob_matrix)

            # Check convergence
            if iter_idx > 0 and abs(log_likelihood - prev_log_likelihood) < self.tol:
                print(f"HMM converged at iteration {iter_idx}")
                break

            prev_log_likelihood = log_likelihood

            # M-step
            self._maximization(X, gamma, xi)

        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Find the most likely state sequence (Viterbi path).

        Args:
            X: Input data matrix (n_samples, n_features)

        Returns:
            state_sequence: Array of shape (n_samples,) containing predicted states
        """
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction.")

        if len(X.shape) == 1:
            X = X.reshape(-1, 1)

        n_samples = X.shape[0]
        log_prob_matrix = self._compute_log_likelihood(X)

        # Viterbi variables
        viterbi = np.zeros((n_samples, self.n_components))
        backpointer = np.zeros((n_samples, self.n_components), dtype=int)

        # Log scale transition probabilities
        log_transmat = np.log(np.maximum(self.transmat_, 1e-300))

        # Initialization
        viterbi[0] = np.log(np.maximum(self.startprob_, 1e-300)) + log_prob_matrix[0]

        # Recursion
        for t in range(1, n_samples):
            for j in range(self.n_components):
                # Prob of being in state j at time t, coming from state i
                trans_probs = viterbi[t-1] + log_transmat[:, j]
                best_prev_state = np.argmax(trans_probs)

                viterbi[t, j] = trans_probs[best_prev_state] + log_prob_matrix[t, j]
                backpointer[t, j] = best_prev_state

        # Termination & Path Backtracking
        state_sequence = np.zeros(n_samples, dtype=int)
        state_sequence[-1] = np.argmax(viterbi[-1])

        for t in range(n_samples - 2, -1, -1):
            state_sequence[t] = backpointer[t+1, state_sequence[t+1]]

        return state_sequence

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Compute the posterior probability of each state using Forward-Backward (Smoothing).
        WARNING: This uses future data and should ONLY be used for historical analysis.
        For live trading, use predict_proba_online() instead.

        Args:
            X: Input data matrix (n_samples, n_features)

        Returns:
            probabilities: Array of shape (n_samples, n_components)
        """
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction.")

        if len(X.shape) == 1:
            X = X.reshape(-1, 1)

        log_prob_matrix = self._compute_log_likelihood(X)
        log_alpha, _ = self._forward(log_prob_matrix)
        log_beta = self._backward(log_prob_matrix)

        log_gamma = log_alpha + log_beta
        log_gamma_max = np.max(log_gamma, axis=1, keepdims=True)
        safe_max = np.where(np.isfinite(log_gamma_max), log_gamma_max, 0.0)
        exp_terms = np.exp(np.clip(log_gamma - safe_max, -700, 700))
        exp_sums = np.sum(exp_terms, axis=1, keepdims=True)
        exp_sums = np.where(exp_sums <= 0, 1e-300, exp_sums)
        probs = exp_terms / exp_sums
        probs = np.nan_to_num(probs, nan=1.0 / self.n_components, posinf=1.0 / self.n_components, neginf=1.0 / self.n_components)
        probs = probs / np.sum(probs, axis=1, keepdims=True)
        return probs

    def predict_proba_online(self, X: np.ndarray) -> np.ndarray:
        """
        Compute the FILTERED probability of each state using Forward pass ONLY.
        SAFE FOR LIVE TRADING: No look-ahead bias.
        """
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction.")
        if len(X.shape) == 1:
            X = X.reshape(-1, 1)
        log_prob_matrix = self._compute_log_likelihood(X)
        log_alpha, _ = self._forward(log_prob_matrix)
        log_alpha_max = np.max(log_alpha, axis=1, keepdims=True)
        safe_max = np.where(np.isfinite(log_alpha_max), log_alpha_max, 0.0)
        exp_terms = np.exp(np.clip(log_alpha - safe_max, -700, 700))
        exp_sums = np.sum(exp_terms, axis=1, keepdims=True)
        exp_sums = np.where(exp_sums <= 0, 1e-300, exp_sums)
        probs = exp_terms / exp_sums
        probs = np.nan_to_num(probs, nan=1.0 / self.n_components, posinf=1.0 / self.n_components, neginf=1.0 / self.n_components)
        probs = probs / np.sum(probs, axis=1, keepdims=True)
        return probs

    def predict_proba_incremental(
        self, 
        X: np.ndarray, 
        prev_posterior: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Compute the FILTERED probability for a SINGLE step (incremental).
        Standard math: 
        1. Predict: prior_t = prev_posterior @ transmat_
        2. Update:  unnorm_t = prior_t * P(x_t | state)
        3. Normalize: posterior_t = unnorm_t / sum(unnorm_t)

        Args:
            X: Input data for a single step (1, n_features) or (n_features,)
            prev_posterior: Posterior from yesterday (n_components,)

        Returns:
            posterior_t: New posterior for today (n_components,)
        """
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction.")

        # Ensure X is (1, n_features)
        if len(X.shape) == 1:
            X = X.reshape(1, -1)
        elif X.shape[0] != 1:
            raise ValueError("predict_proba_incremental only supports single-step input.")

        # 1. Prediction step: yesterday's posterior becomes today's prior via transition matrix
        if prev_posterior is None:
            # First step: use model start probabilities
            prior = self.startprob_
        else:
            # Standard Chapman-Kolmogorov step
            prior = np.dot(prev_posterior, self.transmat_)

        # 2. Update step: combine prior with current observation likelihood
        # Compute log-likelihood for current step: (1, n_components)
        log_obs_prob = self._compute_log_likelihood(X)
        obs_prob = np.exp(np.clip(log_obs_prob, -700, 700))[0] # (n_components,)

        # Bayesian update
        unnorm_posterior = prior * obs_prob
        
        # 3. Normalization
        post_sum = np.sum(unnorm_posterior)
        if post_sum > 0:
            posterior_t = unnorm_posterior / post_sum
        else:
            # Fallback to prior if observation is extremely unlikely
            posterior_t = prior

        return posterior_t


class RegimeConditionalStrategy:
    """
    High-level strategy wrapper that uses the GaussianHMM to detect market regimes
    and outputs regime-aware signals/weights for the ensemble.
    """
    def __init__(self, config: Optional[HMMConfig] = None):
        self.config = config or HMMConfig()
        self.hmm = GaussianHMM(config=self.config)
        self.regime_map: Dict[int, str] = {}  # Maps state ID (0,1,2) to semantic label (e.g., 'Bull', 'Bear')

    def fit(self, features_df: pd.DataFrame, target_returns: Optional[pd.Series] = None):
        """
        Fit the HMM and map hidden states to semantic regimes using historical returns.
        """
        # Ensure we only use configured features
        missing = [f for f in self.config.features if f not in features_df.columns]
        if missing:
            raise ValueError(f"Missing required features for HMM: {missing}")

        X = features_df[self.config.features].values

        # Standardize features for stable HMM training
        self.feature_means_ = np.mean(X, axis=0)
        self.feature_stds_ = np.std(X, axis=0) + 1e-8
        X_scaled = (X - self.feature_means_) / self.feature_stds_

        # Train HMM
        self.hmm.fit(X_scaled)

        # Map states to regimes (if returns are provided, we can infer Bull/Bear)
        if target_returns is not None:
            self._map_regimes_from_returns(X_scaled, target_returns.values)
        else:
            # Fallback: robust VN mapping using Volatility + Trend
            self._map_regimes_by_volatility_and_trend()

        return self

    def _map_regimes_from_returns(self, X: np.ndarray, y: np.ndarray):
        """Map states based on average returns in that state"""
        states = self.hmm.predict(X)
        state_returns = {}
        state_vols = {}

        for i in range(self.config.n_components):
            mask = (states == i)
            if mask.sum() > 0:
                state_returns[i] = np.mean(y[mask])
                state_vols[i] = np.std(y[mask])
            else:
                state_returns[i] = 0.0
                state_vols[i] = 0.0

        # Sort states by return: Highest = Bull, Lowest = Bear, Middle = Sideways
        sorted_states = sorted(state_returns.keys(), key=lambda k: state_returns[k])

        if self.config.n_components == 3:
            self.regime_map = {
                sorted_states[0]: 'Bear',      # Lowest return
                sorted_states[1]: 'Sideways',  # Middle return
                sorted_states[2]: 'Bull'       # Highest return
            }
        elif self.config.n_components == 4:
            # 4-state mapping: Bull, Sideways, Bear, Volatile Sideways
            # Sort by return, then check volatility for middle states
            median_vol = np.median(list(state_vols.values()))
            self.regime_map = {}
            self.regime_map[sorted_states[0]] = 'Bear'  # Lowest return
            self.regime_map[sorted_states[3]] = 'Bull'  # Highest return

            # Middle two states: distinguish by volatility
            mid_states = [sorted_states[1], sorted_states[2]]
            mid_vols = [(s, state_vols[s]) for s in mid_states]
            mid_vols_sorted = sorted(mid_vols, key=lambda x: x[1])

            self.regime_map[mid_vols_sorted[0][0]] = 'Sideways'  # Lower vol
            self.regime_map[mid_vols_sorted[1][0]] = 'Volatile Sideways'  # Higher vol
        else:
            self.regime_map = {i: f'Regime_{i}' for i in range(self.config.n_components)}

    def _map_regimes_by_volatility(self):
        """Map states based on variance of the first feature (usually volatility)"""
        vols = {}
        for i in range(self.config.n_components):
            vols[i] = self.hmm.covars_[i, 0, 0]

        # Highest vol = Bear/Crisis, Lowest vol = Bull/Calm
        sorted_states = sorted(vols.keys(), key=lambda k: vols[k])

        if self.config.n_components == 3:
            self.regime_map = {
                sorted_states[0]: 'Bull',      # Low vol
                sorted_states[1]: 'Sideways',  # Med vol
                sorted_states[2]: 'Bear'       # High vol
            }
        else:
            self.regime_map = {i: f'Regime_{i}' for i in range(self.config.n_components)}

    def predict_regime(self, features_df: pd.DataFrame, mode: str = 'online') -> Tuple[np.ndarray, np.ndarray]:
        """
        Predict regimes for new data.

        Args:
            features_df: DataFrame with required features
            mode: 'online' (Forward-only, safe for trading) or 'smooth' (Forward-Backward, analysis only)

        Returns:
            (semantic_labels, state_probabilities)
        """
        X = features_df[self.config.features].values
        X_scaled = (X - getattr(self, 'feature_means_', 0)) / getattr(self, 'feature_stds_', 1)

        if mode == 'online':
            # SAFE: Forward-only filtering (no look-ahead)
            probs = self.hmm.predict_proba_online(X_scaled)
            # Infer states from filtered probabilities ONLY (No Viterbi)
            states = np.argmax(probs, axis=1)
        elif mode == 'smooth':
            # RISKY: Forward-Backward smoothing (uses future data)
            import logging
            logging.warning("Using 'smooth' mode for regime prediction. This is NOT safe for live trading!")
            probs = self.hmm.predict_proba(X_scaled)
            states = self.hmm.predict(X_scaled)
        else:
            raise ValueError(f"Invalid mode: {mode}. Use 'online' or 'smooth'.")

        # Convert numeric states to semantic labels
        semantic_labels = np.array([self.regime_map.get(s, f"State_{s}") for s in states])

        return semantic_labels, probs

    def _map_regimes_by_volatility_and_trend(self):
        """Use both volatility AND trend (assumed feature 1) for robust mapping in VN Market."""
        state_metrics = []

        for i in range(self.config.n_components):
            vol = self.hmm.covars_[i, 0, 0]
            trend = self.hmm.means_[i, 1] if self.hmm.means_.shape[1] > 1 else 0.0
            state_metrics.append((i, vol, trend))

        if self.config.n_components == 3:
            # Original 3-state logic
            for i in range(self.config.n_components):
                vol = self.hmm.covars_[i, 0, 0]

                if self.hmm.means_.shape[1] > 1:
                    trend = self.hmm.means_[i, 1]
                    if trend > 0.1 and vol < 0.5 * np.max(self.hmm.covars_[:, 0, 0]):
                        label = 'Bull'
                    elif trend < -0.1:
                        label = 'Bear'
                    else:
                        label = 'Sideways'
                else:
                    vols = [self.hmm.covars_[j, 0, 0] for j in range(self.config.n_components)]
                    sorted_idx = np.argsort(vols)
                    if i == sorted_idx[0]:
                        label = 'Bull'
                    elif i == sorted_idx[-1]:
                        label = 'Bear'
                    else:
                        label = 'Sideways'

                self.regime_map[i] = label

        elif self.config.n_components == 4:
            # 4-state logic: Bull, Sideways, Bear, Volatile Sideways
            # Sort by trend (descending)
            sorted_by_trend = sorted(state_metrics, key=lambda x: x[2], reverse=True)

            # Highest trend = Bull
            self.regime_map[sorted_by_trend[0][0]] = 'Bull'

            # Lowest trend = Bear
            self.regime_map[sorted_by_trend[3][0]] = 'Bear'

            # Middle two: distinguish by volatility
            mid_states = [sorted_by_trend[1], sorted_by_trend[2]]
            mid_sorted_by_vol = sorted(mid_states, key=lambda x: x[1])

            self.regime_map[mid_sorted_by_vol[0][0]] = 'Sideways'  # Lower vol
            self.regime_map[mid_sorted_by_vol[1][0]] = 'Volatile Sideways'  # Higher vol
        else:
            # Fallback for other n_components
            for i in range(self.config.n_components):
                self.regime_map[i] = f'Regime_{i}'
