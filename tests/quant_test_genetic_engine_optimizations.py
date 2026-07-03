import numpy as np
import pytest

from omega.quant.evolution.genetic_engine import (
    HOF_ALPHA_CACHE_KEY,
    GeneticEngine,
    GPConfig,
    GPIndividual,
    GPNode,
)


def _make_features(alpha, target=None):
    features = {
        'f1': np.asarray(alpha, dtype=np.float64),
        '__date__': np.repeat(np.arange(max(len(alpha) // 4, 1)), 4)[:len(alpha)],
        '__log_market_cap__': np.linspace(1.0, 2.0, len(alpha)),
        '__sector__': np.arange(len(alpha)) % 3,
    }
    if target is not None:
        return features, np.asarray(target, dtype=np.float64)
    return features


def test_extra2_fast_threshold_matches_dropna_with_inf_target():
    alpha = np.linspace(-2.0, 2.0, 8)
    target = np.array([1.0, np.nan, np.inf, -np.inf, 0.0, 2.0, np.nan, 3.0])
    features, target_arr = _make_features(alpha, target)
    tree = GPNode(operator='terminal', value='f1')

    fast = GPIndividual(tree=tree)
    slow = GPIndividual(tree=tree)
    fast.evaluate(features, target_arr, [], GPConfig(min_observations=6, use_fast_penalties=True))
    slow.evaluate(features, target_arr, [], GPConfig(min_observations=6, use_fast_penalties=False))

    assert np.isfinite(fast.fitness)
    assert np.isfinite(slow.fitness)
    assert fast.ic_score == pytest.approx(slow.ic_score, abs=1e-12)
    assert fast.fitness == pytest.approx(slow.fitness, abs=1e-12)


def test_hof_cache_injected_prevents_reexecution():
    alpha = np.linspace(-1.0, 1.0, 128)
    target = alpha + 0.1
    features, target_arr = _make_features(alpha, target)
    config = GPConfig(min_observations=10, use_fast_penalties=True)

    hof_member = GPIndividual(tree=GPNode(operator='terminal', value='f1'))
    candidate = GPIndividual(tree=GPNode(operator='terminal', value='f1'))
    cached_features = dict(features)
    cached_features[HOF_ALPHA_CACHE_KEY] = [np.asarray(alpha, dtype=np.float64)]

    original = GPIndividual._execute_tree

    def guarded_execute(self, node, feats):
        if self is hof_member:
            raise AssertionError('hof tree re-executed')
        return original(self, node, feats)

    GPIndividual._execute_tree = guarded_execute
    try:
        candidate.evaluate(cached_features, target_arr, [hof_member], config)
    finally:
        GPIndividual._execute_tree = original

    assert candidate.diversity_penalty >= 0.0


def test_hof_cache_rebuild_tracks_membership_change():
    engine = GeneticEngine(GPConfig())
    features = _make_features(np.arange(16, dtype=np.float64))
    hof_a = GPIndividual(tree=GPNode(operator='terminal', value='f1'))
    hof_b = GPIndividual(tree=GPNode(operator='terminal', value='1.0'))

    cache_a = engine._build_hof_alpha_cache([hof_a], features)
    cache_b = engine._build_hof_alpha_cache([hof_a, hof_b], features)

    assert len(cache_a) == 1
    assert len(cache_b) == 2
    assert np.allclose(cache_b[0], cache_a[0])
    assert np.allclose(cache_b[1], np.ones(16))


def test_evolve_with_fast_penalties_keeps_deterministic_history_and_hof():
    n = 240
    x = np.linspace(-1.0, 1.0, n)
    features, target = _make_features(x, 0.7 * x + 0.05)
    features['f2'] = x[::-1]
    config = GPConfig(
        population_size=10,
        generations=2,
        min_observations=20,
        n_jobs=1,
        random_seed=7,
        hall_of_fame_size=4,
        use_fast_penalties=True,
    )

    engine_a = GeneticEngine(config)
    engine_b = GeneticEngine(config)
    hof_a = engine_a.evolve(features, target)
    hof_b = engine_b.evolve(features, target)

    history_a = [
        {k: v for k, v in row.items() if k not in {'elapsed_sec', 'gen_time_sec', 'eta_sec'}}
        for row in engine_a.history
    ]
    history_b = [
        {k: v for k, v in row.items() if k not in {'elapsed_sec', 'gen_time_sec', 'eta_sec'}}
        for row in engine_b.history
    ]
    assert history_a == history_b
    assert [ind.tree.to_string() for ind in hof_a] == [ind.tree.to_string() for ind in hof_b]
