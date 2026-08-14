import json
import sys
from pathlib import Path

from extract_lessons import normalize_lesson_text, search_similar_lessons

WORKSPACE = Path(__file__).resolve().parent.parent
LESSONS_FILE = WORKSPACE / ".agents" / "knowledge" / "lessons.jsonl"

def _format_lessons(lessons):
    if not lessons:
        return ""

    output = ["=== RELEVANT LESSONS LEARNED FROM PAST FAILURES ==="]
    for idx, lesson in enumerate(lessons[:3], 1):
        output.append(f"Lesson {idx}: [Gate: {lesson.get('gate')}]")
        output.append(f"  - Root Cause: {str(lesson.get('root_cause', '')).strip()}")
        output.append(f"  - Recommended Fix Pattern: {str(lesson.get('fix_pattern', '')).strip()}")
        output.append("")
    return "\n".join(output)


def get_lessons(role_id_or_name, task_query=None, max_lessons=3):
    if not LESSONS_FILE.exists():
        return ""

    role_str = normalize_lesson_text(role_id_or_name)

    if task_query:
        matches = search_similar_lessons(
            query=task_query,
            role_id=role_id_or_name,
            limit=max_lessons,
            lessons_file=LESSONS_FILE,
            prefer_chromadb=True,
        )
        if matches:
            return _format_lessons(matches)

    lessons = []
    with open(LESSONS_FILE, encoding='utf-8') as f:
        for line in f:
            try:
                obj = json.loads(line)
                # Match by role_id or role_name
                if (
                    normalize_lesson_text(obj.get("role_id")) == role_str
                    or role_str in normalize_lesson_text(obj.get("role_name"))
                ):
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
        
    return _format_lessons(lessons[:max_lessons])

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python get_relevant_lessons.py <role_id_or_name> <task_query>")
        sys.exit(1)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
    print(get_lessons(sys.argv[1], sys.argv[2]))
