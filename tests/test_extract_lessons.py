import json
import sys
from pathlib import Path
from types import SimpleNamespace
import requests


SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import extract_lessons
from extract_lessons import extract_lessons as run_extract_lessons
from extract_lessons import search_similar_lessons


def test_resolve_lesson_llm_config_detects_omega_openrouter_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_lessons, "LLM_CONFIG_FILE", tmp_path / "nonexistent.jsonl")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OMEGA_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OMEGA_LLM_MODEL", raising=False)
    monkeypatch.setenv("OMEGA_LLM_API_KEY", "omega-key")

    config = extract_lessons._resolve_lesson_llm_config()

    assert config == {
        "api_key": "omega-key",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "free",
    }


def test_resolve_lesson_llm_config_uses_last_non_empty_jsonl_row(tmp_path, monkeypatch):
    config_file = tmp_path / "llm.jsonl"
    config_file.write_text(
        '{"api_key": "first-key", "base_url": "https://first.example.com/", "model": "first-model"}\n'
        '{"api_key": "last-key", "base_url": "https://last.example.com///", "model": "last-model"}\n\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(extract_lessons, "LLM_CONFIG_FILE", config_file)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OMEGA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    config = extract_lessons._resolve_lesson_llm_config()

    assert config == {
        "api_key": "last-key",
        "base_url": "https://last.example.com",
        "model": "last-model",
    }


def test_resolve_lesson_llm_config_falls_back_on_invalid_jsonl_row(tmp_path, monkeypatch):
    config_file = tmp_path / "llm.jsonl"
    config_file.write_text('{"api_key": "broken"\n', encoding="utf-8")
    monkeypatch.setattr(extract_lessons, "LLM_CONFIG_FILE", config_file)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OMEGA_LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example.com///")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")

    config = extract_lessons._resolve_lesson_llm_config()

    assert config == {
        "api_key": "env-key",
        "base_url": "https://env.example.com",
        "model": "env-model",
    }


def test_resolve_lesson_llm_config_falls_back_to_env_api_key_when_missing_in_file(tmp_path, monkeypatch):
    config_file = tmp_path / "llm.jsonl"
    config_file.write_text(
        '{"base_url": "https://file.example.com///", "model": "file-model"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(extract_lessons, "LLM_CONFIG_FILE", config_file)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OMEGA_LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example.com/")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")

    config = extract_lessons._resolve_lesson_llm_config()

    assert config == {
        "api_key": "env-key",
        "base_url": "https://file.example.com",
        "model": "file-model",
    }


def test_resolve_lesson_llm_config_strips_trailing_slashes_from_file_base_url(tmp_path, monkeypatch):
    config_file = tmp_path / "llm.jsonl"
    config_file.write_text(
        '{"api_key": "file-key", "base_url": "https://strip.example.com////", "model": "file-model"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(extract_lessons, "LLM_CONFIG_FILE", config_file)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OMEGA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    config = extract_lessons._resolve_lesson_llm_config()

    assert config["base_url"] == "https://strip.example.com"


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

    class FakeResponse:
        def __init__(self):
            content = json.dumps(
                {
                    "symptom": "Repo-local evidence missing.",
                    "root_cause": "The audit report omitted the required repo-local skill evidence.",
                    "fix_pattern": "List the exact repo-local role and skill files read in the L2 report.",
                }
            )
            self.text = json.dumps({"choices": [{"message": {"content": content}}]})

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "symptom": "Repo-local evidence missing.",
                                    "root_cause": "The audit report omitted the required repo-local skill evidence.",
                                    "fix_pattern": "List the exact repo-local role and skill files read in the L2 report.",
                                }
                            )
                        }
                    }
                ]
            }

    def fake_post(url, headers, json, timeout):
        captured["llm_url"] = url
        captured["llm_headers"] = headers
        captured["llm_payload"] = json
        captured["llm_timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(extract_lessons, "LLM_CONFIG_FILE", tmp_path / "nonexistent.jsonl")
    monkeypatch.setattr(requests, "post", fake_post)
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
    assert captured["llm_url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["llm_timeout"] == 30
    assert captured["llm_payload"]["response_format"] == {"type": "json_object"}


def test_extract_lessons_uses_llm_json_response(tmp_path, monkeypatch):
    knowledge_dir = tmp_path / ".agents" / "knowledge"
    audit_dir = tmp_path / ".ly_state" / "session" / "audit_reports"
    session_dir = tmp_path / ".ly_state" / "session"
    knowledge_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    session_dir.mkdir(parents=True, exist_ok=True)

    gate = "GP_EXTRACT_LESSONS_SEMANTIC"
    (session_dir / "phase_gates.json").write_text(
        json.dumps({gate: {"l2_role_id": 16, "l2_role_name": "machine-learning-engineer"}}),
        encoding="utf-8",
    )
    (audit_dir / "semantic_report.md").write_text(
        f"**Gate**: {gate}\n\n## Findings\nrepo-local lesson extraction failed\n\n## Verdict\n[NEEDS_FIX]\n",
        encoding="utf-8",
    )

    class FakeResponse:
        def __init__(self):
            content = json.dumps(
                {
                    "symptom": "Semantic extraction failed.",
                    "root_cause": "The old parser depended on markdown headings instead of report meaning.",
                    "fix_pattern": "Use an LLM to extract structured JSON from the full markdown.",
                }
            )
            self.text = json.dumps({"choices": [{"message": {"content": content}}]})

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "symptom": "Semantic extraction failed.",
                                    "root_cause": "The old parser depended on markdown headings instead of report meaning.",
                                    "fix_pattern": "Use an LLM to extract structured JSON from the full markdown.",
                                }
                            )
                        }
                    }
                ]
            }

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: FakeResponse())

    monkeypatch.setattr(extract_lessons, "WORKSPACE", tmp_path)
    monkeypatch.setattr(extract_lessons, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(extract_lessons, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", knowledge_dir / "lessons.jsonl")
    monkeypatch.setattr(extract_lessons, "CHROMA_DIR", knowledge_dir / "chromadb")
    monkeypatch.setattr(extract_lessons, "chromadb", None)

    assert run_extract_lessons() == 1

    lessons = [json.loads(line) for line in (knowledge_dir / "lessons.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lessons[0]["symptom"] == "Semantic extraction failed."
    assert lessons[0]["root_cause"] == "The old parser depended on markdown headings instead of report meaning."
    assert lessons[0]["fix_pattern"] == "Use an LLM to extract structured JSON from the full markdown."


def test_extract_lessons_uses_omega_openrouter_defaults(tmp_path, monkeypatch):
    knowledge_dir = tmp_path / ".agents" / "knowledge"
    audit_dir = tmp_path / ".ly_state" / "session" / "audit_reports"
    session_dir = tmp_path / ".ly_state" / "session"
    knowledge_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    session_dir.mkdir(parents=True, exist_ok=True)

    gate = "GP_EXTRACT_LESSONS_LLM_9ROUTER"
    (session_dir / "phase_gates.json").write_text(
        json.dumps({gate: {"l2_role_id": 16, "l2_role_name": "machine-learning-engineer"}}),
        encoding="utf-8",
    )
    (audit_dir / "openrouter_report.md").write_text(
        f"**Gate**: {gate}\n\n## Findings\nopenrouter extraction path\n\n## Verdict\n[NEEDS_FIX]\n",
        encoding="utf-8",
    )

    captured = {}

    class FakeResponse:
        def __init__(self):
            content = json.dumps(
                {
                    "symptom": "OpenRouter extraction used.",
                    "root_cause": "OMEGA_LLM_API_KEY selected the OpenRouter-compatible config.",
                    "fix_pattern": "Keep OMEGA_LLM defaults pointed at OpenRouter unless explicitly overridden.",
                }
            )
            self.text = json.dumps({"choices": [{"message": {"content": content}}]})

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "symptom": "OpenRouter extraction used.",
                                    "root_cause": "OMEGA_LLM_API_KEY selected the OpenRouter-compatible config.",
                                    "fix_pattern": "Keep OMEGA_LLM defaults pointed at OpenRouter unless explicitly overridden.",
                                }
                            )
                        }
                    }
                ]
            }

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OMEGA_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OMEGA_LLM_MODEL", raising=False)
    monkeypatch.setenv("OMEGA_LLM_API_KEY", "omega-key")
    monkeypatch.setattr(extract_lessons, "LLM_CONFIG_FILE", tmp_path / "nonexistent.jsonl")
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(extract_lessons, "WORKSPACE", tmp_path)
    monkeypatch.setattr(extract_lessons, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(extract_lessons, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", knowledge_dir / "lessons.jsonl")
    monkeypatch.setattr(extract_lessons, "CHROMA_DIR", knowledge_dir / "chromadb")
    monkeypatch.setattr(extract_lessons, "chromadb", None)

    assert run_extract_lessons() == 1
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer omega-key"
    assert captured["payload"]["model"] == "free"
    assert captured["timeout"] == 30


def test_extract_lessons_falls_back_when_llm_request_fails(tmp_path, monkeypatch):
    knowledge_dir = tmp_path / ".agents" / "knowledge"
    audit_dir = tmp_path / ".ly_state" / "session" / "audit_reports"
    session_dir = tmp_path / ".ly_state" / "session"
    knowledge_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    session_dir.mkdir(parents=True, exist_ok=True)

    gate = "GP_EXTRACT_LESSONS_LLM"
    report_body = "**Gate**: GP_EXTRACT_LESSONS_LLM\n\n## Findings\nllm extraction request failed\n\n## Verdict\n[NEEDS_FIX]\n"
    (session_dir / "phase_gates.json").write_text(
        json.dumps({gate: {"l2_role_id": 16, "l2_role_name": "machine-learning-engineer"}}),
        encoding="utf-8",
    )
    (audit_dir / "fallback_report.md").write_text(report_body, encoding="utf-8")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(requests.RequestException("boom")))
    monkeypatch.setattr(extract_lessons, "WORKSPACE", tmp_path)
    monkeypatch.setattr(extract_lessons, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(extract_lessons, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", knowledge_dir / "lessons.jsonl")
    monkeypatch.setattr(extract_lessons, "CHROMA_DIR", knowledge_dir / "chromadb")
    monkeypatch.setattr(extract_lessons, "chromadb", None)

    assert run_extract_lessons() == 1

    lesson = json.loads((knowledge_dir / "lessons.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert lesson["symptom"] == "Audit gate 'GP_EXTRACT_LESSONS_LLM' failed for role 'machine-learning-engineer'."
    assert "llm extraction request failed" in lesson["root_cause"]
