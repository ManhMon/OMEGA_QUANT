# OMEGA_QUANT Clean Push — Next Steps

## Immediate decisions already locked

- Keep `.ly_state/` in project scope
- Keep `data/` in project scope
- Keep `models/` in project scope
- Move removed tooling/runtime folders into `archive/`, not delete

## Next safe actions

### Step 1 — Add `.gitignore`
Create `.gitignore` to prevent runtime/tooling clutter from reappearing in active project status.

### Step 2 — Archive tooling roots
Move these out of active workspace root into:

`archive/workspace_cleanup/tooling/`

Targets currently present:
- `.openclaw/`
- `skills/`
- `.pytest_cache/`
- `__pycache__/`

### Step 3 — Re-check repo status
Run:
- `git status`
- inspect ambiguous roots (`OMEGA_QUANT/`, `archive/`, `cache/`, `pytest_temp/`)

### Step 4 — Decide treatment of `OMEGA_QUANT/`
Because it is not current GitHub root and appears duplicate/partial, choose one:
- merge into active docs/state
- keep local only
- archive

### Step 5 — Push cleaned repo
After status is acceptable, push current repo state to GitHub.

### Step 6 — Fresh clone into dedicated repo location
Recommended target:

`C:\Users\GHC\repos\OMEGA_QUANT\`

### Step 7 — Stop using OpenClaw workspace as production repo root
Use cloned repo for production work; keep OpenClaw runtime under `C:\Users\GHC\.openclaw\`.

## SOD note
Workspace cleanup / archive move is operational housekeeping.
If any app code changes happen while cleaning, re-enter full L2 -> L3 flow for those code diffs.
