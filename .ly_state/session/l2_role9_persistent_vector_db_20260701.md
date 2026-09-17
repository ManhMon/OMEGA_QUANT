# L2 Report - Persistent Vector DB Lessons

## Session
- role_id: 9
- role_name: backend-engineer
- gate: HYBRID_REGIME_SOD_PERSISTENT_VECTOR_DB_20260701
- scope:
  - `scripts/extract_lessons.py`
  - `scripts/get_relevant_lessons.py`

## Repo-Local Files Read
- role:
  - `.agents/agent/backend-engineer.md`
- skills:
  - `.agents/skills/nodejs-best-practices/SKILL.md`
  - `.agents/skills/api-patterns/SKILL.md`
  - `.agents/skills/database-design/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`

## Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit` -> not present
- `.openclaw\skills` -> not present
- `C:\Users\GHC\.agents` -> present, not used, non-authoritative
- `.codex\memories` -> not present

## Changes
- `scripts/extract_lessons.py`
  - replaced ephemeral Chroma client path with persistent client via `PersistentClient(path=str(KNOWLEDGE_DIR / 'chromadb'))`
  - switched lesson collection load/write flow to `get_or_create_collection(...); upsert(...)`
  - persisted current lessons into disk-backed Chroma store during extraction
- `scripts/get_relevant_lessons.py`
  - now requires 2 CLI args: `role_id_or_name`, `task_query`
  - uses `search_similar_lessons(query=task_query, role_id=role_id)`
  - prefers persistent Chroma retrieval, falls back to local TF-IDF
  - prints top 3 similar lessons
- `tests/test_extract_lessons.py`
  - added regression test for persistent Chroma client path + collection usage

## Verification
- `pytest tests/test_extract_lessons.py tests/test_sod_gate_enforcer_startup.py` -> passed (`3 passed`)
- `python scripts/get_relevant_lessons.py 9 "persistent vector db failures query lessons"` -> ran successfully
- `pytest` -> passed (`100%`)

## Notes
- `checklist.py` -> missing at repo root
- `verify_all.py` -> missing at repo root
- worktree had many unrelated untracked files; untouched
