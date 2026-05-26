"""
Reinforcement Learning Agent for Portfolio Optimization.

Implements a PPO (Proximal Policy Optimization) agent that learns
to allocate capital weights across assets.

PIT Safety: Agent receives state vectors that are already T-1 lagged.
    No future information in state construction.
Vectorization: All tensor operations are batch-vectorized via PyTorch.

Author: OMEGA_QUANT Team
Version: 2.4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

__all__ = [
    "RLConfig",
    "RLPortfolioAgent",
]

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    nn = None  # type: ignore[assignment]


@dataclass
class RLConfig:
    """Configuration for the RL portfolio agent."""

    n_assets: int = 5
    state_dim: int = 20
    learning_rate: float = 3e-4
    gamma: float = 0.99
    clip_epsilon: float = 0.2
    n_epochs: int = 4
    reward_type: str = "sharpe"  # "sharpe", "sortino", or "raw_return"
    transaction_cost_bps: float = 10.0
    max_turnover: float = 0.5
    cost_model: str = "linear"  # "linear" or "sqrt"


class RLPortfolioAgent:
    """
    PPO-based portfolio allocation agent.

    Treats portfolio weight allocation as a continuous action space
    problem where the state is the current market feature vector.

    The agent outputs portfolio weights that sum to 1 (long-only).
    Transaction costs are incorporated into the reward function.

    PIT Contract:
    - State vectors must be constructed from T-1 lagged features only.
    - Reward is computed from realized (past) returns only.
    """

    def __init__(self, config: Optional[RLConfig] = None) -> None:
        self.config = config or RLConfig()
        self._policy_net: Any = None
        self._optimizer: Any = None

        if TORCH_AVAILABLE:
            self._build_network()
        else:
            logger.warning(
                "PyTorch not found. RLPortfolioAgent will use equal-weight fallback."
            )

    def _build_network(self) -> None:
        """Build Actor-Critic network."""

        class _ActorCritic(nn.Module):
            def __init__(self, state_dim: int, n_assets: int):
                super().__init__()
                self.shared = nn.Sequential(
                    nn.Linear(state_dim, 128),
                    nn.ReLU(),
                    nn.Linear(128, 64),
                    nn.ReLU(),
                )
                self.actor = nn.Sequential(
                    nn.Linear(64, n_assets),
                    nn.Softmax(dim=-1),
                )
                self.critic = nn.Linear(64, 1)

            def forward(
                self, state: torch.Tensor
            ) -> tuple[torch.Tensor, torch.Tensor]:
                shared_out = self.shared(state)
                return self.actor(shared_out), self.critic(shared_out)

        self._policy_net = _ActorCritic(
            self.config.state_dim, self.config.n_assets
        )
        self._optimizer = torch.optim.Adam(
            self._policy_net.parameters(), lr=self.config.learning_rate
        )

    def allocate(self, state: np.ndarray) -> np.ndarray:
        """
        Given a state vector, output portfolio weights.

        Weights sum to 1 (long-only, via softmax).

        Args:
            state: Feature vector of shape (state_dim,).

        Returns:
            Portfolio weights of shape (n_assets,).
        """
        if not TORCH_AVAILABLE or self._policy_net is None:
            return np.ones(self.config.n_assets, dtype=np.float64) / self.config.n_assets

        self._policy_net.eval()
        with torch.no_grad():
            state_t = torch.FloatTensor(state).unsqueeze(0)
            weights, _ = self._policy_net(state_t)
            return weights.numpy().flatten()

    def compute_reward(
        self,
        returns: np.ndarray,
        prev_weights: Optional[np.ndarray] = None,
        new_weights: Optional[np.ndarray] = None,
    ) -> float:
        """
        Compute reward based on portfolio returns with transaction costs.

        Args:
            returns: Array of per-period returns.
            prev_weights: Previous portfolio weights (for turnover calc).
            new_weights: New portfolio weights (for turnover calc).

        Returns:
            Scalar reward value.
        """
        if len(returns) < 2:
            return 0.0

        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns)) + 1e-8

        # Base reward
        if self.config.reward_type == "sharpe":
            base_reward = mean_ret / std_ret * np.sqrt(252)
        elif self.config.reward_type == "sortino":
            downside = float(np.std(returns[returns < 0])) + 1e-8
            base_reward = mean_ret / downside * np.sqrt(252)
        else:
            base_reward = mean_ret

        # Transaction cost penalty (vectorized)
        cost_penalty = 0.0
        if prev_weights is not None and new_weights is not None:
            turnover = float(np.sum(np.abs(new_weights - prev_weights)))

            if turnover > self.config.max_turnover:
                cost_penalty -= (turnover - self.config.max_turnover) * 0.5

            cost_bps_frac = self.config.transaction_cost_bps / 10000.0
            if self.config.cost_model == "linear":
                cost = turnover * cost_bps_frac
            else:  # sqrt model
                cost = np.sqrt(turnover) * cost_bps_frac

            cost_penalty -= cost

        return base_reward + cost_penalty

    def train_episode(
        self,
        states: np.ndarray,
        returns: np.ndarray,
        n_ppo_epochs: Optional[int] = None,
    ) -> float:
        """
        Run one PPO training step on a batch of experiences.

        Args:
            states: State vectors of shape (T, state_dim).
            returns: Per-period portfolio returns of shape (T,).
            n_ppo_epochs: Number of PPO epochs (defaults to config).

        Returns:
            Average loss over training epochs.
        """
        if not TORCH_AVAILABLE or self._policy_net is None:
            return 0.0

        n_epochs = n_ppo_epochs or self.config.n_epochs

        states_t = torch.FloatTensor(states)
        returns_t = torch.FloatTensor(returns)

        # Normalize rewards (vectorized)
        returns_t = (returns_t - returns_t.mean()) / (returns_t.std() + 1e-8)

        total_loss = 0.0
        for _ in range(n_epochs):
            weights, values = self._policy_net(states_t)

            # Advantage estimation
            advantage = returns_t.unsqueeze(1) - values.detach()
            value_loss = nn.MSELoss()(values, returns_t.unsqueeze(1))

            # Policy loss (advantage-weighted log probs)
            log_probs = torch.log(weights + 1e-8).mean(dim=-1)
            policy_loss = -(log_probs * advantage.squeeze()).mean()

            loss = policy_loss + 0.5 * value_loss

            self._optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                self._policy_net.parameters(), 0.5
            )
            self._optimizer.step()

            total_loss += float(loss.item())

        return total_loss / n_epochs
