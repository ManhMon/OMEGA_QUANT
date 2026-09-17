# L3 Clarification Memo

**Role**: code-reviewer (Role 21)
**Date**: 2026-06-21
**Gate**: HYBRID_REGIME_DYNAMIC_BRAKE_20260621
**Type**: Clarification-only advisory pass
**Prior Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/agent/backend-engineer.md`
- `.ly_state/session/audit_reports/role21_hybrid_regime_dynamic_brake_20260621.md`
- `.ly_state/session/l2_role9_hybrid_regime_dynamic_brake_20260621.md`
- `src/omega/quant/pipeline/overlays/drawdown_control.py`
- `src/omega/quant/pipeline/overlays/risk_sizing.py`
- `tests/phase35/test_hybrid_regime_dynamic_brake.py`

Forbidden-path scan: forbidden paths were treated as non-authoritative only. No role or skill source was loaded from `.gemini/antigravity-ide/scratch/ag-kit`, `.openclaw/skills`, `C:\Users\GHC\.agents`, or `.codex/memories`.

## Concise Recommendation

Use remediation A: allow legacy re-entry when `state["gmm_p_bull"]` is missing for the re-entry date. Keep the GMM re-entry filter active only when a date-keyed GMM probability is actually present. Do not treat missing GMM state as `0.0` bearish evidence.

Remediate under the same gate with a new L2 fix pass and a clean staged set. No new FIX gate is required unless L1 intentionally wants a separate tracking gate for expanded scope.

## Explicit Answers

1. **Missing `state["gmm_p_bull"]`: A, yes.** Lowest-risk and most backward-compatible remediation is to allow legacy re-entry when GMM state is missing. Current code sets `p_bull = gmm_p_bull.get(dt_str_re, 0.0)` in `drawdown_control.py`, so missing data is interpreted as bearish evidence and extends cooldown. A preserves legacy behavior for pipelines without upstream GMM state while retaining GMM gating when valid probabilities exist. B is acceptable but disables the feature by default. C is not recommended because fail-closed behavior is the regression already observed.

2. **Same gate remediation: yes.** This can remain `HYBRID_REGIME_DYNAMIC_BRAKE_20260621` with a new L2 fix session/report and a new L3 re-audit. The audit-cycle contract says `[NEEDS_FIX]` returns work to L2, then L3 re-audits after fixes. Open a new FIX gate only if L1 expands scope beyond this gate or wants separate release accounting.

3. **Minimal clean staged set:**

- `src/omega/quant/pipeline/overlays/drawdown_control.py` - missing-GMM fallback fix only.
- `tests/phase35/test_hybrid_regime_dynamic_brake.py` - regression test proving missing `gmm_p_bull` does not cause permanent cash/cooldown under default or explicitly enabled GMM filter.
- `.ly_state/session/l2_role9_hybrid_regime_dynamic_brake_fix_20260621.md` - corrected L2 evidence/report for the fix pass.
- During L3 re-audit only: `.ly_state/session/audit_reports/role21_hybrid_regime_dynamic_brake_fix_20260621.md` and the single `HYBRID_REGIME_DYNAMIC_BRAKE_20260621` entry in `.ly_state/session/phase_gates.json`.

Exclude unrelated staged files such as prior full-backtest reports, unrelated `phase_gates.json` changes before L3, `scripts/backtest_hybrid_regime.py`, `src/omega/quant/walk_forward/risk_sizing_overlay.py`, and any source files not needed for this narrow fix.

4. **Source-contract skills: yes, exact declared backend-engineer skills must appear.** Corrected L2 evidence must list these repo-local files as authoritative reads:

- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`

Extra context-relevant skills may be mentioned only if explicitly marked non-authoritative context, not as dispatch-loaded authoritative skills. The L2 report should make the separation unambiguous, e.g. `Non-authoritative context only: python-patterns, quant-research`. Authoritative dispatch evidence should contain exactly the backend-engineer role file plus its six declared skill files.

## Notes For Re-Audit

- Add an assertion stronger than `blocked >= 0`; it should fail on the current bug.
- Suggested behavior check: with missing `gmm_p_bull`, after cooldown expires and no HMM/BOCPD block applies, weights resume nonzero and `drawdown_control.stopped_out` clears.
- If GMM probabilities are present and below confidence, cooldown extension should still be tested and preserved.
- If GMM probabilities are present and above confidence, full re-entry should still be tested and preserved.

## Boundary

No production source code was modified. `phase_gates.json` was not updated. This memo is advisory only and does not replace the required L2 fix pass plus L3 re-audit verdict.
