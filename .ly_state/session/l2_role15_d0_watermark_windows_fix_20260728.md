# L2 Remediation Report

- **Role:** 15 data-engineer (OpenCode L2)
- **Session:** `l2_role15_d0_watermark_windows_fix_20260728`
- **Gate:** D0 NEEDS_FIX remediation
- **Timestamp:** 2026-07-28
- **Verdict:** `REMEDIATED_PENDING_L3_AUDIT`

## Repo-Local Sources Read

- `.agents/AGENTS.md`
- `.agents/agent/data-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`
- `.ly_state/session/l2_role15_market_data_preflight_d0_20260728.md`
- `.ly_state/session/audit_reports/role17_canonical_vci_updater_legacy_tracking_20260613.md`
- `src/omega/data/official_watermark.py`
- `scripts/update_market_data.py`
- `tests/test_official_watermark.py`
- `tests/test_update_market_data_official_watermark.py`

Forbidden-path scan: no forbidden source used authoritatively. Forbidden names appear only in repo-local protocol/evidence context.

## Remediation

- Unified `available_at` production and validation on `date + 1` calendar day in `Asia/Ho_Chi_Minh`.
- Validation now rejects missing, malformed, naive, and wrong-day timestamps before release provenance checks.
- Updated valid publication fixture to use an aware timestamp; added naive timestamp regression coverage.

- Removed the unconditional Windows rejection from official watermark writes.
- Preserved per-file `flush()` plus `os.fsync()`.
- Preserved POSIX directory `fsync()`.
- Windows uses the supported boundary of durable file flush plus `O_EXCL` atomic creation; Windows directory handles do not provide a supported directory `fsync()` contract.
- Reused the same helper from `scripts/update_market_data.py` for atomic publication paths.
- Updated the Windows regression test to verify successful materialization.

No official HSX/HNX artifacts were materialized. No canonical data, release pointers, phase gates, ledger, lock, manifest, or audit verdict was modified.

## Verification

- `python -m pytest tests/test_official_watermark.py -q --override-ini addopts=`: **12 passed, 1 skipped**
- `python -m pytest tests/test_update_market_data_official_watermark.py -q --override-ini addopts=`: **20 passed**
- `python -m py_compile scripts/update_market_data.py tests/test_update_market_data_official_watermark.py`: **pass**
- `git diff --check -- scripts/update_market_data.py tests/test_update_market_data_official_watermark.py .ly_state/session/l2_role15_d0_watermark_windows_fix_20260728.md`: **pass**
- `python scripts/checklist.py`: **blocked**, file absent
- `python scripts/verify_all.py`: **blocked**, file absent

## Data Availability

Trusted verified HSX/HNX watermark artifacts remain unavailable. No fabrication or download attempted. D0 remains `NEEDS_FIX` pending authoritative artifact acquisition and separate `close.min() == 70.0` VND_FULL contract decision.

No audit or approval performed.
