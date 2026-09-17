# Extraction Evidence

**Gate**: `lessons_extraction_hard_gate_20260726`
**Run date**: 2026-07-26
**Extraction timestamp**: `2026-07-26T13:57:58Z`
**Command**: `$env:OMEGA_SKIP_LLM='1'; python scripts/extract_lessons.py`
**Exit status**: `0`
**Source scope**: `.ly_state/session/audit_reports/*20260726*.md`
**Source reports**: `31`
**Source `[NEEDS_FIX]` reports**: `15`
**Non-eligible `[NEEDS_FIX]` reports**: `14`
**Extractor-eligible reports**: `2` (`1` eligible `[NEEDS_FIX]` report)
**Persisted new lessons**: `0`
**Lesson store**: `.agents/knowledge/lessons.jsonl`
**Rows after run**: `143`
**Unique `(gate, role_id)` keys**: `81`
**Pre-existing duplicate rows**: `62`
**Deduplication outcome**: `0` new keys appended; `0` 2026-07-26 lessons persisted.
**Warning**: Existing extractor reported `phase_gates.json` UTF-8 BOM and skipped gate metadata loading.
**Retrieval**: `get_relevant_lessons.py` remains retrieval-only; it cannot substitute for extraction.
