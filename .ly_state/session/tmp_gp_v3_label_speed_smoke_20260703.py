import io
import logging
import pathlib
import sys

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.omega.quant.evolution.genetic_engine import (
    GPConfig,
    GPIndividual,
    GPNode,
    GeneticEngine,
    NEUTRALIZATION_CACHE_KEY,
    _build_neutralization_cache,
    _compute_time_fold_ir,
    _neutralize_cross_section,
    logger,
)


n_dates = 6
per_date = 8
dates = np.repeat(np.arange(n_dates), per_date)
mcap = np.tile(np.linspace(1.0, 2.4, per_date), n_dates)
sector = np.tile(np.array(["A", "A", "B", "B", "C", "C", "A", "B"], dtype=object), n_dates)
alpha = np.linspace(-1.0, 1.0, n_dates * per_date) + np.sin(np.arange(n_dates * per_date)) * 0.1
target = np.cos(np.arange(n_dates * per_date) / 5.0)

cache = _build_neutralization_cache(mcap, sector, dates)
uncached = _neutralize_cross_section(alpha, mcap, sector, dates)
cached = _neutralize_cross_section(alpha, mcap, sector, dates, neutralization_cache=cache)
assert np.allclose(uncached, cached, equal_nan=True)

features = {
    "x": np.linspace(-2.0, 2.0, n_dates * per_date),
    "__date__": dates,
    "__log_market_cap__": mcap,
    "__sector__": sector,
    NEUTRALIZATION_CACHE_KEY: cache,
}
cfg = GPConfig(
    population_size=6,
    generations=1,
    random_seed=7,
    use_time_fold_ir=True,
    neutralize_size_sector=True,
    time_folds=3,
    time_folds_fast_mode=True,
    n_jobs=1,
    min_observations=1,
)
fold_ir = _compute_time_fold_ir(alpha, target, features, cfg)
assert np.isfinite(fold_ir)

stream = io.StringIO()
handler = logging.StreamHandler(stream)
handler.setLevel(logging.INFO)
old_level = logger.level
logger.setLevel(logging.INFO)
logger.addHandler(handler)

engine = GeneticEngine(cfg)
engine.population = [GPIndividual(tree=GPNode(operator="feature", value="x")) for _ in range(cfg.population_size)]
engine.initialize_population = lambda: None
engine.evolve(
    {
        "x": features["x"],
        "__date__": dates,
        "__log_market_cap__": mcap,
        "__sector__": sector,
    },
    target,
)

logger.removeHandler(handler)
logger.setLevel(old_level)
logs = stream.getvalue()
assert "Fold_IR=" in logs
assert "IC=" not in logs

print(f"SMOKE_OK cache_dates={len(cache)} fold_ir={float(fold_ir):.6f}")
