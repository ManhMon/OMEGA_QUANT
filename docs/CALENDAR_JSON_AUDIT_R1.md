# CALENDAR JSON Audit R1

- Role: `L3-Audit:Role20-Compliance`
- Scope (only):
  - `OMEGA_QUANT/config/vn_holidays.json`
  - `OMEGA_QUANT/packages/data/src/omega/data/calendar.py`
  - `OMEGA_QUANT/packages/data/tests/test_calendar.py`
- Test evidence: `pytest OMEGA_QUANT/packages/data/tests/test_calendar.py -q` -> `18 passed` (1 pytest cache warning, non-functional)

## Final Verdict
`[NEEDS_FIX]`

## Blockers
1. Missing explicit version metadata in holiday config.
- `OMEGA_QUANT/config/vn_holidays.json` metadata has provenance fields but no `version` key.
- `OMEGA_QUANT/packages/data/tests/test_calendar.py` metadata assertions also do not enforce `version`, so contract can regress silently.

2. Fallback behavior not fully evidenced for JSON unavailability/corruption path.
- `OMEGA_QUANT/packages/data/src/omega/data/calendar.py` fallback path is triggered by missing file / JSON load failure (`_load_holidays_from_json` returns `{}` on `except Exception`).
- Tests validate unknown-year fallback only; no test simulates missing/invalid JSON file and verifies deterministic fixed-holiday fallback for in-coverage years.
