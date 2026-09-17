# IT Systems Audit Report
**Role**: IT Systems Auditor (Role 25)
**Date**: 2026-06-27T07:45:14.0417797+07:00
**Submission**: `TC_GATE_TUNING_20260627`
**Tier 2 Engineer**: `14 data-scientist`
**L2 Session**: `l2_role14_tc_gate_tuning_20260627`
**L3 Session**: `l3_role25_tc_gate_tuning_20260627`

## Repo-Local Skill Source Evidence
Files read from authoritative repo-local paths:
- `.agents/agent/it-systems-auditor.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/architecture/SKILL.md`
- `.agents/skills/server-management/SKILL.md`
- `.agents/skills/deployment-procedures/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`

Forbidden path scan:
- `.gemini\antigravity-ide\scratch\ag-kit`: not used as source
- `.openclaw\skills`: not used as source
- `C:\Users\GHC\.agents`: not used as source
- `.codex\memories`: not used as source

## Audit Checks
- [x] Writer/auditor separation verified: `l2_role_id=14 != l3_role_id=25`
- [x] L2 report lists repo-local skill source evidence
- [x] L2 report includes forbidden path scan
- [x] Scope compliance verified: current diff is limited to `build_pipeline_config` only
- [x] Required config keys present in `build_pipeline_config`
- [x] Python verification command passed
- [x] PIT safety preserved: config-only change, no data-access or chronology logic modified
- [x] SOD boundary preserved: L2 implemented, L3 audited only

## Verification Evidence
Scoped diff:
```text
git diff --unified=0 -- scripts/backtest_hybrid_regime.py

@@ -579,0 +580,4 @@ def build_pipeline_config(capital: float, hmm_reentry_threshold: float = 0.6) ->
+        "expected_alpha_scale": 2.0,
+        "expected_alpha_lookback": 60,
+        "dynamic_tc_gate_multiplier": 4.0,
+        "no_trade_band": 0.025,
```

Python verification run:
```powershell
python -c "from scripts.backtest_hybrid_regime import build_pipeline_config; c=build_pipeline_config(2e9); assert c['expected_alpha_scale']==2.0; assert c['expected_alpha_lookback']==60; assert c['dynamic_tc_gate_multiplier']==4.0; assert c['no_trade_band']==0.025; print('PASS')"
```

Result:
```text
Validation successful: All files present and accounted for in .ly_state/
PASS
INFO:omega.quant.alpha.promoted:Successfully imported alpha primitives for promoted alphas
omega.quant.alpha.discovery is deprecated; import from individual submodules instead.
The ``declarative_base()`` function is now available as sqlalchemy.orm.declarative_base(). (deprecated since: 2.0) (Background on SQLAlchemy 2.0 at: https://sqlalche.me/e/b8d9)
```

## Issues Found
None.

## PIT Safety Assessment
Current diff adds four config literals inside `build_pipeline_config` only. No date filters, fold boundaries, feature windows, or execution chronology changed. PIT-safe.

## SOD Boundary Assessment
- L2 report is implementation-only; no self-approval.
- L3 modified only `.ly_state/session/audit_reports/role25_tc_gate_tuning_20260627.md` and `.ly_state/session/phase_gates.json`.
- Writer/auditor separation holds.

## Verdict
[APPROVED]
