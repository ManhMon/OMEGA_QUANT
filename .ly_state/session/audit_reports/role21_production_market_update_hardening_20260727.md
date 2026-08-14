# Code Review Audit Report

**Role**: Code Reviewer (Role 21, L3 Codex)  
**Date**: 2026-07-27T19:xx:xx+07:00  
**Submission**: `scripts/update_market_data.py`, `tests/test_market_release_gates.py`  
**L2 Report**: `.ly_state/session/l2_role15_production_market_update_hardening_20260727.md`  
**Scope**: Release hardening only. No production refresh authorized.

## Repo-Local Source Evidence

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/l2_role15_production_market_update_hardening_20260727.md`

Forbidden-path scan: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` are non-authoritative scan evidence only; no reliance.

## Identity And Boundary

- **FAIL**: Dispatch identifies L2 Role 11. Submission session/report identifies `l2_role15...`, `role_id=15`, `data-engineer`. Writer identity does not match dispatch; L1 must correct the dispatch record or obtain a matching L2 submission before audit approval.
- **PASS**: Submitted writer Role 15 differs from auditor Role 21.
- **FAIL**: No-production-refresh boundary breached. `data/market_current.json` and `data/market_releases/20260727T193603987503Z_fc74813d/` were created at `2026-07-27 19:36:03 +07:00`; the live pointer selects that five-row candidate. `data/market_2015_now.parquet` remains equal to `HEAD` blob `5ad98e244048efcbe9893b1cff0ee56e02dfe326`, but production release state changed.

## Hardening Review

- **PASS**: Source-error and requested-universe coverage gates block publication in `validate_release_gates`.
- **FAIL**: Watermark regression is not enforced. `previous_watermark` is read then discarded; `validate_release_gates(..., None)` at `scripts/update_market_data.py:1371` prevents the regression branch at `scripts/update_market_data.py:1085`.
- **FAIL**: Duplicate rejection is bypassed. `combined.drop_duplicates(...)` at `scripts/update_market_data.py:1349` removes duplicates before `validate_dataframe` checks them at `scripts/update_market_data.py:1360`; duplicates are silently accepted, contrary to the release gate.
- **PASS, conditional**: Schema, invalid OHLCV, exchange, and PIT `available_at` validation occurs before `publish_candidate`; duplicate handling invalidates this overall gate chain.
- **PASS**: Manifest records SHA-256; pointer replacement uses same-directory temporary file then `Path.replace`.
- **FAIL**: No rollback protocol. After pointer replacement, a later failure (including `prune_releases`) cannot restore the prior pointer. Exception handling only logs the run directory; it does not mark or isolate a quarantine state.
- **FAIL**: Retention policy incomplete. `prune_releases` deletes every non-active release after 14 and ignores `CHECKPOINT_RETENTION`, `FAILED_RETENTION_DAYS`, and `PIT_MANIFEST_RETENTION_DAYS`; it also reads `DEFAULT_POINTER_PATH`, not the caller's pointer path.

## Verification

- `python -m pytest tests/test_market_release_gates.py tests/test_vci_updater_validation_write_blocker.py -q --cache-clear`: `6 passed`.
- Tests do not cover coverage failure, watermark regression, duplicate-before-dedup rejection, PIT failure, checksum mismatch, prior-pointer rollback, quarantine state, retention classes, or prevention of live-pointer mutation during hardening validation.

## Required Remediation

1. Reconcile L1 dispatch identity: Role 11 submission, or corrected dispatch to Role 15, with file-backed evidence.
2. Restore/remove the unauthorized `market_current.json` pointer and release directory through the approved L1/L2 recovery process; record pre/post hashes. Do not refresh production data.
3. Pass `previous_watermark` to `validate_release_gates`; gate the candidate that will be published. Reject duplicate `(ticker, date)` rows before any deduplication, or remove deduplication from the release path.
4. Implement tested rollback/quarantine semantics: preserve prior pointer until complete publish succeeds; mark failed candidates; retain active, checkpoint, failed, and PIT-manifest classes per declared policy.
5. Add regression tests for every failed/missing path listed above, including atomic pointer failure with an existing prior pointer and no production-state mutation.

## Verdict

[NEEDS_FIX]