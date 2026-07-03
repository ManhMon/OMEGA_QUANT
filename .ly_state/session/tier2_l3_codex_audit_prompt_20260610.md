⚠️ **LEGACY DOCUMENT - DO NOT USE** ⚠️

This file is preserved for historical context only. It represents the pre-2.0 SOD audit template before strict role resolution and dynamic templating were enforced.

**Superseded by**: `.ly_state/session/sop_codex_l3_audit_call.md` (Version 2.0, 2026-06-11)

**Issues with this legacy template**:
- Hard-coded role IDs/names instead of dynamic frontmatter extraction
- Missing pre-dispatch role resolution requirements
- No REPO_ROOT or Set-Location guards
- No scoped gate update enforcement
- Missing audit evidence checklist
- No session ID validation

**For current L3 audits, use**: `sop_codex_l3_audit_call.md` with strict dynamic template

---

# LEGACY AUDIT PROMPT (2026-06-10)

ROLE: Code Reviewer (Role 21) — Codex L3 Audit
PLATFORM: Codex (L3)
GATE: TIER2_PIPELINE_CONSOLIDATION_20260610
SOD: Writer (L4 direct) ≠ Auditor (Role 21). No self-approval.

## INPUT FILES (READ ALL FIRST)
1. src/omega/quant/pipeline/__init__.py
2. src/omega/quant/pipeline/overlays/__init__.py
3. src/omega/quant/pipeline/overlays/base.py
4. src/omega/quant/pipeline/overlays/smart_money.py
5. src/omega/quant/pipeline/overlays/sentiment.py
6. src/omega/quant/pipeline/overlays/contagion.py
7. src/omega/quant/pipeline/overlays/tcost.py
8. src/omega/quant/pipeline/overlays/circuit_breaker.py
9. src/omega/quant/pipeline/overlays/tail_control.py
10. src/omega/quant/pipeline/overlays/adaptive_sizing.py
11. src/omega/quant/pipeline/overlays/black_litterman.py
12. src/omega/quant/pipeline/overlays/continuous_learning.py
13. src/omega/quant/pipeline/overlays/drift.py
14. src/omega/quant/pipeline/overlays/regime.py
15. src/omega/quant/pipeline/overlays/thompson_sampling.py
16. src/omega/quant/pipeline/overlays/weight_smoothing.py
17. src/omega/quant/pipeline_v2.py (refactored: 648→~370 lines)
18. scripts/run_backtest.py (new unified CLI)

## AUDIT CHECKS
A. **Import Resolution**: All 14 overlay imports resolve via omega.quant.pipeline.overlays. No circular imports.
B. **PIT Safety**: No look-ahead bias introduced. T-1 lag maintained in all overlay apply() methods.
C. **Code Quality**: PEP 8 compliance, type hints present, docstrings on public classes.
D. **Backward Compatibility**: HMMRegimeOverlay and RegimeAwareWFOverlay aliases preserve original parameter signatures (bear_scale/bull_scale/sideways_scale vs bear_exposure/bull_exposure/sideways_exposure).
E. **Test Verification**: Run `pytest tests/ -q`, verify 349 passed, 0 failed.
F. **SOD Compliance**: L2 implementer (L4 SOD direct) ≠ L3 auditor (Role 21). No self-approval.

## VERDICT FORMAT
Write audit report to: .ly_state/session/audit_reports/role21_tier2_consolidation_20260610.md

| Field | Value |
|-------|-------|
| Role | Code Reviewer (Role 21) |
| Verdict | [APPROVED] or [NEEDS_FIX] |
| PIT Safety | PASS or FAIL |
| Role Compliance | PASS or FAIL |
| Tests | N passed, N failed |
| Findings | List of P0/P1/P2 issues |

## GATE UPDATE
Update .ly_state/session/phase_gates.json:
- Set final_verdict to "[APPROVED]" or "[NEEDS_FIX]"
- Set l3_session_id to unique ID
- Set status to "APPROVED" or "NEEDS_FIX"
