"""
Phase 10 registry persistence models.

SQLite-first SQLAlchemy schema for dataset registry, model registry,
and chained audit logs.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import JSON, CheckConstraint, DateTime, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RegistryBase(DeclarativeBase):
    """Base for Phase 10 registry persistence tables."""


class UTCDateTime(TypeDecorator):
    """Persist UTC timestamps and restore tz-aware datetimes on SQLite."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime values are not allowed; timezone-aware UTC boundary required")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: Optional[datetime], dialect):
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc)
        return value.replace(tzinfo=timezone.utc)


class DatasetRecord(RegistryBase):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("version", name="uq_datasets_version"),
        CheckConstraint("length(version) > 0", name="ck_datasets_version_nonempty"),
        CheckConstraint("length(path) > 0", name="ck_datasets_path_nonempty"),
        CheckConstraint("length(checksum) = 64", name="ck_datasets_checksum_sha256"),
    )


class ModelRecord(RegistryBase):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    pit_embargo: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_models_name_version"),
        CheckConstraint("length(name) > 0", name="ck_models_name_nonempty"),
        CheckConstraint("length(version) > 0", name="ck_models_version_nonempty"),
        CheckConstraint("length(path) > 0", name="ck_models_path_nonempty"),
    )


class AuditLogRecord(RegistryBase):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chain_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    previous_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("length(chain_hash) = 64", name="ck_audit_logs_chain_hash_sha256"),
        CheckConstraint(
            "previous_hash IS NULL OR length(previous_hash) = 64",
            name="ck_audit_logs_previous_hash_sha256",
        ),
        CheckConstraint("length(actor) > 0", name="ck_audit_logs_actor_nonempty"),
        CheckConstraint("length(action) > 0", name="ck_audit_logs_action_nonempty"),
    )


def create_registry_engine(database_url: str = "sqlite:///:memory:"):
    return create_engine(database_url)


def init_registry_db(database_url: str = "sqlite:///:memory:"):
    engine = create_registry_engine(database_url)
    RegistryBase.metadata.create_all(engine)
    return engine


def make_registry_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def canonicalize_payload(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_chain_hash(previous_hash: Optional[str], timestamp: datetime, actor: str, action: str) -> str:
    payload = {
        "previous_hash": previous_hash or "",
        "timestamp": timestamp.isoformat(),
        "actor": actor,
        "action": action,
    }
    return hashlib.sha256(canonicalize_payload(payload).encode("utf-8")).hexdigest()
