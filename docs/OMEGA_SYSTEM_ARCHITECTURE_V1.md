# OMEGA+++ QUANT AI — SYSTEM ARCHITECTURE V1
**Version**: v1.0  
**Status**: Implementation-Ready  
**Last Updated**: 2026-05-09  
**Audience**: Engineering Team, OpenCode (Coder), Codex (Auditor)

---

## 1. EXECUTIVE SUMMARY

OMEGA+++ is an **Institutional Grade Quant AI System** built on three foundational principles:

1. **Unified Core Runtime**: Single task state machine driving all execution
2. **Event-Driven IPC**: Versioned, replayable events for all communication
3. **Repository Layout**: Optimized for clarity, testability, and maintainability

This architecture ensures:
- **PIT Safety**: Zero look-ahead bias, T-1 lag enforced
- **Recovery by Design**: Checkpoint, retry, rollback, restore built-in
- **Observability**: Every action logged, traced, audited
- **Scalability**: From individual traders (2B VND) to institutions (100B+)

---

## 2. UNIFIED CORE RUNTIME

### 2.1 Task State Machine

```
CREATED
  ↓
QUEUED (scheduler queue)
  ↓
PLANNED (agent receives task, creates plan)
  ↓
DISPATCHED (agent starts execution)
  ↓
RUNNING (agent working)
  ↓
WAITING (awaiting external event: data, API, user)
  ↓
VERIFYING (tests, risk checks, acceptance)
  ↓
REVIEWING (Codex audit, safety review)
  ↓
RISK_CHECK (circuit breaker, limits, kill switch)
  ↓
APPROVED (all gates passed)
  ↓
DEPLOYED (production)
  ↓
MONITORING (live tracking, alerts)
  ↓
ARCHIVED (completed, for history)
```

### Failure Path

```
FAILED
  ↓
RETRYING (with exponential backoff)
  ↓
FALLBACK (alternative strategy)
  ↓
ESCALATED (human review)
  ↓
ABORTED (final state)
```

### State Transition Rules

1. **Only one transition at a time**: No concurrent state changes
2. **Every transition logged**: Timestamp, agent, reason, context
3. **No bypassing gates**: Risk checks, audits, tests are mandatory
4. **Idempotent transitions**: Same input → same output, always

### Task Fields (Mandatory)

| Field | Type | Description |
|:------|:-----|:------------|
| `task_id` | string | Unique identifier (UUID v4) |
| `parent_task_id` | string | Parent task if hierarchical |
| `task_type` | enum | planning, architecture, coding, research, feature_engineering, model_training, backtesting, risk_review, security_review, audit, test, deployment, monitoring, recovery, evolution |
| `priority` | int | 1-10 (10 = critical) |
| `status` | enum | CREATED, QUEUED, PLANNED, DISPATCHED, RUNNING, WAITING, VERIFYING, REVIEWING, RISK_CHECK, APPROVED, DEPLOYED, MONITORING, ARCHIVED, FAILED, RETRYING, FALLBACK, ESCALATED, ABORTED |
| `created_at` | datetime | ISO 8601 timestamp |
| `updated_at` | datetime | Last state change timestamp |
| `owner_agent` | string | OpenCode, Codex, SOV, Ly |
| `required_context` | object | Inputs, data, models needed |
| `constraints` | object | Time, token, resource limits |
| `dependencies` | array | Task IDs that must complete first |
| `retry_policy` | object | Max retries, backoff strategy |
| `timeout_policy` | object | Max duration, soft/hard limits |
| `resource_budget` | object | CPU, memory, GPU limits |
| `artifact_refs` | array | Output artifacts (models, datasets, reports) |
| `audit_ref` | string | Audit log reference |

### Task Types

| Type | Description | Example | Allowed Agents |
|:-----|:------------|:--------|:---------------|
| `planning` | Create execution plan | "Plan Phase 3.1 implementation" | Ly, SOV, OpenCode |
| `architecture` | Design system structure | "Design memory compression module" | Ly, SOV, OpenCode |
| `coding` | Write implementation | "Implement VWAP executor" | OpenCode |
| `research` | Analyze data, generate hypotheses | "Find new alpha factors" | Ly, SOV, OpenCode, Codex |
| `feature_engineering` | Compute features | "Calculate RSI, MACD, volume profiles" | OpenCode |
| `model_training` | Train ML models | "Train XGBoost alpha model" | OpenCode |
| `backtesting` | Simulate historical performance | "Walk-forward backtest alpha" | OpenCode |
| `risk_review` | Assess risk, circuit breakers | "Check position limits" | Ly, Codex |
| `security_review` | Security audit, vulnerability scan | "Scan for secrets, vulnerabilities" | Codex |
| `audit` | PIT safety, leakage, compliance audit | "Audit model promotion for leakage" | Codex |
| `test` | Run tests | "Execute unit tests for risk module" | OpenCode |
| `deployment` | Deploy to environment | "Deploy to staging" | OpenCode |
| `monitoring` | Track live performance | "Monitor P&L, Greeks, alerts" | Ly, OpenCode |
| `recovery` | Restore from failure | "Resume from checkpoint" | Ly, OpenCode |
| `evolution` | Self-improvement loop | "Generate new alpha hypothesis" | OpenCode |

**Agent Task-Type Matrix (MACHINE-ENFORCED)**:
- **Ly (L1)**: READ-ONLY on code; allowed task types: `planning`, `architecture`, `research`, `risk_review`, `monitoring`, `recovery`
- **OpenCode (L2)**: WRITE access; allowed task types: `coding`, `feature_engineering`, `model_training`, `backtesting`, `test`, `deployment`, `evolution`, `planning`, `architecture`, `research`, `monitoring`, `recovery`
- **Codex (L3)**: READ-ONLY on code; allowed task types: `audit`, `security_review`, `risk_review`, `research`
- **SOV (L-SOV)**: READ-ONLY; allowed task types: `planning`, `architecture`, `research`

**Scheduler Enforcement**:
```python
AGENT_TASK_MATRIX = {
    "Ly": ["planning", "architecture", "research", "risk_review", "monitoring", "recovery"],
    "OpenCode": ["coding", "feature_engineering", "model_training", "backtesting", "test", 
                 "deployment", "evolution", "planning", "architecture", "research", "monitoring", "recovery"],
    "Codex": ["audit", "security_review", "risk_review", "research"],
    "SOV": ["planning", "architecture", "research"]
}

def validate_task_assignment(task_type: str, agent: str) -> bool:
    """Prevent Codex from being assigned implementation/deployment tasks."""
    if agent not in AGENT_TASK_MATRIX:
        raise ValueError(f"Unknown agent: {agent}")
    if task_type not in AGENT_TASK_MATRIX[agent]:
        raise ValueError(f"Agent {agent} cannot execute task type {task_type}")
    return True
```

---

### 2.2 Scheduler

**Responsibilities**:
- Priority queue management
- Dependency resolution (topological sort)
- Bounded concurrency (max N tasks in parallel)
- Timeout enforcement
- Retry with exponential backoff
- Cancellation propagation
- Preemption for high-priority tasks
- Dead-letter queue for failed tasks

**Scheduler Inputs**:
- Task graph (dependencies, priorities)
- Resource budget (CPU, memory, GPU)
- Agent availability (OpenCode, Codex, SOV)
- Current system load
- Risk flags (high-risk tasks queued separately)

**Scheduler Outputs**:
- Task assignment (which agent)
- Execution order (priority + dependencies)
- Worker allocation (resources per task)
- Wait/resume decision (external dependencies)

**Concurrency Policy**:
- **Low priority**: Max 2 tasks in parallel
- **Medium priority**: Max 4 tasks in parallel
- **High priority**: Max 6 tasks in parallel
- **Critical priority**: Max 8 tasks in parallel (with Ly approval)

---

### 2.3 Worker Lifecycle

```
BOOT
  ↓
LOAD_CONTEXT (deserialize task, inputs, artifacts)
  ↓
EXECUTE (run task logic)
  ↓
VERIFY (run tests, checks)
  ↓
REPORT (log results, emit events, create artifacts)
  ↓
UNLOAD (release resources, save checkpoint)
  ↓
IDLE (await next task)
```

**Worker Requirements**:
- No unnecessary context retention
- Heartbeat every 30 seconds
- Timeout enforcement (soft + hard limits)
- Graceful stop (cleanup, checkpoint)
- Crash recovery (resume from last checkpoint)
- Structured logging (JSON, correlation IDs)

**Heartbeat Protocol**:
- Every 30 seconds, worker sends: `{"task_id": "...", "status": "RUNNING", "progress": 0.75}`
- If heartbeat missed for 60 seconds → task marked as FAILED
- Worker can request extension (max 3 extensions per task)

**Crash Recovery**:
- Checkpoint saved at: `BOOT`, `EXECUTE`, `VERIFY`, `REPORT`
- On restart, worker reads last checkpoint and resumes
- If checkpoint too old (>24 hours), task restarts from `DISPATCHED`

---

### 2.4 Checkpointing

**Checkpoint Points**:
- After planning
- After code patch
- After test pass
- After risk pass
- Before deployment
- After deployment
- Before evolution promotion

**Checkpoint Contents**:
- Task state (all fields)
- Context snapshot (inputs, data, models)
- Artifacts (models, datasets, reports)
- Metrics (latency, throughput, errors)
- Decision rationale (why this path?)

**Checkpoint Storage**:
- Local: `.ly_state/checkpoints/task_<id>.json`
- Remote: S3/GCS bucket `omega-checkpoints/`
- Retention: 30 days (auto-delete)

**Checkpoint Format**:
```json
{
  "task_id": "abc-123-def",
  "checkpoint_id": "chk-001",
  "timestamp": "2026-05-09T04:22:17Z",
  "state": {
    "status": "VERIFYING",
    "progress": 0.75,
    "last_completed_step": "coding",
    "next_step": "testing"
  },
  "context": {
    "inputs": {...},
    "data": {...},
    "models": {...}
  },
  "artifacts": [
    {"path": "models/alpha_v1.pkl", "checksum": "sha256:abc123..."}
  ],
  "metrics": {
    "latency_ms": 150,
    "throughput": 1000,
    "errors": 0
  },
  "rationale": "Testing passed, proceeding to deployment"
}
```

---

## 3. EVENT-DRIVEN IPC SCHEMA

### 3.1 Event Model

**Event Fields**:
| Field | Type | Description |
|:------|:-----|:------------|
| `event_id` | string | Unique identifier (UUID v4) |
| `event_type` | string | TASK_CREATED, TASK_COMPLETED, MODEL_TRAINED, etc. |
| `event_version` | string | Event schema version (e.g., "1.0") |
| `timestamp` | datetime | ISO 8601 timestamp |
| `source` | string | Agent or component ID |
| `target` | string | Intended recipient (optional) |
| `correlation_id` | string | Group related events (e.g., all events for a task) |
| `causation_id` | string | Event that caused this event (optional) |
| `payload` | object | Event-specific data |
| `trace_id` | string | Distributed tracing ID |
| `severity` | enum | INFO, WARN, ERROR, CRITICAL |
| `schema_hash` | string | SHA-256 hash of event schema for validation |

**Machine-Verifiable Contract**:
```json
{
  "contract_version": "1.0",
  "contract_type": "event_schema",
  "description": "Canonical JSON schemas for all event types with normative field definitions",
  "schemas": {
    "TASK_CREATED": {
      "version": "1.0",
      "required_fields": ["task_id", "task_type", "priority", "dependencies"],
      "field_definitions": {
        "task_id": {
          "type": "string",
          "format": "uuid-v4",
          "description": "Unique task identifier"
        },
        "task_type": {
          "type": "enum",
          "allowed_values": ["planning", "architecture", "coding", "research", "feature_engineering", "model_training", "backtesting", "risk_review", "security_review", "audit", "test", "deployment", "monitoring", "recovery", "evolution"],
          "description": "Type of task to execute"
        },
        "priority": {
          "type": "integer",
          "min": 1,
          "max": 10,
          "description": "Task priority (10 = critical)"
        },
        "dependencies": {
          "type": "array",
          "items": {"type": "string", "format": "uuid-v4"},
          "description": "Task IDs that must complete first"
        }
      },
      "validation_rules": [
        "task_id must be valid UUID v4",
        "task_type must be in allowed_values",
        "priority must be between 1 and 10",
        "dependencies must be array of valid UUID v4 strings"
      ],
      "schema_hash": "sha256:a1b2c3d4e5f6..."
    },
    "MODEL_TRAINED": {
      "version": "1.0",
      "required_fields": ["model_id", "metrics", "artifacts", "training_window", "validation_window", "horizon", "embargo_days", "dataset_version"],
      "field_definitions": {
        "model_id": {
          "type": "string",
          "format": "uuid-v4",
          "description": "Unique model identifier"
        },
        "metrics": {
          "type": "object",
          "required_keys": ["ic", "sharpe", "max_drawdown"],
          "description": "Model performance metrics"
        },
        "artifacts": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Artifact paths (model files, reports)"
        },
        "training_window": {
          "type": "object",
          "required_keys": ["start", "end"],
          "key_types": {"start": "date-iso8601", "end": "date-iso8601"},
          "description": "Training period boundaries"
        },
        "validation_window": {
          "type": "object",
          "required_keys": ["start", "end"],
          "key_types": {"start": "date-iso8601", "end": "date-iso8601"},
          "description": "Validation period boundaries"
        },
        "horizon": {
          "type": "integer",
          "min": 1,
          "description": "Prediction horizon in days (e.g., 3 for T+3)"
        },
        "embargo_days": {
          "type": "integer",
          "min": 2,
          "description": "Embargo period = horizon + 1"
        },
        "dataset_version": {
          "type": "string",
          "description": "Dataset version used for training"
        }
      },
      "validation_rules": [
        "embargo_days must equal horizon + 1",
        "validation_window.start >= training_window.end + embargo_days",
        "training_window.start < training_window.end",
        "validation_window.start < validation_window.end"
      ],
      "schema_hash": "sha256:f7g8h9i0j1k2..."
    },
    "MODEL_PROMOTED": {
      "version": "1.0",
      "required_fields": ["model_id", "version", "promoted_by", "training_window", "validation_window", "horizon", "embargo_days", "validation_metrics", "dataset_version"],
      "field_definitions": {
        "model_id": {
          "type": "string",
          "format": "uuid-v4",
          "description": "Unique model identifier"
        },
        "version": {
          "type": "string",
          "pattern": "^v\\d+\\.\\d+\\.\\d+$",
          "description": "Semantic version (e.g., v1.2.3)"
        },
        "promoted_by": {
          "type": "string",
          "enum": ["Ly", "OpenCode"],
          "description": "Agent that promoted the model"
        },
        "training_window": {
          "type": "object",
          "required_keys": ["start", "end"],
          "key_types": {"start": "date-iso8601", "end": "date-iso8601"},
          "description": "Training period boundaries"
        },
        "validation_window": {
          "type": "object",
          "required_keys": ["start", "end"],
          "key_types": {"start": "date-iso8601", "end": "date-iso8601"},
          "description": "Out-of-sample validation period"
        },
        "horizon": {
          "type": "integer",
          "min": 1,
          "description": "Prediction horizon in days"
        },
        "embargo_days": {
          "type": "integer",
          "min": 2,
          "description": "Embargo period = horizon + 1"
        },
        "validation_metrics": {
          "type": "object",
          "required_keys": ["ic_validation", "p_value", "validation_days"],
          "description": "Out-of-sample validation metrics"
        },
        "dataset_version": {
          "type": "string",
          "description": "Dataset version for audit trail"
        }
      },
      "validation_rules": [
        "embargo_days must equal horizon + 1",
        "validation_window.start >= training_window.end + embargo_days (STRICT EMBARGO)",
        "validation_metrics.ic_validation > baseline_ic + 0.02",
        "validation_metrics.p_value < 0.05",
        "validation_metrics.validation_days >= 60",
        "promoted_by cannot be 'Codex' (READ-ONLY constraint)"
      ],
      "schema_hash": "sha256:m3n4o5p6q7r8..."
    }
  },
  "runtime_validation": {
    "description": "Python validation function for event contracts",
    "code": "def validate_event(event, schema): assert event.schema_hash == schema['schema_hash']; assert all(f in event.payload for f in schema['required_fields']); # Type and constraint validation..."
  }
}
```

### 3.2 Event Types

| Event Type | Description | Payload Fields |
|:-----------|:------------|:---------------|
| `TASK_CREATED` | New task created | `task_id`, `task_type`, `priority`, `dependencies` |
| `TASK_PLANNED` | Task planning complete | `task_id`, `plan`, `steps` |
| `TASK_DISPATCHED` | Task assigned to agent | `task_id`, `agent`, `worker_id` |
| `TASK_STARTED` | Agent begins execution | `task_id`, `start_time` |
| `TASK_COMPLETED` | Task finished successfully | `task_id`, `artifacts`, `metrics` |
| `TASK_FAILED` | Task failed | `task_id`, `error`, `retry_count` |
| `TASK_RETRIED` | Task retry attempt | `task_id`, `retry_count`, `backoff_ms` |
| `TASK_ABORTED` | Task manually aborted | `task_id`, `reason` |
| `ARTIFACT_CREATED` | New artifact created | `artifact_id`, `path`, `checksum`, `type` |
| `ARTIFACT_VALIDATED` | Artifact passed validation | `artifact_id`, `validation_result` |
| `MODEL_TRAINED` | Model training complete | `model_id`, `metrics`, `artifacts`, `training_window`, `validation_window`, `horizon`, `embargo_days`, `dataset_version` |
| `MODEL_PROMOTED` | Model promoted to production | `model_id`, `version`, `promoted_by`, `training_window`, `validation_window`, `horizon`, `embargo_days`, `validation_metrics`, `dataset_version` |
| `MODEL_ROLLED_BACK` | Model rolled back | `model_id`, `version`, `reason` |
| `DATASET_REGISTERED` | Dataset registered | `dataset_id`, `name`, `version`, `schema` |
| `DATA_QUALITY_FAILED` | Data quality check failed | `dataset_id`, `errors` |
| `RISK_LIMIT_BREACHED` | Risk limit exceeded | `limit_type`, `value`, `threshold` |
| `DEPLOYMENT_STARTED` | Deployment started | `deployment_id`, `environment`, `version` |
| `DEPLOYMENT_COMPLETED` | Deployment successful | `deployment_id`, `artifacts`, `metrics` |
| `DEPLOYMENT_ROLLED_BACK` | Deployment rolled back | `deployment_id`, `reason` |
| `MEMORY_SNAPSHOT_CREATED` | Memory snapshot saved | `snapshot_id`, `size`, `checksum` |
| `EVOLUTION_PROMOTED` | Evolution hypothesis promoted | `hypothesis_id`, `model_id`, `metrics` |

### 3.3 Event Semantics

1. **Idempotent**: Same event twice = same result
2. **Versioned**: Event schema versioned (backward/forward compatible)
3. **Replayable**: Events can be replayed from log
4. **Ordered by correlation_id**: Events for same task ordered chronologically
5. **Immutable**: Events never modified after creation

### 3.4 IPC Protocol

**Supported Protocols**:
1. **In-process function call**: Fastest, same process
2. **Subprocess/PTY**: For CLI commands, shell scripts
3. **File-based handoff**: For large data, artifacts
4. **Event bus**: For async, decoupled communication
5. **Queue-based async messaging**: For distributed systems

**IPC Rules**:
- Payload small and structured (JSON, Protobuf)
- No full context passed unless necessary
- All interfaces versioned and schema-validated
- Error handling explicit (try/catch, error codes)

**Message Routing**:
- Based on task type, priority, agent capability, resource load, runtime mode, failure history
- Dynamic routing: Re-route if agent overloaded or fails

---

## 4. REPOSITORY LAYOUT (OPTIMIZED)

### 4.1 Root Structure

```
omega-quant-ai/
├── apps/                          # Applications (CLI, API, Dashboard)
│   ├── orchestrator/              # Ly orchestrator
│   ├── api/                       # REST/gRPC API server
│   ├── dashboard/                 # Web dashboard (React/Vue)
│   └── workers/                   # Background workers
├── packages/                      # Reusable packages
│   ├── core/                      # Core runtime (task scheduler, event bus)
│   ├── contracts/                 # Schema and interface definitions
│   ├── memory/                    # Memory compression, retrieval, archive
│   ├── quant/                     # Factors, alphas, models, portfolio
│   ├── backtest/                  # Backtesting engine
│   ├── execution/                 # Order routing, execution
│   ├── risk/                      # Circuit breakers, limits, monitoring
│   ├── data/                      # Data ingestion, validation, storage
│   ├── infra/                     # Queue, worker, resource manager
│   ├── observability/             # Logging, metrics, tracing
│   ├── security/                  # Secrets, access control, audit
│   └── governance/                # Approval, release, audit
├── specs/                         # Specifications (source of truth)
│   ├── runtime/                   # Task scheduler, event bus, IPC
│   ├── events/                    # Event schemas
│   ├── ipc/                       # IPC protocol specs
│   ├── db/                        # Database schema
│   ├── memory/                    # Memory engine specs
│   ├── quant/                     # Quant engine specs
│   ├── backtest/                  # Backtest engine specs
│   ├── execution/                 # Execution engine specs
│   ├── live/                      # Live trading specs
│   ├── infra/                     # Infrastructure specs
│   ├── observability/             # Observability specs
│   ├── security/                  # Security specs
│   ├── governance/                # Governance specs
│   └── evolution/                 # Evolution engine specs
├── datasets/                      # Raw and processed datasets
│   ├── raw/                       # Raw data (VNStock, SSI, etc.)
│   ├── processed/                 # Processed data (features, labels)
│   └── external/                  # External data (macro, alternative)
├── artifacts/                     # Models, reports, checkpoints
│   ├── models/                    # Trained models
│   ├── reports/                   # Analysis reports
│   └── checkpoints/               # Task checkpoints
├── logs/                          # Application logs
│   ├── application/               # App logs
│   ├── audit/                     # Audit logs (immutable)
│   └── metrics/                   # Metrics logs
├── benchmarks/                    # Performance benchmarks
├── experiments/                   # A/B tests, hypothesis testing
├── tests/                         # Test suite
│   ├── unit/                      # Unit tests
│   ├── integration/               # Integration tests
│   ├── e2e/                       # End-to-end tests
│   ├── performance/               # Performance tests
│   └── stress/                    # Stress tests
├── scripts/                       # Automation scripts
│   ├── deploy/                    # Deployment scripts
│   ├── test/                      # Test scripts
│   └── data/                      # Data processing scripts
├── configs/                       # Configuration files
│   ├── environment/               # Environment-specific configs
│   ├── model/                     # Model configs
│   └── risk/                      # Risk config
├── docs/                          # Documentation
│   ├── architecture/              | Architecture docs
│   ├── api/                       # API docs
│   └── runbooks/                  # Runbooks
└── deployments/                   # Deployment manifests
    ├── kubernetes/                # K8s manifests
    └── docker/                    # Docker configs
```

### 4.2 Module Organization Rules

1. **One responsibility per module**: Each package has one clear purpose
2. **No circular dependencies**: Dependency graph is acyclic
3. **Explicit boundaries**: All imports are versioned and schema-validated
4. **Testability**: Every module has unit tests
5. **Versioning**: Every module has version (semver)

### 4.3 Contract Files

Every module must have:
- `README.md`: Purpose, dependencies, failure modes
- `CONTRACT.md`: Inputs, outputs, preconditions, postconditions
- `TESTS.md`: Test coverage, acceptance criteria
- `AUDIT.md`: Security, PIT safety, compliance checks

---

## 5. SAFETY STANDARDS

### 5.1 PIT Safety (Point-In-Time Safety)

**Definition**: No information from future (T+n) leaks into current (T) calculations.

**Rules**:
1. **No look-ahead bias**: T+n data never used for T
2. **T-1 lag**: All features shifted by 1 period
3. **Chronological splitting**: Train/test/val split by time, not random
4. **Leakage blocking**: Labels never used as features
5. **Explicit timestamps**: Every data point must have `as_of` (when data reflects) and `available_at` (when data becomes known)
6. **Temporal boundary validation**: `as_of` <= `available_at` enforced at ingestion and computation

**Timestamp Contract**:
```python
# Every dataset row must include:
{
  "as_of": "2026-05-08T00:00:00Z",      # When this data reflects (e.g., close price on 2026-05-08)
  "available_at": "2026-05-09T09:00:00Z", # When this data became available (e.g., next day market open)
  "value": 123.45
}

# PIT Safety Rule: For prediction at time T, only use data where available_at <= T
```

**Enforcement**:
- Automated leakage detection (data pipeline validates `as_of` <= `available_at`)
- PIT safety audit (Codex)
- Test suite with leakage checks
- Runtime assertions in feature computation

### 5.2 No Leakage

**Types of Leakage**:
1. **Data leakage**: Future data in features
2. **Label leakage**: Labels used as features
3. **Dependency leakage**: Circular dependencies
4. **Temporal leakage**: Non-chronological train/test split
5. **Horizon leakage**: Overlapping label windows (e.g., T+3 and T+5 trained on same period)
6. **Promotion leakage**: Model promoted using in-sample or overlapping validation data

**Detection**:
- Automated: Data pipeline checks (`as_of` <= `available_at`, non-overlapping windows)
- Manual: Codex audit
- Test: Leakage-specific tests

**Multi-Horizon Label Protocol**:
```python
# T+3 Alpha: Predict return from T+1 to T+3
# Label available at: T+4 (after T+3 close)
label_t3 = {
  "as_of": "T+3",           # Return measured up to T+3
  "available_at": "T+4",    # Known at T+4 market open
  "value": (price_t3 - price_t0) / price_t0
}

# T+5 Alpha: Predict return from T+1 to T+5
# Label available at: T+6 (after T+5 close)
label_t5 = {
  "as_of": "T+5",           # Return measured up to T+5
  "available_at": "T+6",    # Known at T+6 market open
  "value": (price_t5 - price_t0) / price_t0
}

# Validation Rule: T+3 and T+5 models must be validated on non-overlapping time windows
# Training: [2024-01-01, 2025-06-30]
# T+3 Validation: [2025-07-04, 2025-12-31]  # +4 days for label availability
# T+5 Validation: [2026-01-06, 2026-06-30]  # +6 days for label availability, no overlap
```

**Model Promotion Protocol (UNIFIED - ALL MODELS)**:
1. **Training window**: [train_start, train_end]
2. **Embargo period**: train_end + max_horizon + 1 day (STRICT - applies to ALL models)
   - T+3 models: embargo = train_end + 4 days
   - T+5 models: embargo = train_end + 6 days
   - T+N models: embargo = train_end + (N+1) days
3. **Validation window**: [validation_start, validation_end] where validation_start >= train_end + max_horizon + 1 (MACHINE-ENFORCED)
4. **Promotion gate**: IC_validation > IC_baseline + 0.02 AND p_value < 0.05 AND validation_days >= 60 AND validation_start >= train_end + max_horizon + 1

### 5.3 Kill Switch

**Purpose**: Emergency stop for all trading.

**Triggers**:
- Risk limit breach (position, leverage, drawdown)
- System failure (latency > 1s, error rate > 1%)
- Market anomaly (volatility spike, flash crash)
- Manual override (Ly approval)

**Actions**:
1. Stop all order submission
2. Cancel pending orders
3. Close positions (if necessary)
4. Log event and alert
5. Wait for manual restart

**Restart Protocol**:
1. Ly approval (explicit)
2. System health check
3. Risk check
4. Gradual restart (small positions first)

### 5.4 Circuit Breakers

**Types**:
1. **Volatility-based**: Halt on volatility spike
2. **Correlation-based**: Halt on correlation breakdown
3. **Liquidity-based**: Halt on liquidity drop

**Parameters**:
- Threshold: Configurable (e.g., volatility > 5%)
- Duration: Configurable (e.g., 5 minutes)
- Recovery: Gradual restart (50% → 75% → 100%)

---

## 6. AGENT ROLES (CONSOLIDATED)

### 6.1 Ly (L1) — Orchestrator

**Role**: Decision-maker, resource allocator, human-in-the-loop

**Responsibilities**:
- Review and approve high-risk tasks
- Allocate resources (CPU, memory, GPU)
- Resolve conflicts (agent disagreements)
- Monitor system health
- Emergency intervention (kill switch)

**Constraints**:
- READ-ONLY on code (no direct edits)
- Decision logs in `.ly_state/logs/`
- Approval required for: deployment, evolution promotion, kill switch

### 6.2 OpenCode (L2) — Coder

**Role**: Implementation, refactoring, testing

**Responsibilities**:
- Write code per contracts
- Run tests (unit, integration, e2e)
- Fix bugs
- Refactor for clarity and performance
- Update documentation

**Constraints**:
- Write access to `src/`, `tests/`, `scripts/`
- No direct database edits
- All changes must pass tests
- Codex audit required before deployment

### 6.3 Codex (L3) — Auditor

**Role**: PIT safety, institutional compliance, security audit

**Responsibilities**:
- Audit code for PIT safety
- Check for leakage (data, label, temporal)
- Review security (secrets, access control)
- Validate compliance (regulatory, internal)
- Generate audit reports (READ-ONLY, no implementation)

**Constraints**:
- READ-ONLY on all code and source files (no direct edits, no implementation work)
- Audit logs in `.ly_state/logs/audit_*.json`
- Approve/reject based on: PIT safety, leakage, security, compliance
- Findings reported to OpenCode (L2) for implementation

### 6.4 SOV V2.4 — Reasoning Engine

**Role**: Strategic guidance, strategy design, institutional standards

**Responsibilities**:
- Provide strategic plans (not execution)
- Design alpha discovery strategies
- Set institutional standards (Renaissance/Two Sigma)
- Review architecture decisions
- Guide Ly's decisions

**Constraints**:
- REASONING-ONLY mode (no direct execution)
- Output: Plans, strategies, recommendations
- No direct code writes
- No direct agent control

---

## 7. DATABASE & STORAGE SPEC

### 7.1 Storage Classes

| Class | Purpose | Examples |
|:------|:--------|:---------|
| `metadata` | Task, agent, configuration | tasks, agents, configs |
| `time-series` | Market data, features, labels | prices, volumes, factors |
| `artifact` | Models, reports, checkpoints | models, reports, checkpoints |
| `log` | Application logs | application logs |
| `audit` | Audit trail (immutable) | audit logs |
| `memory` | Memory snapshots | memory snapshots |
| `model-registry` | Model metadata | models, versions |
| `dataset-registry` | Dataset metadata | datasets, versions |
| `experiment` | A/B test results | experiments, results |

### 7.2 Core Tables

**tasks**:
```sql
CREATE TABLE tasks (
  task_id VARCHAR(36) PRIMARY KEY,
  parent_task_id VARCHAR(36),
  task_type VARCHAR(50) NOT NULL,
  priority INT NOT NULL,
  status VARCHAR(50) NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  owner_agent VARCHAR(50) NOT NULL,
  required_context JSONB,
  constraints JSONB,
  dependencies JSONB,
  retry_policy JSONB,
  timeout_policy JSONB,
  resource_budget JSONB,
  artifact_refs JSONB,
  audit_ref VARCHAR(36)
);
```

**task_events**:
```sql
CREATE TABLE task_events (
  event_id VARCHAR(36) PRIMARY KEY,
  task_id VARCHAR(36) NOT NULL,
  event_type VARCHAR(50) NOT NULL,
  event_version VARCHAR(10) NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  source VARCHAR(50) NOT NULL,
  target VARCHAR(50),
  correlation_id VARCHAR(36) NOT NULL,
  causation_id VARCHAR(36),
  payload JSONB,
  trace_id VARCHAR(36),
  severity VARCHAR(10) NOT NULL
);
```

**artifacts**:
```sql
CREATE TABLE artifacts (
  artifact_id VARCHAR(36) PRIMARY KEY,
  task_id VARCHAR(36) NOT NULL,
  path VARCHAR(500) NOT NULL,
  checksum VARCHAR(64) NOT NULL,
  type VARCHAR(50) NOT NULL,
  size_bytes BIGINT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  metadata JSONB
);
```

**datasets**:
```sql
CREATE TABLE datasets (
  dataset_id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  source VARCHAR(100) NOT NULL,
  frequency VARCHAR(20) NOT NULL,
  schema_version VARCHAR(10) NOT NULL,
  provenance JSONB,
  timestamp_semantics VARCHAR(50) NOT NULL,
  as_of_column VARCHAR(50) NOT NULL,        -- Column name for as_of timestamp
  available_at_column VARCHAR(50) NOT NULL, -- Column name for available_at timestamp
  quality_score DECIMAL(5, 4),
  retention_policy JSONB,
  version VARCHAR(20) NOT NULL,
  checksum VARCHAR(64) NOT NULL,
  CONSTRAINT check_timestamp_columns CHECK (as_of_column IS NOT NULL AND available_at_column IS NOT NULL)
);
```

**models**:
```sql
CREATE TABLE models (
  model_id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  type VARCHAR(50) NOT NULL,
  version VARCHAR(20) NOT NULL,
  status VARCHAR(50) NOT NULL,
  metrics JSONB,
  artifacts JSONB,
  training_window JSONB NOT NULL,           -- {start: "2024-01-01", end: "2025-06-30"}
  validation_window JSONB NOT NULL,         -- {start: "2025-07-05", end: "2025-12-31"}
  horizon INT NOT NULL,                     -- 3, 5, etc.
  embargo_days INT NOT NULL,                -- horizon + 1 (e.g., 4 for T+3, 6 for T+5)
  dataset_version VARCHAR(50) NOT NULL,     -- Dataset lineage for audit trail
  created_at TIMESTAMP NOT NULL,
  promoted_at TIMESTAMP,
  promoted_by VARCHAR(50),
  CONSTRAINT check_embargo CHECK (embargo_days = horizon + 1),
  CONSTRAINT check_validation_start CHECK (
    (validation_window->>'start')::date >= (training_window->>'end')::date + (embargo_days || ' days')::interval
  )
);
```

**audit_logs**:
```sql
CREATE TABLE audit_logs (
  log_id VARCHAR(36) PRIMARY KEY,
  timestamp TIMESTAMP NOT NULL,
  agent VARCHAR(50) NOT NULL,
  action VARCHAR(100) NOT NULL,
  target VARCHAR(100) NOT NULL,
  details JSONB,
  trace_id VARCHAR(36)
);
```

### 7.3 Dataset Spec

**Required Fields**:
| Field | Type | Description |
|:------|:-----|:------------|
| `dataset_id` | string | Unique identifier |
| `name` | string | Human-readable name |
| `source` | string | Data source (VNStock, SSI, etc.) |
| `frequency` | string | Daily, hourly, minute, tick |
| `schema_version` | string | Schema version |
| `provenance` | object | Data lineage |
| `timestamp_semantics` | string | T-1 lag, T+0, etc. |
| `as_of_column` | string | Column name for as_of timestamp (REQUIRED) |
| `available_at_column` | string | Column name for available_at timestamp (REQUIRED) |
| `quality_score` | decimal | 0.0-1.0 |
| `retention_policy` | object | Retention rules |
| `version` | string | Dataset version |
| `checksum` | string | SHA-256 checksum |
| `schema_hash` | string | SHA-256 hash of dataset schema for validation |

**Dataset Rules**:
- Every dataset must have version
- Every dataset must have checksum
- Every dataset must have provenance
- Every dataset must specify `as_of_column` and `available_at_column`
- Every row must satisfy: `as_of` <= `available_at` (enforced at ingestion)
- Quality score < 0.8 → alert

**Machine-Verifiable Dataset Contract**:
```json
{
  "contract_version": "1.0",
  "contract_type": "dataset_schema",
  "description": "Canonical JSON schemas for dataset validation with normative field definitions",
  "schemas": {
    "daily_prices_v1": {
      "version": "1.0",
      "required_columns": ["ticker", "date", "open", "high", "low", "close", "volume", "as_of", "available_at"],
      "column_definitions": {
        "ticker": {
          "type": "string",
          "max_length": 10,
          "description": "Stock ticker symbol"
        },
        "date": {
          "type": "datetime",
          "format": "iso8601",
          "description": "Trading date"
        },
        "open": {
          "type": "float64",
          "min": 0,
          "description": "Opening price"
        },
        "high": {
          "type": "float64",
          "min": 0,
          "description": "High price"
        },
        "low": {
          "type": "float64",
          "min": 0,
          "description": "Low price"
        },
        "close": {
          "type": "float64",
          "min": 0,
          "description": "Closing price"
        },
        "volume": {
          "type": "int64",
          "min": 0,
          "description": "Trading volume"
        },
        "as_of": {
          "type": "datetime",
          "format": "iso8601",
          "description": "Point-in-time timestamp (when data reflects reality)"
        },
        "available_at": {
          "type": "datetime",
          "format": "iso8601",
          "description": "Availability timestamp (when data becomes known)"
        }
      },
      "validation_rules": [
        "as_of <= available_at (PIT safety)",
        "open > 0",
        "high >= low",
        "high >= open",
        "high >= close",
        "low <= open",
        "low <= close",
        "volume >= 0"
      ],
      "schema_hash": "sha256:def456..."
    }
  },
  "runtime_validation": {
    "description": "Python validation function for dataset contracts",
    "code": "def validate_dataset(df, schema_name): schema = DATASET_SCHEMAS[schema_name]; assert set(schema['required_columns']).issubset(df.columns); assert all(df['as_of'] <= df['available_at']), 'PIT violation'; # Type and constraint validation..."
  }
}
```

---

## 8. MONITORING & OBSERVABILITY

### 8.1 Logging

**Structured Logging Format**:
```json
{
  "timestamp": "2026-05-09T04:22:17Z",
  "level": "INFO",
  "logger": "orchestrator",
  "message": "Task completed",
  "task_id": "abc-123-def",
  "correlation_id": "corr-456",
  "trace_id": "trace-789",
  "agent": "OpenCode",
  "duration_ms": 150,
  "metrics": {...}
}
```

**Log Levels**:
- `DEBUG`: Detailed debugging info
- `INFO`: Normal operations
- `WARN`: Warning (action needed)
- `ERROR`: Error (manual intervention)
- `CRITICAL`: Critical (immediate action)

### 8.2 Metrics

**Key Metrics**:
- Task latency (p50, p95, p99)
- Task throughput (tasks/minute)
- Error rate (%)
- Resource usage (CPU, memory, GPU)
- Risk metrics (drawdown, VaR, Greeks)

**Metrics Collection**:
- Every 10 seconds (real-time)
- Every 1 minute (aggregated)
- Every 1 hour (archived)

### 8.3 Tracing

**Trace ID**: Every task gets unique trace ID
**Span ID**: Every step gets span ID
**Parent Span ID**: Hierarchical relationship

**Trace Example**:
```
Task: abc-123-def
  Span 1: Planning (duration: 50ms)
  Span 2: Coding (duration: 100ms)
  Span 3: Testing (duration: 30ms)
  Span 4: Audit (duration: 20ms)
```

---

## 9. DEPLOYMENT STRATEGY

### 9.1 Blue-Green Deployment

**Steps**:
1. Deploy new version to green environment
2. Run smoke tests on green
3. Switch traffic from blue to green
4. Monitor green for 5 minutes
5. If OK, decommission blue

### 9.2 Canary Deployment

**Steps**:
1. Deploy new version to 10% of traffic
2. Monitor for 10 minutes
3. If OK, increase to 25%
4. Repeat until 100%

### 9.3 Rollback

**Triggers**:
- Error rate > 1%
- Latency > 1s
- Risk limit breach
- Manual override

**Steps**:
1. Stop new version
2. Switch traffic to previous version
3. Log rollback event
4. Alert team

---

## 10. NEXT STEPS

1. **Week 1**: Implement Task State Machine (OpenCode)
2. **Week 1**: Implement Event Bus (OpenCode)
3. **Week 2**: Implement Scheduler (OpenCode)
4. **Week 2**: Implement Checkpointing (OpenCode)
5. **Week 3**: Implement Database Schema (OpenCode)
6. **Week 3**: Audit PIT Safety and Leakage Controls (Codex - READ-ONLY audit, findings reported to OpenCode)
7. **Week 4**: Implement Repository Layout (OpenCode)
8. **Week 4**: Implement Monitoring (OpenCode)

---

**Document Owner**: OpenCode (L2)  
**Reviewed By**: Codex (L3), Ly (L1)  
**Last Updated**: 2026-05-09  
**Version**: v1.0
