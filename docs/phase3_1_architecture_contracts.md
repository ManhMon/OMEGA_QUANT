# Phase 3.1 Architecture Contracts: Alpha Discovery

**Role**: Architecture Supervisor (Role 3)  
**Date**: 2026-05-10  
**Scope**: Phase 3.1 Alpha Discovery Engine contracts only. No implementation.  
**References**: `packages/core/src/omega/core/trainer.py`, `packages/core/src/omega/core/validator.py`, `packages/core/src/omega/core/promotion.py`, `packages/quant/src/omega/quant/alpha_discovery.py`, `docs/phase3_1_task_breakdown.md`

## 1. Purpose

Phase 3.1 splits current monolithic `alpha_discovery.py` into explicit modules with stable, versioned contracts. Design goal:

- keep discovery orchestration thin
- move PIT-sensitive logic into dedicated modules
- reuse Phase 2.3 temporal-validation semantics
- persist discovery state to files, not RAM
- fail closed on missing timestamps, invalid windows, or incomplete metrics

## 2. Module Interfaces

### 2.1 `packages/quant/src/omega/quant/alpha_discovery.py`

Top-level orchestrator. Owns run lifecycle only.

**Primary interface**

```python
class AlphaDiscoveryEngine:
    def run(self, request: DiscoveryRunRequest) -> list[AlphaRegistryEntry]: ...
```

**Responsibilities**

- validate `DiscoveryRunRequest`
- obtain PIT-safe source panel for requested dataset snapshot
- call `walk_forward_engine` once per run
- call `expression_generator` to create bounded candidate set
- call `label_engine` and `alpha_scoring` for each candidate/window/horizon
- write accepted candidates to `alpha_registry`
- call `decay_monitor` for existing active alphas after run closes
- return promoted or staged registry entries, never raw in-memory dicts

**Must not own**

- operator semantics
- label construction rules
- walk-forward math
- promotion-policy logic
- persistent storage format details

### 2.2 `packages/quant/src/omega/quant/alpha_primitives.py`

Pure, PIT-safe expression primitives and panel guards.

**Primary interface**

```python
def validate_panel_index(panel: pd.Series | pd.DataFrame) -> None: ...
def ensure_series(value: pd.Series | pd.DataFrame) -> pd.Series: ...
def lag_base_panel(panel: pd.DataFrame, periods: int = 1) -> pd.DataFrame: ...
def enforce_pit_snapshot(panel: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame: ...
def get_safe_function_table() -> dict[str, callable]: ...
```

**Contract**

- all expression inputs must be MultiIndex `[timestamp, symbol]`
- all base features exposed to expressions are already lagged by at least `1` bar
- primitives are deterministic and side-effect free
- any malformed panel, timezone mismatch, or missing index level raises hard error

### 2.3 `packages/quant/src/omega/quant/label_engine.py`

Builds horizon-specific labels and label-availability timestamps.

**Primary interface**

```python
class LabelEngine:
    def build_labels(
        self,
        panel: pd.DataFrame,
        request: DiscoveryRunRequest,
    ) -> pd.DataFrame: ...
```

**Output contract**

- returns row-aligned label frame indexed by `[timestamp, symbol]`
- includes per-horizon columns:
  - `target_{h}d`
  - `target_{h}d_available_at`
- supports horizons from `request.horizons`
- label rows without legal future path remain `NaN` and are excluded downstream

### 2.4 `packages/quant/src/omega/quant/expression_generator.py`

Generates bounded, reproducible candidate expressions.

**Primary interface**

```python
class ExpressionGenerator:
    def generate(self, request: DiscoveryRunRequest) -> list[DiscoveryCandidate]: ...
```

**Contract**

- deterministic for same `request.seed`, operator set, base features, and budget
- never emits operators outside request allowlist
- never emits lag `0` or negative lag
- normalizes expression string before candidate ID/hash generation
- generation failure of one candidate does not corrupt run state

### 2.5 `packages/quant/src/omega/quant/alpha_scoring.py`

Scores candidates on coverage, IC, and promotion-readiness metrics.

**Primary interface**

```python
class AlphaScorer:
    def score_candidate(
        self,
        candidate: DiscoveryCandidate,
        factor: pd.Series,
        labels: pd.DataFrame,
        windows: list["WalkForwardWindowSpec"],
        request: DiscoveryRunRequest,
    ) -> ScoringResult: ...
```

**Contract**

- performs PIT checks before scoring
- computes per-window, per-horizon metrics
- aggregates metrics into single `ScoringResult`
- records failures explicitly instead of returning partial silent success
- screening threshold belongs here, not in orchestrator

### 2.6 `packages/quant/src/omega/quant/alpha_registry.py`

File-backed registry for discovered alphas and run metadata.

**Primary interface**

```python
class AlphaRegistry:
    def upsert_entry(self, entry: AlphaRegistryEntry) -> AlphaRegistryEntry: ...
    def get_entry(self, alpha_id: str) -> AlphaRegistryEntry | None: ...
    def list_active(self) -> list[AlphaRegistryEntry]: ...
    def mark_retired(self, alpha_id: str, reason: str, retired_at: pd.Timestamp) -> AlphaRegistryEntry: ...
    def append_run_audit(self, run_id: str, payload: dict[str, object]) -> None: ...
```

**Contract**

- storage is append-safe and recoverable after process restart
- registry state is canonical source for candidate lifecycle
- no caller may rely on transient engine memory for active-alpha universe
- failed writes must be surfaced to caller; no best-effort silent skip

### 2.7 `packages/quant/src/omega/quant/decay_monitor.py`

Compares current out-of-sample scores against discovery baseline.

**Primary interface**

```python
class AlphaDecayMonitor:
    def evaluate(
        self,
        active_entries: list[AlphaRegistryEntry],
        latest_scores: list[ScoringResult],
    ) -> list[dict[str, object]]: ...
```

**Contract**

- compares baseline IC versus latest IC by horizon
- triggers retirement on sign flip or configured decay breach
- fail-closed if baseline metrics missing

### 2.8 `packages/core/src/omega/core/walk_forward_engine.py`

Shared temporal split builder for discovery evaluation.

**Primary interface**

```python
class WalkForwardEngine:
    def build_windows(
        self,
        request: DiscoveryRunRequest,
        available_dates: list[pd.Timestamp],
    ) -> list["WalkForwardWindowSpec"]: ...

    def validate_windows(
        self,
        windows: list["WalkForwardWindowSpec"],
        max_horizon: int,
    ) -> None: ...
```

**Reference alignment**

- `trainer.py` establishes non-overlap and temporal split ownership
- Phase 3.1 contract tightens rule to explicit unified embargo:
  `validation_start >= train_end + max_horizon + 1 trading bars`

### 2.9 `packages/core/src/omega/core/promotion_gate.py`

Promotion-policy adapter for alpha candidates.

**Primary interface**

```python
class PromotionGate:
    def evaluate_candidate(
        self,
        entry: AlphaRegistryEntry,
        scoring_result: ScoringResult,
        windows: list["WalkForwardWindowSpec"],
    ) -> dict[str, object]: ...
```

**Reference alignment**

- keep fail-closed behavior from `promotion.py`
- keep unified embargo rule from `promotion.py`
- keep minimum metric checks at promotion boundary
- filename may remain `promotion.py` during migration, but public contract name is `PromotionGate`

## 3. Data Schemas

All schemas are logical contracts. Storage format may be JSON or parquet-backed metadata, but field names and meanings stay stable.

### 3.1 `DiscoveryRunRequest`

| Field | Type | Required | Notes |
|:--|:--|:--|:--|
| `run_id` | `str` | Yes | Unique discovery run identifier |
| `dataset_id` | `str` | Yes | Immutable dataset snapshot or artifact ID |
| `dataset_uri` | `str` | Yes | File/artifact path used by run |
| `as_of` | `datetime` | Yes | Decision timestamp for run snapshot |
| `available_at_cutoff` | `datetime` | Yes | Max legal availability timestamp for rows consumed in this run |
| `horizons` | `list[int]` | Yes | Default `[3, 5]` |
| `min_train_days` | `int` | Yes | Walk-forward training window length |
| `min_validation_days` | `int` | Yes | Walk-forward validation window length |
| `test_size_days` | `int` | Yes | Reserved holdout region excluded from discovery scoring |
| `expression_budget` | `int` | Yes | Max candidate count for run |
| `max_expression_depth` | `int` | Yes | Bounded expression complexity |
| `base_features` | `list[str]` | Yes | Allowed raw feature names |
| `operator_allowlist` | `list[str]` | Yes | Allowed expression operators |
| `lag_allowlist` | `list[int]` | Yes | Allowed positive lags only |
| `min_coverage` | `float` | Yes | Minimum non-null fraction after factor generation |
| `screening_ic_threshold` | `float` | Yes | Discovery-stage IC threshold |
| `seed` | `int` | Yes | Deterministic generation seed |
| `registry_uri` | `str` | Yes | File-backed registry destination |
| `request_version` | `str` | Yes | Contract version for reproducibility |

**Invariants**

- `available_at_cutoff <= as_of`
- all horizons are positive integers
- `expression_budget > 0`
- `max_expression_depth >= 1`
- `0 < min_coverage <= 1`
- `screening_ic_threshold >= 0`

### 3.2 `DiscoveryCandidate`

| Field | Type | Required | Notes |
|:--|:--|:--|:--|
| `candidate_id` | `str` | Yes | Stable hash of normalized expression + request version |
| `run_id` | `str` | Yes | Parent discovery run |
| `expression` | `str` | Yes | Human-readable expression |
| `normalized_expression` | `str` | Yes | Canonicalized string used for dedupe |
| `base_features_used` | `list[str]` | Yes | Resolved raw inputs |
| `operators_used` | `list[str]` | Yes | Operators present in expression |
| `max_lag` | `int` | Yes | Largest lag consumed by expression |
| `seed` | `int` | Yes | Seed that generated candidate |
| `generation_order` | `int` | Yes | Stable order inside run |
| `status` | `str` | Yes | `generated`, `scored`, `rejected`, `staged`, `promoted`, `retired` |
| `created_at` | `datetime` | Yes | Candidate creation timestamp |

**Invariants**

- `max_lag >= 1`
- `normalized_expression` is unique within `run_id`
- `status` transitions are monotonic through registry lifecycle

### 3.3 `ScoringResult`

| Field | Type | Required | Notes |
|:--|:--|:--|:--|
| `candidate_id` | `str` | Yes | Candidate being scored |
| `run_id` | `str` | Yes | Parent discovery run |
| `pit_safe` | `bool` | Yes | False on any timestamp violation |
| `leakage_detected` | `bool` | Yes | Output from validator-style checks |
| `coverage` | `float` | Yes | Aggregate non-null ratio |
| `window_count` | `int` | Yes | Number of scored walk-forward windows |
| `horizon_metrics` | `dict[str, dict[str, float]]` | Yes | Per-horizon metrics bundle |
| `mean_ic` | `float` | Yes | Aggregate IC across legal windows |
| `mean_sharpe` | `float` | No | Optional if strategy-return proxy exists |
| `ic_std` | `float` | No | Optional dispersion for stability |
| `p_value` | `float` | No | Optional significance estimate |
| `min_required_embargo_days` | `int` | Yes | Usually `max(horizons) + 1` |
| `screening_pass` | `bool` | Yes | Discovery-stage threshold result |
| `promotion_eligible` | `bool` | Yes | Result after gate evaluation |
| `failure_reason` | `str | null` | No | Hard-error reason on fail-closed path |
| `scored_at` | `datetime` | Yes | Scoring completion timestamp |

**`horizon_metrics` required keys per horizon**

- `ic`
- `coverage`
- `window_count`
- `pass_rate`

**Optional keys per horizon**

- `sharpe`
- `p_value`
- `ic_std`

### 3.4 `AlphaRegistryEntry`

| Field | Type | Required | Notes |
|:--|:--|:--|:--|
| `alpha_id` | `str` | Yes | Canonical alpha identifier; may equal promoted `candidate_id` |
| `candidate_id` | `str` | Yes | Source candidate |
| `run_id` | `str` | Yes | Discovery run that created baseline |
| `expression` | `str` | Yes | Persisted alpha formula |
| `status` | `str` | Yes | `staged`, `validated`, `promoted`, `retired`, `rejected` |
| `request_version` | `str` | Yes | Contract version used at discovery time |
| `baseline_metrics` | `dict[str, dict[str, float]]` | Yes | Discovery-time per-horizon baseline |
| `latest_metrics` | `dict[str, dict[str, float]]` | No | Most recent post-promotion metrics |
| `promotion_metadata` | `dict[str, object]` | No | Gate decision, windows, thresholds |
| `decay_policy` | `dict[str, float]` | Yes | Includes min decay ratio and sign-flip rule |
| `source_dataset_id` | `str` | Yes | Provenance link |
| `registry_path` | `str` | Yes | Physical storage location |
| `created_at` | `datetime` | Yes | Initial write timestamp |
| `promoted_at` | `datetime | null` | No | Set only on promotion |
| `retired_at` | `datetime | null` | No | Set only on retirement |
| `retirement_reason` | `str | null` | No | Filled when retired |

**Invariants**

- `baseline_metrics` cannot be empty for `staged`, `validated`, or `promoted`
- `promoted_at` required when `status == "promoted"`
- `retired_at` and `retirement_reason` required when `status == "retired"`
- registry write is authoritative source of lifecycle state

## 4. PIT Safety Contract

### 4.1 Canonical timestamp meanings

- `as_of`: timestamp label for event or observation in market time
- `available_at`: earliest timestamp when row may legally be consumed by engine
- `available_at_cutoff`: run-level legal upper bound for consumed rows

### 4.2 Hard invariants

For every consumed row:

```text
row.as_of <= row.available_at <= request.available_at_cutoff <= request.as_of
```

For every prediction or score generated at timestamp `t`:

```text
feature_row.available_at <= t
label_row.available_at <= scoring_window.validation_end
```

### 4.3 Consumption rules

- base features exposed to candidate expressions are shifted by at least `T-1`
- expression evaluation never sees unlagged raw panel
- rows missing either `as_of` or `available_at` are rejected
- mixed timezone rows are rejected
- PIT violation is hard failure, not warning

### 4.4 Label availability rules

For horizon `h`:

- label return spans future interval implied by horizon
- label is not consumable until all prices needed for target are observable
- contract uses conservative rule:
  `target_{h}d_available_at = as_of + h + 1 trading bars`

Examples:

- `T+3` label becomes available at `T+4`
- `T+5` label becomes available at `T+6`

This matches Phase 2.3 promotion embargo intent and Phase 3 system plan.

## 5. Walk-Forward Window Contract

### 5.1 `WalkForwardWindowSpec`

Supporting schema used by `walk_forward_engine` and `promotion_gate`.

| Field | Type | Required | Notes |
|:--|:--|:--|:--|
| `window_id` | `str` | Yes | Stable identifier |
| `horizon` | `int` | Yes | Horizon scored in this window |
| `train_start` | `datetime` | Yes | Inclusive |
| `train_end` | `datetime` | Yes | Inclusive |
| `embargo_end` | `datetime` | Yes | Last timestamp blocked after training |
| `validation_start` | `datetime` | Yes | Inclusive |
| `validation_end` | `datetime` | Yes | Inclusive |
| `test_partition` | `bool` | Yes | True only for reserved holdout windows |

### 5.2 Window invariants

- `train_start <= train_end < embargo_end < validation_start <= validation_end`
- unified embargo rule:
  `validation_start >= train_end + max_horizon + 1 trading bars`
- validation windows for same horizon must be non-overlapping
- promotion-evaluated validation windows across compared horizons must also be non-overlapping
- reserved final test region is never used for discovery-stage thresholding
- empty window set is invalid and must fail closed

### 5.3 Generation policy

- `walk_forward_engine` owns window generation; other modules consume immutable output
- window construction uses chronologically sorted trading dates only
- training/validation split sizes come from `DiscoveryRunRequest`
- all candidates in same run must use same window set
- if dataset cannot support requested train/validation/test sizes after embargo, run fails before candidate generation

### 5.4 Reference note

`trainer.py` already owns temporal splitting. Phase 3.1 extracts this into shared `walk_forward_engine.py` and makes embargo contract explicit so discovery, validation, and promotion all consume same rule.

## 6. Promotion Gate Contract

### 6.1 Gate purpose

Promotion gate converts scored discovery output into controlled lifecycle transition. It is stricter than discovery screening.

### 6.2 Required inputs

- `AlphaRegistryEntry`
- `ScoringResult`
- full list of scored `WalkForwardWindowSpec`

Missing any required input must return fail-closed rejection.

### 6.3 Hard gate rules

1. PIT safety must pass.
2. Leakage detection must be negative.
3. Unified embargo must hold for every validation window.
4. Validation windows must be non-overlapping.
5. Metrics must satisfy minimum thresholds.
6. Registry entry must contain baseline provenance and contract version.

### 6.4 Default thresholds

Default promotion thresholds inherit current `promotion.py` semantics:

- `mean_ic > 0.10`
- `mean_sharpe > 1.5` when Sharpe is available

Phase-level policy may tighten thresholds, for example toward super-plan target `IC > 0.15`, without changing interface shape.

### 6.5 Gate output

`evaluate_candidate(...)` returns policy payload with at least:

| Field | Type | Meaning |
|:--|:--|:--|
| `approved` | `bool` | Promotion decision |
| `status` | `str` | `validated`, `promoted`, or `rejected` |
| `reason_codes` | `list[str]` | Fail-closed explanations |
| `required_embargo_days` | `int` | Applied unified embargo |
| `checked_window_ids` | `list[str]` | Windows evaluated |
| `checked_thresholds` | `dict[str, float]` | Thresholds used |
| `evaluated_at` | `datetime` | Gate timestamp |

### 6.6 Fail-closed behavior

Any of below returns rejection:

- parse error on dates
- missing metrics
- empty validation windows
- `NaN` in required metrics
- missing baseline registry state
- overlapping windows
- embargo shortfall by even one trading bar

## 7. Boundary Decisions

- `alpha_discovery.py` remains orchestration-only after refactor.
- `validator.py` remains reference for PIT and leakage semantics, but Phase 3.1 scoring path consumes equivalent checks through `alpha_scoring.py` plus `walk_forward_engine.py`.
- `promotion.py` remains migration reference; public contract name becomes `PromotionGate`.
- file-backed registry is mandatory because active alpha universe cannot live only in RAM.

## 8. Handoff Constraints For Implementation

- do not widen interface ownership beyond contracts above
- do not place PIT logic in UI/orchestrator layer
- do not use in-memory-only alpha state
- do not let promotion logic bypass shared walk-forward windows
- do not silently coerce missing timestamps or invalid windows
