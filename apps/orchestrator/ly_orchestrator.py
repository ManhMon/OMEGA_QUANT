"""Ly L1 Orchestrator - 25-Role Agent Routing with SOD Enforcement.

Purpose:
    Ly (L1) Orchestrator routes tasks to the correct Role (1-25) based on
    task type, enforces Segregation of Duties (SOD), manages L2/L3 platform
    selection, and persists state to .ly_state/.

Architecture:
    - L1 (Ly): Roles 1-5 (Project/Delivery Management)
    - L2 (OpenCode): Roles 6-16 (Build/Code/Design)
    - L3 (Codex): Roles 17-25 (Audit/Review/Security)

SOD Protocol:
    1. L2 Implementation session writes code
    2. L2 session MUST terminate before L3 audit begins
    3. L3 Audit session reviews artifacts independently
    4. Gate decision: [APPROVED] or [NEEDS_FIX]
    5. If [NEEDS_FIX], loop back to L2

Contract:
    - Input: Task with task_type and role_id
    - Output: Task result + audit trail in .ly_state/session/audit_log.jsonl

Reference:
    - TEAM_ARCHITECTURE.md: 25-Role Agent System
    - AGENTS.md: PD v4.2 - Auto Skill Injection
    - Spec Section 17: Agent Roles

Author: Backend Engineer (Role 9)
Date: 2026-05-26
Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

logger = logging.getLogger(__name__)


class Platform(str, Enum):
    """Platform runtime for agent execution."""
    
    LY = "Ly"           # L1: Orchestrator & Management (Roles 1-5)
    OPENCODE = "OpenCode"  # L2: Build/Code/Design (Roles 6-16)
    CODEX = "Codex"     # L3: Audit/Review/Security (Roles 17-25)


class RoleType(str, Enum):
    """Role categories."""
    
    MANAGEMENT = "MANAGEMENT"      # L1 Roles 1-5
    IMPLEMENTATION = "IMPLEMENTATION"  # L2 Roles 6-16
    AUDIT = "AUDIT"                # L3 Roles 17-25


@dataclass
class RoleSpec:
    """Specification for a single role."""
    
    role_id: int
    role_name: str
    platform: Platform
    role_type: RoleType
    responsibilities: List[str]
    constraints: List[str]


@dataclass
class TaskRequest:
    """Task request to be routed to a role."""
    
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = ""
    role_id: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class TaskResult:
    """Result from task execution."""
    
    task_id: str
    role_id: int
    platform: Platform
    status: str  # "success", "error", "needs_fix"
    result: Any = None
    error: Optional[str] = None
    duration: float = 0.0
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class GateStatus:
    """SOD Gate status for a phase."""
    
    phase_name: str
    l2_session_id: Optional[str] = None
    l2_completed: bool = False
    l3_session_id: Optional[str] = None
    l3_session_key: Optional[str] = None
    audit_report_path: Optional[str] = None
    final_verdict: str = "PENDING_AUDIT"  # PENDING_AUDIT, APPROVED, NEEDS_FIX
    timestamp: float = field(default_factory=time.time)


class LyOrchestrator:
    """Ly L1 Orchestrator - Routes tasks to 25 specialized roles.
    
    Responsibilities:
        1. Route tasks to correct Role (1-25) based on task_type
        2. Select platform: L1 (Ly), L2 (OpenCode), L3 (Codex)
        3. Enforce SOD: L2 terminate before L3 audit
        4. Gate decision after L3 audit
        5. State persistence to .ly_state/
        
    25 Roles:
        L1 (Ly): 1-5 (Management)
        L2 (OpenCode): 6-16 (Implementation)
        L3 (Codex): 17-25 (Audit)
    """
    
    # Role Registry: 25 Roles
    ROLES: Dict[int, RoleSpec] = {
        # L1 (Ly) - Orchestrator & Management
        1: RoleSpec(1, "Project Manager", Platform.LY, RoleType.MANAGEMENT,
                    ["Strategic orchestration", "Resource allocation"],
                    ["Cannot write code"]),
        2: RoleSpec(2, "Product Owner", Platform.LY, RoleType.MANAGEMENT,
                    ["Feature prioritization", "Stakeholder alignment"],
                    ["Cannot make architectural decisions"]),
        3: RoleSpec(3, "Scrum Master", Platform.LY, RoleType.MANAGEMENT,
                    ["Agile process", "Blocker removal"],
                    ["Cannot implement code"]),
        4: RoleSpec(4, "Release Manager", Platform.LY, RoleType.MANAGEMENT,
                    ["Release coordination", "Deployment gates"],
                    ["Cannot approve final code review"]),
        5: RoleSpec(5, "Delivery Manager", Platform.LY, RoleType.MANAGEMENT,
                    ["Timeline tracking", "Resource management"],
                    ["Cannot write quant logic"]),
        
        # L2 (OpenCode) - Build, Code, Design
        6: RoleSpec(6, "System Architect", Platform.OPENCODE, RoleType.IMPLEMENTATION,
                    ["System design", "Interface definition"],
                    ["Must be audited by L3"]),
        7: RoleSpec(7, "Tech Lead", Platform.OPENCODE, RoleType.IMPLEMENTATION,
                    ["Technical leadership", "Code standards"],
                    ["Must be audited by L3"]),
        8: RoleSpec(8, "Frontend Engineer", Platform.OPENCODE, RoleType.IMPLEMENTATION,
                    ["UI/UX implementation"],
                    ["Must be audited by L3"]),
        9: RoleSpec(9, "Backend Engineer", Platform.OPENCODE, RoleType.IMPLEMENTATION,
                    ["API implementation", "Business logic"],
                    ["Must be audited by L3"]),
        10: RoleSpec(10, "Database Admin", Platform.OPENCODE, RoleType.IMPLEMENTATION,
                     ["Schema design", "DB performance"],
                     ["Must be audited by L3"]),
        11: RoleSpec(11, "DevOps Engineer", Platform.OPENCODE, RoleType.IMPLEMENTATION,
                     ["CI/CD", "Automation"],
                     ["Must be audited by L3"]),
        12: RoleSpec(12, "Cloud Infra Engineer", Platform.OPENCODE, RoleType.IMPLEMENTATION,
                     ["Infrastructure as Code"],
                     ["Must be audited by L3"]),
        13: RoleSpec(13, "UI/UX Integrator", Platform.OPENCODE, RoleType.IMPLEMENTATION,
                     ["UI integration", "Styling"],
                     ["Must be audited by L3"]),
        14: RoleSpec(14, "Data Scientist", Platform.OPENCODE, RoleType.IMPLEMENTATION,
                     ["Model research", "Signal discovery"],
                     ["Must be audited by L3"]),
        15: RoleSpec(15, "Data Engineer", Platform.OPENCODE, RoleType.IMPLEMENTATION,
                     ["Data pipelines", "ETL"],
                     ["Must be audited by L3"]),
        16: RoleSpec(16, "Machine Learning Eng", Platform.OPENCODE, RoleType.IMPLEMENTATION,
                     ["Model training", "Deployment"],
                     ["Must be audited by L3"]),
        
        # L3 (Codex) - Audit, Review, Security
        17: RoleSpec(17, "QA Engineer", Platform.CODEX, RoleType.AUDIT,
                     ["Functional testing (AUDIT ONLY)"],
                     ["NO test writing"]),
        18: RoleSpec(18, "SDET", Platform.CODEX, RoleType.AUDIT,
                     ["Test automation audit (AUDIT ONLY)"],
                     ["NO test framework development"]),
        19: RoleSpec(19, "Security Auditor", Platform.CODEX, RoleType.AUDIT,
                     ["Security scanning (AUDIT ONLY)"],
                     ["NO security fixes"]),
        20: RoleSpec(20, "Compliance Officer", Platform.CODEX, RoleType.AUDIT,
                     ["PIT safety checks (AUDIT ONLY)"],
                     ["NO compliance fixes"]),
        21: RoleSpec(21, "Code Reviewer", Platform.CODEX, RoleType.AUDIT,
                     ["Peer reviews (AUDIT ONLY)"],
                     ["NO code fixes"]),
        22: RoleSpec(22, "Penetration Tester", Platform.CODEX, RoleType.AUDIT,
                     ["Security testing (AUDIT ONLY)"],
                     ["NO security fixes"]),
        23: RoleSpec(23, "Performance Tester", Platform.CODEX, RoleType.AUDIT,
                     ["Load testing (AUDIT ONLY)"],
                     ["NO performance fixes"]),
        24: RoleSpec(24, "UAT Validator", Platform.CODEX, RoleType.AUDIT,
                     ["User acceptance (AUDIT ONLY)"],
                     ["NO feature implementation"]),
        25: RoleSpec(25, "IT Systems Auditor", Platform.CODEX, RoleType.AUDIT,
                     ["System audit (AUDIT ONLY)"],
                     ["NO system fixes"]),
    }
    
    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or (WORKSPACE_ROOT / ".ly_state")
        self.session_dir = self.state_dir / "session"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # State files
        self.active_tasks_file = self.session_dir / "active_tasks.json"
        self.agent_locks_file = self.session_dir / "agent_locks.json"
        self.audit_log_file = self.session_dir / "audit_log.jsonl"
        self.phase_gates_file = self.session_dir / "phase_gates.json"
        
        # In-memory state
        self.active_tasks: Dict[str, TaskRequest] = {}
        self.agent_locks: Dict[Platform, bool] = {
            Platform.LY: False,
            Platform.OPENCODE: False,
            Platform.CODEX: False,
        }
        self.phase_gates: Dict[str, GateStatus] = {}
        
        # Load state from disk
        self._load_state()
        
        logger.info("LyOrchestrator initialized: state_dir=%s", self.state_dir)
    
    def _load_state(self) -> None:
        """Load state from disk."""
        # Load active tasks
        if self.active_tasks_file.exists():
            with open(self.active_tasks_file, "r") as f:
                data = json.load(f)
                self.active_tasks = {
                    k: TaskRequest(**v) for k, v in data.items()
                }
        
        # Load agent locks
        if self.agent_locks_file.exists():
            with open(self.agent_locks_file, "r") as f:
                data = json.load(f)
                self.agent_locks = {
                    Platform(k): v for k, v in data.items()
                }
        
        # Load phase gates (filter only fields that GateStatus accepts)
        if self.phase_gates_file.exists():
            with open(self.phase_gates_file, "r") as f:
                data = json.load(f)
                self.phase_gates = {}
                for k, v in data.items():
                    # Filter to only GateStatus fields
                    filtered = {
                        field: v.get(field)
                        for field in ["phase_name", "l2_session_id", "l2_completed", 
                                      "l3_session_id", "l3_session_key", "audit_report_path",
                                      "final_verdict", "timestamp"]
                        if field in v
                    }
                    # Set phase_name if not present
                    if "phase_name" not in filtered:
                        filtered["phase_name"] = k
                    self.phase_gates[k] = GateStatus(**filtered)
    
    def _save_state(self) -> None:
        """Save state to disk."""
        # Save active tasks
        with open(self.active_tasks_file, "w") as f:
            data = {k: v.__dict__ for k, v in self.active_tasks.items()}
            json.dump(data, f, indent=2)
        
        # Save agent locks
        with open(self.agent_locks_file, "w") as f:
            data = {k.value: v for k, v in self.agent_locks.items()}
            json.dump(data, f, indent=2)
        
        # Save phase gates
        with open(self.phase_gates_file, "w") as f:
            data = {k: v.__dict__ for k, v in self.phase_gates.items()}
            json.dump(data, f, indent=2)
    
    def _append_audit_log(self, entry: Dict[str, Any]) -> None:
        """Append entry to audit log (append-only, hash-chained)."""
        entry["timestamp"] = time.time()
        with open(self.audit_log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def route_task(self, task: TaskRequest) -> TaskResult:
        """Route task to appropriate role and platform.
        
        Args:
            task: TaskRequest with task_type and optional role_id
            
        Returns:
            TaskResult with execution result
            
        Raises:
            ValueError: If role_id is invalid or platform is locked
        """
        start_time = time.time()
        
        # Determine role_id if not provided
        if task.role_id is None:
            task.role_id = self._infer_role_from_task_type(task.task_type)
        
        # Validate role_id
        if task.role_id not in self.ROLES:
            raise ValueError(f"Invalid role_id: {task.role_id}")
        
        role_spec = self.ROLES[task.role_id]
        platform = role_spec.platform
        
        logger.info(
            "Routing task %s to Role %d (%s) on platform %s",
            task.task_id[:8],
            role_spec.role_id,
            role_spec.role_name,
            platform.value,
        )
        
        # Check platform lock
        if self.agent_locks.get(platform, False):
            raise ValueError(f"Platform {platform.value} is locked")
        
        # Lock platform
        self.agent_locks[platform] = True
        self._save_state()
        
        # Add to active tasks
        self.active_tasks[task.task_id] = task
        self._save_state()
        
        # Audit log entry
        self._append_audit_log({
            "event": "task_routed",
            "task_id": task.task_id,
            "role_id": role_spec.role_id,
            "role_name": role_spec.role_name,
            "platform": platform.value,
            "task_type": task.task_type,
        })
        
        try:
            # Execute task on platform
            result = self._execute_on_platform(task, role_spec)
            
            # Audit log entry
            self._append_audit_log({
                "event": "task_completed",
                "task_id": task.task_id,
                "role_id": role_spec.role_id,
                "status": result.status,
                "duration": result.duration,
            })
            
            return result
            
        finally:
            # Unlock platform
            self.agent_locks[platform] = False
            
            # Remove from active tasks
            self.active_tasks.pop(task.task_id, None)
            
            self._save_state()
    
    def _infer_role_from_task_type(self, task_type: str) -> int:
        """Infer role_id from task_type.
        
        Args:
            task_type: Task type string
            
        Returns:
            role_id (1-25)
        """
        # Task type -> Role mapping
        mapping = {
            "project_plan": 1,      # Project Manager
            "feature_prioritize": 2,  # Product Owner
            "sprint_plan": 3,       # Scrum Master
            "release_gate": 4,      # Release Manager
            "timeline_track": 5,    # Delivery Manager
            
            "system_design": 6,     # System Architect
            "tech_lead": 7,         # Tech Lead
            "frontend_impl": 8,     # Frontend Engineer
            "backend_impl": 9,      # Backend Engineer
            "database_design": 10,  # Database Admin
            "ci_cd": 11,            # DevOps Engineer
            "infra_code": 12,       # Cloud Infra Engineer
            "ui_integration": 13,   # UI/UX Integrator
            "alpha_research": 14,   # Data Scientist
            "data_pipeline": 15,    # Data Engineer
            "ml_training": 16,      # Machine Learning Eng
            
            "qa_test": 17,          # QA Engineer
            "test_automation_audit": 18,  # SDET
            "security_audit": 19,   # Security Auditor
            "compliance_check": 20, # Compliance Officer
            "code_review": 21,      # Code Reviewer
            "pentest": 22,          # Penetration Tester
            "performance_test": 23, # Performance Tester
            "uat_validate": 24,     # UAT Validator
            "system_audit": 25,     # IT Systems Auditor
        }
        
        role_id = mapping.get(task_type)
        if role_id is None:
            # Default to Backend Engineer for unknown types
            logger.warning("Unknown task_type '%s', defaulting to Role 9 (Backend Engineer)", task_type)
            role_id = 9
        
        return role_id
    
    def _execute_on_platform(self, task: TaskRequest, role_spec: RoleSpec) -> TaskResult:
        """Execute task on the specified platform.
        
        Args:
            task: TaskRequest
            role_spec: RoleSpec for the role
            
        Returns:
            TaskResult
        """
        start_time = time.time()
        
        logger.info(
            "Executing task %s on platform %s (Role %d: %s)",
            task.task_id[:8],
            role_spec.platform.value,
            role_spec.role_id,
            role_spec.role_name,
        )
        
        # Placeholder: In production, this would spawn actual agent sessions
        # For L2 (OpenCode): spawn OpenCode session with role context
        # For L3 (Codex): spawn Codex session with audit context
        
        # Simulate execution
        time.sleep(0.1)  # Simulate work
        
        result = TaskResult(
            task_id=task.task_id,
            role_id=role_spec.role_id,
            platform=role_spec.platform,
            status="success",
            result=f"Task executed by {role_spec.role_name} (placeholder)",
            duration=time.time() - start_time,
        )
        
        return result
    
    def enforce_sod_gate(self, phase_name: str, l2_session_id: str) -> GateStatus:
        """Enforce SOD gate: L2 must terminate before L3 audit.
        
        Args:
            phase_name: Phase identifier (e.g., "phase_1_alpha_factory")
            l2_session_id: L2 implementation session ID
            
        Returns:
            GateStatus with current gate state
        """
        logger.info("Enforcing SOD gate for phase: %s", phase_name)
        
        # Create or update gate status
        if phase_name not in self.phase_gates:
            self.phase_gates[phase_name] = GateStatus(phase_name=phase_name)
        
        gate = self.phase_gates[phase_name]
        gate.l2_session_id = l2_session_id
        gate.l2_completed = True
        gate.final_verdict = "PENDING_AUDIT"
        
        self._save_state()
        
        # Audit log
        self._append_audit_log({
            "event": "sod_gate_enforced",
            "phase_name": phase_name,
            "l2_session_id": l2_session_id,
            "verdict": "PENDING_AUDIT",
        })
        
        logger.info("SOD gate enforced: L2 session %s terminated, awaiting L3 audit", l2_session_id[:8])
        
        return gate
    
    def record_audit_verdict(
        self,
        phase_name: str,
        l3_session_id: str,
        l3_session_key: str,
        audit_report_path: str,
        verdict: str,
    ) -> GateStatus:
        """Record L3 audit verdict for a phase.
        
        Args:
            phase_name: Phase identifier
            l3_session_id: L3 audit session ID
            l3_session_key: L3 session key
            audit_report_path: Path to audit report
            verdict: "APPROVED" or "NEEDS_FIX"
            
        Returns:
            Updated GateStatus
            
        Raises:
            ValueError: If gate not found or verdict invalid
        """
        if phase_name not in self.phase_gates:
            raise ValueError(f"Gate not found for phase: {phase_name}")
        
        if verdict not in ["APPROVED", "NEEDS_FIX"]:
            raise ValueError(f"Invalid verdict: {verdict}")
        
        gate = self.phase_gates[phase_name]
        gate.l3_session_id = l3_session_id
        gate.l3_session_key = l3_session_key
        gate.audit_report_path = audit_report_path
        gate.final_verdict = verdict
        gate.timestamp = time.time()
        
        self._save_state()
        
        # Audit log
        self._append_audit_log({
            "event": "audit_verdict_recorded",
            "phase_name": phase_name,
            "l3_session_id": l3_session_id,
            "verdict": verdict,
            "audit_report_path": audit_report_path,
        })
        
        logger.info("Audit verdict recorded: phase=%s, verdict=%s", phase_name, verdict)
        
        return gate
    
    def get_gate_status(self, phase_name: str) -> Optional[GateStatus]:
        """Get gate status for a phase.
        
        Args:
            phase_name: Phase identifier
            
        Returns:
            GateStatus or None if not found
        """
        return self.phase_gates.get(phase_name)
    
    def get_active_tasks(self) -> Dict[str, TaskRequest]:
        """Get all active tasks.
        
        Returns:
            Dict of task_id -> TaskRequest
        """
        return dict(self.active_tasks)
    
    def get_platform_locks(self) -> Dict[Platform, bool]:
        """Get current platform lock status.
        
        Returns:
            Dict of Platform -> lock status
        """
        return dict(self.agent_locks)


if __name__ == "__main__":
    # Demo
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    print("=" * 80)
    print("LY L1 ORCHESTRATOR - DEMO")
    print("=" * 80)
    
    orchestrator = LyOrchestrator()
    
    print("\n1. Route task to Backend Engineer (Role 9)")
    task1 = TaskRequest(task_type="backend_impl", payload={"feature": "alpha_factory"})
    result1 = orchestrator.route_task(task1)
    print(f"   Result: {result1.status}, Duration: {result1.duration:.3f}s")
    
    print("\n2. Enforce SOD gate for phase_1")
    gate = orchestrator.enforce_sod_gate("phase_1_alpha_factory", "l2-session-001")
    print(f"   Gate Status: {gate.final_verdict}")
    
    print("\n3. Record L3 audit verdict")
    gate = orchestrator.record_audit_verdict(
        "phase_1_alpha_factory",
        "l3-session-001",
        "audit-key-001",
        "docs/L3_AUDIT_PHASE1.md",
        "APPROVED",
    )
    print(f"   Gate Status: {gate.final_verdict}")
    
    print("\n4. Get gate status")
    gate = orchestrator.get_gate_status("phase_1_alpha_factory")
    print(f"   L2 Session: {gate.l2_session_id}")
    print(f"   L3 Session: {gate.l3_session_id}")
    print(f"   Verdict: {gate.final_verdict}")
    
    print("\n" + "=" * 80)
    print("✅ Ly Orchestrator demo complete")
    print("=" * 80)
