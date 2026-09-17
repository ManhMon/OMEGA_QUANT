import json
import sys
from pathlib import Path
from types import SimpleNamespace
import requests


SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import extract_lessons
from extract_lessons import extract_lessons as run_extract_lessons
from extract_lessons import normalize_lesson_text
from extract_lessons import search_similar_lessons


def mock_fixed_lesson_config(monkeypatch, content):
    fixed_path = Path(r"C:\Users\GHC\llm_configs\lesson_llm.json")
    original_read_text = Path.read_text

    def read_text(path, *args, **kwargs):
        if path == fixed_path:
            return content
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)


def test_normalize_lesson_text_handles_none_and_values():
    assert normalize_lesson_text(None) == ""
    assert normalize_lesson_text("  Backend-Engineer ") == "backend-engineer"
    assert normalize_lesson_text(9) == "9"


def test_extract_lessons_accepts_current_metadata_variants_and_bom_phase_gates(tmp_path, monkeypatch):
    knowledge_dir = tmp_path / ".agents" / "knowledge"
    audit_dir = tmp_path / ".ly_state" / "session" / "audit_reports"
    session_dir = tmp_path / ".ly_state" / "session"
    knowledge_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    session_dir.mkdir(parents=True, exist_ok=True)

    gate = "LESSON_EXTRACTOR_METADATA_COMPAT_20260726"
    (session_dir / "phase_gates.json").write_text(
        "\ufeff" + json.dumps({gate: {"l2_role_id": 9, "l2_role_name": "backend-engineer"}}),
        encoding="utf-8",
    )
    reports = {
        "bold.md": f"**Gate**: `{gate}`\n\n**Verdict**: `[NEEDS_FIX]`\n",
        "plain.md": f"Gate: {gate}\n\nVerdict: [NEEDS_FIX]\n",
        "heading.md": f"Gate: {gate}\n\n## Verdict\n[NEEDS_FIX]\n",
    }
    for name, content in reports.items():
        (audit_dir / name).write_text(content, encoding="utf-8")

    monkeypatch.setenv("OMEGA_SKIP_LLM", "1")
    monkeypatch.setattr(extract_lessons, "WORKSPACE", tmp_path)
    monkeypatch.setattr(extract_lessons, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(extract_lessons, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", knowledge_dir / "lessons.jsonl")
    monkeypatch.setattr(extract_lessons, "CHROMA_DIR", knowledge_dir / "chromadb")
    monkeypatch.setattr(extract_lessons, "chromadb", None)

    assert run_extract_lessons() == 0
    lesson = json.loads((knowledge_dir / "lessons.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert lesson["gate"] == gate
    assert lesson["role_id"] == 9


def test_resolve_lesson_llm_config_reads_only_fixed_external_json(monkeypatch):
    fixed_path = Path(r"C:\Users\GHC\llm_configs\lesson_llm.json")

    def read_fixed_config(path, *args, **kwargs):
        assert path == fixed_path
        return '{"api_key": "external-key", "base_url": "https://external.example.com///", "model": "external-model"}'

    monkeypatch.setattr(Path, "read_text", read_fixed_config)
    monkeypatch.setenv("OPENAI_API_KEY", "ignored-environment-key")

    config = extract_lessons._resolve_lesson_llm_config()

    assert config == {
        "api_key": "external-key",
        "base_url": "https://external.example.com",
        "model": "external-model",
    }


def test_resolve_lesson_llm_config_fails_closed_on_invalid_fixed_external_json(monkeypatch):
    mock_fixed_lesson_config(monkeypatch, '{"api_key": "broken"\n')
    monkeypatch.setenv("OPENAI_API_KEY", "ignored-environment-key")

    assert extract_lessons._resolve_lesson_llm_config() is None

def test_resolve_lesson_llm_config_fails_closed_without_usable_api_key(monkeypatch):
    mock_fixed_lesson_config(
        monkeypatch,
        '{"base_url": "https://file.example.com///", "model": "file-model"}\n',
    )
    monkeypatch.setenv("OPENAI_API_KEY", "ignored-environment-key")

    assert extract_lessons._resolve_lesson_llm_config() is None


def test_resolve_lesson_llm_config_fails_closed_on_non_string_or_blank_routing_values(monkeypatch):
    for field_value in (None, 0, [], {}):
        mock_fixed_lesson_config(
            monkeypatch,
            json.dumps({"api_key": "external-key", "base_url": field_value, "model": "file-model"}),
        )
        assert extract_lessons._resolve_lesson_llm_config() is None

    for field_value in (None, 0, [], {}):
        mock_fixed_lesson_config(
            monkeypatch,
            json.dumps({"api_key": "external-key", "base_url": "https://file.example.com", "model": field_value}),
        )
        assert extract_lessons._resolve_lesson_llm_config() is None

    mock_fixed_lesson_config(
        monkeypatch,
        '{"api_key": "external-key", "base_url": "   ", "model": "file-model"}',
    )
    assert extract_lessons._resolve_lesson_llm_config() is None

    mock_fixed_lesson_config(
        monkeypatch,
        '{"api_key": "external-key", "base_url": "https://file.example.com", "model": "   "}',
    )
    assert extract_lessons._resolve_lesson_llm_config() is None


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

    mock_fixed_lesson_config(
        monkeypatch,
        '{"api_key": "test-key", "base_url": "https://api.openai.com/v1", "model": "test-model"}',
    )
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(extract_lessons, "WORKSPACE", tmp_path)
    monkeypatch.setattr(extract_lessons, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(extract_lessons, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", knowledge_dir / "lessons.jsonl")
    monkeypatch.setattr(extract_lessons, "CHROMA_DIR", knowledge_dir / "chromadb")
    monkeypatch.setattr(extract_lessons, "chromadb", SimpleNamespace(PersistentClient=FakePersistentClient))

    assert run_extract_lessons() == 0
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

    mock_fixed_lesson_config(
        monkeypatch,
        '{"api_key": "test-key", "base_url": "https://api.openai.com/v1", "model": "test-model"}',
    )
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: FakeResponse())

    monkeypatch.setattr(extract_lessons, "WORKSPACE", tmp_path)
    monkeypatch.setattr(extract_lessons, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(extract_lessons, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", knowledge_dir / "lessons.jsonl")
    monkeypatch.setattr(extract_lessons, "CHROMA_DIR", knowledge_dir / "chromadb")
    monkeypatch.setattr(extract_lessons, "chromadb", None)

    assert run_extract_lessons() == 0

    lessons = [json.loads(line) for line in (knowledge_dir / "lessons.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lessons[0]["symptom"] == "Semantic extraction failed."
    assert lessons[0]["root_cause"] == "The old parser depended on markdown headings instead of report meaning."
    assert lessons[0]["fix_pattern"] == "Use an LLM to extract structured JSON from the full markdown."


def test_extract_lessons_does_not_use_environment_model_route(tmp_path, monkeypatch):
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

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OMEGA_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OMEGA_LLM_MODEL", raising=False)
    monkeypatch.setenv("OMEGA_LLM_API_KEY", "omega-key")
    original_read_text = Path.read_text

    def missing_fixed_config(path, *args, **kwargs):
        if path == Path(r"C:\Users\GHC\llm_configs\lesson_llm.json"):
            raise FileNotFoundError(path)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", missing_fixed_config)
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected LLM request")))
    monkeypatch.setattr(extract_lessons, "WORKSPACE", tmp_path)
    monkeypatch.setattr(extract_lessons, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(extract_lessons, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", knowledge_dir / "lessons.jsonl")
    monkeypatch.setattr(extract_lessons, "CHROMA_DIR", knowledge_dir / "chromadb")
    monkeypatch.setattr(extract_lessons, "chromadb", None)

    assert run_extract_lessons() == 0
    lesson = json.loads((knowledge_dir / "lessons.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert lesson["symptom"] == "Audit gate 'GP_EXTRACT_LESSONS_LLM_9ROUTER' failed for role 'machine-learning-engineer'."


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

    mock_fixed_lesson_config(
        monkeypatch,
        '{"api_key": "test-key", "base_url": "https://api.openai.com/v1", "model": "test-model"}',
    )
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: (_ for _ in ()).throw(requests.RequestException("boom")))
    monkeypatch.setattr(extract_lessons, "WORKSPACE", tmp_path)
    monkeypatch.setattr(extract_lessons, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(extract_lessons, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", knowledge_dir / "lessons.jsonl")
    monkeypatch.setattr(extract_lessons, "CHROMA_DIR", knowledge_dir / "chromadb")
    monkeypatch.setattr(extract_lessons, "chromadb", None)

    assert run_extract_lessons() == 0

    lesson = json.loads((knowledge_dir / "lessons.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert lesson["symptom"] == "Audit gate 'GP_EXTRACT_LESSONS_LLM' failed for role 'machine-learning-engineer'."
    assert "llm extraction request failed" in lesson["root_cause"]


def test_extract_lessons_writes_deterministic_append_only_evidence(tmp_path, monkeypatch):
    knowledge_dir = tmp_path / ".agents" / "knowledge"
    audit_dir = tmp_path / ".ly_state" / "session" / "audit_reports"
    session_dir = tmp_path / ".ly_state" / "session"
    knowledge_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    gate = "DETERMINISTIC_LESSON_GATE"
    (session_dir / "phase_gates.json").write_text(
        json.dumps({gate: {"l2_role_id": 9, "l2_role_name": "backend-engineer"}}), encoding="utf-8"
    )
    report = f"Gate: {gate}\n\nVerdict: [NEEDS_FIX]\n"
    (audit_dir / "z.md").write_text(report, encoding="utf-8")
    (audit_dir / "a.md").write_text(report, encoding="utf-8")
    monkeypatch.setenv("OMEGA_SKIP_LLM", "1")
    monkeypatch.setattr(extract_lessons, "WORKSPACE", tmp_path)
    monkeypatch.setattr(extract_lessons, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(extract_lessons, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", knowledge_dir / "lessons.jsonl")
    monkeypatch.setattr(extract_lessons, "CHROMA_DIR", knowledge_dir / "chromadb")
    monkeypatch.setattr(extract_lessons, "chromadb", None)

    previous_evidence = set(session_dir.glob("lessons_extraction_hard_gate_20260726_*.json"))
    assert run_extract_lessons() == 0
    evidence_path = next(iter(set(session_dir.glob("lessons_extraction_hard_gate_20260726_*.json")) - previous_evidence))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    store = (knowledge_dir / "lessons.jsonl").read_bytes()
    assert [source["path"] for source in evidence["source_reports"]] == [
        ".ly_state/session/audit_reports/a.md", ".ly_state/session/audit_reports/z.md"
    ]
    assert evidence["candidate_count"] == evidence["persisted_count"] + evidence["deduplicated_count"] == 1
    assert evidence["persisted_count"] == 1
    assert evidence["prefix_verified"] is True
    assert evidence["post_sha256"] == extract_lessons._sha256(store)
    assert evidence["authorization"] is True

    previous_evidence = set(session_dir.glob("lessons_extraction_hard_gate_20260726_*.json"))
    assert run_extract_lessons() == 0
    evidence = json.loads(next(iter(set(session_dir.glob("lessons_extraction_hard_gate_20260726_*.json")) - previous_evidence)).read_text(encoding="utf-8"))
    assert evidence["persisted_count"] == 0
    assert evidence["deduplicated_count"] == 1
    assert evidence["authorization"] is True


def test_extract_lessons_fails_closed_without_eligible_report(tmp_path, monkeypatch):
    audit_dir = tmp_path / ".ly_state" / "session" / "audit_reports"
    audit_dir.mkdir(parents=True)
    (audit_dir / "report.md").write_text("Gate: NOPE\nVerdict: [APPROVED]\n", encoding="utf-8")
    monkeypatch.setattr(extract_lessons, "WORKSPACE", tmp_path)
    monkeypatch.setattr(extract_lessons, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(extract_lessons, "KNOWLEDGE_DIR", tmp_path / ".agents" / "knowledge")
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", tmp_path / ".agents" / "knowledge" / "lessons.jsonl")

    assert run_extract_lessons() == 1
    evidence = json.loads(next((tmp_path / ".ly_state" / "session").glob("lessons_extraction_hard_gate_20260726_*.json")).read_text(encoding="utf-8"))
    assert evidence["failure_code"] == "NO_ELIGIBLE_AUDIT_EVIDENCE"
    assert evidence["authorization"] is False


def test_extract_lessons_fails_closed_for_malformed_store_and_lock_contention(tmp_path, monkeypatch):
    knowledge_dir = tmp_path / ".agents" / "knowledge"
    audit_dir = tmp_path / ".ly_state" / "session" / "audit_reports"
    session_dir = tmp_path / ".ly_state" / "session"
    knowledge_dir.mkdir(parents=True)
    audit_dir.mkdir(parents=True)
    gate = "MALFORMED_STORE_GATE"
    (session_dir / "phase_gates.json").write_text(json.dumps({gate: {"l2_role_id": 9}}), encoding="utf-8")
    (audit_dir / "report.md").write_text(f"Gate: {gate}\nVerdict: [NEEDS_FIX]\n", encoding="utf-8")
    store = knowledge_dir / "lessons.jsonl"
    store.write_text("not-json\n", encoding="utf-8")
    monkeypatch.setenv("OMEGA_SKIP_LLM", "1")
    monkeypatch.setattr(extract_lessons, "WORKSPACE", tmp_path)
    monkeypatch.setattr(extract_lessons, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(extract_lessons, "KNOWLEDGE_DIR", knowledge_dir)
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", store)
    monkeypatch.setattr(extract_lessons, "CHROMA_DIR", knowledge_dir / "chromadb")
    monkeypatch.setattr(extract_lessons, "chromadb", None)

    assert run_extract_lessons() == 1
    evidence = json.loads(next(session_dir.glob("lessons_extraction_hard_gate_20260726_*.json")).read_text(encoding="utf-8"))
    assert evidence["failure_code"] == "MALFORMED_LESSON_STORE:1"
    assert evidence["malformed_count"] == 1

    store.write_text("", encoding="utf-8")
    lock = extract_lessons._lock_file(store.with_suffix(".jsonl.lock"))
    monkeypatch.setattr(extract_lessons, "LOCK_TIMEOUT_SECONDS", 0)
    previous_evidence = set(session_dir.glob("lessons_extraction_hard_gate_20260726_*.json"))
    try:
        assert run_extract_lessons() == 1
    finally:
        extract_lessons._unlock_file(lock)
    evidence_path = next(iter(set(session_dir.glob("lessons_extraction_hard_gate_20260726_*.json")) - previous_evidence))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["failure_code"] == "LOCK_CONTENTION"
    assert evidence["lock_result"] == "not_acquired"


def test_atomic_store_replacement_preserves_prefix_and_removes_pending(tmp_path, monkeypatch):
    store = tmp_path / "lessons.jsonl"
    store.write_bytes(b'{"gate":"old","role_id":1}\n')
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", store)

    extract_lessons._write_pending("prepared", store.read_bytes(), b'{"gate":"new","role_id":2}\n')
    extract_lessons._recover_transaction()

    assert store.read_bytes() == b'{"gate":"old","role_id":1}\n{"gate":"new","role_id":2}\n'
    assert not extract_lessons._pending_path().exists()


def test_prepared_recovery_accepts_post_store_and_store_committed_requires_post(tmp_path, monkeypatch):
    store = tmp_path / "lessons.jsonl"
    pre, append = b"pre\n", b"append\n"
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", store)
    store.write_bytes(pre + append)

    extract_lessons._write_pending("prepared", pre, append)
    extract_lessons._recover_transaction()
    assert not extract_lessons._pending_path().exists()

    extract_lessons._write_pending("store_committed", pre, append)
    extract_lessons._recover_transaction()
    assert store.read_bytes() == pre + append
    assert not extract_lessons._pending_path().exists()


def test_pending_validation_fails_closed_for_invalid_fields(tmp_path, monkeypatch):
    store = tmp_path / "lessons.jsonl"
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", store)
    for pending in (
        {"state": "other"},
        {"state": "prepared", "pre_bytes": "!", "append_bytes": "", "post_bytes": ""},
        {"state": "prepared", "pre_bytes": "AB==", "append_bytes": "", "post_bytes": "", "pre_length": 1, "pre_sha256": extract_lessons._sha256(b"\x00"), "append_length": 0, "append_sha256": extract_lessons._sha256(b""), "post_length": 1, "post_sha256": extract_lessons._sha256(b"\x00")},
        {"state": "prepared", "pre_bytes": "", "pre_length": 1, "pre_sha256": extract_lessons._sha256(b""), "append_bytes": "", "append_length": 0, "append_sha256": extract_lessons._sha256(b""), "post_bytes": "", "post_length": 0, "post_sha256": extract_lessons._sha256(b"")},
        {"state": "prepared", "pre_bytes": "", "pre_length": 0, "pre_sha256": "wrong", "append_bytes": "", "append_length": 0, "append_sha256": extract_lessons._sha256(b""), "post_bytes": "", "post_length": 0, "post_sha256": extract_lessons._sha256(b"")},
    ):
        extract_lessons._pending_path().write_text(json.dumps(pending), encoding="utf-8")
        try:
            extract_lessons._recover_transaction()
        except RuntimeError as error:
            assert str(error).startswith("INVALID_PENDING")
        else:
            raise AssertionError("invalid pending state recovered")


def test_replace_failures_preserve_store_or_recover_after_replace(tmp_path, monkeypatch):
    store = tmp_path / "lessons.jsonl"
    pre, append = b"pre\n", b"append\n"
    store.write_bytes(pre)
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", store)
    original_replace = extract_lessons.os.replace

    monkeypatch.setattr(extract_lessons.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("before replace")))
    try:
        extract_lessons._durable_replace(store, pre + append)
    except OSError:
        pass
    else:
        raise AssertionError("replace failure did not propagate")
    assert store.read_bytes() == pre

    monkeypatch.setattr(extract_lessons.os, "replace", original_replace)
    extract_lessons._write_pending("prepared", pre, append)
    extract_lessons._durable_replace(store, pre + append)
    monkeypatch.setattr(extract_lessons, "_write_pending", lambda *_: (_ for _ in ()).throw(OSError("after replace")))
    try:
        extract_lessons._write_pending("store_committed", pre, append)
    except OSError:
        pass
    assert store.read_bytes() == pre + append
    monkeypatch.undo()
    monkeypatch.setattr(extract_lessons, "LESSONS_FILE", store)
    extract_lessons._recover_transaction()
    assert store.read_bytes() == pre + append
    assert not extract_lessons._pending_path().exists()


def test_pre_replace_fsync_failure_preserves_store(tmp_path, monkeypatch):
    store = tmp_path / "lessons.jsonl"
    store.write_bytes(b"old\n")
    monkeypatch.setattr(extract_lessons.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("fsync")))

    try:
        extract_lessons._durable_replace(store, b"new\n")
    except OSError:
        pass
    else:
        raise AssertionError("fsync failure did not propagate")
    assert store.read_bytes() == b"old\n"


def test_pre_replace_write_failure_preserves_store(tmp_path, monkeypatch):
    store = tmp_path / "lessons.jsonl"
    store.write_bytes(b"old\n")
    original_open = Path.open

    def fail_temp_write(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        if path.parent == store.parent and path.name.startswith(f".{store.name}."):
            monkeypatch.setattr(handle, "write", lambda _: (_ for _ in ()).throw(OSError("write")))
        return handle

    monkeypatch.setattr(Path, "open", fail_temp_write)
    try:
        extract_lessons._durable_replace(store, b"new\n")
    except OSError:
        pass
    else:
        raise AssertionError("write failure did not propagate")
    assert store.read_bytes() == b"old\n"
