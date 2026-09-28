# Scope Specification: GATE_JEV_DEEP_INTEGRATION_W3_20260928

- **Gate**: `GATE_JEV_DEEP_INTEGRATION_W3_20260928`
- **Packet**: `W3 - Event Forensic Shadow`
- **Owner**: `Role 15 data-engineer` (Co-role: `Role 14 data-scientist`)
- **Independent Auditor**: `Role 20 compliance-officer`
- **Objective**: Implement event forensic shadow integration, including novelty classification, revision/correction chains, corporate-action accounting (avoid duplicate penalties), and counterfactual forensic audit qualification without production hard vetoes.

## Owned Files
1. `src/omega/data/corporate_action.py`
2. `src/omega/data/pipeline/production_pipeline.py`
3. `src/omega/data/production_data_pipeline.py`
4. `src/omega/data/news_aggregator.py`
5. `src/omega/data/micro_llm.py`
6. `src/omega/quant/alpha/forensic_filter.py`
7. `tests/test_data_loader_corporate_action_pit.py`
8. `src/omega/data/loader.py`
9. `tests/test_data_corporate_action_pit.py`
10. `tests/test_jev_event_forensics.py`
11. `tests/test_micro_llm.py`
11. `.ly_state/session/jev_deep_integration_20260926/W3/scope.md`
12. `.ly_state/session/jev_deep_integration_20260926/W3/experiment_manifest.json`
13. `.ly_state/session/jev_deep_integration_20260926/W3/metrics.json`
14. `.ly_state/session/jev_deep_integration_20260926/W3/rollback.md`
15. `.ly_state/session/jev_deep_integration_20260926/W3/matrix_evidence.md`
16. `.ly_state/session/jev_deep_integration_20260926/W3/input_manifest.json`
17. `.ly_state/session/jev_deep_integration_20260926/W3/l2_report.md`

## Status
Remediation rem17 implemented; generation SHA-256 uses bounded reads before legacy replacement; MemoryError and Exception trigger legacy/manifest rollback. Scoped tests: 201 passed, 12 warnings. Pending independent L3 review.
