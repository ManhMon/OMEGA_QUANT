# VCI Candidate Market Download Provenance Critical Re-Audit

**Task**: `task-13496`  
**L2 Session**: `l2_role15_vci_candidate_market_download_provenance_remediation_20260729`  
**L2 Role**: 15 `data-engineer`  
**L3 Role**: 21 `code-reviewer`  
**Date**: 2026-07-29  
**Mode**: Final advisory; no gate authority  
**Write Boundary**: This report only. No source, test, state, pointer, or phase-gate modification.

## Source Contract

- Role source: `.agents/agent/code-reviewer.md`
- Skill sources: `.agents/skills/code-review-checklist/SKILL.md`, `.agents/skills/clean-code/SKILL.md`, `.agents/skills/testing-patterns/SKILL.md`, `.agents/skills/audit-cycle/SKILL.md`, `.agents/skills/omega-sod/SKILL.md`
- Scoped evidence: `src/omega/data/official_watermark.py`, receipt/watermark/updater safety tests, `docs/official-watermark-runbook.md`, and the L2 report.
- Writer/auditor separation: PASS. Role 15 != Role 21.
- Forbidden-path scan: no forbidden path used as authoritative input.

## Blocking Findings

1. **Public production injection remains - `src/omega/data/official_watermark.py:87`**. `fetch_official_source()` publicly accepts `opener`. A caller-supplied opener returned attacker bytes while claiming the fixed official URL, HTTP 200, and `application/json`; the function accepted it. This contradicts the runbook. It bypasses real authentication, token presence/expiry, TLS peer identity, redirect history, and server provenance.

2. **Evidence is caller-forgeable - `src/omega/data/official_watermark.py:58` and `src/omega/data/official_watermark.py:301`**. `OfficialSourceResponse` is publicly constructible. A directly instantiated fake response with expected metadata and attacker bytes successfully produced a `completed` receipt. Frozen fields provide immutability after construction, not authenticity.

3. **Persisted rows are not bound to payload semantics - `src/omega/data/official_watermark.py:314` and `src/omega/data/official_watermark.py:319`**. Only parser `raw` equality is checked. Arbitrary parser rows need not derive from the bytes. Raw JSON containing only HSX/date plus parser-supplied symbol `FORGED` produced a valid canonical artifact and `completed` receipt.

## Forge Matrix

- Fake opener, exact URL/status/MIME/date/exchange: **ACCEPTED**.
- Direct fake `OfficialSourceResponse`: **ACCEPTED**.
- Raw-bound arbitrary rows: **ACCEPTED** and persisted.
- Swapped raw bytes/hash: rejected `vci_receipt_invalid`.
- HTTP 401/404: rejected `vci_receipt_invalid`.
- Redirect/off-domain effective URL: rejected `vci_receipt_invalid`.
- Bad MIME: rejected `vci_receipt_invalid`.
- Wrong date/exchange: rejected `candidate_exact_max_date_missing`.
- Auth absence/expiry: no authenticated acquisition evidence exists; injected transport bypasses endpoint auth behavior.

## Verification

- `python -m pytest -q tests/test_official_watermark.py tests/test_official_source_receipt.py tests/test_update_market_data_official_watermark.py tests/test_vci_production_safety_20260727.py tests/test_vci_final_safety_closure_20260728.py tests/test_vci_updater_validation_write_blocker.py`: **59 passed, 3 skipped**.
- Green-suite gap: tests prove raw equality and metadata rejection, not authentic acquisition or deterministic row derivation.
- Protected state before/after audit: `.ly_state/session/phase_gates.json` SHA-256 `E7769D34EA4F822A0517000D141DC51D94EB8D06C2EB2B053F50DE6A514CB971`.
- No `.ly_state/session/current_task.json`, `task_pointer.json`, or `active_task.json` existed; none created.

## Required Remediation

- Remove public `opener` injection from production API.
- Prevent caller-constructed evidence from satisfying materialization.
- Parse rows inside the trusted acquisition boundary, or verify deterministic parser output from exact raw bytes.
- Add negative tests for opener injection, direct evidence construction, and raw-bound arbitrary rows.
- Correct the runbook only after API inspection proves these seams closed.

## Verdict

[NEEDS_FIX]

Hashes are immutable, but acquisition authenticity and parser-data binding remain forgeable. Advisory only; no gate updated.