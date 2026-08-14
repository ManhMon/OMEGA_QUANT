from contextlib import contextmanager
from types import MethodType, SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from omega.quant.evolution.diverse_alpha_evolution import (
    DiverseAlphaEvolution,
    DiverseEvolutionConfig,
)
from omega.quant.evolution.genetic_alpha import Genome, Node


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"target": [0.1, 0.2, 0.3]})


def _market_frame() -> pd.DataFrame:
    close = pd.Series([10.0, 11.0, 13.0, 12.0, 14.0, 16.0, 15.0, 17.0])
    open_ = close - 0.4
    high = close + 0.6
    low = close - 0.8
    volume = pd.Series([100, 120, 150, 130, 170, 210, 190, 230], dtype=float)
    returns = close.pct_change().fillna(0.0)
    target = returns.shift(-1).fillna(returns.iloc[-1])
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "returns": returns,
            "rsi": pd.Series([40, 42, 47, 45, 51, 58, 55, 60], dtype=float),
            "macd": pd.Series([0.1, 0.15, 0.22, 0.18, 0.3, 0.38, 0.34, 0.41], dtype=float),
            "target": target,
        }
    )


def _population() -> list[Genome]:
    return [
        Genome(tree=Node("rank", [Node("close")])),
        Genome(tree=Node("delay", [Node("returns")])),
        Genome(tree=Node("std", [Node("volume")])),
        Genome(tree=Node("div", [Node("sub", [Node("high"), Node("low")]), Node("close")])),
    ]


def test_evaluate_population_uses_joblib_parallel_and_contexts(monkeypatch):
    events = []

    @contextmanager
    def fake_parallel_config(**kwargs):
        events.append(("enter", kwargs))
        try:
            yield
        finally:
            events.append(("exit", kwargs))

    class FakeParallel:
        def __init__(self, n_jobs):
            events.append(("parallel_init", n_jobs))

        def __call__(self, tasks):
            events.append(("parallel_call", None))
            return [task() for task in tasks]

    def fake_delayed(func):
        def wrapper(*args, **kwargs):
            return lambda: func(*args, **kwargs)

        return wrapper

    evo = DiverseAlphaEvolution(
        DiverseEvolutionConfig(n_jobs=2, parallel_backend="threading")
    )
    evo._evaluate_genome = MethodType(
        lambda self, genome, train_df, val_df, target_col: SimpleNamespace(
            expression=str(genome),
            fitness=lambda: float(genome),
        ),
        evo,
    )

    monkeypatch.setattr("omega.quant.evolution.diverse_alpha_evolution.parallel_config", fake_parallel_config)
    monkeypatch.setattr("omega.quant.evolution.diverse_alpha_evolution.Parallel", FakeParallel)
    monkeypatch.setattr("omega.quant.evolution.diverse_alpha_evolution.delayed", fake_delayed)

    candidates = evo._evaluate_population([1, 3, 2], _frame(), _frame(), "target")

    assert [candidate.expression for candidate in candidates] == ["3", "2", "1"]
    assert events == [
        ("enter", {"backend": "threading"}),
        ("enter", {"n_jobs": 2}),
        ("parallel_init", 2),
        ("parallel_call", None),
        ("exit", {"n_jobs": 2}),
        ("exit", {"backend": "threading"}),
    ]


def test_evaluate_population_threading_backend_returns_candidates():
    evo = DiverseAlphaEvolution(DiverseEvolutionConfig(n_jobs=2, parallel_backend="threading"))
    frame = _market_frame()

    candidates = evo._evaluate_population(_population(), frame, frame.copy(), "target")

    assert candidates
    assert all(candidate.expression for candidate in candidates)
    assert all(candidate.genome is not None for candidate in candidates)


def test_evaluate_population_stays_serial_for_single_worker(monkeypatch):
    events = []

    def fail_parallel_config(**kwargs):
        events.append(("parallel_config", kwargs))
        raise AssertionError("parallel_config should not be used")

    class FailParallel:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Parallel should not be used")

    evo = DiverseAlphaEvolution(DiverseEvolutionConfig(n_jobs=1, parallel_backend="threading"))
    evo._evaluate_genome = MethodType(
        lambda self, genome, train_df, val_df, target_col: SimpleNamespace(
            expression=str(genome),
            fitness=lambda: float(genome),
        ),
        evo,
    )

    monkeypatch.setattr("omega.quant.evolution.diverse_alpha_evolution.parallel_config", fail_parallel_config)
    monkeypatch.setattr("omega.quant.evolution.diverse_alpha_evolution.Parallel", FailParallel)

    candidates = evo._evaluate_population([1, 3, 2], _frame(), _frame(), "target")

    assert [candidate.expression for candidate in candidates] == ["3", "2", "1"]
    assert events == []


def test_run_parallelizes_islands_with_min_worker_count(monkeypatch):
    events = []

    @contextmanager
    def fake_parallel_config(**kwargs):
        events.append(("parallel_config", kwargs))
        yield

    class FakeParallel:
        def __call__(self, tasks):
            events.append(("parallel_call", None))
            return [task() for task in tasks]

    def fake_delayed(func):
        def wrapper(*args, **kwargs):
            return lambda: func(*args, **kwargs)

        return wrapper

    frame = _market_frame()
    evo = DiverseAlphaEvolution(
        DiverseEvolutionConfig(
            n_islands=4,
            n_jobs=6,
            generations=1,
            population_per_island=1,
            migration_interval=10,
        )
    )
    monkeypatch.setattr(evo, "_create_island_population", lambda island_id: [island_id])
    monkeypatch.setattr(
        "omega.quant.evolution.diverse_alpha_evolution.parallel_config",
        fake_parallel_config,
    )
    monkeypatch.setattr("omega.quant.evolution.diverse_alpha_evolution.Parallel", FakeParallel)
    monkeypatch.setattr("omega.quant.evolution.diverse_alpha_evolution.delayed", fake_delayed)
    monkeypatch.setattr(
        "omega.quant.evolution.diverse_alpha_evolution._evolve_island_job",
        lambda island_idx, population, config, train_df, val_df, target_col: (
            population,
            [
                SimpleNamespace(
                    expression=f"alpha-{island_idx}",
                    train_ic=0.2,
                    test_ic=0.2,
                    hit_rate=1.0,
                    fitness=lambda: 1.0,
                    genome=Genome(tree=Node("close")),
                )
            ],
        ),
    )
    monkeypatch.setattr(evo, "_filter_diverse", lambda candidates, train_df: candidates)

    result = evo.run(frame, frame.copy(), "target")

    assert [candidate.expression for candidate in result] == ["alpha-0", "alpha-1", "alpha-2", "alpha-3"]
    assert events == [
        ("parallel_config", {"backend": "threading", "n_jobs": 4}),
        ("parallel_call", None),
    ]


def test_run_falls_back_to_sequential_when_single_worker(monkeypatch):
    frame = _market_frame()
    evo = DiverseAlphaEvolution(
        DiverseEvolutionConfig(
            n_islands=4,
            n_jobs=1,
            generations=1,
            population_per_island=1,
            migration_interval=10,
        )
    )
    calls = []

    monkeypatch.setattr(evo, "_create_island_population", lambda island_id: [island_id])
    monkeypatch.setattr(
        evo,
        "_evolve_island",
        MethodType(
            lambda self, population, train_df, val_df, target_col, config=None: (
                population,
                [
                    SimpleNamespace(
                        expression=f"alpha-{population[0]}",
                        train_ic=0.2,
                        test_ic=0.2,
                        hit_rate=1.0,
                        fitness=lambda: 1.0,
                        genome=Genome(tree=Node("close")),
                    )
                ],
            ),
            evo,
        ),
    )
    monkeypatch.setattr(
        "omega.quant.evolution.diverse_alpha_evolution.parallel_config",
        lambda **kwargs: pytest.fail("parallel_config should not be used"),
    )

    class FailParallel:
        def __init__(self, *args, **kwargs):
            pytest.fail("Parallel should not be used")

    monkeypatch.setattr("omega.quant.evolution.diverse_alpha_evolution.Parallel", FailParallel)
    monkeypatch.setattr(evo, "_filter_diverse", lambda candidates, train_df: candidates)

    result = evo.run(frame, frame.copy(), "target")

    assert [candidate.expression for candidate in result] == ["alpha-0", "alpha-1", "alpha-2", "alpha-3"]
    assert calls == []


def test_n_jobs_island_auto_computes_from_total_workers():
    config = DiverseEvolutionConfig(n_jobs=12, n_islands=4)

    assert config.n_jobs_island == 3


def test_run_partial_parallel_caps_island_workers(monkeypatch):
    events = []

    @contextmanager
    def fake_parallel_config(**kwargs):
        events.append(kwargs)
        yield

    class FakeParallel:
        def __call__(self, tasks):
            return [task() for task in tasks]

    def fake_delayed(func):
        def wrapper(*args, **kwargs):
            return lambda: func(*args, **kwargs)

        return wrapper

    frame = _market_frame()
    evo = DiverseAlphaEvolution(
        DiverseEvolutionConfig(
            n_islands=4,
            n_jobs=2,
            generations=1,
            population_per_island=1,
            migration_interval=10,
        )
    )
    monkeypatch.setattr(evo, "_create_island_population", lambda island_id: [island_id])
    monkeypatch.setattr(
        "omega.quant.evolution.diverse_alpha_evolution.parallel_config",
        fake_parallel_config,
    )
    monkeypatch.setattr("omega.quant.evolution.diverse_alpha_evolution.Parallel", FakeParallel)
    monkeypatch.setattr("omega.quant.evolution.diverse_alpha_evolution.delayed", fake_delayed)
    monkeypatch.setattr(
        "omega.quant.evolution.diverse_alpha_evolution._evolve_island_job",
        lambda island_idx, population, config, train_df, val_df, target_col: (
            population,
            [
                SimpleNamespace(
                    expression=f"alpha-{island_idx}",
                    train_ic=0.2,
                    test_ic=0.2,
                    hit_rate=1.0,
                    fitness=lambda: 1.0,
                    genome=Genome(tree=Node("close")),
                )
            ],
        ),
    )
    monkeypatch.setattr(evo, "_filter_diverse", lambda candidates, train_df: candidates)

    evo.run(frame, frame.copy(), "target")

    assert events == [{"backend": "threading", "n_jobs": 2}]


def test_tournament_migration_uses_random_pool(monkeypatch):
    evo = DiverseAlphaEvolution(DiverseEvolutionConfig())
    islands = [["left0", "left1"], ["right0", "right1"]]
    source_candidates = [
        SimpleNamespace(genome=f"g{i}", train_ic=float(i), test_ic=100.0 - i)
        for i in range(6)
    ]
    calls = []

    def fake_choice(population_size, size, replace):
        calls.append((population_size, size, replace))
        return np.array([1, 4, 2, 0, 3])

    monkeypatch.setattr("omega.quant.evolution.diverse_alpha_evolution.np.random.choice", fake_choice)

    evo._migrate(islands, [source_candidates, []])

    assert calls == [(6, 5, False)]
    assert islands[1][-1] == "g4"


def test_migration_count_1_replaces_only_one(monkeypatch):
    evo = DiverseAlphaEvolution(DiverseEvolutionConfig(migration_count=1))
    islands = [["left0", "left1", "left2"], ["right0", "right1", "right2"]]
    source_candidates = [
        SimpleNamespace(genome="winner", train_ic=1.0, test_ic=0.0),
        SimpleNamespace(genome="other", train_ic=0.5, test_ic=0.0),
    ]

    monkeypatch.setattr(
        "omega.quant.evolution.diverse_alpha_evolution.np.random.choice",
        lambda population_size, size, replace: np.array([0, 1]),
    )

    evo._migrate(islands, [source_candidates, []])

    assert islands[1] == ["right0", "right1", "winner"]


def test_mutation_boost_applied_to_lagging_island(monkeypatch):
    frame = _market_frame()
    config = DiverseEvolutionConfig(
        n_islands=2,
        n_jobs=1,
        generations=2,
        population_per_island=1,
        mutation_rate=0.35,
        island_mutation_boost=0.15,
        migration_interval=10,
    )
    evo = DiverseAlphaEvolution(config)
    seen_rates = {0: [], 1: []}

    monkeypatch.setattr(evo, "_create_island_population", lambda island_id: [island_id])

    def fake_evolve(self, population, train_df, val_df, target_col, island_config=None):
        island_id = population[0]
        seen_rates[island_id].append(island_config.mutation_rate)
        train_ic = 1.0 if island_id == 0 else 0.5
        return population, [
            SimpleNamespace(
                expression=f"alpha-{island_id}-{len(seen_rates[island_id])}",
                train_ic=train_ic,
                test_ic=0.2,
                hit_rate=1.0,
                fitness=lambda: train_ic,
                genome=Genome(tree=Node("close")),
            )
        ]

    monkeypatch.setattr(evo, "_evolve_island", MethodType(fake_evolve, evo))
    monkeypatch.setattr(evo, "_filter_diverse", lambda candidates, train_df: candidates)

    evo.run(frame, frame.copy(), "target")

    assert seen_rates[0] == [0.35, 0.35]
    assert seen_rates[1] == [0.35, 0.5]


def test_corr_threshold_0_7_accepts_moderate_correlation():
    class FakeGenome:
        def __init__(self, values):
            self.values = pd.Series(values, dtype=float)

        def evaluate_vectorized(self, train_df):
            return self.values

    evo = DiverseAlphaEvolution(DiverseEvolutionConfig(corr_threshold=0.7, max_active_alphas=5))
    candidates = [
        SimpleNamespace(expression="alpha-a", genome=FakeGenome([0, 1, 2, 3, 4])),
        SimpleNamespace(expression="alpha-b", genome=FakeGenome([0, 1, 4, 3, 2])),
    ]

    accepted = evo._filter_diverse(candidates, _frame())

    assert [candidate.expression for candidate in accepted] == ["alpha-a", "alpha-b"]
