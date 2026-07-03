# L2 Report: role14 llm_alpha_discovery_vci 20260618

## Role
- role_id: 14
- role_name: data-scientist
- tier: 2
- platform: OpenCode
- gate: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615
- verdict: L2_IMPLEMENTED_NEEDS_L3_AUDIT

## Repo-Local Sources Read
- `.agents/agent/data-scientist.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden Path Scan
- No authoritative skill or role source loaded from `.gemini/antigravity-ide/scratch/ag-kit`, `.openclaw/skills`, `C:\Users\GHC\.agents`, or `.codex/memories`.
- Scoped grep in `scripts/backtest_v2_cpcv.py` found no forbidden path reliance.

## Scope
- Modified only `scripts/backtest_v2_cpcv.py`.
- Added `--data-path` CLI option.
- Routed `--data-path` into both standard and walk-forward panel loaders.
- Default remains `data/market_2015_now.parquet`.

## Verification
- `python -m py_compile scripts/backtest_v2_cpcv.py`: PASS
- Smoke:
  `python scripts/backtest_v2_cpcv.py --smoke --data-path data/market_vci_hsx_hnx_2015_now_20260613.parquet --year-start 2020 --year-end 2020 --out .ly_state/session/backtest_v2_cpcv_smoke_data_path_20260618.json`
  PASS, output `.ly_state/session/backtest_v2_cpcv_smoke_data_path_20260618.json`.
- Full CPCV + LLM:
  `OMEGA_LLM_MODEL=fm/gpt-5.5 OMEGA_LLM_BASE_URL=https://api.openrouter.ai/api/v1 python scripts/backtest_v2_cpcv.py --data-path data/market_vci_hsx_hnx_2015_now_20260613.parquet --use-llm-alphas --llm-provider openai-compatible --year-start 2020 --year-end 2024 --out .ly_state/session/backtest_v2_cpcv_llm_vci_20260618.json --llm-search-evidence .ly_state/session/llm_closed_loop_formula_search_vci_20260618.json`
  PASS, output `.ly_state/session/backtest_v2_cpcv_llm_vci_20260618.json`.

## Full Run Summary
- Dataset: `data/market_vci_hsx_hnx_2015_now_20260613.parquet`
- Panel: 51,135 rows, 44 tickers, 2020-01-02..2024-12-31
- Baseline features: 129
- LLM candidates: 25 total, 24 accepted, 1 rejected, 0 deployable, 24 unsupervised_only
- Baseline median_test_ic: 0.017860390088622734
- Baseline DSR: 0.9186148529833806, pass=false
- Fold DSR: 0.5846368567209911, pass=false

## PIT Notes
- Change only parameterizes dataset path; it does not alter signal timing, target construction, CPCV split logic, embargo, ADV lag, or causal sanitization.
- Existing T-1/causal sanitization paths preserved.

## Artifacts
- `.ly_state/session/backtest_v2_cpcv_smoke_data_path_20260618.json`
- `.ly_state/session/backtest_v2_cpcv_llm_vci_20260618.json`
- `.ly_state/session/llm_closed_loop_formula_search_vci_20260618.json`
