"""
PIT-Safe Query Helpers
Institutional-grade query utilities for temporal data.

Version: 2.1
Compliance: V21_QUANT Institutional Grade

All queries respect PIT semantics:
- No look-ahead bias
- Proper temporal filtering
- Vectorized operations where possible
"""

from datetime import datetime, timezone
from typing import Optional, List, Type, TypeVar
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, Query

from .models import (
    Task, TaskEvent, Artifact, Dataset, Model, ModelVersion,
    Experiment, Backtest, RiskReport, Execution, MemorySnapshot, AuditLog
)

T = TypeVar('T')


def get_task(session: Session, task_id: str) -> Optional[Task]:
    """Return one persisted task without creating fallback state."""
    return session.query(Task).filter(Task.task_id == task_id).one_or_none()


def pit_query(
    session: Session,
    model_class: Type[T],
    as_of: datetime,
    available_at: Optional[datetime] = None
) -> Query:
    """
    Create a PIT-safe query.
    
    Args:
        session: Database session
        model_class: Model class to query
        as_of: Business time - data must represent this time or earlier
        available_at: System time - data must be available by this time
        
    Returns:
        Query object with PIT filters applied
        
    Example:
        # Get all datasets available as of 2024-01-01
        datasets = pit_query(session, Dataset, 
                            as_of=datetime(2024, 1, 1)).all()
    """
    if available_at is None:
        available_at = datetime.now(timezone.utc)
    
    query = session.query(model_class)
    
    # Apply PIT filters
    query = query.filter(
        and_(
            model_class.as_of <= as_of,
            model_class.available_at <= available_at
        )
    )
    
    return query


def get_latest_version(
    session: Session,
    model_class: Type[T],
    entity_id: str,
    as_of: datetime,
    available_at: Optional[datetime] = None
) -> Optional[T]:
    """
    Get the latest version of an entity as of a specific time.
    
    Args:
        session: Database session
        model_class: Model class (must have version field)
        entity_id: Entity identifier
        as_of: Business time
        available_at: System time
        
    Returns:
        Latest version or None
        
    Example:
        # Get latest model version as of 2024-01-01
        latest = get_latest_version(session, ModelVersion, 
                                   "model_123", 
                                   datetime(2024, 1, 1))
    """
    if available_at is None:
        available_at = datetime.now(timezone.utc)
    
    # Determine the ID field name
    if hasattr(model_class, 'dataset_id'):
        id_field = model_class.dataset_id
    elif hasattr(model_class, 'model_id'):
        id_field = model_class.model_id
    elif hasattr(model_class, 'artifact_id'):
        id_field = model_class.artifact_id
    else:
        raise ValueError(f"Model {model_class.__name__} does not have a recognized ID field")
    
    result = (
        session.query(model_class)
        .filter(
            and_(
                id_field == entity_id,
                model_class.as_of <= as_of,
                model_class.available_at <= available_at
            )
        )
        .order_by(model_class.version.desc())
        .first()
    )
    
    return result


def get_task_history(
    session: Session,
    task_id: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[TaskEvent]:
    """
    Get event history for a task.
    
    Args:
        session: Database session
        task_id: Task identifier
        start_time: Optional start time filter
        end_time: Optional end time filter
        
    Returns:
        List of task events ordered by timestamp
    """
    query = session.query(TaskEvent).filter(TaskEvent.task_id == task_id)
    
    if start_time:
        query = query.filter(TaskEvent.timestamp >= start_time)
    
    if end_time:
        query = query.filter(TaskEvent.timestamp <= end_time)
    
    return query.order_by(TaskEvent.timestamp.asc()).all()


def get_active_tasks(
    session: Session,
    owner_agent: Optional[str] = None,
    task_type: Optional[str] = None
) -> List[Task]:
    """
    Get currently active tasks.
    
    Args:
        session: Database session
        owner_agent: Optional filter by owner
        task_type: Optional filter by task type
        
    Returns:
        List of active tasks
    """
    from .models import TaskStatus
    
    active_statuses = [
        TaskStatus.QUEUED,
        TaskStatus.PLANNED,
        TaskStatus.DISPATCHED,
        TaskStatus.RUNNING,
        TaskStatus.WAITING,
        TaskStatus.VERIFYING,
        TaskStatus.REVIEWING,
        TaskStatus.RISK_CHECK
    ]
    
    query = session.query(Task).filter(Task.status.in_(active_statuses))
    
    if owner_agent:
        query = query.filter(Task.owner_agent == owner_agent)
    
    if task_type:
        query = query.filter(Task.task_type == task_type)
    
    return query.order_by(Task.priority.asc(), Task.created_at.asc()).all()


def get_deployed_models(
    session: Session,
    as_of: datetime,
    available_at: Optional[datetime] = None
) -> List[ModelVersion]:
    """
    Get all deployed model versions as of a specific time.
    
    Args:
        session: Database session
        as_of: Business time
        available_at: System time
        
    Returns:
        List of deployed model versions
    """
    from .models import DeploymentState
    
    if available_at is None:
        available_at = datetime.now(timezone.utc)
    
    return (
        session.query(ModelVersion)
        .filter(
            and_(
                ModelVersion.deployment_state == DeploymentState.DEPLOYED,
                ModelVersion.as_of <= as_of,
                ModelVersion.available_at <= available_at
            )
        )
        .all()
    )


def get_audit_trail(
    session: Session,
    target_type: str,
    target_id: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[AuditLog]:
    """
    Get audit trail for a specific entity.
    
    Args:
        session: Database session
        target_type: Type of target entity
        target_id: Target entity identifier
        start_time: Optional start time filter
        end_time: Optional end time filter
        
    Returns:
        List of audit log entries ordered by timestamp
    """
    query = session.query(AuditLog).filter(
        and_(
            AuditLog.target_type == target_type,
            AuditLog.target_id == target_id
        )
    )
    
    if start_time:
        query = query.filter(AuditLog.as_of >= start_time)
    
    if end_time:
        query = query.filter(AuditLog.as_of <= end_time)
    
    return query.order_by(AuditLog.as_of.asc()).all()


def get_backtest_results(
    session: Session,
    model_version_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[Backtest]:
    """
    Get backtest results for a model version.
    
    Args:
        session: Database session
        model_version_id: Model version identifier
        start_date: Optional start date filter
        end_date: Optional end date filter
        
    Returns:
        List of backtest results
    """
    query = session.query(Backtest).filter(
        Backtest.model_version_ref == model_version_id
    )
    
    if start_date:
        query = query.filter(Backtest.start_date >= start_date)
    
    if end_date:
        query = query.filter(Backtest.end_date <= end_date)
    
    return query.order_by(Backtest.start_date.desc()).all()


def get_risk_breaches(
    session: Session,
    as_of: datetime,
    available_at: Optional[datetime] = None
) -> List[RiskReport]:
    """
    Get all risk reports with breaches as of a specific time.
    
    Args:
        session: Database session
        as_of: Business time
        available_at: System time
        
    Returns:
        List of risk reports with breaches
    """
    from .models import EventSeverity
    
    if available_at is None:
        available_at = datetime.now(timezone.utc)
    
    return (
        session.query(RiskReport)
        .filter(
            and_(
                RiskReport.as_of <= as_of,
                RiskReport.available_at <= available_at,
                RiskReport.breaches.isnot(None),
                RiskReport.severity.in_([EventSeverity.WARNING, EventSeverity.ERROR, EventSeverity.CRITICAL])
            )
        )
        .order_by(RiskReport.severity.desc(), RiskReport.as_of.desc())
        .all()
    )


def get_execution_history(
    session: Session,
    symbol: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    backtest_ref: Optional[str] = None
) -> List[Execution]:
    """
    Get execution history with optional filters.
    
    Args:
        session: Database session
        symbol: Optional symbol filter
        start_time: Optional start time filter
        end_time: Optional end time filter
        backtest_ref: Optional backtest reference filter
        
    Returns:
        List of executions ordered by execution time
    """
    query = session.query(Execution)
    
    if symbol:
        query = query.filter(Execution.symbol == symbol)
    
    if start_time:
        query = query.filter(Execution.execution_time >= start_time)
    
    if end_time:
        query = query.filter(Execution.execution_time <= end_time)
    
    if backtest_ref:
        query = query.filter(Execution.backtest_ref == backtest_ref)
    
    return query.order_by(Execution.execution_time.asc()).all()


def get_latest_snapshot(
    session: Session,
    snapshot_type: str,
    as_of: datetime,
    available_at: Optional[datetime] = None
) -> Optional[MemorySnapshot]:
    """
    Get the latest memory snapshot of a specific type.
    
    Args:
        session: Database session
        snapshot_type: Type of snapshot
        as_of: Business time
        available_at: System time
        
    Returns:
        Latest snapshot or None
    """
    if available_at is None:
        available_at = datetime.now(timezone.utc)
    
    return (
        session.query(MemorySnapshot)
        .filter(
            and_(
                MemorySnapshot.snapshot_type == snapshot_type,
                MemorySnapshot.as_of <= as_of,
                MemorySnapshot.available_at <= available_at
            )
        )
        .order_by(MemorySnapshot.as_of.desc())
        .first()
    )
