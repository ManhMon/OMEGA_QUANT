import json
import os
import re
from collections import Counter
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
LLM_CONFIG_FILE = WORKSPACE / "llm" / "llm.jsonl"
COLLECTION_NAME = "omega_lessons_search"
TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")
GATE_RE = re.compile(r'\*\*Gate\*\*:\s*([A-Za-z0-9_]+)')
VERDICT_RE = re.compile(r'## Verdict\s*\n+\s*\[(APPROVED|NEEDS_FIX|APPROVED_PARTIAL)\]')
JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
OPENAI_BASE_URL = "https://api.openai.com/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_OPENROUTER_MODEL = "free"

ROLE_MAP = {
    6: "system-architect", 7: "tech-lead", 8: "frontend-engineer",
    9: "backend-engineer", 10: "database-admin", 11: "devops-engineer",
    12: "cloud-infra-engineer", 13: "ui-ux-integrator", 14: "data-scientist",
    15: "data-engineer", 16: "machine-learning-engineer"
}


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
        file_config = _resolve_lesson_llm_config_file()
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        file_config = None
    if file_config is not None:
        env_config = _resolve_lesson_llm_env_config()
        api_key = file_config.get("api_key") or (env_config or {}).get("api_key")
        if not api_key:
            return env_config
        return {
            "api_key": api_key,
            "base_url": file_config.get("base_url") or (env_config or {}).get("base_url") or OPENAI_BASE_URL,
            "model": file_config.get("model") or (env_config or {}).get("model") or DEFAULT_OPENAI_MODEL,
        }

    return _resolve_lesson_llm_env_config()


def _resolve_lesson_llm_config_file(config_file=None):
    config_path = Path(config_file or LLM_CONFIG_FILE)
    if not config_path.exists():
        return None

    lines = config_path.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        config = json.loads(line)
        return {
            "api_key": config.get("api_key"),
            "base_url": str(config["base_url"]).rstrip("/") if config.get("base_url") else None,
            "model": config.get("model"),
        }
    return None


def _resolve_lesson_llm_env_config():
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key:
        return {
            "api_key": openai_api_key,
            "base_url": os.getenv("OPENAI_BASE_URL", OPENAI_BASE_URL).rstrip("/"),
            "model": os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        }

    omega_api_key = os.getenv("OMEGA_LLM_API_KEY")
    if omega_api_key:
        return {
            "api_key": omega_api_key,
            "base_url": os.getenv("OMEGA_LLM_BASE_URL", OPENROUTER_BASE_URL).rstrip("/"),
            "model": os.getenv("OMEGA_LLM_MODEL", DEFAULT_OPENROUTER_MODEL),
        }

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if gemini_api_key:
        return {
            "api_key": gemini_api_key,
            "base_url": os.getenv("GEMINI_BASE_URL", GEMINI_BASE_URL).rstrip("/"),
            "model": os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        }

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


def _extract_lesson_fields_with_llm(content, gate, role_name):
    config = _resolve_lesson_llm_config()
    if config is None:
        return _fallback_lesson_fields(content, gate, role_name)

    try:
        import requests
    except ImportError:
        return _fallback_lesson_fields(content, gate, role_name)

    prompt = (
        "Extract lessons learned from this L3 audit report. "
        "Return JSON only with keys symptom, root_cause, fix_pattern. "
        "Each value must be a concise plain string. "
        "Do not wrap the JSON in markdown.\n\n"
        f"Gate: {gate}\n"
        f"Role: {role_name}\n\n"
        "Audit report markdown:\n"
        f"{content}"
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
        data = response.json()
        message = data["choices"][0]["message"]["content"]
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

def extract_lessons():
    print("Extracting lessons from audit reports...")
    
    if not AUDIT_DIR.exists():
        print("Audit reports directory does not exist.")
        return 0
        
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load phase_gates.json to cross-reference gate metadata
    gates_path = WORKSPACE / ".ly_state" / "session" / "phase_gates.json"
    gates_dict = {}
    if gates_path.exists():
        try:
            with open(gates_path, encoding='utf-8') as f:
                gates_dict = json.load(f)
        except Exception as e:
            print(f"Warning: failed to load phase_gates.json: {e}")
            
    # Let's read all audit reports
    lessons = []
    
    # Build list of reports and group them by gate base name
    reports = list(AUDIT_DIR.glob("*.md"))
    reports.sort(key=lambda x: x.stat().st_mtime) # Sort by modification time
    
    for r_file in reports:
        content = r_file.read_text(encoding='utf-8')
        
        gate_match = GATE_RE.search(content)
        verdict_match = VERDICT_RE.search(content)
        
        if not gate_match or not verdict_match:
            continue
            
        gate = gate_match.group(1)
        verdict = verdict_match.group(1)
        
        # Try to resolve L2 role ID and Name
        role_id = 0
        role_name = "unknown"
        
        gate_data = gates_dict.get(gate, {})
        l2_role_id = gate_data.get("l2_role_id")
        l2_role_name = gate_data.get("l2_role_name")
        
        if l2_role_id is not None:
            role_id = int(l2_role_id)
            role_name = l2_role_name
        else:
            # Fallback to extracting from l2_session_id or l2_role pattern in content
            session_match = re.search(r'l2_role(\d+)', content)
            if session_match:
                role_id = int(session_match.group(1))
                role_name = ROLE_MAP.get(role_id, "unknown")
            else:
                # Try parsing raw L2 Role text
                l2_role_match = re.search(r'\*\*L2 Role\*\*:\s*([A-Za-z0-9_\-\s\(\),]+)', content, re.IGNORECASE)
                if l2_role_match:
                    nums = re.findall(r'\d+', l2_role_match.group(1))
                    if nums:
                        role_id = int(nums[0])
                        role_name = ROLE_MAP.get(role_id, "unknown")
        
        if verdict == "NEEDS_FIX":
            lesson_fields = _extract_lesson_fields_with_llm(content, gate, role_name)

            lesson = {
                "timestamp": r_file.stat().st_mtime,
                "gate": gate,
                "role_id": role_id,
                "role_name": role_name,
                "symptom": lesson_fields["symptom"],
                "root_cause": lesson_fields["root_cause"],
                "fix_pattern": lesson_fields["fix_pattern"],
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

    all_lessons = load_lessons()
    if all_lessons and chromadb is not None:
        try:
            _search_lessons_with_chromadb("refresh", all_lessons, 1)
        except Exception as error:
            print(f"Warning: failed to persist Chroma lessons index: {error}")
                 
    print(f"Successfully extracted {count} new lessons to {LESSONS_FILE}")
    return count

if __name__ == "__main__":
    extract_lessons()
