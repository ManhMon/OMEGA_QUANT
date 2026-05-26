"""
Database implementation for OMEGA_QUANT.

Provides SQLite for development and PostgreSQL-ready schema.
Institutional Grade Features:
- Task State Machine tables
- Metadata & Registry tables
- Immutable Audit Logs
- Automated Indexing
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DatabaseConfig:
    """Database configuration."""
    db_path: str = "omega.db"
    db_type: str = "sqlite"  # sqlite, postgresql
    auto_init: bool = True


class Database:
    """
    Institutional Database Layer for OMEGA_QUANT.
    """
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.conn = None
        self._init_connection()
        if self.config.auto_init:
            self._create_schema()
            self._create_indexes()

    def _init_connection(self):
        """Initialize database connection."""
        if self.config.db_type == "sqlite":
            self.conn = sqlite3.connect(self.config.db_path)
            self.conn.row_factory = sqlite3.Row
        else:
            raise NotImplementedError("PostgreSQL connection not implemented yet")

    def _create_schema(self):
        """Create database tables."""
        cursor = self.conn.cursor()
        
        # 1. Tasks table (Task State Machine)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                metadata TEXT
            )
        """)
        
        # 2. Task Events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_events (
                event_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks (task_id)
            )
        """)
        
        # 3. Artifacts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                artifact_type TEXT NOT NULL,
                path TEXT NOT NULL,
                checksum TEXT NOT NULL,
                size_bytes INTEGER,
                created_at TEXT NOT NULL,
                metadata TEXT
            )
        """)
        
        # 4. Datasets table (Versioning)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                dataset_name TEXT NOT NULL,
                version TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata TEXT
            )
        """)
        
        # 5. Models table (Registry)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS models (
                model_id TEXT PRIMARY KEY,
                model_name TEXT NOT NULL,
                version TEXT NOT NULL,
                status TEXT NOT NULL,
                artifact_id TEXT,
                created_at TEXT NOT NULL,
                metadata TEXT,
                FOREIGN KEY (artifact_id) REFERENCES artifacts (artifact_id)
            )
        """)
        
        # 6. Experiments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                experiment_name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata TEXT
            )
        """)
        
        # 7. Backtests table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtests (
                backtest_id TEXT PRIMARY KEY,
                model_id TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                metrics TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (model_id) REFERENCES models (model_id)
            )
        """)
        
        # 8. Risk Reports table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_reports (
                report_id TEXT PRIMARY KEY,
                report_date TEXT NOT NULL,
                portfolio_id TEXT NOT NULL,
                metrics TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # 9. Executions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                execution_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                timestamp TEXT NOT NULL,
                metadata TEXT
            )
        """)
        
        # 10. Memory Snapshots table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                snapshot_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                data TEXT NOT NULL
            )
        """)
        
        # 11. Audit Logs table (IMMUTABLE)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                details TEXT
            )
        """)
        
        self.conn.commit()

    def _create_indexes(self):
        """Create indexes for performance."""
        cursor = self.conn.cursor()
        
        # Tasks indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(task_type)")
        
        # Task events indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_events_timestamp ON task_events(timestamp)")
        
        # Artifacts indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_checksum ON artifacts(checksum)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(artifact_type)")
        
        # Datasets indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_datasets_name_version ON datasets(dataset_name, version)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_datasets_name ON datasets(dataset_name)")
        
        # Models indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_name_version ON models(model_name, version)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_status ON models(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_name ON models(model_name)")
        
        # Experiments indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_experiments_name ON experiments(experiment_name)")
        
        # Backtests indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_backtests_model_id ON backtests(model_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_backtests_dates ON backtests(start_date, end_date)")
        
        # Risk reports indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_risk_reports_date ON risk_reports(report_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_risk_reports_portfolio ON risk_reports(portfolio_id)")
        
        # Executions indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_symbol ON executions(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_timestamp ON executions(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_order_id ON executions(order_id)")
        
        # Memory snapshots indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_snapshots_type ON memory_snapshots(snapshot_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_snapshots_timestamp ON memory_snapshots(timestamp)")
        
        # Audit logs indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor)")
        
        self.conn.commit()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def get_tables(self) -> List[str]:
        """Return list of table names."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return [row['name'] for row in cursor.fetchall()]

    def get_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        """Return list of indexes for a table."""
        cursor = self.conn.cursor()
        cursor.execute(f"PRAGMA index_list('{table_name}')")
        return [dict(row) for row in cursor.fetchall()]

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dicts."""
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        if query.strip().upper().startswith("SELECT") or "RETURNING" in query.upper():
            return [dict(row) for row in cursor.fetchall()]
        self.conn.commit()
        return []

    # --- Task Operations ---
    
    def insert_task(self, task_data: Dict[str, Any]):
        """Insert a new task."""
        columns = ', '.join(task_data.keys())
        placeholders = ', '.join(['?' for _ in task_data])
        query = f"INSERT INTO tasks ({columns}) VALUES ({placeholders})"
        self.execute_query(query, tuple(task_data.values()))

    def update_task_status(self, task_id: str, status: str):
        """Update task status."""
        query = "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?"
        self.execute_query(query, (status, datetime.now().isoformat(), task_id))

    def get_tasks(self, task_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve tasks by ID or status."""
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        return self.execute_query(query, tuple(params))

    # --- Task Events Operations ---

    def insert_task_event(self, event_data: Dict[str, Any]):
        """Insert a task event."""
        columns = ', '.join(event_data.keys())
        placeholders = ', '.join(['?' for _ in event_data])
        query = f"INSERT INTO task_events ({columns}) VALUES ({placeholders})"
        self.execute_query(query, tuple(event_data.values()))

    def get_task_events(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieve events for a task."""
        query = "SELECT * FROM task_events WHERE task_id = ? ORDER BY timestamp ASC"
        return self.execute_query(query, (task_id,))

    # --- Artifact Operations ---

    def insert_artifact(self, artifact_data: Dict[str, Any]):
        """Insert artifact metadata."""
        columns = ', '.join(artifact_data.keys())
        placeholders = ', '.join(['?' for _ in artifact_data])
        query = f"INSERT INTO artifacts ({columns}) VALUES ({placeholders})"
        self.execute_query(query, tuple(artifact_data.values()))

    def get_artifacts(self, artifact_id: str) -> List[Dict[str, Any]]:
        """Retrieve artifact by ID."""
        query = "SELECT * FROM artifacts WHERE artifact_id = ?"
        return self.execute_query(query, (artifact_id,))

    def verify_artifact_checksum(self, artifact_id: str, checksum: str) -> bool:
        """Verify artifact checksum."""
        query = "SELECT checksum FROM artifacts WHERE artifact_id = ?"
        result = self.execute_query(query, (artifact_id,))
        if not result:
            return False
        return result[0]['checksum'] == checksum

    # --- Dataset Operations ---

    def insert_dataset(self, dataset_data: Dict[str, Any]):
        """Insert dataset metadata."""
        columns = ', '.join(dataset_data.keys())
        placeholders = ', '.join(['?' for _ in dataset_data])
        query = f"INSERT INTO datasets ({columns}) VALUES ({placeholders})"
        self.execute_query(query, tuple(dataset_data.values()))

    def get_datasets(self, dataset_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve datasets by name."""
        query = "SELECT * FROM datasets WHERE 1=1"
        params = []
        if dataset_name:
            query += " AND dataset_name = ?"
            params.append(dataset_name)
        query += " ORDER BY version DESC"
        return self.execute_query(query, tuple(params))

    def get_latest_dataset(self, dataset_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve latest version of a dataset."""
        datasets = self.get_datasets(dataset_name)
        return datasets[0] if datasets else None

    # --- Model Operations ---

    def insert_model(self, model_data: Dict[str, Any]):
        """Insert model metadata."""
        columns = ', '.join(model_data.keys())
        placeholders = ', '.join(['?' for _ in model_data])
        query = f"INSERT INTO models ({columns}) VALUES ({placeholders})"
        self.execute_query(query, tuple(model_data.values()))

    def update_model_status(self, model_id: str, status: str):
        """Update model status (Promotion)."""
        query = "UPDATE models SET status = ? WHERE model_id = ?"
        self.execute_query(query, (status, model_id))

    def get_models(self, model_id: Optional[str] = None, model_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve models by ID or name."""
        query = "SELECT * FROM models WHERE 1=1"
        params = []
        if model_id:
            query += " AND model_id = ?"
            params.append(model_id)
        if model_name:
            query += " AND model_name = ?"
            params.append(model_name)
        return self.execute_query(query, tuple(params))

    # --- Experiment Operations ---

    def insert_experiment(self, experiment_data: Dict[str, Any]):
        """Insert experiment record."""
        columns = ', '.join(experiment_data.keys())
        placeholders = ', '.join(['?' for _ in experiment_data])
        query = f"INSERT INTO experiments ({columns}) VALUES ({placeholders})"
        self.execute_query(query, tuple(experiment_data.values()))

    def get_experiments(self, experiment_id: str) -> List[Dict[str, Any]]:
        """Retrieve experiment by ID."""
        query = "SELECT * FROM experiments WHERE experiment_id = ?"
        return self.execute_query(query, (experiment_id,))

    # --- Backtest Operations ---

    def insert_backtest(self, backtest_data: Dict[str, Any]):
        """Insert backtest record."""
        columns = ', '.join(backtest_data.keys())
        placeholders = ', '.join(['?' for _ in backtest_data])
        query = f"INSERT INTO backtests ({columns}) VALUES ({placeholders})"
        self.execute_query(query, tuple(backtest_data.values()))

    def get_backtests(self, backtest_id: str) -> List[Dict[str, Any]]:
        """Retrieve backtest by ID."""
        query = "SELECT * FROM backtests WHERE backtest_id = ?"
        return self.execute_query(query, (backtest_id,))

    # --- Risk Report Operations ---

    def insert_risk_report(self, report_data: Dict[str, Any]):
        """Insert risk report."""
        columns = ', '.join(report_data.keys())
        placeholders = ', '.join(['?' for _ in report_data])
        query = f"INSERT INTO risk_reports ({columns}) VALUES ({placeholders})"
        self.execute_query(query, tuple(report_data.values()))

    def get_risk_reports(self, report_id: str) -> List[Dict[str, Any]]:
        """Retrieve risk report by ID."""
        query = "SELECT * FROM risk_reports WHERE report_id = ?"
        return self.execute_query(query, (report_id,))

    # --- Execution Operations ---

    def insert_execution(self, execution_data: Dict[str, Any]):
        """Insert execution record."""
        columns = ', '.join(execution_data.keys())
        placeholders = ', '.join(['?' for _ in execution_data])
        query = f"INSERT INTO executions ({columns}) VALUES ({placeholders})"
        self.execute_query(query, tuple(execution_data.values()))

    def get_executions(self, execution_id: str) -> List[Dict[str, Any]]:
        """Retrieve execution by ID."""
        query = "SELECT * FROM executions WHERE execution_id = ?"
        return self.execute_query(query, (execution_id,))

    # --- Memory Snapshot Operations ---

    def insert_memory_snapshot(self, snapshot_data: Dict[str, Any]):
        """Insert memory snapshot."""
        columns = ', '.join(snapshot_data.keys())
        placeholders = ', '.join(['?' for _ in snapshot_data])
        query = f"INSERT INTO memory_snapshots ({columns}) VALUES ({placeholders})"
        self.execute_query(query, tuple(snapshot_data.values()))

    def get_memory_snapshots(self, snapshot_id: str) -> List[Dict[str, Any]]:
        """Retrieve snapshot by ID."""
        query = "SELECT * FROM memory_snapshots WHERE snapshot_id = ?"
        return self.execute_query(query, (snapshot_id,))

    # --- Audit Log Operations (IMMUTABLE) ---

    def insert_audit_log(self, log_data: Dict[str, Any]):
        """Insert audit log entry."""
        columns = ', '.join(log_data.keys())
        placeholders = ', '.join(['?' for _ in log_data])
        query = f"INSERT INTO audit_logs ({columns}) VALUES ({placeholders})"
        self.execute_query(query, tuple(log_data.values()))

    def get_audit_logs(self, action: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve audit logs."""
        query = "SELECT * FROM audit_logs WHERE 1=1"
        params = []
        if action:
            query += " AND action = ?"
            params.append(action)
        query += " ORDER BY timestamp DESC"
        return self.execute_query(query, tuple(params))

    def update_audit_log(self, log_id: str, data: Dict[str, Any]):
        """Immutable policy: raise error on update."""
        raise PermissionError("Audit logs are immutable and cannot be updated.")

    def delete_audit_log(self, log_id: str):
        """Immutable policy: raise error on delete."""
        raise PermissionError("Audit logs are immutable and cannot be deleted.")
