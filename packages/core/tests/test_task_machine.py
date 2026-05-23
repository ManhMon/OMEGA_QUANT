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
    CancellationToken,
    TaskCancelledError,
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


class TestCancellationToken:
    """Test CancellationToken cooperative cancellation."""

    def test_initial_state_not_cancelled(self):
        """Token starts uncancelled."""
        token = CancellationToken()
        assert not token.is_cancelled
        assert token.reason == ""
        assert token.cancelled_at is None

    def test_cancel_sets_flag(self):
        """cancel() sets is_cancelled and stores reason."""
        token = CancellationToken()
        token.cancel(reason="test reason")
        assert token.is_cancelled
        assert token.reason == "test reason"
        assert token.cancelled_at is not None

    def test_cancel_is_idempotent(self):
        """Calling cancel() twice does not raise and keeps first reason."""
        token = CancellationToken()
        token.cancel(reason="first")
        token.cancel(reason="second")
        assert token.reason == "first"

    def test_check_raises_when_cancelled(self):
        """check() raises TaskCancelledError after cancel()."""
        token = CancellationToken()
        token.cancel(reason="stop now")
        with pytest.raises(TaskCancelledError):
            token.check()

    def test_check_does_not_raise_when_not_cancelled(self):
        """check() is a no-op when not cancelled."""
        token = CancellationToken()
        token.check()  # must not raise

    def test_wait_returns_true_when_cancelled(self):
        """wait() returns True immediately if already cancelled."""
        token = CancellationToken()
        token.cancel()
        assert token.wait(timeout=0.0) is True

    def test_wait_returns_false_on_timeout(self):
        """wait() returns False when timeout expires without cancellation."""
        token = CancellationToken()
        assert token.wait(timeout=0.01) is False


class TestCancelTask:
    """Test TaskStateMachine.cancel_task() safe termination."""

    def test_cancel_created_task(self):
        """cancel_task transitions CREATED -> CANCELLED."""
        machine = TaskStateMachine()
        task = machine.create_task("test", "OpenCode")
        assert machine.cancel_task(task.task_id, reason="no longer needed")
        assert task.state == TaskState.CANCELLED
        assert task.cancellation_token.is_cancelled

    def test_cancel_running_task(self):
        """cancel_task transitions RUNNING -> CANCELLED."""
        machine = TaskStateMachine()
        task = machine.create_task("test", "OpenCode")
        for state in [TaskState.QUEUED, TaskState.PLANNED, TaskState.DISPATCHED, TaskState.RUNNING]:
            machine.transition(task.task_id, state)
        assert machine.cancel_task(task.task_id, reason="timeout")
        assert task.state == TaskState.CANCELLED
        assert task.cancellation_token.is_cancelled
        assert task.cancellation_token.reason == "timeout"

    def test_cancel_archived_task_returns_false(self):
        """cancel_task returns False for terminal ARCHIVED state."""
        machine = TaskStateMachine()
        task = machine.create_task("test", "OpenCode")
        for state in [
            TaskState.QUEUED, TaskState.PLANNED, TaskState.DISPATCHED,
            TaskState.RUNNING, TaskState.VERIFYING, TaskState.REVIEWING,
            TaskState.RISK_CHECK, TaskState.APPROVED, TaskState.DEPLOYED,
            TaskState.MONITORING, TaskState.ARCHIVED,
        ]:
            machine.transition(task.task_id, state)
        assert not machine.cancel_task(task.task_id, reason="too late")
        assert task.state == TaskState.ARCHIVED  # unchanged

    def test_cancel_already_cancelled_task_returns_false(self):
        """cancel_task returns False when task is already CANCELLED."""
        machine = TaskStateMachine()
        task = machine.create_task("test", "OpenCode")
        machine.cancel_task(task.task_id, reason="first")
        assert not machine.cancel_task(task.task_id, reason="second")

    def test_cancel_nonexistent_task_returns_false(self):
        """cancel_task returns False for unknown task_id."""
        machine = TaskStateMachine()
        assert not machine.cancel_task("nonexistent-id")

    def test_cancel_emits_event(self):
        """cancel_task emits a TASK_CANCELLED event."""
        machine = TaskStateMachine()
        task = machine.create_task("test", "OpenCode")
        machine.cancel_task(task.task_id, reason="event check")
        events = machine.get_events()
        cancelled_events = [e for e in events if e.event_type == "TASK_CANCELLED"]
        assert len(cancelled_events) == 1
        assert cancelled_events[0].payload["reason"] == "event check"

    def test_cancel_does_not_corrupt_other_tasks(self):
        """Cancelling one task leaves sibling tasks untouched."""
        machine = TaskStateMachine()
        t1 = machine.create_task("task1", "OpenCode")
        t2 = machine.create_task("task2", "OpenCode")
        machine.cancel_task(t1.task_id, reason="cancel t1 only")
        assert t2.state == TaskState.CREATED
        assert not t2.cancellation_token.is_cancelled


class TestPreemptTask:
    """Test TaskStateMachine.preempt_task() for high-priority preemption."""

    def test_preempt_running_task(self):
        """preempt_task cancels a RUNNING task and sets preemption_requested."""
        machine = TaskStateMachine()
        task = machine.create_task("low_priority", "OpenCode", priority=TaskPriority.LOW)
        for state in [TaskState.QUEUED, TaskState.PLANNED, TaskState.DISPATCHED, TaskState.RUNNING]:
            machine.transition(task.task_id, state)

        assert machine.preempt_task(task.task_id, reason="CRITICAL task needs resources")
        assert task.state == TaskState.CANCELLED
        assert task.preemption_requested is True
        assert task.cancellation_token.is_cancelled

    def test_preempt_emits_preempted_event(self):
        """preempt_task emits both TASK_CANCELLED and TASK_PREEMPTED events."""
        machine = TaskStateMachine()
        task = machine.create_task("test", "OpenCode")
        for state in [TaskState.QUEUED, TaskState.PLANNED, TaskState.DISPATCHED, TaskState.RUNNING]:
            machine.transition(task.task_id, state)

        machine.preempt_task(task.task_id, reason="preemption test")
        event_types = [e.event_type for e in machine.get_events()]
        assert "TASK_CANCELLED" in event_types
        assert "TASK_PREEMPTED" in event_types

    def test_preempt_nonexistent_task_returns_false(self):
        """preempt_task returns False for unknown task_id."""
        machine = TaskStateMachine()
        assert not machine.preempt_task("ghost-id")

    def test_preempt_queued_task(self):
        """preempt_task also works on non-running cancellable states."""
        machine = TaskStateMachine()
        task = machine.create_task("test", "OpenCode")
        machine.transition(task.task_id, TaskState.QUEUED)
        assert machine.preempt_task(task.task_id, reason="queue flush")
        assert task.state == TaskState.CANCELLED

    def test_worker_cooperative_cancellation(self):
        """Simulate a worker polling check() and stopping cleanly."""
        import threading
        import time

        machine = TaskStateMachine()
        task = machine.create_task("long_job", "OpenCode")
        for state in [TaskState.QUEUED, TaskState.PLANNED, TaskState.DISPATCHED, TaskState.RUNNING]:
            machine.transition(task.task_id, state)

        results = []
        worker_started = threading.Event()

        def worker(token: CancellationToken):
            worker_started.set()
            for i in range(10):  # Reduced iterations significantly
                try:
                    token.check()
                except TaskCancelledError:
                    results.append(("cancelled", i))
                    return
                time.sleep(0.01)  # tiny yield
            results.append(("completed", 10))

        t = threading.Thread(target=worker, args=(task.cancellation_token,))
        t.start()
        worker_started.wait(timeout=1.0)
        machine.preempt_task(task.task_id, reason="preempt mid-loop")
        t.join(timeout=1.0) # Faster timeout

        assert len(results) == 1
        assert results[0][0] == "cancelled"
