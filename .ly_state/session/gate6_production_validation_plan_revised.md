# Gate 6: Production Validation Suite (Phase 7a-d) - REVISED Implementation Plan

**Date**: 2026-07-04  
**Status**: REVISED per Codex feedback  
**Prerequisite**: Gate 5 complete (commit 5990bc9c)  
**Context**: GP evolution has daily CS IC, validation-only selection, rolling PIT, ensemble, disabled unsafe primitives.

---

## Revision Summary (Codex Feedback)

**Changes from original plan**:

1. ✅ **Calendar**: Reuse `src/omega/data/calendar.py` + `config/vn_holidays.json` (no hardcoded holidays)
2. ✅ **Cost Model**: Reuse `src/omega/execution/vn_transaction_cost_model.py` (no reimplementation)
3. ✅ **Stats**: Fix permutation test to use per-date shuffling + seeded RNG
4. ✅ **Regime**: Clarify regime definitions with explicit rationale
5. ✅ **SoD**: Repo-local plan path (`.ly_state/session/`)

---

## Objective

Implement production-readiness validation suite covering:
- **Regime IC breakdown**: Detect alpha stability across VN market conditions
- **Net-of-cost analysis**: Ensure strategy viability post-fees using VN cost model
- **Calendar-aware logic**: Use programmatic VN trading calendar (no manual embargo)
- **Statistical validation**: Guard against false discoveries with proper permutation tests

---

## Phase 7a: Regime IC Breakdown

### Goal
Report IC by VN market regime to detect regime-specific failures.

### Regime Definitions (Clarified)

```python
# In scripts/genetic_alpha_evolution_v3.py

VN_REGIME_DEFINITIONS = {
    'COVID_2020': {
        'period': ('2020-03-01', '2020-12-31'),
        'rationale': 'COVID-19 pandemic impact, extreme volatility, govt interventions'
    },
    'Bear_2022': {
        'period': ('2022-01-01', '2022-12-31'),
        'rationale': 'VN-Index -33%, global rate hikes, property sector crisis'
    },
    'Recovery_2023': {
        'period': ('2023-01-01', '2023-12-31'),
        'rationale': 'Post-bear recovery, easing inflation, stabilizing property'
    },
    'Recent_2024': {
        'period': ('2024-01-01', '2024-12-31'),
        'rationale': 'Near-term regime, momentum strategies active'
    },
    'Lockbox_2025': {
        'period': ('2025-01-01', '2025-12-31'),
        'rationale': 'Out-of-sample lockbox validation period'
    },
}

def compute_regime_ic(signal, target, dates, regime_definitions):
    """Compute daily CS IC per regime.
    
    Args:
        signal: Alpha signal array
        target: Forward return target
        dates: Date array (pd.Timestamp or str)
        regime_definitions: Dict of regime_name -> {'period': (start, end), 'rationale': str}
    
    Returns:
        Dict[regime_name, ic_value]
    """
    import pandas as pd
    from scipy.stats import spearmanr
    
    regime_ics = {}
    dates = pd.to_datetime(dates)
    
    for regime_name, regime_spec in regime_definitions.items():
        start, end = regime_spec['period']
        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end)
        
        mask = (dates >= start_dt) & (dates <= end_dt)
        if mask.sum() == 0:
            regime_ics[regime_name] = None  # No data in regime
            continue
        
        regime_signal = signal[mask]
        regime_target = target[mask]
        
        # Daily cross-sectional IC (reuse existing compute_daily_cs_ic if available)
        # Simple fallback: pooled Spearman
        valid_mask = np.isfinite(regime_signal) & np.isfinite(regime_target)
        if valid_mask.sum() < 10:
            regime_ics[regime_name] = None
            continue
        
        ic, _ = spearmanr(regime_signal[valid_mask], regime_target[valid_mask])
        regime_ics[regime_name] = ic
    
    return regime_ics
```

### Acceptance Criteria
- Code computes regime IC for all defined regimes
- Logs IC value + rationale for each regime
- **Gate check**: Reject if any regime IC < -0.01 (negative alpha)

---

## Phase 7b: Net-of-Cost Check

### Goal
Estimate net returns after VN transaction costs using existing cost model.

### Implementation (Reuse VNTransactionCostModel)

```python
# In scripts/genetic_alpha_evolution_v3.py

from omega.execution.vn_transaction_cost_model import VNTransactionCostModel, TransactionCostConfig

def compute_turnover(signal, dates):
    """Compute mean daily absolute position change.
    
    Args:
        signal: Position signal (normalized, e.g., rank-demean)
        dates: Date array
    
    Returns:
        float: Mean daily turnover (0-2 range, where 2 = complete flip)
    """
    import pandas as pd
    import numpy as np
    
    dates = pd.to_datetime(dates)
    df = pd.DataFrame({'date': dates, 'signal': signal})
    
    turnover_by_date = []
    for date in df['date'].unique():
        date_mask = df['date'] == date
        curr_signal = df.loc[date_mask, 'signal'].values
        
        # Compare with previous date
        prev_date_mask = df['date'] < date
        if prev_date_mask.sum() > 0:
            prev_signals = df.loc[prev_date_mask].groupby('date').tail(1)
            if len(prev_signals) > 0:
                prev_signal = prev_signals['signal'].values
                if len(prev_signal) == len(curr_signal):
                    turnover = np.mean(np.abs(curr_signal - prev_signal))
                    turnover_by_date.append(turnover)
    
    return np.mean(turnover_by_date) if turnover_by_date else 0.0

def estimate_cost_drag(signal, target, dates, symbols, prices, adv_values):
    """Estimate transaction cost drag using VNTransactionCostModel.
    
    Args:
        signal: Alpha signal
        target: Forward returns
        dates: Dates
        symbols: Stock symbols
        prices: Current prices (VND)
        adv_values: Average daily value (VND notional)
    
    Returns:
        Dict with gross_ic, turnover, cost_drag_bps
    """
    from scipy.stats import spearmanr
    
    # Gross IC
    valid_mask = np.isfinite(signal) & np.isfinite(target)
    gross_ic, _ = spearmanr(signal[valid_mask], target[valid_mask])
    
    # Turnover
    turnover = compute_turnover(signal, dates)
    
    # Cost estimation using VN model
    cost_model = VNTransactionCostModel()
    
    # Estimate per-symbol average cost
    costs_bps = []
    for i in range(len(symbols)):
        if not np.isfinite(signal[i]) or not np.isfinite(prices[i]):
            continue
        
        # Assume unit position size for average cost estimate
        order_size = 100  # VN board lot
        cost_dict = cost_model.estimate_cost(
            symbol=symbols[i],
            order_size=order_size,
            price=prices[i],
            adv_value_vnd=adv_values[i],
            side='buy'  # Average of buy/sell
        )
        costs_bps.append(cost_dict['total_cost_bps'])
    
    avg_cost_bps = np.mean(costs_bps) if costs_bps else 27.0  # Fallback: 27 bps
    
    # Cost drag = turnover * cost
    cost_drag = turnover * (avg_cost_bps / 10000.0)
    
    return {
        'gross_ic': gross_ic,
        'turnover': turnover,
        'avg_cost_bps': avg_cost_bps,
        'cost_drag_estimate': cost_drag,
    }
```

### Acceptance Criteria
- Code reuses `VNTransactionCostModel.estimate_cost()`
- Reports gross IC, turnover, average cost bps, cost drag
- No reimplementation of cost logic

---

## Phase 7c: VN Trading Calendar (Programmatic)

### Goal
Replace manual 5-trading-day embargo with calendar-aware logic using existing VNTradingCalendar.

### Implementation (Reuse calendar.py)

```python
# In scripts/phase35_data_loader.py or genetic_alpha_evolution_v3.py

from omega.data.calendar import VNTradingCalendar
import pandas as pd

def build_vn_trading_days(start_date, end_date):
    """Build VN trading day list using VNTradingCalendar.
    
    Args:
        start_date: str or Timestamp
        end_date: str or Timestamp
    
    Returns:
        pd.DatetimeIndex of trading days
    """
    all_dates = pd.date_range(start_date, end_date, freq='D')
    
    trading_days = [
        dt for dt in all_dates 
        if VNTradingCalendar.is_trading_day(dt)
    ]
    
    return pd.DatetimeIndex(trading_days)

def apply_trading_day_embargo(end_date, embargo_days, trading_calendar):
    """Get date N trading days before end_date.
    
    Args:
        end_date: Target date
        embargo_days: Number of trading days to embargo
        trading_calendar: pd.DatetimeIndex of trading days
    
    Returns:
        pd.Timestamp: Embargo cutoff date
    """
    try:
        idx = trading_calendar.get_loc(pd.Timestamp(end_date))
        embargo_idx = max(0, idx - embargo_days)
        return trading_calendar[embargo_idx]
    except KeyError:
        # Fallback: approximate with calendar days
        return pd.Timestamp(end_date) - pd.Timedelta(days=embargo_days * 1.4)

# Usage in build_split_windows
trading_cal = build_vn_trading_days(data_start, data_end)
train_end_embargo = apply_trading_day_embargo(
    end_date=val_start, 
    embargo_days=5, 
    trading_calendar=trading_cal
)
```

### Acceptance Criteria
- Code imports `VNTradingCalendar` from `omega.data.calendar`
- Uses `config/vn_holidays.json` automatically (via calendar.py)
- No hardcoded holiday lists in GP scripts

---

## Phase 7d: Statistical Validation (Fixed Permutation Test)

### Goal
Guard against false discoveries with proper permutation test using per-date shuffling and seeded RNG.

### Implementation (Fixed)

```python
# In scripts/genetic_alpha_evolution_v3.py

def permutation_test_ic(signal, target, dates, n_permutations=1000, random_seed=42):
    """Permutation test for IC significance with per-date shuffling.
    
    FIXES:
    - Uses per-date shuffling to preserve cross-sectional structure
    - Uses seeded RNG for reproducibility
    
    Args:
        signal: Alpha signal
        target: Forward return target
        dates: Date array
        n_permutations: Number of permutation rounds
        random_seed: RNG seed for reproducibility
    
    Returns:
        Dict with observed_ic, p_value, null_mean, null_std
    """
    from scipy.stats import spearmanr
    import pandas as pd
    import numpy as np
    
    # Observed IC
    valid_mask = np.isfinite(signal) & np.isfinite(target)
    observed_ic, _ = spearmanr(signal[valid_mask], target[valid_mask])
    
    # Per-date permutation
    rng = np.random.RandomState(random_seed)
    null_ics = []
    
    dates = pd.to_datetime(dates)
    df = pd.DataFrame({
        'date': dates,
        'signal': signal,
        'target': target
    })
    
    for perm_i in range(n_permutations):
        # Shuffle target within each date (preserve cross-sectional structure)
        shuffled_targets = []
        for date in df['date'].unique():
            date_mask = df['date'] == date
            date_targets = df.loc[date_mask, 'target'].values
            shuffled = rng.permutation(date_targets)
            shuffled_targets.append(shuffled)
        
        shuffled_target = np.concatenate(shuffled_targets)
        
        # Compute null IC
        perm_valid_mask = np.isfinite(signal) & np.isfinite(shuffled_target)
        if perm_valid_mask.sum() < 10:
            continue
        
        null_ic, _ = spearmanr(signal[perm_valid_mask], shuffled_target[perm_valid_mask])
        null_ics.append(null_ic)
    
    null_ics = np.array(null_ics)
    
    # Two-tailed p-value
    p_value = (np.abs(null_ics) >= np.abs(observed_ic)).mean()
    
    return {
        'observed_ic': observed_ic,
        'p_value': p_value,
        'null_mean': null_ics.mean(),
        'null_std': null_ics.std(),
        'n_permutations': len(null_ics),
    }
```

### Acceptance Criteria
- Permutation test shuffles target **per-date** (not globally)
- Uses seeded RNG for reproducibility
- Reports two-tailed p-value
- Warns if p > 0.05

---

## Files to Change

1. **`scripts/genetic_alpha_evolution_v3.py`**
   - Add regime IC breakdown (reuse definitions)
   - Add net-of-cost analysis (import VNTransactionCostModel)
   - Add fixed permutation test
   - Use VNTradingCalendar for embargo logic

2. **`scripts/phase35_data_loader.py`** (if embargo logic lives here)
   - Import VNTradingCalendar
   - Replace manual embargo with calendar-aware logic

3. **`tests/test_genetic_alpha_evolution_v3_gate6.py`** (new)
   - Test regime IC computation
   - Test turnover computation
   - Test VN calendar integration
   - Test permutation test (per-date shuffling)

---

## Testing Strategy

### Unit Tests

```python
# tests/test_genetic_alpha_evolution_v3_gate6.py

def test_regime_ic_computes_per_regime():
    """Test regime IC with known synthetic data."""
    # TODO: Synthetic regimes with known IC

def test_turnover_computes_position_change():
    """Test turnover with known signal flips."""
    # TODO: Signal with 50% turnover

def test_vn_calendar_excludes_holidays():
    """Test VNTradingCalendar integration."""
    from omega.data.calendar import VNTradingCalendar
    import pandas as pd
    
    # Tet 2025: Jan 29 - Feb 3 should be non-trading
    tet_dates = pd.date_range('2025-01-29', '2025-02-03')
    for dt in tet_dates:
        assert not VNTradingCalendar.is_trading_day(dt)

def test_permutation_test_per_date_shuffling():
    """Test permutation uses per-date shuffling."""
    # TODO: Synthetic data with known cross-sectional structure
```

---

## Success Metrics

**Minimum acceptance** (validation mechanics):
- ✅ Regime IC computed for all regimes
- ✅ Turnover + cost drag computed using VNTransactionCostModel
- ✅ VN calendar loaded from config/vn_holidays.json
- ✅ Permutation test uses per-date shuffling + seeded RNG

**Report-only** (informational):
- Regime IC values logged with rationale
- Net-of-cost estimates logged
- Permutation p-value logged

**Red flags to reject**:
- Any regime IC < -0.01
- Permutation p-value > 0.05 (not statistically significant)
- Implementation crashes or hangs

---

## SOD Execution Plan

### L2 Implementation (OpenCode)

**Role**: role 16 (machine-learning-engineer)  
**Scope**: Implement Phase 7a-d per revised plan  
**Files**: `scripts/genetic_alpha_evolution_v3.py`, tests  
**Requirements**:
- Import and reuse existing modules (no reimplementation)
- Per-date permutation shuffling
- Repo-relative paths only

### L3 Audit (Codex)

**Role**: role 23 (performance-tester) or role 21 (code-reviewer)  
**Checks**:
- Verify reuse of calendar.py, vn_transaction_cost_model.py
- Verify per-date permutation logic
- Verify no forbidden path reliance
- Run enforcer: `python scripts/sod_gate_enforcer.py`

---

## Implementation Checklist

- [ ] Implement regime IC breakdown with clarified definitions
- [ ] Implement cost analysis using VNTransactionCostModel
- [ ] Implement calendar integration using VNTradingCalendar
- [ ] Implement fixed permutation test (per-date, seeded)
- [ ] Add unit tests for all functions
- [ ] Update main script to log Phase 7a-d metrics
- [ ] Verify no regressions in Phases 1-6
- [ ] Pass SoD enforcer validation

---

## Next Steps

1. ✅ **Revise plan**: Done (this document)
2. **L2 Dispatch**: Open Gate 6 in phase_gates.json, dispatch OpenCode
3. **L3 Audit**: Dispatch Codex for independent review
4. **SoD Validation**: Run `python scripts/sod_gate_enforcer.py`
5. **Commit & Push**: Merge to branch after [APPROVED]
