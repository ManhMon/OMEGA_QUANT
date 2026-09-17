# HYBRID_REGIME_P2FULL_NARROW_SWEEP_PLAN_20260630

Status: PLAN_ONLY

## 1. Exact Repo-Local Files Read

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

Scoped source files read:
- `data/phase35_results/hybrid_regime_cpcv_comparison_p2full_20260629_e2a_tcost15.json`
- `data/phase35_results/hybrid_regime_cpcv_comparison_p2full_20260629_e1_fixed_dd.json`
- `data/phase35_results/hybrid_regime_cpcv_comparison_e4a_tcost15.json`
- `data/phase35_results/hybrid_regime_cpcv_comparison_e4b_tcost20.json`
- `data/phase35_results/hybrid_regime_cpcv_comparison_e4c_tcost50.json`
- `scripts/backtest_hybrid_regime.py`

## 2. Forbidden Path Scan Result

Checked forbidden non-authoritative paths from repo root / exact absolute path contract:
- `.gemini/antigravity-ide/scratch/ag-kit` -> not present
- `.openclaw/skills` -> not present
- `.codex/memories` -> not present
- `C:/Users/GHC/.agents` -> present, non-authoritative, not used as source

Result: no forbidden path used as authoritative source. Global path `C:/Users/GHC/.agents` exists, is non-authoritative, and was not read for role/skill loading.

## 3. Winner Baseline Metrics

Winner baseline artifact: `data/phase35_results/hybrid_regime_cpcv_comparison_p2full_20260629_e2a_tcost15.json`

Why winner:
- Best `Baseline.mean_sharpe` in scoped p2full baseline pair: `-0.20372949799481918` vs `-0.3568554249525631` in `p2full_20260629_e1_fixed_dd`
- Best `Baseline.mean_return`: `0.03137904970327394` vs `-0.013128442668284546`
- Slightly better worst drawdown: `-0.3287411694965605` vs `-0.3151951437785774` is slightly worse on tail, but overall Sharpe/return clearly better
- Lower cost drag than e1: `mean_total_tc_pct=0.056997399373635176` vs `0.0722361629279786`

Winner baseline metrics:
- `mean_sharpe`: `-0.20372949799481918`
- `std_sharpe`: `0.8140193058971625`
- `median_sharpe`: `-0.514537437605934`
- `mean_return`: `0.03137904970327394`
- `median_return`: `-0.12386786831454444`
- `mean_max_dd`: `-0.18700590912873555`
- `worst_max_dd`: `-0.3287411694965605`
- `n_folds_completed`: `45`
- `mean_gross_return`: `0.0883764490769091`
- `mean_total_tc_pct`: `0.056997399373635176`
- `mean_cash_days_pct`: `0.5532092824107343`
- `mean_turnover_avg`: `0.048483566325383365`
- `mean_exposure_avg`: `0.2888842198186341`

Context vs narrow static sweep baselines:
- `e4a_tcost15`: mean_sharpe `-0.47121933006475203`, mean_return `0.004766462065580066`, mean_total_tc_pct `0.5912402539473464`
- `e4b_tcost20`: mean_sharpe `-0.4787383638973117`, mean_return `0.005043551962858212`, mean_total_tc_pct `0.47091047032503974`
- `e4c_tcost50`: mean_sharpe `-0.7981309641631599`, mean_return `-0.13861899912004755`, mean_total_tc_pct `0.5554142114245272`

Takeaway: p2full dynamic-60 / embargo-2.5% / 15bps already dominates the 30-name static narrow sweep. Next step should stay inside p2full neighborhood, not revert to static-30 design.

## 4. Bull / Bear / Sideways Profitability_Diag Takeaways

Using winner baseline regime diagnostics from `p2full_20260629_e2a_tcost15.json`:
- Bull strongest: `alpha_ic_per_regime.bull.mean_ic = 0.01825047737930171`
- Sideways weaker: `alpha_ic_per_regime.sideways.mean_ic = 0.011427835421025243`
- Bear weakest but still positive: `alpha_ic_per_regime.bear.mean_ic = 0.007280408106043597`

Takeaways:
- Bull -> clear edge. Signal stack already monetizes trend regime best. Keep bull behavior mostly intact.
- Sideways -> positive but fragile. Several late folds negative. This is likely where churn/noise still leaks through.
- Bear -> positive IC but much lower than bull, so realized PnL likely constrained by defensive posture + high cash share rather than total signal failure.
- Portfolio-level diag says core problem is not raw gross only. `mean_gross_return=0.0883764490769091` is acceptable-ish, but `mean_cash_days_pct=0.5532092824107343` and `mean_exposure_avg=0.2888842198186341` imply under-deployment. Net result still weak despite lower TC.
- Narrow sweep evidence says pushing static universe + higher effective cost worsens everything. So optimization target is p2full deployment efficiency, not harsher pruning.

## 5. Exact Next 3-4 Experiments

All commands repo-relative from `REPO_ROOT`. Expected output naming from script: `data/phase35_results/hybrid_regime_cpcv_comparison_<output_tag>.json`.

### Experiment C1

Goal: first reduce idle cash without changing p2full structure. Tightest, lowest-risk move.

CLI:
```powershell
python scripts/backtest_hybrid_regime.py --start-date 2015-01-01 --end-date 2026-12-31 --folds 10 --n-test-folds 2 --embargo-pct 0.025 --label-horizon 60 --symbol-count 60 --workers 0 --cost-per-trade-bps 15 --top-k 7 --rebalance-every-n-days 10 --output-tag p2full_20260630_c1_rebal10_tcost15
```

Expected result file:
- `data/phase35_results/hybrid_regime_cpcv_comparison_p2full_20260630_c1_rebal10_tcost15.json`

Expected result:
- Higher exposure, lower cash days, modest TC increase, best shot at improving mean return while preserving current cost regime.

### Experiment C2

Goal: if C1 still leaves too much idle cash, loosen trade suppression next.

CLI:
```powershell
python scripts/backtest_hybrid_regime.py --start-date 2015-01-01 --end-date 2026-12-31 --folds 10 --n-test-folds 2 --embargo-pct 0.025 --label-horizon 60 --symbol-count 60 --workers 0 --cost-per-trade-bps 15 --top-k 7 --min-trade-threshold-bps 200 --output-tag p2full_20260630_c2_trade200_tcost15
```

Expected result file:
- `data/phase35_results/hybrid_regime_cpcv_comparison_p2full_20260630_c2_trade200_tcost15.json`

Expected result:
- Better sideways participation than winner baseline; turnover up slightly; if TC stays near current level, Sharpe should improve.

### Experiment C3

Goal: combine C1 + C2 only if single-factor cash-release moves help independently.

CLI:
```powershell
python scripts/backtest_hybrid_regime.py --start-date 2015-01-01 --end-date 2026-12-31 --folds 10 --n-test-folds 2 --embargo-pct 0.025 --label-horizon 60 --symbol-count 60 --workers 0 --cost-per-trade-bps 15 --top-k 7 --rebalance-every-n-days 10 --min-trade-threshold-bps 200 --output-tag p2full_20260630_c3_rebal10_trade200_tcost15
```

Expected result file:
- `data/phase35_results/hybrid_regime_cpcv_comparison_p2full_20260630_c3_rebal10_trade200_tcost15.json`

Expected result:
- Strongest candidate to lift gross return; risk is TC rebound. Only worth it after C1/C2 isolate whether cadence or gate is the real bottleneck.

### Experiment A1

Goal: only after C-branch cash deployment tests, probe concentration width.

CLI:
```powershell
python scripts/backtest_hybrid_regime.py --start-date 2015-01-01 --end-date 2026-12-31 --folds 10 --n-test-folds 2 --embargo-pct 0.025 --label-horizon 60 --symbol-count 60 --workers 0 --cost-per-trade-bps 15 --top-k 9 --output-tag p2full_20260630_a1_topk9_tcost15
```

Expected result file:
- `data/phase35_results/hybrid_regime_cpcv_comparison_p2full_20260630_a1_topk9_tcost15.json`

Expected result:
- Slightly lower concentration, potentially better sideways/bear stability, but may dilute bull edge. Lower priority than cash-release tests.

## 6. Why Experiment Order Is C -> A

Order rationale:
- `C` first because winner baseline already shows decent gross (`0.0883764490769091`) but poor deployment (`cash_days 55.32%`, `exposure 28.89%`). Capital utilization is the nearest bottleneck.
- `C` first because winner-level profitability still appears regime-fragile: `bull` keeps participation high but `bear` / `sideways` are where net Sharpe can be dragged negative by excess churn and residual weak-conviction trades.
- `A` second because once regime drag is isolated, a narrow sweep around the winner can test only the smallest execution knobs that should preserve the current edge while reducing cost leakage.
- This ordering avoids broad parameter fishing: debug the weakest regimes first, then tighten around the proven winner.

PIT-safe rationale: all four proposed experiments change execution-only knobs only (`--rebalance-every-n-days`, `--min-trade-threshold-bps`, `--top-k`) on top of the fixed winner config. They do not change label horizon, embargo, CPCV fold structure, train/test separation, or lag construction in `scripts/backtest_hybrid_regime.py`, so the plan preserves the existing point-in-time boundary and should not introduce look-ahead bias.

## 7. Stop Condition

Report written to `.ly_state/session/l2_role14_p2full_narrow_sweep_plan_20260630.md`.
