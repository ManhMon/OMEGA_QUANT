"""
V21_QUANT: THOMPSON SAMPLING MODULE
Multi-armed bandit for model selection in SEAE.
"""

from typing import Dict, List, Any
import numpy as np


class ThompsonSampling:
    """
    Thompson Sampling bandit for model selection.
    
    Maintains Beta distributions for each model arm:
    - alpha_success: Number of successes (good IC weeks)
    - alpha_failure: Number of failures (poor IC weeks)
    """
    
    def __init__(self, n_arms: int = 3):
        """
        Initialize Thompson Sampling bandit.
        
        Args:
            n_arms: Number of model arms (default: 3 for conservative/moderate/aggressive)
        """
        self.n_arms = n_arms
        self.alpha_success = np.ones(n_arms)
        self.alpha_failure = np.ones(n_arms)
    
    def select_arm(self) -> int:
        """
        Select arm using Thompson Sampling.
        
        Returns:
            Selected arm index
        """
        # Sample from Beta distribution for each arm
        samples = np.random.beta(self.alpha_success, self.alpha_failure)
        return int(np.argmax(samples))
    
    def update(self, arm: int, reward: float):
        """
        Update arm statistics based on reward (fractional Bayesian update).
        
        Args:
            arm: Arm index to update
            reward: Reward value in [0, 1]; fractional credits assigned to both
                    alpha_success and alpha_failure proportionally.
        
        Raises:
            IndexError: If arm index is out of bounds
            ValueError: If reward is NaN or infinite
        """
        if arm < 0 or arm >= self.n_arms:
            raise IndexError(
                f"Arm index {arm} out of bounds for bandit with {self.n_arms} arms"
            )
        if not np.isfinite(reward):
            raise ValueError(f"Reward must be finite, got {reward}")
        
        reward = float(np.clip(reward, 0.0, 1.0))
        self.alpha_success[arm] += reward
        self.alpha_failure[arm] += (1.0 - reward)
    
    def get_state(self) -> Dict[str, Any]:
        """
        Get current bandit state.
        
        Returns:
            Dict with alpha_success and alpha_failure arrays
        """
        return {
            "alpha_success": self.alpha_success.tolist(),
            "alpha_failure": self.alpha_failure.tolist()
        }
    
    def load_state(self, state: Dict[str, Any]):
        """
        Load bandit state from dict.
        
        Args:
            state: Dict with alpha_success and alpha_failure arrays
        """
        self.alpha_success = np.array(state["alpha_success"])
        self.alpha_failure = np.array(state["alpha_failure"])
        self.n_arms = len(self.alpha_success)
    
    def add_challenger_arm(self, prior_alpha: float = 2.0, prior_beta: float = 2.0):
        """
        Add a new challenger arm with warm-start prior (informative Beta prior).
        
        Appends one arm initialized with (prior_alpha, prior_beta) instead of (1, 1)
        to allow faster exploration of a new model variant.
        
        Args:
            prior_alpha: Initial alpha_success for the new arm (default 2.0)
            prior_beta: Initial alpha_failure for the new arm (default 2.0)
        """
        self.alpha_success = np.append(self.alpha_success, prior_alpha)
        self.alpha_failure = np.append(self.alpha_failure, prior_beta)
        self.n_arms += 1


if __name__ == "__main__":
    print("=== Thompson Sampling Module Test ===")
    
    bandit = ThompsonSampling(n_arms=3)
    print(f"Initial state: {bandit.get_state()}")
    
    # Simulate 10 rounds
    for i in range(10):
        arm = bandit.select_arm()
        reward = np.random.random()
        bandit.update(arm, reward)
        print(f"Round {i+1}: arm={arm}, reward={reward:.2f}")
    
    print(f"Final state: {bandit.get_state()}")
