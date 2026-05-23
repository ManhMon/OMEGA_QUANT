from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError, StatementError

from omega.core.db import AuditLogRecord, DatasetRecord, ModelRecord, compute_chain_hash, init_registry_db, make_registry_session_factory
from omega.core.registry import DatabaseRegistry


@pytest.fixture
def session_factory(tmp_path):
    db_path = tmp_path / "phase10.db"
    engine = init_registry_db(f"sqlite:///{db_path.as_posix()}")
    return make_registry_session_factory(engine)


@pytest.fixture
def registry(session_factory):
    return DatabaseRegistry(session_factory=session_factory)


def test_schema_contains_phase10_tables(session_factory):
    with session_factory() as session:
        inspector = inspect(session.bind)
        assert set(inspector.get_table_names()) == {"audit_logs", "datasets", "models"}


def test_register_dataset_persists_required_fields(registry, session_factory):
    as_of_time = datetime(2026, 5, 18, 9, 30, tzinfo=timezone.utc)

    record = registry.register_dataset(
        version="dataset-2026.05.18",
        path="/data/prices_20260518.parquet",
        checksum="a" * 64,
        provenance={"source": "exchange", "vendor": "internal"},
        as_of_time=as_of_time,
    )

    assert record.id is not None
    with session_factory() as session:
        saved = session.scalar(select(DatasetRecord).where(DatasetRecord.id == record.id))
        assert saved.version == "dataset-2026.05.18"
        assert saved.path == "/data/prices_20260518.parquet"
        assert saved.checksum == "a" * 64
        assert saved.provenance["source"] == "exchange"
        assert saved.as_of_time == as_of_time


def test_register_dataset_rejects_duplicate_version(registry):
    as_of_time = datetime(2026, 5, 18, tzinfo=timezone.utc)
    payload = dict(
        version="dataset-dup",
        path="/data/dataset.parquet",
        checksum="b" * 64,
        provenance={"source": "vendor"},
        as_of_time=as_of_time,
    )

    registry.register_dataset(**payload)
    with pytest.raises(IntegrityError):
        registry.register_dataset(**payload)


def test_register_model_persists_metrics_and_embargo(registry, session_factory):
    embargo = datetime(2026, 5, 20, 16, 0, tzinfo=timezone.utc)

    record = registry.register_model(
        name="alpha_xgb",
        version="v1.0.0",
        path="/models/alpha_xgb_v1.joblib",
        status="validated",
        metrics={"sharpe": 1.8, "rank_ic": 0.07},
        pit_embargo=embargo,
    )

    with session_factory() as session:
        saved = session.scalar(select(ModelRecord).where(ModelRecord.id == record.id))
        assert saved.name == "alpha_xgb"
        assert saved.version == "v1.0.0"
        assert saved.status == "validated"
        assert saved.metrics["sharpe"] == 1.8
        assert saved.pit_embargo == embargo


def test_register_model_rejects_duplicate_name_version(registry):
    embargo = datetime(2026, 5, 20, tzinfo=timezone.utc)
    payload = dict(
        name="alpha_xgb",
        version="v1.0.0",
        path="/models/alpha_xgb_v1.joblib",
        status="validated",
        metrics={"sharpe": 1.8},
        pit_embargo=embargo,
    )

    registry.register_model(**payload)
    with pytest.raises(IntegrityError):
        registry.register_model(**payload)


def test_write_audit_log_chains_sha256_hashes(registry, session_factory):
    t1 = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
    t2 = t1 + timedelta(minutes=5)

    first = registry.write_audit_log(timestamp=t1, actor="role9", action="register_dataset")
    second = registry.write_audit_log(timestamp=t2, actor="role9", action="register_model")

    assert first.previous_hash is None
    assert first.chain_hash == compute_chain_hash(None, t1, "role9", "register_dataset")
    assert second.previous_hash == first.chain_hash
    assert second.chain_hash == compute_chain_hash(first.chain_hash, t2, "role9", "register_model")

    with session_factory() as session:
        rows = session.scalars(select(AuditLogRecord).order_by(AuditLogRecord.id.asc())).all()
        assert len(rows) == 2
        assert rows[1].previous_hash == rows[0].chain_hash


def test_write_audit_log_hash_matches_persisted_utc_timestamp_for_offset_inputs(registry, session_factory):
    offset_timestamp = datetime(2026, 5, 18, 17, 0, tzinfo=timezone(timedelta(hours=7)))

    record = registry.write_audit_log(timestamp=offset_timestamp, actor="role9", action="register_dataset")

    with session_factory() as session:
        saved = session.scalar(select(AuditLogRecord).where(AuditLogRecord.id == record.id))

    assert saved is not None
    assert saved.timestamp == offset_timestamp.astimezone(timezone.utc)
    assert saved.chain_hash == compute_chain_hash(saved.previous_hash, saved.timestamp, saved.actor, saved.action)


def test_checksum_constraint_enforced(session_factory):
    with session_factory() as session:
        session.add(
            DatasetRecord(
                version="bad-checksum",
                path="/data/bad.parquet",
                checksum="short",
                provenance={"source": "test"},
                as_of_time=datetime(2026, 5, 18, tzinfo=timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_pit_embargo_preserves_future_visibility_boundary(registry, session_factory):
    embargo = datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc)
    registry.register_model(
        name="alpha_pit_safe",
        version="v2.0.0",
        path="/models/alpha_pit_safe_v2.joblib",
        status="staged",
        metrics={"sharpe": 1.2},
        pit_embargo=embargo,
    )

    with session_factory() as session:
        visible_before = session.scalars(select(ModelRecord).where(ModelRecord.pit_embargo <= embargo - timedelta(seconds=1))).all()
        visible_after = session.scalars(select(ModelRecord).where(ModelRecord.pit_embargo <= embargo)).all()

    assert visible_before == []
    assert len(visible_after) == 1


@pytest.mark.parametrize(
    ("field_name", "operation"),
    [
        (
            "as_of_time",
            lambda registry, naive_dt: registry.register_dataset(
                version="dataset-naive",
                path="/data/naive.parquet",
                checksum="c" * 64,
                provenance={"source": "vendor"},
                as_of_time=naive_dt,
            ),
        ),
        (
            "pit_embargo",
            lambda registry, naive_dt: registry.register_model(
                name="alpha_naive",
                version="v1.0.1",
                path="/models/alpha_naive.joblib",
                status="validated",
                metrics={"sharpe": 1.0},
                pit_embargo=naive_dt,
            ),
        ),
        (
            "timestamp",
            lambda registry, naive_dt: registry.write_audit_log(
                timestamp=naive_dt,
                actor="role9",
                action="naive_timestamp",
            ),
        ),
    ],
)
def test_registry_rejects_naive_datetimes(registry, field_name, operation):
    naive_dt = datetime(2026, 5, 18, 9, 30)

    with pytest.raises(StatementError, match="Naive datetime values are not allowed") as exc_info:
        operation(registry, naive_dt)

    assert isinstance(exc_info.value.orig, ValueError)
