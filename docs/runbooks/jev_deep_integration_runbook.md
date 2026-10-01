# W7 isolated shadow operating runbook

Gate: `GATE_JEV_DEEP_INTEGRATION_W7_20260930`. Implementation owner: Role 11 devops-engineer, co-role 14 data-scientist. Engineering submission only; production readiness **not demonstrated**.

## Safe profile

- `src/omega/runner.py` defaults to `disabled`; explicit `replay`, `shadow`, `paper` use the same local simulator. No broker, provider, retraining or promotion API is connected. Live lambda is always zero.
- Dedicated `.db` state and sealed inputs/cache stay beneath `.ly_state/session/jev_deep_integration_20260926/W7/`. Parent directories must already exist. Absolute paths, traversal, linked paths and directory targets are rejected. Test roots are explicitly isolated.
- Current admission ceiling: 64 assets, 1 MiB JSON, 4,096 durable records, 256 telemetry samples, HOSE only, continuous-session limit/IOC simulation. Unsupported venues/profile changes require separately verified contracts.
- Input schema is `REQUEST_FIELDS` in `src/omega/pipeline/shadow_pipeline.py`. Every field is required; unknown fields fail closed. `signal` contains prior-observation alpha values and covariance. Supply explicit UTC/ICT timestamps, VND_FULL integer prices, PIT lifecycle/sector labels, synthetic initial cash, bound calendar hash and source revision. Unknown availability is invalid.
- Credential keys are casefolded with whitespace, hyphens and underscores removed before alias lookup. `client_secret`, `api-key`, `access_token`, refresh-token and private-key variants reject at whole-input ingress before request hashing, resource-state resets or storage. Nested keys and credential assignments in strings reject with static errors; safe field names remain unchanged in canonical bytes.
- Baseline is actual `PortfolioOptimizer.optimize_weights`, not equal-weight reconstruction. Asset/sector/exposure/drawdown validators run before simulation and again after overlays. Baseline reject/halt cannot be cleared by JEV.
- W1 cache consumption uses the existing envelope validator through a read-only, immutable, checkpointed SQLite lookup; a miss never calls a provider. Preparation of cache/source evidence is separately budgeted. Its synchronous validation inside `run` is included in the cycle clock.
- W3 counterfactual forensics, W2 four-state mapping, W6 calibrated posterior, W5 schedule primitives, W4 concentration advisory and W6 inert decay attribution execute in isolated B3 fixtures. W2 trained HMM arbitration, W5 matched-order tactic application and durable W4/W6 review publishing remain unqualified. This is not full W1–W6 production integration.
- B1/B2/B4 are disabled with explicit `missing` reasons. B3 zero lambda bypasses cache/solver; any nonzero B3 advisory-stage failure discards the entire proposal and uses immutable valid B0.

## Explicit L1 deferral — remediation disposition

The L1 task for `l2_role11_jev_w7_e2e_production_readiness_rem1_20261001` directs documentation of the W1-W6 full production-equivalence deferral. Source: `.ly_state/session/prompt_l2_role11_jev_w7_e2e_production_readiness_rem1_20261001.txt`, SHA-256 `7d60c76cfa0cdd89db679fdbad35d181eceaa865e8e616add757d07821fbbe1f`. This is a task-directed deferral to isolated offline engineering, not completed production acceptance or deployment permission. `metrics.json:l1_deferral` records the same disposition.

Deferred: full active-pipeline B0 equivalence; W1 provider acquisition/retries; W2 trained HMM arbitration; W4 durable advisory publication on Windows; W5 matched-parent-order tactic application; W6 durable review publication; B1/B2/B4 qualified economic controls, preregistered materiality/uncertainty, qualified historical/model-knowledge PIT and mature prospective outcomes. Existing fixture primitives remain research-only. Missing runtime components stay disconnected; B1/B2/B4 stay disabled. Economics remain inconclusive, `production_ready=false`, live lambda zero. Reconsideration requires separately qualified inputs, completed integration and independent review under L1 control.

## Offline operation

1. Seal eligible input and source/calendar/policy digests; verify strict UTF-8 JSON, no BOM/duplicate keys/non-finite values. Do not copy live credentials into the packet.
2. Use a fresh dedicated sandbox `.db`, or preserve the prior database plus any rollback journal before restarting. Keep one request per decision ID; conflicting IDs and nonmonotonic cutoffs are rejected.
3. Run from repository root:

   ```powershell
   python src/omega/runner.py --mode replay --input .ly_state/session/jev_deep_integration_20260926/W7/input.json --state .ly_state/session/jev_deep_integration_20260926/W7/shadow.db
   ```

   `input.json` above is operator-supplied, schema-validated data. It is not an automatically generated approval artifact. Output is one finite JSON decision; exit 2 indicates failure/rejection/uncommitted state/resource or deadline breach. Import-time legacy diagnostics go to stderr for this direct entry point.
4. Check `committed`, `readiness_within_limits`, outcome/reason, baseline/decision/parent digests and zero live influence. `simulation_applied` describes a local allocation proposal only. Proposed execution schedules are annotated, not applied as fills.
   `resource_usage` contains sampled `rss_bytes`, inclusive `cache_bytes`, `measurement_failed` and frozen `limits`; it is runtime diagnostics outside the economic digest. Measurement errors retain fail-closed limit+1 sentinels, not measured resource quantities. `cycle_seconds` includes final digest/telemetry bookkeeping.
5. Repeating an identical decision is a read-only replay with the same economic digest and no duplicate effects. Resume with later cutoffs after verifying prior-state integrity.

## Accounting and durability

- Integer VND cash, quantities, fee/tax rounded half-up to one VND. Bid/ask slippage/impact is embedded in fill price, not subtracted twice.
- Fills require eligible current book observations, continuous Vietnam sessions, active instruments, valid price bands/ticks/100-share lots. Volume participation <=10%; available depth, cash and settled shares bound quantities. Unfilled remainder is cancelled locally. No naked sells.
- Conservative settlement: second trading session 13:00 ICT. Purchased shares and sell proceeds stay restricted until eligible. Split/dividend actions are atomic and idempotent. Late first-seen actions lacking entitlement history reject instead of inventing cash/shares.
- Resulting receivables and each holding's pending queue must contain <=128 items after actions and fills, before baseline/proposal publication. An invalid baseline rolls back every SQLite table and exits 2; an invalid proposal falls back only to a validated baseline. Settlement can free capacity on a later eligible cutoff.
- Macro-news run manifests publish through unique same-directory temporary files, flush/fsync, close, `os.replace` and owned-file cleanup. Publication failure cannot return success; an existing manifest remains byte-complete. Windows concurrent replacement may fail a writer explicitly; no retry or partial write is hidden.
- SQLite `BEGIN IMMEDIATE`, timeout zero, rollback journal, `synchronous=FULL`, native connection-owned locks and unique decision/action keys publish ledger+decision as one transaction. No custom file lock can release a foreign owner. OS process exit releases its native lock.
- First-write failure yields no complete state; later failure retains the verified prior generation. Corrupt/missing/duplicate/mutated schemas or payloads integrity-stop. Commit acknowledgment errors reconcile against the actual complete transaction. No manual repair of digest/cash/weights.
- SQLite native durability is the publication primitive; there is no separate multi-file atomic replace. Power-loss/filesystem guarantees beyond SQLite on this Windows host remain unproven. The predecessor W4 durable advisory ledger requires POSIX.

## Telemetry

`pipeline.telemetry.snapshot()` exposes bounded JSON. `prometheus()` formats finite enum labels and fixed latency buckets; exporter I/O is outside the decision. Read maxima, not only percentiles:

| Signal | Frozen limit/action |
|---|---|
| Full cycle | <=2.0 seconds; breach means readiness not demonstrated |
| Process tree RSS | <=4,000,000,000 bytes; sampled before/after stages, maximum 64 children |
| Cache | <=500,000,000 bytes inclusive DB/WAL/SHM/journal and admitted classification cache |
| Retained allocations | <=2,000,000-byte allocator-noise envelope over 250-session drill |
| RSS plateau | <=20,000,000-byte first/last 50-session maximum difference |
| NAV residual | Exactly zero VND |
| Broker/provider/training/promotion calls | Zero connected capabilities |
| Fallback/integrity/storage | Stop proposal admissions; preserve deterministic B0 or reject |

Counters are local cycle events, not independent proof that all legacy import side effects are absent. Process RSS sampling can miss intra-stage spikes; source/cache preparation and cold startup are separate costs. Hard interruption of arbitrary slow NumPy/SQLite calls is not proven. Telemetry failure does not change allocation, risk or committed ledger.

F-004 **RESOLVED**: the initial rem3 endurance failure is classified as host resource/scheduler contention from concurrent parallel L3 audit probes executing during endurance, combined with unhandled `tracemalloc` teardown accumulation. Cycle-5 dispatch supplies the causal classification; the archived L3 record confirms overlapping probes but did not retain the breached-cycle measurements. The corrective change is exception-safe owned tracing teardown plus diagnostic telemetry and sequential execution: one pytest process, B0 then B3-fallback then B3-active, 250 ordered sessions each, seed 42, no overlapping L3 probes, worker tasks or parallel pytest workers. Finish all support workers before execution; run the scoped suite synchronously. The fixture owns one-frame `tracemalloc` only when tracing was initially off, releases it on assertion/exception, preserves inherited tracing. Failed cycles attach profile/cycle/decision, elapsed, sampled RSS/cache, limits and measurement status to assertions and JUnit. Repeated injected scheduler-delay aborts verify no tracing accumulation or committed-generation loss. The current report records exact 750-session measurements and the requested 2.5-second/1024-MiB/64-MiB comparisons; frozen runtime checks remain 2 seconds/4,000,000,000 RSS bytes/500,000,000 cache bytes.

## Hard resource and power-loss boundaries

The frozen numbers are admission checks and measured acceptance ceilings, not OS-enforced hard guarantees. `metrics.json:hard_boundaries` records these limits and their proof status.

| Boundary | Current enforcement / evidence | Unproven guarantee / required qualification |
|---|---|---|
| 2.0-second cycle, 0.1-second publication reserve | Monotonic checks around synchronous stages; SQLite progress handler every 1,000 VM operations; late pre-publication work rolls back | Blocking numerical calls, SQLite filesystem waits and commit fsync cannot be preempted. A late successful commit stays durable; final timing marks readiness false and CLI exits 2. Qualify a bounded supervised worker before claiming hard interruption. |
| 4,000,000,000-byte process-tree RSS; <=64 children | Before/after-stage and final samples reject observed excess; 750 three-asset fixture cycles | Intra-stage spikes, host/other-process memory and maximum 64-asset/64-view workload are not continuously bounded. No OS memory job/container limit is installed by this packet. Qualify supervisor limits and maximum-universe stress before hard-memory claims. |
| 500,000,000-byte inclusive cache; 60,000 DB pages | Samples include state DB/journal/WAL/SHM plus admitted sealed classification cache; storage failure rolls back an open transaction | Page cap bounds the DB, not all sidecar peaks or whole-host disk usage. No disk quota; preparation/output evidence are separately budgeted (10,000,000-byte packet). |
| Startup/preparation/physical recovery | Cycle timing starts inside `ShadowPipeline.run`; preparation separately sampled | Cold-start and physical-recovery maxima are unmeasured (`null`). No boot-to-result or instantaneous-recovery promise. |
| Local transaction crash recovery | Windows host, native SQLite rollback journal, `synchronous=FULL`; first/later-write faults, ambiguous acknowledgment and `os._exit(23)` restart drills | Process kill is not workstation power loss. Device flush/cache, torn writes, foreign/network filesystems and cross-host recovery are untested. No power-loss guarantee. |

For a breach: stop proposal admissions, retain verified committed state, use safe B0 or return an uncommitted/rejected result; CLI exits 2. If a commit completed before a late breach was detected, verify/replay that complete generation; never delete it to pretend rollback. After actual power loss, preserve DB **and** journal, restart with proposals disabled, verify schema/digests/accounting; corruption integrity-stops. Only storage-qualified power-cut/recovery evidence can support stronger durability claims. L1's task-directed scope disposition retains these unproven boundaries; it does not waive the ceilings or certify production readiness.

## Incident rollback

1. Record last verified run/arm/decision/source and database digest. Disable proposal admission using `--mode disabled`; preserve deterministic risk and lambda zero.
2. Stop the sandbox writer. Preserve the database and journal; never delete raw market history or production state. There are no outstanding paid calls/reservations in this offline profile.
3. Restart with the same compatible database. SQLite recovers a killed transaction; the coordinator verifies schema, state digest and latest committed decision consistency. Corrupt or missing prior state stops.
4. Replay the captured identical input offline. Verify decision digest, cash/positions/receivables, NAV residual and exactly-once fills. Logical B0 fallback and physical recovery latency are different measurements.
5. Keep proposals disabled until authorized independent review disposes of the blocker. A passing synthetic drill is neither economic merit nor deployment authority.

## Scoped verification and unresolved requirements

```powershell
python -m pytest --collect-only -q -o addopts="" tests/test_jev_e2e_production_readiness.py
python -m pytest tests/test_jev_e2e_production_readiness.py -o addopts="" --junitxml=.ly_state/session/jev_deep_integration_20260926/W7/rem5_w7.xml -o junit_family=legacy
python scripts/validate_l2_report.py l2_role11_jev_w7_e2e_production_readiness_rem5_20261001 11 devops-engineer
```

The plan's `-q` plus `-p no:terminal` combination exits 4 in this pytest environment; dropping `-q` preserves machine-readable test evidence. Master `checklist.py`/`verify_all.py` expose no scoped test selectors; full runs conflict with the test-scope directive. `validate_l2_report.py --pre-audit` invokes supplementary provider judgments; the deterministic structural validator is used here.

The related `_llm_final_exit_state` remediation validates nonnegative integer counters, treats any extraction failure as non-success and retains upstream source failure when extraction succeeds or makes zero attempts. Metrics cannot overwrite unrelated manifest state. Exceptions retain credential-safe error types. Exact executed test results are in `metrics.json` and `matrix_evidence.md`.

Structural validator: `PASS`, exit `0`, reconciled date `2026-10-01`.

The historical rem2 report `.ly_state/session/l2_role11_jev_w7_e2e_production_readiness_rem2_20261001.md` preserves Date `2026-10-01`, matching session suffix `20261001`. Its earlier exit-1/date-mismatch output remains historical evidence in that report and `metrics.json:mechanical_validation_history`. Current cycle 3 report: `.ly_state/session/l2_role11_jev_w7_e2e_production_readiness_rem3_20261001.md`; F-001 pending-ledger bound, F-002 atomic macro manifest, F-003 immutable packet bindings. Current mutable L3 audit report is excluded from immutable L2 evidence; sealed bytes still reject tampering. Source finding digest remains in the unchanged anti-drip contract. Final candidate/evidence hashes resealed after report publication. Structural PASS is an L2 format check; the gate still awaits independent disposition. Full production equivalence, economics and hard resource/power-loss guarantees remain deferred/unproven above.

Historical cycle-4 report: `.ly_state/session/l2_role11_jev_w7_e2e_production_readiness_rem4_20261001.md`; 1,519 related tests passed, 21 inherited Windows skips, W7 205 passed. Its unclassified F-004 disposition is superseded by cycle 5. Current report: `.ly_state/session/l2_role11_jev_w7_e2e_production_readiness_rem5_20261001.md`; F-004 **RESOLVED** by contention classification, tracing cleanup, diagnostics and sequential 750-session evidence; F-005 **RESOLVED** within scoped ingress by alias normalization and pre-digest rejection. Candidate/evidence bindings are resealed in `input_manifest.json`; mutable current L3 output is excluded. These are L2 remediation dispositions; independent gate disposition remains with L3.
