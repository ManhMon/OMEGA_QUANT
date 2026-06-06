"""
OMEGA_QUANT Pareto Hall of Fame (Phase 2.3)

NSGA-II non-dominated sorting for diversity-aware GP Hall of Fame.

Objectives (all maximized):
    - obj1: ic_score              (signal strength)
    - obj2: -diversity_penalty    (diverse from existing HoF)
    - obj3: -tree.size()          (parsimony / simpler trees)

100% Vectorized | PIT-Safe | Institutional Grade

Author: Backend Engineer (Role 09)
Date: 2026-05-29
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Dict, List

import numpy as np

from .genetic_engine import GPIndividual

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ParetoHallOfFame:
    """Pareto-front Hall of Fame using NSGA-II non-dominated sorting."""

    def __init__(self, max_size: int = 20) -> None:
        if max_size <= 0:
            raise ValueError(f"max_size must be > 0, got {max_size}")
        self.max_size: int = max_size
        self.archive: List[GPIndividual] = []

    def update(
        self,
        candidates: List[GPIndividual],
        features: Dict[str, np.ndarray],
    ) -> None:
        """Update HoF with NSGA-II non-dominated sorting.

        Args:
            candidates: New GP individuals to consider for archive.
            features: Feature dict (reserved for future diversity metrics).
        """
        del features  # reserved hook; current objectives use ind attributes
        pool: List[GPIndividual] = self.archive + candidates
        if not pool:
            self.archive = []
            return
        if len(pool) <= self.max_size:
            self.archive = list(pool)
            return

        objectives = self._build_objectives(pool)
        fronts = self._fast_non_dominated_sort(objectives)

        new_archive: List[GPIndividual] = []
        for front in fronts:
            if not front:
                continue
            if len(new_archive) + len(front) <= self.max_size:
                new_archive.extend(pool[i] for i in front)
                continue
            remaining = self.max_size - len(new_archive)
            if remaining <= 0:
                break
            front_objectives = objectives[front]
            crowding = self._crowding_distance(front_objectives)
            top_local = np.argsort(-crowding)[:remaining]
            new_archive.extend(pool[front[i]] for i in top_local)
            break

        self.archive = new_archive
        logger.debug(
            "ParetoHoF.update: pool=%d, fronts=%d, archive=%d",
            len(pool), len(fronts), len(self.archive),
        )

    @staticmethod
    def _build_objectives(pool: List[GPIndividual]) -> np.ndarray:
        """Vectorized objective matrix (n x 3): all maximized."""
        return np.array(
            [
                [
                    float(ind.ic_score),
                    -float(ind.diversity_penalty),
                    -float(ind.tree.size()),
                ]
                for ind in pool
            ],
            dtype=np.float64,
        )

    def _fast_non_dominated_sort(
        self, objectives: np.ndarray
    ) -> List[List[int]]:
        """NSGA-II fast non-dominated sort. Returns list of fronts (index lists)."""
        n = len(objectives)
        if n == 0:
            return []

        # Vectorized domination matrix: dom[p, q] == True iff p dominates q.
        # a dominates b iff all(a >= b) and any(a > b).
        a = objectives[:, np.newaxis, :]   # (n, 1, m)
        b = objectives[np.newaxis, :, :]   # (1, n, m)
        ge_all = np.all(a >= b, axis=2)
        gt_any = np.any(a > b, axis=2)
        dom = ge_all & gt_any
        np.fill_diagonal(dom, False)

        domination_count = dom.sum(axis=0).astype(int)  # times p is dominated
        dominated_solutions: List[List[int]] = [
            list(np.where(dom[p])[0]) for p in range(n)
        ]

        fronts: List[List[int]] = [list(np.where(domination_count == 0)[0])]
        i = 0
        while fronts[i]:
            next_front: List[int] = []
            for p in fronts[i]:
                for q in dominated_solutions[p]:
                    domination_count[q] -= 1
                    if domination_count[q] == 0:
                        next_front.append(q)
            i += 1
            fronts.append(next_front)

        return [f for f in fronts if f]

    @staticmethod
    def _crowding_distance(objectives: np.ndarray) -> np.ndarray:
        """Compute NSGA-II crowding distance for diversity preservation."""
        n, m = objectives.shape
        if n == 0:
            return np.zeros(0, dtype=np.float64)
        if n <= 2:
            return np.full(n, np.inf, dtype=np.float64)

        distance = np.zeros(n, dtype=np.float64)
        for obj_idx in range(m):
            sorted_idx = np.argsort(objectives[:, obj_idx])
            distance[sorted_idx[0]] = np.inf
            distance[sorted_idx[-1]] = np.inf
            obj_min = objectives[sorted_idx[0], obj_idx]
            obj_max = objectives[sorted_idx[-1], obj_idx]
            obj_range = obj_max - obj_min
            if obj_range <= 0:
                continue
            # Vectorized neighbor diff for interior points
            interior = sorted_idx[1:-1]
            nxt = objectives[sorted_idx[2:], obj_idx]
            prv = objectives[sorted_idx[:-2], obj_idx]
            distance[interior] += (nxt - prv) / obj_range

        return distance

    def get_top_n(self, n: int) -> List[GPIndividual]:
        """Return top N individuals by IC score (descending)."""
        if n <= 0:
            return []
        return sorted(
            self.archive, key=lambda ind: ind.ic_score, reverse=True
        )[:n]

    def __len__(self) -> int:
        return len(self.archive)

    def __repr__(self) -> str:
        return (
            f"ParetoHallOfFame(max_size={self.max_size}, "
            f"archive_size={len(self.archive)})"
        )
