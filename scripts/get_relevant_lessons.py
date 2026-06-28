import os
import sys
import json
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
LESSONS_FILE = WORKSPACE / ".agents" / "knowledge" / "lessons.jsonl"

def get_lessons(role_id_or_name, max_lessons=3):
    if not LESSONS_FILE.exists():
        return ""
        
    role_str = str(role_id_or_name).lower()
    
    lessons = []
    with open(LESSONS_FILE, encoding='utf-8') as f:
        for line in f:
            try:
                obj = json.loads(line)
                # Match by role_id or role_name
                if str(obj.get("role_id")) == role_str or role_str in str(obj.get("role_name")).lower():
                    lessons.append(obj)
            except Exception:
                pass
                
    # Fallback to general lessons if no specific ones
    if not lessons:
        with open(LESSONS_FILE, encoding='utf-8') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    lessons.append(obj)
                except Exception:
                    pass
                    
    # Sort by timestamp descending (newest first)
    lessons.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    
    if not lessons:
        return ""
        
    output = []
    output.append("=== RELEVANT LESSONS LEARNED FROM PAST FAILURES ===")
    for idx, l in enumerate(lessons[:max_lessons], 1):
        output.append(f"Lesson {idx}: [Gate: {l.get('gate')}]")
        output.append(f"  - Root Cause: {l.get('root_cause').strip()}")
        output.append(f"  - Recommended Fix Pattern: {l.get('fix_pattern').strip()}")
        output.append("")
    return "\n".join(output)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_relevant_lessons.py <role_id_or_name>")
        sys.exit(1)
        
    print(get_lessons(sys.argv[1]))
