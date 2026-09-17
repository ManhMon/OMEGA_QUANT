# GP v30 Plan Audit

**Role**: Code Reviewer (Role 21, L3 Codex)
**Date**: 2026-07-14
**Verdict**: [NEEDS_FIX]

## Blocking Findings

1. **CRITICAL - ctypes pointer memo collision**: pointer and pointer.contents share one native address. Early pointer registration makes pointee cloning return the pointer clone. Separate wrapper identity from pointee allocation identity; test non-null typed pointers.
2. **CRITICAL - multidimensional memoryview reconstruction invalid**: offset and slicing model one dimension; ND-to-ND memoryview.cast is generally invalid. Rebuild from 1D bytes using exact byte offset and span, or fail closed before slicing.
3. **HIGH - ctypes owner sizing underspecified**: _objects becomes a dictionary; ctypes.sizeof(pointer) is pointer width, not pointee allocation extent. Define ownership and extent rules; test casts, offsets, external pointers, nested _objects, aliases.
4. **HIGH - schema fingerprint incomplete**: hash covers mapping only. Include normalized effective columns, allowlist and schema version, mapping, expected raw or lagged state before no-op.

## Verified Directions

- Shared key and value ledgers, NumPy header proxy, native-address payload deduplication.
- Tuple cycle fail-closed, early mutable and structure memo, bitfield check, private MRO slots.
- Freeze and final writable-memoryview validation across containers, dict keys and values, slots, __dict__, and .obj.
- Stable mergesort, UUID temporary column, deep DataFrame, object, attrs copy, try and finally cleanup.
- Barrier main participation, worker exception queue, BrokenBarrier propagation, abort, join, liveness.
- Future-sentinel controls and segment plus non-decreasing date validation.

## Compliance

- No production or test modifications.
- Repo-local sources read: .agents/agent/code-reviewer.md; .agents/skills/code-review-checklist/SKILL.md; .agents/skills/clean-code/SKILL.md; .agents/skills/testing-patterns/SKILL.md; .agents/skills/audit-cycle/SKILL.md; .agents/skills/omega-sod/SKILL.md.
- Forbidden paths: no authoritative reliance.

**Signature**: Codex L3 Auditor
