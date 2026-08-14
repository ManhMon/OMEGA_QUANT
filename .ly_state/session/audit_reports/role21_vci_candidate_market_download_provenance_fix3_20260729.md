# VCI Candidate Market Download Provenance Fix3 Final Re-Audit

**Task**: `l2_role15_vci_candidate_market_download_provenance_fix2_20260729`  
**Prior Audit**: `role21_vci_candidate_market_download_provenance_fix2_20260729` `[NEEDS_FIX]`  
**Roles**: L2 Role15 `data-engineer`; L3 Role21 `code-reviewer`  
**Date**: 2026-07-29  
**Mode**: Advisory only; no gate authority  
**Write Boundary**: This report only.

## Source Contract

- Read `.agents/agent/code-reviewer.md`.
- Read repo-local `.agents/skills/code-review-checklist/SKILL.md`, `.agents/skills/clean-code/SKILL.md`, `.agents/skills/testing-patterns/SKILL.md`, `.agents/skills/audit-cycle/SKILL.md`, `.agents/skills/omega-sod/SKILL.md`.
- Read scoped `src/omega/data/official_watermark.py`, `tests/test_official_watermark.py`, `docs/official-watermark-runbook.md`, L2 report, prior Role21 report.
- Writer/auditor separation: PASS. Role 15 != Role 21.
- Forbidden paths were not authoritative. A non-authoritative `.codex/memories` keyword scan supplied no audit evidence or conclusion.
- Code-review graph attempted first; `get_minimal_context_tool` timed out after 300 seconds. Direct source/runtime audit completed independently.

## Security Result

- Prior blocker remediated. `_materialize_validated` is absent.
- `materialize_watermark(config, market, expected_date)` exposes exactly three parameters: `src/omega/data/official_watermark.py:325`.
- Internal `_materialize_acquired` also accepts only those three values, then calls `_acquire_official_source`, validates private evidence/fixed metadata, parses `source_evidence.raw`, selects the exact candidate, and derives canonical data, coverage, hashes, and receipt: `src/omega/data/official_watermark.py:330`, `src/omega/data/official_watermark.py:340`, `src/omega/data/official_watermark.py:344`, `src/omega/data/official_watermark.py:355`, `src/omega/data/official_watermark.py:359`, `src/omega/data/official_watermark.py:370`, `src/omega/data/official_watermark.py:396`.
- No receipt-producing function accepts caller evidence, raw bytes, parsed rows, candidate, coverage, or metadata.
- Private symbols remain directly importable under Python semantics. Underscores are privacy conventions, not sandbox barriers. This is acceptable here: private receipt materialization has no evidence/raw/rows input, while arbitrary in-process code can already replace functions or write files.

## Exploit Replay

All runtime attempts used temporary directories.

1. Raw JSON symbol `REAL` plus forged extra rows symbol `FORGED` passed to `materialize_watermark`: `TypeError`; `_exclusive_write` calls `0`; artifacts `0`.
2. Same forged evidence/raw/rows passed to directly imported `_materialize_acquired`: `TypeError`; `_exclusive_write` calls `0`; artifacts `0`.
3. Caller-constructed `_OfficialSourceResponse` without writer invocation: artifacts `0`.
4. Test-only monkeypatch of `_acquire_official_source` supplied fake raw containing `REAL`, leaving the real parser intact: `completed`; canonical candidate `REAL`; coverage `REAL`; raw hash bound exactly. Internal parse/derive confirmed.
5. Test-only monkeypatch of both acquisition and private parser produced `FORGED`. This requires arbitrary in-process replacement of production code. It is not callable production input, config, dependency parameter, or supported seam. Monkeypatch capability is test instrumentation, not external provenance authority.

## Tests and Runbook

- `test_forged_rows_cannot_reach_receipt_writer` enforces rejection plus zero artifacts: `tests/test_official_watermark.py:85`.
- Public surface/signature tests pass: `tests/test_official_watermark.py:202`, `tests/test_official_watermark.py:208`.
- Runbook matches private acquisition, internal parsing, no evidence/rows injection, exact derivation, quarantine behavior.
- L2 claimed `45 passed, 3 skipped`. Exact five-file focused command currently produced **48 passed, 3 skipped**. Count is stale/undercounted, not failing; all collected tests passed.
- Only unrelated dependency/deprecation and existing `.pytest_cache` warnings appeared.

## Protected State

- `.ly_state/session/phase_gates.json` before/after SHA-256: `E7769D34EA4F822A0517000D141DC51D94EB8D06C2EB2B053F50DE6A514CB971`.
- `.ly_state/session/current_task.json`, `.ly_state/session/task_pointer.json`, `.ly_state/session/active_task.json`: absent before/after.
- Protected state unchanged. No gate updated.

## Verdict

[APPROVED]

Raw `REAL` plus rows `FORGED` callable-input exploit closed. Materialization internally acquires, parses, validates, and derives persisted provenance. Advisory only.
