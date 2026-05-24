"""
Tests for Task State Machine (Institutional Grade)

Purpose:
    Verify full lifecycle task management with strict state transitions,
    dead-letter queue, event tracing, and dependency resolution.

Author: DevOps Engineer (Role 12)
Date: 2026-05-13
Version: 1.0.0
"""

import pytest
from omega.core.runtime.task_machine import (
    TaskStateMachine,
    Task,
    TaskState,
    TaskPriority,
    TaskEvent,
    DeadLetterQueue,
    get_task_machine,
)


class TestTaskState:
    """Test Task state transitions."""
    
    def test_task_creation(self):
        """Test task creation with default values."""
        machine = TaskStateMachine()
        task = machine.create_task(
            task_type="alpha_discovery",
            owner_agent="OpenCode",
            priority=TaskPriority.HIGH,
        )
        
        assert task.task_id is not None
        assert task.task_type == "alpha_discovery"
        assert task.owner_agent == "OpenCode"
        assert task.priority == TaskPriority.HIGH
        assert task.state == TaskState.CREATED
        assert task.dependencies == []
    
    def test_valid_state_transitions(self):
        """Test valid state transitions."""
        machine = TaskStateMachine()
        task = machine.create_task("test", "OpenCode")
        
        # CREATED -> QUEUED
        assert machine.transition(task.task_id, TaskState.QUEUED)
        assert task.state == TaskState.QUEUED
        
        # QUEUED -> PLANNED
        assert machine.transition(task.task_id, TaskState.PLANNED)
        assert task.state == TaskState.PLANNED
        
        # PLANNED -> DISPATCHED
        assert machine.transition(task.task_id, TaskState.DISPATCHED)
        assert task.state == TaskState.DISPATCHED
        
        # DISPATCHED -> RUNNING
        assert machine.transition(task.task_id, TaskState.RUNNING)
        assert task.state == TaskState.RUNNING
    
    def test_invalid_state_transitions(self):
        """Test invalid state transitions are rejected."""
        machine = TaskStateMachine()
        task = machine.create_task("test", "OpenCode")
        
        # CREATED -> RUNNING (invalid, should skip QUEUED)
        assert not machine.transition(task.task_id, TaskState.RUNNING)
        assert task.state == TaskState.CREATED
    
    def test_failure_path(self):
        """Test failure path transitions."""
        machine = TaskStateMachine()
        task = machine.create_task("test", "OpenCode")
        
        # CREATED -> FAILED
        assert machine.transition(task.task_id, TaskState.FAILED)
        assert task.state == TaskState.FAILED
        
        # FAILED -> RETRYING
        assert machine.transition(task.task_id, TaskState.RETRYING)
        assert task.state == TaskState.RETRYING
        
        # RETRYING -> QUEUED (retry)
        assert machine.transition(task.task_id, TaskState.QUEUED)
        assert task.state == TaskState.QUEUED


class TestDeadLetterQueue:
    """Test DeadLetterQueue for repeated failures."""
    
    def test_add_to_dlq(self):
        """Test adding task to DLQ after max retries."""
        dlq = DeadLetterQueue(max_retries=3)
        
        task = Task(
            task_id="test-123",
            retry_count=3,
            last_error="Test error",
        )
        
        dlq.add(task, "Test error")
        
        tasks = dlq.get_all()
        assert len(tasks) == 1
        assert tasks[0][0].task_id == "test-123"
    
    def test_dlq_clear(self):
        """Test clearing DLQ."""
        dlq = DeadLetterQueue()
        dlq.add(Task(task_id="test-123"), "Error")
        
        dlq.clear()
        assert len(dlq.get_all()) == 0


class TestEventTracing:
    """Test event tracing with causation_id and trace_id."""
    
    def test_event_has_tracing_fields(self):
        """Test event has all required tracing fields."""
        event = TaskEvent(
            event_type="TASK_CREATED",
            source="TaskStateMachine",
            target="task-123",
            correlation_id="corr-123",
            causation_id="caus-123",
            trace_id="trace-123",
            severity="INFO",
        )
        
        assert event.event_id is not None
        assert event.event_type == "TASK_CREATED"
        assert event.causation_id == "caus-123"
        assert event.trace_id == "trace-123"
        assert event.severity == "INFO"


class TestDependencyResolution:
    """Test task dependency resolution."""
    
    def test_dependencies_satisfied(self):
        """Test that satisfied dependencies allow transition."""
        machine = TaskStateMachine()
        
        # Create dependency task and transition to ARCHIVED via shortest path
        dep_task = machine.create_task("dep", "OpenCode")
        # Shortest path: CREATED -> QUEUED -> PLANNED -> DISPATCHED -> RUNNING -> VERIFYING -> REVIEWING -> RISK_CHECK -> APPROVED -> DEPLOYED -> MONITORING -> ARCHIVED
        transitions = [
            TaskState.QUEUED, TaskState.PLANNED, TaskState.DISPATCHED,
            TaskState.RUNNING, TaskState.VERIFYING, TaskState.REVIEWING,
            TaskState.RISK_CHECK, TaskState.APPROVED, TaskState.DEPLOYED,
            TaskState.MONITORING, TaskState.ARCHIVED
        ]
        for state in transitions:
            assert machine.transition(dep_task.task_id, state), f"Failed to transition to {state.value}"
        
        # Verify dep_task is ARCHIVED
        assert dep_task.state == TaskState.ARCHIVED
        
        # Create dependent task
        task = machine.create_task(
            "main",
            "OpenCode",
            dependencies=[dep_task.task_id],
        )
        
        assert machine._dependencies_satisfied(task.task_id)
    
    def test_dependencies_not_satisfied(self):
        """Test that unsatisfied dependencies block transition."""
        machine = TaskStateMachine()
        
        # Create dependency task (not archived)
        dep_task = machine.create_task("dep", "OpenCode")
        
        # Create dependent task
        task = machine.create_task(
            "main",
            "OpenCode",
            dependencies=[dep_task.task_id],
        )
        
        assert not machine._dependencies_satisfied(task.task_id)


class TestRetryWithBackoff:
    """Test retry logic with exponential backoff."""
    
    def test_retry_within_limit(self):
        """Test retry within max_retries limit."""
        machine = TaskStateMachine()
        task = machine.create_task("test", "OpenCode")
        
        # First failure
        will_retry = machine.handle_failure(task.task_id, "Error 1")
        assert will_retry
        assert task.retry_count == 1
        assert task.state == TaskState.RETRYING
    
    def test_retry_exceeds_limit(self):
        """Test task moved to DLQ after max retries."""
        machine = TaskStateMachine()
        task = machine.create_task("test", "OpenCode")
        
        # Exhaust retries (3 times)
        machine.handle_failure(task.task_id, "Error 1")
        machine.handle_failure(task.task_id, "Error 2")
        result = machine.handle_failure(task.task_id, "Error 3")
        
        assert task.retry_count == 3
        assert task.state == TaskState.FAILED
        assert result == False
        
        # Check DLQ
        dlq_tasks = machine.get_dlq_tasks()
        assert len(dlq_tasks) == 1
        assert dlq_tasks[0][0].task_id == task.task_id


class TestTaskStateMachineSingleton:
    """Test TaskStateMachine singleton pattern."""
    
    def test_singleton(self):
        """Test get_task_machine returns same instance."""
        tm1 = get_task_machine()
        tm2 = get_task_machine()
        
        assert tm1 is tm2
