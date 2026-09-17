"""Update HYBRID_REGIME_COST_REDUCTION_FIX2_20260621 gate to APPROVED status."""
import json
from pathlib import Path

REPO = Path(r'C:\Users\GHC\repos\OMEGA_QUANT')
GATES_FILE = REPO / '.ly_state' / 'session' / 'phase_gates.json'

raw = GATES_FILE.read_bytes()
gates = json.loads(raw.decode('utf-8-sig'))

gates['HYBRID_REGIME_COST_REDUCTION_FIX2_20260621'] = {
    'l2_session_id': 'l2_role9_hybrid_regime_cost_reduction_fix4_20260621',
    'l2_completed': True,
    'l2_role_id': 9,
    'l2_role_name': 'backend-engineer',
    'l3_session_id': 'l3_role21_hybrid_regime_cost_reduction_fix4_20260621',
    'l3_session_key': 'role21_hybrid_regime_cost_reduction_fix4_20260621',
    'l3_role_id': 21,
    'l3_role_name': 'code-reviewer',
    'audit_report_path': '.ly_state/session/audit_reports/role21_hybrid_regime_cost_reduction_fix4_20260621.md',
    'final_verdict': '[APPROVED]',
    'sod_boundary_checked': True,
    'writer_auditor_separated': True,
    'repo_local_skill_sources': [
        '.agents/agent/code-reviewer.md',
        '.agents/skills/code-review-checklist/SKILL.md',
        '.agents/skills/clean-code/SKILL.md',
        '.agents/skills/testing-patterns/SKILL.md',
        '.agents/skills/audit-cycle/SKILL.md',
        '.agents/skills/omega-sod/SKILL.md'
    ],
    'forbidden_path_scan': 'PASS',
    'recovery_note': 'L3 audit completed 2026-06-21. APPROVED: sparse-date PIT safety gap fill verified, all 59 tests passed.'
}

output = json.dumps(gates, indent=2, ensure_ascii=False, sort_keys=False)
GATES_FILE.write_text(output, encoding='utf-8', newline='\n')
print(f'Updated gate: HYBRID_REGIME_COST_REDUCTION_FIX2_20260621 to [APPROVED]')
print(f'Total gates: {len(gates)}')
