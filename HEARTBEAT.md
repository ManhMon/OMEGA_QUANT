# HEARTBEAT.md — OMEGA_QUANT
**Version:** 2.5-lite

## Current status
- Phase 1: approved
- Phase 3.1: approved
- Phase 3.4: approved
- Phase 7: approved
- Phase 19: approved
- Phase 20: approved
- Phase 21: approved
- Phase 22: approved

## Key facts
- Production baseline: stable
- PIT safety: enforced
- Architecture/migration still needs evidence-based cleanup
- Use `.ly_state/session/` for live project state

## Current focus
- Canonical path decisions by evidence, not assumption
- Prefer `src/omega/...` unless imports/tests prove active package exceptions
- Archive uncertain duplicates; do not delete blind
- Always keep L3 audit evidence before gate approval

## Next-step rule
- Read repo state, `.ly_state/session/*`, and memory before major cleanup or gating.
