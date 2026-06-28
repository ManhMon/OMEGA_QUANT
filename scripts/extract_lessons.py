import os
import json
import re
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
AUDIT_DIR = WORKSPACE / ".ly_state" / "session" / "audit_reports"
KNOWLEDGE_DIR = WORKSPACE / ".agents" / "knowledge"
LESSONS_FILE = KNOWLEDGE_DIR / "lessons.jsonl"

def extract_lessons():
    print("Extracting lessons from audit reports...")
    
    if not AUDIT_DIR.exists():
        print("Audit reports directory does not exist.")
        return
        
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Let's read all audit reports
    lessons = []
    
    # Build list of reports and group them by gate base name
    reports = list(AUDIT_DIR.glob("*.md"))
    reports.sort(key=lambda x: x.stat().st_mtime) # Sort by modification time
    
    for r_file in reports:
        content = r_file.read_text(encoding='utf-8')
        
        # Parse fields using simple regex
        gate_match = re.search(r'\*\*Gate\*\*:\s*([A-Za-z0-9_]+)', content)
        role_match = re.search(r'\*\*Role\*\*:\s*([A-Za-z0-9_\-]+)\s*\(Role\s*(\d+)\)', content)
        verdict_match = re.search(r'## Verdict\s*\n+\s*\[(APPROVED|NEEDS_FIX|APPROVED_PARTIAL)\]', content)
        
        if not gate_match or not verdict_match:
            continue
            
        gate = gate_match.group(1)
        verdict = verdict_match.group(1)
        role_name = role_match.group(1) if role_match else "unknown"
        role_id = int(role_match.group(2)) if role_match else 0
        
        # Extract findings/issues
        findings_sec = ""
        findings_match = re.search(r'## Findings\s*\n(.*?)(\n##|$)', content, re.DOTALL)
        if findings_match:
            findings_sec = findings_match.group(1).strip()
            
        required_fixes_sec = ""
        fixes_match = re.search(r'## Required Action[s]?\s*\n(.*?)(\n##|$)', content, re.DOTALL)
        if fixes_match:
            required_fixes_sec = fixes_match.group(1).strip()
            
        if verdict == "NEEDS_FIX" and findings_sec:
            # We found a failure point! This is a rich lesson source.
            symptom = f"Failed audit on gate '{gate}' for role '{role_name}'."
            root_cause = findings_sec
            fix_pattern = required_fixes_sec or "See subsequent fix gates."
            
            lesson = {
                "timestamp": r_file.stat().st_mtime,
                "gate": gate,
                "role_id": role_id,
                "role_name": role_name,
                "symptom": symptom,
                "root_cause": root_cause,
                "fix_pattern": fix_pattern,
                "audit_report_path": str(r_file.relative_to(WORKSPACE))
            }
            lessons.append(lesson)
            
    # Write lessons to append-only jsonl
    # First, load existing if any
    existing_lessons = set()
    if LESSONS_FILE.exists():
        with open(LESSONS_FILE, encoding='utf-8') as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                    existing_lessons.add((obj.get("gate"), obj.get("role_id")))
                except Exception:
                    pass
                    
    with open(LESSONS_FILE, "a", encoding='utf-8') as fh:
        count = 0
        for l in lessons:
            if (l["gate"], l["role_id"]) not in existing_lessons:
                fh.write(json.dumps(l) + "\n")
                count += 1
                
    print(f"Successfully extracted {count} new lessons to {LESSONS_FILE}")

if __name__ == "__main__":
    extract_lessons()
