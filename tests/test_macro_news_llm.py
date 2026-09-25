import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
import pyarrow.parquet as pq
import pytest

from omega.data.macro_news_llm import MAX_EXTRACT_RECORDS, MacroNewsLLMExtractor


def _raw(record_id):
    return pd.DataFrame([{"raw_record_id": record_id, "title": "Tin", "summary": "",
                          "published_at": "2026-09-24T00:00:00Z", "available_at": "2026-09-24T01:00:00Z"}])


def test_parallel_extraction_preserves_both_records(tmp_path, monkeypatch):
    monkeypatch.setattr("omega.data.macro_news_llm.classify_jev", lambda **_: {
        "selected": {"polarity": "NEUTRAL", "category": "macro", "impact": "low"}, "fingerprint": "a" * 64})
    output = tmp_path / "out.parquet"

    def run(record_id):
        extractor = MacroNewsLLMExtractor(tmp_path, narrative=lambda *_: "Narrative")
        return asyncio.run(extractor.process_dataframe(_raw(record_id), output, tmp_path / "links.parquet",
                                                    datetime(2026, 9, 25, tzinfo=timezone.utc)))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("one", "two")))
    assert sorted(pd.read_parquet(output)["news_id"].tolist()) == ["one", "two"]
    assert sorted(len(result) for result in results) == [1, 1]


def test_extraction_write_failure_keeps_previous_parquet(tmp_path, monkeypatch):
    monkeypatch.setattr("omega.data.macro_news_llm.classify_jev", lambda **_: {
        "selected": {"polarity": "NEUTRAL", "category": "macro", "impact": "low"}, "fingerprint": "a" * 64})
    output = tmp_path / "out.parquet"
    original = b"previous"
    output.write_bytes(original)
    pd.DataFrame({"wrong": ["value"]}).to_parquet(output, index=False)
    original = output.read_bytes()
    extractor = MacroNewsLLMExtractor(tmp_path, narrative=lambda *_: "Narrative")
    with pytest.raises(ValueError, match="schema drift"):
        asyncio.run(extractor.process_dataframe(_raw("one"), output, tmp_path / "links.parquet"))
    assert output.read_bytes() == original
    assert not (tmp_path / "out.parquet.lock").exists()


def test_extraction_replace_failure_cleans_temp_and_preserves_output(tmp_path, monkeypatch):
    monkeypatch.setattr("omega.data.macro_news_llm.classify_jev", lambda **_: {
        "selected": {"polarity": "NEUTRAL", "category": "macro", "impact": "low"}, "fingerprint": "a" * 64})
    output = tmp_path / "out.parquet"
    extractor = MacroNewsLLMExtractor(tmp_path, narrative=lambda *_: "Narrative")
    asyncio.run(extractor.process_dataframe(_raw("one"), output, tmp_path / "links.parquet"))
    before = output.read_bytes()
    monkeypatch.setattr("omega.data.macro_news_llm.os.replace", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        asyncio.run(extractor.process_dataframe(_raw("two"), output, tmp_path / "links.parquet"))
    assert output.read_bytes() == before
    assert not list(tmp_path.glob("*.parquet.lock"))
    assert not [path for path in tmp_path.glob("*.parquet") if path != output]


def test_extraction_rejects_oversized_batch_before_provider_or_write(tmp_path, monkeypatch):
    def forbidden(**_):
        raise AssertionError("provider called")

    monkeypatch.setattr("omega.data.macro_news_llm.classify_jev", forbidden)
    extractor = MacroNewsLLMExtractor(tmp_path, narrative=lambda *_: "Narrative")
    raw = pd.concat([_raw(str(index)) for index in range(MAX_EXTRACT_RECORDS + 1)], ignore_index=True)
    output = tmp_path / "out.parquet"
    with pytest.raises(ValueError, match="batch exceeds limit"):
        asyncio.run(extractor.process_dataframe(raw, output, tmp_path / "links.parquet"))
    assert not output.exists()
    assert extractor.metrics == {"extraction_successes": 0, "extraction_failures": 0}


def test_extraction_streams_history_in_bounded_batches(tmp_path, monkeypatch):
    monkeypatch.setattr("omega.data.macro_news_llm.classify_jev", lambda **_: {
        "selected": {"polarity": "NEUTRAL", "category": "macro", "impact": "low"}, "fingerprint": "a" * 64})
    output = tmp_path / "out.parquet"
    extractor = MacroNewsLLMExtractor(tmp_path, narrative=lambda *_: "Narrative")
    extractor.extract(_raw("old"), output, tmp_path / "links.parquet")
    original_batches = pq.ParquetFile.iter_batches
    sizes = []

    def bounded(self, *args, **kwargs):
        sizes.append(kwargs.get("batch_size"))
        yield from original_batches(self, *args, **kwargs)

    monkeypatch.setattr(pq.ParquetFile, "iter_batches", bounded)
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("full read")))
    extractor.extract(_raw("new"), output, tmp_path / "links.parquet")
    assert sizes == [1024]
    assert pq.read_table(output, columns=["news_id"]).column("news_id").to_pylist() == ["old", "new"]
