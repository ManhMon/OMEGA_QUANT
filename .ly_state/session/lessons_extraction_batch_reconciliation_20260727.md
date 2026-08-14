# Lessons Extraction Hard-Gate Evidence

- Gate: `lessons_extraction_hard_gate_20260726`
- Evidence timestamp: `2026-07-27`
- Source evidence: `.ly_state/session/audit_reports/` current repo-local audit reports, including `role21_legacy_reconciliation_enforcer_20260727.md`; extraction scope was the existing audit-report corpus.
- Exact command: `python scripts/extract_lessons.py`
- Exit status: `0`
- Extractor result: `Successfully extracted 0 new lessons to C:\\Users\\GHC\\repos\\OMEGA_QUANT\\.agents\\knowledge\\lessons.jsonl`
- Exact count persisted: `0`
- Deduplication outcome: no new lesson records persisted; extractor output does not report a separate deduplication count. This is recorded as `0 new lessons`, not `1 persisted`.
- Lesson store: `.agents/knowledge/lessons.jsonl`
- Operational note: extractor emitted repeated external LLM HTTP `404` warnings, but completed with exit status `0`.
- No manual override.
