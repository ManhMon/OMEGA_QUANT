# L2 Implementation Report: Risk-Adjusted Portfolio Guard CLI Wiring Fix

| Field | Value |
|---|---|
| **Gate** | `RISK_ADJUSTED_PORTFOLIO_GUARD_FIX1_20260614` |
| **Role** | 16 — Machine Learning Engineer (Tier 2) |
| **Date** | 2026-06-14 |
| **Status** | Implementation complete, pending Tier 3 audit |
| **Session ID** | `l2_role16_risk_adjusted_portfolio_guard_fix1_20260614` |

---

## 1. Problem Statement

L2 previously implemented `portfolio_guard_enabled` (default `False`) and `portfolio_guard_tolerance` (default `0.005`) in `Phase35WalkForwardEngine.__init__()` as part of GATE `RISK_ADJUSTED_PORTFOLIO_GUARD_20260614`. However, `scripts/run_phase35_backtest.py` did **not** expose or pass these parameters. Consequently, any post-audit A/B run using `--risk-adjusted-alpha-selection` would never exercise the portfolio guard — the guard remained silently disabled regardless of user intent.

## 2. Scope

| File | Change Type |
|---|---|
| `scripts/run_phase35_backtest.py` | Added CLI flags, derived `portfolio_guard_enabled`, wired to engine, added config output fields, added logging, added fold serialization for guard evidence |
| `tests/phase35/test_portfolio_guard_cli_wiring.py` | New test file: 18 tests verifying CLI flag registration, derivation logic, engine wiring, config output, logging, and baseline preservation |
| `src/omega/quant/alpha/phase35.py` | No changes needed (engine already accepts and uses `portfolio_guard_enabled` / `portfolio_guard_tolerance`) |

## 3. Changes Detail

### 3.1 CLI Flags Added

| Flag | Type | Default | Description |
|---|---|---|---|
| `--disable-risk-adjusted-portfolio-guard` | `store_true` | `False` | Explicitly opt out of portfolio guard when `--risk-adjusted-alpha-selection` is active |
| `--risk-adjusted-portfolio-guard-tolerance` | `float` | `0.005` | Maximum allowed IC underperformance vs baseline before guard triggers fallback |

### 3.2 Auto-Derivation Logic

```python
args.portfolio_guard_enabled = (
    args.risk_adjusted_alpha_selection
    and not args.disable_risk_adjusted_portfolio_guard
)
args.portfolio_guard_tolerance = args.risk_adjusted_portfolio_guard_tolerance
```

**Behavior matrix:**

| `--risk-adjusted-alpha-selection` | `--disable-risk-adjusted-portfolio-guard` | Result: `portfolio_guard_enabled` |
|---|---|---|
| Not set | Not set | `False` (baseline preserved) |
| Not set | Set | `False` (baseline preserved) |
| Set | Not set | `True` (guard auto-enabled) |
| Set | Set | `False` (explicit opt-out) |

### 3.3 Engine Wiring

Added to `Phase35WalkForwardEngine()` constructor call:
```python
portfolio_guard_enabled=args.portfolio_guard_enabled,
portfolio_guard_tolerance=args.portfolio_guard_tolerance,
```

### 3.4 Config Output Fields

Added to results JSON `config` dict:
- `"portfolio_guard_enabled"`: `args.portfolio_guard_enabled`
- `"portfolio_guard_tolerance"`: `args.portfolio_guard_tolerance`

### 3.5 Fold Serialization

Added `portfolio_guard_evidence` persistence in `serialize_fold_details()`.

### 3.6 Logging

```
[GATE] Portfolio Guard Enabled: {True|False}
[GATE] Portfolio Guard Tolerance: {value}
```

## 4. Test Results

### 4.1 New Tests: `tests/phase35/test_portfolio_guard_cli_wiring.py`

- **18 tests** — all **PASSED**
- Classes:
  - `TestPortfolioGuardEngineParams` (6 tests): engine signature defaults, instance storage
  - `TestPortfolioGuardCLIWiring` (11 tests): flag registration, derivation logic, engine pass-through, config output, logging, baseline preservation
  - `TestPortfolioGuardSerializeFoldDetails` (1 test): fold evidence serialization

### 4.2 Existing Tests: `tests/test_risk_adjusted_alpha_score.py`

- **120 tests** — all **PASSED** (no regressions)

### 4.3 Smoke Test

Command:
```
python scripts/run_backtest.py phase35 --quick-mode --risk-adjusted-alpha-selection \
  --risk-adjusted-preset ic_first_guarded --drawdown-control --enable-evolved \
  --multi-horizon-blend --p10-gate-mode relaxed --p10-gate-allow-fallback-candidates \
  --enable-data-cleaning
```

**Result:** Completed successfully. Key evidence:
- `[GATE] Portfolio Guard Enabled: True` — guard auto-enabled
- `[GATE] Portfolio Guard Tolerance: 0.005` — tolerance wired
- `[PortfolioGuard][H1] Fallback to baseline: ...` — guard actively exercised per horizon
- `[PortfolioGuard] Fallback to baseline: ...` — guard exercised in single-horizon fallback path
- Zero IC values expected (1-symbol smoke test; cross-sectional metrics collapse)

### 4.4 Opt-Out Verification

Command with `--disable-risk-adjusted-portfolio-guard`:
- `[GATE] Portfolio Guard Enabled: False` — confirmed disabled

### 4.5 Baseline Preservation

Command without `--risk-adjusted-alpha-selection`:
- `[GATE] Risk-Adjusted Alpha Selection: False`
- `[GATE] Portfolio Guard Enabled: False` — baseline unchanged

## 5. PIT Safety

No PIT-safety changes. All guard logic uses only embargoed train/validation data (enforced upstream in `phase35.py`). The CLI wiring fix only connects existing parameters; it does not alter data flow.

## 6. Backward Compatibility

- Default behavior when `--risk-adjusted-alpha-selection` is not set: **unchanged** (`portfolio_guard_enabled=False`)
- Existing CLI flags and behavior: **unchanged**
- Engine constructor defaults: **unchanged** (`portfolio_guard_enabled=False`, `portfolio_guard_tolerance=0.005`)

## 7. Tier 3 Audit Submission

Submitted to:
- Code Reviewer (role 21): CLI wiring quality, flag naming, backward compatibility
- QA Engineer (role 17): test coverage, smoke test results, baseline preservation
