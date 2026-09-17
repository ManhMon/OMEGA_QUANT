import base64
import json
import os
import re
import hashlib
import secrets
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:
    import chromadb
except ImportError:  # ponytail: local TF-IDF is default; enable Chroma only when installed.
    chromadb = None

WORKSPACE = Path(__file__).resolve().parent.parent
AUDIT_DIR = WORKSPACE / ".ly_state" / "session" / "audit_reports"
KNOWLEDGE_DIR = WORKSPACE / ".agents" / "knowledge"
LESSONS_FILE = KNOWLEDGE_DIR / "lessons.jsonl"
CHROMA_DIR = KNOWLEDGE_DIR / "chromadb"
COLLECTION_NAME = "omega_lessons_search"
EVIDENCE_GATE = "lessons_extraction_hard_gate_20260726"
EVIDENCE_SCHEMA_VERSION = 1
LOCK_TIMEOUT_SECONDS = 5.0
TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")
GATE_RE = re.compile(
    r"(?im)^\s*(?:\*\*)?Gate(?:\*\*)?\s*:\s*`?([A-Za-z0-9_]+)`?\s*$"
)
VERDICT_RE = re.compile(
    r"(?im)^\s*(?:##\s+)?(?:\*\*)?Verdict(?:\*\*)?\s*:\s*`?\[(APPROVED|NEEDS_FIX|APPROVED_PARTIAL)\]`?\s*$"
    r"|^\s*##\s+Verdict\s*\n+\s*`?\[(APPROVED|NEEDS_FIX|APPROVED_PARTIAL)\]`?"
)
JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

ROLE_MAP = {
    6: "system-architect", 7: "tech-lead", 8: "frontend-engineer",
    9: "backend-engineer", 10: "database-admin", 11: "devops-engineer",
    12: "cloud-infra-engineer", 13: "ui-ux-integrator", 14: "data-scientist",
    15: "data-engineer", 16: "machine-learning-engineer"
}


def normalize_lesson_text(value):
    return "" if value is None else str(value).strip().lower()


def _tokenize(text):
    return TOKEN_RE.findall((text or "").lower())


def _lesson_document(lesson):
    parts = [
        lesson.get("gate", ""),
        lesson.get("role_name", ""),
        lesson.get("symptom", ""),
        lesson.get("root_cause", ""),
        lesson.get("fix_pattern", ""),
    ]
    return "\n".join(part for part in parts if part)


def _resolve_lesson_llm_config():
    try:
        config = json.loads(
            Path(r"C:\Users\GHC\llm_configs\lesson_llm.json").read_text(encoding="utf-8")
        )
        if not isinstance(config, dict):
            raise TypeError("lesson LLM config must be a JSON object")
        api_key = config.get("api_key")
        if not isinstance(api_key, str) or not api_key.strip():
            return None
        base_url = config.get("base_url")
        model = config.get("model")
        if (
            not isinstance(base_url, str)
            or not base_url.strip()
            or not isinstance(model, str)
            or not model.strip()
        ):
            return None
        return {
            "api_key": api_key,
            "base_url": base_url.rstrip("/"),
            "model": model,
        }
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _fallback_lesson_fields(content, gate, role_name):
    compact_content = (content or "").strip()
    return {
        "symptom": f"Audit gate '{gate}' failed for role '{role_name}'.",
        "root_cause": compact_content[:4000],
        "fix_pattern": "Review the audit report markdown and apply the required fix before rerunning the gate.",
    }


def _parse_llm_json_payload(payload):
    if isinstance(payload, dict):
        return payload

    text = (payload or "").strip()
    if not text:
        raise ValueError("empty LLM response")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = JSON_BLOCK_RE.search(text)
        if not match:
            raise
        return json.loads(match.group(0))


def _completion_message_content(response_body):
    try:
        return json.loads(response_body)["choices"][0]["message"]["content"]
    except json.JSONDecodeError:
        chunks = []
        for line in response_body.splitlines():
            if not line.startswith("data:"):
                continue
            event = line[5:].strip()
            if event == "[DONE]":
                continue
            choices = json.loads(event).get("choices")
            if not isinstance(choices, list):
                raise ValueError("malformed SSE choices")
            if not choices:
                continue
            chunk = choices[0]["delta"].get("content")
            if chunk:
                chunks.append(chunk)
        content = "".join(chunks)
        if not content:
            raise ValueError("empty SSE response")
        return content


def _extract_lesson_fields_with_llm(content, gate, role_name):
    if os.getenv("SKIP_LESSON_EXTRACTION") == "1" or os.getenv("OMEGA_SKIP_LLM") == "1":
        return {"symptom": "Skipped", "root_cause": "Skipped", "fix_pattern": "Skipped"}

    config = _resolve_lesson_llm_config()
    if config is None:
        return _fallback_lesson_fields(content, gate, role_name)

    try:
        import requests
    except ImportError:
        return _fallback_lesson_fields(content, gate, role_name)

    content_excerpt = content[:3000]
    prompt = (
        "Extract lessons learned from this L3 audit report. "
        "Return JSON only with keys symptom, root_cause, fix_pattern. "
        "Each value must be a concise plain string. "
        "Do not wrap the JSON in markdown.\n\n"
        f"Gate: {gate}\n"
        f"Role: {role_name}\n\n"
        "Audit report markdown:\n"
        f"{content_excerpt}"
    )
    payload = {
        "model": config["model"],
        "messages": [
            {
                "role": "system",
                "content": "You extract structured lessons from audit reports and respond with strict JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        message = _completion_message_content(response.text)
        lesson_fields = _parse_llm_json_payload(message)
    except Exception as error:
        print(f"Warning: lesson extraction LLM call failed: {error}")
        return _fallback_lesson_fields(content, gate, role_name)

    symptom = str(lesson_fields.get("symptom", "")).strip()
    root_cause = str(lesson_fields.get("root_cause", "")).strip()
    fix_pattern = str(lesson_fields.get("fix_pattern", "")).strip()
    if not symptom or not root_cause or not fix_pattern:
        return _fallback_lesson_fields(content, gate, role_name)

    return {
        "symptom": symptom,
        "root_cause": root_cause,
        "fix_pattern": fix_pattern,
    }


def load_lessons(lessons_file=LESSONS_FILE):
    if not Path(lessons_file).exists():
        return []

    lessons = []
    with Path(lessons_file).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                lessons.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return lessons


def _build_tfidf_matrix(documents):
    tokenized_documents = [_tokenize(document) for document in documents]
    vocabulary = sorted({token for document in tokenized_documents for token in document})
    if not vocabulary:
        return np.zeros((len(documents), 0), dtype=float), vocabulary

    index_by_token = {token: idx for idx, token in enumerate(vocabulary)}
    term_matrix = np.zeros((len(documents), len(vocabulary)), dtype=float)
    document_frequency = np.zeros(len(vocabulary), dtype=float)

    for row_index, tokens in enumerate(tokenized_documents):
        counts = Counter(tokens)
        if not counts:
            continue
        for token, count in counts.items():
            column_index = index_by_token[token]
            term_matrix[row_index, column_index] = float(count)
        for token in counts:
            document_frequency[index_by_token[token]] += 1.0

    row_sums = term_matrix.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0.0] = 1.0
    term_frequency = term_matrix / row_sums
    inverse_document_frequency = np.log((1.0 + len(documents)) / (1.0 + document_frequency)) + 1.0
    return term_frequency * inverse_document_frequency, vocabulary


def _vectorize_query(query, vocabulary):
    query_vector = np.zeros(len(vocabulary), dtype=float)
    counts = Counter(_tokenize(query))
    if not counts or not vocabulary:
        return query_vector

    index_by_token = {token: idx for idx, token in enumerate(vocabulary)}
    total = float(sum(counts.values())) or 1.0
    for token, count in counts.items():
        column_index = index_by_token.get(token)
        if column_index is not None:
            query_vector[column_index] = count / total
    return query_vector


def _cosine_similarity(matrix, query_vector):
    if matrix.size == 0 or query_vector.size == 0:
        return np.zeros(matrix.shape[0], dtype=float)

    matrix_norm = np.linalg.norm(matrix, axis=1)
    query_norm = np.linalg.norm(query_vector)
    if query_norm == 0.0:
        return np.zeros(matrix.shape[0], dtype=float)

    denominator = matrix_norm * query_norm
    denominator[denominator == 0.0] = 1.0
    return matrix.dot(query_vector) / denominator


def _search_lessons_locally(query, lessons, limit):
    documents = [_lesson_document(lesson) for lesson in lessons]
    matrix, vocabulary = _build_tfidf_matrix(documents)
    query_vector = _vectorize_query(query, vocabulary)
    scores = _cosine_similarity(matrix, query_vector)
    ranked_indexes = np.argsort(scores)[::-1]

    matches = []
    for index in ranked_indexes[:limit]:
        lesson = dict(lessons[int(index)])
        lesson["similarity"] = float(scores[int(index)])
        lesson["matching_engine"] = "local_tfidf_numpy"
        matches.append(lesson)
    return matches


def _search_lessons_with_chromadb(query, lessons, limit):
    if chromadb is None:
        raise RuntimeError("chromadb unavailable")

    client_factory = getattr(chromadb, "PersistentClient", None)
    if client_factory is None:
        raise RuntimeError("chromadb client unavailable")

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = client_factory(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    documents = [_lesson_document(lesson) for lesson in lessons]
    ids = [f"lesson-{index}" for index in range(len(lessons))]
    if ids:
        try:
            collection.delete(ids=ids)
        except Exception:
            pass
        collection.upsert(ids=ids, documents=documents)
    result = collection.query(query_texts=[query], n_results=min(limit, len(lessons)))

    matches = []
    ids_list = result.get("ids", [[]])[0]
    distance_list = result.get("distances", [[]])[0]
    for lesson_id, distance in zip(ids_list, distance_list):
        lesson_index = int(lesson_id.split("-")[-1])
        lesson = dict(lessons[lesson_index])
        lesson["similarity"] = float(1.0 / (1.0 + distance))
        lesson["matching_engine"] = "chromadb"
        matches.append(lesson)
    return matches


def search_similar_lessons(query, role_id=None, limit=3, lessons_file=LESSONS_FILE, prefer_chromadb=False):
    lessons = load_lessons(lessons_file)
    if role_id is not None:
        filtered_lessons = [lesson for lesson in lessons if str(lesson.get("role_id")) == str(role_id)]
        if filtered_lessons:
            lessons = filtered_lessons

    if not lessons:
        return []

    if prefer_chromadb:
        try:
            return _search_lessons_with_chromadb(query, lessons, limit)
        except Exception:
            pass

    return _search_lessons_locally(query, lessons, limit)

def _canonical_json(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(value):
    return hashlib.sha256(value).hexdigest()




def _utc_compact_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _lock_file(path, timeout=LOCK_TIMEOUT_SECONDS):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if not handle.tell():
        handle.write(b"\0")
        handle.flush()
    deadline = time.monotonic() + timeout
    while True:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except OSError:
            if time.monotonic() >= deadline:
                handle.close()
                raise TimeoutError("lesson-store lock contention")
            time.sleep(0.05)


def _unlock_file(handle):
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _role_from_report(content, gate_data):
    role_id = gate_data.get("l2_role_id")
    if role_id is not None:
        return int(role_id), gate_data.get("l2_role_name") or ROLE_MAP.get(int(role_id), "unknown")
    match = re.search(r"l2_role(\d+)", content)
    if match:
        role_id = int(match.group(1))
        return role_id, ROLE_MAP.get(role_id, "unknown")
    match = re.search(r"\*\*L2 Role\*\*:\s*([^\n]+)", content, re.IGNORECASE)
    if match and (numbers := re.findall(r"\d+", match.group(1))):
        role_id = int(numbers[0])
        return role_id, ROLE_MAP.get(role_id, "unknown")
    return 0, "unknown"


def _load_gates():
    path = WORKSPACE / ".ly_state" / "session" / "phase_gates.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("phase_gates.json must be an object")
    return data


def _snapshot_reports(gates):
    snapshots = []
    for report in sorted(AUDIT_DIR.glob("*.md"), key=lambda item: item.relative_to(WORKSPACE).as_posix()):
        raw = report.read_bytes()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"invalid UTF-8 audit report: {report}") from error
        gate_match, verdict_match = GATE_RE.search(content), VERDICT_RE.search(content)
        gate = gate_match.group(1) if gate_match else None
        verdict = next((value for value in verdict_match.groups() if value is not None), None) if verdict_match else None
        role_id, role_name = _role_from_report(content, gates.get(gate, {})) if gate else (0, "unknown")
        snapshots.append({
            "path": report.relative_to(WORKSPACE).as_posix(), "sha256": _sha256(raw),
            "gate": gate, "verdict": verdict, "role_id": role_id, "role_name": role_name,
            "eligible": bool(gate and verdict == "NEEDS_FIX"), "content": content,
        })
    return snapshots


def _load_existing_identities(raw):
    identities = set()
    malformed = 0
    for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            lesson = json.loads(line)
            identity = (lesson["gate"], lesson["role_id"])
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            malformed += 1
            continue
        identities.add(identity)
    if malformed:
        raise ValueError(f"MALFORMED_LESSON_STORE:{malformed}")
    return identities


def _write_evidence(evidence):
    directory = WORKSPACE / ".ly_state" / "session"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{EVIDENCE_GATE}_{_utc_compact_timestamp()}_{secrets.token_hex(8)}.json"
    temporary = target.with_suffix(".tmp")
    payload = _canonical_json(evidence)
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    try:
        directory_handle = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_handle)
        finally:
            os.close(directory_handle)
    except (AttributeError, OSError):
        pass
    return target.relative_to(WORKSPACE).as_posix()


def _pending_path(lessons_file=None):
    return Path(LESSONS_FILE if lessons_file is None else lessons_file).with_suffix(".jsonl.pending.json")


def _fsync_directory(directory):
    try:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except (AttributeError, OSError):
        pass


def _durable_replace(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _pending_bytes(state, pre_bytes, append_bytes):
    post_bytes = pre_bytes + append_bytes
    return _canonical_json({
        "state": state,
        "pre_bytes": base64.b64encode(pre_bytes).decode("ascii"), "pre_length": len(pre_bytes), "pre_sha256": _sha256(pre_bytes),
        "append_bytes": base64.b64encode(append_bytes).decode("ascii"), "append_length": len(append_bytes), "append_sha256": _sha256(append_bytes),
        "post_bytes": base64.b64encode(post_bytes).decode("ascii"), "post_length": len(post_bytes), "post_sha256": _sha256(post_bytes),
    })


def _write_pending(state, pre_bytes, append_bytes):
    _durable_replace(_pending_path(), _pending_bytes(state, pre_bytes, append_bytes))


def _validated_pending():
    try:
        pending = json.loads(_pending_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("INVALID_PENDING") from error
    if not isinstance(pending, dict) or pending.get("state") not in {"prepared", "store_committed"}:
        raise RuntimeError("INVALID_PENDING_STATE")
    decoded = {}
    for name in ("pre", "append", "post"):
        value = pending.get(f"{name}_bytes")
        if not isinstance(value, str):
            raise RuntimeError(f"INVALID_PENDING_{name.upper()}")
        try:
            payload = base64.b64decode(value.encode("ascii"), validate=True)
        except (UnicodeEncodeError, ValueError) as error:
            raise RuntimeError(f"INVALID_PENDING_{name.upper()}") from error
        if base64.b64encode(payload).decode("ascii") != value:
            raise RuntimeError(f"INVALID_PENDING_{name.upper()}")
        length = pending.get(f"{name}_length")
        if not isinstance(length, int) or isinstance(length, bool) or length != len(payload) or pending.get(f"{name}_sha256") != _sha256(payload):
            raise RuntimeError(f"INVALID_PENDING_{name.upper()}")
        decoded[name] = payload
    if decoded["post"] != decoded["pre"] + decoded["append"]:
        raise RuntimeError("INVALID_PENDING_POST")
    return pending["state"], decoded["pre"], decoded["append"], decoded["post"]


def _recover_transaction():
    pending_path = _pending_path()
    if not pending_path.exists():
        return
    state, pre_bytes, append_bytes, post_bytes = _validated_pending()
    current = LESSONS_FILE.read_bytes() if LESSONS_FILE.exists() else b""
    if state == "prepared":
        if current == pre_bytes:
            _durable_replace(LESSONS_FILE, post_bytes)
        elif current != post_bytes:
            raise RuntimeError("PENDING_STORE_HASH_MISMATCH")
        _write_pending("store_committed", pre_bytes, append_bytes)
    elif current != post_bytes:
        raise RuntimeError("PENDING_STORE_HASH_MISMATCH")
    if (LESSONS_FILE.read_bytes() if LESSONS_FILE.exists() else b"") != post_bytes:
        raise RuntimeError("PENDING_STORE_HASH_MISMATCH")
    pending_path.unlink()
    _fsync_directory(pending_path.parent)


def extract_lessons():
    evidence = {
        "authorization": False, "command": "python scripts/extract_lessons.py", "exit_status": 1,
        "failure_code": None, "failure_detail": None, "gate": EVIDENCE_GATE,
        "lesson_store_path": LESSONS_FILE.relative_to(WORKSPACE).as_posix(), "lock_result": "not_acquired",
        "schema_version": EVIDENCE_SCHEMA_VERSION, "source_date_scope": "all audit reports",
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "append_bytes_length": 0, "append_sha256": _sha256(b""), "candidate_count": 0,
        "deduplicated_count": 0, "eligible_reports": 0, "malformed_count": 0,
        "persisted_count": 0, "post_bytes_length": 0, "post_sha256": None,
        "pre_bytes_length": 0, "pre_sha256": None, "prefix_verified": False, "source_reports": [],
    }
    lock = None
    try:
        if not AUDIT_DIR.exists():
            raise RuntimeError("AUDIT_DIRECTORY_MISSING")
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        lock = _lock_file(LESSONS_FILE.with_suffix(".jsonl.lock"), LOCK_TIMEOUT_SECONDS)
        evidence["lock_result"] = "acquired"
        _recover_transaction()
        snapshots = _snapshot_reports(_load_gates())
        evidence["source_reports"] = [{key: item[key] for key in ("path", "sha256", "gate", "verdict", "role_id", "role_name", "eligible")} for item in snapshots]
        eligible = [item for item in snapshots if item["eligible"]]
        evidence["eligible_reports"] = len(eligible)
        if not eligible:
            raise RuntimeError("NO_ELIGIBLE_AUDIT_EVIDENCE")
        pre_bytes = LESSONS_FILE.read_bytes() if LESSONS_FILE.exists() else b""
        existing = _load_existing_identities(pre_bytes)
        candidates, unique = [], set()
        for item in eligible:
            identity = (item["gate"], item["role_id"])
            if identity not in unique:
                unique.add(identity)
                fields = _extract_lesson_fields_with_llm(item["content"], item["gate"], item["role_name"])
                candidates.append({"gate": item["gate"], "role_id": item["role_id"], "role_name": item["role_name"], **fields, "audit_report_path": item["path"]})
        appended = [lesson for lesson in candidates if (lesson["gate"], lesson["role_id"]) not in existing]
        append_bytes = b"".join(_canonical_json(lesson) for lesson in appended)
        post_bytes = pre_bytes + append_bytes
        _write_pending("prepared", pre_bytes, append_bytes)
        _durable_replace(LESSONS_FILE, post_bytes)
        _write_pending("store_committed", pre_bytes, append_bytes)
        if LESSONS_FILE.read_bytes() != post_bytes:
            raise RuntimeError("APPEND_INTEGRITY_FAILURE")
        _pending_path().unlink()
        _fsync_directory(_pending_path().parent)
        evidence.update({"append_bytes_length": len(append_bytes), "append_sha256": _sha256(append_bytes), "candidate_count": len(candidates), "deduplicated_count": len(candidates) - len(appended), "persisted_count": len(appended), "post_bytes_length": len(post_bytes), "post_sha256": _sha256(post_bytes), "pre_bytes_length": len(pre_bytes), "pre_sha256": _sha256(pre_bytes), "prefix_verified": True, "authorization": True, "exit_status": 0})
        all_lessons = load_lessons()
        if all_lessons and chromadb is not None:
            try:
                _search_lessons_with_chromadb("refresh", all_lessons, 1)
            except Exception as error:
                print(f"Warning: failed to persist Chroma lessons index: {error}")
    except Exception as error:
        code = "LOCK_CONTENTION" if isinstance(error, TimeoutError) else str(error) if str(error).isupper() or str(error).startswith("MALFORMED_") else "EXTRACTION_FAILURE"
        evidence["failure_code"], evidence["failure_detail"] = code, str(error)
        if code.startswith("MALFORMED_LESSON_STORE:"):
            evidence["malformed_count"] = int(code.rsplit(":", 1)[1])
    finally:
        if lock is not None:
            _unlock_file(lock)
    try:
        evidence["evidence_path"] = _write_evidence(evidence)
    except Exception as error:
        print(f"EVIDENCE_WRITE_FAILURE: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"authorization": evidence["authorization"], "evidence_path": evidence["evidence_path"], "exit_status": evidence["exit_status"]}, sort_keys=True))
    return evidence["exit_status"]


if __name__ == "__main__":
    raise SystemExit(extract_lessons())
