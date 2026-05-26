"""
Worker Lifecycle Management - OMEGA_QUANT Quant AI System
Version: 1.0.0
Status: Implementation-Ready

Implements the Worker lifecycle with:
- WorkerState enum (BOOT → LOAD_CONTEXT → EXECUTE → VERIFY → REPORT → UNLOAD)
- Worker class with full lifecycle management
- Error handling and retry logic
- Audit trail logging
- Integration with Task State Machine
"""

from enum import Enum
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timezone
from pathlib import Path
import json
import logging
import uuid


class WorkerState(Enum):
    """Worker state enum - defines all possible worker states."""
    
    BOOT = "BOOT"
    LOAD_CONTEXT = "LOAD_CONTEXT"
    EXECUTE = "EXECUTE"
    VERIFY = "VERIFY"
    REPORT = "REPORT"
    UNLOAD = "UNLOAD"
    ERROR = "ERROR"
    TERMINATED = "TERMINATED"


class WorkerError(Exception):
    """Raised when a worker operation fails."""
    pass


class Worker:
    """
    Worker class - represents a single worker executing a task.
    
    Lifecycle: BOOT → LOAD_CONTEXT → EXECUTE → VERIFY → REPORT → UNLOAD
    
    Error handling: On error, transitions to ERROR state and can retry.
    """
    
    def __init__(
        self,
        worker_id: str,
        role: str,
        max_retries: int = 3,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize worker.
        
        Args:
            worker_id: Unique worker identifier
            role: Worker role (e.g., "Backend Engineer")
            max_retries: Maximum number of retries on error
            logger: Optional logger instance
        """
        self.worker_id = worker_id
        self.role = role
        self.max_retries = max_retries
        self.logger = logger or logging.getLogger(f"Worker-{worker_id}")
        
        # State
        self.state = WorkerState.BOOT
        self.current_task = None
        self.context = None
        self.execution_result = None
        self.verification_passed = False
        self.report_path = None
        
        # Error tracking
        self.error_count = 0
        self.last_error = None
        
        # Timestamps
        self.boot_time = None
        self.start_time = None
        self.end_time = None
        
        # Audit trail
        self.audit_log_path = None
        self.state_transitions = []
    
    def set_audit_log(self, audit_log_path: Path) -> None:
        """Set the audit log file path.
        
        Args:
            audit_log_path: Path to audit log file
        """
        self.audit_log_path = Path(audit_log_path)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _log_transition(self, new_state: WorkerState, details: Optional[Dict[str, Any]] = None) -> None:
        """Log state transition to audit trail.
        
        Args:
            new_state: New worker state
            details: Optional additional details
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "worker_id": self.worker_id,
            "role": self.role,
            "from_state": self.state.value,
            "to_state": new_state.value,
            "task_id": self.current_task.task_id if self.current_task else None,
        }
        
        if details:
            entry.update(details)
        
        self.state_transitions.append(entry)
        
        # Write to audit log if configured
        if self.audit_log_path:
            with open(self.audit_log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        
        self.logger.info(f"State transition: {self.state.value} → {new_state.value}")
    
    def boot(self) -> bool:
        """Boot the worker.
        
        Returns:
            True if boot successful, False otherwise
        """
        try:
            self.boot_time = datetime.now(timezone.utc)
            self.logger.info(f"Worker {self.worker_id} booting...")
            
            # Verify state is BOOT
            if self.state != WorkerState.BOOT:
                raise WorkerError(f"Cannot boot from state {self.state.value}")
            
            self.logger.info(f"Worker {self.worker_id} boot complete")
            return True
        except Exception as e:
            self.logger.error(f"Boot failed: {e}")
            self.last_error = str(e)
            self.error_count += 1
            self.state = WorkerState.ERROR
            return False
    
    def load_context(
        self,
        task: Any,
        state_dir: Optional[Path] = None
    ) -> bool:
        """Load task context.
        
        Args:
            task: Task to load context for
            state_dir: State directory path
        
        Returns:
            True if context loaded successfully, False otherwise
        """
        try:
            if self.state != WorkerState.BOOT:
                raise WorkerError(f"Cannot load context from state {self.state.value}")
            
            self.current_task = task
            self.logger.info(f"Loading context for task {task.task_id}...")
            
            # Try to load context from file
            self.context = {}
            if state_dir:
                context_file = state_dir / "session" / f"context_{task.task_id}.json"
                if context_file.exists():
                    with open(context_file, "r") as f:
                        self.context = json.load(f)
                    self.logger.info(f"Loaded context from {context_file}")
            
            self._log_transition(WorkerState.LOAD_CONTEXT)
            self.state = WorkerState.LOAD_CONTEXT
            return True
        except Exception as e:
            self.logger.error(f"Load context failed: {e}")
            self.last_error = str(e)
            self.error_count += 1
            self._log_transition(WorkerState.ERROR, {"error": str(e)})
            self.state = WorkerState.ERROR
            return False
    
    def execute(
        self,
        execute_fn: Callable[[Any, Dict[str, Any]], Dict[str, Any]]
    ) -> bool:
        """Execute task.
        
        Args:
            execute_fn: Function to execute task. Signature: (task, context) -> result_dict
        
        Returns:
            True if execution successful, False otherwise
        """
        try:
            if self.state != WorkerState.LOAD_CONTEXT:
                raise WorkerError(f"Cannot execute from state {self.state.value}")
            
            self.start_time = datetime.now(timezone.utc)
            self.logger.info(f"Executing task {self.current_task.task_id}...")
            
            # Call execution function
            self.execution_result = execute_fn(self.current_task, self.context)
            
            self._log_transition(WorkerState.EXECUTE, {"result_status": self.execution_result.get("status")})
            self.state = WorkerState.EXECUTE
            return True
        except Exception as e:
            self.logger.error(f"Execution failed: {e}")
            self.last_error = str(e)
            self.error_count += 1
            self._log_transition(WorkerState.ERROR, {"error": str(e)})
            self.state = WorkerState.ERROR
            return False
    
    def verify(
        self,
        verify_fn: Callable[[Any, Dict[str, Any]], bool]
    ) -> bool:
        """Verify task execution results.
        
        Args:
            verify_fn: Function to verify results. Signature: (task, result) -> bool
        
        Returns:
            True if verification passed, False otherwise
        """
        try:
            if self.state != WorkerState.EXECUTE:
                raise WorkerError(f"Cannot verify from state {self.state.value}")
            
            self.logger.info(f"Verifying task {self.current_task.task_id}...")
            
            # Call verification function
            self.verification_passed = verify_fn(self.current_task, self.execution_result)
            
            if not self.verification_passed:
                raise WorkerError("Verification failed")
            
            self._log_transition(WorkerState.VERIFY, {"verification_passed": True})
            self.state = WorkerState.VERIFY
            return True
        except Exception as e:
            self.logger.error(f"Verification failed: {e}")
            self.last_error = str(e)
            self.error_count += 1
            self.verification_passed = False
            self._log_transition(WorkerState.ERROR, {"error": str(e)})
            self.state = WorkerState.ERROR
            return False
    
    def report(
        self,
        report_dir: Optional[Path] = None
    ) -> bool:
        """Generate audit report.
        
        Args:
            report_dir: Directory to save report
        
        Returns:
            True if report generated successfully, False otherwise
        """
        try:
            if self.state != WorkerState.VERIFY:
                raise WorkerError(f"Cannot report from state {self.state.value}")
            
            self.logger.info(f"Generating report for task {self.current_task.task_id}...")
            
            # Create report
            report = {
                "worker_id": self.worker_id,
                "role": self.role,
                "task_id": self.current_task.task_id,
                "task_type": self.current_task.task_type.value,
                "status": "SUCCESS" if self.verification_passed else "FAILED",
                "execution_result": self.execution_result,
                "verification_passed": self.verification_passed,
                "error_count": self.error_count,
                "last_error": self.last_error,
                "boot_time": self.boot_time.isoformat() if self.boot_time else None,
                "start_time": self.start_time.isoformat() if self.start_time else None,
                "end_time": datetime.now(timezone.utc).isoformat(),
                "state_transitions": self.state_transitions,
            }
            
            # Save report
            if report_dir:
                report_dir = Path(report_dir)
                report_dir.mkdir(parents=True, exist_ok=True)
                
                report_file = report_dir / f"report_{self.current_task.task_id}_{self.worker_id}.json"
                with open(report_file, "w") as f:
                    json.dump(report, f, indent=2)
                
                self.report_path = report_file
                self.logger.info(f"Report saved to {report_file}")
            
            self._log_transition(WorkerState.REPORT, {"report_path": str(self.report_path) if self.report_path else None})
            self.state = WorkerState.REPORT
            return True
        except Exception as e:
            self.logger.error(f"Report generation failed: {e}")
            self.last_error = str(e)
            self.error_count += 1
            self._log_transition(WorkerState.ERROR, {"error": str(e)})
            self.state = WorkerState.ERROR
            return False
    
    def unload(self) -> bool:
        """Unload worker and clean up resources.
        
        Returns:
            True if unload successful, False otherwise
        """
        try:
            if self.state not in [WorkerState.REPORT, WorkerState.ERROR]:
                raise WorkerError(f"Cannot unload from state {self.state.value}")
            
            self.logger.info(f"Unloading worker {self.worker_id}...")
            
            # Clean up resources
            self.current_task = None
            self.context = None
            self.execution_result = None
            
            self.end_time = datetime.now(timezone.utc)
            
            self._log_transition(WorkerState.UNLOAD)
            self.state = WorkerState.UNLOAD
            
            self.logger.info(f"Worker {self.worker_id} unload complete")
            return True
        except Exception as e:
            self.logger.error(f"Unload failed: {e}")
            self.last_error = str(e)
            self.error_count += 1
            self._log_transition(WorkerState.ERROR, {"error": str(e)})
            self.state = WorkerState.ERROR
            return False
    
    def retry(self) -> bool:
        """Retry task execution after error.
        
        Returns:
            True if retry initiated, False if max retries exceeded
        
        Raises:
            WorkerError: If called from a non-ERROR state
        """
        if self.state != WorkerState.ERROR:
            raise WorkerError(f"Cannot retry from state {self.state.value} (must be in ERROR state)")
            
        if not self.can_retry():
            self.logger.error(f"Max retries ({self.max_retries}) exceeded")
            return False
        
        self.logger.info(f"Retrying task {self.current_task.task_id} (attempt {self.error_count + 1}/{self.max_retries})")
        
        # Reset to LOAD_CONTEXT state to retry
        self._log_transition(WorkerState.LOAD_CONTEXT, {"retry_attempt": self.error_count})
        self.state = WorkerState.LOAD_CONTEXT
        self.execution_result = None
        self.verification_passed = False
        
        return True
    
    def can_retry(self) -> bool:
        """Check if worker can retry.
        
        Returns:
            True if retries remaining, False otherwise
        """
        return self.error_count < self.max_retries
    
    def get_status(self) -> Dict[str, Any]:
        """Get worker status.
        
        Returns:
            Dictionary with worker status information
        """
        return {
            "worker_id": self.worker_id,
            "role": self.role,
            "state": self.state.value,
            "task_id": self.current_task.task_id if self.current_task else None,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "verification_passed": self.verification_passed,
            "can_retry": self.can_retry(),
        }
