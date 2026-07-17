## Repo-Local Files Read
- `.agents/AGENTS.md`
- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `scripts/run_weekly_evolution.py`
- `tests/test_genetic_alpha_evolution_v4.py`
- `tests/test_vn_features_targeted.py`

## Changes
- Replaced duplicate-key hard failure in `_generate_alternative_features()` with warning plus `drop_duplicates(..., keep="last")` before index construction.
- Preserved `prepare_features()` fallback path so weekly evolution continues after alternative-feature exceptions.
- Added regression coverage for duplicate `(date, ticker)` input rows.

## Verification
- `pytest tests/test_genetic_alpha_evolution_v4.py -k alternative_features`
