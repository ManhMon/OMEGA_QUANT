---
name: elite-karpathy
description: Enforces Karpathy coding principles, simplicity, surgical edits, vectorization, and compliance trails.
when_to_use: "Apply during coding, architectural design, and codebase auditing. Essential for all Tier 2 developer and Tier 3 auditor roles."
allowed-tools: Read, Task
version: 1.0
priority: HIGH
---

# Elite Karpathy Coding and Auditing Principles

This skill defines the core software quality standards for the OMEGA_QUANT system, heavily inspired by the coding philosophy of Andrej Karpathy: simplicity, surgical precision, and direct alignment with system constraints.

---

## 🧘 Simplicity & Clarity

### The Golden Rule:
*Code must be simple, transparent, and easy to read. Avoid over-engineering, unnecessary abstractions, and redundant packages.*

### Key Guidelines:
- **No Over-Engineering**: Prefer simple, explicit functions over complex class hierarchies.
- **Readable Logic**: Write code that self-documents. Keep control flow linear and minimize nested loops.
- **Minimal Dependencies**: Do not import packages if a standard library function can easily do the job.

---

## 🎯 Surgical Modifications

### The Golden Rule:
*Do not make sweeping refactorings when a small, targeted change is sufficient. Keep diffs minimal and clean.*

### Key Guidelines:
- **Surgical Edits**: Target exactly the lines of code that need fixing. Never rewrite entire files for a single bug fix.
- **Maintain Comments**: Preserve unrelated comments and docstrings.
- **Git Hygiene**: Commits should be granular and describe exactly one change.

---

## 📊 Vectorization Standards

### The Golden Rule:
*Avoid raw Python loops (for/while) when processing numerical data. Always use NumPy, Pandas, or PyTorch vectorized operations.*

### Key Guidelines:
- **Vectorized Math**: Multi-dimensional operations must be performed using array slices, matrix multiplication, and element-wise functions.
- **Pandas `.apply()` vs Vectorization**: Use vectorized series operations instead of `.apply()` or `.iterrows()` whenever possible.
- **Performance Profiling**: Verify that data transformations do not cause performance bottlenecks or CPU-bound loops.

---

## 🛡️ Compliance & Audit Trails

### The Golden Rule:
*Every change must leave an auditable, transparent trail of justification, tests, and compliance validation.*

### Key Guidelines:
- **Assumption Documentation**: Clearly docstring any mathematical assumptions, constants, or formulas.
- **PIT Safety**: Ensure no look-ahead data leakage in feature engineering (T-1 Lag).
- **Audit Logging**: Any production change must be linked to a Codex (L3) audit report with a verdict.

---

## 🏦 OMEGA Quant-Specific Requirements

### Point-in-Time (PIT) Safety
*CRITICAL: All data access must respect temporal boundaries to prevent look-ahead bias.*

**Requirements:**
- **T-1 Lag Rule**: Features for time T must use ONLY data available at T-1 or earlier
- **No Future Data**: Never access data from future timestamps in backtests
- **Explicit Date Filtering**: Always use `.loc[df.index <= current_date]` patterns
- **Audit Trail**: Document PIT compliance in function docstrings

**Example (CORRECT):**
```python
def compute_features(df, as_of_date):
    """Compute features for as_of_date using ONLY T-1 data.
    
    PIT Compliance: Uses data.loc[data.index < as_of_date] to ensure
    no look-ahead bias. Audited: 2026-06-11 by Codex L3.
    """
    historical_data = df.loc[df.index < as_of_date]
    return historical_data.rolling(20).mean()
```

**Example (WRONG - Look-ahead bias):**
```python
def compute_features(df, as_of_date):
    # VIOLATION: Uses all data including future
    return df.rolling(20).mean().loc[as_of_date]
```

### Vectorization for Performance
*Quant code processes millions of data points - vectorization is mandatory.*

**Requirements:**
- **No Python Loops**: Use NumPy/Pandas vectorized operations
- **Batch Operations**: Process entire DataFrames/arrays at once
- **Memory Efficiency**: Use `.values` or `.to_numpy()` for large computations
- **Profile Critical Paths**: Verify <100ms execution for feature computation

**Example (CORRECT):**
```python
# Vectorized - processes entire DataFrame at once
returns = (prices.pct_change() * 100).fillna(0)
signals = (returns > threshold).astype(int)
```

**Example (WRONG - Slow loop):**
```python
# VIOLATION: Row-by-row processing
returns = []
for i in range(len(prices)):
    if i > 0:
        ret = (prices[i] / prices[i-1] - 1) * 100
        returns.append(ret)
```

### Audit Trail Integration
*Every code change must be traceable to L3 audit verdict.*

**Requirements:**
- **Docstring Attribution**: Include audit date and L3 session in function docs
- **Commit Messages**: Reference L3 audit report path
- **Phase Gates**: Record l3_session_id, l3_session_key, audit_report_path
- **SOD Compliance**: Follow omega-sod segregation rules

**Example Docstring:**
```python
def calculate_sharpe_ratio(returns, risk_free_rate=0.02):
    """Calculate annualized Sharpe ratio.
    
    Args:
        returns: Daily return series (PIT-compliant)
        risk_free_rate: Annual risk-free rate (default 2%)
    
    Returns:
        float: Annualized Sharpe ratio
    
    PIT Safety: Verified - uses only historical returns
    Vectorization: Verified - uses NumPy operations
    Audit: L3 Session 20260611-001, [APPROVED]
    SOP: SOP_BACKTEST Section 3.2
    """
    excess_returns = returns - (risk_free_rate / 252)
    return np.sqrt(252) * excess_returns.mean() / excess_returns.std()
```

---

## 🎓 Code Review Checklist

### For L2 Developers (Self-Review Before L3 Submission)
- [ ] No Python loops for numerical operations
- [ ] PIT safety verified (T-1 lag enforced)
- [ ] All functions have docstrings with assumptions
- [ ] Tests written and passing
- [ ] No hardcoded magic numbers
- [ ] Surgical edits only (minimal diff)
- [ ] Commit message references SOP

### For L3 Auditors (Codex Review)
- [ ] Code follows Karpathy simplicity principles
- [ ] Vectorization used where applicable
- [ ] PIT compliance verified (no look-ahead)
- [ ] Audit trail complete (docstrings, commits)
- [ ] Tests cover edge cases
- [ ] Performance acceptable (<100ms critical paths)
- [ ] SOP adherence confirmed
- [ ] Verdict: [APPROVED] or [NEEDS_FIX]

---

## 🔗 Integration with OMEGA SOD

This skill supports the OMEGA segregation of duties framework:

**L2 (OpenCode) Usage:**
- Apply these principles when writing code
- Self-review against checklist before L3 submission
- Document PIT safety and vectorization in code

**L3 (Codex) Usage:**
- Audit code against these principles
- Issue [APPROVED] or [NEEDS_FIX] verdict
- Reference specific violations in audit report

**L1 (Ly) Usage:**
- Verify both L2 and L3 followed these principles
- Make final approval decision
- Escalate pattern violations

---

## 📚 Reference SOPs

- **SOP_PIT_SAFETY**: Detailed PIT compliance rules
- **SOP_BACKTEST**: Performance validation standards
- **SOP_AC**: Audit cycle workflow
- **omega-sod**: L1/L2/L3 segregation framework

---

## Version History

- v1.1 (2026-06-11): Added OMEGA quant requirements, PIT safety, vectorization, audit trail
- v1.0 (2026-06-10): Initial Karpathy principles
