# Gate 7: Size/Sector Neutralization + Liquidity Filter

**Version**: 1.0  
**Created**: 2026-07-04  
**Parent Plan**: gp_improvement_plan_20260703.md (Phase 2 & 4)

## Objective

Implement remaining 2 phases from GP Improvement Plan:
- **Phase 2**: Size/sector neutralization before IC computation
- **Phase 4**: Avg-volume liquidity filter

This completes the 5-phase GP improvement roadmap (Phases 1,3,5 done in Gate 6).

---

## Phase 2: Reconcile Existing Neutralization + Fix K=3 Contract

### Current State (Gates 2-3 Already Implemented ~80%)

**EXISTING INFRASTRUCTURE**:
- ✅ `log_market_cap`: Already computed and shifted (lines 127, 130)
- ✅ Sector proxy: Uses `_volume_quartile_sector_proxy()` (lines 88, 128) - NOT CSV
- ✅ Metadata: `__log_market_cap__` and `__sector__` already in train/val/oos/lockbox (lines 616-633)
- ✅ Config: `neutralize_size_sector=True` already set (line 662)
- ✅ Neutralization: `_neutralize_cross_section()` (line 117) + `_batch_neutralize_cross_section()` (line 168) with per-date design cache (`_build_neutralization_cache`, line 90)
- ✅ Integration: Wired into pooled (line 829), fold (line 249), batch (line 1385) IC paths

**CURRENT BEHAVIOR**: Neutralizes **ALPHA ONLY**, not target.

### Problems to Fix

1. **Gate 6 K=3 Contract Violation** (CONFIRMED BUG):
   - Current code: `time_folds=8` (line 660)
   - Gate 6 contract: `time_folds=3`
   - **Must fix**: Change to 3

2. **Alpha-Only vs Both Neutralization** (METHODOLOGY DECISION):
   - Current: Neutralizes alpha residual against size/sector
   - Proposed: Also neutralize target
   - **Decision needed**: Alpha-only already removes IC inflation (alpha residual is orthogonal to size/sector by construction). Neutralizing target is a research choice requiring explicit rationale.

3. **Volume-Quartile Semantics** (DOCUMENTATION GAP):
   - Plan sells "economic sector" neutralization
   - Code uses volume quartile as "sector" proxy
   - **Must document**: Clarify semantics in code

### Implementation (RECONCILE, DON'T REBUILD)

#### File 1: `scripts/genetic_alpha_evolution_v3.py`

**Changes**:
#### File 1: `scripts/genetic_alpha_evolution_v3.py`

**Changes** (reconcile with existing, DON'T rebuild):

1. **FIX K=3 Bug** (lines 658-661 - CONFIRMED BUG):
   ```python
   # BEFORE (wrong):
   time_folds=8,
   
   # AFTER (correct - Gate 6 K=3 contract):
   time_folds=3,
   ```

2. **Document volume-quartile semantics** (line 128):
   ```python
   # NOTE: 'sector' here = volume quartile proxy (Q1/Q2/Q3/Q4)
   # This is a LIQUIDITY proxy, not economic sector classification
   # Uses _volume_quartile_sector_proxy() - see line 88
   # CSV sector_mapping_level2.csv is NOT used
   df["sector"] = _volume_quartile_sector_proxy(df)
   ```

3. **NO new metadata needed** (lines 616-633 already exist):
   ```python
   # EXISTING (no change needed):
   features_train["__sector__"] = train_df["sector"].values
   features_train["__log_market_cap__"] = train_df["log_market_cap"].values
   # Already done for val/oos/lockbox too
   ```


#### File 2: `src/omega/quant/evolution/genetic_engine.py`

**Changes** (extend existing, DON'T add parallel helper):

1. **NO NEW GPConfig fields needed** - neutralization fields already exist from Gates 2-3:
   ```python
   # EXISTING (no change):
   neutralize_size_sector: bool  # line ~267
   neutralize_min_cross_section: int
   neutralize_size_key: str
   neutralize_sector_key: str
   ```

2. **DO NOT add new `_residualize_size_sector()` helper** - use existing:
   ```python
   # EXISTING helpers (don't duplicate):
   _neutralize_cross_section()   # line 117
   _batch_neutralize_cross_section()  # line 168
   _build_neutralization_cache()  # line 90 (per-date design cache)
   ```

3. **METHODOLOGY DECISION: Extend neutralization to target** (research choice):
   - **Option A**: Keep alpha-only (current) - already orthogonal by construction
   - **Option B**: Also neutralize target - cleaner IC semantics, standard in literature
   - **Gate 7 Decision**: Option B
   
   **Implementation** (extend existing, no new helper, no signature change):
   - Find all callers of `_neutralize_cross_section` in IC paths (lines 249, 829, 1385)
   - After each call residualizes alpha, add a second call to residualize target:
   ```python
   # EXISTING call (don't change signature):
   alpha_resid = _neutralize_cross_section(alpha_arr, log_mcap_arr, sector_arr, date_arr,
                                            neutralization_cache=cache)
   # NEW: mirror call for target residualization:
   target_resid = _neutralize_cross_section(target_arr, log_mcap_arr, sector_arr, date_arr,
                                             neutralization_cache=cache)
   # Use target_resid instead of raw target in spearmanr
   ```
   
   **Rationale**: Option B gives IC that measures pure signal quality, independent of size/sector exposure.

4. **Update ALL IC paths to pass target to neutralization** (extend existing calls):
   - Pooled IC path (line 829): pass target to `_neutralize_cross_section`
   - Time-fold IR path (line 249): currently alpha-only → extend to target
   - Batch path (line 1385): currently alpha-only → extend to target
   - Multi-target IC path: align consistently

5. **Add `_evaluation_mask()` helper** (new, for Phase 4 liquidity):
   ```python
   def _evaluation_mask(
       alpha_series: np.ndarray,
       target: np.ndarray,
       features: dict
   ) -> np.ndarray:
       """Centralized mask combining finite check + liquidity filter."""
       mask = np.isfinite(alpha_series) & np.isfinite(target)
       if "__liquidity_mask__" in features:
           mask &= features["__liquidity_mask__"]
       return mask
   ```
   Use this mask in `_score_alpha_series()` observation count AND all IC computation paths.

### Verification

**Test**: `tests/test_genetic_engine_neutralization.py`

```python
def test_size_sector_neutralization_removes_common_exposure():
    """
    Synthetic test: alpha and target both contaminated by size + sector.
    
    Setup:
    - true_signal: independent cross-sectional signal
    - alpha = true_signal + 3*log_mcap + sector_effect
    - target = true_signal + 2*log_mcap + sector_effect
    
    Without neutralization: IC inflated by common exposure
    With neutralization: IC reflects only true_signal
    """
    np.random.seed(42)
    n_dates = 10
    n_symbols = 50
    
    # Generate synthetic data
    dates = np.repeat(np.arange(n_dates), n_symbols)
    sectors = np.random.choice(['A', 'B', 'C'], size=n_dates*n_symbols)
    log_mcap = np.random.randn(n_dates*n_symbols)
    true_signal = np.random.randn(n_dates*n_symbols)
    
    # Contaminate with size + sector
    sector_effect = np.where(sectors == 'A', 1.0, np.where(sectors == 'B', -0.5, 0.0))
    alpha = true_signal + 3*log_mcap + sector_effect
    target = true_signal + 2*log_mcap + sector_effect
    
    # Without neutralization
    ic_raw, _ = spearmanr(alpha, target)
    
    # With neutralization - use EXISTING engine path
    # Call the existing evaluation_mask + neutralize path through the engine
    # (does NOT use _residualize_size_sector - that helper must NOT be created)
    features = {
        "__date__": dates,
        "__log_market_cap__": log_mcap,
        "__sector__": sectors
    }
    mask = np.ones(len(alpha), dtype=bool)
    config = GPConfig(neutralize_size_sector=True)
    
    # Use existing _neutralize_cross_section from Gates 2-3 (correct signature):
    alpha_resid = _neutralize_cross_section(alpha, log_mcap, sectors, dates,
                                             neutralization_cache=None)
    target_resid = _neutralize_cross_section(target, log_mcap, sectors, dates,
                                              neutralization_cache=None)
    ic_neutral, _ = spearmanr(alpha_resid, target_resid)
    
    # Assertions
    assert ic_raw > 0.7  # High IC due to common factors
    assert 0.4 < ic_neutral < 0.7  # Lower IC after neutralization (only true_signal remains)
```

---

## Phase 4: Liquidity Filter

### Problem

Current IC includes all rows regardless of liquidity. Low-volume rows can:
- Have stale prices
- Large bid-ask spreads
- Unreliable signals

These contaminate IC and are untradeable.

### Solution

**Filter rows by trailing average TRADED VALUE** (VND = close × volume) before IC computation:
```python
# CORRECT: Use traded value (VND), not raw volume (shares)
df["traded_value"] = df["close"] * df["volume"]
df["avg_traded_value"] = (
    df.groupby("ticker")["traded_value"]
    .rolling(20, min_periods=5).mean()
    .reset_index(level=0, drop=True)  # reset before shift
)
df["avg_traded_value"] = df.groupby("ticker")["avg_traded_value"].shift(1)  # ticker-local PIT
liquidity_mask = df["avg_traded_value"] > min_avg_volume
```

Only rows with `liquidity_mask=True` contribute to IC.

### Implementation

#### File 1: `scripts/genetic_alpha_evolution_v3.py`

**Changes**:
1. Add CLI parameters (FIX units - use traded value in VND, not shares):
   ```python
   parser.add_argument("--min-avg-volume", type=float, default=500000.0,
                       help="Minimum 20-day average TRADED VALUE in VND (close * volume)")
   parser.add_argument("--avg-volume-window", type=int, default=20,
                       help="Window for average volume calculation")
   ```

2. In `load_dataset()`, compute liquidity mask (CRITICAL: use traded value, not shares):
   ```python
   # CRITICAL: Compute trailing average TRADED VALUE (VND), not volume (shares)
   # This matches --min-avg-volume threshold units
   df["traded_value"] = df["close"] * df["volume"]
   
   # Compute rolling mean per ticker (PIT-safe with proper shift)
   df["avg_traded_value"] = (
       df.groupby("ticker")["traded_value"]
       .rolling(args.avg_volume_window, min_periods=5)
       .mean()
       .reset_index(level=0, drop=True)  # CRITICAL: reset_index before shift
   )
   
   # CRITICAL: Shift by ticker to ensure PIT safety
   df["avg_traded_value"] = df.groupby("ticker")["avg_traded_value"].shift(1)
   
   # Liquidity mask (filter low-liquidity rows)
   df["liquidity_mask"] = df["avg_traded_value"] > args.min_avg_volume
   
   # Log exclusion rate for monitoring
   exclusion_rate = 1.0 - df["liquidity_mask"].mean()
   if exclusion_rate > 0.5:
       logger.warning(f"Liquidity filter excludes {exclusion_rate:.1%} of rows. Consider lowering threshold.")
   ```

3. Add to features metadata (include for train/val/oos/lockbox, not just train/test):
   ```python
   features_train["__liquidity_mask__"] = train_df["liquidity_mask"].values
   features_test["__liquidity_mask__"] = test_df["liquidity_mask"].values
   ```

#### File 2: `src/omega/quant/evolution/genetic_engine.py`

**Changes**:
1. Add centralized evaluation mask (already shown above in Phase 2 section)

2. Update `_score_alpha_series()` to use centralized mask:
   ```python
   # CRITICAL: Use centralized mask for observation counting
   # Current code only checks pd.notna(target) - must include liquidity
   mask = _evaluation_mask(alpha_series, target, features)
   
   if mask.sum() < config.min_observations:
       return 0.0  # Reject before IC computation
   ```

3. Update validation scoring to be engine-consistent (FIX raw ranking issue):
   ```python
   # CRITICAL: Replace raw validation IC at genetic_alpha_evolution_v3.py:690-693
   # Current code uses spearmanr(signal, target_val) directly - not engine-consistent
   
   # NEW: Use engine-consistent scoring helper
   def score_individual_consistent(ind, features, target, config):
       """
       Score individual using SAME logic as training:
       - Centralized evaluation mask (liquidity filter)
       - Neutralization if enabled
       - K=3 fold IR if enabled
       
       Returns: (ic_or_ir, hit_rate)
       """
       signal = ind.execute(features)
       # Apply same preprocessing as _compute_combined_ic
       mask = _evaluation_mask(signal, target, features)
       
       if mask.sum() < config.min_observations:
           return 0.0, 0.0
         # Neutralize both if enabled (use EXISTING engine path, not new helper)
           if config.neutralize_size_sector and "__sector__" in features:
               # Call through existing _compute_combined_ic with neutralization
               # which internally uses _neutralize_cross_section (existing, Gate 2-3)
               signal_neutral = existing_neutralize(signal, features, mask, config)
               target_resid = existing_neutralize(target, features, mask, config)
           else:
               signal_neutral, target_resid = signal, target
   
           # Compute IC using existing engine (fold IR if enabled)
           # Note: _compute_combined_ic handles time_fold_ir internally
           ic = ind._compute_combined_ic_from_signal(
               signal_neutral[mask], target_resid[mask],
               features, config
           )
   
           # Hit rate on filtered rows
           hit = (np.sign(signal[mask]) == np.sign(target[mask])).mean()
   
           return ic, hit
   ```
   
   **IMPORTANT**: L2 must use the EXISTING engine's neutralization path (Gates 2-3 `_neutralize_cross_section`), NOT create a new `_residualize_size_sector` helper.
   Replace raw validation ranking with this helper to ensure selection criteria match training.


### Verification

**Test**: `tests/test_genetic_engine_liquidity.py`

```python
def test_liquidity_mask_excludes_low_volume_rows():
    """
    Low-volume rows have misleading perfect correlation.
    High-volume rows have weaker but realistic correlation.
    
    With mask disabled: IC inflated by low-volume noise
    With mask enabled: IC reflects only liquid rows
    """
    np.random.seed(42)
    n = 100
    
    # Setup
    alpha = np.random.randn(n)
    target = 0.5 * alpha + 0.5 * np.random.randn(n)
    
    # First 20 rows: low volume, perfect correlation (noise)
    target[:20] = alpha[:20]
    liquidity_mask = np.ones(n, dtype=bool)
    liquidity_mask[:20] = False
    
    # Without mask
    ic_all, _ = spearmanr(alpha, target)
    
    # With mask
    ic_liquid, _ = spearmanr(alpha[liquidity_mask], target[liquidity_mask])
    
    assert ic_all > ic_liquid  # Mask reduces IC by excluding noise
    assert ic_liquid > 0.4  # But signal remains positive
```

---

## Integration Notes

### Interaction with Gate 6 Features

Gate 6 implemented:
- Phase 1: Raw OHLC removed ✅
- Phase 3: K=3 chronological fold IR ✅
- Phase 5: Test IC matching training ✅

Gate 7 adds:
- Phase 2: Neutralization (works with fold IR)
- Phase 4: Liquidity filter (applies to all IC paths)

**Critical**: All Phase 2 & 4 changes must integrate with existing fold IR logic from Gate 6.

### PIT Safety Checklist

- ✅ `log_market_cap` shifted by ticker (existing, Gate 2-3)
- ✅ `avg_traded_value` shifted per-ticker (NOT global shift after groupby)
- ✅ `sector` = volume quartile proxy (static classification, no future data)
- ✅ Neutralization uses only T-1 controls (existing infrastructure)
- ✅ Liquidity mask uses only T-1 avg traded value

---

## Files to Modify

| File | Changes | Lines Affected |
|------|---------|----------------|
| `scripts/genetic_alpha_evolution_v3.py` | Fix time_folds=8→3, add CLI args, doc volume-quartile | ~20 lines |
| `src/omega/quant/evolution/genetic_engine.py` | Add _evaluation_mask, extend target neutralization | ~80 lines |
| `tests/test_genetic_engine_liquidity.py` | New liquidity mask test | ~60 lines |

---

## Validation Protocol

### Stage 1: Unit Tests
```powershell
pytest tests/test_genetic_engine_neutralization.py tests/test_genetic_engine_liquidity.py -v
```

### Stage 2: Smoke Test
```powershell
python scripts/genetic_alpha_evolution_v3.py `
  --rounds 1 `
  --population-size 20 `
  --generations 3 `
  --workers 2 `
  --min-avg-volume 500000
```

**Expected**:
- Training uses neutralized fold IR
- Liquidity mask reduces row count
- Results still register to conformal_registry.sqlite

### Stage 3: Full Run
```powershell
python scripts/genetic_alpha_evolution_v3.py `
  --rounds 5 `
  --population-size 50 `
  --generations 20 `
  --workers 10 `
  --backend loky `
  --min-avg-volume 500000
```

**Expected**:
- Alphas have cleaner IC (less size/sector bias)
- Lower turnover (liquidity filter removes noise)
- Better OOS/Lockbox IC stability

---

## Success Criteria

### Gate 7 Passes If:

1. ✅ **Phase 2 Implemented**:
   - Existing `_neutralize_cross_section` EXTENDED to residualize target (not new helper)
   - `time_folds` fixed from 8 → 3 (K=3 contract restored)
   - Volume-quartile semantics documented in code comments
   - Test proves target neutralization reduces common-factor IC

2. ✅ **Phase 4 Implemented**:
   - `--min-avg-volume` CLI parameter works
   - Liquidity mask excludes low-volume rows
   - IC observation counts reduced appropriately
   - Test proves noise exclusion

3. ✅ **Integration Works**:
   - Neutralization compatible with fold IR (Gate 6)
   - All IC paths (pooled, ICIR, fold) use liquidity mask
   - PIT safety maintained
   - Tests pass (10+ tests)

4. ✅ **Production Validation**:
   - Smoke run completes successfully
   - Full run generates alphas with cleaner IC
   - SoD enforcer passes
   - L3 audit approves

---

---

## SoD Dispatch Plan

### L2 Implementation (OpenCode)
**Role**: 16 (machine-learning-engineer)
**Scope**: Implement Phase 2 & 4 per this plan
**Output**: L2 report + code changes + tests

### L3 Audit (Codex)
**Role**: 23 (performance-tester)
**Scope**: Verify correctness, PIT safety, integration with Gate 6
**Output**: L3 report + verdict [APPROVED / NEEDS_FIX]

### L1 Gate Control (Orchestrator)
**Actions**:
1. Update phase_gates.json with Gate 7 entry
2. Run sod_gate_enforcer.py
3. Commit & push if APPROVED

---

**Plan Ready for L2 Dispatch** ✅
