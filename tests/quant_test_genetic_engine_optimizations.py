import numpy as np
import pytest
from scipy.stats import rankdata, spearmanr

from omega.quant.evolution.genetic_engine import (
    ALPHA_CACHE_KEY,
    FOLD_STRUCTURE_CACHE_KEY,
    HOF_ALPHA_CACHE_KEY,
    GeneticEngine,
    GPConfig,
    GPIndividual,
    GPNode,
    ORTHO_RANKS_CACHE_KEY,
    _build_time_fold_structure,
    _compute_time_fold_ir,
    _pearson_corr,
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


def test_fix_a_precomputed_ortho_ranks_match_spearman_baseline_penalty():
    alpha = np.linspace(-2.0, 3.0, 128) ** 3
    baseline = np.linspace(4.0, -1.0, 128)
    features, target = _make_features(alpha, alpha * 0.2 + 1.0)
    config = GPConfig(
        min_observations=10,
        use_fast_penalties=True,
        ortho_baseline_set={'base': baseline},
        ortho_correlation_threshold=0.1,
        ortho_penalty_weight=0.05,
    )
    engine = GeneticEngine(config)
    individual = GPIndividual(tree=GPNode(operator='terminal', value='f1'))
    features[ORTHO_RANKS_CACHE_KEY] = engine._ortho_ranks

    individual.evaluate(features, target, [], config)

    lower = np.nanpercentile(alpha, 1)
    upper = np.nanpercentile(alpha, 99)
    alpha_norm = np.clip(alpha, lower, upper)
    alpha_norm = (alpha_norm - np.nanmean(alpha_norm)) / (np.nanstd(alpha_norm) + 1e-9)
    alpha_norm = np.nan_to_num(alpha_norm, nan=0.0, posinf=0.0, neginf=0.0)
    fast_corr = abs(_pearson_corr(rankdata(alpha_norm), engine._ortho_ranks['base']))
    slow_spearman = abs(spearmanr(alpha_norm, baseline)[0])
    assert fast_corr == pytest.approx(slow_spearman, abs=1e-12)
    expected = 0.05 * ((slow_spearman - 0.1) / 0.9)
    assert individual.orthogonalization_penalty == pytest.approx(expected, abs=1e-10)


def test_fix_c_fold_structure_cache_matches_recomputed_ir():
    alpha = np.linspace(-1.0, 1.0, 64)
    target = alpha[::-1]
    features, target_arr = _make_features(alpha, target)
    config = GPConfig(use_time_fold_ir=True, time_folds=4, use_fast_penalties=True)

    cached_features = dict(features)
    cached_features[FOLD_STRUCTURE_CACHE_KEY] = _build_time_fold_structure(features['__date__'], 4)

    fast = _compute_time_fold_ir(alpha, target_arr, cached_features, config)
    slow = _compute_time_fold_ir(alpha, target_arr, features, config)

    assert fast == pytest.approx(slow, abs=1e-12)


def test_fix_b_hof_corr_cache_scoped_by_generation_membership():
    alpha = np.linspace(-1.0, 1.0, 128)
    target = alpha + 0.2
    features, target_arr = _make_features(alpha, target)
    config = GPConfig(min_observations=10, use_fast_penalties=True, diversity_threshold=0.1)
    candidate = GPIndividual(tree=GPNode(operator='terminal', value='f1'))
    hof_a = GPIndividual(tree=GPNode(operator='terminal', value='f1'))
    hof_b = GPIndividual(tree=GPNode(operator='terminal', value='1.0'))

    gen1 = dict(features)
    gen1[HOF_ALPHA_CACHE_KEY] = [alpha]
    gen1[ALPHA_CACHE_KEY] = {}
    candidate.evaluate(gen1, target_arr, [hof_a], config)
    gen1_cache = gen1[ALPHA_CACHE_KEY][id(candidate)].copy()

    gen2 = dict(features)
    gen2[HOF_ALPHA_CACHE_KEY] = [np.ones_like(alpha)]
    gen2[ALPHA_CACHE_KEY] = {}
    candidate.evaluate(gen2, target_arr, [hof_b], config)
    gen2_cache = gen2[ALPHA_CACHE_KEY][id(candidate)].copy()

    assert list(gen1_cache.keys()) == [id(hof_a)]
    assert list(gen2_cache.keys()) == [id(hof_b)]
    assert id(hof_a) not in gen2_cache


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
