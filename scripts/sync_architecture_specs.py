import os
import re
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
AGENT_DIR = WORKSPACE / ".agents" / "agent"
SKILLS_DIR = WORKSPACE / ".agents" / "skills"
WORKFLOWS_DIR = WORKSPACE / ".agents" / "workflows"
ARCH_FILE = WORKSPACE / ".agents" / "ARCHITECTURE.md"

def parse_frontmatter(file_path):
    """Parse YAML frontmatter from a markdown file."""
    if not file_path.exists():
        return {}
    content = file_path.read_text(encoding='utf-8')
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return {}
    
    yaml_text = match.group(1)
    metadata = {}
    for line in yaml_text.split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.startswith('[') and val.endswith(']'):
                # Simple list parsing
                val = [item.strip().strip('"').strip("'") for item in val[1:-1].split(',')]
            metadata[key] = val
    return metadata

def sync_architecture():
    print("Syncing architecture specifications...")
    
    # 1. Parse Agents
    agents = []
    for f in AGENT_DIR.glob("*.md"):
        meta = parse_frontmatter(f)
        if meta and "role_id" in meta:
            meta["filename"] = f.name
            meta["role_id"] = int(meta["role_id"])
            agents.append(meta)
    agents.sort(key=lambda x: x["role_id"])
    
    # 2. Parse Skills
    skills = []
    for skill_dir in SKILLS_DIR.iterdir():
        if skill_dir.is_dir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                meta = parse_frontmatter(skill_file)
                if meta:
                    meta["name"] = meta.get("name", skill_dir.name)
                    meta["dir"] = skill_dir.name
                    skills.append(meta)
    skills.sort(key=lambda x: x["name"])
    
    # 3. Parse Workflows
    workflows = []
    for f in WORKFLOWS_DIR.glob("*.md"):
        # Simple extraction of command name and description
        content = f.read_text(encoding='utf-8')
        # Check first line for title/description
        lines = content.split('\n')
        name = f.stem
        desc = ""
        for line in lines:
            if line.startswith("#"):
                desc = line.replace("#", "").strip()
                break
        workflows.append({"name": f"/{name}", "description": desc or "Slash command workflow"})
    workflows.sort(key=lambda x: x["name"])
    
    # 4. Generate ARCHITECTURE.md content
    lines = []
    lines.append("# AG Kit Architecture")
    lines.append("")
    lines.append("> Comprehensive AI Agent Capability Expansion Toolkit — Synced dynamically")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📋 Overview")
    lines.append("")
    lines.append("AG Kit is a modular system consisting of:")
    lines.append("")
    lines.append(f"- **{len(agents)} OMEGA Agents** - Three-tier role-based AI personas with segregation of duties")
    lines.append(f"- **{len(skills)} Skills** - Domain-specific knowledge modules with conditional loading")
    lines.append(f"- **{len(workflows)} Workflows** - Slash command procedures")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🏗️ Directory Structure")
    lines.append("")
    lines.append("```plaintext")
    lines.append(".agents/")
    lines.append("├── ARCHITECTURE.md          # This file")
    lines.append("├── agent/                  # OMEGA Agents (3-tier SOD)")
    lines.append("├── skills/                  # Skills (with conditional loading)")
    lines.append("├── workflows/               # Slash Commands")
    lines.append("├── rules/                   # Global Rules")
    lines.append("├── memory/                  # Persistent Memory")
    lines.append("└── scripts/                 # Master Validation Scripts")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🤖 OMEGA Agents")
    lines.append("")
    lines.append("OMEGA agents follow a three-tier segregation of duties (SOD) architecture with strict boundaries between orchestration, implementation, and audit.")
    lines.append("")
    lines.append("### Three-Tier Structure")
    lines.append("")
    lines.append("- **Tier 1 (Ly)**: Orchestration and gate decisions only. Cannot implement or audit.")
    lines.append("- **Tier 2 (OpenCode)**: Implementation and coding. Must test all code. Cannot self-approve. Must submit to Tier 3 for audit.")
    lines.append("- **Tier 3 (Codex)**: READ-ONLY audit. No code modifications. Must provide final verdict: `[APPROVED]` or `[NEEDS_FIX]`. ")
    lines.append("")
    
    # Tier 1
    t1_agents = [a for a in agents if a.get("tier") == "1"]
    lines.append("### Tier 1: Ly (Orchestration/Gate-Only)")
    lines.append("")
    lines.append("| Role ID | Agent | Focus |")
    lines.append("| ------- | ----- | ----- |")
    for a in t1_agents:
        lines.append(f"| {a['role_id']} | `{a['name']}` | {a.get('description', '') or a.get('sod_boundary', '')} |")
    lines.append("")
    
    # Tier 2
    t2_agents = [a for a in agents if a.get("tier") == "2"]
    lines.append("### Tier 2: OpenCode (Implementation)")
    lines.append("")
    lines.append("| Role ID | Agent | Focus |")
    lines.append("| ------- | ----- | ----- |")
    for a in t2_agents:
        lines.append(f"| {a['role_id']} | `{a['name']}` | {a.get('description', '') or a.get('sod_boundary', '')} |")
    lines.append("")
    
    # Tier 3
    t3_agents = [a for a in agents if a.get("tier") == "3"]
    lines.append("### Tier 3: Codex (Audit)")
    lines.append("")
    lines.append("| Role ID | Agent | Focus |")
    lines.append("| ------- | ----- | ----- |")
    for a in t3_agents:
        lines.append(f"| {a['role_id']} | `{a['name']}` | {a.get('description', '') or a.get('sod_boundary', '')} |")
    lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append("## 🧩 Skills")
    lines.append("")
    lines.append("Modular knowledge domains that agents can load on-demand based on task context.")
    lines.append("")
    lines.append("| Skill | Directory | Description |")
    lines.append("| ----- | --------- | ----------- |")
    for s in skills:
        lines.append(f"| `{s['name']}` | `{s['dir']}` | {s.get('description', '')} |")
    lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append("## 🔄 Workflows")
    lines.append("")
    lines.append("Slash command procedures. Invoke with `/command`.")
    lines.append("")
    lines.append("| Command | Description |")
    lines.append("| ------- | ----------- |")
    for w in workflows:
        lines.append(f"| `{w['name']}` | {w['description']} |")
    lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append("## 📊 Statistics")
    lines.append("")
    lines.append(f"- **Total Agents**: {len(agents)}")
    lines.append(f"- **Total Skills**: {len(skills)}")
    lines.append(f"- **Total Workflows**: {len(workflows)}")
    
    ARCH_FILE.write_text("\n".join(lines), encoding='utf-8')
    print(f"Successfully synced architecture to {ARCH_FILE}")

if __name__ == "__main__":
    sync_architecture()
