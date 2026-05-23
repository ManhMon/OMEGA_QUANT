"""
Test Suite for Scheduler - OMEGA+++ Quant AI System
Version: 1.0.0

Tests:
- Priority queue ordering
- Dependency resolution (topological sort)
- Circular dependency detection
- Agent-task assignment validation
- Ready task detection
- FIFO for same priority
"""

import pytest
from datetime import datetime, timezone, timedelta

from omega.core.task_state_machine import Task, TaskStatus, TaskType
from omega.core.scheduler import (
    TaskScheduler,
    DependencyResolver,
    DependencyError,
    SchedulerError
)


class TestDependencyResolver:
    """Test dependency resolution and topological sort"""
    
    def test_resolve_no_dependencies(self):
        """Test resolving tasks with no dependencies"""
        tasks = [
            Task(TaskType.CODING, priority=5, owner_agent="OpenCode"),
            Task(TaskType.RESEARCH, priority=3, owner_agent="Ly"),
            Task(TaskType.AUDIT, priority=7, owner_agent="Codex"),
        ]
        
        resolved = DependencyResolver.resolve_dependencies(tasks)
        
        # All tasks should be present
        assert len(resolved) == 3
        assert set(t.task_id for t in resolved) == set(t.task_id for t in tasks)
    
    def test_resolve_linear_dependencies(self):
        """Test resolving tasks with linear dependencies (A -> B -> C)"""
        task_a = Task(TaskType.PLANNING, priority=5, owner_agent="Ly")
        task_b = Task(TaskType.CODING, priority=5, owner_agent="OpenCode", dependencies=[task_a.task_id])
        task_c = Task(TaskType.TEST, priority=5, owner_agent="OpenCode", dependencies=[task_b.task_id])
        
        tasks = [task_c, task_b, task_a]  # Intentionally out of order
        resolved = DependencyResolver.resolve_dependencies(tasks)
        
        # Should be ordered: A, B, C
        assert resolved[0].task_id == task_a.task_id
        assert resolved[1].task_id == task_b.task_id
        assert resolved[2].task_id == task_c.task_id
    
    def test_resolve_diamond_dependencies(self):
        """Test resolving diamond dependency pattern (A -> B,C -> D)"""
        task_a = Task(TaskType.PLANNING, priority=5, owner_agent="Ly")
        task_b = Task(TaskType.CODING, priority=5, owner_agent="OpenCode", dependencies=[task_a.task_id])
        task_c = Task(TaskType.RESEARCH, priority=5, owner_agent="Ly", dependencies=[task_a.task_id])
        task_d = Task(TaskType.TEST, priority=5, owner_agent="OpenCode", dependencies=[task_b.task_id, task_c.task_id])
        
        tasks = [task_d, task_c, task_b, task_a]
        resolved = DependencyResolver.resolve_dependencies(tasks)
        
        # A must be first, D must be last
        assert resolved[0].task_id == task_a.task_id
        assert resolved[3].task_id == task_d.task_id
        
        # B and C can be in any order (both depend only on A)
        middle_ids = {resolved[1].task_id, resolved[2].task_id}
        assert middle_ids == {task_b.task_id, task_c.task_id}
    
    def test_circular_dependency_detection(self):
        """Test detection of circular dependencies"""
        task_a = Task(TaskType.CODING, priority=5, owner_agent="OpenCode")
        task_b = Task(TaskType.TEST, priority=5, owner_agent="OpenCode", dependencies=[task_a.task_id])
        # Create circular dependency: A -> B -> A
        task_a.dependencies = [task_b.task_id]
        
        tasks = [task_a, task_b]
        
        with pytest.raises(DependencyError, match="Circular dependency"):
            DependencyResolver.resolve_dependencies(tasks)
    
    def test_missing_dependency_detection(self):
        """Test detection of missing dependencies"""
        task_a = Task(TaskType.CODING, priority=5, owner_agent="OpenCode", dependencies=["nonexistent-task-id"])
        
        with pytest.raises(DependencyError, match="missing task"):
            DependencyResolver.resolve_dependencies([task_a])
    
    def test_get_ready_tasks_no_dependencies(self):
        """Test getting ready tasks when none have dependencies"""
        tasks = [
            Task(TaskType.CODING, priority=5, owner_agent="OpenCode"),
            Task(TaskType.RESEARCH, priority=3, owner_agent="Ly"),
        ]
        
        ready = DependencyResolver.get_ready_tasks(tasks, set())
        
        # All tasks should be ready
        assert len(ready) == 2
    
    def test_get_ready_tasks_with_dependencies(self):
        """Test getting ready tasks with dependencies"""
        task_a = Task(TaskType.PLANNING, priority=5, owner_agent="Ly")
        task_b = Task(TaskType.CODING, priority=5, owner_agent="OpenCode", dependencies=[task_a.task_id])
        task_c = Task(TaskType.TEST, priority=5, owner_agent="OpenCode", dependencies=[task_b.task_id])
        
        tasks = [task_a, task_b, task_c]
        
        # No tasks completed yet
        ready = DependencyResolver.get_ready_tasks(tasks, set())
        assert len(ready) == 1
        assert ready[0].task_id == task_a.task_id
        
        # Task A completed
        ready = DependencyResolver.get_ready_tasks(tasks, {task_a.task_id})
        assert len(ready) == 2
        assert set(t.task_id for t in ready) == {task_a.task_id, task_b.task_id}
        
        # Tasks A and B completed
        ready = DependencyResolver.get_ready_tasks(tasks, {task_a.task_id, task_b.task_id})
        assert len(ready) == 3


class TestTaskScheduler:
    """Test task scheduler functionality"""
    
    def test_enqueue_single_task(self):
        """Test enqueueing a single task"""
        scheduler = TaskScheduler()
        task = Task(TaskType.CODING, priority=5, owner_agent="OpenCode")
        
        scheduler.enqueue(task)
        
        assert scheduler.size() == 1
        assert not scheduler.is_empty()
        assert task.status == TaskStatus.QUEUED
    
    def test_enqueue_multiple_tasks(self):
        """Test enqueueing multiple tasks"""
        scheduler = TaskScheduler()
        tasks = [
            Task(TaskType.CODING, priority=5, owner_agent="OpenCode"),
            Task(TaskType.RESEARCH, priority=3, owner_agent="Ly"),
            Task(TaskType.AUDIT, priority=7, owner_agent="Codex"),
        ]
        
        for task in tasks:
            scheduler.enqueue(task)
        
        assert scheduler.size() == 3
    
    def test_enqueue_duplicate_task(self):
        """Test that enqueueing duplicate task raises error"""
        scheduler = TaskScheduler()
        task = Task(TaskType.CODING, priority=5, owner_agent="OpenCode")
        
        scheduler.enqueue(task)
        
        with pytest.raises(SchedulerError, match="already in queue"):
            scheduler.enqueue(task)
    
    def test_enqueue_invalid_agent_task_assignment(self):
        """Test that invalid agent-task assignment raises error"""
        scheduler = TaskScheduler()
        
        # Codex cannot do coding tasks
        with pytest.raises(ValueError, match="cannot execute task type"):
            task = Task(TaskType.CODING, priority=5, owner_agent="Codex")
    
    def test_dequeue_priority_order(self):
        """Test that dequeue returns tasks in priority order"""
        scheduler = TaskScheduler()
        
        task_low = Task(TaskType.CODING, priority=3, owner_agent="OpenCode")
        task_med = Task(TaskType.RESEARCH, priority=5, owner_agent="Ly")
        task_high = Task(TaskType.AUDIT, priority=8, owner_agent="Codex")
        
        # Enqueue in random order
        scheduler.enqueue(task_med)
        scheduler.enqueue(task_low)
        scheduler.enqueue(task_high)
        
        # Dequeue should return highest priority first
        assert scheduler.dequeue().task_id == task_high.task_id
        assert scheduler.dequeue().task_id == task_med.task_id
        assert scheduler.dequeue().task_id == task_low.task_id
        assert scheduler.dequeue() is None
    
    def test_dequeue_fifo_for_same_priority(self):
        """Test that tasks with same priority are dequeued FIFO"""
        scheduler = TaskScheduler()
        
        # Create tasks with same priority but different creation times
        task1 = Task(TaskType.CODING, priority=5, owner_agent="OpenCode")
        task2 = Task(TaskType.TEST, priority=5, owner_agent="OpenCode")
        task3 = Task(TaskType.DEPLOYMENT, priority=5, owner_agent="OpenCode")
        
        scheduler.enqueue(task1)
        scheduler.enqueue(task2)
        scheduler.enqueue(task3)
        
        # Should dequeue in FIFO order
        assert scheduler.dequeue().task_id == task1.task_id
        assert scheduler.dequeue().task_id == task2.task_id
        assert scheduler.dequeue().task_id == task3.task_id
    
    def test_dequeue_respects_dependencies(self):
        """Test that dequeue only returns tasks with satisfied dependencies"""
        scheduler = TaskScheduler()
        
        task_a = Task(TaskType.PLANNING, priority=5, owner_agent="Ly")
        task_b = Task(TaskType.CODING, priority=10, owner_agent="OpenCode", dependencies=[task_a.task_id])
        
        scheduler.enqueue(task_a)
        scheduler.enqueue(task_b)
        
        # Even though task_b has higher priority, task_a should be dequeued first
        dequeued = scheduler.dequeue()
        assert dequeued.task_id == task_a.task_id
        
        # Mark task_a as completed
        scheduler.mark_completed(task_a.task_id)
        
        # Now task_b should be ready
        dequeued = scheduler.dequeue()
        assert dequeued.task_id == task_b.task_id
    
    def test_get_ready_tasks(self):
        """Test getting all ready tasks"""
        scheduler = TaskScheduler()
        
        task_a = Task(TaskType.PLANNING, priority=5, owner_agent="Ly")
        task_b = Task(TaskType.CODING, priority=8, owner_agent="OpenCode", dependencies=[task_a.task_id])
        task_c = Task(TaskType.RESEARCH, priority=3, owner_agent="Ly")
        
        scheduler.enqueue(task_a)
        scheduler.enqueue(task_b)
        scheduler.enqueue(task_c)
        
        # Only task_a and task_c should be ready
        ready = scheduler.get_ready_tasks()
        assert len(ready) == 2
        assert set(t.task_id for t in ready) == {task_a.task_id, task_c.task_id}
        
        # Should be ordered by priority (task_a=5, task_c=3)
        assert ready[0].task_id == task_a.task_id
        assert ready[1].task_id == task_c.task_id
    
    def test_mark_completed(self):
        """Test marking tasks as completed"""
        scheduler = TaskScheduler()
        
        task_a = Task(TaskType.PLANNING, priority=5, owner_agent="Ly")
        task_b = Task(TaskType.CODING, priority=5, owner_agent="OpenCode", dependencies=[task_a.task_id])
        
        scheduler.enqueue(task_a)
        scheduler.enqueue(task_b)
        
        # Initially only task_a is ready
        ready = scheduler.get_ready_tasks()
        assert len(ready) == 1
        
        # Mark task_a as completed
        scheduler.mark_completed(task_a.task_id)
        
        # Now both should be ready
        ready = scheduler.get_ready_tasks()
        assert len(ready) == 2
    
    def test_get_task(self):
        """Test retrieving task by ID"""
        scheduler = TaskScheduler()
        task = Task(TaskType.CODING, priority=5, owner_agent="OpenCode")
        
        scheduler.enqueue(task)
        
        retrieved = scheduler.get_task(task.task_id)
        assert retrieved is not None
        assert retrieved.task_id == task.task_id
        
        # Non-existent task
        assert scheduler.get_task("nonexistent") is None
    
    def test_clear(self):
        """Test clearing the scheduler"""
        scheduler = TaskScheduler()
        
        for i in range(1, 6):  # Priority must be 1-10
            task = Task(TaskType.CODING, priority=i, owner_agent="OpenCode")
            scheduler.enqueue(task)
        
        assert scheduler.size() == 5
        
        scheduler.clear()
        
        assert scheduler.size() == 0
        assert scheduler.is_empty()
    
    def test_resolve_dependencies_integration(self):
        """Test resolve_dependencies method on scheduler"""
        scheduler = TaskScheduler()
        
        task_a = Task(TaskType.PLANNING, priority=5, owner_agent="Ly")
        task_b = Task(TaskType.CODING, priority=5, owner_agent="OpenCode", dependencies=[task_a.task_id])
        task_c = Task(TaskType.TEST, priority=5, owner_agent="OpenCode", dependencies=[task_b.task_id])
        
        tasks = [task_c, task_b, task_a]
        resolved = scheduler.resolve_dependencies(tasks)
        
        # Should be in order: A, B, C
        assert resolved[0].task_id == task_a.task_id
        assert resolved[1].task_id == task_b.task_id
        assert resolved[2].task_id == task_c.task_id
    
    def test_complex_priority_and_dependency_scenario(self):
        """Test complex scenario with mixed priorities and dependencies"""
        scheduler = TaskScheduler()
        
        # Create a complex task graph:
        # task_a (priority=5) -> task_b (priority=10) -> task_d (priority=3)
        #                     -> task_c (priority=8)
        # task_e (priority=9, no dependencies)
        
        task_a = Task(TaskType.PLANNING, priority=5, owner_agent="Ly")
        task_b = Task(TaskType.CODING, priority=10, owner_agent="OpenCode", dependencies=[task_a.task_id])
        task_c = Task(TaskType.RESEARCH, priority=8, owner_agent="Ly", dependencies=[task_a.task_id])
        task_d = Task(TaskType.TEST, priority=3, owner_agent="OpenCode", dependencies=[task_b.task_id])
        task_e = Task(TaskType.AUDIT, priority=9, owner_agent="Codex")
        
        for task in [task_a, task_b, task_c, task_d, task_e]:
            scheduler.enqueue(task)
        
        # First dequeue: task_e (priority=9, no deps) or task_a (priority=5, no deps)
        # task_e should win due to higher priority
        first = scheduler.dequeue()
        assert first.task_id == task_e.task_id
        
        # Second dequeue: task_a (only one with no deps)
        second = scheduler.dequeue()
        assert second.task_id == task_a.task_id
        
        # Mark task_a as completed
        scheduler.mark_completed(task_a.task_id)
        
        # Third dequeue: task_b (priority=10) or task_c (priority=8)
        # task_b should win
        third = scheduler.dequeue()
        assert third.task_id == task_b.task_id
        
        # Mark task_b as completed
        scheduler.mark_completed(task_b.task_id)
        
        # Fourth dequeue: task_c (priority=8) or task_d (priority=3)
        # task_c should win
        fourth = scheduler.dequeue()
        assert fourth.task_id == task_c.task_id
        
        # Mark task_c as completed
        scheduler.mark_completed(task_c.task_id)
        
        # Last dequeue: task_d
        fifth = scheduler.dequeue()
        assert fifth.task_id == task_d.task_id
        
        # Queue should be empty
        assert scheduler.is_empty()
