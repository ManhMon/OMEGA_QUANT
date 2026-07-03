# L2 Implementation Report: Role 14 (Data Scientist)

**GATE**: GP_EXPANSION_ALTERNATIVE_REGIMES_20260617
**Date**: 2026-06-17
**Role**: 14 (Data Scientist, Tier 2)
**Task**: Fix duplicate alpha_id reuse across regimes in `scripts/aggregate_regime_alphas.py`
**Status**: [IMPLEMENTED] - Awaiting Tier 3 Audit

---

## 1. Forbidden Path Scan

| Path | Scanned | Result |
|------|---------|--------|
| `C:\Users\GHC\.agents` (global) | YES | Only contains `skills/` subdirectory - NOT Codex memory |
| Antigravity scratch | YES | Not accessed |
| OpenClaw | YES | Not accessed |
| `C:\Users\GHC\.agents/Codex` memory | YES | Not accessed |

**Verdict**: PASS - All skill files read exclusively from REPO_SKILL_ROOT (`C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`).

## 2. Repo-Local Files Read

### Agent Definition
- `.agents/agent/data-scientist.md` (role_id: 14, tier: 2, platform: OpenCode)

### Skills Loaded (from REPO_SKILL_ROOT)
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

### Source Files
- `scripts/aggregate_regime_alphas.py` (target for fix)
- `scripts/run_phase35_backtest.py` (backtest runner)
- `.ly_state/session/evolved_alphas_bull_20_21.json` (3 alphas)
- `.ly_state/session/evolved_alphas_bear_22.json` (2 alphas)
- `.ly_state/session/evolved_alphas_sideways_24_26.json` (1 alpha)
- `.ly_state/session/evolved_alphas.json` (aggregated output - pre and post fix)

## 3. Problem Analysis

### Root Cause
When per-regime GP evolution runs produced promoted alphas, each run independently generated alpha_ids starting from `gp_alpha_20260617_000`. The aggregation script in `scripts/aggregate_regime_alphas.py` naively appended alphas from all regimes without ensuring global uniqueness.

### Duplicate Evidence (Pre-Fix)
| alpha_id | Regimes Present | Count |
|----------|----------------|-------|
| `gp_alpha_20260617_000` | bull_20_21, bear_22, sideways_24_26 | **3** (duplicate) |
| `gp_alpha_20260617_001` | bear_22 | 1 |
| `gp_alpha_20260617_002` | bull_20_21 | 1 |
| `gp_alpha_20260617_004` | bull_20_21 | 1 |

**Pre-fix totals**: 6 alphas, 4 unique IDs, 3 duplicates of `gp_alpha_20260617_000`.

### Impact
- Downstream consumers (backtest engine, alpha selector) could not distinguish between regime-specific alphas sharing the same alpha_id.
- Regime routing could potentially pick the wrong alpha formula for a given regime context.
- Alpha deduplication or look-up by alpha_id would silently merge distinct evolved formulas.

## 4. Fix Implementation

### File Modified: `scripts/aggregate_regime_alphas.py`

**Change 1** (line 38-44): Append regime name suffix to alpha_id during aggregation.

```python
# BEFORE:
for alpha in alphas:
    alpha["regime"] = regime_name
    all_alphas.append(alpha)

# AFTER:
for alpha in alphas:
    alpha["regime"] = regime_name
    # GATE: GP_EXPANSION_ALTERNATIVE_REGIMES_20260617 - ensure globally unique
    # alpha_id by appending regime name to prevent duplicate reuse across regimes.
    # Example: gp_alpha_20260617_000 -> gp_alpha_20260617_000_bull_20_21
    alpha["alpha_id"] = f"{alpha['alpha_id']}_{regime_name}"
    all_alphas.append(alpha)
```

**Change 2** (line 47-53): Post-aggregation uniqueness verification guard.

```python
# Verify global alpha_id uniqueness after regime-suffix appending
all_ids = [a["alpha_id"] for a in all_alphas]
dup_ids = [aid for aid in all_ids if all_ids.count(aid) > 1]
if dup_ids:
    print(f"[ERROR] Duplicate alpha_ids remain after aggregation: {set(dup_ids)}")
    raise SystemExit(1)
print(f"  Uniqueness check PASSED: {len(all_ids)} unique alpha_ids")
```

### Design Decisions
- **Suffix format**: `{original_id}_{regime_name}` (e.g., `gp_alpha_20260617_000_bull_20_21`). This preserves the original GP evolution counter semantics while making IDs globally unique and human-readable.
- **Fail-fast guard**: The uniqueness check raises `SystemExit(1)` if any duplicates survive, preventing silent corruption of downstream JSON outputs.
- **No upstream mutation**: Per-regime source files (`evolved_alphas_<regime>.json`) are left unchanged; the fix is purely in the aggregation layer.

## 5. Regeneration Results

### Post-Fix Alpha IDs (All Globally Unique)

| alpha_id | Regime | Formula (truncated) |
|----------|--------|---------------------|
| `gp_alpha_20260617_000_bull_20_21` | bull_20_21 | `(target_h10 * sqrt(...))` |
| `gp_alpha_20260617_002_bull_20_21` | bull_20_21 | `sqrt((vn_stock_sector_corr ts_mean 5))` |
| `gp_alpha_20260617_004_bull_20_21` | bull_20_21 | `(vn_stock_sector_corr ts_mean 10)` |
| `gp_alpha_20260617_000_bear_22` | bear_22 | `(target_h10 - rank((vn_expiry_effect ts_rank 10)))` |
| `gp_alpha_20260617_001_bear_22` | bear_22 | `neg(vn_sector_rel_momentum_20)` |
| `gp_alpha_20260617_000_sideways_24_26` | sideways_24_26 | `(sigmoid(target_h10) ts_rank 20)` |

**Post-fix totals**: 6 alphas, 6 unique IDs, 0 duplicates.

### Output Files Regenerated
- `.ly_state/session/evolved_alphas.json` (6 alphas, 6 unique IDs)
- `.ly_state/session/all_regimes_evolved_alphas.json` (mirror, 6 alphas, 6 unique IDs)

## 6. Backtest Validation

### Command
```
python scripts/run_phase35_backtest.py --quick-mode --enable-regime-routing --output-tag regime_routing_fix1
```

### Execution Evidence
- **Regime Routing**: ENABLED, active on both folds
  - Fold 1: routed 251 dates, fallback=0
  - Fold 2: routed 251 dates, fallback=0
- **No crashes or errors**: Script completed successfully
- **No alpha_id collisions**: Backtest engine processed all alphas without duplicate-key issues
- **Output persisted**: `data/phase35_results/phase35_backtest_results_regime_routing_fix1_baseline.json`

### Smoke Test Note
Quick-mode (1 symbol, 2 folds) is a smoke test for code execution verification only, not performance evidence. Portfolio IC = 0.0000 is expected for single-symbol cross-sectional analysis. Full validation requires `--top-n-symbols 30` with full fold configuration (separate Tier 3 task).

## 7. Scope Compliance

| Requirement | Status |
|-------------|--------|
| Fix duplicate alpha_id across regimes | DONE |
| Append regime name to alpha_id | DONE |
| Regenerate `evolved_alphas.json` | DONE |
| Regenerate `all_regimes_evolved_alphas.json` | DONE |
| Rerun backtest with `--enable-regime-routing` | DONE |
| Use repo-relative paths only | DONE |
| No self-approval (Tier 2 constraint) | COMPLIANT |

## 8. SOD Boundary

As Role 14 (Tier 2 Data Scientist), this implementation:
- **Does**: Implement the fix, regenerate outputs, validate with smoke backtest
- **Does NOT**: Audit, approve, or promote to live
- **Submits to**: Code Reviewer (Role 21) + QA Engineer (Role 17) for Tier 3 audit

---

**Submitted for Tier 3 Audit**
