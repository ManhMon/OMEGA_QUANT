# L2 Evidence Report: LLM Alpha Grouped Smoke

**Gate**: LLM_ALPHA_GROUPED_SMOKE_20260612
**Role**: L1/Ly runtime validation evidence for L3 audit
**Date**: 2026-06-12T05:57:48+07:00

## Scope

Smoke validation after approved grouped LLM alpha execution implementation.

## Commands

```powershell
python scripts/backtest_v2_cpcv.py --smoke --use-llm-alphas --year-start 2020 --year-end 2020 --out .ly_state/session/llm_alpha_grouped_smoke_20260612.json
```

Result: PASS. Output saved to `.ly_state/session/llm_alpha_grouped_smoke_20260612.json`.

```powershell
python scripts/backtest_v2_cpcv.py --smoke --use-llm-alphas --shuffle-y --year-start 2020 --year-end 2020 --out .ly_state/session/llm_alpha_grouped_shuffle_smoke_20260612.json
```

Result: PASS. Output saved to `.ly_state/session/llm_alpha_grouped_shuffle_smoke_20260612.json`.

## Evidence

Normal grouped smoke:
- LLM grouped alphas added: `alpha_llm_0`, `alpha_llm_1`
- Total features: 158
- After variance filter: 144
- Model samples/features: 988 samples, 116 feats
- CPCV folds: 45
- `med_test_IC`: 0.0127
- `med_train_IC`: -0.0239
- `med_SR`: -0.0370
- `DSR`: 0.000

Shuffle-y falsification:
- Target shuffled within date.
- LLM grouped alphas added: `alpha_llm_0`, `alpha_llm_1`
- CPCV folds: 45
- `med_test_IC`: -0.0406
- `med_train_IC`: 0.0293
- `med_SR`: -0.1136
- `DSR`: 0.000

## Interpretation

- Runtime path is healthy.
- Grouped LLM alpha injection works.
- Shuffle-y degraded performance, so no obvious leakage signal appeared.
- Current mock alpha formulas are not deployable alpha yet (`DSR=0`, negative SR).

## Files

- `.ly_state/session/llm_alpha_grouped_smoke_20260612.json`
- `.ly_state/session/llm_alpha_grouped_shuffle_smoke_20260612.json`

## Status

Ready for L3 audit.
