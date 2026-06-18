---
type: project
created: 2026-05-25
updated: 2026-05-25
---

# Project Conventions

## Git Workflow
- Always create a new dedicated branch for major code changes.
- Branch name format should follow: `feature/[task-slug]` or `fix/[bug-slug]`.

## OMEGA_QUANT Constitution (SOD & AG Kit Rules)
- **Strict SOD Tiers**: Ly (L1 Orchestration/Gate-Only, Role 1-5), OpenCode (L2 Implementation/Testing, Role 6-16), Codex (L3 READ-ONLY Audit, Role 17-25). Never self-approve or write code in L1/L3.
- **Vietnamese Language Rule**: Always communicate with the user in Vietnamese.
- **Zero-Timer Policy**: Absolutely DO NOT use `schedule`, `cron`, or background sleep/timers. Rely exclusively on Reactive Wakeup (the system resumes execution automatically when tasks finish).
- **Agent Selection Checklist**: Before responding, analyze the request, select the best agent, and announce:
  ```markdown
  🤖 **Applying knowledge of `@[agent-name]`...**
  ```

