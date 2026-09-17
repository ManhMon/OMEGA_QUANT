# L2 Implementation Report: Risk-Adjusted Portfolio Guard CLI Wiring Fix (FIX2 — Evidence-Only Revision)

| Field | Value |
|---|---|
| **Gate** | `RISK_ADJUSTED_PORTFOLIO_GUARD_FIX2_20260614` |
| **Prior Gate** | `RISK_ADJUSTED_PORTFOLIO_GUARD_FIX1_20260614` (L3 NEEDS_FIX) |
| **Role** | 16 — Machine Learning Engineer (Tier 2) |
| **Date** | 2026-06-14 |
| **Status** | Evidence-only fix; code and tests unchanged |
| **Session ID** | `l2_role16_risk_adjusted_portfolio_guard_fix2_20260614` |
| **L3 Audit Triggering Fix** | `.ly_state/session/audit_reports/role20_risk_adjusted_portfolio_guard_fix1_20260614.md` |

---

## 0. FIX2 Revision Notes

This report is an **evidence-only revision** of `l2_role16_risk_adjusted_portfolio_guard_fix1_20260614.md`. No production source files, test files, or configuration files were modified. The sole change addresses the L3 blocking finding:

> SOD evidence violation: L2 report does not list exact repo-local role/skill files read and does not include the required forbidden-path scan wording.

### What Changed (FIX1 → FIX2)

| Section | Change |
|---|---|
| **§0 (this section)** | Added revision notes |
| **§8 SOD Evidence** | New section: exact repo-local role and skill files read |
| **§9 Forbidden Path Scan** | New section: same-sentence forbidden path wording |
| **§10 Test Preservation** | New section: re-confirmed test results |
| **§1–§7** | Unchanged from FIX1 (preserved verbatim below) |

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

### 4.3 Combined Test Run (FIX2 re-verification)

Command:
```
python -m pytest tests/phase35/test_portfolio_guard_cli_wiring.py tests/test_risk_adjusted_alpha_score.py -q --tb=no
```

**Result:** **138 passed**, 3 warnings, exit code 0.

### 4.4 Smoke Test

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

### 4.5 Opt-Out Verification

Command with `--disable-risk-adjusted-portfolio-guard`:
- `[GATE] Portfolio Guard Enabled: False` — confirmed disabled

### 4.6 Baseline Preservation

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

---

## 8. SOD Evidence — Repo-Local Sources Read

### 8.1 Agent Contract (REPO_AGENT_ROOT)

| File | Path (repo-local) |
|---|---|
| **Role definition** | `.agents/agent/machine-learning-engineer.md` |

**Frontmatter parsed:**
- `name`: machine-learning-engineer
- `role_id`: 16
- `tier`: 2
- `platform`: OpenCode
- `skills`: [python-patterns, clean-code, testing-patterns, performance-profiling, systematic-debugging, ml-dl-rl, backtesting-pit-safety, vietnam-market-data]
- `sod_boundary`: "implementation-only, test required, no self-approval, submit to Tier3"

### 8.2 Skill Files (REPO_SKILL_ROOT)

All skill files loaded from `.agents/skills/<skill>/SKILL.md`:

| # | Skill | Repo-Local Path |
|---|---|---|
| 1 | python-patterns | `.agents/skills/python-patterns/SKILL.md` |
| 2 | clean-code | `.agents/skills/clean-code/SKILL.md` |
| 3 | testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| 4 | performance-profiling | `.agents/skills/performance-profiling/SKILL.md` |
| 5 | systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` |
| 6 | ml-dl-rl | `.agents/skills/ml-dl-rl/SKILL.md` |
| 7 | backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| 8 | vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` |

**Skill coverage for this change:**

| Skill | Relevance to Portfolio Guard CLI Wiring |
|---|---|
| python-patterns | CLI argument patterns, argparse usage, function signatures |
| clean-code | Naming conventions, guard clauses, SRP in CLI wiring |
| testing-patterns | AAA pattern, mocking strategy, test organization for 18 new tests |
| performance-profiling | N/A for this CLI wiring change (no performance impact) |
| systematic-debugging | Root cause identification of silent guard disable (4-phase process) |
| ml-dl-rl | Model deployment context, walk-forward integration, ensemble gating |
| backtesting-pit-safety | PIT-safe guard logic, embargoed data usage, walk-forward protocol |
| vietnam-market-data | VN market context for backtest smoke runs, exchange-aware validation |

---

## 9. Forbidden Path Scan

`.gemini\antigravity-ide\scratch\ag-kit is non-authoritative and not used as source; .openclaw\skills is non-authoritative and not used as source; C:\Users\GHC\.agents is non-authoritative and not used as source; .codex\memories is non-authoritative and not used as source.`

All sources used for this implementation are exclusively from the repo-local paths:
- `REPO_AGENT_ROOT` = `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent`
- `REPO_SKILL_ROOT` = `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`

No external agent directories, scratch spaces, or non-repo skill directories were consulted.

---

## 10. Test Preservation Confirmation

| Test Suite | Tests | Result |
|---|---|---|
| `tests/phase35/test_portfolio_guard_cli_wiring.py` | 18 | PASSED |
| `tests/test_risk_adjusted_alpha_score.py` | 120 | PASSED |
| **Combined** | **138** | **PASSED** (3 warnings, exit code 0) |

Re-verification command (FIX2):
```
python -m pytest tests/phase35/test_portfolio_guard_cli_wiring.py tests/test_risk_adjusted_alpha_score.py -q --tb=no
```

No production source files or test files were modified in this FIX2 revision.

---

## 11. Implementation Summary

| Aspect | Status |
|---|---|
| CLI flags registered | PASS |
| Auto-derive behavior matrix | PASS |
| Engine wiring | PASS |
| Config output fields | PASS |
| Fold serialization | PASS |
| Logging | PASS |
| 18 new tests | PASS |
| 120 existing tests | PASS (no regressions) |
| Smoke test (guard enabled) | PASS |
| Opt-out test (guard disabled) | PASS |
| Baseline preservation | PASS |
| PIT safety | PASS |
| Backward compatibility | PASS |
| SOD evidence (role + skills read) | PASS (FIX2) |
| Forbidden path scan | PASS (FIX2) |
