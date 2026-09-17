# Gate 5: GP Ensemble & Selection - Implementation Plan

**Date**: 2026-07-04  
**Prerequisite**: Gate 4 complete (Phases 1-5 implemented & pushed)  
**Context**: GP evolution now uses daily CS IC, validation-only selection, rolling PIT, disabled unsafe primitives.

---

## Objective

Implement validation-IC-weighted, decorrelated ensemble of top GP alphas to harvest additional gains beyond single-best selection.

**Expected Impact**: 
- Ensemble IC: 0.04-0.05 (for N=8 alphas with mean IC=0.03, correlation=0.5-0.7)
- Reduced idiosyncratic risk through decorrelation
- More stable performance across regimes

---

## Current State Analysis

**Gate 4 Results** (expected):
- Single best alpha selected by validation IC
- No ensemble or diversification
- High correlation between GP alphas (~0.5-0.7 typical)

**Issues**:
- Missing diversification benefit
- Single-alpha exposure to idiosyncratic risk
- Sqrt(N) gain limited by high correlation

---

## Design Principles (From Original Plan)

1. **Freeze on validation ONLY**: Ensemble weights and selection use validation IC only
2. **Report on OOS/lockbox**: Evaluate ensemble ONCE on OOS and lockbox (no re-optimization)
3. **Decorrelation filter**: Greedily select alphas with low pairwise correlation
4. **IC-weighted with shrinkage**: Weight by validation IC, shrink 50% toward equal-weight
5. **Realistic expectations**: With correlation 0.5-0.7, expect modest gains (not sqrt(N))

---

## Implementation Scope

### Files to Change

1. **`scripts/genetic_alpha_evolution_v3.py`** (main)
   - Add `select_ensemble()` function
   - Add `evaluate_ensemble()` function
   - Update candidate loop to build ensemble
   - Report ensemble metrics

2. **`scripts/alpha_evolution_pipeline.py`** (optional)
   - Pipeline integration if needed

3. **`tests/test_genetic_alpha_evolution_v3.py`** (tests)
   - Test ensemble selection logic
   - Test decorrelation filter
   - Test IC weighting

---

## Detailed Design

### 1. Ensemble Selection Function

```python
def select_ensemble(
    candidates: List[Dict],
    val_signals: Dict[str, np.ndarray],
    val_ic_threshold: float = 0.015,
    max_corr: float = 0.6,
    max_alphas: int = 10,
) -> Tuple[List[Dict], np.ndarray]:
    """Select diverse, high-IC ensemble from candidates.
    
    CRITICAL: Freeze selection on VALIDATION IC only.
    
    Args:
        candidates: List of candidate dicts with 'val_IC_daily', 'tree', 'val_signal'
        val_signals: Dict of validation signals keyed by candidate ID
        val_ic_threshold: Minimum validation IC to include
        max_corr: Maximum pairwise correlation threshold
        max_alphas: Maximum ensemble size
        
    Returns:
        selected: List of selected candidate dicts
        weights: np.ndarray of ensemble weights (sum to 1.0)
    """
    # Filter by VALIDATION IC only (no OOS/lockbox in selection)
    pool = [c for c in candidates if c['val_IC_daily'] >= val_ic_threshold]
    pool.sort(key=lambda x: x['val_IC_daily'], reverse=True)
    
    if not pool:
        return [], np.array([])
    
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
    
    if not selected:
        # Fallback: top-1 if decorrelation filters everyone
        selected = [pool[0]]
    
    # Weight by validation IC, shrunk 50% to equal-weight
    val_ics = np.array([c['val_IC_daily'] for c in selected])
    ic_weights = val_ics / val_ics.sum()
    equal_weights = np.ones(len(selected)) / len(selected)
    weights = 0.5 * ic_weights + 0.5 * equal_weights
    
    return selected, weights
```

### 2. Ensemble Evaluation Function

```python
def evaluate_ensemble(
    selected: List[Dict],
    weights: np.ndarray,
    oos_signals: Dict[str, np.ndarray],
    lockbox_signals: Dict[str, np.ndarray],
    oos_target: np.ndarray,
    lockbox_target: np.ndarray,
    oos_dates: np.ndarray,
    lockbox_dates: np.ndarray,
) -> Dict[str, float]:
    """Evaluate ensemble ONCE on OOS and lockbox (report only).
    
    CRITICAL: No re-optimization using OOS/lockbox. Report only.
    
    Returns:
        metrics: Dict with 'oos_IC_daily', 'lockbox_IC_daily'
    """
    # Build ensemble signals (weighted sum)
    oos_ensemble = np.zeros_like(oos_target)
    lockbox_ensemble = np.zeros_like(lockbox_target)
    
    for candidate, weight in zip(selected, weights):
        cand_id = candidate['id']
        oos_ensemble += weight * oos_signals[cand_id]
        lockbox_ensemble += weight * lockbox_signals[cand_id]
    
    # Compute daily CS IC (report only, NOT for selection)
    oos_ic = compute_daily_cs_ic(oos_ensemble, oos_target, oos_dates)
    lockbox_ic = compute_daily_cs_ic(lockbox_ensemble, lockbox_target, lockbox_dates)
    
    return {
        'oos_IC_daily': oos_ic,
        'lockbox_IC_daily': lockbox_ic,
    }
```

### 3. Integration into Main Script

```python
# In genetic_alpha_evolution_v3.py main flow

# After single-best selection and validation
best_candidate = max(candidates, key=lambda x: x['val_IC_daily'])

# Build ensemble
selected_ensemble, ensemble_weights = select_ensemble(
    candidates=candidates,
    val_signals={c['id']: c['val_signal'] for c in candidates},
    val_ic_threshold=0.015,
    max_corr=0.6,
    max_alphas=10,
)

# Evaluate ensemble on OOS/lockbox (report only)
if selected_ensemble:
    ensemble_metrics = evaluate_ensemble(
        selected=selected_ensemble,
        weights=ensemble_weights,
        oos_signals={c['id']: c['oos_signal'] for c in candidates},
        lockbox_signals={c['id']: c['lockbox_signal'] for c in candidates},
        oos_target=oos_target,
        lockbox_target=lockbox_target,
        oos_dates=oos_dates,
        lockbox_dates=lockbox_dates,
    )
    
    # Report ensemble metrics
    logger.info(f"Ensemble size: {len(selected_ensemble)}")
    logger.info(f"Ensemble weights: {ensemble_weights}")
    logger.info(f"Ensemble OOS IC: {ensemble_metrics['oos_IC_daily']:.4f}")
    logger.info(f"Ensemble lockbox IC: {ensemble_metrics['lockbox_IC_daily']:.4f}")
```

---

## Testing Strategy

### Unit Tests

1. **Test decorrelation filter**:
   - Create synthetic signals with known correlations
   - Verify filter excludes high-correlation pairs

2. **Test IC weighting**:
   - Verify weights are IC-weighted + 50% equal-weight
   - Verify weights sum to 1.0

3. **Test ensemble evaluation**:
   - Verify weighted sum is correct
   - Verify no OOS/lockbox used in selection

### Integration Tests

1. Run full evolution with ensemble enabled
2. Verify ensemble IC >= single-best IC
3. Verify ensemble metrics in logs

---

## Success Metrics

**CRITICAL (Codex)**: Acceptance criteria MUST be validation-only. OOS/lockbox are report-only, NOT acceptance gates.

**Minimum acceptance** (validation-only mechanics):
- Ensemble weights sum to 1.0
- Decorrelation filter correctly excludes pairs with |corr| > max_corr
- No OOS/lockbox inputs in `select_ensemble()` function
- NaN/constant-signal correlation handled gracefully (skip pair, don't crash)
- Ensemble size >= 1 (at least fallback to top-1)

**Report-only** (log once, NOT for approval):
- Ensemble OOS IC (informational)
- Ensemble lockbox IC (informational)
- Comparison to single-best IC (informational)

**Red flags to reject**:
- Ensemble weights don't sum to 1.0
- Implementation uses OOS/lockbox in selection (validation leak)
- Crashes on NaN or constant signals

---

## Rollback Plan

If ensemble performs worse than single-best:
- Add config flag `use_ensemble = False` to disable
- Keep single-best selection as default
- Investigate correlation assumptions

---

## Implementation Checklist

- [ ] Implement `select_ensemble()` function
- [ ] Implement `evaluate_ensemble()` function
- [ ] Integrate into main evolution script
- [ ] Add unit tests for ensemble selection
- [ ] Add integration test for full evolution
- [ ] Update logging to report ensemble metrics
- [ ] Verify no OOS/lockbox leakage in selection
- [ ] Document ensemble parameters in config

---

## Next Steps

1. **Create this plan**: ✓
2. **Review by Codex + Claude Code**: Get approvals
3. **Open Gate 5**: Add to phase_gates.json
4. **L2 Implementation**: Dispatch OpenCode
5. **L3 Audit**: Dispatch Codex for review
6. **SoD Validation**: Run enforcer
7. **Commit & Push**: Merge to branch
