# Code Review Audit Report

**Gate**: `macro_and_sentiment_alpha_v1_20260808`
**L3 Session**: `l3_role21_macro_and_sentiment_alpha_v1_20260808_final`
**Role**: `21 code-reviewer` (L3 Codex)
**L2 Session**: `l2_role15_macro_and_sentiment_alpha_v1_20260808`
**L2 Role**: `15 data-engineer` (L2 OpenCode)
**Timestamp**: `2026-08-08T19:07:09+07:00`

## Findings

1. **[CRITICAL] `src/omega/data/macro_pipeline.py:77` and `src/omega/data/macro_pipeline.py:87`**: Provider observation-period fields become release timestamps. A World Bank row with `date="2024"` becomes `announcement_date=2024-01-01` and `available_at=2024-01-02`. Current revised history also lacks vintage snapshots. Backtests can access values and revisions before publication. A one-day offset does not provide PIT safety.
2. **[HIGH] `src/omega/quant/signal/sentiment_alpha.py:39`**: `_validate_pit` omits `as_of <= available_at`. Impossible metadata with availability preceding observation passes validation.
3. **[HIGH] `src/omega/quant/signal/sentiment_alpha.py:32` and `src/omega/quant/signal/sentiment_alpha.py:88`**: Negative `sentiment_decay` is accepted. With decay `-0.5` and age `2`, a unit score grows to `e=2.718281828459045`. Require finite, non-negative decay plus finite age/count inputs.
4. **[MEDIUM] `tests/test_macro_pipeline.py:31` and `tests/test_sentiment_alpha_opt.py:17`**: Tests encode unsafe assumptions. Missing cases: actual World Bank period payloads, revisions, `available_at < as_of`, negative/non-finite decay, non-finite counts.

## Verification

- `pytest -q tests/test_macro_pipeline.py tests/test_sentiment_alpha_opt.py tests/quant_test_sentiment_alpha.py`: `7 passed`.
- Adversarial World Bank payload reproduced false release dating.
- Adversarial negative decay reproduced exponential amplification.
- Passing tests do not establish PIT safety or complete math correctness.

## Required Remediation

- Store trustworthy historical release timestamps and vintage identifiers. Reject sources lacking release metadata, or use documented conservative calendars backed by immutable snapshots.
- Preserve original vintages; never overwrite historical values with revised history.
- Enforce `as_of <= available_at < timestamp`, plus T-1.
- Validate decay, age, scores, counts as finite; require decay and counts non-negative.
- Add adversarial regression tests.

## Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `src/omega/data/macro_pipeline.py`
- `tests/test_macro_pipeline.py`
- `src/omega/quant/signal/sentiment_alpha.py`
- `tests/test_sentiment_alpha_opt.py`
- `tests/quant_test_sentiment_alpha.py`
- `.ly_state/session/l2_role15_macro_and_sentiment_alpha_v1_20260808.md`
- `.ly_state/session/audit_reports/role20_macro_and_sentiment_alpha_v1_20260808.md`
- `.ly_state/session/phase_gates.json`

## Forbidden Path Scan

Forbidden paths were not authoritative sources. Role and skill loading used repo-local `.agents` files.

## Verdict

[NEEDS_FIX]
