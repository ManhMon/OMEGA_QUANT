# Gate4 Original Provenance Sidecar Audit

- Verdict: [NEEDS_FIX]
- Audit date: `2026-07-30`
- Gate: `gate4_original_provenance_sidecar_20260731`
- L2 session: `l2_role9_gate4_original_provenance_sidecar_20260731`
- Writer/auditor separation: PASS (`9 != 21`)

## Blocking Findings

- `scripts/sod_gate_enforcer.py:562` omits predecessor raw-hash equals predecessor-lock validation. Independent tampering changed predecessor bytes, regenerated its lock, regenerated the sidecar and sidecar lock; validation still returned `(True, 'Gate4 original provenance valid')`. Predecessor authority remains replaceable.
- `.ly_state/session/legacy_gate4_original_provenance_20260731.json:1` claims `published_at` `2026-07-31T00:00:00Z`, future-dated relative to Thursday, July 30, 2026. `scripts/sod_gate_enforcer.py:549` checks format only.

## Verified Evidence

- Exact schema, canonical UTF-8 bytes, newline, sidecar SHA-256 lock: PASS.
- Pinned commit `f34fcbbaef7bcc1bc0e306c5ca1dde57d2df8344`; immutable record hash `5ad73f3daa5a31215953d6383e7f8466ae8ecad563bb01b5ee83e2045da0cbb8`: PASS.
- Role23 report exact raw bytes; hash `e353d150124407fbc50f6dbd1fec900896e06ce5174586adfc59c9f391f88d4e`; Gate/Role/verdict: PASS.
- Current immutable hash `be0861d7e1bfc40685e6f483d64887bcf817f0315587f7e6a7096700f9e6433f`: PASS.
- No-clobber, partial invalid fail-closed, recorded-field tampering: PASS.
- `python -m pytest -q tests/test_legacy_reconciliation_contract.py`: `72 passed`; unrelated cache warning.

## Sources

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `scripts/sod_gate_enforcer.py`
- `tests/test_legacy_reconciliation_contract.py`
- `.ly_state/session/legacy_gate4_original_provenance_20260731.json`
- `.ly_state/session/legacy_gate4_original_provenance_20260731.sha256`
- `.ly_state/session/legacy_residual_reconciliation_20260727.json`
- `.ly_state/session/legacy_residual_reconciliation_20260727.sha256`
- `.ly_state/session/l2_role9_gate4_original_provenance_sidecar_20260731.md`
- `.ly_state/session/audit_reports/role23_gp_gate4_20260704.md`
- `.ly_state/session/phase_gates.json`
- Git object `f34fcbbaef7bcc1bc0e306c5ca1dde57d2df8344`

## Forbidden Path Scan

- Matches were enforcement constants or explicitly non-authoritative scan evidence only.
- No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`.

## Authority Determination

[NEEDS_FIX] Gate4 original authority is not yet proven.
