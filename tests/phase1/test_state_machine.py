"""
Test Suite for Task State Machine - OMEGA+++ Quant AI System
Version: 1.0.0

Tests:
- TaskStatus enum
- TaskType enum
- Task class initialization
- State transition validation
- Agent-task assignment validation
- Serialization/deserialization
- Transition history tracking
"""

import pytest
from datetime import datetime
from omega.core.task_state_machine import (
    TaskStatus,
    TaskType,
    Task,
    TaskTransitionError
)


class TestTaskStatus:
    """Test TaskStatus enum"""
    
    def test_all_success_states_exist(self):
        """Verify all success path states exist"""
        expected_states = [
            "CREATED", "QUEUED", "PLANNED", "DISPATCHED", "RUNNING",
            "WAITING", "VERIFYING", "REVIEWING", "RISK_CHECK", "APPROVED",
            "DEPLOYED", "MONITORING", "ARCHIVED"
        ]
        for state in expected_states:
            assert hasattr(TaskStatus, state)
            assert TaskStatus[state].value == state
    
    def test_all_failure_states_exist(self):
        """Verify all failure path states exist"""
        expected_states = ["FAILED", "RETRYING", "FALLBACK", "ESCALATED", "ABORTED"]
        for state in expected_states:
            assert hasattr(TaskStatus, state)
            assert TaskStatus[state].value == state


class TestTaskType:
    """Test TaskType enum"""
    
    def test_all_task_types_exist(self):
        """Verify all task types exist"""
        expected_types = [
            "planning", "architecture", "coding", "research",
            "feature_engineering", "model_training", "backtesting",
            "risk_review", "security_review", "audit", "test",
            "deployment", "monitoring", "recovery", "evolution"
        ]
        for task_type in expected_types:
            # Find the enum member with this value
            found = False
            for member in TaskType:
                if member.value == task_type:
                    found = True
                    break
            assert found, f"TaskType.{task_type} not found"


class TestTaskInitialization:
    """Test Task class initialization"""
    
    def test_create_basic_task(self):
        """Test creating a basic task with minimal parameters"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        assert task.task_id is not None
        assert task.task_type == TaskType.CODING
        assert task.priority == 5
        assert task.owner_agent == "OpenCode"
        assert task.status == TaskStatus.CREATED
        assert isinstance(task.created_at, datetime)
        assert isinstance(task.updated_at, datetime)
    
    def test_create_task_with_all_fields(self):
        """Test creating a task with all optional fields"""
        task = Task(
            task_type=TaskType.MODEL_TRAINING,
            priority=8,
            owner_agent="OpenCode",
            required_context={"model": "xgboost", "data": "daily_prices"},
            constraints={"max_time_ms": 60000},
            dependencies=["task-123", "task-456"],
            retry_policy={"max_retries": 5, "backoff_ms": 2000},
            timeout_policy={"max_duration_ms": 600000, "soft_limit_ms": 480000},
            resource_budget={"cpu_cores": 4, "memory_mb": 2048},
            parent_task_id="parent-task-789"
        )
        
        assert task.required_context == {"model": "xgboost", "data": "daily_prices"}
        assert task.constraints == {"max_time_ms": 60000}
        assert task.dependencies == ["task-123", "task-456"]
        assert task.retry_policy["max_retries"] == 5
        assert task.timeout_policy["max_duration_ms"] == 600000
        assert task.resource_budget["cpu_cores"] == 4
        assert task.parent_task_id == "parent-task-789"
    
    def test_invalid_priority_raises_error(self):
        """Test that invalid priority raises ValueError"""
        with pytest.raises(ValueError, match="Priority must be between 1 and 10"):
            Task(
                task_type=TaskType.CODING,
                priority=11,
                owner_agent="OpenCode"
            )
        
        with pytest.raises(ValueError, match="Priority must be between 1 and 10"):
            Task(
                task_type=TaskType.CODING,
                priority=0,
                owner_agent="OpenCode"
            )
    
    def test_invalid_agent_raises_error(self):
        """Test that invalid agent raises ValueError"""
        with pytest.raises(ValueError, match="Unknown agent"):
            Task(
                task_type=TaskType.CODING,
                priority=5,
                owner_agent="InvalidAgent"
            )
    
    def test_agent_task_matrix_enforcement(self):
        """Test that agent-task assignment is enforced"""
        # Valid: OpenCode can do coding
        task1 = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        assert task1.owner_agent == "OpenCode"
        
        # Valid: Codex can do audit
        task2 = Task(
            task_type=TaskType.AUDIT,
            priority=5,
            owner_agent="Codex"
        )
        assert task2.owner_agent == "Codex"
        
        # Invalid: Codex cannot do coding (READ-ONLY)
        with pytest.raises(ValueError, match="Agent Codex cannot execute task type coding"):
            Task(
                task_type=TaskType.CODING,
                priority=5,
                owner_agent="Codex"
            )
        
        # Invalid: Ly cannot do coding (READ-ONLY)
        with pytest.raises(ValueError, match="Agent Ly cannot execute task type coding"):
            Task(
                task_type=TaskType.CODING,
                priority=5,
                owner_agent="Ly"
            )
        
        # Valid: Ly can do planning
        task3 = Task(
            task_type=TaskType.PLANNING,
            priority=5,
            owner_agent="Ly"
        )
        assert task3.owner_agent == "Ly"


class TestStateTransitions:
    """Test state transition validation"""
    
    def test_valid_success_path_transitions(self):
        """Test valid transitions along success path"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        # Success path: CREATED -> QUEUED -> PLANNED -> DISPATCHED -> RUNNING
        assert task.status == TaskStatus.CREATED
        
        task.transition_to(TaskStatus.QUEUED, "Added to queue")
        assert task.status == TaskStatus.QUEUED
        
        task.transition_to(TaskStatus.PLANNED, "Planning complete")
        assert task.status == TaskStatus.PLANNED
        
        task.transition_to(TaskStatus.DISPATCHED, "Assigned to worker")
        assert task.status == TaskStatus.DISPATCHED
        
        task.transition_to(TaskStatus.RUNNING, "Execution started")
        assert task.status == TaskStatus.RUNNING
        
        task.transition_to(TaskStatus.VERIFYING, "Running tests")
        assert task.status == TaskStatus.VERIFYING
        
        task.transition_to(TaskStatus.REVIEWING, "Codex audit")
        assert task.status == TaskStatus.REVIEWING
        
        task.transition_to(TaskStatus.RISK_CHECK, "Risk validation")
        assert task.status == TaskStatus.RISK_CHECK
        
        task.transition_to(TaskStatus.APPROVED, "All gates passed")
        assert task.status == TaskStatus.APPROVED
        
        task.transition_to(TaskStatus.DEPLOYED, "Deployed to production")
        assert task.status == TaskStatus.DEPLOYED
        
        task.transition_to(TaskStatus.MONITORING, "Monitoring live")
        assert task.status == TaskStatus.MONITORING
        
        task.transition_to(TaskStatus.ARCHIVED, "Task complete")
        assert task.status == TaskStatus.ARCHIVED
    
    def test_valid_failure_path_transitions(self):
        """Test valid transitions along failure path"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        # Move to RUNNING
        task.transition_to(TaskStatus.QUEUED)
        task.transition_to(TaskStatus.PLANNED)
        task.transition_to(TaskStatus.DISPATCHED)
        task.transition_to(TaskStatus.RUNNING)
        
        # Failure path: RUNNING -> FAILED -> RETRYING -> RUNNING
        task.transition_to(TaskStatus.FAILED, "Test failed")
        assert task.status == TaskStatus.FAILED
        
        task.transition_to(TaskStatus.RETRYING, "Retry attempt 1")
        assert task.status == TaskStatus.RETRYING
        
        task.transition_to(TaskStatus.RUNNING, "Retry execution")
        assert task.status == TaskStatus.RUNNING
    
    def test_invalid_transition_raises_error(self):
        """Test that invalid transitions raise TaskTransitionError"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        # Cannot go directly from CREATED to RUNNING
        with pytest.raises(TaskTransitionError, match="Invalid transition from CREATED to RUNNING"):
            task.transition_to(TaskStatus.RUNNING)
        
        # Cannot go from CREATED to ARCHIVED
        with pytest.raises(TaskTransitionError, match="Invalid transition from CREATED to ARCHIVED"):
            task.transition_to(TaskStatus.ARCHIVED)
    
    def test_terminal_states_cannot_transition(self):
        """Test that terminal states (ARCHIVED, ABORTED) cannot transition"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        # Move to ARCHIVED
        task.transition_to(TaskStatus.QUEUED)
        task.transition_to(TaskStatus.PLANNED)
        task.transition_to(TaskStatus.DISPATCHED)
        task.transition_to(TaskStatus.RUNNING)
        task.transition_to(TaskStatus.VERIFYING)
        task.transition_to(TaskStatus.REVIEWING)
        task.transition_to(TaskStatus.RISK_CHECK)
        task.transition_to(TaskStatus.APPROVED)
        task.transition_to(TaskStatus.DEPLOYED)
        task.transition_to(TaskStatus.MONITORING)
        task.transition_to(TaskStatus.ARCHIVED)
        
        # Cannot transition from ARCHIVED
        with pytest.raises(TaskTransitionError, match="Invalid transition from ARCHIVED"):
            task.transition_to(TaskStatus.RUNNING)
    
    def test_can_abort_from_any_non_terminal_state(self):
        """Test that ABORTED can be reached from any non-terminal state"""
        states_to_test = [
            TaskStatus.CREATED, TaskStatus.QUEUED, TaskStatus.PLANNED,
            TaskStatus.DISPATCHED, TaskStatus.RUNNING, TaskStatus.WAITING,
            TaskStatus.VERIFYING, TaskStatus.REVIEWING, TaskStatus.RISK_CHECK,
            TaskStatus.APPROVED, TaskStatus.DEPLOYED, TaskStatus.MONITORING,
            TaskStatus.FAILED, TaskStatus.RETRYING, TaskStatus.FALLBACK,
            TaskStatus.ESCALATED
        ]
        
        for status in states_to_test:
            task = Task(
                task_type=TaskType.CODING,
                priority=5,
                owner_agent="OpenCode"
            )
            # Manually set status for testing (bypass property)
            task._status = status
            
            # Should be able to abort
            assert task.can_transition_to(TaskStatus.ABORTED)
    
    def test_waiting_state_transitions(self):
        """Test WAITING state transitions (for external dependencies)"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        # Move to RUNNING
        task.transition_to(TaskStatus.QUEUED)
        task.transition_to(TaskStatus.PLANNED)
        task.transition_to(TaskStatus.DISPATCHED)
        task.transition_to(TaskStatus.RUNNING)
        
        # Can transition to WAITING
        task.transition_to(TaskStatus.WAITING, "Waiting for external data")
        assert task.status == TaskStatus.WAITING
        
        # Can resume from WAITING
        task.transition_to(TaskStatus.RUNNING, "Data available, resuming")
        assert task.status == TaskStatus.RUNNING


class TestTransitionHistory:
    """Test transition history tracking"""
    
    def test_transition_history_recorded(self):
        """Test that all transitions are recorded in history"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        history = task.get_transition_history()
        assert len(history) == 1
        assert history[0]["from_status"] is None
        assert history[0]["to_status"] == TaskStatus.CREATED
        
        task.transition_to(TaskStatus.QUEUED, "Added to queue")
        history = task.get_transition_history()
        assert len(history) == 2
        assert history[1]["from_status"] == TaskStatus.CREATED
        assert history[1]["to_status"] == TaskStatus.QUEUED
        assert history[1]["reason"] == "Added to queue"
        
        task.transition_to(TaskStatus.PLANNED, "Planning complete")
        history = task.get_transition_history()
        assert len(history) == 3
        assert history[2]["from_status"] == TaskStatus.QUEUED
        assert history[2]["to_status"] == TaskStatus.PLANNED
    
    def test_transition_history_includes_timestamps(self):
        """Test that transition history includes timestamps"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        task.transition_to(TaskStatus.QUEUED)
        history = task.get_transition_history()
        
        for entry in history:
            assert "timestamp" in entry
            assert isinstance(entry["timestamp"], datetime)


class TestTaskSerialization:
    """Test task serialization and deserialization"""
    
    def test_to_dict(self):
        """Test converting task to dictionary"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            required_context={"key": "value"}
        )
        
        task_dict = task.to_dict()
        
        assert task_dict["task_id"] == task.task_id
        assert task_dict["task_type"] == "coding"
        assert task_dict["priority"] == 5
        assert task_dict["status"] == "CREATED"
        assert task_dict["owner_agent"] == "OpenCode"
        assert task_dict["required_context"] == {"key": "value"}
    
    def test_from_dict(self):
        """Test creating task from dictionary"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        task.transition_to(TaskStatus.QUEUED)
        task.transition_to(TaskStatus.PLANNED)
        
        task_dict = task.to_dict()
        restored_task = Task.from_dict(task_dict)
        
        assert restored_task.task_id == task.task_id
        assert restored_task.task_type == task.task_type
        assert restored_task.priority == task.priority
        assert restored_task.status == task.status
        assert restored_task.owner_agent == task.owner_agent
        assert len(restored_task.get_transition_history()) == len(task.get_transition_history())
    
    def test_round_trip_serialization(self):
        """Test that serialization and deserialization preserve all data"""
        original_task = Task(
            task_type=TaskType.MODEL_TRAINING,
            priority=8,
            owner_agent="OpenCode",
            required_context={"model": "xgboost"},
            dependencies=["task-123"]
        )
        
        original_task.transition_to(TaskStatus.QUEUED)
        original_task.transition_to(TaskStatus.PLANNED)
        
        # Serialize and deserialize
        task_dict = original_task.to_dict()
        restored_task = Task.from_dict(task_dict)
        
        # Verify all fields match
        assert restored_task.task_id == original_task.task_id
        assert restored_task.task_type == original_task.task_type
        assert restored_task.priority == original_task.priority
        assert restored_task.status == original_task.status
        assert restored_task.owner_agent == original_task.owner_agent
        assert restored_task.required_context == original_task.required_context
        assert restored_task.dependencies == original_task.dependencies
    
    def test_json_serialization(self):
        """Test JSON serialization with enum values as strings (P1 fix)"""
        import json
        
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode",
            required_context={"key": "value"}
        )
        
        task.transition_to(TaskStatus.QUEUED, "Added to queue")
        task.transition_to(TaskStatus.PLANNED, "Planning complete")
        
        # Convert to dict and serialize to JSON
        task_dict = task.to_dict()
        json_str = json.dumps(task_dict)
        
        # Verify JSON is valid
        assert json_str is not None
        
        # Deserialize from JSON
        restored_dict = json.loads(json_str)
        restored_task = Task.from_dict(restored_dict)
        
        # Verify all fields match
        assert restored_task.task_id == task.task_id
        assert restored_task.task_type == task.task_type
        assert restored_task.priority == task.priority
        assert restored_task.status == task.status
        assert restored_task.owner_agent == task.owner_agent
        
        # Verify transition history is properly restored
        history = restored_task.get_transition_history()
        assert len(history) == 3
        assert history[0]["to_status"] == TaskStatus.CREATED
        assert history[1]["from_status"] == TaskStatus.CREATED
        assert history[1]["to_status"] == TaskStatus.QUEUED
        assert history[1]["reason"] == "Added to queue"
        assert history[2]["from_status"] == TaskStatus.QUEUED
        assert history[2]["to_status"] == TaskStatus.PLANNED
        assert history[2]["reason"] == "Planning complete"
    
    def test_status_protection(self):
        """Test that status attribute is protected (P2 fix)"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        # Status should be readable
        assert task.status == TaskStatus.CREATED
        
        # Direct assignment should fail (property is read-only)
        with pytest.raises(AttributeError):
            task.status = TaskStatus.QUEUED
        
        # Only transition_to() should work
        task.transition_to(TaskStatus.QUEUED)
        assert task.status == TaskStatus.QUEUED


class TestTaskUtilityMethods:
    """Test utility methods"""
    
    def test_is_terminal(self):
        """Test is_terminal() method"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        assert not task.is_terminal()
        
        task.transition_to(TaskStatus.QUEUED)
        assert not task.is_terminal()
        
        task.transition_to(TaskStatus.ABORTED)
        assert task.is_terminal()
    
    def test_can_transition_to(self):
        """Test can_transition_to() method"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        assert task.can_transition_to(TaskStatus.QUEUED)
        assert task.can_transition_to(TaskStatus.ABORTED)
        assert not task.can_transition_to(TaskStatus.RUNNING)
        assert not task.can_transition_to(TaskStatus.ARCHIVED)
    
    def test_repr(self):
        """Test __repr__ method"""
        task = Task(
            task_type=TaskType.CODING,
            priority=5,
            owner_agent="OpenCode"
        )
        
        repr_str = repr(task)
        assert "Task(" in repr_str
        assert "type=coding" in repr_str
        assert "status=CREATED" in repr_str
        assert "priority=5" in repr_str
        assert "owner=OpenCode" in repr_str


class TestAgentTaskMatrix:
    """Test agent-task assignment matrix enforcement"""
    
    def test_ly_allowed_tasks(self):
        """Test Ly can only execute allowed task types"""
        allowed = ["planning", "architecture", "research", "risk_review", "monitoring", "recovery"]
        
        for task_type_str in allowed:
            task_type = TaskType(task_type_str)
            task = Task(
                task_type=task_type,
                priority=5,
                owner_agent="Ly"
            )
            assert task.owner_agent == "Ly"
    
    def test_opencode_allowed_tasks(self):
        """Test OpenCode can execute all implementation tasks"""
        allowed = [
            "coding", "feature_engineering", "model_training", "backtesting",
            "test", "deployment", "evolution", "planning", "architecture",
            "research", "monitoring", "recovery"
        ]
        
        for task_type_str in allowed:
            task_type = TaskType(task_type_str)
            task = Task(
                task_type=task_type,
                priority=5,
                owner_agent="OpenCode"
            )
            assert task.owner_agent == "OpenCode"
    
    def test_codex_allowed_tasks(self):
        """Test Codex can only execute audit/review tasks (READ-ONLY)"""
        allowed = ["audit", "security_review", "risk_review", "research"]
        
        for task_type_str in allowed:
            task_type = TaskType(task_type_str)
            task = Task(
                task_type=task_type,
                priority=5,
                owner_agent="Codex"
            )
            assert task.owner_agent == "Codex"
        
        # Codex cannot do implementation tasks
        with pytest.raises(ValueError):
            Task(
                task_type=TaskType.CODING,
                priority=5,
                owner_agent="Codex"
            )
    
    def test_sov_allowed_tasks(self):
        """Test SOV can only execute reasoning tasks"""
        allowed = ["planning", "architecture", "research"]
        
        for task_type_str in allowed:
            task_type = TaskType(task_type_str)
            task = Task(
                task_type=task_type,
                priority=5,
                owner_agent="SOV"
            )
            assert task.owner_agent == "SOV"
