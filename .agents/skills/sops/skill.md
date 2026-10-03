---
name: sops
description: Standard Operating Procedures (SOPs) index for OMEGA_QUANT (SOP_AC, SOP_BACKTEST, SOP_PIT_SAFETY, SOP_FIX_0_RETURN, SOP_APSE_INTEGRATION).
when_to_use: "Reference when performing audit cycles, running backtests, verifying PIT safety, debugging zero returns, or integrating external biological/genomic data."
allowed-tools: Read, Task
version: 1.0
priority: HIGH
---

# Standard Operating Procedures (SOPs) — OMEGA_QUANT

This skill houses the central index and execution guidelines for all Standard Operating Procedures (SOPs) within the OMEGA_QUANT system.

---

## 📋 SOP Directory

| SOP ID | Name | Core Objective |
|--------|------|----------------|
| **SOP_AC** | [Audit Cycle](SOP_AC.md) | Systematic code review workflow and L1-L3 validation lifecycle. |
| **SOP_BACKTEST** | [Backtest Validation](SOP_BACKTEST.md) | Ensures institutional-grade historical backtesting and performance metrics. |
| **SOP_PIT_SAFETY** | [Point-In-Time Safety](SOP_PIT_SAFETY.md) | Enforces T-1 data lag to completely eliminate look-ahead data leakage. |
| **SOP_FIX_0_RETURN** | [Fix 0% Return Diagnostics](SOP_FIX_0_RETURN.md) | Diagnostic checklist for resolving zero-return/missing-trade pipeline issues. |
| **SOP_APSE_INTEGRATION**| [APSE Integration](SOP_APSE_INTEGRATION.md) | Rules for integrating AlphaGenome and biological variant metadata. |

---

## 🛡️ Usage and Adherence

### Mandatory Checkpoints:
1. **Prior to code submission (L2)**: Must adhere to **SOP_AC** and self-test.
2. **During feature engineering**: Must check **SOP_PIT_SAFETY** to ensure historical date logic does not query future data.
3. **During model evaluation**: Must run validation pipelines governed by **SOP_BACKTEST**.
4. **On pipeline failures (0% returns)**: Run the diagnostics checklist in **SOP_FIX_0_RETURN**.
5. **When integrating external data**: Follow **SOP_APSE_INTEGRATION** protocols.

---

## 📖 SOP Details

### SOP_AC: Audit Cycle

**Purpose:** Systematic code review workflow with L1-L3 validation lifecycle.

**Key Steps:**
1. L2 (OpenCode) implements code changes
2. L2 runs self-review checklist (elite-karpathy principles)
3. L2 submits to L3 (Codex) for audit
4. L3 reviews code and issues verdict: [APPROVED] or [NEEDS_FIX]
5. If [NEEDS_FIX]: L2 fixes issues and resubmits to L3
6. If [APPROVED]: L1 (Ly) authorizes deployment

**Audit Trail Requirements:**
- l3_session_id: Unique audit session identifier
- l3_session_key: Session key for traceability
- audit_report_path: Path to markdown audit report
- final_verdict: [APPROVED] or [NEEDS_FIX]

**SOD Enforcement:**
- L1: Orchestration and final approval only
- L2: Implementation and testing only
- L3: READ-ONLY audit, no code modifications

---

### SOP_PIT_SAFETY: Point-In-Time Safety

**Purpose:** Enforce T-1 data lag to eliminate look-ahead bias.

**Critical Rule:** Features for time T must use ONLY data available at T-1 or earlier.

**Verification Checklist:**
- [ ] All date filters use `<` not `<=` for current date
- [ ] No `.shift(-1)` or future-referencing operations
- [ ] Rolling windows respect historical boundaries
- [ ] Backtest splits use `train_end < test_start`
- [ ] No data leakage in cross-validation folds

**Common Violations:**
```python
# WRONG: Look-ahead bias
features = df.rolling(20).mean().loc[current_date]

# CORRECT: T-1 lag
historical = df.loc[df.index < current_date]
features = historical.rolling(20).mean().iloc[-1]
```

**Audit Requirement:**
Every function that accesses temporal data must have PIT compliance documented in docstring and verified by L3.

---

### SOP_BACKTEST: Backtest Validation

**Purpose:** Ensure institutional-grade historical backtesting and performance metrics.

**Required Metrics:**
- Annualized Return
- Annualized Volatility
- Sharpe Ratio (>1.0 target)
- Maximum Drawdown (<20% target)
- Win Rate
- Profit Factor
- Calmar Ratio

**Validation Requirements:**
- [ ] Walk-forward validation (expanding window)
- [ ] Out-of-sample test set (minimum 20% of data)
- [ ] Transaction costs modeled (slippage + commission)
- [ ] Position sizing constraints enforced
- [ ] Realistic execution assumptions (no market orders at close price)
- [ ] PIT compliance verified (SOP_PIT_SAFETY)

**Reporting Standard:**
```python
backtest_results = {
    'annual_return': 0.15,  # 15%
    'annual_volatility': 0.12,  # 12%
    'sharpe_ratio': 1.25,
    'max_drawdown': -0.08,  # -8%
    'win_rate': 0.58,
    'profit_factor': 1.8,
    'num_trades': 250,
    'start_date': '2020-01-01',
    'end_date': '2025-12-31',
    'pit_compliant': True,
    'l3_audit_session': '20260611-002',
    'verdict': '[APPROVED]'
}
```

---

### SOP_FIX_0_RETURN: Fix 0% Return Diagnostics

**Purpose:** Diagnostic checklist for resolving zero-return/missing-trade pipeline issues.

**Common Root Causes:**
1. **Data Issues:**
   - Missing price data
   - Stale or duplicate timestamps
   - Currency/timezone mismatches
   
2. **Signal Issues:**
   - Signals not generating (all zeros)
   - Signal threshold too restrictive
   - Feature computation errors
   
3. **Execution Issues:**
   - Position sizing returns zero shares
   - Order fills failing silently
   - Slippage model rejecting all trades

**Diagnostic Steps:**
```python
# Step 1: Verify data loaded
assert not prices.empty, "Price data is empty"
assert not prices.isna().all().all(), "All prices are NaN"

# Step 2: Verify signals generated
print(f"Signal range: {signals.min()} to {signals.max()}")
print(f"Non-zero signals: {(signals != 0).sum()}")

# Step 3: Verify position sizing
print(f"Position range: {positions.min()} to {positions.max()}")
print(f"Non-zero positions: {(positions != 0).sum()}")

# Step 4: Verify returns computed
print(f"Return stats: mean={returns.mean():.4f}, std={returns.std():.4f}")
print(f"Non-zero returns: {(returns != 0).sum()}")
```

**Escalation:**
If diagnostics don't reveal root cause, escalate to L1 (Ly) with full diagnostic log.

---

### SOP_APSE_INTEGRATION: APSE Integration

**Purpose:** Rules for integrating AlphaGenome and biological variant metadata.

**Data Sources:**
- AlphaGenome: Proprietary genomic signals
- Public variant databases (dbSNP, ClinVar)
- Phenotype associations (GWAS catalogs)

**Integration Requirements:**
- [ ] Variant IDs normalized to rsID format
- [ ] Allele frequencies validated against reference populations
- [ ] Effect sizes and p-values preserved with metadata
- [ ] PIT compliance: Use only publicly available data at backtest date
- [ ] Data lineage documented (source + date + version)

**Quality Checks:**
```python
def validate_apse_data(variant_df):
    """Validate APSE integration data quality.
    
    Returns: (is_valid: bool, issues: list)
    """
    issues = []
    
    # Check required columns
    required = ['rsid', 'allele_freq', 'effect_size', 'p_value', 'source_date']
    missing = set(required) - set(variant_df.columns)
    if missing:
        issues.append(f"Missing columns: {missing}")
    
    # Check data types
    if variant_df['p_value'].max() > 1.0:
        issues.append("p_value > 1.0 detected")
    
    # Check PIT compliance
    if 'source_date' in variant_df.columns:
        future_dates = variant_df['source_date'] > pd.Timestamp.now()
        if future_dates.any():
            issues.append(f"Future source dates detected: {future_dates.sum()}")
    
    return len(issues) == 0, issues
```

**L3 Audit Focus:**
- Data provenance documented
- PIT compliance verified
- Quality checks passing
- Integration code follows vectorization standards

---

## 🔄 SOP Workflow Integration

### How SOPs Work Together:

```
┌─────────────────────────────────────────────────────────┐
│ Development Phase                                        │
│ - L2 implements code following elite-karpathy          │
│ - Applies SOP_PIT_SAFETY for temporal data             │
│ - Uses SOP_APSE_INTEGRATION for external data          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ Self-Review Phase                                        │
│ - L2 runs SOP_AC self-review checklist                 │
│ - Verifies PIT compliance                               │
│ - Runs diagnostic checks (SOP_FIX_0_RETURN)            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ L3 Audit Phase                                          │
│ - Codex (L3) audits against all applicable SOPs        │
│ - Issues verdict: [APPROVED] or [NEEDS_FIX]            │
│ - Records audit trail with phase_gates                  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│ Validation Phase                                         │
│ - Run SOP_BACKTEST validation                           │
│ - Verify metrics meet institutional standards           │
│ - L1 (Ly) makes final approval decision                │
└─────────────────────────────────────────────────────────┘
```

---

## 📋 Cross-Reference Matrix

| Task | Primary SOP | Supporting SOPs |
|------|------------|-----------------|
| Implement new feature | SOP_AC | SOP_PIT_SAFETY, elite-karpathy |
| Add external data source | SOP_APSE_INTEGRATION | SOP_PIT_SAFETY, SOP_AC |
| Run backtest | SOP_BACKTEST | SOP_PIT_SAFETY |
| Debug zero returns | SOP_FIX_0_RETURN | SOP_BACKTEST |
| Code review (L3) | SOP_AC | All SOPs, omega-sod |

---

## 🎯 Compliance Score

Each code submission is scored against SOP adherence:

```python
def calculate_sop_compliance_score(submission):
    """Calculate SOP compliance score (0-100).
    
    Returns: {
        'total_score': float,
        'sop_scores': {
            'SOP_AC': float,
            'SOP_PIT_SAFETY': float,
            'SOP_BACKTEST': float,
            ...
        },
        'verdict': '[APPROVED]' or '[NEEDS_FIX]'
    }
    """
    # Score >= 90: [APPROVED]
    # Score < 90: [NEEDS_FIX]
```

**Scoring Criteria:**
- SOP_AC: 30 points (audit trail complete)
- SOP_PIT_SAFETY: 30 points (no look-ahead bias)
- SOP_BACKTEST: 20 points (metrics meet standards)
- Code Quality: 20 points (elite-karpathy compliance)

**Minimum Passing Score:** 90/100 for [APPROVED] verdict

---

## Version History

- v1.1 (2026-06-11): Added detailed SOP sections, workflow integration, compliance scoring
- v1.0 (2026-06-10): Initial SOP index
