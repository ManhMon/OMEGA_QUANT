# TOOLS.md — OMEGA_QUANT Tooling
**Version:** 2.5-lite
**Purpose:** minimal execution rules, paths, and defaults.

## Default execution
- **L2 implementation:** `opencode run "<task>"`
- **L3 audit:** `codex exec --dangerously-bypass-approvals-and-sandbox "[L3-Audit:*] <task>"`
- Use background `exec` for long tasks.
- Prefer PTY for agent CLIs.

## When to use what
- **Quick shell / python / git:** `exec`
- **Precise file changes:** `edit`
- **Whole-file rewrite:** `write`
- **Browser/web automation:** `browser`
- **Repo architecture / blast radius:** code-review-graph tools
- **Long-running CLI:** `exec(background:true)` + `process`

## Codex / OpenCode rules
- Use **stdin prompt file** for multiline Codex prompts.
- Do not let implementation and audit happen in same session.
- Use focused tests for touched scope before asking L3.

## Important paths
### Workspace
- `C:\Users\GHC\.openclaw\workspace`

### Repo
- `C:\Users\GHC\repos\OMEGA_QUANT`

### Python
- `C:\Users\GHC\AppData\Local\Programs\Python\Python314\python.exe`

### Memory / state
- Workspace memory: `C:\Users\GHC\.openclaw\workspace\MEMORY.md`
- Repo state: `C:\Users\GHC\repos\OMEGA_QUANT\.ly_state\session\`

## Repo guidance
- Treat `src/omega/...` as canonical by default unless evidence shows otherwise.
- `packages/...` may hold active exceptions; verify imports/tests before cleanup.
- Archive uncertain duplicates; do not delete blind.

## CRG usage
- On Windows, prefer repo path with forward slashes for CRG tools:
  - `C:/Users/GHC/repos/OMEGA_QUANT`
- If graph exists but flows/communities missing, run postprocess.

## Verification defaults
- Run smallest relevant test set first.
- For audit loops, keep evidence:
  - changed files
  - test commands/results
  - Codex verdict

## Messaging / style
- Be brief, exact, and action-first.
- If user says `Ok` after options, continue with proposed next step.
