"""Unit tests for MicroLLMInterpreter."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from pathlib import Path
import threading
import pytest
import pandas as pd

from omega.data.micro_llm import MicroLLMInterpreter, OUTPUT_COLUMNS
from omega.core.llm_config import classify_jev
from types import SimpleNamespace
import sys


def test_micro_jev_rejects_invalid_cache_and_insert_race(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def system_one(self, **kwargs):
            return SimpleNamespace(choices={"quality": SimpleNamespace(choice="strong")})

    monkeypatch.setitem(sys.modules, "typesafe_sdk", SimpleNamespace(Choice=lambda **kw: kw, TypeSafeClient=Client,
        TypeSafeAPIConnectionError=OSError, TypeSafeAPITimeoutError=TimeoutError, TypeSafeInternalServerError=RuntimeError))
    cache = tmp_path / "micro.sqlite"
    kwargs = dict(domain="micro", facts={}, choices={"quality": ("strong",)}, cache_path=cache,
                  as_of=datetime(2026, 5, 1, tzinfo=timezone.utc), available_at=datetime(2026, 4, 1, tzinfo=timezone.utc), model="jev-test")
    classify_jev(**kwargs)
    with sqlite3.connect(cache) as db:
        fingerprint, raw = db.execute("SELECT fingerprint, envelope FROM decisions").fetchone()
        envelope = json.loads(raw)
        envelope["available_at"] = "2026-05-02T00:00:00+00:00"
        db.execute("UPDATE decisions SET envelope=? WHERE fingerprint=?", (json.dumps(envelope), fingerprint))
    with pytest.raises(ValueError, match="invalid JEV cache envelope"):
        classify_jev(**kwargs)
    original_connect = sqlite3.connect

    class RaceConnection:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def execute(self, sql, params=()):
            if sql.startswith("SELECT envelope FROM decisions WHERE fingerprint"):
                return self.connection.execute("SELECT envelope FROM decisions WHERE fingerprint=?", params)
            return self.connection.execute(sql, params)

    # Mo phong hang bi chen truoc INSERT OR IGNORE: duong doc sau ghi van phai chan.
    with original_connect(cache) as db:
        db.execute("DELETE FROM decisions")
    count = 0

    def connect(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            with original_connect(cache) as db:
                envelope["available_at"] = "2026-05-02T00:00:00+00:00"
                db.execute("INSERT INTO decisions VALUES (?, ?)", (fingerprint, json.dumps(envelope)))
        return RaceConnection(original_connect(*args, **kwargs))

    monkeypatch.setattr("omega.core.llm_config.sqlite3.connect", connect)
    with pytest.raises(ValueError, match="invalid JEV cache envelope"):
        classify_jev(**kwargs)


@pytest.fixture
def mock_financial_statements_file(tmp_path: Path) -> Path:
    data = [
        # VCB Q1 2026
        {
            "symbol": "VCB",
            "endpoint": "income_statement",
            "period_type": "quarter",
            "fiscal_year": 2026,
            "fiscal_quarter": 1,
            "item_code": "NET_PROFIT",
            "item_value": 10000.0,
            "fiscal_period_end": "2026-03-31",
            "source_publish_at": "2026-04-15T00:00:00Z",
            "available_at": "2026-04-16T00:00:00Z",
            "ingested_at": "2026-04-16T00:00:00Z",
        },
        {
            "symbol": "VCB",
            "endpoint": "cash_flow",
            "period_type": "quarter",
            "fiscal_year": 2026,
            "fiscal_quarter": 1,
            "item_code": "OPERATING_CASH_FLOW",
            "item_value": 8500.0,
            "fiscal_period_end": "2026-03-31",
            "source_publish_at": "2026-04-15T00:00:00Z",
            "available_at": "2026-04-18T00:00:00Z",
            "ingested_at": "2026-04-18T00:00:00Z",
        },
        {
            "symbol": "VCB",
            "endpoint": "ratios",
            "period_type": "quarter",
            "fiscal_year": 2026,
            "fiscal_quarter": 1,
            "item_code": "ROE",
            "item_value": 0.22,
            "fiscal_period_end": "2026-03-31",
            "source_publish_at": "2026-04-15T00:00:00Z",
            "available_at": "2026-04-16T00:00:00Z",
            "ingested_at": "2026-04-16T00:00:00Z",
        },
        # VNM Q1 2026 (later available_at)
        {
            "symbol": "VNM",
            "endpoint": "income_statement",
            "period_type": "quarter",
            "fiscal_year": 2026,
            "fiscal_quarter": 1,
            "item_code": "NET_PROFIT",
            "item_value": 2500.0,
            "fiscal_period_end": "2026-03-31",
            "source_publish_at": "2026-05-01T00:00:00Z",
            "available_at": "2026-05-02T00:00:00Z",
            "ingested_at": "2026-05-02T00:00:00Z",
        },
    ]
    df = pd.DataFrame(data)
    file_path = tmp_path / "financial_statements_mock.parquet"
    df.to_parquet(file_path, index=False)
    return file_path


def test_micro_jev_fault_injection_and_adapter(tmp_path: Path, mock_financial_statements_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class ConnectionError(Exception):
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
                raise ConnectionError()
            return SimpleNamespace(choices={k: SimpleNamespace(choice=v) for k, v in
                {"quality": "strong", "growth": "high", "cash": "positive"}.items()})

    monkeypatch.setitem(sys.modules, "typesafe_sdk", SimpleNamespace(Choice=lambda **kw: kw, TypeSafeClient=Client,
        TypeSafeAPIConnectionError=ConnectionError, TypeSafeAPITimeoutError=ConnectionError, TypeSafeInternalServerError=ConnectionError))
    sleeps = []
    monkeypatch.setattr("omega.core.llm_config.time.sleep", sleeps.append)
    output = tmp_path / "micro_jev.parquet"
    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "jev", "model": "jev-test"})
    run = lambda: asyncio.run(interpreter.interpret(as_of="2030-01-01T00:00:00Z", symbol="VCB", financial_statements_path=mock_financial_statements_file, output_path=output))
    row = run().iloc[0]
    assert (row["growth_signal"], row["cash_signal"], row["micro_score"]) == (1.0, 1.0, 1.0)
    assert sleeps == [2.0] and len(calls) == 2
    assert len(run()) == len(pd.read_parquet(output)) == 1
    assert len(calls) == 2


@pytest.mark.parametrize("provider", ["mock", "jev"])
@pytest.mark.parametrize("quarter", [5, 1.5, True])
def test_micro_rejects_invalid_quarter(tmp_path: Path, mock_financial_statements_file: Path, provider: str, quarter: object) -> None:
    source = pd.read_parquet(mock_financial_statements_file)
    source["fiscal_quarter"] = quarter
    source.to_parquet(mock_financial_statements_file, index=False)
    output = tmp_path / "invalid-quarter.parquet"
    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": provider})
    with pytest.raises(ValueError, match="fiscal_quarter must be an integer"):
        asyncio.run(interpreter.interpret(financial_statements_path=mock_financial_statements_file, output_path=output))
    assert not output.exists()


@pytest.mark.parametrize("provider", ["mock", "jev"])
@pytest.mark.parametrize("year", [2026.5, True, "2026", "bad", 1899, 2101, None])
def test_micro_rejects_invalid_year(tmp_path: Path, mock_financial_statements_file: Path, provider: str, year: object) -> None:
    source = pd.read_parquet(mock_financial_statements_file)
    source["fiscal_year"] = pd.Series([year] * len(source), dtype=object)
    source.to_parquet(mock_financial_statements_file, index=False)
    output = tmp_path / "invalid-year.parquet"
    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": provider})
    with pytest.raises(ValueError, match="fiscal_year must be an integer in 1900..2100"):
        asyncio.run(interpreter.interpret(financial_statements_path=mock_financial_statements_file, output_path=output))
    assert not output.exists()


@pytest.mark.parametrize("provider", ["mock", "jev"])
def test_micro_extra_store_columns_removed(tmp_path: Path, mock_financial_statements_file: Path, monkeypatch: pytest.MonkeyPatch, provider: str) -> None:
    output = tmp_path / "extra.parquet"
    pd.DataFrame(columns=OUTPUT_COLUMNS + ["injected"]).to_parquet(output)
    if provider == "jev":
        monkeypatch.setattr("omega.data.micro_llm.classify_jev", lambda **kw: {"fingerprint": "x", "selected": {"quality": "neutral", "growth": "low", "cash": "neutral"}, "decided_at": datetime.now(timezone.utc).isoformat()})
    result = asyncio.run(MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": provider}).interpret(financial_statements_path=mock_financial_statements_file, output_path=output))
    assert list(result.columns) == list(pd.read_parquet(output).columns) == OUTPUT_COLUMNS


def test_micro_llm_interpreter_mock_and_schema(tmp_path: Path, mock_financial_statements_file: Path) -> None:
    output_path = tmp_path / "micro_llm_interpretation.parquet"
    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})

    df = asyncio.run(
        interpreter.interpret(
            financial_statements_path=mock_financial_statements_file,
            output_path=output_path,
        )
    )

    assert output_path.exists()
    assert len(df) == 2  # VCB and VNM
    assert list(df.columns) == OUTPUT_COLUMNS

    vcb_row = df.loc[df["symbol"] == "VCB"].iloc[0]
    assert vcb_row["quality"] == "neutral"
    assert -1.0 <= vcb_row["growth_signal"] <= 1.0
    assert -1.0 <= vcb_row["cash_signal"] <= 1.0
    assert -1.0 <= vcb_row["micro_score"] <= 1.0
    assert vcb_row["fiscal_year"] == 2026
    assert vcb_row["fiscal_quarter"] == 1
    assert vcb_row["period_type"] == "quarter"
    assert vcb_row["prompt_version"] == "micro_llm_v1"
    assert vcb_row["response_sha256"]


def test_micro_llm_pit_available_at_and_cache_idempotency(tmp_path: Path, mock_financial_statements_file: Path) -> None:
    output_path = tmp_path / "micro_llm_interpretation.parquet"
    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})

    # 1. Test PIT filtering: as_of = 2026-04-20 -> VCB is available in source, but generated inference available_at is now_utc (> 2026-04-20)
    # When filtering returned df at as_of, 0 rows match because available_at <= as_of_ts
    df_as_of = asyncio.run(
        interpreter.interpret(
            as_of="2026-04-20T00:00:00Z",
            financial_statements_path=mock_financial_statements_file,
            output_path=output_path,
        )
    )
    assert len(df_as_of) == 0

    # Store contains VCB row
    df_store = pd.read_parquet(output_path)
    assert len(df_store) == 1
    assert df_store.iloc[0]["symbol"] == "VCB"
    ext_id_vcb = df_store.iloc[0]["extraction_id"]

    # 2. Test cache idempotency: running again should not duplicate rows
    df_cached = asyncio.run(
        interpreter.interpret(
            as_of="2026-04-20T00:00:00Z",
            financial_statements_path=mock_financial_statements_file,
            output_path=output_path,
        )
    )
    assert len(df_cached) == 0
    df_store_2 = pd.read_parquet(output_path)
    assert len(df_store_2) == 1
    assert df_store_2.iloc[0]["extraction_id"] == ext_id_vcb

    # 3. Expanding source as_of to include VNM
    df_all = asyncio.run(
        interpreter.interpret(
            as_of="2026-05-10T00:00:00Z",
            financial_statements_path=mock_financial_statements_file,
            output_path=output_path,
        )
    )
    assert len(df_all) == 0
    df_store_all = pd.read_parquet(output_path)
    assert len(df_store_all) == 2
    symbols = set(df_store_all["symbol"])
    assert symbols == {"VCB", "VNM"}


def test_micro_llm_reverse_as_of_filtering(tmp_path: Path, mock_financial_statements_file: Path) -> None:
    output_path = tmp_path / "micro_llm_interpretation.parquet"
    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})

    # 1. Run for later date (2026-05-10) -> generates interpretations for both VCB and VNM
    asyncio.run(
        interpreter.interpret(
            as_of="2026-05-10T00:00:00Z",
            financial_statements_path=mock_financial_statements_file,
            output_path=output_path,
        )
    )
    df_store = pd.read_parquet(output_path)
    assert len(df_store) == 2

    # 2. Run for future as_of -> should return all records
    df_future = asyncio.run(
        interpreter.interpret(
            as_of="2030-01-01T00:00:00Z",
            financial_statements_path=mock_financial_statements_file,
            output_path=output_path,
        )
    )
    assert len(df_future) == 2


def test_micro_llm_model_change_cache_isolation(tmp_path: Path, mock_financial_statements_file: Path) -> None:
    output_path = tmp_path / "micro_llm_interpretation.parquet"
    interpreter_a = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "model-a"})
    interpreter_b = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "model-b"})

    as_of = "2026-04-20T00:00:00Z"
    asyncio.run(interpreter_a.interpret(as_of=as_of, financial_statements_path=mock_financial_statements_file, output_path=output_path))
    asyncio.run(interpreter_b.interpret(as_of=as_of, financial_statements_path=mock_financial_statements_file, output_path=output_path))

    df_store = pd.read_parquet(output_path)
    assert len(df_store) == 2
    ext_id_a = df_store.loc[df_store["model"] == "model-a"].iloc[0]["extraction_id"]
    ext_id_b = df_store.loc[df_store["model"] == "model-b"].iloc[0]["extraction_id"]
    assert ext_id_a != ext_id_b


def test_micro_llm_revision_deduplication(tmp_path: Path) -> None:
    data = [
        {
            "symbol": "VCB",
            "endpoint": "income_statement",
            "period_type": "quarter",
            "fiscal_year": 2026,
            "fiscal_quarter": 1,
            "item_code": "NET_PROFIT",
            "item_value": 10000.0,
            "fiscal_period_end": "2026-03-31",
            "source_publish_at": "2026-04-15T00:00:00Z",
            "available_at": "2026-04-16T00:00:00Z",
            "ingested_at": "2026-04-16T00:00:00Z",
            "revision_id": "r1",
        },
        {
            "symbol": "VCB",
            "endpoint": "income_statement",
            "period_type": "quarter",
            "fiscal_year": 2026,
            "fiscal_quarter": 1,
            "item_code": "NET_PROFIT",
            "item_value": 12000.0,
            "fiscal_period_end": "2026-03-31",
            "source_publish_at": "2026-04-20T00:00:00Z",
            "available_at": "2026-04-21T00:00:00Z",
            "ingested_at": "2026-04-21T00:00:00Z",
            "revision_id": "r2",
        },
    ]
    df = pd.DataFrame(data)
    fs_file = tmp_path / "financial_statements_rev.parquet"
    df.to_parquet(fs_file, index=False)
    output_path = tmp_path / "micro_llm_interpretation.parquet"

    captured_requests = []
    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})
    orig_post = interpreter._post

    def _intercept_post(body_bytes: bytes) -> dict:
        payload = json.loads(body_bytes.decode("utf-8"))
        captured_requests.append(payload)
        return orig_post(body_bytes)

    interpreter._post = _intercept_post

    asyncio.run(
        interpreter.interpret(
            as_of="2026-04-25T00:00:00Z",
            financial_statements_path=fs_file,
            output_path=output_path,
        )
    )
    df_store = pd.read_parquet(output_path)
    assert len(df_store) == 1
    assert df_store.iloc[0]["symbol"] == "VCB"

    # Explicitly inspect captured request payload (H-01)
    assert len(captured_requests) == 1
    user_msg_content = json.loads(captured_requests[0]["messages"][1]["content"])
    financials = user_msg_content["financials"]
    net_profit = financials["income_statement"]["NET_PROFIT"]
    assert net_profit == 12000.0
    assert net_profit != 10000.0
    assert "12000.0" in captured_requests[0]["messages"][1]["content"]
    assert "10000.0" not in captured_requests[0]["messages"][1]["content"]


def test_micro_llm_strictly_requires_ingested_and_available(tmp_path: Path) -> None:
    # Missing ingested_at or available_at
    data_missing_col = pd.DataFrame([
        {
            "symbol": "VCB",
            "endpoint": "income_statement",
            "period_type": "quarter",
            "fiscal_year": 2026,
            "fiscal_quarter": 1,
            "item_code": "NET_PROFIT",
            "item_value": 10000.0,
            "available_at": "2026-04-16T00:00:00Z",
        }
    ])
    f_missing_col = tmp_path / "fs_missing_col.parquet"
    data_missing_col.to_parquet(f_missing_col, index=False)

    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})
    with pytest.raises(ValueError, match="financial statements must contain PIT available_at and ingested_at columns"):
        asyncio.run(interpreter.interpret(financial_statements_path=f_missing_col, output_path=tmp_path / "out.parquet"))

    # Null value in ingested_at
    data_null = pd.DataFrame([
        {
            "symbol": "VCB",
            "endpoint": "income_statement",
            "period_type": "quarter",
            "fiscal_year": 2026,
            "fiscal_quarter": 1,
            "item_code": "NET_PROFIT",
            "item_value": 10000.0,
            "available_at": "2026-04-16T00:00:00Z",
            "ingested_at": None,
        }
    ])
    f_null = tmp_path / "fs_null.parquet"
    data_null.to_parquet(f_null, index=False)
    with pytest.raises(ValueError, match="invalid or missing available_at/ingested_at timestamps"):
        asyncio.run(interpreter.interpret(financial_statements_path=f_null, output_path=tmp_path / "out2.parquet"))


def test_micro_llm_fail_closed_on_invalid_schema_store(tmp_path: Path, mock_financial_statements_file: Path) -> None:
    output_path = tmp_path / "micro_llm_interpretation.parquet"
    df_invalid = pd.DataFrame([{"invalid_col": 123}])
    df_invalid.to_parquet(output_path, index=False)

    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})
    with pytest.raises(ValueError, match="invalid schema in micro LLM interpretation store"):
        asyncio.run(
            interpreter.interpret(
                as_of="2026-04-20T00:00:00Z",
                financial_statements_path=mock_financial_statements_file,
                output_path=output_path,
            )
        )


def test_micro_llm_concurrent_writers(tmp_path: Path, mock_financial_statements_file: Path) -> None:
    output_path = tmp_path / "micro_llm_interpretation.parquet"
    num_writers = 4
    barrier = threading.Barrier(num_writers)

    def run_single_writer(model_idx: int) -> None:
        interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": f"model-{model_idx}"})
        orig_post = interpreter._post

        def _sync_post(body_bytes: bytes) -> dict:
            barrier.wait(timeout=10)
            return orig_post(body_bytes)

        interpreter._post = _sync_post
        asyncio.run(
            interpreter.interpret(
                as_of="2026-04-20T00:00:00Z",
                financial_statements_path=mock_financial_statements_file,
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


def test_micro_llm_response_sha256_calculation(tmp_path: Path, mock_financial_statements_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_path = tmp_path / "micro_llm_interpretation.parquet"
    mock_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "quality": "strong",
                            "growth_signal": 0.85,
                            "cash_signal": 0.65,
                            "narrative": "Fundamental quality verification narrative test.",
                            "micro_score": 0.75,
                        }
                    )
                }
            }
        ]
    }
    expected_bytes = json.dumps(mock_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    expected_sha256 = hashlib.sha256(expected_bytes).hexdigest()

    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "sha-test-model"})
    monkeypatch.setattr(interpreter, "_post", lambda _: mock_payload)

    asyncio.run(
        interpreter.interpret(
            as_of="2026-04-20T00:00:00Z",
            financial_statements_path=mock_financial_statements_file,
            output_path=output_path,
        )
    )

    df_store = pd.read_parquet(output_path)
    assert len(df_store) == 1
    assert df_store.iloc[0]["response_sha256"] == expected_sha256
    assert df_store.iloc[0]["quality"] == "strong"
    assert df_store.iloc[0]["growth_signal"] == 0.85
    assert df_store.iloc[0]["cash_signal"] == 0.65
    assert df_store.iloc[0]["micro_score"] == 0.75


def test_micro_llm_endpoint_isolation_cache(tmp_path: Path, mock_financial_statements_file: Path) -> None:
    output_path = tmp_path / "micro_llm_interpretation.parquet"
    interpreter_ep1 = MicroLLMInterpreter(
        repo_root=tmp_path,
        llm_config={"provider": "openai-compatible", "api_key": "k1", "base_url": "https://api1.example.com/v1", "model": "same-model"},
    )
    interpreter_ep2 = MicroLLMInterpreter(
        repo_root=tmp_path,
        llm_config={"provider": "openai-compatible", "api_key": "k2", "base_url": "https://api2.example.com/v1", "model": "same-model"},
    )

    mock_resp = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "quality": "neutral",
                            "growth_signal": 0.0,
                            "cash_signal": 0.0,
                            "narrative": "Mock narrative.",
                            "micro_score": 0.0,
                        }
                    )
                }
            }
        ]
    }
    interpreter_ep1._post = lambda _: mock_resp
    interpreter_ep2._post = lambda _: mock_resp

    as_of = "2026-04-20T00:00:00Z"
    asyncio.run(interpreter_ep1.interpret(as_of=as_of, financial_statements_path=mock_financial_statements_file, output_path=output_path))
    asyncio.run(interpreter_ep2.interpret(as_of=as_of, financial_statements_path=mock_financial_statements_file, output_path=output_path))

    df_store = pd.read_parquet(output_path)
    assert len(df_store) == 2
    ext_ids = df_store["extraction_id"].tolist()
    assert ext_ids[0] != ext_ids[1]


def test_micro_llm_fail_closed_on_corrupt_store(tmp_path: Path, mock_financial_statements_file: Path) -> None:
    output_path = tmp_path / "micro_llm_interpretation.parquet"
    output_path.write_bytes(b"corrupted parquet file content")

    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})
    with pytest.raises(ValueError, match="corrupt micro LLM interpretation store"):
        asyncio.run(
            interpreter.interpret(
                as_of="2026-04-20T00:00:00Z",
                financial_statements_path=mock_financial_statements_file,
                output_path=output_path,
            )
        )


def test_micro_llm_post_retry_and_timeout_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    interpreter = MicroLLMInterpreter(
        repo_root=tmp_path,
        llm_config={"provider": "openai-compatible", "api_key": "test-key", "base_url": "https://api.example.com/v1", "model": "test-model"},
        timeout=45.0,
        max_retries=3,
        backoff_factor=0.01,
    )
    assert interpreter.timeout == 45.0
    assert interpreter.max_retries == 3
    assert interpreter.backoff_factor == 0.01

    call_count = 0
    captured_timeouts = []

    def mock_post(url, headers, data, timeout):
        nonlocal call_count
        call_count += 1
        captured_timeouts.append(timeout)
        if call_count < 2:
            resp = requests.Response()
            resp.status_code = 429
            resp._content = b"Too Many Requests"
            raise requests.exceptions.HTTPError("429 Client Error", response=resp)
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps({
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "quality": "neutral",
                        "growth_signal": 0.0,
                        "cash_signal": 0.0,
                        "narrative": "ok",
                        "micro_score": 0.0,
                    })
                }
            }]
        }).encode("utf-8")
        return resp

    monkeypatch.setattr(requests, "post", mock_post)
    res = interpreter._post(b"{}")
    assert call_count == 2
    assert captured_timeouts == [45.0, 45.0]
    assert "choices" in res


def test_micro_llm_graceful_single_item_failure_in_batch(tmp_path: Path, mock_financial_statements_file: Path) -> None:
    output_path = tmp_path / "micro_llm_interpretation.parquet"
    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})

    # Make VCB succeed and VNM fail in _process_single or _post
    orig_post = interpreter._post

    def failing_post(body_bytes: bytes) -> dict:
        parsed = json.loads(body_bytes.decode("utf-8"))
        user_content = json.loads(parsed["messages"][1]["content"])
        if user_content.get("symbol") == "VNM":
            raise RuntimeError("Simulated transient failure for VNM")
        return orig_post(body_bytes)

    interpreter._post = failing_post

    # Interpret both VCB and VNM
    df = asyncio.run(
        interpreter.interpret(
            financial_statements_path=mock_financial_statements_file,
            output_path=output_path,
        )
    )

    # Batch should not abort; VCB should succeed and be saved
    assert output_path.exists()
    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "VCB"


def test_micro_llm_implicit_as_of_filters_future_source_data(tmp_path: Path) -> None:
    data = [
        # Past record (eligible under implicit as_of = now_utc)
        {
            "symbol": "VCB",
            "endpoint": "income_statement",
            "period_type": "quarter",
            "fiscal_year": 2026,
            "fiscal_quarter": 1,
            "item_code": "NET_PROFIT",
            "item_value": 10000.0,
            "fiscal_period_end": "2026-03-31",
            "source_publish_at": "2026-04-15T00:00:00Z",
            "available_at": "2026-04-16T00:00:00Z",
            "ingested_at": "2026-04-16T00:00:00Z",
        },
        # Future-dated source record (available_at in 2099)
        {
            "symbol": "FUTURE_SYM",
            "endpoint": "income_statement",
            "period_type": "quarter",
            "fiscal_year": 2099,
            "fiscal_quarter": 1,
            "item_code": "NET_PROFIT",
            "item_value": 50000.0,
            "fiscal_period_end": "2099-03-31",
            "source_publish_at": "2099-04-15T00:00:00Z",
            "available_at": "2099-04-16T00:00:00Z",
            "ingested_at": "2099-04-16T00:00:00Z",
        },
    ]
    df_raw = pd.DataFrame(data)
    fs_file = tmp_path / "fs_future.parquet"
    df_raw.to_parquet(fs_file, index=False)
    output_path = tmp_path / "micro_llm_interpretation.parquet"

    interpreter = MicroLLMInterpreter(repo_root=tmp_path, llm_config={"provider": "mock", "model": "mock-model"})

    # When as_of=None, future-dated source row is filtered out from interpretation source,
    # and returned output is unfiltered (returning the freshly generated VCB interpretation).
    df_result = asyncio.run(
        interpreter.interpret(
            as_of=None,
            financial_statements_path=fs_file,
            output_path=output_path,
        )
    )

    assert len(df_result) == 1
    assert df_result.iloc[0]["symbol"] == "VCB"
    assert "FUTURE_SYM" not in df_result["symbol"].values
