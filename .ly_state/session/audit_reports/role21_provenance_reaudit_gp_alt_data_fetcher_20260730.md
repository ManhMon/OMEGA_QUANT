# Role 21 Provenance Re-Audit - GP_ALT_DATA_FETCHER_OPTIMIZATION

- **Role**: `21 code-reviewer` (Codex L3 independent re-audit)
- **Date**: `2026-07-30`
- **Gate**: `GP_ALT_DATA_FETCHER_OPTIMIZATION`
- **L3 session ID**: `l3_role21_provenance_reaudit_gp_alt_data_fetcher_20260730`
- **L3 session key**: `l3_role21_provenance_reaudit_gp_alt_data_fetcher_20260730`
- **Scope**: provenance authority for recorded-vs-current original gate hash drift only
- **Write boundary**: this report only; no source, tests, phase gate, reconciliation ledger, lock, or L2 evidence modified

## Repo-Local Files Read

- `REPO_AGENT_ROOT=.agents/agent`
- `REPO_SKILL_ROOT=.agents/skills`

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

Role resolution passed: `role_id=21`, `tier=3`, `platform=Codex`, `role_name=code-reviewer`; read-only SOD boundary observed. Historical L2 writer is role `15 data-engineer`; reconciliation evidence writer is role `9 backend-engineer`; both differ from role 21.

## Evidence Examined

- `.ly_state/session/phase_gates.json`
- `scripts/sod_gate_enforcer.py`
- `tests/test_legacy_reconciliation_contract.py`
- `.ly_state/session/legacy_gate_reconciliation_20260727.json`
- `.ly_state/session/legacy_gate_reconciliation_20260727.sha256`
- `.ly_state/session/legacy_gate_reconciliation_retry2_20260727.json`
- `.ly_state/session/legacy_gate_reconciliation_retry2_20260727.sha256`
- `.ly_state/session/legacy_gate_reconciliation_retry3_20260727.json`
- `.ly_state/session/legacy_gate_reconciliation_retry3_20260727.sha256`
- `.ly_state/session/legacy_residual_reconciliation_20260727.json`
- `.ly_state/session/legacy_residual_reconciliation_20260727.sha256`
- `.ly_state/session/l2_role15_gp_alt_data_fetcher_optimization_20260708.md`
- `.ly_state/session/audit_reports/role21_gp_alt_data_fetcher_optimization_20260708.md`
- `.ly_state/session/l2_role9_legacy_gate_evidence_gp_alt_data_fetcher_optimization_20260727.md`
- `.ly_state/session/audit_reports/role21_legacy_reaudit_gp_alt_data_fetcher_optimization_20260727.md`
- `.ly_state/session/audit_reports/l3_role21_residual_reaudit_gp_alt_data_fetcher_optimization_20260727.md`
- `.ly_state/session/l2_role9_legacy_residual_closure_semantics_20260730.md`
- `.ly_state/session/audit_reports/role21_legacy_residual_closure_semantics_20260730.md`
- Git snapshots `78fd415d` and `ac4b4115` of `.ly_state/session/phase_gates.json`

## Exact Field-Level Drift

`load_canonical_gate_map()` synthesizes the top-level key as `phase_name` when the stored object omits that field. `_immutable_gate_record()` excludes only `LEGACY_MUTABLE_FIELDS`; it does not exclude `phase_name`.

Authoritative canonical immutable projection:

```json
{"l2_role_id":15,"l2_role_name":"data-engineer","l2_session_id":"l2_role15_gp_alt_data_fetcher_optimization_20260708","phase_name":"GP_ALT_DATA_FETCHER_OPTIMIZATION","status":"AUDIT_PASSED"}
```

SHA-256: `3021a6c615c4f106ea8188e93b00717aa8b181222cfc7b87530800f19918f679`.

Defective historical projection used by the July 27 residual evidence:

```json
{"l2_role_id":15,"l2_role_name":"data-engineer","l2_session_id":"l2_role15_gp_alt_data_fetcher_optimization_20260708","status":"AUDIT_PASSED"}
```

SHA-256: `bfd78b7b04379e9f1c6a168f922f4ddd781266c26c2cdcf7edabf9a62f4998d3`.

The sole field-level difference is the omitted synthesized field:

| Field | Canonical current/original record | Defective historical snapshot |
|---|---|---|
| `phase_name` | `"GP_ALT_DATA_FETCHER_OPTIMIZATION"` | absent |

No drift exists in `l2_role_id`, `l2_role_name`, `l2_session_id`, `status`, or `timestamp` (`null`).

## Authority Determination

The canonical metadata hash `3021a6c...` is authoritative.

1. `scripts/sod_gate_enforcer.py` defines canonical loading before immutable projection. The synthesized `phase_name` is therefore part of the record hashed by validators.
2. The initial reconciliation record and both append-only retry records independently store `original_gate_record_sha256=3021a6c...` for this gate.
3. Their locks match raw artifact bytes:
   - initial: `d29045a45c49ff42eaff77ae2b47995a8fe74e82ed52bdd1e14c394853e66e97`
   - retry2: `ffa6552d4aa5dc536cb839a42a0c4d3fd55c41f52c860d754da33f1bf5fff06f`
   - retry3: `8248295de899262b16a9efca5917c2d0c64be43547c089d7b5d86c9dcbc7bc16`
4. Retry2 names the initial artifact and predecessor lock; retry3 names retry2 and its predecessor lock. The chain is internally consistent.
5. Git snapshots `78fd415d` and `ac4b4115` produce the same canonical immutable projection and `3021a6c...` hash. Current metadata did not invent a new immutable value.
6. Historical L3 report bytes match recorded SHA-256 `7e0715bcf74ed34bea603f2aae3b190fcbd0717caebf4af30b048e2ad0384bba` and contain `[APPROVED]`; evidence-file integrity is not the source of drift.
7. The July 27 L2 evidence and pre-sidecar L3 report computed `bfd78b7b...` directly from the raw nested object, bypassing canonical key synthesis. The residual reconciliation record copied that non-canonical hash. Its lock proves byte integrity, not semantic authority.

## Validator Result And Consequence

Fresh command: `python scripts/sod_gate_enforcer.py` exits `1` with `residual reconciliation record GP_ALT_DATA_FETCHER_OPTIMIZATION original gate record hash drift`.

This failure is correct fail-closed behavior against the semantically defective residual record. It does not establish current gate metadata drift. The current gate must not be rewritten to reproduce `bfd78b7b...`; doing so would remove the canonical identity field from the projection model rather than restore provenance.

Operational closure still requires an L2-owned append-only successor artifact plus lock, superseding the residual reconciliation artifact without rewriting any existing ledger or lock. This audit approves the authority determination only; it does not approve closure publication or an enforcer bypass.

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: non-authoritative scan evidence only; no reliance.
- `.codex\memories`: non-authoritative scan evidence only; no reliance.

Matches are protocol constants, explicit scan evidence, or test fixtures. No forbidden-path role, skill, or audit source was read.

## Verdict

[APPROVED]

Authority is proven: `3021a6c615c4f106ea8188e93b00717aa8b181222cfc7b87530800f19918f679` is the authoritative original gate record hash. `bfd78b7b04379e9f1c6a168f922f4ddd781266c26c2cdcf7edabf9a62f4998d3` is a non-canonical historical projection caused solely by omitted synthesized `phase_name`.
