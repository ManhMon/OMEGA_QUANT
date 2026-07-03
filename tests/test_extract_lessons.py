import json
import sys
from pathlib import Path
from types import SimpleNamespace


SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import extract_lessons
from extract_lessons import extract_lessons as run_extract_lessons
from extract_lessons import search_similar_lessons


def test_search_similar_lessons_prefers_relevant_root_cause(tmp_path):
    lessons_file = tmp_path / "lessons.jsonl"
    lessons = [
        {
            "gate": "STRICT_REPO_LOCAL_SKILL_LOADING_20260612",
            "role_id": 9,
            "role_name": "backend-engineer",
            "symptom": "L2 report failed repo-local validation.",
            "root_cause": "Repo-local skill source evidence missing from the report and role file path omitted.",
            "fix_pattern": "List exact .agents role and skill files read.",
        },
        {
            "gate": "PATH_TRAVERSAL_BLOCK_20260620",
            "role_id": 9,
            "role_name": "backend-engineer",
            "symptom": "Audit report path rejected.",
            "root_cause": "audit_report_path used path traversal with dot dot segments.",
            "fix_pattern": "Keep audit report path relative under .ly_state/session/audit_reports/.",
        },
        {
            "gate": "VECTOR_MEMORY_20260630",
            "role_id": 11,
            "role_name": "devops-engineer",
            "symptom": "Similarity lookup missed the best lesson.",
            "root_cause": "Keyword retrieval ignored semantic overlap between root cause and symptom.",
            "fix_pattern": "Use TF-IDF cosine similarity for retrieval.",
        },
    ]
    lessons_file.write_text("".join(json.dumps(lesson) + "\n" for lesson in lessons), encoding="utf-8")

    matches = search_similar_lessons(
        "repo local skill source missing from l2 report",
        role_id=9,
        limit=2,
        lessons_file=lessons_file,
    )

    assert matches
    assert matches[0]["gate"] == "STRICT_REPO_LOCAL_SKILL_LOADING_20260612"
    assert matches[0]["matching_engine"] == "local_tfidf_numpy"
    assert matches[0]["similarity"] >= matches[1]["similarity"]


def test_extract_lessons_uses_persistent_chromadb_client(tmp_path, monkeypatch):
    knowledge_dir = tmp_path / ".agents" / "knowledge"
    audit_dir = tmp_path / ".ly_state" / "session" / "audit_reports"
    session_dir = tmp_path / ".ly_state" / "session"
    knowledge_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    session_dir.mkdir(parents=True, exist_ok=True)

    (session_dir / "phase_gates.json").write_text(
        json.dumps({"HYBRID_REGIME_SOD_PERSISTENT_VECTOR_DB_20260701": {"l2_role_id": 9, "l2_role_name": "backend-engineer"}}),
        encoding="utf-8",
    )
    (audit_dir / "report.md").write_text(
        "**Gate**: HYBRID_REGIME_SOD_PERSISTENT_VECTOR_DB_20260701\n\n## Findings\nmissing repo-local evidence\n\n## Required Actions\nwrite report\n\n## Verdict\n[NEEDS_FIX]\n",
        encoding="utf-8",
    )

    captured = {}

    class FakeCollection:
        def delete(self, ids):
            captured["deleted_ids"] = ids

        def upsert(self, ids, documents):
            captured["ids"] = ids
            captured["documents"] = documents

        def query(self, query_texts, n_results):
            captured["query_texts"] = query_texts
            captured["n_results"] = n_results
            return {"ids": [["lesson-0"]], "distances": [[0.0]]}

    class FakePersistentClient:
        def __init__(self, path):
            captured["path"] = path

        def get_or_create_collection(self, name):
            captured["collection_name"] = name
            return FakeCollection()

    monkeypatch.setattr(extract_lessons, "WORKSPACE", tmp_path)
    monkeypatch.setattr(extract_lessons, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(extract_lessons, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", knowledge_dir / "lessons.jsonl")
    monkeypatch.setattr(extract_lessons, "CHROMA_DIR", knowledge_dir / "chromadb")
    monkeypatch.setattr(extract_lessons, "chromadb", SimpleNamespace(PersistentClient=FakePersistentClient))

    assert run_extract_lessons() == 1
    assert captured["path"] == str(knowledge_dir / "chromadb")
    assert captured["collection_name"] == "omega_lessons_search"
    assert captured["documents"][0]
