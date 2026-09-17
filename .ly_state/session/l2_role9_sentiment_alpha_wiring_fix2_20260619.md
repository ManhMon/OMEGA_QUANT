# L2 Implementation Report — FIX2: Embedded JSON Date Validation in Archive Scanner

| Field | Value |
|-------|-------|
| **Role** | backend-engineer (role_id: 9, tier: 2) |
| **Platform** | OpenCode |
| **Gate** | SENTIMENT_ALPHA_WIRING_20260619 |
| **Task** | FIX2 — Validate embedded JSON date in archive scanner |
| **Source** | L3 audit `role21_sentiment_alpha_wiring_fix1_20260619.md` (NEEDS_FIX) |
| **Date** | 2026-06-19 |
| **Status** | IMPLEMENTED — submitted to Tier 3 audit |

---

## Provenance

### Repo-local files read (authoritative)

| File | Path (repo-relative) |
|------|----------------------|
| Role definition | `.agents/agent/backend-engineer.md` |
| Skill: clean-code | `.agents/skills/clean-code/SKILL.md` |
| Skill: testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| Skill: systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` |
| Source (pre-fix) | `scripts/run_sentiment_blend.py` |
| Tests (pre-fix) | `tests/test_sentiment_blend.py` |

### Forbidden path scan

| Path | Exists | Accessed |
|------|--------|----------|
| `C:\Users\GHC\.agents` (non-authoritative, not accessed) | Yes | No |
| `C:\Users\GHC\.agents\Codex` (non-authoritative, not accessed) | No | N/A |
| `C:\Users\GHC\.agents\Codex\memory` (non-authoritative, not accessed) | No | N/A |
| Antigravity scratch | No | N/A |
| OpenClaw | No | N/A |

**Result:** All role/skill files read exclusively from `REPO_AGENT_ROOT` and `REPO_SKILL_ROOT` within the repo. No forbidden paths accessed.

---

## Finding Summary (from L3 Audit)

`find_latest_valid_sentiment()` in `scripts/run_sentiment_blend.py` selected archive candidates using **filename date only** without validating the embedded JSON `date` field. A misdated archive named `sentiment_scores_2026-06-18.json` containing `{"date": "2026-06-19"}` would pass the filename-based PIT check (2026-06-18 < 2026-06-19) and be returned as valid T-1 data, violating PIT safety at the scanner level.

Although `validate_pit_safety()` in `blend_signals()` would catch this downstream, scanner-level defense-in-depth is required per the L3 audit.

---

## Fix Applied

### File: `scripts/run_sentiment_blend.py`

**Function:** `find_latest_valid_sentiment()` — archive scanning loop (lines 143–193)

**Changes:**

1. **Renamed** `file_dt` → `filename_dt` to clarify it is a discovery hint only.
2. **Added embedded date extraction:** After loading archive JSON, extract `data.get("date", "")`.
3. **Missing date guard:** If embedded date is missing/empty, log warning and skip archive.
4. **Invalid date guard:** If embedded date fails `%Y-%m-%d` parse, log warning and skip archive.
5. **PIT validity check on embedded date:** Only select archives where `embedded_dt < target_dt`. Archives with same-day-or-later embedded dates are skipped with a warning.
6. **Use embedded date for ranking:** `best_date` comparison now uses `embedded_dt` (not `filename_dt`), ensuring the most recent PIT-valid archive by embedded date is selected.

### Design Decisions

- **Filename date retained as early filter:** Archives with filename date >= target are skipped before I/O (performance optimization). This is safe because a file named with a future date is almost certainly not useful, and the embedded date check provides the authoritative PIT gate.
- **Embedded date is authoritative:** The embedded `date` field in the JSON is the single source of truth for PIT validity. Filename is only a discovery/hint mechanism.
- **Graceful degradation:** Missing or invalid embedded dates produce warnings but do not raise exceptions. The scanner continues to the next archive.

---

## Tests Added

### File: `tests/test_sentiment_blend.py`

**Class:** `TestOracleIntegrationPath` (4 new tests appended)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_misdated_archive_same_day_embedded_date_returns_none` | Archive filename=2026-06-18, embedded date=2026-06-19, target=2026-06-19 | Returns `None` |
| `test_misdated_archive_falls_back_to_older_valid` | Misdated archive (_2026-06-18.json, embedded=2026-06-19) + valid older archive (_2026-06-17.json, embedded=2026-06-17) | Returns older valid archive (date=2026-06-17) |
| `test_archive_missing_date_field_skipped_gracefully` | Archive with no `date` field + valid older archive | Returns older valid archive (date=2026-06-16) |
| `test_archive_missing_date_field_returns_none_when_only_option` | Only archive has no `date` field | Returns `None` |

---

## Test Results

```
24 passed, 4 warnings in 5.93s
```

All 24 tests pass (20 pre-existing + 4 new FIX2 regression tests).

---

## Scope Compliance

| Constraint | Status |
|------------|--------|
| Repo-relative paths only | PASS |
| Scope limited to `scripts/run_sentiment_blend.py`, `tests/test_sentiment_blend.py` | PASS |
| No audit or approval actions | PASS |
| Implementation + tests only | PASS |

---

## Tier 3 Submission

**Status:** IMPLEMENTED — ready for Tier 3 audit.

**Submitted to:**
- Code Reviewer (role 21): Code quality and PIT safety review
- QA Engineer (role 17): Functional and regression test coverage
- Security Auditor (role 18): Input validation and data integrity
