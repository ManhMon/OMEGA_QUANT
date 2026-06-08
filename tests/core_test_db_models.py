"""
Unit tests for OMEGA_QUANT database models.

Version: 2.1
Compliance: V21_QUANT Institutional Grade

Tests cover:
- Model creation and validation
- PIT query semantics
- Temporal filtering
- Relationship integrity
- Index performance
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

from omega.core.db import (
    init_db, get_session,
    Task, TaskEvent, Artifact, Dataset, Model, ModelVersion,
    Experiment, Backtest, RiskReport, Execution, MemorySnapshot, AuditLog
)
from omega.core.db.models import TaskStatus, TaskType, DeploymentState, EventSeverity
from omega.core.db.queries import (
    pit_query, get_latest_version, get_task_history, get_active_tasks,
    get_deployed_models, get_audit_trail, get_backtest_results,
    get_risk_breaches, get_execution_history, get_latest_snapshot
)


@pytest.fixture
def db_session():
    """Create a test database session."""
    engine = init_db(drop_all=True)
    session = get_session(engine)
    yield session
    session.close()


@pytest.fixture
def sample_task(db_session):
    """Create a sample task for testing."""
    now = datetime.utcnow()
    task = Task(
        task_id="task_001",
        task_type=TaskType.CODING,
        priority=5,
        status=TaskStatus.CREATED,
        owner_agent="agent_001",
        as_of=now,
        available_at=now
    )
    db_session.add(task)
    db_session.commit()
    return task


@pytest.fixture
def sample_dataset(db_session):
    """Create a sample dataset for testing."""
    now = datetime.utcnow()
    dataset = Dataset(
        dataset_id="dataset_001",
        name="test_dataset",
        source="test_source",
        frequency="daily",
        schema_version="1.0",
        provenance={"source": "test"},
        timestamp_semantics="trade_time",
        storage_path="/data/test",
        version="1.0.0",
        as_of=now,
        available_at=now
    )
    db_session.add(dataset)
    db_session.commit()
    return dataset


class TestTaskModel:
    """Test Task model functionality."""
    
    def test_create_task(self, db_session):
        """Test creating a task."""
        now = datetime.utcnow()
        task = Task(
            task_id="task_test_001",
            task_type=TaskType.PLANNING,
            priority=3,
            status=TaskStatus.CREATED,
            owner_agent="agent_test",
            as_of=now,
            available_at=now
        )
        db_session.add(task)
        db_session.commit()
        
        # Verify task was created
        retrieved = db_session.query(Task).filter_by(task_id="task_test_001").first()
        assert retrieved is not None
        assert retrieved.task_type == TaskType.PLANNING
        assert retrieved.priority == 3
        assert retrieved.status == TaskStatus.CREATED
    
    def test_task_hierarchy(self, db_session, sample_task):
        """Test parent-child task relationships."""
        now = datetime.utcnow()
        child_task = Task(
            task_id="task_child_001",
            parent_task_id=sample_task.task_id,
            task_type=TaskType.CODING,
            priority=5,
            status=TaskStatus.CREATED,
            owner_agent="agent_001",
            as_of=now,
            available_at=now
        )
        db_session.add(child_task)
        db_session.commit()
        
        # Verify relationship
        parent = db_session.query(Task).filter_by(task_id=sample_task.task_id).first()
        assert len(parent.children) == 1
        assert parent.children[0].task_id == "task_child_001"
    
    def test_task_events(self, db_session, sample_task):
        """Test task event logging."""
        now = datetime.utcnow()
        event = TaskEvent(
            event_id="event_001",
            event_type="TASK_STARTED",
            timestamp=now,
            source="scheduler",
            task_id=sample_task.task_id,
            payload={"message": "Task started"},
            as_of=now,
            available_at=now
        )
        db_session.add(event)
        db_session.commit()
        
        # Verify event was logged
        task = db_session.query(Task).filter_by(task_id=sample_task.task_id).first()
        assert len(task.events) == 1
        assert task.events[0].event_type == "TASK_STARTED"


class TestPITQueries:
    """Test Point-in-Time query semantics."""
    
    def test_pit_query_basic(self, db_session):
        """Test basic PIT query filtering."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        
        # Create datasets at different times
        for i in range(3):
            dataset = Dataset(
                dataset_id=f"dataset_pit_{i}",
                name=f"dataset_{i}",
                source="test",
                frequency="daily",
                schema_version="1.0",
                provenance={"source": "test"},
                timestamp_semantics="trade_time",
                storage_path=f"/data/test_{i}",
                version="1.0.0",
                as_of=base_time + timedelta(days=i),
                available_at=base_time + timedelta(days=i, hours=1)
            )
            db_session.add(dataset)
        db_session.commit()
        
        # Query as of day 1 - should get only first 2 datasets
        query_time = base_time + timedelta(days=1)
        results = pit_query(db_session, Dataset, as_of=query_time).all()
        assert len(results) == 2
        
        # Query as of day 2 - should get all 3 datasets
        query_time = base_time + timedelta(days=2)
        results = pit_query(db_session, Dataset, as_of=query_time).all()
        assert len(results) == 3
    
    def test_pit_query_available_at(self, db_session):
        """Test PIT query with available_at filtering."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        
        # Create dataset that becomes available later
        dataset = Dataset(
            dataset_id="dataset_delayed",
            name="delayed_dataset",
            source="test",
            frequency="daily",
            schema_version="1.0",
            provenance={"source": "test"},
            timestamp_semantics="trade_time",
            storage_path="/data/delayed",
            version="1.0.0",
            as_of=base_time,
            available_at=base_time + timedelta(hours=2)
        )
        db_session.add(dataset)
        db_session.commit()
        
        # Query before available_at - should not find dataset
        query_time = base_time + timedelta(hours=1)
        results = pit_query(
            db_session, Dataset,
            as_of=base_time,
            available_at=query_time
        ).all()
        assert len(results) == 0
        
        # Query after available_at - should find dataset
        query_time = base_time + timedelta(hours=3)
        results = pit_query(
            db_session, Dataset,
            as_of=base_time,
            available_at=query_time
        ).all()
        assert len(results) == 1
    
    def test_get_latest_version(self, db_session):
        """Test getting latest version of an entity."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        
        # Create multiple versions of a dataset
        # Note: Each version needs a unique dataset_id since it's the primary key
        for i in range(3):
            dataset = Dataset(
                dataset_id=f"dataset_versioned_v{i}",
                name="versioned_dataset",
                source="test",
                frequency="daily",
                schema_version="1.0",
                provenance={"source": "test"},
                timestamp_semantics="trade_time",
                storage_path=f"/data/v{i}",
                version=f"1.{i}.0",
                as_of=base_time + timedelta(days=i),
                available_at=base_time + timedelta(days=i)
            )
            db_session.add(dataset)
        db_session.commit()
        
        # Get latest version as of day 1
        query_time = base_time + timedelta(days=1)
        latest = get_latest_version(
            db_session, Dataset,
            "dataset_versioned_v1",
            as_of=query_time
        )
        assert latest is not None
        assert latest.version == "1.1.0"
        
        # Get latest version as of day 2
        query_time = base_time + timedelta(days=2)
        latest = get_latest_version(
            db_session, Dataset,
            "dataset_versioned_v2",
            as_of=query_time
        )
        assert latest is not None
        assert latest.version == "1.2.0"


class TestModelVersioning:
    """Test model versioning and deployment."""
    
    def test_model_version_lifecycle(self, db_session):
        """Test model version lifecycle."""
        now = datetime.utcnow()
        
        # Create model
        model = Model(
            model_id="model_001",
            name="test_model",
            model_type="alpha",
            created_by="agent_001",
            as_of=now,
            available_at=now
        )
        db_session.add(model)
        db_session.commit()
        
        # Create model version
        version = ModelVersion(
            version_id="version_001",
            model_id="model_001",
            version="1.0.0",
            training_data_ref="dataset_001",
            training_config={"epochs": 100},
            evaluation_metrics={"accuracy": 0.95},
            deployment_state=DeploymentState.TRAINED,
            as_of=now,
            available_at=now
        )
        db_session.add(version)
        db_session.commit()
        
        # Verify version was created
        retrieved = db_session.query(ModelVersion).filter_by(version_id="version_001").first()
        assert retrieved is not None
        assert retrieved.deployment_state == DeploymentState.TRAINED
        
        # Update deployment state
        retrieved.deployment_state = DeploymentState.DEPLOYED
        db_session.commit()
        
        # Verify state was updated
        retrieved = db_session.query(ModelVersion).filter_by(version_id="version_001").first()
        assert retrieved.deployment_state == DeploymentState.DEPLOYED
    
    def test_get_deployed_models(self, db_session):
        """Test getting deployed models."""
        now = datetime.utcnow()
        
        # Create model
        model = Model(
            model_id="model_deployed",
            name="deployed_model",
            model_type="alpha",
            created_by="agent_001",
            as_of=now,
            available_at=now
        )
        db_session.add(model)
        
        # Create deployed version
        version = ModelVersion(
            version_id="version_deployed",
            model_id="model_deployed",
            version="1.0.0",
            training_data_ref="dataset_001",
            training_config={"epochs": 100},
            evaluation_metrics={"accuracy": 0.95},
            deployment_state=DeploymentState.DEPLOYED,
            as_of=now,
            available_at=now
        )
        db_session.add(version)
        db_session.commit()
        
        # Get deployed models
        deployed = get_deployed_models(db_session, as_of=now)
        assert len(deployed) == 1
        assert deployed[0].version_id == "version_deployed"


class TestBacktestAndExecution:
    """Test backtest and execution models."""
    
    def test_backtest_creation(self, db_session, sample_dataset):
        """Test creating a backtest."""
        now = datetime.utcnow()
        
        # Create model and version
        model = Model(
            model_id="model_backtest",
            name="backtest_model",
            model_type="alpha",
            created_by="agent_001",
            as_of=now,
            available_at=now
        )
        db_session.add(model)
        
        version = ModelVersion(
            version_id="version_backtest",
            model_id="model_backtest",
            version="1.0.0",
            training_data_ref=sample_dataset.dataset_id,
            training_config={"epochs": 100},
            evaluation_metrics={"accuracy": 0.95},
            deployment_state=DeploymentState.VALIDATED,
            as_of=now,
            available_at=now
        )
        db_session.add(version)
        
        # Create backtest
        backtest = Backtest(
            backtest_id="backtest_001",
            name="test_backtest",
            config={"universe": "VN30"},
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            model_version_ref="version_backtest",
            dataset_ref=sample_dataset.dataset_id,
            results={"sharpe": 1.5},
            metrics={"return": 0.25},
            status="completed",
            created_by="agent_001",
            version="1.0.0",
            as_of=now,
            available_at=now
        )
        db_session.add(backtest)
        db_session.commit()
        
        # Verify backtest was created
        retrieved = db_session.query(Backtest).filter_by(backtest_id="backtest_001").first()
        assert retrieved is not None
        assert retrieved.status == "completed"
        assert retrieved.results["sharpe"] == 1.5
    
    def test_execution_tracking(self, db_session):
        """Test execution tracking."""
        now = datetime.utcnow()
        
        execution = Execution(
            execution_id="exec_001",
            order_id="order_001",
            symbol="VNM",
            side="BUY",
            quantity=1000,
            price=85.5,
            order_time=now - timedelta(seconds=10),
            execution_time=now,
            commission=0.15,
            slippage=0.05,
            as_of=now,
            available_at=now
        )
        db_session.add(execution)
        db_session.commit()
        
        # Verify execution was tracked
        retrieved = db_session.query(Execution).filter_by(execution_id="exec_001").first()
        assert retrieved is not None
        assert retrieved.symbol == "VNM"
        assert retrieved.quantity == 1000
        assert retrieved.price == 85.5


class TestAuditLog:
    """Test audit logging functionality."""
    
    def test_audit_log_creation(self, db_session, sample_task):
        """Test creating audit log entries."""
        now = datetime.utcnow()
        
        audit = AuditLog(
            audit_id="audit_001",
            action="task_created",
            action_type="create",
            actor="agent_001",
            actor_type="agent",
            target_type="task",
            target_id=sample_task.task_id,
            after_state={"status": "CREATED"},
            context={"reason": "new_feature"},
            as_of=now,
            available_at=now
        )
        db_session.add(audit)
        db_session.commit()
        
        # Verify audit log was created
        retrieved = db_session.query(AuditLog).filter_by(audit_id="audit_001").first()
        assert retrieved is not None
        assert retrieved.action == "task_created"
        assert retrieved.target_id == sample_task.task_id
    
    def test_get_audit_trail(self, db_session, sample_task):
        """Test getting audit trail for an entity."""
        now = datetime.utcnow()
        
        # Create multiple audit entries
        for i in range(3):
            audit = AuditLog(
                audit_id=f"audit_trail_{i}",
                action=f"action_{i}",
                action_type="update",
                actor="agent_001",
                actor_type="agent",
                target_type="task",
                target_id=sample_task.task_id,
                as_of=now + timedelta(seconds=i),
                available_at=now + timedelta(seconds=i)
            )
            db_session.add(audit)
        db_session.commit()
        
        # Get audit trail
        trail = get_audit_trail(db_session, "task", sample_task.task_id)
        assert len(trail) == 3
        assert trail[0].action == "action_0"
        assert trail[2].action == "action_2"


class TestMemorySnapshot:
    """Test memory snapshot functionality."""
    
    def test_snapshot_creation(self, db_session):
        """Test creating memory snapshots."""
        now = datetime.utcnow()
        
        snapshot = MemorySnapshot(
            snapshot_id="snapshot_001",
            snapshot_type="checkpoint",
            name="test_checkpoint",
            current_objective="Complete Phase 2.1",
            active_tasks=["task_001", "task_002"],
            working_state={"phase": "2.1"},
            recent_decisions=[{"decision": "use_sqlalchemy"}],
            version="1.0.0",
            created_by="agent_001",
            as_of=now,
            available_at=now
        )
        db_session.add(snapshot)
        db_session.commit()
        
        # Verify snapshot was created
        retrieved = db_session.query(MemorySnapshot).filter_by(snapshot_id="snapshot_001").first()
        assert retrieved is not None
        assert retrieved.snapshot_type == "checkpoint"
        assert len(retrieved.active_tasks) == 2
    
    def test_get_latest_snapshot(self, db_session):
        """Test getting latest snapshot."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        
        # Create multiple snapshots
        for i in range(3):
            snapshot = MemorySnapshot(
                snapshot_id=f"snapshot_{i}",
                snapshot_type="checkpoint",
                name=f"checkpoint_{i}",
                version="1.0.0",
                created_by="agent_001",
                as_of=base_time + timedelta(hours=i),
                available_at=base_time + timedelta(hours=i)
            )
            db_session.add(snapshot)
        db_session.commit()
        
        # Get latest snapshot
        query_time = base_time + timedelta(hours=2)
        latest = get_latest_snapshot(db_session, "checkpoint", as_of=query_time)
        assert latest is not None
        assert latest.snapshot_id == "snapshot_2"


class TestQueryHelpers:
    """Test query helper functions."""
    
    def test_get_active_tasks(self, db_session):
        """Test getting active tasks."""
        now = datetime.utcnow()
        
        # Create tasks with different statuses
        statuses = [TaskStatus.RUNNING, TaskStatus.QUEUED, TaskStatus.ARCHIVED]
        for i, status in enumerate(statuses):
            task = Task(
                task_id=f"task_active_{i}",
                task_type=TaskType.CODING,
                priority=i + 1,
                status=status,
                owner_agent="agent_001",
                as_of=now,
                available_at=now
            )
            db_session.add(task)
        db_session.commit()
        
        # Get active tasks (should exclude ARCHIVED)
        active = get_active_tasks(db_session)
        assert len(active) == 2
        assert all(t.status != TaskStatus.ARCHIVED for t in active)
    
    def test_get_task_history(self, db_session, sample_task):
        """Test getting task event history."""
        now = datetime.utcnow()
        
        # Create task events
        for i in range(3):
            event = TaskEvent(
                event_id=f"event_history_{i}",
                event_type=f"EVENT_{i}",
                timestamp=now + timedelta(seconds=i),
                source="test",
                task_id=sample_task.task_id,
                as_of=now + timedelta(seconds=i),
                available_at=now + timedelta(seconds=i)
            )
            db_session.add(event)
        db_session.commit()
        
        # Get task history
        history = get_task_history(db_session, sample_task.task_id)
        assert len(history) == 3
        assert history[0].event_type == "EVENT_0"
        assert history[2].event_type == "EVENT_2"


class TestDatabaseConstraints:
    """Test database constraints and negative cases."""
    
    def test_pit_constraint_violation(self, db_session):
        """Test that available_at < as_of violates PIT constraint."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=1)
        
        # Try to create a task where available_at < as_of (should fail)
        task = Task(
            task_id="task_pit_violation",
            task_type=TaskType.CODING,
            priority=5,
            status=TaskStatus.CREATED,
            owner_agent="agent_001",
            as_of=future,  # Data represents future
            available_at=now  # But available now (impossible!)
        )
        db_session.add(task)
        
        with pytest.raises(IntegrityError) as exc_info:
            db_session.commit()
        
        assert "ck_tasks_pit_safety" in str(exc_info.value) or "CHECK constraint failed" in str(exc_info.value)
        db_session.rollback()
    
    def test_priority_constraint_too_low(self, db_session):
        """Test that priority < 1 violates constraint."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        task = Task(
            task_id="task_priority_low",
            task_type=TaskType.CODING,
            priority=0,  # Invalid: must be >= 1
            status=TaskStatus.CREATED,
            owner_agent="agent_001",
            as_of=now,
            available_at=now
        )
        db_session.add(task)
        
        with pytest.raises(IntegrityError) as exc_info:
            db_session.commit()
        
        assert "ck_tasks_priority_range" in str(exc_info.value) or "CHECK constraint failed" in str(exc_info.value)
        db_session.rollback()
    
    def test_priority_constraint_too_high(self, db_session):
        """Test that priority > 10 violates constraint."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        task = Task(
            task_id="task_priority_high",
            task_type=TaskType.CODING,
            priority=11,  # Invalid: must be <= 10
            status=TaskStatus.CREATED,
            owner_agent="agent_001",
            as_of=now,
            available_at=now
        )
        db_session.add(task)
        
        with pytest.raises(IntegrityError) as exc_info:
            db_session.commit()
        
        assert "ck_tasks_priority_range" in str(exc_info.value) or "CHECK constraint failed" in str(exc_info.value)
        db_session.rollback()
    
    def test_quality_score_constraint_negative(self, db_session):
        """Test that quality_score < 0 violates constraint."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        dataset = Dataset(
            dataset_id="dataset_quality_neg",
            name="test_dataset",
            source="test_source",
            frequency="daily",
            schema_version="1.0",
            provenance={"source": "test"},
            timestamp_semantics="trade_time",
            storage_path="/data/test",
            version="1.0.0",
            quality_score=-0.1,  # Invalid: must be >= 0
            as_of=now,
            available_at=now
        )
        db_session.add(dataset)
        
        with pytest.raises(IntegrityError) as exc_info:
            db_session.commit()
        
        assert "ck_datasets_quality_score_range" in str(exc_info.value) or "CHECK constraint failed" in str(exc_info.value)
        db_session.rollback()
    
    def test_quality_score_constraint_too_high(self, db_session):
        """Test that quality_score > 1 violates constraint."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        dataset = Dataset(
            dataset_id="dataset_quality_high",
            name="test_dataset",
            source="test_source",
            frequency="daily",
            schema_version="1.0",
            provenance={"source": "test"},
            timestamp_semantics="trade_time",
            storage_path="/data/test",
            version="1.0.0",
            quality_score=1.1,  # Invalid: must be <= 1
            as_of=now,
            available_at=now
        )
        db_session.add(dataset)
        
        with pytest.raises(IntegrityError) as exc_info:
            db_session.commit()
        
        assert "ck_datasets_quality_score_range" in str(exc_info.value) or "CHECK constraint failed" in str(exc_info.value)
        db_session.rollback()
    
    def test_composite_pk_artifact_versioning(self, db_session):
        """Test that composite PK (artifact_id, version) allows multiple versions."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        # Create version 1.0.0
        artifact_v1 = Artifact(
            artifact_id="artifact_001",
            version="1.0.0",
            artifact_type="model",
            name="test_artifact",
            storage_path="/artifacts/v1",
            owner="agent_001",
            as_of=now,
            available_at=now
        )
        db_session.add(artifact_v1)
        db_session.commit()
        
        # Create version 2.0.0 (should succeed with composite PK)
        artifact_v2 = Artifact(
            artifact_id="artifact_001",
            version="2.0.0",
            artifact_type="model",
            name="test_artifact",
            storage_path="/artifacts/v2",
            owner="agent_001",
            as_of=now + timedelta(hours=1),
            available_at=now + timedelta(hours=1)
        )
        db_session.add(artifact_v2)
        db_session.commit()
        
        # Verify both versions exist
        artifacts = db_session.query(Artifact).filter_by(artifact_id="artifact_001").all()
        assert len(artifacts) == 2
        assert {a.version for a in artifacts} == {"1.0.0", "2.0.0"}
    
    def test_composite_pk_dataset_versioning(self, db_session):
        """Test that composite PK (dataset_id, version) allows multiple versions."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        # Create version 1.0.0
        dataset_v1 = Dataset(
            dataset_id="dataset_001",
            version="1.0.0",
            name="test_dataset",
            source="test_source",
            frequency="daily",
            schema_version="1.0",
            provenance={"source": "test"},
            timestamp_semantics="trade_time",
            storage_path="/data/v1",
            as_of=now,
            available_at=now
        )
        db_session.add(dataset_v1)
        db_session.commit()
        
        # Create version 2.0.0 (should succeed with composite PK)
        dataset_v2 = Dataset(
            dataset_id="dataset_001",
            version="2.0.0",
            name="test_dataset",
            source="test_source",
            frequency="daily",
            schema_version="2.0",
            provenance={"source": "test"},
            timestamp_semantics="trade_time",
            storage_path="/data/v2",
            as_of=now + timedelta(hours=1),
            available_at=now + timedelta(hours=1)
        )
        db_session.add(dataset_v2)
        db_session.commit()
        
        # Verify both versions exist
        datasets = db_session.query(Dataset).filter_by(dataset_id="dataset_001").all()
        assert len(datasets) == 2
        assert {d.version for d in datasets} == {"1.0.0", "2.0.0"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
