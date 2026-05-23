# TEAM AGENT REDESIGN SPEC (OMEGA_QUANT ALIGNED)

**Version**: 2.3
**Status**: R8 (Backend Engineer Role 9 - Audit Findings Fix)
**Last Updated**: 2026-05-10

## 1. PLATFORM MAPPING & TIERS
- **L1 Supervisor (Orchestrator):** Ly
- **L2 Supervisor (Build/Code):** OpenCode
- **L3 Supervisor (CLI Audit/Review):** Codex

## 2. CORE RULES
- **Strict Isolation:** 1 Agent = 1 Role = 1 Task.
- **Segregation of Duties (SOD):** Implementation session MUST terminate before Audit session spawns.
- **Context Blindness:** Agents see only necessary task inputs.
- **No Self-Approval:** Maker cannot be Checker.
- **Minimal Context:** Pass only required diffs/specs, no full histories.
- **State Persistence:** All workflow states save to `.ly_state/`.

## 3. WORKFLOW (SOD ENFORCED)
1. **Initiate:** Ly (L1) creates task, persists state.
2. **Implement:** Ly spawns OpenCode (L2 Impl).
3. **Terminate:** OpenCode finishes code, session TERMINATES completely.
4. **Audit:** Ly spawns Codex (L3 Audit).
5. **Evaluate:** Codex runs CLI checks, reviews code, generates Verdict.
6. **Gate:** Codex terminates. Ly Gate reads Verdict. Pass -> merge. Fail -> loop to step 2.

## 4. 25 ROLES MAPPING

### L1 (Ly) - Orchestrator & Management
1. Project Manager
2. Product Owner
3. Scrum Master
4. Release Manager
5. Delivery Manager

### L2 (OpenCode) - Build, Code, Design
6. System Architect
7. Tech Lead
8. Frontend Engineer
9. Backend Engineer
10. Database Admin
11. DevOps Engineer
12. Cloud Infra Engineer
13. UI/UX Integrator
14. Data Scientist
15. Data Engineer
16. Machine Learning Eng

### L3 (Codex) - Audit, Review, Security
17. QA Engineer
18. SDET (Software Development Engineer in Test)
19. Security Auditor
20. Compliance Officer
21. Code Reviewer
22. Penetration Tester
23. Performance Tester
24. UAT Validator
25. IT Systems Auditor
