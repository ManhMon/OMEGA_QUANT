# L2 Report Template

Choose exactly one variant from `ANTI_DRIP_MODE`. Replace every placeholder. Never edit contract, sidecar, or prompt artifacts.

## Baseline Variant

```markdown
# L2 Implementation Report

- **Role**: <ROLE_ID> <ROLE_NAME> - OpenCode L2 Implementation
- **Gate**: `<GATE_NAME>`
- **Session**: `<L2_SESSION_ID>`
- **Date**: `<YYYY-MM-DD>`
- **Anti-Drip Mode**: `baseline`
- **Anti-Drip Contract**: `<CONTRACT_PATH>`
- **Anti-Drip Contract SHA-256**: `<CONTRACT_SHA256>`

## Summary

[Brief description of what was implemented]

## Repo-Local Files Read

- `.agents/agent/<ROLE_NAME>.md`
- `.agents/skills/<SKILL_NAME>/SKILL.md`

## Changes Made

- `<REPO_RELATIVE_PATH>`: [what changed]

## Verification

- [test command run and result]

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: <STATUS>; non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: <STATUS>; non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: <STATUS>; non-authoritative scan evidence only; no reliance.
- `.codex\memories`: <STATUS>; non-authoritative scan evidence only; no reliance.
```

## Remediation Variant

````markdown
# L2 Implementation Report

- **Role**: <ROLE_ID> <ROLE_NAME> - OpenCode L2 Implementation
- **Gate**: `<GATE_NAME>`
- **Session**: `<L2_SESSION_ID>`
- **Date**: `<YYYY-MM-DD>`
- **Anti-Drip Mode**: `remediation`
- **Anti-Drip Contract**: `<CONTRACT_PATH>`
- **Anti-Drip Contract SHA-256**: `<CONTRACT_SHA256>`

## Summary

[Brief description of what was implemented]

## Repo-Local Files Read

- `.agents/agent/<ROLE_NAME>.md`
- `.agents/skills/<SKILL_NAME>/SKILL.md`

## Changes Made

- `<REPO_RELATIVE_PATH>`: [what changed]

## Verification

- [test command run and result]

## Root-Cause Architectural Sweep

```json
{
  "schema_version": "anti-drip-sweep/v1",
  "session_id": "<L2_SESSION_ID>",
  "gate_name": "<GATE_NAME>",
  "mode": "remediation",
  "contract_path": "<CONTRACT_PATH>",
  "contract_sha256": "<CONTRACT_SHA256>",
  "source_audit_path": "<SOURCE_AUDIT_PATH>",
  "source_audit_sha256": "<SOURCE_AUDIT_SHA256>",
  "finding_sweeps": [{
    "finding_id": "<FINDING_ID>",
    "root_cause": "<ROOT_CAUSE>",
    "probe_strings": ["<PROBE_STRING>"],
    "searches": [{
      "search_regex": "<SEARCH_REGEX>",
      "scanned_paths": ["<REPO_RELATIVE_PATH>"],
      "total_matches": <TOTAL_MATCHES>,
      "changed_matches": <CHANGED_MATCHES>,
      "non_actionable_matches": <NON_ACTIONABLE_MATCHES>,
      "non_actionable_justifications": <NON_ACTIONABLE_JUSTIFICATIONS>,
      "unresolved_matches": 0
    }],
    "test_node_ids": ["<PYTEST_NODE_ID>"],
    "fault_injection_test_node_ids": ["<PYTEST_NODE_ID>"],
    "unresolved_matches": 0
  }],
  "pytest_node_ids": ["<PYTEST_NODE_ID>"],
  "fault_injection_test_node_ids": ["<PYTEST_NODE_ID>"],
  "unresolved_matches": 0
}
```

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit`: <STATUS>; non-authoritative scan evidence only; no reliance.
- `.openclaw\skills`: <STATUS>; non-authoritative scan evidence only; no reliance.
- `C:\Users\GHC\.agents`: <STATUS>; non-authoritative scan evidence only; no reliance.
- `.codex\memories`: <STATUS>; non-authoritative scan evidence only; no reliance.
````

## Completion Rules

1. Baseline: remove the entire Root-Cause Architectural Sweep.
2. Remediation: one finding sweep per contract finding, same order and exact probes.
3. Every `unresolved_matches` is integer `0`; search accounting balances exactly.
4. Top-level test arrays equal ordered unions of finding arrays; fault nodes are subsets.
5. Every forbidden status is exactly `absent` or `not read`.
6. Run `python scripts/validate_l2_report.py <L2_SESSION_ID> <ROLE_ID> <ROLE_NAME>`; proceed only on exit `0`.
