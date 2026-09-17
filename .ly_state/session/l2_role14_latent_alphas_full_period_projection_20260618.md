# L2 Implementation Report — Role 14 (data-scientist)

## Task: Fix `scripts/mine_latent_alphas.py` — Full Period Projection

| Field | Value |
|-------|-------|
| **Role** | 14 (data-scientist) |
| **Tier** | L2 — implementation only, no self-approval |
| **Gate** | `LATENT_ALPHA_MINING_64D_20260617` |
| **Date** | 2026-06-18 |
| **Scope** | `scripts/mine_latent_alphas.py` |
| **Status** | IMPLEMENTED — submit to Tier 3 audit |

---

## 1. Problem Statement

The walk-forward backtest (`scripts/run_phase35_backtest.py`) could not compute valid training/validation ICs for latent alpha signals because `data/latent_alphas_components.parquet` contained only `df_test` rows. Training-period rows were absent, causing the left-merge in the backtest to fill latent columns with 0.0 for all training dates. This prevented the backtest from selecting latent alphas in walk-forward folds.

## 2. Root Cause Analysis

**Location**: `scripts/mine_latent_alphas.py`, Step 10a (lines 1334-1352 in original).

**Bug**: The artifact persistence step saved only `df_test[output_cols]` to the output parquet:

```python
# BEFORE (bug):
df_out = df_test[output_cols].copy()
df_out.to_parquet(output_parquet, index=False)
```

Both `df_train` and `df_test` were correctly projected onto latent components in Step 6, but only the test split was persisted. The training-period projections were computed and then discarded.

**Impact**: Downstream `run_phase35_backtest.py` merges the parquet by `(ticker, date)` using a left-join. For all training-period dates, no matching rows existed, so latent columns were NaN → filled with 0.0. Walk-forward backtest folds that span the training period therefore had zero IC, preventing latent alpha selection.

## 3. Fix Applied

**Changed**: Step 10a now concatenates `df_train` and `df_test` before saving, producing a full-period parquet covering both training and test date ranges.

```python
# AFTER (fix):
df_full = pd.concat(
    [df_train[output_cols], df_test[output_cols]], ignore_index=True
)
df_full.sort_values(["date", "ticker"], inplace=True)
df_full.reset_index(drop=True, inplace=True)
df_full.to_parquet(output_parquet, index=False)
```

### Changes Detail

| Line(s) | Change | Rationale |
|---------|--------|-----------|
| 1334-1340 | Updated comment from "test set only" to "full period: train + test" | Document intent |
| 1352-1356 | Filter latent columns present in BOTH `df_train` AND `df_test` | Safety: ensure concat columns exist in both splits |
| 1358-1362 | `pd.concat([df_train, df_test])` + sort + reset index | Produce chronologically ordered full-period output |
| 1363-1367 | Updated log message with train/test row counts | Observability |

## 4. PIT Safety Verification

| Check | Status | Rationale |
|-------|--------|-----------|
| No look-ahead in projection | PASS | Models fit on training data only (Step 5); frozen model used for both splits (Step 6) |
| T-1 lag preserved | PASS | Source features pre-lagged; no new feature computation added |
| No re-fit on test data | PASS | PCA/ICA/PLS/AE models are frozen after Step 5 training fit |
| Chronological ordering | PASS | Output sorted by (date, ticker); parquet maintains temporal order |
| Forward returns not in projection | PASS | `returns` column is metadata only, not used in model fitting or projection |

## 5. Verification

| Verification | Result |
|-------------|--------|
| Python syntax (`py_compile`) | PASS — no errors |
| Gate tests (`tests/phase35/test_latent_alphas_gate.py`) | PASS — **132/132 tests passed** |
| Downstream compatibility | Compatible — `run_phase35_backtest.py` merges by `(ticker, date)`, full-period parquet provides matches for all backtest dates |

## 6. Files Modified

| File | Change Type | Lines Affected |
|------|-------------|----------------|
| `scripts/mine_latent_alphas.py` | Edit (Step 10a) | ~1334-1367 (replaced 19 lines with 34 lines) |

## 7. Artifact Compliance

| Requirement | Status |
|-------------|--------|
| Repo-relative paths from `REPO_ROOT` | PASS |
| Seeds set at script top (`SEED=42`) | Unchanged, PASS |
| No self-approval (L2 role) | COMPLIANT — submit to Tier 3 |
| Evidence persisted to `.ly_state/session/` | PASS — this report |

## 8. Forbidden Path Scan

| Scan Target | Result |
|-------------|--------|
| `.gemini\antigravity-ide\scratch\ag-kit` (non-authoritative, not used as source) | NOT accessed |
| `.openclaw\skills` (non-authoritative, not used as source) | NOT accessed |
| `C:\Users\GHC\.agents` (non-authoritative, not used as source) | NOT accessed |
| `.codex\memories` (non-authoritative, not used as source) | NOT accessed |
| All skill files read from REPO_SKILL_ROOT only | PASS |


### Repo-local Files Read

| Path | Purpose |
|------|---------|
| `.agents/agent/data-scientist.md` | Role frontmatter and constraints |
| `.agents/skills/python-patterns/SKILL.md` | Python development principles |
| `.agents/skills/clean-code/SKILL.md` | Concise coding standards |
| `.agents/skills/testing-patterns/SKILL.md` | Testing patterns |
| `.agents/skills/systematic-debugging/SKILL.md` | 4-phase debugging methodology |
| `.agents/skills/performance-profiling/SKILL.md` | Performance profiling |
| `.agents/skills/quant-research/SKILL.md` | Alpha/factor research principles |
| `.agents/skills/vietnam-market-data/SKILL.md` | Vietnam market data contract |
| `.agents/skills/backtesting-pit-safety/SKILL.md` | PIT safety and backtesting integrity |
| `.agents/skills/data-science-workflow/SKILL.md` | Data science reproducibility |
| `scripts/mine_latent_alphas.py` | Target script (full read) |
| `scripts/run_phase35_backtest.py` (lines 1380-1459) | Downstream consumer merge logic |

## 9. Tier 3 Audit Submission

**MUST submit to:**
- Code Reviewer (role 21): Code quality and reproducibility
- QA Engineer (role 17): Model validation and testing review

**Cannot proceed until:** All relevant Tier 3 roles return `[APPROVED]`.
