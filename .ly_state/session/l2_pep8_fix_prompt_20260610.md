ROLE: Backend Engineer (Role 9) — OpenCode L2 Implementation
TASK: Fix P1-3 PEP 8 compliance issues from L3 audit
GATE: TIER2_PIPELINE_CONSOLIDATION_20260610 (currently NEEDS_FIX)

## CONTEXT
L3 Codex audit (role21-tier2-consolidation-audit-20260610T141949+0700) returned [NEEDS_FIX] with 4 P1 findings:
- P1-1: PIT T-1 lag (regime/drift overlays) — FIXED by L4 SOD (shift(1) added)
- P1-2: Unicode arrow crash in run_backtest.py — FIXED by L4 SOD (→ replaced with ->)
- P1-3: PEP 8 compliance (163 pycodestyle violations) — **NEEDS FIX**
- P1-4: Test evidence reproduction — PENDING (pytest shows 349 passed after P1-1/P1-2 fixes)

## INPUT FILES
1. Audit report: .ly_state/session/audit_reports/role21_tier2_consolidation_20260610.md
2. src/omega/quant/pipeline/overlays/ (14 modules)
3. src/omega/quant/pipeline_v2.py
4. scripts/run_backtest.py

## REQUIREMENTS
1. Fix all pycodestyle violations in overlay files, pipeline_v2.py, and run_backtest.py
2. Run: `pycodestyle --max-line-length=120` on all affected files
3. Zero violations required (pass strict PEP 8)
4. Common issues: trailing whitespace, line length >120, imports not at top, missing docstrings
5. Do NOT modify any business logic — only formatting/style fixes
6. Verify with: `python -m pytest tests/ -q` (must still pass 349 tests)

## OUTPUT
1. Write fix report to: .ly_state/session/l2_pep8_fix_tier2_20260610.md
2. Include: files modified, violations fixed, pycodestyle result (0 violations), pytest result (349 passed)
3. Do NOT commit/push, do NOT modify tests, surgical formatting fixes only

## SOD COMPLIANCE
- L2 implementer (Role 9) will fix PEP 8 issues
- L3 auditor (Role 21) will re-audit after L2 completion
- No self-approval: L2 reports to L4 SOD for verification
