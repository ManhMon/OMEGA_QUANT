# L2 Implementation Report: Hướng 4 Drawdown Re-Entry

**GATE**: `STAGE6_3_DRAWDOWN_RE_ENTRY_20260616`
**Role**: 14 data-scientist (OpenCode L2 Implementation)
**Date**: 2026-06-16
**Status**: IMPLEMENTED — Tests Passing (17/17)

---

## 1. Role & Skill Source Contract

| Item | Value |
|------|-------|
| **Agent file** | `.agents/agent/data-scientist.md` |
| **Role ID** | 14 |
| **Tier** | 2 (implementation-only, test required, no self-approval) |
| **Platform** | OpenCode |
| **SOD boundary** | implementation-only, test required, no self-approval, submit to Tier3 |

### Skills loaded (repo-local, authoritative)

| Skill | Path |
|-------|------|
| python-patterns | `.agents/skills/python-patterns/SKILL.md` |
| clean-code | `.agents/skills/clean-code/SKILL.md` |
| testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| systematic-debugging | (declared, not loaded — not needed) |
| performance-profiling | (declared, not loaded — not needed) |
| quant-research | `.agents/skills/quant-research/SKILL.md` |
| vietnam-market-data | (declared, not loaded — not needed) |
| backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` |

### Forbidden path scan

| Path | Scanned? | Result |
|------|----------|--------|
### Forbidden Path Scan Result
- Zero reliance on any forbidden path as authoritative source.
- Forbidden path scan: PASS.
- No forbidden path strings appear as authoritative markers.

All files read exclusively from `C:\Users\GHC\repos\OMEGA_QUANT\` (REPO_ROOT).

---

## 2. Scope & Files Modified

| File | Action | Description |
|------|--------|-------------|
| `src/omega/quant/alpha/phase35.py` | Modified | Added gate constant, constructor params, `_apply_drawdown_control` method, evidence field |
| `scripts/run_phase35_backtest.py` | Modified | Added 3 CLI args, engine wiring, evidence serialization, logging |
| `tests/phase35/test_drawdown_control_re_entry.py` | Created | 17 unit tests covering all paths |

---

## 3. Implementation Summary

### 3.1 Gate Constant

```python
DRAWDOWN_RE_ENTRY_GATE_ID = "STAGE6_3_DRAWDOWN_RE_ENTRY_20260616"
```

### 3.2 Constructor Parameters (Phase35WalkForwardEngine)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `drawdown_re_entry_enabled` | `bool` | `False` | Opt-in re-entry after stop-out |
| `drawdown_cooldown_days` | `int` | `5` | Trading days in cash before re-entry |
| `drawdown_hwm_reset` | `bool` | `True` | Reset HWM to NAV on re-entry |

All parameters have type/range validation with `ValueError` on invalid input.

### 3.3 Stage 6.3 Logic (`_apply_drawdown_control`)

State machine with 3 states:

```
NORMAL → (breach) → STOP_OUT → (cooldown expires) → RE_ENTERED → NORMAL
```

**State transitions**:
1. **NORMAL → STOP_OUT**: When `current_dd < -threshold`
   - Records breach event (date, NAV, HWM, DD)
   - If `re_entry_enabled=False`: zeros ALL remaining returns (permanent stop-out, backward compatible)
   - If `cooldown_days=0`: immediate re-entry (no cash days)
   - Otherwise: enters cooldown state
2. **STOP_OUT → RE_ENTERED**: When `cooldown_remaining <= 0`
   - If `hwm_reset=True`: resets HWM to current NAV
   - Records re-entry event
   - Returns to NORMAL state
3. **RE_ENTERED → NORMAL → STOP_OUT**: Can re-trigger on new breach

**PIT Safety**: Walks through daily returns sequentially. Uses ONLY realised test-fold returns (`daily_series`). No future data, no train-period data.

### 3.4 CLI Arguments

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--drawdown-re-entry` | `store_true` | `False` | Enable re-entry |
| `--drawdown-cooldown-days` | `int` | `5` | Cooldown period |
| `--drawdown-no-hwm-reset` | `store_true` | `False` | Disable HWM reset (keep original) |

### 3.5 Evidence Serialization

Per-fold evidence dict persisted in `FoldMetrics.drawdown_re_entry_evidence` and serialized via `serialize_fold_details()` in CLI script.

Evidence structure:
```json
{
  "gate": "STAGE6_3_DRAWDOWN_RE_ENTRY_20260616",
  "enabled": true,
  "re_entry_enabled": true,
  "cooldown_days": 5,
  "hwm_reset": true,
  "threshold": 0.05,
  "stop_out_events": [
    {
      "breach_day_index": 3,
      "breach_date": "2020-01-06",
      "nav_at_breach": 0.955087,
      "hwm_at_breach": 1.061208,
      "drawdown_at_breach": -0.10001,
      "cooldown_days": 5
    }
  ],
  "re_entry_events": [
    {
      "re_entry_day_index": 7,
      "re_entry_date": "2020-01-10",
      "nav_at_re_entry": 0.955087,
      "hwm_after_reset": 0.955087,
      "hwm_reset_applied": true
    }
  ],
  "n_stop_outs": 1,
  "n_re_entries": 1,
  "total_cooldown_days": 3,
  "pit_safe": true
}
```

---

## 4. Test Results

### 4.1 New Tests (17/17 PASS)

```
tests/phase35/test_drawdown_control_re_entry.py — 17 passed
```

| Test Class | Tests | Description |
|------------|-------|-------------|
| `TestDrawdownReEntryConstructor` | 5 | Param validation, defaults, type errors |
| `TestDrawdownReEntryBackwardCompat` | 2 | Permanent stop-out, evidence reports |
| `TestDrawdownReEntryWithCooldown` | 3 | Cooldown timing, re-entry, zero cooldown |
| `TestDrawdownHWMReset` | 3 | HWM reset prevents re-trigger, no-reset re-triggers, evidence records |
| `TestMultipleStopOutCycles` | 1 | Multiple stop-out/re-entry cycles |
| `TestPITSafety` | 1 | Train-fold DD doesn't trigger test stop-out |
| `TestDrawdownControlDisabled` | 1 | No evidence when control disabled |
| `TestEvidenceGateId` | 1 | Gate ID and PIT flag correctness |

### 4.2 Regression Tests (34/34 PASS)

```
tests/phase35/test_stage6_3_drawdown_control.py — 5 passed
tests/phase35/test_drawdown_control_default_on_cli.py — 29 passed
```

**Total: 51/51 tests passing.**

---

## 5. Backward Compatibility

| Scenario | Behavior | Status |
|----------|----------|--------|
| Default (no flags) | `drawdown_re_entry_enabled=False`, permanent stop-out | PRESERVED |
| `--drawdown-control` (deprecated) | No-op, already default-on | PRESERVED |
| `--disable-drawdown-control` | Disables all DD control | PRESERVED |
| `--drawdown-re-entry` (new) | Opt-in stateful re-entry | NEW |

---

## 6. SOD/Tier 3 Submission

This implementation is submitted for Tier 3 audit:
- **Code Reviewer** (role 21): Code quality, reproducibility
- **QA Engineer** (role 17): Model validation, testing review

**Cannot proceed until**: All relevant Tier 3 roles return [APPROVED].

---

## 7. Checklist

- [x] PIT Safety: all decisions use only realised test-fold returns
- [x] Constructor validation: type/range checks on all new params
- [x] Backward compatible: default behavior unchanged
- [x] Evidence persisted: per-fold evidence in FoldMetrics + CLI serialization
- [x] Unit tests: 17 new tests, all passing
- [x] Regression: 34 existing tests still passing
- [x] CLI wired: 3 new args, engine construction, logging
- [x] Gate ID: `STAGE6_3_DRAWDOWN_RE_ENTRY_20260616`
- [x] No forbidden paths accessed
