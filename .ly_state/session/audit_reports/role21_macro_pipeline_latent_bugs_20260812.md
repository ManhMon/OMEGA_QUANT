# L3 Independent Audit: MACRO_PIPELINE_V8_LATENT_BUGS_20260812

`[NEEDS_FIX]`

- Audit execution date: `2026-08-12`.
- Gate and session identifiers use the `20260812` suffix.
- L2 session: `l2_role9_macro_pipeline_latent_bugs_20260812`.
- L2 role: `9 backend-engineer` (`Tier 2`, `OpenCode`).
- L3 session: `l3_role21_macro_pipeline_latent_bugs_20260812`.
- L3 role: `21 code-reviewer` (`Tier 3`, `Codex`).
- Approved implementation scope: `src/omega/data/macro_pipeline.py`, `tests/test_macro_pipeline.py`.

## Acceptance Checks

| Check | Result | Evidence |
|---|---|---|
| `query_as_of` mixed-offset handling | **FAIL** | `published_at` and `ingested_at` are normalized at `src/omega/data/macro_pipeline.py:135`, but `observation_date` remains raw while serving as the deduplication key at `src/omega/data/macro_pipeline.py:138`. Equivalent observation instants with `+07:00` and `+00:00` return two vintages. |
| Empty `urls` fail-open | **PASS** | `src/omega/data/macro_pipeline.py:80` uses defaults only when `urls is None`; `tests/test_macro_pipeline.py:44` covers explicit `{}`. |
| Regression tests | **PARTIAL** | Mixed `published_at` offsets, equivalent publication instants, explicit empty URLs, and null `published_at` are covered at `tests/test_macro_pipeline.py:44`, `tests/test_macro_pipeline.py:207`, `tests/test_macro_pipeline.py:217`, and `tests/test_macro_pipeline.py:227`. No equivalent-offset `observation_date` regression exists. |

## Blocking Finding

1. **[HIGH] Equivalent observation instants are not deduplicated.**
   - `query_as_of()` normalizes ordering fields but not the `observation_date` grouping key.
   - Counter-probe input used `2026-01-01T00:00:00+07:00` and `2025-12-31T17:00:00+00:00`, the same instant.
   - Result: `equivalent_observation_rows=2`; one latest vintage is required.
   - Impact: downstream consumers can receive duplicate rows for one economic observation, breaking deterministic latest-vintage semantics and potentially double-counting macro features.
   - Required fix: canonicalize `observation_date` before `drop_duplicates()` and final sorting; add a regression asserting one selected vintage for equivalent offsets.

## Additional Integrity Gap

- `src/omega/data/macro_pipeline.py:153` parses `ingested_at`, but `src/omega/data/macro_pipeline.py:154` never validates it. A probe showed `_validate_store()` accepts null `ingested_at`. This contradicts the L2 report claim that null timestamps fail closed through `_validate_store()` before selection. Either reject null `ingested_at` explicitly with a regression or narrow the report claim.

## Audit Evidence Checklist

1. **Writer != Auditor:** PASS. `l2_role_id=9` differs from `l3_role_id=21`.
2. **Approved scope:** PASS. The submitted implementation paths are the two approved files. The repository is broadly dirty; conclusions remain restricted to these paths and file-backed L2 evidence.
3. **All tests:** PASS. Focused suite: `22 passed`. Full repository suite: exit `0`; `3233` tests collected; three skip markers.
4. **PIT safety / no look-ahead:** NEEDS_FIX. Availability and ingestion cutoffs remain fail-closed, but equivalent observation instants can survive as duplicate latest vintages.
5. **SOD boundaries:** PASS. `.agents` is a regular repo directory; no `opencode` process was running; L3 changed no production source or tests.
6. **L2 repo-local source evidence:** PASS. `.agents/agent/backend-engineer.md` resolves role `9`, Tier `2`, platform `OpenCode`; all six declared repo-local skill files are listed in the L2 report and exist.

## Validation

- `python -B -m py_compile src/omega/data/macro_pipeline.py tests/test_macro_pipeline.py`: PASS.
- `python -B -m pytest tests/test_macro_pipeline.py -q -p no:cacheprovider`: PASS, `22 passed`.
- `python -B -m pytest -q -p no:cacheprovider`: PASS, exit `0`.
- Collection probe: `3233` tests.
- Scoped staged and unstaged `git diff --check`: PASS.
- Source SHA-256: `E9C22ACAEF83E079377F82BA00F5A8DB53B16A67FA9DB420E071583EEE338D88`.
- Test SHA-256: `DA6AB427F7EC6EA83FD28F338C218D7FBC187666C8D897C1BB79976F57D0E555`.

## Exact Repo-Local Files Read

- `AGENTS.md` (provided in the L1 task context).
- `.agents/AGENTS.md`.
- `.agents/agent/code-reviewer.md`.
- `.agents/agent/backend-engineer.md` (frontmatter only).
- `.agents/skills/code-review-checklist/SKILL.md`.
- `.agents/skills/clean-code/SKILL.md`.
- `.agents/skills/testing-patterns/SKILL.md`.
- `.agents/skills/audit-cycle/SKILL.md`.
- `.agents/skills/omega-sod/SKILL.md`.
- `src/omega/data/macro_pipeline.py`.
- `tests/test_macro_pipeline.py`.
- `.ly_state/session/l2_role9_macro_pipeline_latent_bugs_20260812.md`.
- `.ly_state/session/l2_role9_macro_pipeline_deep_audit_fix2_20260811.md`.
- `.ly_state/session/audit_reports/role21_MACRO_PIPELINE_V8_FIX2_20260811.md`.
- `.ly_state/session/phase_gates.json`.

## Forbidden Path Scan

- [.gemini\antigravity-ide\scratch\ag-kit]: non-authoritative scan evidence only; no reliance.
- [.openclaw\skills]: non-authoritative scan evidence only; no reliance.
- [C:\Users\GHC\.agents]: non-authoritative scan evidence only; no reliance.
- [.codex\memories]: non-authoritative scan evidence only; no reliance.

- Scoped source/test scan: zero forbidden-path tokens.
- L2 report occurrences are explicit negative scan evidence only.

## Verdict

`[NEEDS_FIX]`

The mixed-offset fix is incomplete until equivalent `observation_date` instants collapse to one deterministic latest vintage. L1 final step: run `python scripts/sod_gate_enforcer.py` after this gate update.


