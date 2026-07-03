# L2 Fix Scope: ML Engineer report compliance update for Direction 1

## Role
- Role ID: 16
- Role Name: machine-learning-engineer
- Tier: 2
- Platform: OpenCode
- SOD Boundary: implementation-only, test required, no self-approval, submit to Tier3

## Scope
- .ly_state/session/l2_role16_alphas_opt_20260616.md

## Required Fixes

1. **Mandatory Skills list update**:
   - In `.ly_state/session/l2_role16_alphas_opt_20260616.md`, under the "Repo-Local Files Read" / "Mandatory Skills" section, list all 8 skills declared in `machine-learning-engineer.md`:
     - `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\clean-code\SKILL.md`
     - `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\testing-patterns\SKILL.md`
     - `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\ml-dl-rl\SKILL.md`
     - `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\backtesting-pit-safety\SKILL.md`
     - `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\vietnam-market-data\SKILL.md`
     - `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\python-patterns\SKILL.md`
     - `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\performance-profiling\SKILL.md`
     - `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\systematic-debugging\SKILL.md`

2. **Forbidden Path Scan Wording**:
   - Format the scan row/table so that `C:\Users\GHC\.agents`, `.codex\memories`, `.gemini\antigravity-ide\scratch\ag-kit`, and `.openclaw\skills` are each explicitly marked `non-authoritative` and `not used as source`.

3. **Role spec SHA256 Update**:
   - Update the `Role spec SHA256` value to `418348c40e652b744faaf10b1ca215c39a2a1f877e0514521c67622873dae310` to match the current specs file.

## Verification
- Run: `python scripts/sod_gate_enforcer.py` (ensure no wording or skill mismatches are flagged for Direction 1).

## Output
- Write the updated report directly to `.ly_state/session/l2_role16_alphas_opt_20260616.md`.
