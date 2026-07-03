import json
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
COLLECTION_NAME = "omega_lessons_search"
TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")

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
        
        # Parse fields using simple regex
        gate_match = re.search(r'\*\*Gate\*\*:\s*([A-Za-z0-9_]+)', content)
        verdict_match = re.search(r'## Verdict\s*\n+\s*\[(APPROVED|NEEDS_FIX|APPROVED_PARTIAL)\]', content)
        
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
