"""
Evolution Engine - OMEGA_QUANT Phase 6.
Hypothesis generation and promotion with leakage guards.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger("OmegaEvolutionEngine")

@dataclass
class EvolutionConfig:
    """Configuration for evolution engine."""
    max_generations: int = 10
    population_size: int = 50
    mutation_rate: float = 0.1
    crossover_rate: float = 0.5
    min_ic_improvement: float = 0.01  # Minimum IC improvement for promotion

class EvolutionEngine:
    """Generates and validates alpha hypotheses with leakage protection."""
    
    def __init__(self, config: Optional[EvolutionConfig] = None):
        self.config = config or EvolutionConfig()
        
    def generate_hypothesis(
        self,
        features: pd.DataFrame,
        labels: pd.Series,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate a new alpha hypothesis.
        
        Args:
            features: Feature matrix (samples x features)
            labels: Target labels
            seed: Random seed for reproducibility
            
        Returns:
            Hypothesis dict with signal, IC, and metadata
        """
        if seed is not None:
            np.random.seed(seed)
            
        # Simple linear combination of features
        n_features = features.shape[1]
        weights = np.random.randn(n_features)
        
        norm = np.linalg.norm(weights)
        if norm > 0:
            weights = weights / norm
        else:
            weights = np.zeros(n_features)
            weights[0] = 1.0  # Safe fallback
        
        signal = features @ weights
        
        # Compute IC (Information Coefficient)
        ic = signal.corr(labels)
        
        return {
            "signal": signal,
            "ic": float(ic),
            "weights": weights,
            "generation": 0,
            "seed": seed
        }
    
    def evolve(
        self,
        population: List[Dict[str, Any]],
        features: pd.DataFrame,
        labels: pd.Series
    ) -> List[Dict[str, Any]]:
        """
        Evolve population to next generation.
        
        Args:
            population: Current generation of hypotheses
            features: Feature matrix
            labels: Target labels
            
        Returns:
            Next generation population
        """
        # Sort by IC (descending)
        sorted_pop = sorted(population, key=lambda x: x["ic"], reverse=True)
        
        # Keep top 20% (elitism)
        elite_count = max(1, len(sorted_pop) // 5)
        elite = sorted_pop[:elite_count]
        
        # Generate offspring
        offspring = []
        while len(offspring) < len(population) - elite_count:
            parent1 = elite[np.random.randint(len(elite))]
            parent2 = elite[np.random.randint(len(elite))]
            
            # Crossover
            child_weights = (parent1["weights"] + parent2["weights"]) / 2
            
            # Mutation
            if np.random.random() < self.config.mutation_rate:
                child_weights += np.random.randn(len(child_weights)) * 0.1
            
            # Normalize with zero-norm guard
            norm = np.linalg.norm(child_weights)
            if norm > 0:
                child_weights = child_weights / norm
            else:
                child_weights = parent1["weights"].copy()
            
            signal = features @ child_weights
            ic = signal.corr(labels)
            
            offspring.append({
                "signal": signal,
                "ic": float(ic),
                "weights": child_weights,
                "generation": parent1["generation"] + 1
            })
        
        return elite + offspring
    
    def check_leakage(
        self,
        signal: pd.Series,
        labels: pd.Series
    ) -> bool:
        """
        Check for lookahead leakage in signal.
        
        Args:
            signal: Alpha signal
            labels: Future labels
            
        Returns:
            True if leakage detected
        """
        # Signal should be computed from data <= T-1
        # Labels should be available at T+1 or later
        # Check: signal at T should not correlate with labels at T
        if len(signal) != len(labels):
            return True
            
        # Correlation-based check
        correlation = signal.corr(labels)
        
        # If correlation is NaN (constant signal), treat as potential issue
        if pd.isna(correlation):
            logger.warning("Leakage guard: correlation is NaN (constant signal/labels). Suspect leakage or dead signal.")
            return True
            
        # Hard threshold for linear lookahead
        if abs(correlation) > 0.95:
            logger.error(f"Leakage guard: extreme correlation ({correlation:.4f}) detected.")
            return True
            
        return False
