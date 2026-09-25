"""Unit tests for MacroLLMInterpreter."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import sqlite3
from pathlib import Path
import tempfile
import threading
import pytest
import pandas as pd

from omega.data.macro_llm import ALLOWED_REGIMES, ALLOWED_TRENDS, MacroLLMInterpreter, OUTPUT_COLUMNS
from omega.core.llm_config import classify_jev
from datetime import datetime, timezone
from types import SimpleNamespace
import sys


@pytest.fixture
def mock_indicators_file(tmp_path: Path) -> Path:
    data = [
        {"indicator": "cpi", "value": 3.5, "observation_date": "2026-01-01", "available_at": "2026-01-05T00:00:00Z", "ingested_at": "2026-01-05T00:00:00Z", "revision_id": "r1"},
        {"indicator": "gdp_growth", "value": 6.8, "observation_date": "2026-01-01", "available_at": "2026-01-10T00:00:00Z", "ingested_at": "2026-01-10T00:00:00Z", "revision_id": "r1"},
        {"indicator": "policy_rate", "value": 4.5, "observation_date": "2026-02-01", "available_at": "2026-02-05T00:00:00Z", "ingested_at": "2026-02-05T00:00:00Z", "revision_id": "r1"},
        # Future record relative to early 2026 as_of
        {"indicator": "cpi", "value": 4.0, "observation_date": "2026-06-01", "available_at": "2026-06-05T00:00:00Z", "ingested_at": "2026-06-05T00:00:00Z", "revision_id": "r1"},
    ]
    df = pd.DataFrame(data)
    file_path = tmp_path / "macro_indicators.parquet"
    df.to_parquet(file_path, index=False)
    return file_path


def test_macro_llm_interpreter_mock_and_schema(tmp_path: Path, mock_indicators_file: Path) -> None:
    output_path = tmp_path / "macro_llm_interpretation.parquet"
    interpreter = MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})

    # When as_of is None, it interprets as of now_utc without filtering out the current inference
    df = asyncio.run(
        interpreter.interpret_as_of(
            indicators_path=mock_indicators_file,
            output_path=output_path,
        )
    )

    assert output_path.exists()
    assert len(df) == 1
    assert list(df.columns) == OUTPUT_COLUMNS
    row = df.iloc[0]
    assert row["trend"] == "neutral"
    assert row["regime"] == "other"
    assert -1.0 <= row["macro_score"] <= 1.0
    assert row["model"] == "mock-model"
    assert row["prompt_version"] == "macro_llm_v1"
    assert row["response_sha256"]


def test_macro_llm_cache_hit_and_pit_boundary(tmp_path: Path, mock_indicators_file: Path) -> None:
    output_path = tmp_path / "macro_llm_interpretation.parquet"
    interpreter = MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})

    as_of = "2026-02-15T00:00:00Z"
    # First execution
    df1 = asyncio.run(
        interpreter.interpret_as_of(
            as_of=as_of,
            indicators_path=mock_indicators_file,
            output_path=output_path,
        )
    )
    # Output available_at is inference creation timestamp now_utc (> as_of), so interpret_as_of filtered at as_of returns 0 rows
    assert len(df1) == 0

    # Store contains the generated record with response_sha256
    df_store = pd.read_parquet(output_path)
    assert len(df_store) == 1
    ext_id1 = df_store.iloc[0]["extraction_id"]
    assert df_store.iloc[0]["response_sha256"]

    # Second execution (cache hit)
    df2 = asyncio.run(
        interpreter.interpret_as_of(
            as_of=as_of,
            indicators_path=mock_indicators_file,
            output_path=output_path,
        )
    )
    assert len(df2) == 0

    # Verify context built at as_of does not include future data (2026-06-01)
    df_raw = pd.read_parquet(mock_indicators_file)
    context = interpreter.build_context(df_raw, pd.to_datetime(as_of, utc=True))
    obs_dates = [r["observation_date"] for r in context["records"]]
    assert "2026-06-01" not in obs_dates


def test_macro_llm_reverse_as_of_filtering(tmp_path: Path, mock_indicators_file: Path) -> None:
    output_path = tmp_path / "macro_llm_interpretation.parquet"
    interpreter = MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})

    # 1. Run for date 1 (2026-06-10)
    asyncio.run(
        interpreter.interpret_as_of(
            as_of="2026-06-10T00:00:00Z",
            indicators_path=mock_indicators_file,
            output_path=output_path,
        )
    )

    # 2. Run for date 2 (2026-02-15)
    asyncio.run(
        interpreter.interpret_as_of(
            as_of="2026-02-15T00:00:00Z",
            indicators_path=mock_indicators_file,
            output_path=output_path,
        )
    )

    # Persisted parquet store should contain both (2 rows)
    df_store = pd.read_parquet(output_path)
    assert len(df_store) == 2

    # Query without generating new run (cache hit for 2026-06-10)
    df_cached = asyncio.run(
        interpreter.interpret_as_of(
            as_of="2026-06-10T00:00:00Z",
            indicators_path=mock_indicators_file,
            output_path=output_path,
        )
    )
    # Filtered by as_of="2026-06-10", but records have available_at = 2026-08-22 (now_utc)
    # so available_at <= as_of filters to 0
    assert len(df_cached) == 0
    assert len(pd.read_parquet(output_path)) == 2


def test_macro_llm_model_change_cache_isolation(tmp_path: Path, mock_indicators_file: Path) -> None:
    output_path = tmp_path / "macro_llm_interpretation.parquet"
    interpreter_a = MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "model-a"})
    interpreter_b = MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "model-b"})

    as_of = "2026-02-15T00:00:00Z"
    asyncio.run(interpreter_a.interpret_as_of(as_of=as_of, indicators_path=mock_indicators_file, output_path=output_path))
    asyncio.run(interpreter_b.interpret_as_of(as_of=as_of, indicators_path=mock_indicators_file, output_path=output_path))

    df_store = pd.read_parquet(output_path)
    assert len(df_store) == 2
    ext_id_a = df_store.loc[df_store["model"] == "model-a"].iloc[0]["extraction_id"]
    ext_id_b = df_store.loc[df_store["model"] == "model-b"].iloc[0]["extraction_id"]
    assert ext_id_a != ext_id_b


def test_macro_llm_fail_closed_on_invalid_schema_store(tmp_path: Path, mock_indicators_file: Path) -> None:
    output_path = tmp_path / "macro_llm_interpretation.parquet"
    # Store with missing columns
    df_invalid = pd.DataFrame([{"invalid_col": 123}])
    df_invalid.to_parquet(output_path, index=False)

    interpreter = MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})
    with pytest.raises(ValueError, match="invalid schema in macro LLM interpretation store"):
        asyncio.run(interpreter.interpret_as_of(as_of="2026-02-15T00:00:00Z", indicators_path=mock_indicators_file, output_path=output_path))


def test_macro_llm_concurrent_writers(tmp_path: Path, mock_indicators_file: Path) -> None:
    output_path = tmp_path / "macro_llm_interpretation.parquet"
    num_writers = 5
    barrier = threading.Barrier(num_writers)

    def run_single_writer(model_idx: int) -> None:
        interpreter = MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": f"model-{model_idx}"})
        orig_post = interpreter._post

        def _sync_post(body_bytes: bytes) -> dict:
            barrier.wait(timeout=10)
            return orig_post(body_bytes)

        interpreter._post = _sync_post
        asyncio.run(
            interpreter.interpret_as_of(
                as_of="2026-02-15T00:00:00Z",
                indicators_path=mock_indicators_file,
                output_path=output_path,
            )
        )

    with ThreadPoolExecutor(max_workers=num_writers) as executor:
        futures = [executor.submit(run_single_writer, i) for i in range(num_writers)]
        for f in futures:
            f.result()

    df_store = pd.read_parquet(output_path)
    assert len(df_store) == num_writers
    assert set(df_store["model"]) == {f"model-{i}" for i in range(num_writers)}
    assert list(df_store.columns) == OUTPUT_COLUMNS
    assert df_store["extraction_id"].nunique() == num_writers


def test_macro_llm_response_sha256_calculation(tmp_path: Path, mock_indicators_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_path = tmp_path / "macro_llm_interpretation.parquet"
    mock_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "trend": "easing",
                            "regime": "deflation",
                            "narrative": "Detailed monetary easing narrative test.",
                            "macro_score": 0.42,
                        }
                    )
                }
            }
        ]
    }
    expected_bytes = json.dumps(mock_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    expected_sha256 = hashlib.sha256(expected_bytes).hexdigest()

    interpreter = MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "sha-test-model"})
    monkeypatch.setattr(interpreter, "_post", lambda _: mock_payload)

    asyncio.run(
        interpreter.interpret_as_of(
            as_of="2026-02-15T00:00:00Z",
            indicators_path=mock_indicators_file,
            output_path=output_path,
        )
    )

    df_store = pd.read_parquet(output_path)
    assert len(df_store) == 1
    assert df_store.iloc[0]["response_sha256"] == expected_sha256
    assert df_store.iloc[0]["trend"] == "easing"
    assert df_store.iloc[0]["regime"] == "deflation"
    assert df_store.iloc[0]["macro_score"] == 0.42


def test_macro_llm_endpoint_isolation_cache(tmp_path: Path, mock_indicators_file: Path) -> None:
    output_path = tmp_path / "macro_llm_interpretation.parquet"
    interpreter_ep1 = MacroLLMInterpreter(
        repo_root=tmp_path,
        llm_config={"provider": "openai-compatible", "api_key": "k1", "base_url": "https://api1.example.com/v1", "model": "same-model"},
    )
    interpreter_ep2 = MacroLLMInterpreter(
        repo_root=tmp_path,
        llm_config={"provider": "openai-compatible", "api_key": "k2", "base_url": "https://api2.example.com/v1", "model": "same-model"},
    )

    mock_resp = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "trend": "neutral",
                            "regime": "other",
                            "narrative": "Mock narrative.",
                            "macro_score": 0.0,
                        }
                    )
                }
            }
        ]
    }
    interpreter_ep1._post = lambda _: mock_resp
    interpreter_ep2._post = lambda _: mock_resp

    as_of = "2026-02-15T00:00:00Z"
    asyncio.run(interpreter_ep1.interpret_as_of(as_of=as_of, indicators_path=mock_indicators_file, output_path=output_path))
    asyncio.run(interpreter_ep2.interpret_as_of(as_of=as_of, indicators_path=mock_indicators_file, output_path=output_path))

    df_store = pd.read_parquet(output_path)
    assert len(df_store) == 2
    ext_ids = df_store["extraction_id"].tolist()
    assert ext_ids[0] != ext_ids[1]


def test_macro_llm_revision_deduplication(tmp_path: Path) -> None:
    # Indicators with 2 revisions for the same indicator and observation_date
    data = [
        {"indicator": "cpi", "value": 3.0, "observation_date": "2026-01-01", "available_at": "2026-01-05T00:00:00Z", "ingested_at": "2026-01-05T00:00:00Z", "revision_id": "r1"},
        {"indicator": "cpi", "value": 3.2, "observation_date": "2026-01-01", "available_at": "2026-01-06T00:00:00Z", "ingested_at": "2026-01-06T00:00:00Z", "revision_id": "r2"},
    ]
    df = pd.DataFrame(data)
    file_path = tmp_path / "macro_rev.parquet"
    df.to_parquet(file_path, index=False)

    interpreter = MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})
    context = interpreter.build_context(df, pd.to_datetime("2026-01-10T00:00:00Z", utc=True))
    assert len(context["records"]) == 1
    assert context["records"][0]["value"] == 3.2  # Latest revision selected


def test_macro_llm_fail_closed_on_corrupt_store(tmp_path: Path, mock_indicators_file: Path) -> None:
    output_path = tmp_path / "macro_llm_interpretation.parquet"
    output_path.write_bytes(b"corrupted parquet file content")

    interpreter = MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})
    with pytest.raises(ValueError, match="corrupt macro LLM interpretation store"):
        asyncio.run(interpreter.interpret_as_of(as_of="2026-02-15T00:00:00Z", indicators_path=mock_indicators_file, output_path=output_path))


def test_macro_llm_post_retry_and_timeout_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    interpreter = MacroLLMInterpreter(
        repo_root=tmp_path,
        llm_config={"provider": "openai-compatible", "api_key": "test-key", "base_url": "https://api.example.com/v1", "model": "test-model"},
        timeout=15.0,
        max_retries=3,
        backoff_factor=0.01,
    )
    assert interpreter.timeout == 15.0
    assert interpreter.max_retries == 3
    assert interpreter.backoff_factor == 0.01

    call_count = 0
    captured_timeouts = []

    def mock_post(url, headers, data, timeout):
        nonlocal call_count
        call_count += 1
        captured_timeouts.append(timeout)
        if call_count < 3:
            resp = requests.Response()
            resp.status_code = 503
            resp._content = b"Service Unavailable"
            raise requests.exceptions.HTTPError("503 Server Error", response=resp)
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps({
            "choices": [{"message": {"content": json.dumps({"trend": "neutral", "regime": "other", "narrative": "ok", "macro_score": 0.0})}}]
        }).encode("utf-8")
        return resp

    monkeypatch.setattr(requests, "post", mock_post)
    res = interpreter._post(b"{}")
    assert call_count == 3
    assert captured_timeouts == [15.0, 15.0, 15.0]
    assert "choices" in res


def test_macro_llm_post_retry_exhaustion_on_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    interpreter = MacroLLMInterpreter(
        repo_root=tmp_path,
        llm_config={"provider": "openai-compatible", "api_key": "test-key", "base_url": "https://api.example.com/v1", "model": "test-model"},
        timeout=60.0,
        max_retries=3,
        backoff_factor=0.01,
    )
    call_count = 0

    def mock_post(url, headers, data, timeout):
        nonlocal call_count
        call_count += 1
        raise requests.exceptions.ReadTimeout("Read timed out")

    monkeypatch.setattr(requests, "post", mock_post)
    with pytest.raises(requests.exceptions.ReadTimeout):
        interpreter._post(b"{}")
    assert call_count == 3


def test_macro_jev_fault_injection_and_adapter(tmp_path: Path, mock_indicators_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class TimeoutError(Exception):
        pass

    calls = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["timeout"] == 10.0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def system_one(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise TimeoutError()
            return SimpleNamespace(choices={"regime": SimpleNamespace(choice="risk_on"), "trend": SimpleNamespace(choice="improving")})

    monkeypatch.setitem(sys.modules, "typesafe_sdk", SimpleNamespace(Choice=lambda **kw: kw, TypeSafeClient=Client,
        TypeSafeAPIConnectionError=TimeoutError, TypeSafeAPITimeoutError=TimeoutError, TypeSafeInternalServerError=TimeoutError))
    sleeps = []
    monkeypatch.setattr("omega.core.llm_config.time.sleep", sleeps.append)
    interpreter = MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "jev", "model": "jev-test"})
    output = tmp_path / "macro_jev.parquet"
    run = lambda: asyncio.run(interpreter.interpret_as_of(as_of="2026-06-10T00:00:00Z", indicators_path=mock_indicators_file, output_path=output))
    run()
    assert pd.read_parquet(output).iloc[0]["macro_score"] == 1.0
    assert sleeps == [2.0] and len(calls) == 2
    run()
    assert len(pd.read_parquet(output)) == 1
    assert len(calls) == 2
    with pytest.raises(ValueError, match="source not available"):
        classify_jev(domain="macro", facts={}, choices={"regime": ("neutral",)}, cache_path=tmp_path / "bad.sqlite",
                     as_of=datetime(2026, 1, 1, tzinfo=timezone.utc), available_at=datetime(2026, 1, 2, tzinfo=timezone.utc), model="jev-test")


@pytest.mark.parametrize("regime,trend", [("risk_on", "improving"), ("neutral", "stable"), ("risk_off", "deteriorating")])
def test_macro_jev_labels_conform_to_declared_contract(tmp_path: Path, mock_indicators_file: Path, monkeypatch: pytest.MonkeyPatch, regime: str, trend: str) -> None:
    monkeypatch.setattr("omega.data.macro_llm.classify_jev", lambda **kw: {"fingerprint": regime, "selected": {"regime": regime, "trend": trend}, "decided_at": datetime.now(timezone.utc).isoformat()})
    output = tmp_path / "jev-labels.parquet"
    result = asyncio.run(MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "jev"}).interpret_as_of(indicators_path=mock_indicators_file, output_path=output))
    for row in (result.iloc[0], pd.read_parquet(output).iloc[0]):
        assert row["regime"] == regime and row["regime"] in ALLOWED_REGIMES
        assert row["trend"] == trend and row["trend"] in ALLOWED_TRENDS


@pytest.mark.parametrize("labels", [{"regime": "other", "trend": "stable"}, {"regime": "risk_on", "trend": "easing"}, {"regime": True, "trend": "stable"}, {"regime": "risk_on"}])
def test_macro_jev_rejects_invalid_labels(tmp_path: Path, mock_indicators_file: Path, monkeypatch: pytest.MonkeyPatch, labels: dict) -> None:
    monkeypatch.setattr("omega.data.macro_llm.classify_jev", lambda **kw: {"fingerprint": "invalid", "selected": labels, "decided_at": datetime.now(timezone.utc).isoformat()})
    output = tmp_path / "invalid-labels.parquet"
    with pytest.raises(ValueError, match="invalid JEV macro labels"):
        asyncio.run(MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "jev"}).interpret_as_of(indicators_path=mock_indicators_file, output_path=output))
    assert not output.exists()


def test_macro_jev_rejects_corrupt_store(tmp_path: Path, mock_indicators_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("omega.data.macro_llm.classify_jev", lambda **kw: {"fingerprint": "x", "selected": {"regime": "neutral", "trend": "stable"}, "decided_at": datetime.now(timezone.utc).isoformat()})
    output = tmp_path / "corrupt.parquet"
    output.write_bytes(b"corrupt")
    with pytest.raises(Exception):
        asyncio.run(MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "jev"}).interpret_as_of(indicators_path=mock_indicators_file, output_path=output))
    assert output.read_bytes() == b"corrupt"


@pytest.mark.parametrize("provider", ["mock", "jev"])
def test_macro_extra_store_columns_removed(tmp_path: Path, mock_indicators_file: Path, monkeypatch: pytest.MonkeyPatch, provider: str) -> None:
    output = tmp_path / "extra.parquet"
    pd.DataFrame(columns=OUTPUT_COLUMNS + ["injected"]).to_parquet(output)
    if provider == "jev":
        monkeypatch.setattr("omega.data.macro_llm.classify_jev", lambda **kw: {"fingerprint": "x", "selected": {"regime": "neutral", "trend": "stable"}, "decided_at": datetime.now(timezone.utc).isoformat()})
    result = asyncio.run(MacroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": provider}).interpret_as_of(indicators_path=mock_indicators_file, output_path=output))
    assert list(result.columns) == list(pd.read_parquet(output).columns) == OUTPUT_COLUMNS


@pytest.mark.parametrize("field,value", [
    ("version", True), ("domain", "micro"), ("as_of", "2026-01-04T00:00:00+00:00"),
    ("available_at", "2026-01-03T00:00:00+00:00"), ("model", "other"),
    ("attempts", 0), ("attempts", 3), ("attempts", True), ("decided_at", "not-a-date"),
    ("decided_at", "2026-01-01T00:00:00"),
    ("decided_at", "2025-12-31T00:00:00+00:00"),
    ("choices", ["neutral"]), ("selected", []), ("available_at", None),
])
def test_macro_jev_rejects_tampered_cache_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: object) -> None:
    from omega.core import llm_config

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def system_one(self, **kwargs):
            return SimpleNamespace(choices={"regime": SimpleNamespace(choice="neutral")})

    monkeypatch.setitem(sys.modules, "typesafe_sdk", SimpleNamespace(Choice=lambda **kw: kw, TypeSafeClient=Client,
        TypeSafeAPIConnectionError=OSError, TypeSafeAPITimeoutError=TimeoutError, TypeSafeInternalServerError=RuntimeError))
    cache = tmp_path / "jev.sqlite"
    kwargs = dict(domain="macro", facts={}, choices={"regime": ("neutral",)}, cache_path=cache,
                  as_of=datetime(2026, 1, 2, tzinfo=timezone.utc), available_at=datetime(2026, 1, 1, tzinfo=timezone.utc), model="jev-test")
    llm_config.classify_jev(**kwargs)
    with sqlite3.connect(cache) as db:
        fingerprint, raw = db.execute("SELECT fingerprint, envelope FROM decisions").fetchone()
        envelope = json.loads(raw)
        envelope[field] = value
        db.execute("UPDATE decisions SET envelope=? WHERE fingerprint=?", (json.dumps(envelope), fingerprint))
    with pytest.raises(ValueError, match="invalid JEV cache envelope"):
        llm_config.classify_jev(**kwargs)
