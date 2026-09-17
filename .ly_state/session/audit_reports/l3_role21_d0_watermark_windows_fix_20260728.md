# L3 Independent Re-Audit Report

- **Role:** 21 code-reviewer (Codex L3)
- **L2 role:** 15 data-engineer (OpenCode L2)
- **Requested L2 session:** `l2_role15_d0_available_at_timezone_fix_20260728`
- **Persisted remediation report:** `.ly_state/session/l2_role15_d0_watermark_windows_fix_20260728.md`
- **Date:** 2026-07-28
- **Boundary:** Advisory only; no phase-gate update

## Sources

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/audit_reports/l3_role21_d0_watermark_windows_fix_20260728.md` (prior audit)
- `.ly_state/session/l2_role15_market_data_preflight_d0_20260728.md`
- `.ly_state/session/l2_role15_d0_watermark_windows_fix_20260728.md`
- `src/omega/data/official_watermark.py`
- `scripts/update_market_data.py`
- `tests/test_official_watermark.py`
- `tests/test_update_market_data_official_watermark.py`

Forbidden-path scan: no forbidden source used authoritatively.

## Re-Audit Findings

- **PASS - SoD:** Writer role 15 differs from auditor role 21. L2 explicitly records no self-audit or approval.
- **PASS - Windows durability:** `_exclusive_write()` retains `os.O_EXCL`, descriptor-backed binary write, `flush()`, and `os.fsync()` before close. Windows skips only unsupported directory `fsync()`.
- **PASS - POSIX durability:** `_fsync_directory()` retains directory open, `os.fsync(directory_fd)`, and guaranteed close. Failure remains fail closed.
- **PASS - Single PIT rule:** Producer and validator require `available_at` on calendar `date + 1`, timezone-aware in `Asia/Ho_Chi_Minh`. Release provenance applies the same rule.
- **PASS - Fail closed:** Missing, malformed, naive, or wrong-day `available_at` values are rejected. Missing/tampered watermark artifacts, invalid receipt fields, hashes, coverage, and timestamps remain rejected.
- **PASS - Reachability:** Valid publication reaches `published`. Stale generation and stale pointer hash paths are reached and raise their expected errors.
- **PASS - Regression coverage:** Updater suite contains 20 tests and passes. Watermark suite passes with its expected conditional skip.
- **PASS - Scope:** No source or test mutation performed by L3. No canonical parquet, watermark artifact, release pointer, phase gate, ledger, or manifest mutation observed during verification.

## Verification

- `python -m pytest tests/test_update_market_data_official_watermark.py -q --override-ini addopts=`: **20 passed**.
- `python -m pytest tests/test_official_watermark.py -q --override-ini addopts=`: **12 passed, 1 skipped**.
- Sensitive before/after SHA-256 checks: `.ly_state/session/phase_gates.json`, `.ly_state/session/risk_status.json`, and `data/market_2015_now.parquet` unchanged; `data/market_current.json` remained absent.
- Scoped `git diff --check`: pass.

## Advisory Note

The requested session label `l2_role15_d0_available_at_timezone_fix_20260728` is not a standalone report filename. The remediation is persisted in the existing Role 15 report named above. This does not affect writer/auditor independence or the verified implementation result.

## Verdict

**[APPROVED]**

Prior blocking timezone-contract regression is resolved. Windows and POSIX durability contracts remain intact; fail-closed and publication/stale-generation paths pass.
