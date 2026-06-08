"""
Scheduler - OMEGA+++ Quant AI System
Version: 1.0.0
Status: Implementation-Ready

Implements the task scheduler with:
- Priority queue management (heapq)
- Dependency resolution (topological sort)
- Agent-task assignment validation
- Ready task detection
"""

import heapq
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict, deque
from datetime import datetime, timezone

from .task_state_machine import Task, TaskStatus, TaskType


class DependencyError(Exception):
    """Raised when dependency resolution fails (circular dependencies, missing tasks)"""
    pass


class SchedulerError(Exception):
    """Raised when scheduler operations fail"""
    pass


class DependencyResolver:
    """
    Resolves task dependencies using topological sort
    
    Detects circular dependencies and ensures tasks are executed in valid order.
    """
    
    @staticmethod
    def resolve_dependencies(tasks: List[Task]) -> List[Task]:
        """
        Topologically sort tasks based on dependencies
        
        Args:
            tasks: List of tasks to sort
            
        Returns:
            List of tasks in execution order (dependencies first)
            
        Raises:
            DependencyError: If circular dependency detected or missing dependency
        """
        # Build task lookup
        task_map = {task.task_id: task for task in tasks}
        
        # Validate all dependencies exist
        for task in tasks:
            for dep_id in task.dependencies:
                if dep_id not in task_map:
                    raise DependencyError(
                        f"Task {task.task_id} depends on missing task {dep_id}"
                    )
        
        # Build adjacency list (task_id -> list of dependent task_ids)
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        
        # Initialize in_degree for all tasks
        for task in tasks:
            if task.task_id not in in_degree:
                in_degree[task.task_id] = 0
        
        # Build graph
        for task in tasks:
            for dep_id in task.dependencies:
                graph[dep_id].append(task.task_id)
                in_degree[task.task_id] += 1
        
        # Kahn's algorithm for topological sort
        queue = deque()
        
        # Start with tasks that have no dependencies
        for task in tasks:
            if in_degree[task.task_id] == 0:
                queue.append(task.task_id)
        
        sorted_task_ids = []
        
        while queue:
            task_id = queue.popleft()
            sorted_task_ids.append(task_id)
            
            # Reduce in-degree for dependent tasks
            for dependent_id in graph[task_id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)
        
        # Check for circular dependencies
        if len(sorted_task_ids) != len(tasks):
            # Find tasks involved in cycle
            remaining = [tid for tid in task_map.keys() if tid not in sorted_task_ids]
            raise DependencyError(
                f"Circular dependency detected involving tasks: {remaining}"
            )
        
        # Return tasks in sorted order
        return [task_map[tid] for tid in sorted_task_ids]
    
    @staticmethod
    def get_ready_tasks(tasks: List[Task], completed_task_ids: Set[str]) -> List[Task]:
        """
        Get tasks that are ready to execute (all dependencies completed)
        
        Args:
            tasks: List of tasks to check
            completed_task_ids: Set of task IDs that have completed
            
        Returns:
            List of tasks ready to execute
        """
        ready = []
        for task in tasks:
            # Skip terminal tasks
            if task.is_terminal():
                continue
            
            # Check if all dependencies are completed
            deps_satisfied = all(dep_id in completed_task_ids for dep_id in task.dependencies)
            
            if deps_satisfied:
                ready.append(task)
        
        return ready


class TaskScheduler:
    """
    Task scheduler with priority queue and dependency resolution
    
    Features:
    - Priority-based scheduling (higher priority = executed first)
    - Dependency resolution (topological sort)
    - Agent-task assignment validation
    - FIFO for same priority (using created_at as tiebreaker)
    """
    
    def __init__(self):
        """Initialize the scheduler"""
        # Priority queue: (priority, created_at, task_id, task)
        # Note: heapq is a min-heap, so we negate priority for max-heap behavior
        self._queue: List[Tuple[int, datetime, str, Task]] = []
        
        # Task lookup for fast access
        self._task_map: Dict[str, Task] = {}
        
        # Completed task IDs (for dependency checking)
        self._completed_task_ids: Set[str] = set()
        
        # Counter for heap stability (ensures FIFO for same priority)
        self._counter = 0
    
    def enqueue(self, task: Task) -> None:
        """
        Add a task to the scheduler queue
        
        Args:
            task: Task to enqueue
            
        Raises:
            SchedulerError: If task already exists or validation fails
        """
        # Validate task doesn't already exist
        if task.task_id in self._task_map:
            raise SchedulerError(f"Task {task.task_id} already in queue")
        
        # Validate agent-task assignment (already done in Task.__init__, but double-check)
        if task.owner_agent not in Task.AGENT_TASK_MATRIX:
            raise SchedulerError(f"Unknown agent: {task.owner_agent}")
        
        if task.task_type.value not in Task.AGENT_TASK_MATRIX[task.owner_agent]:
            raise SchedulerError(
                f"Agent {task.owner_agent} cannot execute task type {task.task_type.value}"
            )
        
        # Transition to QUEUED if still in CREATED state
        if task.status == TaskStatus.CREATED:
            task.transition_to(TaskStatus.QUEUED, "Task enqueued in scheduler")
        
        # Add to priority queue
        # Use negative priority for max-heap behavior (higher priority first)
        # Use created_at as tiebreaker (earlier tasks first)
        # Use counter for stable sort
        heap_entry = (
            -task.priority,  # Negate for max-heap
            task.created_at,
            self._counter,
            task
        )
        heapq.heappush(self._queue, heap_entry)
        self._task_map[task.task_id] = task
        self._counter += 1
    
    def dequeue(self) -> Optional[Task]:
        """
        Remove and return the highest priority task that is ready to execute
        
        Returns:
            Task with highest priority and satisfied dependencies, or None if queue empty
        """
        # Get all ready tasks
        ready_tasks = self.get_ready_tasks()
        
        if not ready_tasks:
            return None
        
        # Find the highest priority ready task
        # Since get_ready_tasks returns tasks in priority order, take the first one
        task = ready_tasks[0]
        
        # Remove from queue and task map
        self._remove_task(task.task_id)
        
        return task
    
    def _remove_task(self, task_id: str) -> None:
        """
        Remove a task from the queue
        
        Args:
            task_id: ID of task to remove
        """
        if task_id not in self._task_map:
            return
        
        # Remove from task map
        del self._task_map[task_id]
        
        # Rebuild heap without this task
        # Note: This is O(n) but simpler than lazy deletion
        self._queue = [
            entry for entry in self._queue
            if entry[3].task_id != task_id
        ]
        heapq.heapify(self._queue)
    
    def get_ready_tasks(self) -> List[Task]:
        """
        Get all tasks that are ready to execute (dependencies satisfied)
        
        Returns:
            List of tasks in priority order (highest priority first)
        """
        # Get all queued tasks
        queued_tasks = [entry[3] for entry in self._queue]
        
        # Filter by ready status
        ready = DependencyResolver.get_ready_tasks(queued_tasks, self._completed_task_ids)
        
        # Sort by priority (highest first), then by created_at (earliest first)
        ready.sort(key=lambda t: (-t.priority, t.created_at))
        
        return ready
    
    def resolve_dependencies(self, tasks: List[Task]) -> List[Task]:
        """
        Topologically sort tasks based on dependencies
        
        Args:
            tasks: List of tasks to sort
            
        Returns:
            List of tasks in execution order
            
        Raises:
            DependencyError: If circular dependency or missing task
        """
        return DependencyResolver.resolve_dependencies(tasks)
    
    def mark_completed(self, task_id: str) -> None:
        """
        Mark a task as completed (for dependency tracking)
        
        Args:
            task_id: ID of completed task
        """
        self._completed_task_ids.add(task_id)
    
    def mark_failed(self, task_id: str) -> None:
        """
        Mark a task as failed and remove from queue
        
        Args:
            task_id: ID of failed task
        """
        self._remove_task(task_id)
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get a task by ID
        
        Args:
            task_id: Task ID
            
        Returns:
            Task if found, None otherwise
        """
        return self._task_map.get(task_id)
    
    def get_all_tasks(self) -> List[Task]:
        """
        Get all tasks in the queue
        
        Returns:
            List of all tasks (unsorted)
        """
        return [entry[3] for entry in self._queue]
    
    def size(self) -> int:
        """
        Get the number of tasks in the queue
        
        Returns:
            Number of tasks
        """
        return len(self._queue)
    
    def is_empty(self) -> bool:
        """
        Check if the queue is empty
        
        Returns:
            True if empty, False otherwise
        """
        return len(self._queue) == 0
    
    def clear(self) -> None:
        """Clear all tasks from the queue"""
        self._queue.clear()
        self._task_map.clear()
        self._completed_task_ids.clear()
        self._counter = 0
