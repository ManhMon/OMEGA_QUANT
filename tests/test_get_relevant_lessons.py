import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_NAMES = ("extract_lessons.py", "get_relevant_lessons.py")


def _run_cli(tmp_path, lessons_content=None):
    scripts_dir = tmp_path / "scripts"
    knowledge_dir = tmp_path / ".agents" / "knowledge"
    scripts_dir.mkdir(parents=True)
    knowledge_dir.mkdir(parents=True)
    for name in SCRIPT_NAMES:
        shutil.copy(REPO_ROOT / "scripts" / name, scripts_dir / name)
    if lessons_content is not None:
        (knowledge_dir / "lessons.jsonl").write_text(lessons_content, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(scripts_dir / "get_relevant_lessons.py"), "9", "repair mandatory lesson lookup gate"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, knowledge_dir / "lessons.jsonl"


def test_cli_returns_lessons_without_traceback_for_valid_local_file(tmp_path):
    lesson = {
        "gate": "LESSON_GATE_REPAIR",
        "role_id": 9,
        "role_name": "backend-engineer",
        "root_cause": "mandatory lesson lookup import failed",
        "fix_pattern": "restore the pure normalization helper",
    }

    result, lessons_file = _run_cli(tmp_path, json.dumps(lesson) + "\n")

    assert result.returncode == 0
    assert "LESSON_GATE_REPAIR" in result.stdout
    assert "Traceback" not in result.stderr
    assert lessons_file.read_text(encoding="utf-8") == json.dumps(lesson) + "\n"


def test_cli_returns_empty_success_for_missing_local_file(tmp_path):
    result, lessons_file = _run_cli(tmp_path)

    assert result.returncode == 0
    assert result.stdout == "\n"
    assert "Traceback" not in result.stderr
    assert not lessons_file.exists()


def test_cli_returns_empty_success_for_malformed_local_file(tmp_path):
    result, lessons_file = _run_cli(tmp_path, "not json\n{\"role_id\":\n")

    assert result.returncode == 0
    assert result.stdout == "\n"
    assert "Traceback" not in result.stderr
    assert lessons_file.read_text(encoding="utf-8") == "not json\n{\"role_id\":\n"
