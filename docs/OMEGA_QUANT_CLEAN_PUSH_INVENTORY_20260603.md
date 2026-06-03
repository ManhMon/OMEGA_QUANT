# OMEGA_QUANT Clean Push Inventory

Date: 2026-06-03
Status: Approved direction — inventory only
Goal: prepare clean GitHub push before workspace cleanup and fresh clone

## 1. Keep in active project / eligible for GitHub push

Tracked project roots currently present in `origin/main`:

- `.ly_state/`
- `apps/`
- `config/`
- `data/`
- `docs/`
- `memory/`
- `models/`
- `packages/`
- `scripts/`
- `spec/`
- `src/`
- `tests/`

Tracked/important project files at repo root to keep:

- `AGENTS.md`
- `SOUL.md`
- `TOOLS.md`
- `USER.md`
- `IDENTITY.md`
- `HEARTBEAT.md`
- `pytest.ini`
- `conftest.py`
- `.code-review-graph.yml`
- `.gitattributes`
- `.codexignore`

Needs manual keep/review before push:

- `OMEGA_QUANT/` (currently contains docs + `.ly_state`; likely duplicate/transition folder)
- `archive/` (contains historical material; not automatically safe to push)
- `cache/`
- `pytest_temp/`
- `.token-savior-cache.json`
- `check_pid.ps1`
- `_check_uaa.py`

## 2. Archive out of active workspace before final cleanup

Confirmed by user: move removed items into `archive/`, do not delete.

Current active workspace items that are tooling/runtime/junk and should be archived out of active project scope:

- `.openclaw/`
- `skills/`
- `.pytest_cache/`
- `__pycache__/`

Expected but not currently present at workspace root when inventoried:

- `.code-review-graph/`
- `.antigravitycli/`
- `pi_skill/`

Recommended archive destination:

```text
archive/workspace_cleanup/tooling/
```

Recommended exact targets:

- `archive/workspace_cleanup/tooling/.openclaw/`
- `archive/workspace_cleanup/tooling/skills/`
- `archive/workspace_cleanup/tooling/.pytest_cache/`
- `archive/workspace_cleanup/tooling/__pycache__/`

If later found:

- `archive/workspace_cleanup/tooling/.code-review-graph/`
- `archive/workspace_cleanup/tooling/.antigravitycli/`
- `archive/workspace_cleanup/tooling/pi_skill/`

## 3. Ambiguous roots requiring explicit decision before final push

These exist locally but are not in the confirmed tracked-root set from `origin/main`:

- `OMEGA_QUANT/`
- `archive/`
- `cache/`
- `pytest_temp/`

Recommended default:

- keep them local for now
- do not include new large archive/cache trees in clean push unless explicitly intended

## 4. Draft `.gitignore` items for future cleanup

These are recommended ignore entries so runtime/tooling clutter does not keep re-polluting repo root:

```gitignore
# Python caches
__pycache__/
*.py[cod]
.pytest_cache/

# OpenClaw / tool runtime
.openclaw/
.code-review-graph/
.antigravitycli/
skills/
pi_skill/
cache/
pytest_temp/
.token-savior-cache.json

# OS/editor noise
.DS_Store
Thumbs.db
```

Note:
- `.ly_state/` intentionally NOT ignored per user choice
- `data/` intentionally NOT ignored per user choice
- `models/` intentionally NOT ignored per user choice

## 5. Recommended next execution order

1. Review ambiguous roots (`OMEGA_QUANT/`, `archive/`, `cache/`, `pytest_temp/`)
2. Create `.gitignore`
3. Move tooling/runtime roots into `archive/workspace_cleanup/tooling/`
4. Re-run `git status`
5. Decide whether `OMEGA_QUANT/` stays, merges, or archives
6. Push cleaned project state to GitHub
7. Clone fresh repo into dedicated project directory outside OpenClaw runtime workspace

## 6. Fresh clone target recommendation

Preferred new repo location:

```text
C:\Users\GHC\repos\OMEGA_QUANT\
```

Preferred runtime/tooling location remains:

```text
C:\Users\GHC\.openclaw\
```
