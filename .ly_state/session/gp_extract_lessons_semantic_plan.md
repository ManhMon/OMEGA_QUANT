# Semantic Extraction for Lessons Learned

This plan upgrades `scripts/extract_lessons.py` to correctly extract lessons learned from L3 Codex audit reports using semantic understanding (or robust fallback parsing) instead of rigid keyword matching.

## User Review Required
> [!IMPORTANT]
> The current script uses `re.search(r'## Findings\s*\n(.*?)(\n##|$)', content)` which fails when L3 generates headings like `## Required Fix`. Do you want L2 to implement a full LLM-based extraction (via API) or just a robust parser that captures all possible Markdown headings?

## Open Questions
> [!NOTE]
> If we use an LLM API for extraction, which provider/model should we default to? (e.g., Gemini, OpenAI, or the existing `mock` provider in `llm_symbolic_synthesizer.py`)

## Proposed Changes

### scripts/extract_lessons.py

#### [MODIFY] extract_lessons.py
- **Semantic Parsing Logic**: Replace the rigid `## Findings` regex with a semantic chunking method. 
- **Implementation Strategy**:
  1. Extract all text sections from the markdown report based on dynamic `## ` headings.
  2. Map sections semantically to `root_cause` and `fix_pattern` (e.g., matching "Required Fix", "Action Items", "Findings", "Issues" to the relevant fields).
  3. *(Optional if LLM available)*: Pass the raw Markdown to a lightweight LLM prompt to summarize the `symptom`, `root_cause`, and `fix_pattern`.
- **Validation**: Ensure that it successfully extracts lessons from `[NEEDS_FIX]` verdicts regardless of the specific heading names chosen by L3 Codex.

## Verification Plan

### Automated Tests
- Create a mock audit report with irregular headings (e.g., `## Required Action` instead of `## Findings`) and run `python scripts/extract_lessons.py` to ensure the lesson is successfully extracted.
- Check the output of `python scripts/get_relevant_lessons.py 16 "test"` to verify the new lesson appears in the knowledge base.
