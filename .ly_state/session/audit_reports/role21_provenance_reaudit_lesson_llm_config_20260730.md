# Role 21 Provenance Re-Audit - lesson_llm_config_precedence_20260726

- **Role**: `21 code-reviewer` (Codex L3 independent re-audit)
- **Date**: `2026-07-30`
- **Gate**: `lesson_llm_config_precedence_20260726`
- **L3 session ID/key**: `l3_role21_provenance_reaudit_lesson_llm_config_20260730`
- **Scope**: recorded-vs-current original gate hash drift only
- **Write boundary**: report only; no source, tests, phase gate, ledger, reconciliation, lock, or L2 evidence modified

## Repo-Local Files Read

- `.agents/AGENTS.md`; `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`; `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`; `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

Role resolution passed: role 21, tier 3, Codex. Historical writer role 9; `9 != 21`.

## Exact Field Drift

`load_canonical_gate_map()` synthesizes the top-level key into `phase_name`; `_immutable_gate_record()` retains it.

- Recorded projection omits `phase_name`; SHA-256 `d1f9be8ecb4a644eb6b90b23a27c31882ee74903b184de54be07a0406230e4ca`.
- Current projection adds `phase_name=lesson_llm_config_precedence_20260726`; SHA-256 `c1dafeac9e4b8c74395947d289692f6655ca10ebee665c08d6bc484521ec9c92`.
- Sole drift: `phase_name`. Other immutable fields and timestamp `null` match.

## Integrity And Authority

- Residual JSON hash/lock: `e4cfa641e3c611b8fa332311d8b8befc178fb0bed0fa4f4c42bf7677afaa263f`; byte integrity proven.
- Historical/fresh report hashes match: `40e490b35fcc978e0f46da5d92d60f4fc7f06b2474cd20efc596afe0ddfacc9f`; `eaa9b85ef1f12cd669d83cb647d234ad9f9e347063b2f63613f85ea63bf7a1df`.
- Reports prove implementation/classification, not an immutable canonical gate snapshot.
- Initial/retry2/retry3 omit this gate. Lock contents: `d29045a45c49ff42eaff77ae2b47995a8fe74e82ed52bdd1e14c394853e66e97`; `ffa6552d4aa5dc536cb839a42a0c4d3fd55c41f52c860d754da33f1bf5fff06f`; `8248295de899262b16a9efca5917c2d0c64be43547c089d7b5d86c9dcbc7bc16`.
- Residual schema permits original snapshot only for Gate 4. This gate has none.
- Current code proves present semantics. Locked publication proves recorded value. Neither proves original-time canonical authority.

Authority is not proven.

## Required Append-Only Remediation

Publish only:

- `.ly_state/session/legacy_residual_provenance_retry1_20260730.json`
- `.ly_state/session/legacy_residual_provenance_retry1_20260730.sha256`

Exact top-level fields: `version`, `supersedes`, `supersedes_lock_sha256`, `records`.

- `version`: `legacy-residual-provenance-retry1/v1`
- `supersedes`: `.ly_state/session/legacy_residual_reconciliation_20260727.json`
- `supersedes_lock_sha256`: `364f00554d9e66ad94fcc9bf543885110b023c95c7a5f2d604504288ba4fc497`
- `records`: exactly one key, `lesson_llm_config_precedence_20260726`

Exact record fields:

- `original_key`
- `recorded_original_gate_record_sha256` = `d1f9be8ecb4a644eb6b90b23a27c31882ee74903b184de54be07a0406230e4ca`
- `authoritative_original_gate_record_sha256`
- `authority_basis` = `canonical_snapshot` or `contemporaneous_snapshot`
- `original_gate_snapshot` = exact `record` plus matching `record_sha256`
- `original_gate_snapshot_sha256`
- `field_drift` = exactly `{phase_name:{recorded:null,authoritative:lesson_llm_config_precedence_20260726}}`
- `authority_evidence_path`, `authority_evidence_sha256`, `reconciled_at`

Predecessor lock content must remain `e4cfa641e3c611b8fa332311d8b8befc178fb0bed0fa4f4c42bf7677afaa263f`. Publication: both targets absent; validate temporary pair; create JSON then lock; collision/partial state fails closed; invalid retry1 never falls back.

Required validator: `validate_residual_provenance_retry1(gates=None)`, called after `validate_residual_reconciliation()` and before closure output. Enforce exact schemas/one-key scope/version; predecessor path and both predecessor hashes; lowercase SHA-256; safe evidence path/hash; unique L3 identity; `[APPROVED]` without `[NEEDS_FIX]` or manual override; snapshot hash/key/record hash; exact field-drift map; equality between authoritative snapshot hash and `_sha256(_immutable_gate_record(load_canonical_gate_map()[key]))`.

Required tests: missing pair, partial publication, no-clobber collision, schema/version drift, predecessor path/hash drift, predecessor JSON/lock drift, snapshot drift, report hash/identity/verdict drift, traversal, extra/missing records, wrong field drift, canonical mismatch, validation ordering before closure output.

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: non-authoritative scan evidence only; no reliance.
- `.codex\memories`: non-authoritative scan evidence only; no reliance.

No forbidden-path role, skill, or audit source was read.

## Verdict

[NEEDS_FIX]

Exact drift is synthesized `phase_name`. Current canonical hash is `c1dafeac...`; recorded locked hash is `d1f9be8e...`. Original-time authority is unproven. Publish and validate the append-only successor above; do not rewrite gates, ledgers, retries, reports, or locks.
