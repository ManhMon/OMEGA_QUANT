import json
import sys
from pathlib import Path

import requests


SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import extract_lessons


LESSON = {
    "symptom": "SSE response was not parsed.",
    "root_cause": "The completion body used streamed delta events.",
    "fix_pattern": "Concatenate delta content before parsing lesson JSON.",
}


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


def extract_fields(monkeypatch, response_text):
    monkeypatch.setattr(
        extract_lessons,
        "_resolve_lesson_llm_config",
        lambda: {"api_key": "test-key", "base_url": "http://127.0.0.1:9999/v1", "model": "test-model"},
    )
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: FakeResponse(response_text))
    return extract_lessons._extract_lesson_fields_with_llm("report", "SSE_GATE", "devops-engineer")


def test_lesson_extractor_preserves_normal_json_completion(monkeypatch):
    response = json.dumps({"choices": [{"message": {"content": json.dumps(LESSON)}}]})
    assert extract_fields(monkeypatch, response) == LESSON


def test_lesson_extractor_reconstructs_observed_sse_chunks(monkeypatch):
    content = json.dumps(LESSON)
    chunks = [content[:31], content[31:72], content[72:]]
    response = "\n".join(
        f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}" for chunk in chunks
    )
    assert extract_fields(monkeypatch, response) == LESSON


def test_lesson_extractor_ignores_sse_terminal_done(monkeypatch):
    response = "\n".join(
        (
            f"data: {json.dumps({'choices': [{'delta': {'role': 'assistant'}}]})}",
            f"data: {json.dumps({'choices': [{'delta': {'content': json.dumps(LESSON)}}]})}",
            "data: [DONE]",
        )
    )
    assert extract_fields(monkeypatch, response) == LESSON


def test_lesson_extractor_ignores_sse_usage_trailer(monkeypatch):
    content = json.dumps(LESSON)
    response = "\n".join(
        (
            f"data: {json.dumps({'choices': [{'delta': {'content': content[:42]}}]})}",
            f"data: {json.dumps({'choices': [{'delta': {'content': content[42:]}}]})}",
            f"data: {json.dumps({'choices': [], 'usage': {'total_tokens': 42}})}",
            "data: [DONE]",
        )
    )
    assert extract_fields(monkeypatch, response) == LESSON


def test_lesson_extractor_falls_back_for_malformed_or_empty_sse(monkeypatch):
    fallback = {
        "symptom": "Audit gate 'SSE_GATE' failed for role 'devops-engineer'.",
        "root_cause": "report",
        "fix_pattern": "Review the audit report markdown and apply the required fix before rerunning the gate.",
    }
    for response in ("data: {bad json}", "data: [DONE]", ""):
        assert extract_fields(monkeypatch, response) == fallback
