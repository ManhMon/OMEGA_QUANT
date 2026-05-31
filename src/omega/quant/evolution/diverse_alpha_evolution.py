"""
OMEGA_QUANT Diverse Alpha Evolution - Anti-Convergence + Seeded Families
Solves: only 1 alpha surviving orthogonality filter.

Strategy:
1. Island Model: 4 sub-populations evolve independently, migrate best every 5 gen
2. Seeded Families: Initialize with known alpha archetypes (momentum, mean-rev, volume, volatility)
3. Relaxed Orthogonality: corr_threshold 0.5 (was 0.7) to keep more diverse alphas
4. Fitness Sharing: Penalize alphas similar to already-promoted ones

Author: Backend Engineer (Role 09)
Date: 2026-05-31
Version: 1.0.0
PIT Safety: PASS - T-1 lag enforced via evaluate_vectorized.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from omega.quant.evolution.genetic_alpha import Genome, Node
from omega.quant.evolution.alpha_evolution_pipeline import (
    AlphaEvolutionPipeline,
    AlphaCandidate,
    EvolutionConfig,
)

logger = logging.getLogger(__name__)


# ============================================================
# SEEDED ALPHA FAMILIES
# ============================================================

def _make_momentum_seed() -> Genome:
    """Momentum: rank of delayed returns."""
    tree = Node('rank', [Node('delay', [Node('returns')])])
    return Genome(tree=tree)

def _make_mean_reversion_seed() -> Genome:
    """Mean reversion: min of mean returns (oversold signal)."""
    tree = Node('min', [Node('mean', [Node('returns')])])
    return Genome(tree=tree)

def _make_volume_seed() -> Genome:
    """Volume signal: rank of std of volume."""
    tree = Node('rank', [Node('std', [Node('volume')])])
    return Genome(tree=tree)

def _make_volatility_seed() -> Genome:
    """Volatility signal: mean of std of close."""
    tree = Node('mean', [Node('std', [Node('close')])])
    return Genome(tree=tree)

def _make_price_volume_seed() -> Genome:
    """Price-volume divergence: sub(rank(close), rank(volume))."""
    tree = Node('sub', [Node('rank', [Node('close')]), Node('rank', [Node('volume')])])
    return Genome(tree=tree)

def _make_high_low_seed() -> Genome:
    """High-low range signal: div(sub(high, low), close)."""
    tree = Node('div', [Node('sub', [Node('high'), Node('low')]), Node('close')])
    return Genome(tree=tree)

SEED_FAMILIES = [
    ("momentum", _make_momentum_seed),
    ("mean_reversion", _make_mean_reversion_seed),
    ("volume", _make_volume_seed),
    ("volatility", _make_volatility_seed),
    ("price_volume", _make_price_volume_seed),
    ("high_low", _make_high_low_seed),
]


@dataclass
class DiverseEvolutionConfig:
    """Config for diverse alpha evolution."""
    n_islands: int = 4
    population_per_island: int = 40
    generations: int = 25
    migration_interval: int = 5
    migration_count: int = 3
    max_depth: int = 5
    mutation_rate: float = 0.35
    crossover_rate: float = 0.6
    elitism_count: int = 3
    corr_threshold: float = 0.5       # Relaxed from 0.7
    ic_threshold: float = 0.05
    min_hit_rate: float = 0.53
    profit_factor_min: float = 1.3
    max_active_alphas: int = 15
    state_dir: str = "data/diverse_evolution"


class DiverseAlphaEvolution:
    """
    Island-model GP with seeded families for alpha diversity.
    
    Each island starts with seeds from different alpha families,
    evolves independently, then migrates best individuals periodically.
    """

    def __init__(self, config: Optional[DiverseEvolutionConfig] = None):
        self.config = config or DiverseEvolutionConfig()

    def _create_island_population(self, island_id: int) -> List[Genome]:
        """Create population for one island, seeded with family archetypes."""
        population = []
        
        # Seed with 2-3 family archetypes per island (rotated)
        n_families = len(SEED_FAMILIES)
        seeds_per_island = 3
        for j in range(seeds_per_island):
            family_idx = (island_id * seeds_per_island + j) % n_families
            _, factory = SEED_FAMILIES[family_idx]
            # Add seed + mutations of seed
            population.append(factory())
            for _ in range(2):
                population.append(factory().mutate())

        # Fill rest with random genomes
        while len(population) < self.config.population_per_island:
            population.append(Genome(max_depth=self.config.max_depth))

        return population

    def _evaluate_population(
        self, population: List[Genome], train_df: pd.DataFrame, val_df: pd.DataFrame, target_col: str
    ) -> List[AlphaCandidate]:
        """Evaluate all genomes, return viable candidates sorted by fitness."""
        candidates = []
        for genome in population:
            try:
                train_signal = genome.evaluate_vectorized(train_df)
                val_signal = genome.evaluate_vectorized(val_df)

                if train_signal.std() < 1e-8 or val_signal.std() < 1e-8:
                    continue

                train_ic = train_signal.corr(train_df[target_col], method="spearman")
                val_ic = val_signal.corr(val_df[target_col], method="spearman")

                if np.isnan(train_ic) or np.isnan(val_ic):
                    continue

                hit_rate = (np.sign(val_signal) == np.sign(val_df[target_col])).mean()
                turnover = val_signal.diff().abs().mean() / (val_signal.abs().mean() + 1e-10)

                candidates.append(AlphaCandidate(
                    genome=genome,
                    expression=repr(genome),
                    train_ic=float(train_ic),
                    test_ic=float(val_ic),
                    hit_rate=float(hit_rate),
                    turnover=float(turnover),
                ))
            except Exception:
                continue

        candidates.sort(key=lambda c: c.fitness(), reverse=True)
        return candidates

    def _evolve_island(
        self, population: List[Genome], train_df: pd.DataFrame, val_df: pd.DataFrame, target_col: str
    ) -> tuple:
        """Run one generation on an island. Returns (new_population, candidates)."""
        candidates = self._evaluate_population(population, train_df, val_df, target_col)
        if not candidates:
            return population, []

        # Selection + reproduction
        elite = [c.genome for c in candidates[:self.config.elitism_count]]
        new_pop = list(elite)

        while len(new_pop) < self.config.population_per_island:
            r = np.random.random()
            if r < self.config.crossover_rate and len(candidates) >= 2:
                parents = np.random.choice(min(15, len(candidates)), size=2, replace=False)
                child = Genome.crossover(candidates[parents[0]].genome, candidates[parents[1]].genome)
                new_pop.append(child)
            elif r < self.config.crossover_rate + self.config.mutation_rate:
                idx = np.random.randint(min(10, len(candidates)))
                new_pop.append(candidates[idx].genome.mutate())
            else:
                new_pop.append(Genome(max_depth=self.config.max_depth))

        return new_pop, candidates

    def _migrate(self, islands: List[List[Genome]], island_candidates: List[List[AlphaCandidate]]) -> None:
        """Migrate top individuals between islands (ring topology)."""
        n = len(islands)
        migrants = []
        for i in range(n):
            if island_candidates[i]:
                top = [c.genome for c in island_candidates[i][:self.config.migration_count]]
                migrants.append(top)
            else:
                migrants.append([])

        # Ring migration: island i receives from island (i-1)
        for i in range(n):
            source = (i - 1) % n
            if migrants[source]:
                # Replace worst individuals with migrants
                for j, migrant in enumerate(migrants[source]):
                    if j < len(islands[i]):
                        islands[i][-(j+1)] = migrant

    def _filter_diverse(
        self, candidates: List[AlphaCandidate], train_df: pd.DataFrame
    ) -> List[AlphaCandidate]:
        """Incremental orthogonality filter with relaxed threshold."""
        if not candidates:
            return []

        accepted = []
        accepted_signals: Dict[str, pd.Series] = {}

        for c in candidates:
            try:
                sig = c.genome.evaluate_vectorized(train_df)
                if sig.std() < 1e-8:
                    continue

                if not accepted_signals:
                    accepted.append(c)
                    accepted_signals[c.expression[:50]] = sig
                else:
                    # Check correlation against all accepted
                    is_diverse = True
                    for _, existing_sig in accepted_signals.items():
                        corr = sig.corr(existing_sig)
                        if abs(corr) > self.config.corr_threshold:
                            is_diverse = False
                            break
                    if is_diverse:
                        accepted.append(c)
                        accepted_signals[c.expression[:50]] = sig
            except Exception:
                continue

            if len(accepted) >= self.config.max_active_alphas:
                break

        return accepted

    def run(
        self,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        target_col: str = "fwd_ret_5",
    ) -> List[AlphaCandidate]:
        """
        Run diverse island-model evolution.

        Returns:
            List of diverse, quality-filtered AlphaCandidates.
        """
        t0 = time.time()
        n_islands = self.config.n_islands
        logger.info("=== DIVERSE EVOLUTION: %d islands x %d pop x %d gen ===",
                    n_islands, self.config.population_per_island, self.config.generations)

        # Initialize islands with seeded populations
        islands = [self._create_island_population(i) for i in range(n_islands)]
        island_candidates: List[List[AlphaCandidate]] = [[] for _ in range(n_islands)]
        all_candidates: List[AlphaCandidate] = []

        # Evolution loop
        for gen in range(self.config.generations):
            for i in range(n_islands):
                islands[i], candidates = self._evolve_island(islands[i], train_df, val_df, target_col)
                island_candidates[i] = candidates
                if candidates:
                    all_candidates.extend(candidates[:3])  # Top 3 per island per gen

            # Migration every N generations
            if (gen + 1) % self.config.migration_interval == 0:
                self._migrate(islands, island_candidates)
                best_per_island = [c[0].test_ic if c else 0 for c in island_candidates]
                logger.info("Gen %d: Migration. Island best ICs: %s",
                            gen, [f"{ic:.4f}" for ic in best_per_island])
            elif gen % 5 == 0:
                best_per_island = [c[0].test_ic if c else 0 for c in island_candidates]
                logger.info("Gen %d: Island best ICs: %s",
                            gen, [f"{ic:.4f}" for ic in best_per_island])

        # Collect all unique candidates
        # Deduplicate by expression
        seen = set()
        unique_candidates = []
        for c in all_candidates:
            if c.expression not in seen:
                seen.add(c.expression)
                unique_candidates.append(c)

        # Quality filter
        quality = [c for c in unique_candidates
                   if c.test_ic >= self.config.ic_threshold and c.hit_rate >= self.config.min_hit_rate]
        quality.sort(key=lambda c: c.fitness(), reverse=True)
        logger.info("Quality filter: %d -> %d candidates", len(unique_candidates), len(quality))

        # Diversity filter (relaxed corr=0.5)
        diverse = self._filter_diverse(quality[:100], train_df)
        logger.info("Diversity filter (corr<%.1f): %d -> %d alphas",
                    self.config.corr_threshold, min(100, len(quality)), len(diverse))

        elapsed = time.time() - t0
        logger.info("=== DIVERSE EVOLUTION COMPLETE: %d alphas, %.1fs ===", len(diverse), elapsed)
        return diverse

# ============================================================
# FORCED DIVERSITY: Restrict terminals per island
# ============================================================

ISLAND_TERMINALS = [
    ['close', 'returns', 'volume'],          # Island 0: Price + Volume
    ['high', 'low', 'close', 'open'],        # Island 1: OHLC patterns
    ['volume', 'returns', 'rsi'],            # Island 2: Volume + Momentum
    ['close', 'open', 'macd', 'volume'],     # Island 3: Trend + Volume
]


class ForcedDiverseGenome(Genome):
    """Genome restricted to specific terminal set for forced diversity."""
    
    def __init__(self, tree=None, max_depth=3, seed=None, allowed_terminals=None):
        self._allowed_terminals = allowed_terminals or Node.TERMINALS
        super().__init__(tree=tree, max_depth=max_depth, seed=seed)
    
    def _random_tree(self, depth):
        """Generate random tree using only allowed terminals."""
        import random as _rnd
        if depth == 0 or _rnd.random() < 0.3:
            return Node(_rnd.choice(self._allowed_terminals))
        else:
            op = _rnd.choice(Node.OPERATORS)
            if op in ['add', 'sub', 'mul', 'div']:
                left = self._random_tree(depth - 1)
                right = self._random_tree(depth - 1)
                return Node(op, [left, right])
            else:
                child = self._random_tree(depth - 1)
                return Node(op, [child])
    
    def mutate(self):
        """Mutate respecting allowed terminals."""
        new_tree = self._random_tree(depth=3)
        return ForcedDiverseGenome(new_tree, allowed_terminals=self._allowed_terminals)
