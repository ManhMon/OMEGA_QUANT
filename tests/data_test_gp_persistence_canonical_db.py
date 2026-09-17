import json
from datetime import datetime, timezone

import pandas as pd

from omega.core.registry.persistence import DatabaseRegistry
from omega.quant.evolution.genetic_programming import GPNode
from scripts import genetic_alpha_evolution_v3 as gp_script
from scripts import precompute_all_features as precompute_script


def _sample_tree() -> GPNode:
    return GPNode(
        operator="+",
        children=[
            GPNode(operator="terminal", value="close"),
            GPNode(operator="terminal", value="volume"),
        ],
    )


def test_gp_registry_is_canonical_and_exports_views(tmp_path, monkeypatch):
    session_dir = tmp_path / "session"
    stable_dir = tmp_path / "stable"
    legacy_dir = tmp_path / "legacy"
    models_dir = tmp_path / "models"
    db_url = f"sqlite:///{(session_dir / 'conformal_registry.sqlite').as_posix()}"
    monkeypatch.setattr(gp_script, "SESSION_DIR", session_dir)
    monkeypatch.setattr(gp_script, "STABLE_RESULTS_DIR", stable_dir)
    monkeypatch.setattr(gp_script, "LEGACY_RESULTS_DIR", legacy_dir)
    monkeypatch.setattr(gp_script, "MODEL_RESULTS_DIR", models_dir)
    monkeypatch.setattr(gp_script, "REGISTRY_DB_URL", db_url)

    tree = _sample_tree()
    rows = gp_script.register_top_models(
        [
            {
                "rank": 1,
                "round": 2,
                "train_IC": 0.1234,
                "test_IC": 0.2345,
                "hit_rate": 0.61,
                "expression": tree.to_string(),
                "serialized_tree": repr(tree),
            }
        ],
        datetime(2026, 7, 2, tzinfo=timezone.utc),
    )

    registry = DatabaseRegistry(database_url=db_url)
    record = registry.get_model(name="genetic_alpha_v3_rank_01", version=rows[0]["version"])
    assert record is not None
    assert record.metrics["serialized_tree"] == repr(tree)

    csv_df = pd.read_csv(stable_dir / gp_script.RESULTS_CSV_NAME)
    assert csv_df.loc[0, "serialized_tree"] == repr(tree)

    jsonl_rows = (stable_dir / gp_script.RESULTS_JSONL_NAME).read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(jsonl_rows[0])["serialized_tree"] == repr(tree)

    legacy_csv_df = pd.read_csv(legacy_dir / gp_script.RESULTS_CSV_NAME)
    assert legacy_csv_df.loc[0, "serialized_tree"] == repr(tree)


def test_precompute_reads_db_and_skips_unsupported_truncated_payload(tmp_path, monkeypatch, caplog):
    db_url = f"sqlite:///{(tmp_path / 'conformal_registry.sqlite').as_posix()}"
    monkeypatch.setattr(precompute_script, "REGISTRY_DB_URL", db_url)
    registry = DatabaseRegistry(database_url=db_url)
    pit_embargo = datetime(2026, 7, 2, tzinfo=timezone.utc)
    tree = _sample_tree()

    registry.register_model(
        name="genetic_alpha_v3_rank_01",
        version="20260702T000000_r01",
        path=str(tmp_path / "valid.json"),
        status="ready",
        metrics={
            "rank": 1,
            "round": 1,
            "train_IC": 0.11,
            "test_IC": 0.22,
            "hit_rate": 0.55,
            "expression": tree.to_string(),
            "serialized_tree": repr(tree),
        },
        pit_embargo=pit_embargo,
    )
    registry.register_model(
        name="genetic_alpha_v3_rank_02",
        version="20260702T000001_r02",
        path=str(tmp_path / "invalid.json"),
        status="ready",
        metrics={
            "rank": 2,
            "round": 1,
            "train_IC": 0.1,
            "test_IC": 0.2,
            "hit_rate": 0.5,
            "expression": "(close + volume",
            "serialized_tree": "(close + volume",
        },
        pit_embargo=pit_embargo,
    )

    feat_df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=3).tolist() * 2,
            "symbol": ["AAA"] * 3 + ["BBB"] * 3,
            "open": [10, 11, 12, 20, 21, 22],
            "high": [11, 12, 13, 21, 22, 23],
            "low": [9, 10, 11, 19, 20, 21],
            "close": [10, 11, 12, 20, 21, 22],
            "volume": [100, 110, 120, 200, 210, 220],
            "returns": [0.0, 0.1, 0.09, 0.0, 0.05, 0.0476],
        }
    )

    out_df = precompute_script.compile_and_execute_gp_alphas(feat_df.copy())

    assert out_df["alpha_gp_00"].notna().any()
    assert out_df["alpha_gp_01"].isna().all()
    assert "Unsupported GP payload; canonical serialized_tree required" in caplog.text
    assert "Falling back to terminal GP expression" not in caplog.text


def test_precompute_loads_latest_ready_row_per_rank(tmp_path, monkeypatch):
    db_url = f"sqlite:///{(tmp_path / 'conformal_registry.sqlite').as_posix()}"
    monkeypatch.setattr(precompute_script, "REGISTRY_DB_URL", db_url)
    registry = DatabaseRegistry(database_url=db_url)
    pit_embargo = datetime(2026, 7, 2, tzinfo=timezone.utc)
    tree = _sample_tree()

    registry.register_model(
        name="genetic_alpha_v3_rank_01",
        version="20260702T000000_r01",
        path=str(tmp_path / "rank01_old.json"),
        status="ready",
        metrics={
            "rank": 1,
            "round": 1,
            "train_IC": 0.10,
            "test_IC": 0.20,
            "hit_rate": 0.50,
            "expression": "old_rank_1",
            "serialized_tree": repr(tree),
        },
        pit_embargo=pit_embargo,
    )
    registry.register_model(
        name="genetic_alpha_v3_rank_01",
        version="20260702T000100_r01",
        path=str(tmp_path / "rank01_new.json"),
        status="ready",
        metrics={
            "rank": 1,
            "round": 2,
            "train_IC": 0.11,
            "test_IC": 0.21,
            "hit_rate": 0.51,
            "expression": "new_rank_1",
            "serialized_tree": repr(tree),
        },
        pit_embargo=pit_embargo,
    )
    registry.register_model(
        name="genetic_alpha_v3_rank_02",
        version="20260702T000200_r02",
        path=str(tmp_path / "rank02.json"),
        status="ready",
        metrics={
            "rank": 2,
            "round": 2,
            "train_IC": 0.12,
            "test_IC": 0.22,
            "hit_rate": 0.52,
            "expression": "rank_2",
            "serialized_tree": repr(tree),
        },
        pit_embargo=pit_embargo,
    )
    registry.register_model(
        name="genetic_alpha_v3_rank_03",
        version="20260702T000300_r03",
        path=str(tmp_path / "rank03.json"),
        status="ready",
        metrics={
            "rank": 3,
            "round": 2,
            "train_IC": 0.13,
            "test_IC": 0.23,
            "hit_rate": 0.53,
            "expression": "rank_3",
            "serialized_tree": repr(tree),
        },
        pit_embargo=pit_embargo,
    )

    gp_df = precompute_script._load_gp_registry_rows()

    assert gp_df["rank"].tolist() == [1, 2, 3]
    assert gp_df["version"].tolist() == [
        "20260702T000100_r01",
        "20260702T000200_r02",
        "20260702T000300_r03",
    ]
    assert gp_df["expression"].tolist() == ["new_rank_1", "rank_2", "rank_3"]
