# SKILL AUTO-LOADER ARCHITECTURE
## V21_QUANT Elite Team - Progressive Disclosure System

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                         SKILL AUTO-LOADER FLOWCHART                                 ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                      ║
║   ┌─────────────────────────────────────────────────────────────────────────────┐    ║
║   │                        1. USER REQUEST                                      │    ║
║   │                                                                              │    ║
║   │   "Implement alpha mới với TDD"                                             │    ║
║   │   "Audit file X"                                                            │    ║
║   │   "Chạy backtest"                                                           │    ║
║   └──────────────────────────────┬──────────────────────────────────────────────┘    ║
║                                  ▼                                                     ║
║   ┌─────────────────────────────────────────────────────────────────────────────┐    ║
║   │                        2. LY SCANS REGISTRY                                 │    ║
║   │                                                                              │    ║
║   │   Read: skills_registry.json                                                 │    ║
║   │   ├── 23 skills loaded                                                      │    ║
║   │   ├── Keywords indexed                                                      │    ║
║   │   └── Target agents mapped                                                  │    ║
║   └──────────────────────────────┬──────────────────────────────────────────────┘    ║
║                                  ▼                                                     ║
║   ┌─────────────────────────────────────────────────────────────────────────────┐    ║
║   │                        3. KEYWORD MATCHING                                 │    ║
║   │                                                                              │    ║
║   │   Input: "implement", "TDD"                                                 │    ║
║   │                                                                              │    ║
║   │   Match Results:                                                             │    ║
║   │   ├── tdd              (keywords: "test", "pytest", "TDD")     → OpenCode   │    ║
║   │   ├── karpathy-coder  (keywords: "implement", "surgical")     → OpenCode   │    ║
║   │   └── coding-agent    (keywords: "code", "build", "feature")  → OpenCode   │    ║
║   └──────────────────────────────┬──────────────────────────────────────────────┘    ║
║                                  ▼                                                     ║
║   ┌─────────────────────────────────────────────────────────────────────────────┐    ║
║   │                        4. SKILL PRIORITIZATION                             │    ║
║   │                                                                              │    ║
║   │   Rule-based selection:                                                      │    ║
║   │   ├── Task type detection: "implement" → CODE task                           │    ║
║   │   ├── Prioritize by specificity: tdd > karpathy-coder > coding-agent        │    ║
║   │   └── Auto-select: tdd (most specific for TDD request)                      │    ║
║   │                                                                              │    ║
║   │   ✅ Selected: tdd/SKILL.md                                                  │    ║
║   └──────────────────────────────┬──────────────────────────────────────────────┘    ║
║                                  ▼                                                     ║
║   ┌─────────────────────────────────────────────────────────────────────────────┐    ║
║   │                        5. SKILL HYDRATION                                   │    ║
║   │                                                                              │    ║
║   │   Load: C:/Users/GHC/.openclaw/skills/tdd/SKILL.md                         │    ║
║   │                                                                              │    ║
║   │   Content injected into:                                                     │    ║
║   │   Get-Content "tdd/SKILL.md" | opencode run "[TASK]"                        │    ║
║   └──────────────────────────────┬──────────────────────────────────────────────┘    ║
║                                  ▼                                                     ║
║   ┌─────────────────────────────────────────────────────────────────────────────┐    ║
║   │                        6. AGENT EXECUTION                                   │    ║
║   │                                                                              │    ║
║   │   OpenCode receives:                                                         │    ║
║   │   ├── TDD workflow context                                                  │    ║
║   │   ├── Skill instructions (red-green-refactor)                               │    ║
║   │   └── Task: "Implement alpha_vn_foreign_flow"                                │    ║
║   │                                                                              │    ║
║   │   OpenCode EXECUTES → Unit tests written first                              │    ║
║   │                                   → Implementation                          │    ║
║   │                                   → Tests pass                               │    ║
║   │                                   → Refactor                                 │    ║
║   └──────────────────────────────┬──────────────────────────────────────────────┘    ║
║                                  ▼                                                     ║
║   ┌─────────────────────────────────────────────────────────────────────────────┐    ║
║   │                        7. RESULT & PERSISTENCE                             │    ║
║   │                                                                              │    ║
║   │   ├── Tests: 38/38 PASSED                                                   │    ║
║   │   ├── Commit: [COMMIT_HASH]                                                 │    ║
║   │   ├── Update: checkpoint.json                                               │    ║
║   │   └── Notify: Ly → Report to user                                           │    ║
║   │                                                                              │    ║
║   └─────────────────────────────────────────────────────────────────────────────┘    ║
║                                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
```

---

## ARCHITECTURE COMPONENTS

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              SKILL ECOSYSTEM                                     │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐     │
│  │                        skills_registry.json                              │     │
│  │  ┌─────────┬───────────────────┬────────────────┬──────────────────┐  │     │
│  │  │    ID   │      PATH          │  TARGET_AGENT  │    KEYWORDS      │  │     │
│  │  ├─────────┼───────────────────┼────────────────┼──────────────────┤  │     │
│  │  │  tdd    │ tdd/SKILL.md      │    OpenCode    │ test, pytest...  │  │     │
│  │  │  qa     │ qa/SKILL.md       │    OpenCode    │ bug, issue...    │  │     │
│  │  │ audit   │ audit-cycle/SKILL  │    Codex       │ /ac, audit...    │  │     │
│  │  │ karpathy│ elite_karpathy/... │    Codex       │ pit safety...    │  │     │
│  │  │ startup │ startup/SKILL.md   │      Ly        │ session, init...│  │     │
│  │  │  team   │ team/SKILL.md     │      Ly        │ /team, delegate │  │     │
│  │  │  ...    │       ...         │      ...       │       ...       │  │     │
│  │  └─────────┴───────────────────┴────────────────┴──────────────────┘  │     │
│  └─────────────────────────────────────────────────────────────────────────┘     │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐     │
│  │                     SKILL DIRECTORIES (20 folders)                       │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │     │
│  │  │   tdd    │ │   qa    │ │  audit   │ │ gstack   │ │ startup  │ ...   │     │
│  │  │  /SKILL  │ │  /SKILL │ │  /SKILL  │ │  /SKILL  │ │  /SKILL  │       │     │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘      │     │
│  └─────────────────────────────────────────────────────────────────────────┘     │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐     │
│  │                          TEAM AGENTS                                     │     │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐              │     │
│  │  │       LY       │  │    OpenCode    │  │     Codex     │              │     │
│  │  │  (Orchestrator)│  │    (Coder)    │  │   (Auditor)  │              │     │
│  │  │  - Delegate    │  │  - Write Code  │  │  - Read Only  │              │     │
│  │  │  - Scan Reg    │  │  - TDD Flow    │  │  - PIT Safety │              │     │
│  │  │  - Route       │  │  - Implement    │  │  - Approve    │              │     │
│  │  └────────────────┘  └────────────────┘  └────────────────┘              │     │
│  └─────────────────────────────────────────────────────────────────────────┘     │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## TASK TYPE → SKILL MAPPING

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                           DECISION TREE                                         │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│                          USER REQUEST                                           │
│                              │                                                  │
│              ┌───────────────┼───────────────┐                                 │
│              ▼               ▼               ▼                                 │
│       ┌──────────┐    ┌──────────┐    ┌──────────┐                            │
│       │  CODE?   │    │  AUDIT?  │    │   ORCH?  │                            │
│       │implement │    │ /ac audit│    │ delegate │                            │
│       │   fix    │    │  review  │    │  route   │                            │
│       │   refactor│   │  check   │    │  setup   │                            │
│       └────┬─────┘    └────┬─────┘    └────┬─────┘                            │
│            │               │               │                                    │
│            ▼               ▼               ▼                                    │
│   ┌────────────────┐ ┌────────────────┐ ┌────────────────┐                       │
│   │ PRIORITY SKILL │ │ PRIORITY SKILL│ │ PRIORITY SKILL│                       │
│   │                │ │               │ │               │                       │
│   │  1. tdd        │ │ 1. karpathy-   │ │ 1. startup    │                       │
│   │  2. karpathy-  │ │    auditor    │ │ 2. team       │                       │
│   │     coder      │ │  2. audit-    │ │ 3. auto-skill │                       │
│   │  3. coding-    │ │    cycle      │ │ 4. delegate-  │                       │
│   │     agent      │ │               │ │    task       │                       │
│   └───────┬────────┘ └───────┬────────┘ └───────┬────────┘                       │
│           │                 │                 │                                 │
│           ▼                 ▼                 ▼                                 │
│   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                           │
│   │  OpenCode    │ │    Codex     │ │      Ly      │                           │
│   │  WRITE MODE  │ │ READ-ONLY    │ │  ORCHESTRATE │                           │
│   └──────────────┘ └──────────────┘ └──────────────┘                           │
│                                                                                 │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## AUTO-LOADER RULES

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                              RULES ENGINE                                       │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  RULE 1: KEYWORD MATCHING                                                        │
│  ─────────────────────────                                                       │
│  IF user_input CONTAINS any keyword IN registry                                  │
│  THEN select matching skills                                                    │
│  ELSE ask user to specify                                                       │
│                                                                                 │
│  RULE 2: SINGLE SKILL AUTO-SELECT                                               │
│  ────────────────────────────────                                               │
│  IF exactly 1 skill matched                                                     │
│  THEN auto-load without prompt                                                  │
│                                                                                 │
│  RULE 3: MULTIPLE SKILLS → PRIORITIZE                                           │
│  ─────────────────────────────────────                                          │
│  IF multiple skills matched                                                     │
│  THEN select by specificity score:                                              │
│    - Exact keyword match: +10 points                                            │
│    - Partial keyword match: +5 points                                           │
│    - Agent match (OpenCode/Codex): +3 points                                    │
│    - Task type match: +2 points                                                 │
│                                                                                 │
│  RULE 3: MULTIPLE SKILLS → PROMPT                                               │
│  ─────────────────────────────────────                                          │
│  IF multiple skills with same score                                             │
│  THEN show selection options to user                                            │
│                                                                                 │
│  RULE 4: NO MATCH → DEFAULT                                                     │
│  ────────────────────────                                                       │
│  IF no skill matched                                                           │
│  THEN use coding-agent (default) or ask user                                    │
│                                                                                 │
│  RULE 5: SILENT EXECUTION                                                       │
│  ────────────────────────                                                       │
│  IF skill auto-selected AND user didn't specify "ask me"                        │
│  THEN execute silently, report ONLY on completion/error                         │
│                                                                                 │
│  RULE 6: SOP /ac MANDATORY                                                      │
│  ──────────────────────────                                                     │
│  BEFORE any code deployment                                                     │
│  MUST run: Codex audit with karpathy-auditor skill                              │
│                                                                                 │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## SKILL → AGENT → ACTION MATRIX

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SKILL MATRIX                                        │
├───────────────┬──────────────┬─────────────────────┬───────────────────────────┤
│    SKILL ID   │ TARGET AGENT │      KEYWORDS       │       RESULT ACTION        │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ tdd           │ OpenCode     │ test, pytest, TDD   │ Write test → Implement →  │
│               │              │                     │ Pass → Refactor            │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ karpathy-     │ OpenCode     │ implement, surgical │ Vectorized code, clear     │
│ coder         │              │                     │ assumptions, robust        │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ coding-agent  │ OpenCode     │ code, build, refactor│ Complex logic, large      │
│               │              │                     │ codebase                  │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ qa            │ OpenCode     │ bug, issue, github  │ Interactive QA → File    │
│               │              │                     │ GitHub issue              │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ karpathy-     │ Codex        │ pit safety, elite   │ Surgical audit, PIT       │
│ auditor       │              │ audit               │ check, no look-ahead      │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ audit-cycle   │ Codex        │ /ac, audit, approve │ Full audit loop with     │
│               │              │                     │ FreeCode workflow         │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ startup       │ Ly           │ session, init       │ Load context, run         │
│               │              │                     │ checklist, show dashboard │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ team          │ Ly           │ /team, delegate     │ Orchestrate sub-agents,   │
│               │              │                     │ progressive disclosure    │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ code-review-  │ Ly           │ crg, minimal context│ Blast radius, hub nodes,   │
│ graph         │              │                     │ token-saving analysis     │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ token-savior  │ Ly           │ token saving, prune │ Emergency context prune,  │
│               │              │                     │ compress logs              │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ gstack        │ OpenCode     │ browser, qa         │ Headless browser for       │
│               │              │                     │ deployment testing         │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ git-guardrails│ OpenCode     │ git safety, hooks   │ Block dangerous git        │
│               │              │                     │ (push, reset-hard)         │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ delegate-task │ Ly           │ openspace, mcp     │ Delegate to OpenSpace      │
│               │              │                     │ autonomous worker          │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ version-      │ Ly           │ version, lessons    │ Update MEMORY.md with      │
│ management    │              │                     │ lessons learned            │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ auto-skill    │ Ly           │ auto, workflow      │ Execute skills based on    │
│               │              │                     │ context triggers          │
├───────────────┼──────────────┼─────────────────────┼───────────────────────────┤
│ request-      │ Ly           │ refactor plan, rfc  │ Create refactor