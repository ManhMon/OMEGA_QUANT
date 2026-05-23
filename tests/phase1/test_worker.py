"""
Test suite for Worker Lifecycle Management

Tests cover:
- Worker state transitions (BOOT → LOAD_CONTEXT → EXECUTE → VERIFY → REPORT → UNLOAD)
- Error handling and recovery
- Context loading and cleanup
- Integration with Task State Machine
- Graceful degradation
- Audit trail logging

Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 2 (Worker Lifecycle)
"""

import pytest
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any

from omega.core.worker import Worker, WorkerState, WorkerError
from omega.core.task_state_machine import Task, TaskStatus, TaskType


class TestWorkerState:
    """Test WorkerState enum."""
    
    def test_worker_state_enum_values(self):
        """Test that all worker states are defined."""
        assert WorkerState.BOOT.value == "BOOT"
        assert WorkerState.LOAD_CONTEXT.value == "LOAD_CONTEXT"
        assert WorkerState.EXECUTE.value == "EXECUTE"
        assert WorkerState.VERIFY.value == "VERIFY"
        assert WorkerState.REPORT.value == "REPORT"
        assert WorkerState.UNLOAD.value == "UNLOAD"
        assert WorkerState.ERROR.value == "ERROR"
        assert WorkerState.TERMINATED.value == "TERMINATED"


class TestWorkerLifecycle:
    """Test Worker lifecycle transitions."""
    
    def test_worker_initialization(self):
        """Test worker initialization in BOOT state."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        
        assert worker.worker_id == "worker-001"
        assert worker.role == "Backend Engineer"
        assert worker.state == WorkerState.BOOT
        assert worker.current_task is None
        assert worker.error_count == 0
    
    def test_worker_boot(self):
        """Test worker boot process."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        
        result = worker.boot()
        
        assert result is True
        assert worker.state == WorkerState.BOOT
        assert worker.boot_time is not None
    
    def test_worker_load_context(self, workspace_tmp):
        """Test loading task context."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        worker.boot()
        
        # Create a test task
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        # Create context file
        context_dir = workspace_tmp / ".ly_state" / "session"
        context_dir.mkdir(parents=True, exist_ok=True)
        context_file = context_dir / f"context_{task.task_id}.json"
        context_file.write_text(json.dumps({
            "task_id": task.task_id,
            "files": ["worker.py", "checkpoint.py"],
            "dependencies": ["task_state_machine.py"]
        }))
        
        result = worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        
        assert result is True
        assert worker.state == WorkerState.LOAD_CONTEXT
        assert worker.current_task == task
        assert worker.context is not None
        assert "files" in worker.context
    
    def test_worker_load_context_missing_file(self, workspace_tmp):
        """Test loading context when context file doesn't exist."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        # Don't create context file - should use default context
        result = worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        
        assert result is True
        assert worker.state == WorkerState.LOAD_CONTEXT
        assert worker.context == {}  # Default empty context
    
    def test_worker_execute(self, workspace_tmp):
        """Test worker execution."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        
        # Mock execution function
        def mock_execute(task: Task, context: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "success", "output": "Task completed"}
        
        result = worker.execute(execute_fn=mock_execute)
        
        assert result is True
        assert worker.state == WorkerState.EXECUTE
        assert worker.execution_result is not None
        assert worker.execution_result["status"] == "success"
    
    def test_worker_execute_with_error(self, workspace_tmp):
        """Test worker execution with error."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        
        # Mock execution function that raises error
        def mock_execute_error(task: Task, context: Dict[str, Any]) -> Dict[str, Any]:
            raise ValueError("Execution failed")
        
        result = worker.execute(execute_fn=mock_execute_error)
        
        assert result is False
        assert worker.state == WorkerState.ERROR
        assert worker.error_count == 1
        assert worker.last_error is not None
    
    def test_worker_verify(self, workspace_tmp):
        """Test worker verification."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        worker.execute(execute_fn=lambda t, c: {"status": "success"})
        
        # Mock verification function
        def mock_verify(task: Task, result: Dict[str, Any]) -> bool:
            return result.get("status") == "success"
        
        result = worker.verify(verify_fn=mock_verify)
        
        assert result is True
        assert worker.state == WorkerState.VERIFY
        assert worker.verification_passed is True
    
    def test_worker_verify_failure(self, workspace_tmp):
        """Test worker verification failure."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        worker.execute(execute_fn=lambda t, c: {"status": "failed"})
        
        # Mock verification function that fails
        def mock_verify_fail(task: Task, result: Dict[str, Any]) -> bool:
            return False
        
        result = worker.verify(verify_fn=mock_verify_fail)
        
        assert result is False
        assert worker.state == WorkerState.ERROR
        assert worker.verification_passed is False
    
    def test_worker_report(self, workspace_tmp):
        """Test worker report generation."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        worker.execute(execute_fn=lambda t, c: {"status": "success"})
        worker.verify(verify_fn=lambda t, r: True)
        
        report_dir = workspace_tmp / ".ly_state" / "session" / "audit_reports"
        result = worker.report(report_dir=report_dir)
        
        assert result is True
        assert worker.state == WorkerState.REPORT
        assert worker.report_path is not None
        assert worker.report_path.exists()
    
    def test_worker_unload(self, workspace_tmp):
        """Test worker unload and cleanup."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        worker.execute(execute_fn=lambda t, c: {"status": "success"})
        worker.verify(verify_fn=lambda t, r: True)
        worker.report(report_dir=workspace_tmp / ".ly_state" / "session" / "audit_reports")
        
        result = worker.unload()
        
        assert result is True
        assert worker.state == WorkerState.UNLOAD
        assert worker.current_task is None
        assert worker.context is None
        assert worker.execution_result is None
    
    def test_worker_full_lifecycle(self, workspace_tmp):
        """Test complete worker lifecycle from BOOT to UNLOAD."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        
        # BOOT
        assert worker.boot() is True
        assert worker.state == WorkerState.BOOT
        
        # LOAD_CONTEXT
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        assert worker.load_context(task, state_dir=workspace_tmp / ".ly_state") is True
        assert worker.state == WorkerState.LOAD_CONTEXT
        
        # EXECUTE
        assert worker.execute(execute_fn=lambda t, c: {"status": "success"}) is True
        assert worker.state == WorkerState.EXECUTE
        
        # VERIFY
        assert worker.verify(verify_fn=lambda t, r: True) is True
        assert worker.state == WorkerState.VERIFY
        
        # REPORT
        assert worker.report(report_dir=workspace_tmp / ".ly_state" / "session" / "audit_reports") is True
        assert worker.state == WorkerState.REPORT
        
        # UNLOAD
        assert worker.unload() is True
        assert worker.state == WorkerState.UNLOAD


class TestWorkerErrorHandling:
    """Test worker error handling and recovery."""
    
    def test_worker_retry_after_error(self, workspace_tmp):
        """Test worker retry after execution error."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer", max_retries=3)
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        
        # First execution fails
        worker.execute(execute_fn=lambda t, c: (_ for _ in ()).throw(ValueError("Error")))
        assert worker.state == WorkerState.ERROR
        assert worker.error_count == 1
        
        # Retry should reset to EXECUTE state
        result = worker.retry()
        assert result is True
        assert worker.state == WorkerState.LOAD_CONTEXT  # Reset to reload context

    def test_worker_retry_only_from_error(self, workspace_tmp):
        """Test that retry is only allowed from ERROR state."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer", max_retries=3)
        worker.boot()

        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )

        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        assert worker.state == WorkerState.LOAD_CONTEXT

        with pytest.raises(WorkerError, match="Cannot retry from state"):
            worker.retry()
    
    def test_worker_max_retries_exceeded(self, workspace_tmp):
        """Test worker behavior when max retries exceeded."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer", max_retries=2)
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        
        # Fail 3 times
        for i in range(3):
            worker.execute(execute_fn=lambda t, c: (_ for _ in ()).throw(ValueError("Error")))
            if i < 2:
                worker.retry()
        
        assert worker.error_count == 3
        assert worker.can_retry() is False
    
    def test_worker_graceful_degradation(self, workspace_tmp):
        """Test worker graceful degradation on non-critical errors."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        
        # Execute with partial success
        def partial_execute(task: Task, context: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "status": "partial_success",
                "completed": ["file1.py"],
                "failed": ["file2.py"],
                "warnings": ["Non-critical error in file2.py"]
            }
        
        result = worker.execute(execute_fn=partial_execute)
        
        assert result is True
        assert worker.execution_result["status"] == "partial_success"
        assert "warnings" in worker.execution_result


class TestWorkerAuditTrail:
    """Test worker audit trail logging."""
    
    def test_worker_logs_all_transitions(self, workspace_tmp):
        """Test that worker logs all state transitions."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        
        audit_log = workspace_tmp / ".ly_state" / "session" / "audit_log.jsonl"
        audit_log.parent.mkdir(parents=True, exist_ok=True)
        
        worker.set_audit_log(audit_log)
        
        # Run through lifecycle
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        worker.execute(execute_fn=lambda t, c: {"status": "success"})
        worker.verify(verify_fn=lambda t, r: True)
        worker.report(report_dir=workspace_tmp / ".ly_state" / "session" / "audit_reports")
        worker.unload()
        
        # Read audit log
        assert audit_log.exists()
        log_lines = audit_log.read_text().strip().split("\n")
        assert len(log_lines) >= 5  # At least 5 transitions (LOAD_CONTEXT, EXECUTE, VERIFY, REPORT, UNLOAD)
        
        # Verify log entries
        for line in log_lines:
            entry = json.loads(line)
            assert "timestamp" in entry
            assert "worker_id" in entry
            assert "to_state" in entry
            assert entry["worker_id"] == "worker-001"
    
    def test_worker_logs_errors(self, workspace_tmp):
        """Test that worker logs errors to audit trail."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        
        audit_log = workspace_tmp / ".ly_state" / "session" / "audit_log.jsonl"
        audit_log.parent.mkdir(parents=True, exist_ok=True)
        worker.set_audit_log(audit_log)
        
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        worker.execute(execute_fn=lambda t, c: (_ for _ in ()).throw(ValueError("Test error")))
        
        # Read audit log
        log_lines = audit_log.read_text().strip().split("\n")
        error_entries = [json.loads(line) for line in log_lines if json.loads(line).get("to_state") == "ERROR"]
        
        assert len(error_entries) >= 1
        assert "error" in error_entries[0]
        assert "Test error" in error_entries[0]["error"]


class TestWorkerIntegration:
    """Test worker integration with Task State Machine."""
    
    def test_worker_updates_task_status(self, workspace_tmp):
        """Test that worker updates task status during lifecycle."""
        worker = Worker(worker_id="worker-001", role="Backend Engineer")
        worker.boot()
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            task_id="task-001"
        )
        
        # Initial status
        assert task.status == TaskStatus.CREATED
        
        # Load context
        worker.load_context(task, state_dir=workspace_tmp / ".ly_state")
        task.transition_to(TaskStatus.QUEUED)
        task.transition_to(TaskStatus.PLANNED)
        task.transition_to(TaskStatus.DISPATCHED)
        task.transition_to(TaskStatus.RUNNING)
        assert task.status == TaskStatus.RUNNING
        
        # Execute
        worker.execute(execute_fn=lambda t, c: {"status": "success"})
        
        # Verify
        worker.verify(verify_fn=lambda t, r: True)
        task.transition_to(TaskStatus.VERIFYING)
        assert task.status == TaskStatus.VERIFYING
        
        # Report
        worker.report(report_dir=workspace_tmp / ".ly_state" / "session" / "audit_reports")
        task.transition_to(TaskStatus.REVIEWING)
        assert task.status == TaskStatus.REVIEWING
