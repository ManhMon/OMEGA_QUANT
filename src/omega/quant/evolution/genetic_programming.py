"""Genetic Programming Engine for Alpha Discovery - V21_QUANT Layer 01.

Institutional-grade genetic programming for automated alpha factor discovery.
Evolves mathematical expressions using OHLCV and derived features to maximize IC.

Key Features:
- Tree-based GP with protected operators
- IC-based fitness with complexity penalty
- Diversity enforcement via Hall of Fame
- Numerical stability (winsorization, z-score normalization)
- Point-in-time compliance (no look-ahead bias)

Contract: layer_01_core_intelligence/genetic_programming_contract.md
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from omega.quant.evolution.alpha_to_execution_bridge import CANONICAL_METRIC_KEY

try:
    import bottleneck as bn
except ImportError:  # pragma: no cover - optional fast path
    bn = None

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
    """Rank transformation (percentile rank)."""
    if len(x) == 0:
        return x
    nan_mask = np.isnan(x)
    ranks = np.full(len(x), np.nan, dtype=float)
    valid_count = np.count_nonzero(~nan_mask)
    if valid_count:
        ranks[~nan_mask] = rankdata(x[~nan_mask], method='average') / valid_count
    return ranks


def _ts_rank(x: np.ndarray, window: int = 5) -> np.ndarray:
    """Rolling rank percentile (vectorized, no pandas rolling apply)."""
    if len(x) < window:
        return np.zeros_like(x, dtype=float)
    windows = np.stack([x[k:len(x) - window + 1 + k] for k in range(window)])
    target = windows[-1]
    ranks = (1.0 + np.sum(windows < target, axis=0) +
             0.5 * (np.sum(windows == target, axis=0) - 1)) / window
    valid = ~np.any(np.isnan(windows), axis=0)
    result = np.zeros(len(x), dtype=float)
    result[window - 1:] = np.where(valid, ranks, 0.0)
    return result


def _ts_std(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Rolling standard deviation."""
    if len(x) < window:
        return np.zeros_like(x)
    if bn is not None:
        values = bn.move_std(x, window=window, min_count=1, ddof=1)
        values[:window - 1] = np.nan
        return np.nan_to_num(values, nan=0.0)
    return pd.Series(x).rolling(window).std().fillna(0).values


def _ts_mean(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Rolling mean."""
    if len(x) < window:
        return np.zeros_like(x)
    if bn is not None:
        values = bn.move_mean(x, window=window, min_count=1)
        values[:window - 1] = np.nan
        return np.nan_to_num(values, nan=0.0)
    return pd.Series(x).rolling(window).mean().fillna(0).values


def _cached_spearman_corr(
    signal: np.ndarray,
    finite_mask: np.ndarray,
    target_ranks: np.ndarray,
) -> float:
    """Spearman correlation using cached target ranks."""
    signal_arr = np.asarray(signal)[finite_mask]
    if signal_arr.size < 2:
        return 0.0
    signal_ranks = rankdata(signal_arr, method='average')
    target_rank_slice = target_ranks[finite_mask]
    if target_rank_slice.size < 2:
        return 0.0
    corr = np.corrcoef(signal_ranks, target_rank_slice)[0, 1]
    if np.isnan(corr):
        return 0.0
    return float(corr)


def _precompute_target_ranks(target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cache finite target mask and ranks for repeated Spearman evaluation."""
    finite_mask = ~np.isnan(target)
    target_ranks = np.full(target.shape, np.nan, dtype=float)
    if np.any(finite_mask):
        target_ranks[finite_mask] = rankdata(target[finite_mask], method='average')
    return finite_mask, target_ranks


def _decay_linear(x: np.ndarray, window: int = 10) -> np.ndarray:
    """Linear decay weighted average (vectorized, no pandas rolling apply)."""
    if len(x) < window:
        return np.zeros_like(x, dtype=float)
    weights = np.arange(1, window + 1, dtype=float)
    x_clean = np.where(np.isnan(x), 0.0, x)
    conv = np.convolve(x_clean, weights[::-1], mode='full')[:len(x)]
    nan_counts = np.concatenate(([0], np.cumsum(np.isnan(x), dtype=int)))
    valid = np.zeros(len(x), dtype=bool)
    valid[window - 1:] = (
        nan_counts[window:] - nan_counts[:-window] == 0
    )
    return np.where(valid, conv / weights.sum(), 0.0)


# =============================================================================
# GP Node (Expression Tree)
# =============================================================================

@dataclass
class GPNode:
    """Node in genetic programming expression tree."""
    
    operator: str
    children: List[GPNode] = field(default_factory=list)
    value: Optional[str] = None  # Terminal node (feature name)
    _string_cached: Optional[str] = field(default=None, init=False, repr=False)
    
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
        if self._string_cached is not None:
            return self._string_cached
        
        if not self.children:
            result = self.value or "0"
        elif len(self.children) == 1:
            result = f"{self.operator}({self.children[0].to_string()})"
        elif len(self.children) == 2:
            result = f"({self.children[0].to_string()} {self.operator} {self.children[1].to_string()})"
        else:
            args = ", ".join(child.to_string() for child in self.children)
            result = f"{self.operator}({args})"
        
        self._string_cached = result
        return result
    
    def copy(self) -> GPNode:
        """Deep copy of tree."""
        return GPNode(
            operator=self.operator,
            children=[child.copy() for child in self.children],
            value=self.value
        )
    
    def get_random_subtree(self) -> GPNode:
        """Get random subtree for crossover."""
        nodes = self._collect_nodes()
        return random.choice(nodes)
    
    def _collect_nodes(self) -> List[GPNode]:
        """Collect all nodes in tree."""
        nodes = [self]
        for child in self.children:
            nodes.extend(child._collect_nodes())
        return nodes
    
    def replace_subtree(self, old: GPNode, new: GPNode) -> None:
        """Replace subtree (for crossover)."""
        self._string_cached = None  # Invalidate cache when tree structure changes
        for i, child in enumerate(self.children):
            if child is old:
                self.children[i] = new.copy()
                return
            child.replace_subtree(old, new)


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
    signal_pnl_score: float = 0.0
    
    def evaluate(
        self,
        features: Dict[str, np.ndarray],
        target: np.ndarray,
        hall_of_fame: List[GPIndividual],
        config: GeneticProgrammingConfig,
        target_ranks: Optional[np.ndarray] = None,
        finite_mask: Optional[np.ndarray] = None,
    ) -> None:
        """Evaluate fitness of individual."""
        try:
            # Execute expression tree
            alpha_series = self._execute_tree(self.tree, features)
            
            # Variance guard: reject constant signals
            if np.std(alpha_series) < 1e-6:
                self.fitness = -np.inf
                logger.debug(f"Rejected constant alpha: {self.tree.to_string()}")
                return
            
            # Winsorization (1%-99% quantile clipping)
            lower = np.nanpercentile(alpha_series, 1)
            upper = np.nanpercentile(alpha_series, 99)
            alpha_series = np.clip(alpha_series, lower, upper)
            
            # Z-score normalization
            alpha_series = (alpha_series - np.nanmean(alpha_series)) / (np.nanstd(alpha_series) + 1e-9)
            
            # Handle inf/nan
            alpha_series = np.nan_to_num(alpha_series, nan=0.0, posinf=0.0, neginf=0.0)
            
            if finite_mask is None or target_ranks is None:
                finite_mask, target_ranks = _precompute_target_ranks(target)

            valid_observations = int(np.count_nonzero(finite_mask))

            # Observation threshold: require 1000+ samples for institutional grade
            if valid_observations < config.min_observations:
                self.fitness = -np.inf
                logger.debug(f"Rejected low-observation alpha: {valid_observations} < {config.min_observations}")
                return
            # Calculate Information Coefficient (Spearman)
            ic = _cached_spearman_corr(alpha_series, finite_mask, target_ranks)

            self.ic_score = abs(ic)
            
            # Transaction Cost Penalty (Slippage + Fees)
            # Slippage: 0.1% per trade, Trading Fees: 0.15% total
            # Total: 0.25% per round-trip trade
            self.transaction_cost_penalty = 0.0
            self.turnover_rate = 0.0
            
            # Calculate turnover: count signal changes (sign flips)
            # PIT-safe: only uses past alpha values, no look-ahead
            alpha_sign = np.sign(alpha_series)
            signal_changes = np.sum(np.abs(np.diff(alpha_sign)) > 0)
            
            # Turnover rate: trades per observation
            if len(alpha_series) > 1:
                self.turnover_rate = signal_changes / len(alpha_series)
                
                # Transaction cost penalty: 0.25% per trade * turnover rate
                # Scale to IC units (typical IC ~0.01-0.10)
                # High turnover (e.g., 50% = 0.5 trades/obs) → penalty ~0.125
                self.transaction_cost_penalty = 0.0025 * self.turnover_rate
            self.signal_pnl_score = self.ic_score - self.transaction_cost_penalty
            
            # Progressive complexity penalty
            depth = self.tree.depth()
            if depth <= 2:
                self.complexity_penalty = 0.002 * depth
            elif depth <= 4:
                self.complexity_penalty = 0.003 * depth
            else:
                self.complexity_penalty = 0.008 * depth
            
            # Diversity penalty: penalize correlation with Hall of Fame
            self.diversity_penalty = 0.0
            if hall_of_fame:
                for hof_individual in hall_of_fame:
                    try:
                        hof_alpha = self._execute_tree(hof_individual.tree, features)
                        hof_alpha = np.nan_to_num(hof_alpha, nan=0.0, posinf=0.0, neginf=0.0)
                        
                        mask = ~(np.isnan(alpha_series) | np.isnan(hof_alpha))
                        if mask.sum() > 100:
                            a_clean, b_clean = alpha_series[mask], hof_alpha[mask]
                            corr = np.corrcoef(rankdata(a_clean), rankdata(b_clean))[0, 1]
                            if not np.isnan(corr) and abs(corr) > config.diversity_threshold:
                                self.diversity_penalty = max(self.diversity_penalty, 0.02)
                    except Exception as e:
                        logger.debug(f"Diversity check failed: {e}")
                        continue
            
            # Final fitness
            self.fitness = self.ic_score - self.complexity_penalty - self.diversity_penalty - self.transaction_cost_penalty
            
        except Exception as e:
            logger.debug(f"Fitness evaluation failed: {e}")
            self.fitness = -np.inf
    
    def _execute_tree(self, node: GPNode, features: Dict[str, np.ndarray]) -> np.ndarray:
        """Execute expression tree to compute alpha values."""
        # Terminal node (feature)
        if not node.children:
            if node.value in features:
                return features[node.value].copy()
            else:
                try:
                    val = float(node.value)
                    return np.full(len(next(iter(features.values()))), val)
                except ValueError:
                    return np.zeros(len(next(iter(features.values()))))
        
        # Unary operators
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
            else:
                return child_val
        
        # Binary operators
        elif len(node.children) == 2 and node.operator in ['+', '-', '*', '/', 'max', 'min']:
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
            else:
                return left_val
        
        # Time-series operators (with window parameter)
        elif len(node.children) == 2 and node.operator in ['ts_std', 'ts_mean', 'ts_rank', 'decay_linear']:
            child_val = self._execute_tree(node.children[0], features)
            window = int(self._execute_tree(node.children[1], features)[0])  # Extract window size
            window = max(2, min(window, 60))  # Clamp to [2, 60]
            
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
# GP Configuration
# =============================================================================

@dataclass
class GeneticProgrammingConfig:
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
# Genetic Programming Engine
# =============================================================================

class GeneticProgrammingEngine:
    """Genetic Programming Engine for alpha discovery."""
    
    def __init__(self, config: Optional[GeneticProgrammingConfig] = None):
        self.config = config or GeneticProgrammingConfig()
        self.population: List[GPIndividual] = []
        self.hall_of_fame: List[GPIndividual] = []
        self.history: List[Dict[str, float]] = []
        self.feature_names: List[str] = []
    
    def generate_random_tree(self, depth: int = 0) -> GPNode:
        """Generate random expression tree."""
        # Terminal node (feature or constant)
        if depth >= self.config.max_depth or (depth > 0 and random.random() < self.config.terminal_prob):
            return GPNode(operator='terminal', value=random.choice(self.feature_names))
        
        # At depth max_depth - 1, only allow terminal nodes to avoid exceeding max_depth
        if depth >= self.config.max_depth - 1:
            return GPNode(operator='terminal', value=random.choice(self.feature_names))
        
        # Choose operator type
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
        
        else:  # ts_ops
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
        """Crossover two individuals (subtree exchange)."""
        if random.random() > self.config.crossover_rate:
            return GPIndividual(tree=parent1.tree.copy())
        
        # Deep copy trees
        tree1 = parent1.tree.copy()
        tree2 = parent2.tree.copy()
        
        # Select random subtrees
        subtree1 = tree1.get_random_subtree()
        subtree2 = tree2.get_random_subtree()
        
        # Exchange subtrees
        tree1.replace_subtree(subtree1, subtree2)
        
        return GPIndividual(tree=tree1)
    
    def mutate(self, individual: GPIndividual) -> GPIndividual:
        """Mutate individual (subtree replacement)."""
        if random.random() > self.config.mutation_rate:
            return individual
        
        tree = individual.tree.copy()
        
        # Select random subtree to replace
        subtree = tree.get_random_subtree()
        new_subtree = self.generate_random_tree(depth=0)
        
        # Replace subtree
        tree.replace_subtree(subtree, new_subtree)
        
        return GPIndividual(tree=tree)
    
    def update_hall_of_fame(self) -> None:
        """Update Hall of Fame with diverse high-fitness individuals."""
        candidates = sorted(self.population, key=lambda ind: ind.fitness, reverse=True)
        
        self.hall_of_fame = []
        for candidate in candidates:
            if len(self.hall_of_fame) >= self.config.hall_of_fame_size:
                break
            
            # Check diversity with existing Hall of Fame
            is_diverse = True
            if self.hall_of_fame:
                # Simplified diversity check (already done in fitness evaluation)
                if candidate.diversity_penalty > 0:
                    is_diverse = False
            
            if is_diverse or len(self.hall_of_fame) == 0:
                self.hall_of_fame.append(candidate)
    
    def evolve(
        self,
        features: Dict[str, np.ndarray],
        target: np.ndarray
    ) -> List[GPIndividual]:
        """Run genetic programming evolution."""
        self.feature_names = list(features.keys())
        
        logger.info(f"Starting GP evolution: pop={self.config.population_size}, gen={self.config.generations}")
        logger.info(f"Features: {len(self.feature_names)}, Observations: {len(target)}")
        
        # Initialize population
        self.initialize_population()
        finite_mask, target_ranks = _precompute_target_ranks(target)
        
        for generation in range(self.config.generations):
            # Evaluate population
            for individual in self.population:
                individual.evaluate(
                    features,
                    target,
                    self.hall_of_fame,
                    self.config,
                    target_ranks=target_ranks,
                    finite_mask=finite_mask,
                )
            
            # Sort by fitness
            self.population.sort(key=lambda ind: ind.fitness, reverse=True)
            
            # Update Hall of Fame
            self.update_hall_of_fame()
            
            # Log progress
            best = self.population[0]
            avg_fitness = np.mean([ind.fitness for ind in self.population if ind.fitness > -np.inf])
            
            self.history.append({
                'generation': generation,
                'best_fitness': best.fitness,
                'best_ic': best.ic_score,
                'avg_fitness': avg_fitness,
                'hof_size': len(self.hall_of_fame)
            })
            
            logger.info(
                f"Gen {generation+1}/{self.config.generations}: "
                f"Best IC={best.ic_score:.4f}, Fitness={best.fitness:.4f}, "
                f"Turnover={best.turnover_rate:.2%}, TxCost={best.transaction_cost_penalty:.4f}, "
                f"Expr={best.tree.to_string()[:60]}..."
            )
            
            # Create new population
            new_population = []
            
            # Elitism: keep best individuals
            new_population.extend(self.population[:self.config.elitism_count])
            
            # Reinject Hall of Fame
            new_population.extend([ind for ind in self.hall_of_fame if ind not in new_population])
            
            # Generate offspring
            while len(new_population) < self.config.population_size:
                parent1 = self.tournament_selection()
                parent2 = self.tournament_selection()
                
                child = self.crossover(parent1, parent2)
                child = self.mutate(child)
                
                new_population.append(child)
            
            self.population = new_population[:self.config.population_size]
        
        logger.info(f"Evolution complete. Hall of Fame size: {len(self.hall_of_fame)}")
        return self.hall_of_fame


# =============================================================================
# Public API
# =============================================================================

def discover_alphas_gp(
    panel: pd.DataFrame,
    target: pd.Series,
    config: Optional[GeneticProgrammingConfig] = None
) -> List[Dict[str, Any]]:
    """Discover alpha factors using genetic programming.
    
    Args:
        panel: DataFrame with MultiIndex [timestamp, symbol] and feature columns
        target: Series with forward returns (same index as panel)
        config: GP configuration (optional)
    
    Returns:
        List of discovered alphas with metadata
    """
    # Convert panel to feature dict
    features = {col: panel[col].values for col in panel.columns}
    target_array = target.values
    
    # Run GP
    engine = GeneticProgrammingEngine(config)
    hall_of_fame = engine.evolve(features, target_array)
    
    # Format results
    results = []
    for i, individual in enumerate(hall_of_fame):
        results.append({
            'name': f'gp_alpha_{i+1}',
            'expression': individual.tree.to_string(),
            'ic': individual.ic_score,
            'fitness': individual.fitness,
            'depth': individual.tree.depth(),
            'size': individual.tree.size(),
            'complexity_penalty': individual.complexity_penalty,
            'diversity_penalty': individual.diversity_penalty,
            'transaction_cost_penalty': individual.transaction_cost_penalty,
            'turnover_rate': individual.turnover_rate
        })
    
    return results


if __name__ == '__main__':
    # Demo
    print("=" * 80)
    print("GENETIC PROGRAMMING ENGINE - DEMO")
    print("=" * 80)
    
    # Create synthetic data
    np.random.seed(42)
    n_samples = 2000
    n_features = 10
    
    # Generate features
    feature_data = {}
    for i in range(n_features):
        feature_data[f'feature_{i}'] = np.random.randn(n_samples)
    
    # Generate target with some correlation
    target = (
        0.3 * feature_data['feature_0'] +
        0.2 * feature_data['feature_1'] +
        np.random.randn(n_samples) * 0.5
    )
    
    # Run GP
    config = GeneticProgrammingConfig(
        population_size=50,
        generations=10,
        max_depth=3,
        min_observations=100
    )
    
    engine = GeneticProgrammingEngine(config)
    hall_of_fame = engine.evolve(feature_data, target)
    
    print(f"\n{'='*80}")
    print("HALL OF FAME")
    print(f"{'='*80}")
    for i, individual in enumerate(hall_of_fame):
        print(f"\n{i+1}. IC={individual.ic_score:.4f}, Fitness={individual.fitness:.4f}")
        print(f"   Expression: {individual.tree.to_string()}")
        print(f"   Depth={individual.tree.depth()}, Size={individual.tree.size()}")
    
    print(f"\n{'='*80}")
    print("✅ Genetic Programming demo complete")
    print(f"{'='*80}")

# Aliases for backward compatibility
GPConfig = GeneticProgrammingConfig
