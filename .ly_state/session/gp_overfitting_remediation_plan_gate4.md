# GP Overfitting Remediation Plan - Gate 4

**Date**: 2026-07-04  
**Context**: Gates 1-3 complete (performance optimizations). GP evolution shows severe overfitting (TrainICIR=5.35, TestIC=0.014).

**Root Cause Analysis** (Codex + Claude Code consensus):
- Metric mismatch: TrainIC is ICIR (mean/std), TestIC is IC
- Only 3 folds → unstable std → inflated ICIR
- No validation set → test leakage into selection
- Penalties 10-100× too weak for IR scale
- 18,750 candidate search → multiple comparisons problem

---

## Gate 4 Scope

### Phase 1: Metric & Label Fixes (Medium Risk - Codex Corrected)
**Files**: `scripts/genetic_alpha_evolution_v3.py`

**CRITICAL FIX (Codex)**: IC must be **daily cross-sectional**, not global Spearman.

1. Rename output labels for clarity:
   - `TrainIC` → `TrainICIR` or `TrainFoldIR`
   - Add true `TrainIC_daily` (mean daily cross-sectional IC)
   - Rename `TestIC` → `TestIC_daily` (daily CS IC)

2. Implement daily cross-sectional IC calculation:
   ```python
   def compute_daily_cs_ic(signal: np.ndarray, target: np.ndarray, dates: np.ndarray) -> float:
       """Compute mean daily cross-sectional IC."""
       daily_ics = []
       for date in np.unique(dates):
           mask = dates == date
           if mask.sum() > 5:  # min obs per date
               ic, _ = spearmanr(signal[mask], target[mask])
               if not np.isnan(ic):
                   daily_ics.append(ic)
       return float(np.mean(daily_ics)) if daily_ics else 0.0
   
   # Usage in reporting
   train_ic_daily = compute_daily_cs_ic(signal_train, target_train, train_dates)
   train_icir = engine.history[-1]['best_fitness']
   test_ic_daily = compute_daily_cs_ic(signal_test, target_test, test_dates)
   ```

3. **CRITICAL (Claude Code - Blocker #3)**: Change evolution objective to daily CS IC:
   ```python
   # genetic_engine.py _compute_time_fold_ir
   # REPLACE pooled spearmanr per fold WITH mean daily CS IC per fold
   def _compute_time_fold_ir(self, alpha, target, dates, folds, config):
       fold_ics = []
       for fold_dates in folds:
           fold_mask = np.isin(dates, fold_dates)
           fold_daily_ics = []
           for date in np.unique(dates[fold_mask]):
               date_mask = dates == date
               if date_mask.sum() > 5:
                   ic, _ = spearmanr(alpha[date_mask], target[date_mask])
                   if not np.isnan(ic):
                       fold_daily_ics.append(ic)
           fold_ics.append(np.mean(fold_daily_ics) if fold_daily_ics else 0.0)
       
       return float(np.mean(fold_ics) / max(np.std(fold_ics, ddof=1), config.fold_ir_std_floor))
   ```
   **Why critical**: Aligns GP optimization objective with validation/selection metric. Naturally deflates inflated IR.

**Expected**: TrainIC_daily ~0.08-0.15 (realistic). Evolution optimizes what we select on.

---

### Phase 2: 3-Way Split + Embargo + PIT Universe (High → Medium Risk after fixes)
**Files**: `scripts/genetic_alpha_evolution_v3.py`, `scripts/phase35_data_loader.py`

**CRITICAL FIXES (Codex)**:
1. **No test leakage**: Use ONLY validation IC for selection. OOS/lockbox = report only.
2. **Rolling PIT universe**: Replace static top-100 with per-stage dynamic universe.
3. **Trading-day embargo**: Purge ≥5 trading days (not calendar), respect VN holidays.

```python
# Stage definitions with rolling PIT universe
EMBARGO_TRADING_DAYS = 5  # purge >= forward return horizon

def get_pit_universe(df, start_date, end_date, min_adtv_vnd=5e9, min_price=5000, top_n=100):
    """Select universe using ONLY data available up to start_date."""
    # NOTE (Claude Code): Pseudocode - reconcile schema: use 'ticker' not 'symbol', compute adtv from close*volume
    hist_window = df[df['date'] < start_date].tail(252 * 100)  # 1yr lookback
    eligible = hist_window.groupby('ticker').filter(  # CORRECTED: 'ticker' not 'symbol'
        lambda g: (g['close'].mean() * g['volume'].mean() >= min_adtv_vnd) and (g['close'].mean() >= min_price)  # CORRECTED: compute adtv
    )
    top_tickers = eligible.groupby('ticker')['close'].mean().mul(eligible.groupby('ticker')['volume'].mean()).nlargest(top_n).index.tolist()
    return df[(df['date'] >= start_date) & (df['date'] <= end_date) & (df['ticker'].isin(top_tickers))]

stages = [
    {
        'name': 'Stage1_COVID',
        'train': get_pit_universe(df, '2015-01-05', '2018-12-31', ...),
        'val':   get_pit_universe(df, '2019-01-02', '2019-12-31', ...),  # 5-day gap after train
        'oos':   get_pit_universe(df, '2020-01-02', '2020-12-31', ...),  # 5-day gap after val
    },
    # ... similar for Stage2_Bear2022, Stage3_Recovery
]

lockbox = get_pit_universe(df, '2025-01-02', '2026-05-14', ...)  # NEVER touched until final
```

**Implementation**:
- Run evolution on train set
- **Select** top-K by **validation IC ONLY** (NOT train ICIR, NOT oos_ic, NOT lockbox_ic)
- Report OOS IC per stage (logging only, NOT selection)
- Final lockbox IC reported once at very end (logging only)

**Selection gates** (CORRECTED - Codex):
- `val_ic_daily >= 0.015` ← ONLY validation used for selection
- `val_ic_daily_std <= 0.03` ← stability check

**Report only** (NOT selection criteria):
- OOS IC per stage
- Lockbox IC (final report)
- Regime breakdown

**Expected**: Validation IC ~40-70% of train IC. Eliminates multiple comparisons + survivorship bias.

---

### Phase 3: Penalty Rescaling (Medium-High Risk - Codex Corrected)
**Files**: `scripts/genetic_alpha_evolution_v3.py`, `src/omega/quant/evolution/genetic_engine.py`

**CRITICAL NOTE (Codex)**: Turnover penalty hiện dùng flat diff → sai cho panel VN. Rescale penalty trước khi sửa metric = noise.

#### 3a. Increase Time Folds
```python
# genetic_alpha_evolution_v3.py GPConfig
time_folds = 8  # was 3
fold_ir_std_floor = 0.03  # was 0.01
```

#### 3b. Cap ICIR
```python
# genetic_engine.py _compute_time_fold_ir (line ~265)
raw_ir = np.mean(fold_ics) / max(np.std(fold_ics, ddof=1), config.fold_ir_std_floor)
capped_ir = float(np.clip(raw_ir, -2.0, 2.0))
```

#### 3c. Rescale Penalties (DEFERRED per Codex)
**Issue**: Turnover penalty uses flat `np.sum(np.abs(np.diff(alpha)))` → wrong for panel data (cross-ticker contamination).

**Decision**: 
- Increase `time_folds` and cap ICIR (safe, immediate benefit)
- **DEFER** turnover/ortho penalty rescaling to future gate (after fixing turnover metric to be ticker-aware)
- Keep current penalty weights temporarily

**Expected**: Penalties become more stable with 8 folds + capped IR. Full rescaling after turnover fix.

---

### Phase 4: Date-Aware CS Ops OR Disable Unsafe Primitives (High Risk - Codex Corrected)
**Files**: `src/omega/quant/evolution/genetic_engine.py`

**CRITICAL FIXES (Codex)**:
1. **Preserve semantic**: cs_rank must stay percentile [0,1], NOT ordinal 1..N (would break fitness scale)
2. **Prefer lazy path**: Disable unsafe `cs_*` primitives first, re-enable after tested date-aware impl

**Current Issue**: `cs_rank()` and `cs_zscore()` operate on flattened arrays, mixing dates → regime/time artifacts.

**Recommended Approach (Codex/Claude Code - lazy path - CORRECTED)**:
```python
# scripts/genetic_alpha_evolution_v3.py GPConfig
# TEMPORARILY disable unsafe primitives until date-aware impl tested
# Claude Code verified: no primitive_set, use config.unary_ops/ts_ops
# CRITICAL: Must include 'rank' (has same flat-array bug as cs_rank)

config = GPConfig(
    # ... other config ...
    unary_ops=[op for op in DEFAULT_UNARY_OPS if op not in ['rank', 'cs_rank', 'cs_zscore']],
    ts_ops=[],  # disable ALL ts_ops (ts_mean, ts_rank, ts_std, decay_linear)
)

# Note: cs_demean, ts_delta don't exist - removed from disable list
```

**Alternative Approach (if need CS ops immediately)**:
Make date-aware while preserving percentile semantic:
```python
def cs_rank_date_aware(arr: np.ndarray, dates: np.ndarray) -> np.ndarray:
    """Cross-sectional percentile rank [0,1] within each date."""
    result = np.full_like(arr, np.nan, dtype=float)
    for date in np.unique(dates):
        mask = dates == date
        date_values = arr[mask]
        if mask.sum() > 1:
            ranks = scipy.stats.rankdata(date_values, nan_policy='omit')
            result[mask] = (ranks - 1) / (len(ranks) - 1)  # percentile [0,1]
    return result
```

**Integration**: Add `__date__` to features dict, update `_register_functions`.

**Risk**: High. Prefer lazy path (disable first), test thoroughly before re-enable.

---

### Phase 5: Disable TS Ops (Low Risk - MANDATORY in Minimum Scope)
**Files**: `scripts/genetic_alpha_evolution_v3.py` (in GPConfig, same location as Phase 4)

**CRITICAL (Codex + Claude Code)**: MANDATORY, NOT optional. TS ops chạy flat array → rolling cross-ticker contamination. Must be in phases 1-5 minimum scope.

**Current Issue**: TS ops (ts_mean, ts_rank, ts_std, decay_linear) run on flat panel arrays → can cross ticker boundaries.

**Decision**: DISABLE ts_ops in Phase 5 via GPConfig (same as Phase 4). Re-enable only after ticker-aware impl + comprehensive regression tests.

**Implementation** (CORRECTED - Codex):
```python
# scripts/genetic_alpha_evolution_v3.py GPConfig
# Phase 5 is part of same GPConfig as Phase 4
config = GPConfig(
    # ... other config ...
    ts_ops=[],  # disable ALL ts_ops (ts_mean, ts_rank, ts_std, decay_linear)
)
```

---

### Phase 6: Ensemble & Selection (Medium Risk - Codex Corrected)
**Files**: `scripts/genetic_alpha_evolution_v3.py`, `scripts/alpha_evolution_pipeline.py`

**CRITICAL (Codex)**: Ensemble = another optimizer layer. Freeze weights from validation ONLY, evaluate ONCE on OOS/lockbox.

**ADJUST EXPECTATIONS (Codex)**: GP alphas highly correlated. sqrt(N) benefit quá lạc quan. Use covariance-aware expectation.

Replace equal-weight top-K with validation-IC-weighted, decorrelated ensemble:

```python
def select_ensemble(candidates, val_signals, val_ic_threshold=0.015, max_corr=0.6, max_alphas=10):
    """Select diverse, high-IC ensemble. Freeze on validation IC only."""
    # Filter by VALIDATION IC only (no OOS/lockbox in selection)
    pool = [c for c in candidates if c['val_IC'] >= val_ic_threshold]
    pool.sort(key=lambda x: x['val_IC'], reverse=True)
    
    selected = []
    for candidate in pool:
        if len(selected) >= max_alphas:
            break
        
        # Check correlation with already-selected (on VALIDATION signals only)
        signal = candidate['val_signal']
        is_diverse = True
        for s in selected:
            corr = np.corrcoef(signal, s['val_signal'])[0, 1]
            if abs(corr) > max_corr:
                is_diverse = False
                break
        
        if is_diverse:
            selected.append(candidate)
    
    # Weight by validation IC, shrunk 50% to equal-weight
    weights = np.array([c['val_IC'] for c in selected])
    weights = 0.5 * (weights / weights.sum()) + 0.5 / len(selected)
    
    return selected, weights

# Evaluate ensemble ONCE on OOS/lockbox (report only, NOT for re-optimization)
```

**Expected (Codex - covariance-aware)**: With typical GP alpha correlation ~0.5-0.7, ensemble of N=8 alphas with mean IC=0.03 → blended IC ~0.04-0.05 (NOT 0.03×sqrt(8)=0.08).

---

### Phase 7: Missing Elements (Medium Risk - Codex Required)
**Files**: `scripts/genetic_alpha_evolution_v3.py`, `scripts/phase35_data_loader.py`

**CRITICAL MISSING (Codex)**:

#### 7a. Regime IC Breakdown
```python
# Report IC by major VN market regimes
REGIMES = {
    'COVID_2020': ('2020-01-01', '2020-12-31'),
    'Bear_2022': ('2022-01-01', '2022-12-31'),
    'Recovery_2023': ('2023-01-01', '2023-12-31'),
    'Recent_2024': ('2024-01-01', '2024-12-31'),
    'Lockbox_2025': ('2025-01-01', '2026-05-14'),
}

# Reject if any regime IC < -0.01
```

#### 7b. Net-of-Cost Check
- VN round-trip cost: 27 bps (0.27%)
- Turnover: daily position change
- Board lot: 100 shares
- ADV/capacity check per symbol
- Limit up/down impact

#### 7c. VN Trading Calendar
- Implement proper embargo with VN trading days (not calendar days)
- Respect VN holidays for train/val/test splits
- Purge forward-return horizon at boundaries

#### 7d. Statistical Validation
- BH-FDR (Benjamini-Hochberg False Discovery Rate) for multiple testing
- Null y-shuffle baseline (permutation test)
- Multi-seed stability check
- IC confidence intervals

#### 7e. SoD Path Fix (CRITICAL)
**Issue**: Plan currently at `.gemini\antigravity-ide\brain\...` (scratch path)
**Fix**: Copy final approved plan to `.ly_state/session/gp_overfitting_remediation_plan_gate4.md` for formal gate evidence

---

## Rollback & Testing

**Rollback Flags**:
- `use_walk_forward_validation = True` (new config flag)
- Can revert to single-split if walk-forward issues detected

**NO ROLLBACK** to global CS ops or re-enabling unsafe primitives - those are bugs, not features.

**Testing**:
- Unit tests for date-aware ops (verify per-date behavior)
- Regression test: old config should produce similar trees
- Smoke test: 1 round, 10 pop, 3 gens, validate logs

**Expected Timeline**:
- Phases 1-2: 2-3 hours (metric + split)
- Phase 3: 1-2 hours (penalties)
- Phases 4-5: 1 hour (disable unsafe ops - LOW RISK, mandatory)
- Phase 7e: 30 min (move plan to .ly_state)
- Phase 6: 2 hours (ensemble)
- Phases 7a-d: deferred to future gate

---

## Success Metrics

**Before fixes**:
- TrainICIR: 5.35
- TestIC: 0.014
- TestIC/TrainICIR ratio: 0.3%

**After fixes (realistic targets)**:
- TrainIC (raw): 0.08-0.15
- ValidationIC: 0.05-0.10
- TestIC: 0.03-0.08
- Validation/Train ratio: ≥40%
- Ensemble test IC: 0.05-0.08

**Red flags to reject**:
- ValidationIC < 0.01
- Train/Val IC gap > 0.05
- Any stage OOS IC < 0
- Negative lockbox IC

---

## Implementation Order

**Recommended (Claude Code corrected)**:
1. Phase 1 (labels + evolution objective daily CS IC) - CRITICAL alignment
2. Phase 2 (3-way split + rolling PIT + embargo) - highest leverage
3. Phase 3 (increase folds, cap ICIR) - stabilize
4. Phase 4 (disable unsafe CS primitives) - MANDATORY in minimum scope
5. Phase 5 (disable TS ops) - MANDATORY in minimum scope
6. Phase 7e (move plan to .ly_state) - SoD requirement
7. Phase 6 (ensemble) - harvest gains
8. Phase 7a-d (regime IC, net-of-cost, stats) - validation

**Minimum scope for Gate 4**: Phases 1-5 + 7e (all MANDATORY per Claude Code)

---

## Gate 4 Checklist

- [ ] Codex review plan
- [ ] Claude Code review plan
- [ ] Both approve
- [ ] L2 OpenCode implement (phases 1-5 + 7e mandatory)
- [ ] L3 Codex audit
- [ ] SoD enforcer [PASS]
- [ ] Commit & push
- [ ] Run smoke test and compare IC metrics
