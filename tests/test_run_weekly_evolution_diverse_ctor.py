import sys
import types
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

import scripts.run_weekly_evolution as rwe
from omega.core.registry.persistence import DatabaseRegistry


def _build_frame(rows: int = 40) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "open": np.linspace(1.0, 2.0, rows),
            "high": np.linspace(1.0, 2.0, rows),
            "low": np.linspace(1.0, 2.0, rows),
            "close": np.linspace(1.0, 2.0, rows),
            "volume": np.linspace(100.0, 200.0, rows),
            "returns": np.linspace(0.0, 0.1, rows),
            "target": np.linspace(0.0, 0.1, rows),
        }
    )
    frame["date"] = pd.date_range("2024-01-01", periods=rows, freq="D")
    frame["ticker"] = "AAA"
    return frame


def test_run_evolution_diverse_uses_supported_config_kwargs(monkeypatch):
    train_df = _build_frame()
    val_df = _build_frame()
    captured = {}

    class FakeConfig:
        n_islands = 4

        def __init__(self, **kwargs):
            captured["config_kwargs"] = kwargs
            self.n_islands = 4

    class FakeEvolution:
        def __init__(self, config):
            captured["config"] = config

        def run(self, train_df, val_df, target_col):
            captured["run"] = {
                "train_rows": len(train_df),
                "val_rows": len(val_df),
                "target_col": target_col,
            }
            return []

    class FakeIndividual:
        def __init__(self, tree):
            self.tree = tree

    monkeypatch.setitem(
        sys.modules,
        "omega.quant.evolution.diverse_alpha_evolution",
        types.SimpleNamespace(
            DiverseAlphaEvolution=FakeEvolution,
            DiverseEvolutionConfig=FakeConfig,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "omega.quant.evolution.genetic_engine",
        types.SimpleNamespace(GPIndividual=FakeIndividual),
    )

    result = rwe.run_evolution(
        train_df,
        val_df,
        engine_type="diverse",
        generations=7,
        population_size=10,
        backend="threads",
        workers=3,
        ortho_correlation_threshold=0.25,
    )

    assert result == []
    assert captured["config_kwargs"] == {
        "population_per_island": 3,
        "generations": 7,
        "corr_threshold": 0.25,
        "n_jobs": 3,
        "parallel_backend": "threading",
    }
    assert captured["run"] == {
        "train_rows": 40,
        "val_rows": 40,
        "target_col": "target",
    }


def test_build_ortho_baseline_set_loads_hybrid_db_records(tmp_path, monkeypatch):
    db_path = tmp_path / "conformal_registry.sqlite"
    registry = DatabaseRegistry(database_url=f"sqlite:///{db_path.as_posix()}")
    registry.register_model(
        name="hybrid_alpha_llm_alpha_001",
        version="20260723T010101_01_abc",
        path=str(tmp_path / "alpha_001.json"),
        status="ready",
        metrics={"alpha_id": "alpha_001", "formula": "close"},
        pit_embargo=datetime(2026, 6, 30, tzinfo=timezone.utc),
    )
    registry.register_model(
        name="hybrid_alpha_llm_alpha_002",
        version="20260723T010102_01_def",
        path=str(tmp_path / "alpha_002.json"),
        status="ready",
        metrics={"alpha_id": "alpha_002"},
        pit_embargo=datetime(2026, 6, 30, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(rwe, "CONFORMAL_REGISTRY_PATH", db_path)

    frame = _build_frame()
    baseline_set = rwe._build_ortho_baseline_set(frame, baseline_source="hybrid_db")

    assert list(baseline_set) == ["alpha_001"]
    assert np.allclose(baseline_set["alpha_001"], frame["close"].to_numpy(dtype=np.float64))


def test_main_raises_when_hybrid_db_loads_no_baselines(monkeypatch):
    frame = _build_frame()
    args = types.SimpleNamespace(
        regime="all",
        generations=1,
        population_size=4,
        orthogonalize="hybrid_db",
        no_alt_features=False,
        workers=1,
        backend="threads",
        min_oos_ic=0.01,
        min_oos_score=0.08,
        start_date=None,
        end_date=None,
        ortho_baseline_path=None,
        ortho_penalty_weight=0.05,
        ortho_correlation_threshold=0.5,
        random_seed=42,
        use_time_fold_ir=True,
        time_folds=3,
        fold_ir_std_floor=0.03,
        engine="standard",
    )

    monkeypatch.setattr(rwe, "_install_v4_optimizations", lambda: None)
    monkeypatch.setattr(rwe, "parse_args", lambda argv=None: args)
    monkeypatch.setattr(rwe, "load_market_data", lambda **_kwargs: frame)
    monkeypatch.setattr(rwe, "prepare_features", lambda df: df)
    monkeypatch.setattr(rwe, "walk_forward_split", lambda *_args, **_kwargs: (frame, frame, frame))
    monkeypatch.setattr(rwe, "_build_ortho_baseline_set", lambda **_kwargs: {})

    with pytest.raises(ValueError, match="no baseline signals were loaded"):
        rwe.main([])


def test_parse_args_accepts_hybrid_db_source():
    args = rwe.parse_args(["--orthogonalize", "hybrid_db"])
    assert args.orthogonalize == "hybrid_db"
