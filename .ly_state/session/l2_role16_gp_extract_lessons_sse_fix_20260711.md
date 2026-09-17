## Summary

- Gate: `GP_EXTRACT_LESSONS_SSE_FIX`
- Scope: `scripts/extract_lessons.py`
- Result: fixed SSE trailer JSON parsing; truncated LLM audit content to 3000 chars before prompt construction.

## Changes

- Replaced `response.json()` path with explicit parse of `response.text.split("\ndata:")[0].strip()` then `json.loads(...)` to tolerate the 9router `data: [DONE]` trailer.
- Added `content_excerpt = content[:3000]` and used it in the prompt payload to reduce oversized request failures.

## Verification

- Ran: `python -m py_compile scripts/extract_lessons.py`
- Result: success

## Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `scripts/extract_lessons.py`

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` are non-authoritative forbidden paths and were not used as authoritative sources.

## Notes

- No other files changed.
