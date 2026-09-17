import numpy as np
import pytest
from scipy.stats import rankdata, spearmanr
import importlib.util
import sys
from pathlib import Path

from omega.quant.evolution.genetic_engine import (
    ALPHA_CACHE_KEY,
    FOLD_STRUCTURE_CACHE_KEY,
    HOF_ALPHA_CACHE_KEY,
    GeneticEngine,
    GPConfig,
    GPIndividual,
    GPNode,
    ORTHO_RANKS_CACHE_KEY,
    _batch_neutralize_cross_section,
    _build_neutralization_cache,
    _build_time_fold_structure,
    _compute_time_fold_ir,
    _neutralize_cross_section,
    _pearson_corr,
)

import omega.quant.evolution.genetic_engine as ge


@pytest.fixture(scope="module", autouse=True)
def restore_originals():
    """Module-scoped fixture to isolate monkeypatches from other test modules."""
    import omega.quant.evolution.genetic_engine as ge
    
    # Save current state
    saved_state = {
        'GeneticEngine': ge.GeneticEngine,
        'GPConfig': ge.GPConfig,
        'GPIndividual': ge.GPIndividual,
        '_neutralize_cross_section': ge._neutralize_cross_section,
        '_batch_neutralize_cross_section': ge._batch_neutralize_cross_section,
        '_compute_time_fold_ir': ge._compute_time_fold_ir,
    }
    
    # Restore to originals if monkeypatched
    if ge.GeneticEngine.__name__ == "GeneticEngineV4":
        import genetic_alpha_evolution_v4 as v4
        ge.GeneticEngine = v4.ORIGINAL_GENETIC_ENGINE
        ge.GPConfig = v4.ORIGINAL_GPCONFIG
        ge.GPIndividual = v4.ORIGINAL_GPINDIVIDUAL
        ge._neutralize_cross_section = v4.ORIGINAL_NEUTRALIZE_CROSS_SECTION
        ge._batch_neutralize_cross_section = v4.ORIGINAL_BATCH_NEUTRALIZE_CROSS_SECTION
        ge._compute_time_fold_ir = v4.ORIGINAL_COMPUTE_TIME_FOLD_IR
        
        # Re-bind local names in test module's namespace
        import sys
        current_module = sys.modules[__name__]
        current_module.GeneticEngine = ge.GeneticEngine
        current_module.GPConfig = ge.GPConfig
        current_module.GPIndividual = ge.GPIndividual
        current_module._neutralize_cross_section = ge._neutralize_cross_section
        current_module._batch_neutralize_cross_section = ge._batch_neutralize_cross_section
        current_module._compute_time_fold_ir = ge._compute_time_fold_ir
    
    yield
    
    # Restore saved state
    ge.GeneticEngine = saved_state['GeneticEngine']
    ge.GPConfig = saved_state['GPConfig']
    ge.GPIndividual = saved_state['GPIndividual']
    ge._neutralize_cross_section = saved_state['_neutralize_cross_section']
    ge._batch_neutralize_cross_section = saved_state['_batch_neutralize_cross_section']
    ge._compute_time_fold_ir = saved_state['_compute_time_fold_ir']


def _load_v4_module():
    module = sys.modules.get("genetic_alpha_evolution_v4")
    if module is not None:
        return module
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "genetic_alpha_evolution_v4.py"
    scripts_dir = str(module_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("genetic_alpha_evolution_v4", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load genetic_alpha_evolution_v4 from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    fast.evaluate(features, target_arr, [], GPConfig(min_observations=4, use_fast_penalties=True))
    slow.evaluate(features, target_arr, [], GPConfig(min_observations=4, use_fast_penalties=False))

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


def test_time_fold_ir_uses_daily_cs_ic_and_cap():
    dates = np.repeat(np.arange(16), 6)
    alpha = np.tile(np.arange(6, dtype=float), 16)
    target = alpha.copy()
    features = {
        'f1': alpha,
        '__date__': dates,
        '__log_market_cap__': np.tile(np.linspace(1.0, 2.0, 6), 16),
        '__sector__': np.tile(np.arange(6) % 3, 16),
    }
    config = GPConfig(use_time_fold_ir=True, time_folds=8, fold_ir_std_floor=0.03)
    assert _compute_time_fold_ir(alpha, target, features, config) == pytest.approx(2.0)


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


def test_gate3_batch_neutralization_matches_per_alpha_path():
    n_dates = 6
    per_date = 5
    n = n_dates * per_date
    dates = np.repeat(np.arange(n_dates), per_date)
    log_mcap = np.tile(np.linspace(1.0, 2.0, per_date), n_dates)
    sector = np.tile(np.array([0, 1, 2, 0, 1]), n_dates)
    alpha_matrix = np.column_stack([
        np.linspace(-1.0, 1.0, n),
        np.sin(np.linspace(0.0, 2.0, n)),
        np.cos(np.linspace(0.0, 3.0, n)),
    ])
    cache = _build_neutralization_cache(log_mcap, sector, dates)

    batch = _batch_neutralize_cross_section(alpha_matrix, dates, cache)
    sequential = np.column_stack([
        _neutralize_cross_section(alpha_matrix[:, i], log_mcap, sector, dates, cache)
        for i in range(alpha_matrix.shape[1])
    ])

    assert np.allclose(batch, sequential, atol=1e-10, rtol=1e-10)


def test_gate3_batch_neutralization_flag_preserves_legacy_scores():
    n_dates = 24
    per_date = 6
    n = n_dates * per_date
    x = np.linspace(-2.0, 2.0, n)
    dates = np.repeat(np.arange(n_dates), per_date)
    features = {
        'f1': x,
        'f2': x[::-1],
        '__date__': dates,
        '__log_market_cap__': np.tile(np.linspace(1.0, 3.0, per_date), n_dates),
        '__sector__': np.tile(np.array([0, 1, 2, 0, 1, 2]), n_dates),
    }
    target = 0.4 * x - 0.2 * x[::-1]
    base_config = GPConfig(
        population_size=6,
        generations=1,
        min_observations=10,
        n_jobs=1,
        random_seed=11,
        neutralize_size_sector=True,
        use_fast_penalties=True,
        hall_of_fame_size=3,
    )

    batch_engine = GeneticEngine(base_config)
    legacy_engine = GeneticEngine(GPConfig(**{**base_config.__dict__, 'use_batch_neutralization': False}))

    batch_hof = batch_engine.evolve(features, target)
    legacy_hof = legacy_engine.evolve(features, target)

    assert len(batch_engine.history) == len(legacy_engine.history)
    for batch_row, legacy_row in zip(batch_engine.history, legacy_engine.history):
        compare_keys = {'generation', 'best_fitness', 'best_ic', 'best_tree_size'}
        assert compare_keys.issubset(batch_row.keys())
        assert compare_keys.issubset(legacy_row.keys())
        for key in compare_keys:
            assert batch_row[key] == pytest.approx(legacy_row[key], abs=1e-10)
    assert [ind.tree.to_string() for ind in batch_hof] == [ind.tree.to_string() for ind in legacy_hof]
    assert [ind.fitness for ind in batch_hof] == pytest.approx([ind.fitness for ind in legacy_hof], abs=1e-10)


def test_gp_numba_ic_date_index_builder_groups_rows_in_stable_order():
    v4 = _load_v4_module()

    date_ids = np.array([2, 0, 2, 1, 0, 1, 2], dtype=np.int64)

    flat_indices, offsets = v4._build_date_group_index_from_ids(date_ids)

    assert flat_indices.tolist() == [1, 4, 3, 5, 0, 2, 6]
    assert offsets.tolist() == [0, 2, 4, 7]


def test_gp_numba_daily_ics_pregroup_matches_legacy_scan():
    v4 = _load_v4_module()

    def legacy_daily_ics(alpha, target, date_ids, eval_mask):
        n_dates = int(date_ids.max()) + 1
        out = np.full(n_dates, np.nan, dtype=np.float64)
        counts = np.zeros(n_dates, dtype=np.int64)
        for i in range(date_ids.size):
            if eval_mask[i]:
                counts[date_ids[i]] += 1
        for date_id in range(n_dates):
            if counts[date_id] <= 5:
                continue
            alpha_day = np.empty(counts[date_id], dtype=np.float64)
            target_day = np.empty(counts[date_id], dtype=np.float64)
            pos = 0
            for i in range(date_ids.size):
                if eval_mask[i] and date_ids[i] == date_id:
                    alpha_day[pos] = alpha[i]
                    target_day[pos] = target[i]
                    pos += 1
            out[date_id] = v4._numba_pearson_corr(
                v4._numba_rank_average_ties(alpha_day),
                v4._numba_rank_average_ties(target_day),
            )
        return out

    rows_per_date = 7
    date_ids = np.repeat(np.array([2, 0, 3, 1], dtype=np.int64), rows_per_date)
    alpha = np.linspace(-3.0, 4.0, date_ids.size)
    target = alpha[::-1] + 0.25
    eval_mask = np.ones(date_ids.size, dtype=np.bool_)
    eval_mask[[1, 9, 20]] = False
    flat_indices, offsets = v4._build_date_group_index_from_ids(date_ids)

    actual = v4._numba_daily_ics(alpha, target, flat_indices, offsets, eval_mask)
    expected = legacy_daily_ics(alpha, target, date_ids, eval_mask)

    assert actual == pytest.approx(expected, nan_ok=True, abs=1e-12)


def test_gp_numba_batch_daily_ics_pregroup_matches_daily_path():
    v4 = _load_v4_module()

    date_ids = np.repeat(np.array([1, 0, 2], dtype=np.int64), 8)
    alpha_matrix = np.column_stack([
        np.linspace(-1.0, 1.0, date_ids.size),
        np.sin(np.linspace(0.0, 3.0, date_ids.size)),
    ])
    target = np.cos(np.linspace(0.0, 2.0, date_ids.size))
    eval_mask_matrix = np.ones_like(alpha_matrix, dtype=np.bool_)
    eval_mask_matrix[0, 0] = False
    eval_mask_matrix[5, 1] = False
    flat_indices, offsets = v4._build_date_group_index_from_ids(date_ids)

    batch = v4._numba_batch_daily_ics(alpha_matrix, target, flat_indices, offsets, eval_mask_matrix)
    sequential = np.column_stack([
        v4._numba_daily_ics(alpha_matrix[:, idx], target, flat_indices, offsets, eval_mask_matrix[:, idx])
        for idx in range(alpha_matrix.shape[1])
    ])

    assert np.allclose(batch, sequential, equal_nan=True, atol=1e-12, rtol=1e-12)


def test_gp_numba_parallel_batch_daily_ics_matches_daily_path_with_sparse_masks():
    v4 = _load_v4_module()

    date_ids = np.repeat(np.array([3, 1, 0, 2], dtype=np.int64), 7)
    alpha_matrix = np.column_stack([
        np.linspace(-2.0, 2.0, date_ids.size),
        np.cos(np.linspace(0.0, 4.0, date_ids.size)),
        np.sin(np.linspace(0.0, 5.0, date_ids.size)),
    ])
    target = 0.3 * alpha_matrix[:, 0] - 0.2 * alpha_matrix[:, 1] + 0.1
    eval_mask_matrix = np.ones_like(alpha_matrix, dtype=np.bool_)
    eval_mask_matrix[[0, 8, 16], 0] = False
    eval_mask_matrix[[2, 9, 18], 1] = False
    eval_mask_matrix[[4, 11, 20], 2] = False
    flat_indices, offsets = v4._build_date_group_index_from_ids(date_ids)

    batch = v4._numba_batch_daily_ics(alpha_matrix, target, flat_indices, offsets, eval_mask_matrix)
    sequential = np.column_stack([
        v4._numba_daily_ics(alpha_matrix[:, idx], target, flat_indices, offsets, eval_mask_matrix[:, idx])
        for idx in range(alpha_matrix.shape[1])
    ])

    assert np.allclose(batch, sequential, equal_nan=True, atol=1e-12, rtol=1e-12)


def test_gp_numba_parallel_batch_ridge_neutralize_matches_single_path_with_nans():
    v4 = _load_v4_module()

    n_dates = 5
    per_date = 6
    n = n_dates * per_date
    dates = np.repeat(np.arange(n_dates), per_date)
    log_mcap = np.tile(np.linspace(1.0, 2.5, per_date), n_dates)
    sector = np.tile(np.array([0, 1, 2, 0, 1, 2]), n_dates)
    features = {
        'f1': np.linspace(-1.0, 1.0, n),
        '__date__': dates,
        '__log_market_cap__': log_mcap,
        '__sector__': sector,
        ge.NEUTRALIZATION_CACHE_KEY: _build_neutralization_cache(log_mcap, sector, dates),
    }
    v4._ensure_neutralization_jit_context(features)
    cache = features[ge.NEUTRALIZATION_CACHE_KEY]
    payload = v4._get_jit_neutralization_payload(cache)
    assert payload is not None
    design_matrix, valid_mask, date_flat_indices, date_group_offsets, max_group_size = payload

    alpha_matrix = np.column_stack([
        np.linspace(-1.0, 1.0, n),
        np.sin(np.linspace(0.0, 3.0, n)),
        np.cos(np.linspace(0.0, 4.0, n)),
    ])
    alpha_matrix[1, 0] = np.nan
    alpha_matrix[8, 1] = np.nan
    alpha_matrix[17, 2] = np.nan

    batch = v4._numba_batch_ridge_neutralize(
        alpha_matrix,
        design_matrix,
        valid_mask,
        date_flat_indices,
        date_group_offsets,
        max_group_size,
        v4.RIDGE_ALPHA,
    )
    sequential = np.column_stack([
        v4._numba_ridge_neutralize(
            alpha_matrix[:, idx],
            design_matrix,
            valid_mask,
            date_flat_indices,
            date_group_offsets,
            max_group_size,
            v4.RIDGE_ALPHA,
        )
        for idx in range(alpha_matrix.shape[1])
    ])

    assert np.allclose(batch, sequential, equal_nan=True, atol=1e-10, rtol=1e-10)


def test_gp_numba_parallel_eval_thread_safety():
    """Test that parallel tree evaluation produces same results as sequential.
    
    Verifies thread-local stack allocation prevents race conditions and state corruption
    when multiple threads evaluate trees concurrently.
    """
    v4 = _load_v4_module()
    
    # Create test dataset with sufficient complexity
    n_rows = 240
    n_dates = 12
    per_date = n_rows // n_dates
    dates = np.repeat(np.arange(n_dates), per_date)
    
    features = {
        'f1': np.linspace(-2.0, 3.0, n_rows),
        'f2': np.sin(np.linspace(0.0, 4.0, n_rows)),
        'f3': np.cos(np.linspace(0.0, 3.0, n_rows)),
        '__date__': dates,
        '__ticker__': np.tile(np.arange(per_date), n_dates),
        '__log_market_cap__': np.tile(np.linspace(1.0, 2.5, per_date), n_dates),
        '__sector__': np.tile(np.array([0, 1, 2, 0, 1] * (per_date // 5 + 1))[:per_date], n_dates),
    }
    target = 0.7 * features['f1'] - 0.3 * features['f2'] + 0.1 * features['f3']
    
    # Build VM context to trigger thread-local stack allocation
    v4._get_vm_context(features)
    
    # Create multiple individuals with different tree structures
    trees = [
        GPNode(operator='terminal', value='f1'),
        GPNode(operator='terminal', value='f2'),
        GPNode(operator='+', children=[
            GPNode(operator='terminal', value='f1'),
            GPNode(operator='terminal', value='f2'),
        ]),
        GPNode(operator='*', children=[
            GPNode(operator='terminal', value='f1'),
            GPNode(operator='terminal', value='2.0'),
        ]),
        GPNode(operator='cs_rank', children=[
            GPNode(operator='terminal', value='f3'),
        ]),
    ]
    
    individuals = [v4.GPIndividualV4(tree=tree) for tree in trees]
    
    # Sequential evaluation
    sequential_results = []
    for ind in individuals:
        result = ind._execute_tree(ind.tree, features)
        sequential_results.append(result.copy())
    
    # Parallel evaluation using threads
    import concurrent.futures
    
    def eval_individual(ind):
        return ind._execute_tree(ind.tree, features).copy()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        parallel_results = list(executor.map(eval_individual, individuals))
    
    # Verify results match
    assert len(parallel_results) == len(sequential_results)
    for idx, (parallel, sequential) in enumerate(zip(parallel_results, sequential_results)):
        assert parallel.shape == sequential.shape, f"Individual {idx}: shape mismatch"
        assert np.allclose(parallel, sequential, equal_nan=True, atol=1e-12, rtol=1e-12), \
            f"Individual {idx}: results differ between parallel and sequential execution"
    
    # Run multiple parallel iterations to stress-test thread safety
    for iteration in range(3):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            iteration_results = list(executor.map(eval_individual, individuals))
        
        for idx, (iteration_result, expected) in enumerate(zip(iteration_results, sequential_results)):
            assert np.allclose(iteration_result, expected, equal_nan=True, atol=1e-12, rtol=1e-12), \
                f"Iteration {iteration}, Individual {idx}: state corruption detected"
