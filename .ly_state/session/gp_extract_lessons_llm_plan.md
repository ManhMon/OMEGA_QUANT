# LLM-Based Semantic Extraction for Lessons Learned

This plan upgrades `scripts/extract_lessons.py` to use a true LLM-based semantic extraction approach, replacing the recently added robust heading regex parser. The LLM will read the entire L3 audit report and intelligently extract the core symptom, root cause, and fix pattern regardless of the report's markdown structure.

## Proposed Changes

### scripts/extract_lessons.py

#### [MODIFY] extract_lessons.py
- **Remove Regex Heading Parser**: Strip out the rigid and robust regex heading parsers (`HEADING_RE`, `ROOT_CAUSE_HEADINGS`, `FIX_PATTERN_HEADINGS`).
- **Implement LLM Client**:
  - Add a lightweight API client (using `requests` module, similar to how `OpenAICompatibleProvider` is implemented in `llm_symbolic_synthesizer.py`).
  - Read API configuration (like `OPENAI_API_KEY` or `GEMINI_API_KEY`) from environment variables.
  - If no API key is present, fallback gracefully to returning a generic extracted structure or the raw markdown content to prevent pipeline failure.
- **LLM Prompt Design**:
  - Send the raw L3 Audit Report markdown to the LLM.
  - Instruct the LLM to output a strict JSON structure containing:
    - `symptom`: What went wrong or what was flagged.
    - `root_cause`: The underlying technical reason for the issue.
    - `fix_pattern`: The exact instruction on how to prevent or fix it next time.
- **Integration**: Parse the LLM's JSON response and store the result in `lessons.jsonl` and ChromaDB just as before.

## Verification Plan

### Automated Tests
- Update `tests/test_extract_lessons.py` to mock the `requests.post` call to the LLM API, ensuring that the script correctly processes the JSON response and handles API failures gracefully.
- Run `pytest tests/test_extract_lessons.py` to ensure all tests pass.
