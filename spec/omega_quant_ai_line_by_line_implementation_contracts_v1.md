# OMEGA+++ QUANT AI — LINE-BY-LINE IMPLEMENTATION CONTRACTS
Phiên bản: v1.0
Trạng thái: Implementation Contract Layer
Mục tiêu: Cung cấp contract đủ chi tiết để AI coder có thể triển khai theo file, class, function, event, schema và test, với mức độ line-by-line.

---

# 1. MỤC ĐÍCH

Tài liệu này là lớp tiếp theo sau “Institutional Engineering Spec”. Nó không còn dừng ở architecture hay module-level spec, mà chuyển sang:

- file-level contract;
- class-level contract;
- function-level contract;
- event-level contract;
- schema-level contract;
- test-level contract;
- acceptance-level contract.

Mục tiêu là để AI coder có thể nhận tài liệu này và chuyển trực tiếp sang:

- tạo repo;
- tạo file;
- tạo class;
- tạo function;
- gắn test;
- chạy verify;
- sửa lỗi;
- hoàn thiện đến khi hệ thống build được.

---

# 2. NGUYÊN TẮC CHUNG

## 2.1. One file, one responsibility
Mỗi file chỉ nên giữ một trách nhiệm chính.

## 2.2. One class, one contract
Mỗi class phải có contract đầu vào/đầu ra rõ.

## 2.3. One function, one behavior
Mỗi function phải làm một hành vi chính.

## 2.4. No hidden side effects
Không được tạo side effect ngầm mà contract không mô tả.

## 2.5. Every boundary is explicit
Tất cả boundary giữa module phải mô tả bằng schema hoặc interface.

## 2.6. Everything is testable
Mọi contract phải có test hoặc acceptance check.

## 2.7. Everything is versioned
File, schema, event, model, dataset, prompt, config đều phải version hóa.

---

# 3. REPOSITORY CONTRACT MAP

## 3.1. Root structure

```text
omega-quant-ai/
├── apps/
├── packages/
├── specs/
├── tests/
├── scripts/
├── configs/
├── datasets/
├── artifacts/
├── logs/
├── docs/
└── deployments/
```

## 3.2. Required engineering subtrees

```text
specs/
├── runtime/
├── events/
├── ipc/
├── db/
├── memory/
├── quant/
├── backtest/
├── execution/
├── live/
├── infra/
├── observability/
├── security/
├── governance/
├── evolution/
└── contracts/
```

## 3.3. Mandatory artifact rules
- Mỗi spec file phải có version.
- Mỗi implementation file phải có reference đến spec.
- Mỗi test file phải có target module rõ ràng.
- Mỗi config file phải có ownership rõ.
- Mỗi artifact phải trace được đến task id.

---

# 4. CONTRACT LEVELS

## 4.1. Level 0 — System contract
Mô tả mục tiêu, topology, boundaries, constraints.

## 4.2. Level 1 — Module contract
Mô tả trách nhiệm của module, public interface, dependency, failure modes.

## 4.3. Level 2 — File contract
Mô tả từng file: purpose, inputs, outputs, imports, side effects, tests.

## 4.4. Level 3 — Class contract
Mô tả mỗi class: state, methods, invariants, lifecycle.

## 4.5. Level 4 — Function contract
Mô tả mỗi function: signature, preconditions, postconditions, errors, complexity.

## 4.6. Level 5 — Line contract
Mô tả các block logic bên trong function khi cần cực chi tiết:
- validation block;
- transformation block;
- persistence block;
- emit event block;
- error handling block.

---

# 5. FILE CONTRACT TEMPLATE

Mỗi file implementation phải bám theo template sau.

## 5.1. File header contract

```text
File:
Purpose:
Spec reference:
Owner agent:
Inputs:
Outputs:
Dependencies:
Side effects:
Failure modes:
Tests:
```

## 5.2. File rules
- Nếu file chứa logic, phải có contract.
- Nếu file chỉ re-export, phải ghi rõ.
- Nếu file chứa constants, phải mô tả nguồn chuẩn hóa.
- Nếu file tạo network/db side effects, phải ghi rõ quyền hạn.

## 5.3. File acceptance
File chỉ được chấp nhận khi:
- import được;
- không vi phạm contract;
- có test liên quan;
- không tạo circular dependency.

---

# 6. CLASS CONTRACT TEMPLATE

## 6.1. Class header contract

```text
Class:
Purpose:
Responsibilities:
Non-responsibilities:
State:
Dependencies:
Invariant:
Lifecycle:
Methods:
Failure modes:
Tests:
```

## 6.2. Class rules
- Một class không được kiêm quá nhiều vai.
- State phải explicit.
- Constructor chỉ setup dependency và invariant.
- Method phải có precondition/postcondition.
- State mutation phải trace được.

---

# 7. FUNCTION CONTRACT TEMPLATE

## 7.1. Function contract fields

```text
Function:
Signature:
Purpose:
Inputs:
Outputs:
Preconditions:
Postconditions:
Exceptions:
Side effects:
Complexity:
Idempotency:
Retryability:
Test cases:
```

## 7.2. Function rules
- Function phải return value rõ.
- Không được dùng magic global state.
- Không được có hidden IO nếu contract không ghi.
- Nếu function async thì phải ghi timeout/cancel behavior.
- Nếu function ghi DB hoặc file thì phải ghi transaction semantics.

---

# 8. EVENT CONTRACT TEMPLATE

## 8.1. Event schema fields

```json
{
  "event_id": "",
  "event_type": "",
  "event_version": "",
  "timestamp": "",
  "source": "",
  "target": "",
  "correlation_id": "",
  "causation_id": "",
  "payload": {},
  "severity": "",
  "trace_id": ""
}
```

## 8.2. Event contract fields
- Name
- Version
- Producer
- Consumer
- Delivery guarantee
- Ordering guarantee
- Idempotency rule
- Retry rule
- Dead-letter rule
- Schema evolution rule

## 8.3. Mandatory events
- TASK_CREATED
- TASK_PLANNED
- TASK_DISPATCHED
- TASK_STARTED
- TASK_COMPLETED
- TASK_FAILED
- TASK_RETRIED
- ARTIFACT_CREATED
- DATASET_REGISTERED
- MODEL_TRAINED
- MODEL_PROMOTED
- BACKTEST_COMPLETED
- RISK_BREACH
- DEPLOYMENT_COMPLETED
- MEMORY_SNAPSHOT_CREATED
- EVOLUTION_PROMOTED

---

# 9. SCHEMA CONTRACT TEMPLATE

## 9.1. Schema fields
- entity_name
- schema_version
- primary_key
- required_fields
- optional_fields
- validation_rules
- timestamp_semantics
- retention_policy
- migration_policy

## 9.2. Schema rule
Không được để schema undefined trong code. Mọi structure đều phải có schema hoặc typed interface.

---

# 10. TASK CONTRACT

## 10.1. Task schema

```text
task_id
parent_task_id
task_type
priority
status
created_at
updated_at
owner_agent
required_context
constraints
dependencies
retry_policy
timeout_policy
resource_budget
artifact_refs
audit_ref
```

## 10.2. Task contract rules
- Task phải có owner.
- Task phải có status hợp lệ.
- Task phải có dependency rõ.
- Task phải có policy cho retry/timeout.
- Task phải lưu được audit trail.

---

# 11. AGENT CONTRACT

## 11.1. Agent contract fields

```text
agent_id
agent_type
role
runtime
capabilities
inputs
outputs
scope
limits
failure_modes
escalation_path
```

## 11.2. Agent rules
- Agent phải có scope.
- Agent chỉ làm đúng nhiệm vụ.
- Agent phải có escalation path.
- Agent phải có output format chuẩn.
- Agent phải có memory policy.

---

# 12. MODULE-BY-MODULE IMPLEMENTATION CONTRACTS

---

## 12.1. Orchestrator Module

### Purpose
Điều phối task, agent, context, event, verification.

### Files
- `orchestrator.py`
- `scheduler.py`
- `router.py`
- `task_graph.py`
- `state_machine.py`

### Required functions
- create_task
- plan_task
- route_task
- dispatch_task
- update_task_state
- handle_task_failure
- retry_task
- archive_task

### Required invariants
- dependency order preserved;
- retry count bounded;
- task state valid;
- context minimal;
- audit always on.

---

## 12.2. Planner Module

### Purpose
Tạo kế hoạch thực thi từ objective.

### Files
- `planner.py`
- `dependency_resolver.py`
- `priority_ranker.py`

### Required functions
- decompose_objective
- rank_subtasks
- resolve_dependencies
- estimate_resource_cost
- emit_plan

### Invariants
- plan must be deterministic for same input;
- every subtask must map to owner class;
- no orphan task.

---

## 12.3. Code Module

### Purpose
Tạo và sửa code theo spec.

### Files
- `code_agent.py`
- `patch_builder.py`
- `repo_editor.py`
- `refactor_engine.py`

### Required functions
- load_repo_context
- identify_target_files
- generate_patch
- apply_patch
- validate_patch
- rollback_patch

### Invariants
- no speculative edits;
- preserve architecture;
- patch must be testable.

---

## 12.4. Review Module

### Purpose
Phản biện logic, contract, architecture.

### Files
- `review_agent.py`
- `contract_checker.py`
- `architecture_checker.py`

### Required functions
- review_spec
- review_code
- detect_violations
- classify_severity
- issue_review_report

---

## 12.5. Test Module

### Purpose
Sinh và chạy test.

### Files
- `test_agent.py`
- `test_generator.py`
- `regression_runner.py`

### Required functions
- generate_unit_tests
- generate_integration_tests
- run_tests
- collect_results
- compare_against_baseline

---

## 12.6. Risk Module

### Purpose
Chặn chiến lược hoặc trạng thái nguy hiểm.

### Files
- `risk_agent.py`
- `risk_metrics.py`
- `risk_rules.py`

### Required functions
- compute_exposure
- compute_drawdown
- compute_tail_risk
- evaluate_liquidity_risk
- evaluate_regime_fragility
- approve_or_block

---

## 12.7. Memory Module

### Purpose
Lưu, truy hồi, nén context.

### Files
- `memory_agent.py`
- `retrieval_engine.py`
- `compression_engine.py`
- `snapshot_store.py`

### Required functions
- store_snapshot
- retrieve_context
- rank_memory_items
- compress_context
- evict_old_memory

---

## 12.8. Quant Module

### Purpose
Feature, alpha, model, portfolio, risk logic.

### Files
- `feature_engine.py`
- `alpha_engine.py`
- `model_engine.py`
- `portfolio_engine.py`
- `risk_engine.py`

### Required functions
- build_features
- normalize_features
- score_alpha
- train_model
- evaluate_model
- optimize_portfolio
- compute_risk

---

## 12.9. Backtest Module

### Purpose
Mô phỏng chiến lược lịch sử.

### Files
- `backtest_engine.py`
- `execution_simulator.py`
- `cost_model.py`

### Required functions
- run_backtest
- simulate_order_flow
- simulate_fills
- account_for_costs
- produce_report

---

## 12.10. Execution Module

### Purpose
Tạo và thực thi lệnh.

### Files
- `execution_engine.py`
- `order_manager.py`
- `fill_engine.py`

### Required functions
- create_order
- validate_order
- send_order
- cancel_order
- reconcile_orders
- reconcile_positions

---

## 12.11. Live Trading Module

### Purpose
Kết nối broker/exchange và quản trị live order lifecycle.

### Files
- `broker_adapter.py`
- `oms.py`
- `reconciliation.py`
- `kill_switch.py`

### Required functions
- connect_broker
- submit_live_order
- monitor_order_status
- reconcile_live_state
- trigger_kill_switch

---

## 12.12. Infra Module

### Purpose
Quản lý runtime, queue, worker, resource.

### Files
- `queue_manager.py`
- `worker_pool.py`
- `resource_manager.py`
- `runtime_health.py`

### Required functions
- enqueue_task
- dequeue_task
- spawn_worker
- stop_worker
- throttle_workers
- measure_health

---

## 12.13. Observability Module

### Purpose
Logging, metrics, tracing, alerting.

### Files
- `logger.py`
- `metrics.py`
- `tracer.py`
- `alerting.py`

### Required functions
- emit_log
- record_metric
- start_trace
- stop_trace
- raise_alert

---

## 12.14. Security Module

### Purpose
Secret safety, sandbox, dependency safety.

### Files
- `secret_manager.py`
- `sandbox.py`
- `dependency_scanner.py`

### Required functions
- load_secret
- rotate_secret
- validate_sandbox_policy
- scan_dependencies
- block_unsafe_action

---

## 12.15. Governance Module

### Purpose
Approval gates, release, audit, rollback.

### Files
- `approval_gate.py`
- `release_manager.py`
- `audit_trail.py`

### Required functions
- request_approval
- approve_release
- reject_release
- record_audit
- initiate_rollback

---

## 12.16. Evolution Module

### Purpose
Benchmark, promote, retire, archive.

### Files
- `evolution_engine.py`
- `benchmark_runner.py`
- `promotion_manager.py`

### Required functions
- run_benchmark
- compare_versions
- promote_candidate
- retire_candidate
- archive_result

---

# 13. LINE-BY-LINE IMPLEMENTATION RULES

## 13.1. Validation first block
Mọi function xử lý input phải bắt đầu bằng validation.

## 13.2. Transformation block
Sau validation, chuyển đổi dữ liệu theo contract.

## 13.3. Core logic block
Thực hiện logic chính ở đây, không trộn validation.

## 13.4. Persistence block
Nếu có lưu trữ, phải ghi rõ transaction and failure handling.

## 13.5. Event emission block
Nếu có event, phát sau khi state change thành công.

## 13.6. Error handling block
Phải convert lỗi kỹ thuật thành lỗi contract có mã.

---

# 14. AI CODER EXECUTION SEQUENCE

## 14.1. Step 1
Read spec.

## 14.2. Step 2
Resolve file contract.

## 14.3. Step 3
Resolve class and function contracts.

## 14.4. Step 4
Generate code skeleton.

## 14.5. Step 5
Implement file by file.

## 14.6. Step 6
Run tests after each file or bounded group.

## 14.7. Step 7
Patch failures.

## 14.8. Step 8
Run integration verification.

## 14.9. Step 9
Run acceptance verification.

## 14.10. Step 10
Archive result and update memory.

---

# 15. TEST CONTRACTS

## 15.1. Unit test contract
- test one behavior;
- one failure mode;
- deterministic result.

## 15.2. Integration test contract
- test module boundaries;
- verify schema compatibility;
- verify event emission;
- verify state transitions.

## 15.3. Regression test contract
- test previous bug paths;
- ensure no recurrence.

## 15.4. Stress test contract
- test high load;
- test memory pressure;
- test concurrency.

## 15.5. Quant test contract
- test leakage;
- test OOS stability;
- test regime robustness;
- test cost realism.

---

# 16. ACCEPTANCE CRITERIA

Một implementation pass khi:

- file contract đúng;
- class contract đúng;
- function contract đúng;
- tests pass;
- events emitted đúng schema;
- states transition hợp lệ;
- memory and resource limits respected;
- no architecture violation;
- no leakage;
- audit trail đầy đủ.

---

# 17. OUTPUT ARTIFACTS

Bắt buộc sinh ra:

- source files;
- unit tests;
- integration tests;
- schema files;
- event files;
- migration files nếu có;
- logs;
- benchmark reports;
- audit reports;
- deployment notes.

---

# 18. FINAL CONTRACT

Tài liệu này là cầu nối từ:
- engineering spec
đến
- executable implementation.

Nó được thiết kế để AI coder có thể:
- đọc contract;
- tạo code file theo file;
- cài từng class/function;
- verify từng bước;
- sửa từng lỗi;
- đi từ spec sang chương trình có thể vận hành.
