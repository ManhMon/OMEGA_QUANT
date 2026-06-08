"""
Task State Machine - OMEGA+++ Quant AI System
Version: 1.0.0
Status: Implementation-Ready

Implements the unified task state machine with:
- TaskStatus enum (all states from architecture)
- TaskType enum (all task types)
- Task class (all mandatory fields)
- State transition validation (prevents illegal transitions)
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid


class TaskStatus(Enum):
    """Task status enum - defines all possible task states"""
    
    # Success path
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    PLANNED = "PLANNED"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VERIFYING = "VERIFYING"
    REVIEWING = "REVIEWING"
    RISK_CHECK = "RISK_CHECK"
    APPROVED = "APPROVED"
    DEPLOYED = "DEPLOYED"
    MONITORING = "MONITORING"
    ARCHIVED = "ARCHIVED"
    
    # Failure path
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    FALLBACK = "FALLBACK"
    ESCALATED = "ESCALATED"
    ABORTED = "ABORTED"


class TaskType(Enum):
    """Task type enum - defines all possible task types"""
    
    PLANNING = "planning"
    ARCHITECTURE = "architecture"
    CODING = "coding"
    RESEARCH = "research"
    FEATURE_ENGINEERING = "feature_engineering"
    MODEL_TRAINING = "model_training"
    BACKTESTING = "backtesting"
    RISK_REVIEW = "risk_review"
    SECURITY_REVIEW = "security_review"
    AUDIT = "audit"
    TEST = "test"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    RECOVERY = "recovery"
    EVOLUTION = "evolution"


class TaskTransitionError(Exception):
    """Raised when an illegal state transition is attempted"""
    pass


class Task:
    """
    Task class - represents a single unit of work in the system
    
    Implements all mandatory fields from OMEGA_SYSTEM_ARCHITECTURE_V1.md
    and enforces state transition rules.
    """
    
    # Valid state transitions (from_state -> [to_states])
    VALID_TRANSITIONS = {
        TaskStatus.CREATED: [TaskStatus.QUEUED, TaskStatus.ABORTED],
        TaskStatus.QUEUED: [TaskStatus.PLANNED, TaskStatus.ABORTED],
        TaskStatus.PLANNED: [TaskStatus.DISPATCHED, TaskStatus.ABORTED],
        TaskStatus.DISPATCHED: [TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.ABORTED],
        TaskStatus.RUNNING: [TaskStatus.WAITING, TaskStatus.VERIFYING, TaskStatus.FAILED, TaskStatus.ABORTED],
        TaskStatus.WAITING: [TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.ABORTED],
        TaskStatus.VERIFYING: [TaskStatus.REVIEWING, TaskStatus.FAILED, TaskStatus.ABORTED],
        TaskStatus.REVIEWING: [TaskStatus.RISK_CHECK, TaskStatus.FAILED, TaskStatus.ESCALATED, TaskStatus.ABORTED],
        TaskStatus.RISK_CHECK: [TaskStatus.APPROVED, TaskStatus.FAILED, TaskStatus.ESCALATED, TaskStatus.ABORTED],
        TaskStatus.APPROVED: [TaskStatus.DEPLOYED, TaskStatus.ABORTED],
        TaskStatus.DEPLOYED: [TaskStatus.MONITORING, TaskStatus.FAILED, TaskStatus.ABORTED],
        TaskStatus.MONITORING: [TaskStatus.ARCHIVED, TaskStatus.FAILED, TaskStatus.ABORTED],
        TaskStatus.ARCHIVED: [],  # Terminal state
        TaskStatus.FAILED: [TaskStatus.RETRYING, TaskStatus.ESCALATED, TaskStatus.ABORTED],
        TaskStatus.RETRYING: [TaskStatus.RUNNING, TaskStatus.FALLBACK, TaskStatus.ESCALATED, TaskStatus.ABORTED],
        TaskStatus.FALLBACK: [TaskStatus.RUNNING, TaskStatus.ESCALATED, TaskStatus.ABORTED],
        TaskStatus.ESCALATED: [TaskStatus.RUNNING, TaskStatus.ABORTED],
        TaskStatus.ABORTED: [],  # Terminal state
    }
    
    # Agent task-type matrix (machine-enforced)
    AGENT_TASK_MATRIX = {
        "Ly": ["planning", "architecture", "research", "risk_review", "monitoring", "recovery"],
        "OpenCode": ["coding", "feature_engineering", "model_training", "backtesting", "test", 
                     "deployment", "evolution", "planning", "architecture", "research", "monitoring", "recovery"],
        "Codex": ["audit", "security_review", "risk_review", "research"],
        "SOV": ["planning", "architecture", "research"]
    }
    
    def __init__(
        self,
        task_type: TaskType,
        priority: int,
        owner_agent: str,
        required_context: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
        retry_policy: Optional[Dict[str, Any]] = None,
        timeout_policy: Optional[Dict[str, Any]] = None,
        resource_budget: Optional[Dict[str, Any]] = None,
        parent_task_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ):
        """
        Initialize a new Task
        
        Args:
            task_type: Type of task (from TaskType enum)
            priority: Priority level (1-10, 10 = critical)
            owner_agent: Agent responsible for task (Ly, OpenCode, Codex, SOV)
            required_context: Inputs, data, models needed
            constraints: Time, token, resource limits
            dependencies: Task IDs that must complete first
            retry_policy: Max retries, backoff strategy
            timeout_policy: Max duration, soft/hard limits
            resource_budget: CPU, memory, GPU limits
            parent_task_id: Parent task if hierarchical
            task_id: Unique identifier (auto-generated if not provided)
        """
        # Validate priority
        if not 1 <= priority <= 10:
            raise ValueError(f"Priority must be between 1 and 10, got {priority}")
        
        # Validate agent-task assignment
        if owner_agent not in self.AGENT_TASK_MATRIX:
            raise ValueError(f"Unknown agent: {owner_agent}")
        if task_type.value not in self.AGENT_TASK_MATRIX[owner_agent]:
            raise ValueError(
                f"Agent {owner_agent} cannot execute task type {task_type.value}. "
                f"Allowed types: {self.AGENT_TASK_MATRIX[owner_agent]}"
            )
        
        # Mandatory fields
        self.task_id = task_id or str(uuid.uuid4())
        self.parent_task_id = parent_task_id
        self.task_type = task_type
        self.priority = priority
        self._status = TaskStatus.CREATED  # Protected attribute
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.owner_agent = owner_agent
        self.required_context = required_context or {}
        self.constraints = constraints or {}
        self.dependencies = dependencies or []
        self.retry_policy = retry_policy or {"max_retries": 3, "backoff_ms": 1000}
        self.timeout_policy = timeout_policy or {"max_duration_ms": 300000, "soft_limit_ms": 240000}
        self.resource_budget = resource_budget or {"cpu_cores": 1, "memory_mb": 512}
        self.artifact_refs = []
        self.audit_ref = None
        
        # State transition history
        self._transition_history = [
            {
                "from_status": None,
                "to_status": TaskStatus.CREATED,
                "timestamp": self.created_at,
                "reason": "Task created"
            }
        ]
    
    @property
    def status(self) -> TaskStatus:
        """Get current task status (read-only)"""
        return self._status
    
    def transition_to(self, new_status: TaskStatus, reason: str = "") -> None:
        """
        Transition task to a new status
        
        Args:
            new_status: Target status
            reason: Reason for transition (for audit trail)
        
        Raises:
            TaskTransitionError: If transition is not allowed
        """
        # Check if transition is valid
        valid_next_states = self.VALID_TRANSITIONS.get(self._status, [])
        if new_status not in valid_next_states:
            raise TaskTransitionError(
                f"Invalid transition from {self._status.value} to {new_status.value}. "
                f"Valid transitions: {[s.value for s in valid_next_states]}"
            )
        
        # Record transition
        old_status = self._status
        self._status = new_status
        self.updated_at = datetime.now(timezone.utc)
        
        self._transition_history.append({
            "from_status": old_status,
            "to_status": new_status,
            "timestamp": self.updated_at,
            "reason": reason or f"Transition to {new_status.value}"
        })
    
    def get_transition_history(self) -> List[Dict[str, Any]]:
        """Get the full transition history for this task"""
        return self._transition_history.copy()
    
    def is_terminal(self) -> bool:
        """Check if task is in a terminal state (ARCHIVED or ABORTED)"""
        return self.status in [TaskStatus.ARCHIVED, TaskStatus.ABORTED]
    
    def can_transition_to(self, new_status: TaskStatus) -> bool:
        """Check if transition to new_status is valid"""
        valid_next_states = self.VALID_TRANSITIONS.get(self._status, [])
        return new_status in valid_next_states
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary (for serialization)"""
        return {
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "task_type": self.task_type.value,
            "priority": self.priority,
            "status": self._status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "owner_agent": self.owner_agent,
            "required_context": self.required_context,
            "constraints": self.constraints,
            "dependencies": self.dependencies,
            "retry_policy": self.retry_policy,
            "timeout_policy": self.timeout_policy,
            "resource_budget": self.resource_budget,
            "artifact_refs": self.artifact_refs,
            "audit_ref": self.audit_ref,
            "transition_history": [
                {
                    "from_status": h["from_status"].value if h["from_status"] else None,
                    "to_status": h["to_status"].value if isinstance(h["to_status"], TaskStatus) else h["to_status"],
                    "timestamp": h["timestamp"].isoformat() if isinstance(h["timestamp"], datetime) else h["timestamp"],
                    "reason": h["reason"]
                }
                for h in self._transition_history
            ]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Create task from dictionary (for deserialization)"""
        task = cls(
            task_type=TaskType(data["task_type"]),
            priority=data["priority"],
            owner_agent=data["owner_agent"],
            required_context=data.get("required_context"),
            constraints=data.get("constraints"),
            dependencies=data.get("dependencies"),
            retry_policy=data.get("retry_policy"),
            timeout_policy=data.get("timeout_policy"),
            resource_budget=data.get("resource_budget"),
            parent_task_id=data.get("parent_task_id"),
            task_id=data["task_id"]
        )
        
        # Restore state (bypass property setter)
        task._status = TaskStatus(data["status"])
        task.created_at = datetime.fromisoformat(data["created_at"])
        task.updated_at = datetime.fromisoformat(data["updated_at"])
        task.artifact_refs = data.get("artifact_refs", [])
        task.audit_ref = data.get("audit_ref")
        
        # Restore transition history with proper deserialization
        transition_history = data.get("transition_history", [])
        task._transition_history = [
            {
                "from_status": TaskStatus(h["from_status"]) if h["from_status"] else None,
                "to_status": TaskStatus(h["to_status"]) if isinstance(h["to_status"], str) else h["to_status"],
                "timestamp": datetime.fromisoformat(h["timestamp"]) if isinstance(h["timestamp"], str) else h["timestamp"],
                "reason": h["reason"]
            }
            for h in transition_history
        ]
        
        return task
    
    def __repr__(self) -> str:
        return (
            f"Task(task_id={self.task_id}, "
            f"type={self.task_type.value}, "
            f"status={self._status.value}, "
            f"priority={self.priority}, "
            f"owner={self.owner_agent})"
        )
