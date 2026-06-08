"""Phase 10 database-backed registry interface."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from omega.core.db.persistence import (
    AuditLogRecord,
    DatasetRecord,
    ModelRecord,
    compute_chain_hash,
    init_registry_db,
    make_registry_session_factory,
)


class DatabaseRegistry:
    """Database-backed registry for datasets, models, and audit logs."""

    def __init__(self, database_url: str = "sqlite:///:memory:", session_factory: Optional[sessionmaker[Session]] = None):
        if session_factory is None:
            engine = init_registry_db(database_url)
            session_factory = make_registry_session_factory(engine)
        self._session_factory = session_factory

    def register_dataset(
        self,
        *,
        version: str,
        path: str,
        checksum: str,
        provenance: Dict[str, Any],
        as_of_time: datetime,
    ) -> DatasetRecord:
        record = DatasetRecord(
            version=version,
            path=path,
            checksum=checksum,
            provenance=provenance,
            as_of_time=as_of_time,
        )
        with self._session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def register_model(
        self,
        *,
        name: str,
        version: str,
        path: str,
        status: str,
        metrics: Dict[str, Any],
        pit_embargo: datetime,
    ) -> ModelRecord:
        record = ModelRecord(
            name=name,
            version=version,
            path=path,
            status=status,
            metrics=metrics,
            pit_embargo=pit_embargo,
        )
        with self._session_factory() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def write_audit_log(
        self,
        *,
        timestamp: datetime,
        actor: str,
        action: str,
    ) -> AuditLogRecord:
        normalized_timestamp = timestamp.astimezone(timezone.utc) if timestamp.tzinfo is not None else timestamp
        with self._session_factory() as session:
            previous_hash = self._get_latest_chain_hash(session)
            record = AuditLogRecord(
                previous_hash=previous_hash,
                timestamp=normalized_timestamp,
                actor=actor,
                action=action,
                chain_hash=compute_chain_hash(previous_hash, normalized_timestamp, actor, action),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
        return record

    def _get_latest_chain_hash(self, session: Session) -> Optional[str]:
        stmt = select(AuditLogRecord.chain_hash).order_by(AuditLogRecord.id.desc()).limit(1)
        return session.execute(stmt).scalar_one_or_none()
