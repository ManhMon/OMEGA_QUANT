import pathlib

agent_dir = pathlib.Path('.agents/agent')

tier1_compliance = """## AG Kit Compliance
- Ly agents must execute strictly within the AG Kit framework, using the appropriate orchestration workflows (`/coordinate`, `/orchestrate`, `/plan`, etc.).
- All state changes, decisions, active tasks, locks, and evidence must be logged in `.ly_state/session/` using file-based persistence as defined in the memory system.
- Before final approval and release, Ly agents must ensure that all gates are verified by running `scripts/sod_gate_enforcer.py`.

"""

tier2_compliance = """## AG Kit Compliance
- OpenCode agents must operate strictly within the AG Kit framework, using the appropriate implementation workflows (`/create`, `/enhance`, `/verify`, `/debug`, `/test`, etc.).
- Before completing any task, OpenCode agents must run the master scripts (`checklist.py` and `verify_all.py`) to verify compliance with security, linting, quality, and performance standards.
- All implementation outputs, logs, and verification results must be persisted in `.ly_state/session/` for Tier 3 auditing.

"""

tier3_compliance = """## AG Kit Compliance
- Codex agents must operate strictly within the AG Kit framework, using the appropriate auditing and review workflows.
- Codex agents must generate structured audit reports in markdown under `.ly_state/session/audit_reports/` using the standardized Codex template.
- All audit verdicts, session keys, and verification evidence must be persisted in `.ly_state/session/phase_gates.json` to enable gate verification by `scripts/sod_gate_enforcer.py`.

"""

count = 0
for f in agent_dir.glob('*.md'):
    content = f.read_text(encoding='utf-8')
    
    # Avoid duplicate insertion
    if '## AG Kit Compliance' in content:
        print(f"Skipping {f.name} - already contains compliance section.")
        continue
        
    # Detect tier from YAML frontmatter
    tier = None
    for line in content.splitlines():
        if line.startswith('tier:'):
            tier = line.split(':')[1].strip()
            break
            
    if not tier:
        print(f"Warning: Could not detect tier in {f.name}")
        continue
        
    if tier == '1':
        compliance_text = tier1_compliance
    elif tier == '2':
        compliance_text = tier2_compliance
    elif tier == '3':
        compliance_text = tier3_compliance
    else:
        print(f"Warning: Unknown tier {tier} in {f.name}")
        continue
        
    target = "## Success Metrics"
    if target in content:
        new_content = content.replace(target, compliance_text + target)
        f.write_text(new_content, encoding='utf-8')
        print(f"Successfully updated {f.name}")
        count += 1
    else:
        print(f"Warning: Could not find ## Success Metrics in {f.name}")

print(f"Finished. Updated {count} files.")
