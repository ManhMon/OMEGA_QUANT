# L2 Role 9: Legacy Gate Date Policy

- Session: `l2_role9_legacy_gate_date_policy_20260727`
- Role: `9 backend-engineer` (`OpenCode` L2)
- Date: `2026-07-27`
- Mode: read-only discovery; this report is the only new file written.
- Decision: no gate metadata, source, tests, data, config, phase-gate, or historical report edits.

## Authority And Scope

Reviewed the approved legacy migration baseline and its independent inventory audit:

- `.ly_state/session/legacy_gate_global_migration_20260727.md`
- `.ly_state/session/l2_role9_legacy_gate_global_inventory_20260727.md`
- `.ly_state/session/l2_role9_legacy_gate_global_inventory_fix1_20260727.md`
- `.ly_state/session/audit_reports/l3_role21_legacy_gate_global_inventory_fix1_reaudit_20260727.md`
- `.ly_state/session/phase_gates.json`
- `scripts/sod_gate_enforcer.py`
- `scripts/sod_report_evidence.py`
- `scripts/phase_workflow_enforcer.py`

The migration manifest is inventory evidence, not approval or authorization to mutate historical state. Its 9 `date_mismatch` and 4 `missing_gate_or_timestamp_date` records are the complete date-failure set. The 13 `missing_l3_session_key` records are analyzed separately below.

## Enforcer Contract

`scripts/sod_gate_enforcer.py` resolves the policy date before report wording validation:

1. `_gate_key_date()` accepts one valid trailing `YYYYMMDD` selector in the gate key.
2. `resolve_gate_date()` parses `gate_record["timestamp"]` only when present; it requires an ISO-8601 timestamp with `Z` or an explicit offset.
3. If both dates exist, they must be equal. Otherwise it returns `gate key date and timestamp date mismatch`.
4. If neither exists, it returns `gate key date or valid timestamp date is required`.
5. Only after resolution does `check_report_evidence_wording()` call `validate_report_evidence()`.

`scripts/sod_report_evidence.py` permits a report filename date equal to or newer than the resolved gate date. It does not override gate-date resolution. Therefore a truthful current audit timestamp or a new append-only L3 report cannot repair either gate-record failure while preserving the original key and timestamp.

## Date-Failure Matrix

| Gate | Gate-key date | Existing gate timestamp date | Failure | Append-only current L3 report while preserving metadata | Allowed next action |
|---|---:|---:|---|---|---|
| `GP_PRODUCTION_VALIDATION_GATE6_20260704` | 2026-07-04 | 2026-07-26 | mismatch | **No**; resolution fails first | L1 policy decision, then scoped L3 re-audit only after an approved compatibility rule or metadata repair |
| `GP_OVERFITTING_REMEDIATION_GATE4_20260704` | 2026-07-04 | 2026-06-26 | mismatch | **No**; resolution fails first | Same |
| `HYBRID_REGIME_DYNAMIC_BRAKE_FIX_20260621` | 2026-06-21 | 2026-06-22 | mismatch | **No**; resolution fails first | Same |
| `RECOVERY_SELECTOR_OPT_IN_20260614` | 2026-06-14 | 2026-06-19 | mismatch | **No**; resolution fails first | Same |
| `VNSTOCK_LATEST_STANDARDIZATION_20260612` | 2026-06-12 | 2026-06-11 | mismatch | **No**; resolution fails first | Same |
| `LABEL_HORIZON_SWEEP_ENSEMBLE_20260623` | 2026-06-23 | 2026-06-24 | mismatch | **No**; resolution fails first | Same |
| `VN_ALPHA_GMM_SMOOTH_TRANSITION_20260624` | 2026-06-24 | 2026-06-25 | mismatch | **No**; resolution fails first | Same |
| `LATENT_ALPHA_MINING_64D_20260617` | 2026-06-17 | 2026-06-28 | mismatch | **No**; resolution fails first | Same |
| `GP_CLAUDE_IDEAS_UPGRADE_20260702` | 2026-07-02 | 2026-07-03 | mismatch | **No**; resolution fails first | Same |
| `GP_V4_IMPLEMENTATION` | none | none | missing key/timestamp date | **No**; no policy date can be resolved | L1 must choose truthful metadata repair or explicit legacy exception policy |
| `GP_V4_ADVANCED_IMPLEMENTATION` | none | none | missing key/timestamp date | **No**; no policy date can be resolved | Same |
| `GP_NUMBA_JIT_VM_IMPLEMENTATION` | none | 2026-07-05 | missing key date only, but baseline class says missing gate/timestamp date | **No** under preserved key/timestamp if report is pre-resolved against absent key; timestamp is present in current JSON, so validate exact current baseline before remediation | L1 rechecks baseline; do not infer approval or edit metadata |
| `GP_ALT_DATA_FETCHER_OPTIMIZATION` | none | none | missing key/timestamp date | **No**; no policy date can be resolved | L1 triage; compound with missing `l3_session_key` |

### Date conclusions

- A new report named with `20260727` can satisfy the report-selector rule only after a gate date is successfully resolved. It cannot make an old gate timestamp truthful, nor can it supply a missing gate date to the current resolver.
- Reusing the original report path is not append-only and would violate the requested preservation model. A new report also cannot change the gate record selected by `phase_gates.json`.
- `GP_NUMBA_JIT_VM_IMPLEMENTATION` is an inventory ambiguity: current JSON has timestamp `2026-07-05T07:35:39.9987041+07:00` and no gate-key date. The current resolver can use that timestamp date; the recorded baseline still requires direct re-check before any action. No repair is authorized here.

## 13 `l3_session_key` Workflow Gaps

`scripts/phase_workflow_enforcer.py:70-75` requires `l3_session_key` as a field in each gate record. It does not inspect an append-only report for a substitute. The 13 exact failures are:

| Gate | Key available in report/record? | Append-only reconciliation report sufficient? | Allowed next action |
|---|---|---|---|
| `GP_ALTERNATIVE_FEATURES_MEMORY_FIX` | No gate field | **No** | L1 obtains truthful L3 session key; scoped metadata update only through protocol |
| `GP_ALT_DATA_FETCHER_OPTIMIZATION` | No gate field | **No**; also date compound | L1 resolves date policy and key separately |
| `GP_ALT_FEATURES_OVERLAP_AND_OOM_FIX` | No gate field | **No** | Same |
| `GP_DIVERSITY_ORTHO_PENALTY_20260702` | No gate field | **No** | Same |
| `GP_EVOLUTION_BACKEND_LOKY_20260702` | No gate field | **No** | Same |
| `GP_PARALLEL_OPTIMIZATION_20260705` | No gate field | **No** | Same |
| `GP_PRODUCTION_RUN_CODE_AUDIT` | `l3_session_id` is `none`; key absent | **No** | Recover truthful L3 session evidence; no fabricated key |
| `GP_PRODUCTION_RUN_WORKFLOW_SETUP` | `l3_session_id` is `none`; key absent | **No** | Same |
| `GP_V4_ADVANCED_IMPLEMENTATION` | `l3_session_id` is `none`; key absent; date gap too | **No** | Resolve both independent contract gaps |
| `GP_V4_ADVANCED_PLAN_REVIEW` | No gate field; date present | **No** | Truthful key recovery or scoped protocol remediation |
| `GP_V4_IMPLEMENTATION` | `l3_session_id` is `none`; key absent; date gap too | **No** | Resolve both independent contract gaps |
| `GP_V4_OPTIMIZATION_PLAN_REVIEW` | No gate field; date present | **No** | Truthful key recovery or scoped protocol remediation |
| `GP_VN_ALPHAS_MEMORY_FIX` | No gate field | **No** | Truthful key recovery or scoped protocol remediation |

These are workflow-contract failures, not date failures. A report may document a recovered key, but the current workflow enforcer will continue to fail until the gate field exists. A fabricated or inferred key is not truthful reconciliation.

## Minimal Safe Policy Proposal

No code change proposed in this session. The smallest safe future policy change is an explicit, append-only legacy reconciliation sidecar consumed by both enforcers, with these constraints:

- allowlist exact gate key and immutable original gate-record hash;
- store `resolved_gate_date`, `original_timestamp`, `reconciliation_timestamp`, reason, source report path, and L3 session identity;
- accept a mismatch only when the sidecar proves the original gate record hash and L3 independently attests the historical date decision;
- accept missing date only when an authoritative source establishes exactly one date; otherwise hard-fail;
- accept `l3_session_key` only from an actual L3 audit/session record, never generated from the current timestamp;
- preserve current behavior for non-allowlisted and newly created gates;
- require L1 authorization, independent L3 approval, sidecar hash verification, and both enforcers exit `0`.

Contract gap: the current enforcers have no reconciliation input. They read only `phase_gates.json` for gate dates/keys and report files for evidence. Until this sidecar contract exists or metadata is truthfully repaired through the normal SOD flow, no append-only report can satisfy these failures.

## Verification And Scope

- Baseline evidence: `python scripts/sod_gate_enforcer.py --check-before-push` exit `1`; date failures preserved.
- Workflow evidence: `python scripts/phase_workflow_enforcer.py --check-all` exit `1`; 13 failures, each missing `l3_session_key`.
- No enforcer run after this report was needed; this report does not change the evaluated state.
- No phase gate, history, source, test, data, config, or audit file edited.

## Repo-Local Files Read

- `REPO_AGENT_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`
- `REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`
- `.agents/AGENTS.md`
- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `scripts/sod_gate_enforcer.py`
- `scripts/sod_report_evidence.py`
- `scripts/phase_workflow_enforcer.py`
- `.ly_state/session/phase_gates.json`
- `.ly_state/session/legacy_gate_global_migration_20260727.md`
- `.ly_state/session/l2_role9_legacy_gate_global_inventory_20260727.md`
- `.ly_state/session/l2_role9_legacy_gate_global_inventory_fix1_20260727.md`
- `.ly_state/session/audit_reports/l3_role21_legacy_gate_global_inventory_20260727.md`
- `.ly_state/session/audit_reports/l3_role21_legacy_gate_global_inventory_fix1_reaudit_20260727.md`

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: non-authoritative scan evidence only; no reliance.
- `.codex\memories`: non-authoritative scan evidence only; no reliance.

## Verdict

`NEEDS_FIX` for enforcement state. Diagnosis complete. No historical gate approval inferred. No metadata repair performed.
