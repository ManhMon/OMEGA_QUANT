# Phase 3.1 Task Breakdown: Alpha Discovery Engine

**Role**: Planner Supervisor (Role 2)  
**Date**: 2026-05-10  
**Source**: `OMEGA_QUANT/docs/COMPREHENSIVE_SYSTEM_BUILD_PLAN.md`  
**Scope**: Planning only. No implementation.

## Planning Assumptions

- Source plan has naming mismatch: phase tracker says `Phase 3.1: Alpha Discovery Engine`, but body under that header still describes former `Phase 2.3` model-training deliverables.
- Breakdown below treats **Alpha Discovery Engine** as target scope and reuses already-specified PIT, walk-forward, and promotion constraints because those constraints are explicitly required elsewhere in system docs.
- Module names are planning targets for estimation and sequencing. Architecture Supervisor can finalize exact filenames before code starts.
- Resource caps follow workspace protocol: `<= 4 GB RAM` per implementation task, single-platform execution, file-backed state only.

## 1. Module List

| Module | Proposed Path | Purpose | Notes | Effort |
|:--|:--|:--|:--|:--|
| `alpha_discovery.py` | `packages/quant/src/omega/quant/alpha_discovery.py` | Top-level orchestration for discovery runs, candidate evaluation, lifecycle hooks | Existing file likely refactored from monolith into thin orchestrator | 6h |
| `alpha_primitives.py` | `packages/quant/src/omega/quant/alpha_primitives.py` | Safe expression operators, panel validation, T-1 lag helpers, PIT guards | Extract from current consolidated module | 5h |
| `label_engine.py` | `packages/quant/src/omega/quant/label_engine.py` | Multi-horizon label generation with settlement-gap and `available_at` discipline | Must enforce T+3/T+5 timing semantics | 4h |
| `expression_generator.py` | `packages/quant/src/omega/quant/expression_generator.py` | Candidate alpha expression generation with bounded operator depth | Needs deterministic seeding for reproducibility | 3h |
| `alpha_scoring.py` | `packages/quant/src/omega/quant/alpha_scoring.py` | IC/coverage scoring, thresholding, pass/fail decision logic | Central scoring contract for discovery engine | 5h |
| `alpha_registry.py` | `packages/quant/src/omega/quant/alpha_registry.py` | Persistent catalog of discovered alphas, metadata, discovery IC baseline, status | Needed because session state cannot live only in RAM | 5h |
| `decay_monitor.py` | `packages/quant/src/omega/quant/decay_monitor.py` | Decay detection, sign-flip retirement rules, baseline-vs-current comparison | Can reuse discovery IC baseline from registry | 4h |
| `walk_forward_engine.py` | `packages/core/src/omega/core/walk_forward_engine.py` | Shared temporal window generation, embargo enforcement, non-overlap checks for discovery evaluation | Likely extracted from current `trainer.py` logic | 6h |
| `promotion_gate.py` | `packages/core/src/omega/core/promotion_gate.py` | Promotion checks for alpha candidates/models using embargo, window, and minimum metric rules | Existing repo uses `promotion.py`; naming alignment required | 4h |
| `tests/phase3/test_alpha_discovery_engine.py` | `tests/phase3/test_alpha_discovery_engine.py` | End-to-end and integration tests across discovery, walk-forward, promotion, decay | Includes PIT and fail-closed cases | 8h |

**Total planned implementation effort**: `50h`  
**Recommended Codex audit/test pass after implementation**: `10h`

## 2. Atomic Implementation Tasks

| Task ID | Module | Atomic Task | Depends On | Owner Role | Effort |
|:--|:--|:--|:--|:--|:--|
| `T01` | `alpha_primitives.py` | Extract safe operators, panel-index validators, lag helpers, PIT filtering utilities into standalone module | - | Alpha Agent | 5h |
| `T02` | `label_engine.py` | Build multi-horizon label generator for T+3/T+5 with settlement-gap and explicit label availability rules | `T01` | Alpha Agent | 4h |
| `T03` | `expression_generator.py` | Build reproducible candidate-expression generator with operator/lag constraints | `T01` | Research Agent | 3h |
| `T04` | `alpha_scoring.py` | Implement coverage filters, IC scoring, threshold evaluation, score serialization contract | `T01`, `T02` | Quant Supervisor + Alpha Agent | 5h |
| `T05` | `alpha_registry.py` | Add file-backed registry for discovered alphas, baselines, status transitions, audit metadata | `T04` | Alpha Agent | 5h |
| `T06` | `decay_monitor.py` | Implement decay checks against discovery baselines, sign-flip retirement, fail-closed handling | `T05` | Alpha Agent | 4h |
| `T07` | `walk_forward_engine.py` | Extract shared walk-forward window builder with embargo and non-overlap rules for discovery evaluation | `T02` | Model Agent | 6h |
| `T08` | `promotion_gate.py` | Implement promotion rule adapter for alpha candidates using embargo, metrics, and validation-window checks | `T07` | Risk Agent | 4h |
| `T09` | `alpha_discovery.py` | Rebuild top-level orchestration around generator, scorer, walk-forward engine, registry, and decay monitor | `T02`, `T03`, `T04`, `T05`, `T06`, `T07` | Alpha Agent | 6h |
| `T10` | `test_alpha_discovery_engine.py` | Write unit and integration tests for PIT safety, walk-forward isolation, registry persistence, promotion failure modes, decay retirement | `T08`, `T09` | Test Agent | 8h |

## 3. Dependencies DAG

```json
{
  "phase": "3.1",
  "name": "Alpha Discovery Engine",
  "nodes": [
    {
      "id": "T01",
      "module": "alpha_primitives.py",
      "path": "packages/quant/src/omega/quant/alpha_primitives.py",
      "depends_on": [],
      "effort_hours": 5,
      "ram_gb": 1.0,
      "cpu_cores": 1
    },
    {
      "id": "T02",
      "module": "label_engine.py",
      "path": "packages/quant/src/omega/quant/label_engine.py",
      "depends_on": ["T01"],
      "effort_hours": 4,
      "ram_gb": 1.5,
      "cpu_cores": 2
    },
    {
      "id": "T03",
      "module": "expression_generator.py",
      "path": "packages/quant/src/omega/quant/expression_generator.py",
      "depends_on": ["T01"],
      "effort_hours": 3,
      "ram_gb": 1.0,
      "cpu_cores": 1
    },
    {
      "id": "T04",
      "module": "alpha_scoring.py",
      "path": "packages/quant/src/omega/quant/alpha_scoring.py",
      "depends_on": ["T01", "T02"],
      "effort_hours": 5,
      "ram_gb": 2.0,
      "cpu_cores": 2
    },
    {
      "id": "T05",
      "module": "alpha_registry.py",
      "path": "packages/quant/src/omega/quant/alpha_registry.py",
      "depends_on": ["T04"],
      "effort_hours": 5,
      "ram_gb": 1.0,
      "cpu_cores": 1
    },
    {
      "id": "T06",
      "module": "decay_monitor.py",
      "path": "packages/quant/src/omega/quant/decay_monitor.py",
      "depends_on": ["T05"],
      "effort_hours": 4,
      "ram_gb": 1.0,
      "cpu_cores": 1
    },
    {
      "id": "T07",
      "module": "walk_forward_engine.py",
      "path": "packages/core/src/omega/core/walk_forward_engine.py",
      "depends_on": ["T02"],
      "effort_hours": 6,
      "ram_gb": 2.0,
      "cpu_cores": 2
    },
    {
      "id": "T08",
      "module": "promotion_gate.py",
      "path": "packages/core/src/omega/core/promotion_gate.py",
      "depends_on": ["T07"],
      "effort_hours": 4,
      "ram_gb": 1.0,
      "cpu_cores": 1
    },
    {
      "id": "T09",
      "module": "alpha_discovery.py",
      "path": "packages/quant/src/omega/quant/alpha_discovery.py",
      "depends_on": ["T02", "T03", "T04", "T05", "T06", "T07"],
      "effort_hours": 6,
      "ram_gb": 3.0,
      "cpu_cores": 2
    },
    {
      "id": "T10",
      "module": "test_alpha_discovery_engine.py",
      "path": "tests/phase3/test_alpha_discovery_engine.py",
      "depends_on": ["T08", "T09"],
      "effort_hours": 8,
      "ram_gb": 3.5,
      "cpu_cores": 3
    }
  ]
}
```

## 4. Effort Estimate Per Module

| Module | Effort | Complexity | Driver |
|:--|:--|:--|:--|
| `alpha_primitives.py` | 5h | Medium | Safe operator extraction, PIT-safe panel semantics |
| `label_engine.py` | 4h | Medium | Multi-horizon timing and settlement-gap correctness |
| `expression_generator.py` | 3h | Low | Bounded expression generation, reproducibility |
| `alpha_scoring.py` | 5h | Medium | IC/coverage logic, threshold contract, serialization |
| `alpha_registry.py` | 5h | Medium | File persistence, metadata schema, recovery-safe writes |
| `decay_monitor.py` | 4h | Medium | Baseline comparison and fail-closed retirement logic |
| `walk_forward_engine.py` | 6h | High | Temporal split correctness, embargo, non-overlap guarantees |
| `promotion_gate.py` | 4h | Medium | Rule reuse plus naming/path reconciliation |
| `alpha_discovery.py` | 6h | High | Integration of all submodules into single run loop |
| `tests/phase3/test_alpha_discovery_engine.py` | 8h | High | PIT edge cases, integration matrix, persistence cases |

## 5. Resource Allocation

| Task ID | Module | RAM | CPU | Runtime Notes |
|:--|:--|:--|:--|:--|
| `T01` | `alpha_primitives.py` | 1.0 GB | 1 core | Pure logic extraction |
| `T02` | `label_engine.py` | 1.5 GB | 2 cores | Label generation on medium sample panels |
| `T03` | `expression_generator.py` | 1.0 GB | 1 core | CPU-light unless candidate counts increase |
| `T04` | `alpha_scoring.py` | 2.0 GB | 2 cores | Correlation/scoring over candidate batches |
| `T05` | `alpha_registry.py` | 1.0 GB | 1 core | File IO and metadata serialization |
| `T06` | `decay_monitor.py` | 1.0 GB | 1 core | Low compute, mostly comparison logic |
| `T07` | `walk_forward_engine.py` | 2.0 GB | 2 cores | Window construction, boundary validation |
| `T08` | `promotion_gate.py` | 1.0 GB | 1 core | Rule checks, low footprint |
| `T09` | `alpha_discovery.py` | 3.0 GB | 2 cores | Orchestration plus candidate evaluation loop |
| `T10` | `test_alpha_discovery_engine.py` | 3.5 GB | 3 cores | Integration tests on representative datasets |

**Platform guidance**

- Keep implementation on single L2 platform session at any one time.
- Do not exceed `4 GB RAM` for any spawned implementation task.
- Check system free RAM `> 10 GB` before `T09` and `T10`, since those are highest-footprint tasks.

## 6. Risk Assessment

| Risk | Severity | Why It Matters | Mitigation |
|:--|:--|:--|:--|
| Spec mismatch: `Phase 3.1` tracker vs `Phase 2.3` body | High | Team may implement wrong scope or wrong filenames | Freeze scope before coding; Architecture Supervisor confirms module naming and acceptance criteria |
| PIT leakage in labels or walk-forward windows | Critical | Invalidates alpha quality and audit outcome | Implement `T02` and `T07` first; Codex review on timing semantics before integration |
| Monolith carry-over from existing `alpha_discovery.py` | High | Hard to test, easy to regress | Split responsibilities early; keep orchestrator thin |
| Filename mismatch: `promotion.py` vs planned `promotion_gate.py` | Medium | Import churn and broken tests likely | Resolve naming contract before `T08`; add compatibility shim only if Architecture Supervisor approves |
| In-memory alpha universe/state | High | Violates file-backed state rule and hurts recoverability | `T05` mandatory before integration; persist discovery baseline and status transitions |
| Test matrix explosion across horizons and windows | Medium | Can slip schedule and hide gaps | Prioritize fail-closed and PIT cases first; keep minimal golden-path integration set |
| Reproducibility drift from random expression generation | Medium | Hard to audit and compare discovery runs | Deterministic seeding in `T03`; record seed in registry metadata |

## Recommended Execution Order

1. `T01` -> `T02` and `T03`
2. `T04` -> `T05` -> `T06`
3. `T07` -> `T08`
4. `T09`
5. `T10`

## Exit Criteria For Planning Handoff

- Module names and target paths accepted by Architecture Supervisor.
- DAG accepted by Engineering Supervisor for execution sequencing.
- PIT-sensitive tasks (`T02`, `T07`, `T08`, `T10`) explicitly marked as audit gates.
- Resource envelope accepted by Ly before implementation begins.
