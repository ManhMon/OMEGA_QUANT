"""
Test suite for Phase 1.2 Database Schema

Tests database schema creation, indexing, and basic CRUD operations.
Follows TDD approach with behavior-focused tests.
"""

import pytest
import sqlite3
from pathlib import Path
from datetime import datetime
from omega.core.database import Database, DatabaseConfig


@pytest.fixture
def test_db_path(tmp_path):
    """Provide temporary database path for testing."""
    return tmp_path / "test_omega.db"


@pytest.fixture
def db(test_db_path):
    """Provide initialized database instance."""
    config = DatabaseConfig(
        db_path=str(test_db_path),
        db_type="sqlite"
    )
    database = Database(config)
    yield database
    database.close()


class TestDatabaseInitialization:
    """Test database initialization and schema creation."""
    
    def test_database_creates_all_tables(self, db):
        """Database should create all required tables on initialization."""
        expected_tables = [
            'tasks',
            'task_events',
            'artifacts',
            'datasets',
            'models',
            'experiments',
            'backtests',
            'risk_reports',
            'executions',
            'memory_snapshots',
            'audit_logs'
        ]
        
        tables = db.get_tables()
        for table in expected_tables:
            assert table in tables, f"Table {table} not created"
    
    def test_database_creates_indexes(self, db):
        """Database should create indexes for performance."""
        indexes = db.get_indexes('tasks')
        assert len(indexes) > 0, "No indexes created on tasks table"

        index_names = [idx['name'] for idx in indexes]
        assert any('status' in name.lower() for name in index_names), "Missing status index"

    def test_all_tables_have_required_indexes(self, db):
        """All 11 tables should have required performance indexes."""
        required_index_checks = {
            'tasks': ['idx_tasks_status', 'idx_tasks_type'],
            'task_events': ['idx_task_events_task_id', 'idx_task_events_timestamp'],
            'artifacts': ['idx_artifacts_checksum', 'idx_artifacts_type'],
            'datasets': ['idx_datasets_name_version', 'idx_datasets_name'],
            'models': ['idx_models_name_version', 'idx_models_status', 'idx_models_name'],
            'experiments': ['idx_experiments_status', 'idx_experiments_name'],
            'backtests': ['idx_backtests_model_id', 'idx_backtests_dates'],
            'risk_reports': ['idx_risk_reports_date', 'idx_risk_reports_portfolio'],
            'executions': ['idx_executions_symbol', 'idx_executions_timestamp', 'idx_executions_order_id'],
            'memory_snapshots': ['idx_memory_snapshots_type', 'idx_memory_snapshots_timestamp'],
            'audit_logs': ['idx_audit_logs_action', 'idx_audit_logs_timestamp', 'idx_audit_logs_actor'],
        }

        for table_name, expected_indexes in required_index_checks.items():
            indexes = db.get_indexes(table_name)
            existing_names = {idx['name'] for idx in indexes}
            for expected in expected_indexes:
                assert expected in existing_names, (
                    f"Missing index {expected} on table {table_name}. "
                    f"Found: {sorted(existing_names)}"
                )
    
    def test_database_connection_is_valid(self, db):
        """Database connection should be valid and queryable."""
        result = db.execute_query("SELECT 1 as test")
        assert result[0]['test'] == 1


class TestTasksTable:
    """Test tasks table operations."""
    
    def test_insert_task(self, db):
        """Should insert task with all required fields."""
        task_data = {
            'task_id': 'task_001',
            'task_type': 'FEATURE_ENGINEERING',
            'status': 'CREATED',
            'priority': 1,
            'created_at': datetime.now().isoformat(),
            'metadata': '{"description": "Test task"}'
        }
        
        db.insert_task(task_data)
        
        # Verify insertion
        tasks = db.get_tasks(task_id='task_001')
        assert len(tasks) == 1
        assert tasks[0]['task_type'] == 'FEATURE_ENGINEERING'
        assert tasks[0]['status'] == 'CREATED'
    
    def test_update_task_status(self, db):
        """Should update task status."""
        task_data = {
            'task_id': 'task_002',
            'task_type': 'MODEL_TRAINING',
            'status': 'CREATED',
            'priority': 2,
            'created_at': datetime.now().isoformat()
        }
        db.insert_task(task_data)
        
        # Update status
        db.update_task_status('task_002', 'RUNNING')
        
        # Verify update
        tasks = db.get_tasks(task_id='task_002')
        assert tasks[0]['status'] == 'RUNNING'
    
    def test_query_tasks_by_status(self, db):
        """Should query tasks by status."""
        # Insert multiple tasks
        for i in range(3):
            db.insert_task({
                'task_id': f'task_{i}',
                'task_type': 'TEST',
                'status': 'RUNNING' if i < 2 else 'COMPLETED',
                'priority': i,
                'created_at': datetime.now().isoformat()
            })
        
        running_tasks = db.get_tasks(status='RUNNING')
        assert len(running_tasks) == 2


class TestTaskEventsTable:
    """Test task_events table for event logging."""
    
    def test_insert_task_event(self, db):
        """Should insert task event."""
        event_data = {
            'event_id': 'evt_001',
            'task_id': 'task_001',
            'event_type': 'STATUS_CHANGE',
            'timestamp': datetime.now().isoformat(),
            'payload': '{"from": "CREATED", "to": "RUNNING"}'
        }
        
        db.insert_task_event(event_data)
        
        events = db.get_task_events(task_id='task_001')
        assert len(events) == 1
        assert events[0]['event_type'] == 'STATUS_CHANGE'
    
    def test_query_events_by_task(self, db):
        """Should query all events for a task."""
        task_id = 'task_multi_event'
        
        for i in range(5):
            db.insert_task_event({
                'event_id': f'evt_{i}',
                'task_id': task_id,
                'event_type': f'EVENT_{i}',
                'timestamp': datetime.now().isoformat()
            })
        
        events = db.get_task_events(task_id=task_id)
        assert len(events) == 5


class TestArtifactsTable:
    """Test artifacts table for artifact storage metadata."""
    
    def test_insert_artifact(self, db):
        """Should insert artifact with checksum."""
        artifact_data = {
            'artifact_id': 'art_001',
            'artifact_type': 'MODEL',
            'path': '/models/xgb_v1.pkl',
            'checksum': 'abc123def456',
            'size_bytes': 1024000,
            'created_at': datetime.now().isoformat(),
            'metadata': '{"version": "v1.0.0"}'
        }
        
        db.insert_artifact(artifact_data)
        
        artifacts = db.get_artifacts(artifact_id='art_001')
        assert len(artifacts) == 1
        assert artifacts[0]['checksum'] == 'abc123def456'
    
    def test_verify_artifact_checksum(self, db):
        """Should verify artifact by checksum."""
        artifact_data = {
            'artifact_id': 'art_002',
            'artifact_type': 'DATASET',
            'path': '/data/train.parquet',
            'checksum': 'xyz789',
            'size_bytes': 5000000,
            'created_at': datetime.now().isoformat()
        }
        db.insert_artifact(artifact_data)
        
        # Verify checksum
        is_valid = db.verify_artifact_checksum('art_002', 'xyz789')
        assert is_valid is True
        
        is_invalid = db.verify_artifact_checksum('art_002', 'wrong_checksum')
        assert is_invalid is False


class TestDatasetsTable:
    """Test datasets table for dataset versioning."""
    
    def test_insert_dataset(self, db):
        """Should insert dataset with version."""
        dataset_data = {
            'dataset_id': 'ds_001',
            'dataset_name': 'market_data',
            'version': 'v1.0.0',
            'path': '/data/market_v1.parquet',
            'created_at': datetime.now().isoformat(),
            'metadata': '{"rows": 100000, "cols": 50}'
        }
        
        db.insert_dataset(dataset_data)
        
        datasets = db.get_datasets(dataset_name='market_data')
        assert len(datasets) == 1
        assert datasets[0]['version'] == 'v1.0.0'
    
    def test_dataset_versioning(self, db):
        """Should support multiple versions of same dataset."""
        for i in range(3):
            db.insert_dataset({
                'dataset_id': f'ds_v{i}',
                'dataset_name': 'market_data',
                'version': f'v1.{i}.0',
                'path': f'/data/market_v1_{i}.parquet',
                'created_at': datetime.now().isoformat()
            })
        
        datasets = db.get_datasets(dataset_name='market_data')
        assert len(datasets) == 3
        
        # Get latest version
        latest = db.get_latest_dataset('market_data')
        assert latest['version'] == 'v1.2.0'


class TestModelsTable:
    """Test models table for model registry."""
    
    def test_insert_model(self, db):
        """Should insert model with version."""
        model_data = {
            'model_id': 'mdl_001',
            'model_name': 'xgb_alpha',
            'version': 'v1.0.0',
            'status': 'STAGING',
            'artifact_id': 'art_001',
            'created_at': datetime.now().isoformat(),
            'metadata': '{"train_date": "2024-01-01"}'
        }
        
        db.insert_model(model_data)
        
        models = db.get_models(model_name='xgb_alpha')
        assert len(models) == 1
        assert models[0]['status'] == 'STAGING'
    
    def test_model_promotion(self, db):
        """Should support model promotion workflow."""
        model_data = {
            'model_id': 'mdl_002',
            'model_name': 'lgb_alpha',
            'version': 'v1.0.0',
            'status': 'STAGING',
            'artifact_id': 'art_002',
            'created_at': datetime.now().isoformat()
        }
        db.insert_model(model_data)
        
        # Promote to VALIDATED
        db.update_model_status('mdl_002', 'VALIDATED')
        models = db.get_models(model_id='mdl_002')
        assert models[0]['status'] == 'VALIDATED'
        
        # Promote to PRODUCTION
        db.update_model_status('mdl_002', 'PRODUCTION')
        models = db.get_models(model_id='mdl_002')
        assert models[0]['status'] == 'PRODUCTION'


class TestAuditLogsTable:
    """Test audit_logs table for immutable logging."""
    
    def test_insert_audit_log(self, db):
        """Should insert audit log entry."""
        log_data = {
            'log_id': 'log_001',
            'action': 'MODEL_REGISTER',
            'actor': 'system',
            'timestamp': datetime.now().isoformat(),
            'details': '{"model": "xgb_alpha", "version": "v1.0.0"}'
        }
        
        db.insert_audit_log(log_data)
        
        logs = db.get_audit_logs(action='MODEL_REGISTER')
        assert len(logs) == 1
    
    def test_audit_logs_are_immutable(self, db):
        """Audit logs should not support updates or deletes."""
        log_data = {
            'log_id': 'log_002',
            'action': 'DATASET_CREATE',
            'actor': 'user_001',
            'timestamp': datetime.now().isoformat()
        }
        db.insert_audit_log(log_data)
        
        # Attempt to update should raise error
        with pytest.raises(Exception):
            db.update_audit_log('log_002', {'action': 'MODIFIED'})
        
        # Attempt to delete should raise error
        with pytest.raises(Exception):
            db.delete_audit_log('log_002')


class TestExperimentsTable:
    """Test experiments table for experiment tracking."""
    
    def test_insert_experiment(self, db):
        """Should insert experiment record."""
        exp_data = {
            'experiment_id': 'exp_001',
            'experiment_name': 'alpha_test_1',
            'status': 'RUNNING',
            'created_at': datetime.now().isoformat(),
            'metadata': '{"params": {"lr": 0.01}}'
        }
        
        db.insert_experiment(exp_data)
        
        exps = db.get_experiments(experiment_id='exp_001')
        assert len(exps) == 1
        assert exps[0]['status'] == 'RUNNING'


class TestBacktestsTable:
    """Test backtests table for backtest results."""
    
    def test_insert_backtest(self, db):
        """Should insert backtest record."""
        bt_data = {
            'backtest_id': 'bt_001',
            'model_id': 'mdl_001',
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
            'metrics': '{"sharpe": 2.5, "returns": 0.35}',
            'created_at': datetime.now().isoformat()
        }
        
        db.insert_backtest(bt_data)
        
        bts = db.get_backtests(backtest_id='bt_001')
        assert len(bts) == 1


class TestRiskReportsTable:
    """Test risk_reports table."""
    
    def test_insert_risk_report(self, db):
        """Should insert risk report."""
        report_data = {
            'report_id': 'rr_001',
            'report_date': '2024-01-01',
            'portfolio_id': 'port_001',
            'metrics': '{"var": 0.02, "cvar": 0.03}',
            'created_at': datetime.now().isoformat()
        }
        
        db.insert_risk_report(report_data)
        
        reports = db.get_risk_reports(report_id='rr_001')
        assert len(reports) == 1


class TestExecutionsTable:
    """Test executions table for trade execution records."""
    
    def test_insert_execution(self, db):
        """Should insert execution record."""
        exec_data = {
            'execution_id': 'exec_001',
            'order_id': 'ord_001',
            'symbol': 'VNM',
            'side': 'BUY',
            'quantity': 1000,
            'price': 85.5,
            'timestamp': datetime.now().isoformat()
        }
        
        db.insert_execution(exec_data)
        
        execs = db.get_executions(execution_id='exec_001')
        assert len(execs) == 1
        assert execs[0]['symbol'] == 'VNM'


class TestMemorySnapshotsTable:
    """Test memory_snapshots table for system state snapshots."""
    
    def test_insert_memory_snapshot(self, db):
        """Should insert memory snapshot."""
        snapshot_data = {
            'snapshot_id': 'snap_001',
            'snapshot_type': 'CHECKPOINT',
            'timestamp': datetime.now().isoformat(),
            'data': '{"state": "running", "tasks": 5}'
        }
        
        db.insert_memory_snapshot(snapshot_data)
        
        snapshots = db.get_memory_snapshots(snapshot_id='snap_001')
        assert len(snapshots) == 1
