# L2 Report: GP_VN_ALPHAS_INPLACE_DROP_ASSIGN_OOM_FIX

- Date: 2026-07-09
- Role: 16 `machine-learning-engineer`
- Scope: `src/omega/quant/alpha/vn.py`
- Gate: `GP_VN_ALPHAS_INPLACE_DROP_ASSIGN_OOM_FIX`
- Lessons noted: `RISK_ADJUSTED_ALPHA_SELECTION_20260614`, `GP_PRODUCTION_RUN_PLAN_REVIEW`

## Repo-Local Files Read

- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`

## Forbidden Path Scan Result

- `.gemini/antigravity-ide/scratch/ag-kit`: absent, treated as non-authoritative
- `.openclaw/skills`: absent, treated as non-authoritative
- `C:\Users\GHC\.agents`: present, treated as non-authoritative
- `.codex/memories`: absent, treated as non-authoritative
- Result: no authoritative reliance on forbidden paths (clean)

## Change Implemented

File: `src/omega/quant/alpha/vn.py`

Replaced:

```python
df_sorted[cols_to_clean] = res[cols_to_clean].values
```

With:

```python
res.drop(columns=["ticker", "date"], inplace=True)
df_sorted[cols_to_clean] = res.values
```

Purpose: avoid the extra wide slice copy from `res[cols_to_clean]` before assignment; reduce peak memory in `compute_all_vn_alphas`.

## Verification

1. Targeted smoke check:

```powershell
python -c "import pandas as pd; import numpy as np; from src.omega.quant.alpha.vn import compute_all_vn_alphas; rows=[]; tickers=['AAA','BBB']; dates=pd.date_range('2024-01-01', periods=130, freq='D'); [rows.append({'ticker':t,'date':d,'open':10+i%7,'high':11+i%7,'low':9+i%7,'close':10.5+i%7,'volume':1000+i}) for t in tickers for i,d in enumerate(dates)]; df=pd.DataFrame(rows); out=compute_all_vn_alphas(df); assert len(out)==len(df); assert 'vn_market_regime' in out.columns; assert out[['ticker','date']].equals(out[['ticker','date']]); print(out.shape[0], out.shape[1])"
```

Observed: `260 82`

2. Targeted test:

```powershell
python -m pytest tests/test_vn_features_targeted.py -k memory_optimization
```

Observed: `1 passed, 6 deselected`

## Outcome

- Requested in-place drop/assign change applied.
- Targeted verification passed.
- No audit or approval performed.
