"""
OMEGA_QUANT Genetic Programming Engine (Layer 01)
Phase 3.3: Alpha Discovery - Genetic Programming

100% Vectorized | PIT-Safe | Institutional Grade

Ported from V21_QUANT layer_01_core_intelligence/genetic_programming.py
Adapted to OMEGA standards with stricter PIT compliance.

Key Features:
- Tree-based GP with protected operators
- IC-based fitness with complexity penalty
- Diversity enforcement via Hall of Fame
- Numerical stability (winsorization, z-score normalization)
- Point-in-time compliance (no look-ahead bias)

Author: Backend Engineer (Role 09)
Date: 2026-05-13
Version: 1.0.0 (V21 Port)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Protected Operators (Numerical Stability)
# =============================================================================

def _protected_div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Division with zero protection."""
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(np.abs(b) > 1e-9, a / b, 0.0)


def _protected_log(x: np.ndarray) -> np.ndarray:
    """Logarithm with negative/zero protection."""
    return np.log(np.abs(x) + 1e-9)


def _protected_sqrt(x: np.ndarray) -> np.ndarray:
    """Square root with negative protection."""
    return np.sqrt(np.abs(x))


def _protected_exp(x: np.ndarray) -> np.ndarray:
    """Exponential with overflow protection."""
    return np.exp(np.clip(x, -10, 10))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    """Sigmoid activation with overflow protection."""
    return 1.0 / (1.0 + _protected_exp(-x))


def _rank_transform(x: np.ndarray) -> np.ndarray:
    """Percentile rank transformation."""
    if len(x) == 0:
        return x
    return pd.Series(x).rank(pct=True, method='average').values


def _ts_rank(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Time-series rank within rolling window."""
    if len(x) < window:
        return np.zeros_like(x)
    return pd.Series(x).rolling(window).apply(
        lambda w: pd.Series(w).rank(pct=True).iloc[-1] if len(w) == window else np.nan,
        raw=True
    ).fillna(0.0).values


def _ts_std(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Rolling standard deviation."""
    if len(x) < window:
        return np.zeros_like(x)
    return pd.Series(x).rolling(window).std().fillna(0.0).values


def _ts_mean(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Rolling mean."""
    if len(x) < window:
        return np.zeros_like(x)
    return pd.Series(x).rolling(window).mean().fillna(0.0).values


def _decay_linear(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Linear decay weighted average."""
    if len(x) < window:
        return np.zeros_like(x)
    weights = np.arange(1, window + 1)
    return pd.Series(x).rolling(window).apply(
        lambda w: np.dot(w, weights) / weights.sum() if len(w) == window else np.nan,
        raw=True
    ).fillna(0.0).values


# =============================================================================
# GP Node (Expression Tree)
# =============================================================================

@dataclass
class GPNode:
    """Node in genetic programming expression tree."""
    
    operator: str
    children: List["GPNode"] = field(default_factory=list)
    value: Optional[str] = None  # Terminal node (feature name)
    
    def depth(self) -> int:
        """Calculate tree depth."""
        if not self.children:
            return 1
        return 1 + max(child.depth() for child in self.children)
    
    def size(self) -> int:
        """Calculate tree size (node count)."""
        if not self.children:
            return 1
        return 1 + sum(child.size() for child in self.children)
    
    def to_string(self) -> str:
        """Convert tree to readable expression string."""
        if not self.children:
            return self.value or "0"
        
        if len(self.children) == 1:
            return f"{self.operator}({self.children[0].to_string()})"
        elif len(self.children) == 2:
            return f"({self.children[0].to_string()} {self.operator} {self.children[1].to_string()})"
        else:
            args = ", ".join(child.to_string() for child in self.children)
            return f"{self.operator}({args})"
    
    def copy(self) -> "GPNode":
        """Deep copy of tree."""
        return GPNode(
            operator=self.operator,
            children=[child.copy() for child in self.children],
            value=self.value
        )
    
    def get_random_subtree(self) -> "GPNode":
        """Get random subtree for crossover."""
        nodes = self._collect_nodes()
        return random.choice(nodes)
    
    def _collect_nodes(self) -> List["GPNode"]:
        """Collect all nodes in tree."""
        nodes = [self]
        for child in self.children:
            nodes.extend(child._collect_nodes())
        return nodes
    
    def replace_subtree(self, old: "GPNode", new: "GPNode") -> None:
        """Replace subtree (for crossover)."""
        for i, child in enumerate(self.children):
            if child is old:
                self.children[i] = new.copy()
                return
            child.replace_subtree(old, new)


# =============================================================================
# GP Configuration
# =============================================================================

@dataclass
class GPConfig:
    """Configuration for genetic programming engine."""
    
    population_size: int = 100
    generations: int = 30
    max_depth: int = 5
    tournament_size: int = 5
    crossover_rate: float = 0.7
    mutation_rate: float = 0.2
    elitism_count: int = 1
    hall_of_fame_size: int = 10
    diversity_threshold: float = 0.7
    min_observations: int = 1000
    
    # Operator probabilities
    terminal_prob: float = 0.3
    unary_ops: List[str] = field(default_factory=lambda: ['abs', 'log', 'sqrt', 'rank', 'neg', 'sigmoid'])
    binary_ops: List[str] = field(default_factory=lambda: ['+', '-', '*', '/', 'max', 'min'])
    ts_ops: List[str] = field(default_factory=lambda: ['ts_std', 'ts_mean', 'ts_rank', 'decay_linear'])
    ts_windows: List[int] = field(default_factory=lambda: [5, 10, 20])


# =============================================================================
# GP Individual
# =============================================================================

@dataclass
class GPIndividual:
    """Individual in genetic programming population."""
    
    tree: GPNode
    fitness: float = -np.inf
    ic_score: float = 0.0
    complexity_penalty: float = 0.0
    diversity_penalty: float = 0.0
    transaction_cost_penalty: float = 0.0
    turnover_rate: float = 0.0
    
    def evaluate(
        self,
        features: Dict[str, np.ndarray],
        target: np.ndarray,
        hall_of_fame: List["GPIndividual"],
        config: GPConfig
    ) -> None:
        """Evaluate fitness of individual."""
        try:
            # Execute expression tree
            alpha_series = self._execute_tree(self.tree, features)
            
            # Variance guard: reject constant signals
            if np.std(alpha_series) < 1e-6:
                self.fitness = -np.inf
                logger.debug(f"Rejected constant alpha")
                return
            
            # Winsorization (1%-99% quantile clipping)
            lower = np.nanpercentile(alpha_series, 1)
            upper = np.nanpercentile(alpha_series, 99)
            alpha_series = np.clip(alpha_series, lower, upper)
            
            # Z-score normalization
            alpha_series = (alpha_series - np.nanmean(alpha_series)) / (np.nanstd(alpha_series) + 1e-9)
            
            # Handle inf/nan
            alpha_series = np.nan_to_num(alpha_series, nan=0.0, posinf=0.0, neginf=0.0)
            
            # Align with target and drop NaN
            combined = pd.DataFrame({'alpha': alpha_series, 'target': target}).dropna()
            
            # Observation threshold
            if len(combined) < config.min_observations:
                self.fitness = -np.inf
                return
            
            # Calculate IC (Spearman)
            ic, _ = spearmanr(combined['alpha'], combined['target'])
            if np.isnan(ic):
                ic = 0.0
            
            self.ic_score = abs(ic)
            
            # Turnover calculation
            alpha_sign = np.sign(alpha_series)
            signal_changes = np.sum(np.abs(np.diff(alpha_sign)) > 0)
            if len(alpha_series) > 1:
                self.turnover_rate = signal_changes / len(alpha_series)
                self.transaction_cost_penalty = 0.0025 * self.turnover_rate
            
            # Progressive complexity penalty
            depth = self.tree.depth()
            if depth <= 2:
                self.complexity_penalty = 0.002 * depth
            elif depth <= 4:
                self.complexity_penalty = 0.003 * depth
            else:
                self.complexity_penalty = 0.008 * depth
            
            # Diversity penalty
            self.diversity_penalty = 0.0
            if hall_of_fame:
                for hof_individual in hall_of_fame:
                    try:
                        hof_alpha = self._execute_tree(hof_individual.tree, features)
                        hof_alpha = np.nan_to_num(hof_alpha, nan=0.0, posinf=0.0, neginf=0.0)
                        corr_df = pd.DataFrame({'a': alpha_series, 'b': hof_alpha}).dropna()
                        if len(corr_df) > 100:
                            corr, _ = spearmanr(corr_df['a'], corr_df['b'])
                            if not np.isnan(corr) and abs(corr) > config.diversity_threshold:
                                self.diversity_penalty = max(self.diversity_penalty, 0.02)
                    except Exception:
                        continue
            
            # Final fitness
            self.fitness = self.ic_score - self.complexity_penalty - self.diversity_penalty - self.transaction_cost_penalty
            
        except Exception as e:
            logger.debug(f"Fitness evaluation failed: {e}")
            self.fitness = -np.inf
    
    def _execute_tree(self, node: GPNode, features: Dict[str, np.ndarray]) -> np.ndarray:
        """Execute expression tree to compute alpha values."""
        if not node.children:
            if node.value in features:
                return features[node.value].copy()
            else:
                return np.zeros(len(next(iter(features.values()))))
        
        if len(node.children) == 1:
            child_val = self._execute_tree(node.children[0], features)
            if node.operator == 'abs':
                return np.abs(child_val)
            elif node.operator == 'log':
                return _protected_log(child_val)
            elif node.operator == 'sqrt':
                return _protected_sqrt(child_val)
            elif node.operator == 'exp':
                return _protected_exp(child_val)
            elif node.operator == 'sigmoid':
                return _sigmoid(child_val)
            elif node.operator == 'rank':
                return _rank_transform(child_val)
            elif node.operator == 'neg':
                return -child_val
            return child_val
        
        elif len(node.children) == 2:
            left_val = self._execute_tree(node.children[0], features)
            right_val = self._execute_tree(node.children[1], features)
            
            if node.operator == '+':
                return left_val + right_val
            elif node.operator == '-':
                return left_val - right_val
            elif node.operator == '*':
                return left_val * right_val
            elif node.operator == '/':
                return _protected_div(left_val, right_val)
            elif node.operator == 'max':
                return np.maximum(left_val, right_val)
            elif node.operator == 'min':
                return np.minimum(left_val, right_val)
            return left_val
        
        elif len(node.children) == 2 and node.operator in ['ts_std', 'ts_mean', 'ts_rank', 'decay_linear']:
            child_val = self._execute_tree(node.children[0], features)
            window = int(self._execute_tree(node.children[1], features)[0])
            window = max(2, min(window, 60))
            
            if node.operator == 'ts_std':
                return _ts_std(child_val, window)
            elif node.operator == 'ts_mean':
                return _ts_mean(child_val, window)
            elif node.operator == 'ts_rank':
                return _ts_rank(child_val, window)
            elif node.operator == 'decay_linear':
                return _decay_linear(child_val, window)
        
        return np.zeros(len(next(iter(features.values()))))


# =============================================================================
# Genetic Programming Engine
# =============================================================================

class GeneticEngine:
    """Genetic Programming Engine for alpha discovery."""
    
    def __init__(self, config: Optional[GPConfig] = None):
        self.config = config or GPConfig()
        self.population: List[GPIndividual] = []
        self.hall_of_fame: List[GPIndividual] = []
        self.history: List[Dict[str, float]] = []
        self.feature_names: List[str] = []
    
    def generate_random_tree(self, depth: int = 0) -> GPNode:
        """Generate random expression tree."""
        if depth >= self.config.max_depth or (depth > 0 and random.random() < self.config.terminal_prob):
            return GPNode(operator='terminal', value=random.choice(self.feature_names))
        
        if depth >= self.config.max_depth - 1:
            return GPNode(operator='terminal', value=random.choice(self.feature_names))
        
        op_type = random.choice(['unary', 'binary', 'ts'])
        
        if op_type == 'unary':
            op = random.choice(self.config.unary_ops)
            child = self.generate_random_tree(depth + 1)
            return GPNode(operator=op, children=[child])
        elif op_type == 'binary':
            op = random.choice(self.config.binary_ops)
            left = self.generate_random_tree(depth + 1)
            right = self.generate_random_tree(depth + 1)
            return GPNode(operator=op, children=[left, right])
        else:
            op = random.choice(self.config.ts_ops)
            child = self.generate_random_tree(depth + 1)
            window = GPNode(operator='terminal', value=str(random.choice(self.config.ts_windows)))
            return GPNode(operator=op, children=[child, window])
    
    def initialize_population(self) -> None:
        """Initialize random population."""
        self.population = []
        for _ in range(self.config.population_size):
            tree = self.generate_random_tree()
            self.population.append(GPIndividual(tree=tree))
    
    def tournament_selection(self) -> GPIndividual:
        """Select individual via tournament selection."""
        tournament = random.sample(self.population, self.config.tournament_size)
        return max(tournament, key=lambda ind: ind.fitness)
    
    def crossover(self, parent1: GPIndividual, parent2: GPIndividual) -> GPIndividual:
        """Crossover two individuals."""
        if random.random() > self.config.crossover_rate:
            return GPIndividual(tree=parent1.tree.copy())
        
        tree1 = parent1.tree.copy()
        tree2 = parent2.tree.copy()
        subtree1 = tree1.get_random_subtree()
        subtree2 = tree2.get_random_subtree()
        tree1.replace_subtree(subtree1, subtree2)
        return GPIndividual(tree=tree1)
    
    def mutate(self, individual: GPIndividual) -> GPIndividual:
        """Mutate individual."""
        if random.random() > self.config.mutation_rate:
            return individual
        
        tree = individual.tree.copy()
        subtree = tree.get_random_subtree()
        new_subtree = self.generate_random_tree(depth=0)
        tree.replace_subtree(subtree, new_subtree)
        return GPIndividual(tree=tree)
    
    def update_hall_of_fame(self) -> None:
        """Update Hall of Fame."""
        candidates = sorted(self.population, key=lambda ind: ind.fitness, reverse=True)
        self.hall_of_fame = []
        for candidate in candidates:
            if len(self.hall_of_fame) >= self.config.hall_of_fame_size:
                break
            if candidate.diversity_penalty <= 0 or len(self.hall_of_fame) == 0:
                self.hall_of_fame.append(candidate)
    
    def evolve(
        self,
        features: Dict[str, np.ndarray],
        target: np.ndarray
    ) -> List[GPIndividual]:
        """Run genetic programming evolution."""
        self.feature_names = list(features.keys())
        
        logger.info(f"Starting GP evolution: pop={self.config.population_size}, gen={self.config.generations}")
        self.initialize_population()
        
        for generation in range(self.config.generations):
            for individual in self.population:
                individual.evaluate(features, target, self.hall_of_fame, self.config)
            
            self.population.sort(key=lambda ind: ind.fitness, reverse=True)
            self.update_hall_of_fame()
            
            best = self.population[0]
            self.history.append({
                'generation': generation,
                'best_fitness': best.fitness,
                'best_ic': best.ic_score
            })
            
            logger.info(f"Gen {generation+1}: IC={best.ic_score:.4f}, Fitness={best.fitness:.4f}")
        
        return self.hall_of_fame