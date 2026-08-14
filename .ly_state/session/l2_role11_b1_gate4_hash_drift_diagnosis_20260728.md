# Gate4 Residual Hash Drift Diagnosis

## Identity

- Session: `l2_role11_b1_gate4_hash_drift_diagnosis_20260728`
- Role: `11 devops-engineer` (OpenCode L2)
- Gate: `GP_OVERFITTING_REMEDIATION_GATE4_20260704`
- Date: `2026-07-28`
- Status: `NEEDS_FIX`
- Scope: read-only diagnosis; no production, test, phase-gate, manifest, or audit mutation

## Source Contract

Authoritative repo-local files read:

- `.agents/AGENTS.md`
- `.agents/agent/devops-engineer.md`
- `.agents/skills/deployment-procedures/SKILL.md`
- `.agents/skills/server-management/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `scripts/sod_gate_enforcer.py`
- `scripts/verify_legacy_gate_manifest.py`
- `.ly_state/session/phase_gates.json`
- `.ly_state/session/legacy_residual_reconciliation_20260727.json`
- `.ly_state/session/legacy_gate_reconciliation_20260727.json`
- `.ly_state/session/legacy_gate_reconciliation_retry2_20260727.json`
- `.ly_state/session/legacy_gate_reconciliation_retry3_20260727.json`
- `.ly_state/session/legacy_gate_migration_b1_manifest_20260728.json`
- `.ly_state/session/l2_role9_b1_manifest_20260728.md`
- `.ly_state/session/l2_role16_b1_gate4_reconcile_20260728.md`
- `.ly_state/session/audit_reports/role21_b1_gate4_reaudit_20260728.md`
- `.ly_state/session/audit_reports/l3_role21_residual_reaudit_gp_overfitting_remediation_gate4_20260704_20260727.md`
- `.ly_state/session/l2_role9_legacy_gate_reconciliation_gp_overfitting_remediation_gate4_20260704_20260726.md`

Forbidden-path scan: no forbidden path used as an authoritative source. Forbidden paths were considered only as non-authoritative scan evidence.

## Reproduction

`scripts/sod_gate_enforcer.py` defines `_immutable_gate_record()` as the current Gate4 object with mutable L3/reconciliation fields removed. Both residual validators then compare:

```text
sha256(_immutable_gate_record(current_phase_gates[Gate4]))
== record["original_gate_record_sha256"]
```

Observed Gate4 values:

| Value | Observed |
|---|---|
| Residual record | `.ly_state/session/legacy_residual_reconciliation_20260727.json` → `records[GP_OVERFITTING_REMEDIATION_GATE4_20260704]` |
| Stored original hash | `a406d7bfda3ab8c312bcfe4e7ed97973535c4d9a1a6beb6bb3016da98651ed66` |
| Current computed immutable hash | `be0861d7e1bfc40685e6f483d64887bcf817f0315587f7e6a7096700f9e6433f` |
| Current Gate4 timestamp | `2026-06-26T06:36:11.4153000+07:00` |
| Residual original timestamp | `2026-06-26T06:36:11.4153000+07:00` |
| Residual class | `gate_date_mismatch` |
| Enforcer failure | `residual reconciliation record GP_OVERFITTING_REMEDIATION_GATE4_20260704 original gate hash drift` |

The timestamp comparison passes. The original-record hash comparison fails.

## Root Cause

1. The residual record stores an “original” canonical gate hash.
2. Gate4 subsequently received a legitimate L3 reconciliation update in `phase_gates.json`: L2 session/role, L3 session/key/role, audit report path, verdict, repo-local source evidence, and forbidden-path evidence changed.
3. The enforcer removes those fields before hashing, so those mutable-field changes alone should not invalidate the hash.
4. The verifier still derives the supposedly original record from the mutable current `phase_gates.json`, rather than from an immutable original snapshot.
5. Therefore, current mutable state is being used as historical provenance. The stored residual hash (`a406...`) cannot be reconstructed from the current Gate4 entry under the enforcer’s current canonicalization, producing deterministic false drift after legitimate reconciliation metadata updates.

Additional evidence: the B1 manifest records a Gate4 phase snapshot hash of `5761e767de8579f2d8410f9b2b49727f24702787df8e445f77b17fbdd3881a9c`, while the current Gate4 snapshot computes to `2187d91b8307251c97e253e3244da22bfc594e0f027c1fd292f028c6c53e0363`. The manifest is itself immutable evidence of a prior B1 snapshot, not proof that the mutable current gate is the original residual record.

## Authority Decision

`phase_gates.json` is authoritative for the current active gate metadata and current L3 approval. It is not authoritative for the historical “original gate record” after reconciliation metadata has changed.

The current B1 manifest is authoritative for B1 membership and its captured B1 precondition snapshots, as enforced by `scripts/verify_legacy_gate_manifest.py`. It is not currently authoritative for the residual record’s original hash: it contains no dedicated canonical original Gate4 record/hash field and must not be used to silently replace the residual record hash.

## Minimal Compliant Reconciliation

Do not edit the residual JSON or its lock to replace `a406...` with the current hash. That would destroy historical provenance and bypass the drift signal.

Minimal compliant remediation is one of these equivalent designs:

1. Add an immutable, hash-locked original Gate4 record snapshot (including the exact canonical record that produced `a406...`) to the approved reconciliation evidence, then validate the residual hash against that snapshot.
2. Extend the immutable B1 manifest with the exact original Gate4 canonical record/hash only if the existing B1 contract is formally updated and independently audited; do not overload `phase_gate_snapshot_sha256`, which represents a different object.
3. Make both `validate_legacy_reconciliation()` and `validate_residual_reconciliation()` resolve historical hash provenance through the same immutable snapshot resolver. Continue validating current mutable metadata, fresh L3 identity, report hash, and timestamp separately.

Required negative coverage: mutate only legitimate L3 fields and confirm historical hash remains valid; mutate an immutable original field and confirm `original gate hash drift`; reject missing, duplicate, mismatched, or current-gate-derived original snapshots.

## Verification

- Read-only hash recomputation reproduced the failure: stored `a406...` != current `be086...`.
- Current and residual timestamps match exactly.
- Git history confirms original Gate4 creation at commit `f34fcbbaef7bcc1bc0e306c5ca1dde57d2df8344`; that historical Gate4 record differs from the current reconciled metadata.
- No source, test, phase-gate, manifest, reconciliation, lock, or audit file changed.

## Disposition

`NEEDS_FIX`: historical original Gate4 record provenance must be made immutable and shared by both reconciliation validators. No residual record publication or gate approval recommended until then.
