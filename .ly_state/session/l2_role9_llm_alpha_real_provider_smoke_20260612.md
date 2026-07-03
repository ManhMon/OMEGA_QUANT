# L2 Evidence Report: Real Provider LLM Alpha Smoke

**Gate**: LLM_ALPHA_REAL_PROVIDER_SMOKE_20260612
**Role**: L1/Ly runtime validation evidence for L3 audit
**Date**: 2026-06-12T09:37:03+07:00

## Scope

Real-provider smoke validation for `--use-llm-alphas --llm-provider openai-compatible` after safe provider interface approval.

## Evidence Summary

Normal real-provider smoke:
- Command run by user in local PowerShell with provider env set.
- Output: `.ly_state/session/llm_alpha_real_provider_smoke_20260612.json`
- Provider path: `OpenAICompatibleProvider`, model `cx/gpt-5.5`, base URL `http://localhost:20128/v1`
- Cache used formulas: 3
- Valid formulas: 2
- Grouped alphas added: `alpha_llm_0`, `alpha_llm_1`
- `median_test_ic`: 0.0106
- `median_train_cv_ic`: -0.0215
- `median_fold_sr`: -0.0674
- `dsr`: 0.000

Real-provider shuffle-y falsification:
- Output: `.ly_state/session/llm_alpha_real_provider_shuffle_20260612.json`
- `median_test_ic`: -0.0433347465340177
- `median_train_cv_ic`: 0.02633960473318229
- `median_fold_sr`: -0.08569136161521478
- `dsr`: 1.5534005406240887e-28
- `pass`: false

## Interpretation

- Real provider path runs successfully.
- Grouped alpha execution remains active.
- Shuffle-y degrades IC and remains non-significant, so no obvious leakage signal.
- Current real-provider formulas are not deployable alpha yet because DSR is ~0 and SR is negative.

## Security Notes

- API key is not recorded in this report.
- Report records only provider class/model/base URL and aggregate metrics.
- Secret rotation remains recommended because key appeared in external terminal/chat logs.

## Status

Ready for L3 audit.
