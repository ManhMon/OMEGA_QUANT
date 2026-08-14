# VCI Candidate Market Download Provenance Fix2 Critical Re-Audit

**Task**: acquisition-boundary remediation after `role21_vci_candidate_market_download_provenance_20260729`  
**L2 Session**: `l2_role15_vci_candidate_market_download_provenance_20260729`  
**L2 Role**: 15 `data-engineer`  
**L3 Role**: 21 `code-reviewer`  
**Date**: 2026-07-29  
**Mode**: Advisory only; no gate authority  
**Write Boundary**: This report only. No production, test, runbook, pointer, protected-state, or phase-gate modification.

## Source Contract

- Role source read: `.agents/agent/code-reviewer.md`.
- Repo-local skills read: `.agents/skills/code-review-checklist/SKILL.md`, `.agents/skills/clean-code/SKILL.md`, `.agents/skills/testing-patterns/SKILL.md`, `.agents/skills/audit-cycle/SKILL.md`, `.agents/skills/omega-sod/SKILL.md`.
- Scoped evidence: `src/omega/data/official_watermark.py`, official receipt/watermark/updater safety tests, `docs/official-watermark-runbook.md`, and `.ly_state/session/l2_role15_vci_candidate_market_download_provenance_20260729.md`.
- Writer/auditor separation: PASS. Role 15 != Role 21.
- Forbidden paths: not used as authoritative sources.
- Code-review graph: unavailable; `get_minimal_context_tool` timed out after 300 seconds. Targeted source and runtime review completed independently.

## Blocking Finding

1. **Forged evidence and rows still reach a completed receipt through module-callable seams** — `src/omega/data/official_watermark.py:59`, `src/omega/data/official_watermark.py:335`, `src/omega/data/official_watermark.py:361`, `src/omega/data/official_watermark.py:363`.
   - `_OfficialSourceResponse` remains directly importable and caller-constructible. A leading underscore is a naming convention, not an acquisition authenticity boundary.
   - `_materialize_validated` remains directly importable and accepts caller-provided `source_evidence` plus `parsed_result` containing raw bytes and rows.
   - Validation binds `parsed_result["raw"]` to the constructed evidence bytes, but does not re-run `_parse_official_payload` or compare every supplied row with deterministic rows parsed from those bytes.
   - Independent exploit used raw JSON containing symbol `REAL`, then supplied rows containing symbol `FORGED`. Result: `FORGE_STATUS=completed`, canonical symbol `FORGED`, receipt status `completed`.
   - Therefore external evidence/raw/rows injection can still reach receipt materialization. Forged raw/rows are not impossible. The runbook statement that no evidence or rows injection exists is false for the current module surface.

## Independent Check Matrix

- Public `fetch_official_source`: absent — PASS.
- Public `OfficialSourceResponse`: absent — PASS by exact public name, but private-named constructor remains externally importable — SECURITY FAIL.
- Public `materialize_watermark` parameters limited to `config`, `market`, `expected_date`: PASS.
- Missing token rejection: implemented before transport in `_require_vci_token` — PASS.
- Expired JWT-like token rejection: implemented before transport — PASS.
- TLS/default transport: `ssl.create_default_context`, certifi/platform trust, `urllib.request.urlopen`, no injectable opener parameter — PASS for the public path.
- Fixed source: immutable market URL mapping, exact HTTPS URL and final URL checks — PASS for the public path.
- Raw JSON parsing: deterministic inside `materialize_watermark` — PASS for the public path.
- Every persisted row exact exchange/date from raw: FAIL. `_materialize_validated` accepts supplied rows, and `select_candidate` validates only the selected market/date candidate, not equality with rows parsed from raw.
- Forged evidence/raw/rows impossible: FAIL. Runtime exploit completed and persisted `FORGED`.

## Focused Verification

- `python -m pytest -q tests/test_official_watermark.py tests/test_official_source_receipt.py tests/test_update_market_data_official_watermark.py tests/test_vci_production_safety_20260727.py tests/test_vci_final_safety_closure_20260728.py tests/test_vci_updater_validation_write_blocker.py`: **58 passed, 3 skipped**.
- Green-suite gap: tests exercise private construction/materialization as accepted test seams but do not assert that inconsistent raw and rows are rejected. Existing raw-binding test changes raw bytes; it does not forge rows while retaining bound raw bytes.
- Targeted receipt security selection: **1 passed**. Full-suite execution provides the meaningful coverage result above.

## Protected Artifact Evidence

- Current `.ly_state/session/phase_gates.json` SHA-256 before final report write: `E7769D34EA4F822A0517000D141DC51D94EB8D06C2EB2B053F50DE6A514CB971`; same hash observed earlier in this audit and in the prior Role21 report.
- `.ly_state/session/current_task.json`, `.ly_state/session/task_pointer.json`, and `.ly_state/session/active_task.json`: absent throughout checked current state.
- No protected artifact was modified by this audit.
- **Baseline-before evidence is unavailable.** The L2 report explicitly states no baseline hash was supplied. This is an evidence gap, not proof of a code-security defect by itself.
- Separate post-state inconsistency: L2 records `src/omega/data/official_watermark.py` SHA-256 `6C9A8519F2AC17D2F9686DAAB6F2CEA8EAB47A0375C7BD51A036C217D1186DF9`; current audited file is `A993FE80E527201318FE492B0D7145A020E0AAAE9B6BA00C555702272CC23060`. Other listed scoped test/runbook hashes match the L2 report. This prevents treating the L2 source hash as current-state proof, independently of the demonstrated security failure.

## Required Remediation

- Remove the receipt-producing API that accepts caller-provided evidence/raw/rows, including `_materialize_validated`, or make it incapable of writing receipts unless it internally obtains and parses the authenticated response.
- At the final write boundary, deterministically parse exact `source_evidence.raw` and derive all persisted rows/candidate/coverage from that parse. Do not trust caller-supplied rows.
- Add a negative test where raw contains `REAL` and supplied rows contain `FORGED`; require rejection and zero artifacts.
- Update the runbook only after runtime inspection proves no caller-provided evidence/raw/rows can produce a receipt.

## Verdict

[NEEDS_FIX]

Public acquisition improved, but the receipt boundary remains forgeable through directly callable private-named construction and materialization seams. Advisory only; no gate updated.
