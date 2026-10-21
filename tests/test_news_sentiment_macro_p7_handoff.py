"""P7 cross-module final verification; no production joined policy is asserted."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from omega.data.earnings_ledger import AccountingBasis, EarningsAnnouncement, EarningsLedger
from omega.data.llm_sentiment_scorer import JEVRequest, JEVResponse, TypeSafeJEVScorer
from omega.data.macro_pipeline import SCHEMA, MacroDataPipeline
from omega.data.registry import ScoringModel, ScoringRegistrySnapshot
from omega.quant.signal.sentiment_alpha import (
    direct_news_features,
    ecosystem_sentiment_spillover,
)
from omega.quant.strategy.pead_drift import PEADDriftEngine
from omega.quant.strategy.unified_alpha_evaluator import blend_features


ICT = timezone(timedelta(hours=7))
_LAG = datetime(2024, 1, 2, 15, 30, tzinfo=ICT)
_CUTOFF = datetime(2024, 1, 3, 15, 30, tzinfo=ICT)
_TRADE_DATE = date(2024, 1, 3)


def _jev_result():
    model = ScoringModel(
        name="sentiment",
        version="v1.0.0",
        provider="local",
        model_revision="p7-revision",
        artifact_sha256=hashlib.sha256(b"p7-model").hexdigest(),
        languages=("vi",),
        task="sentiment",
        schema_version="jev-sentiment-v1",
        rights="research-only",
        training_cutoff_at=_LAG - timedelta(days=90),
        training_evidence_sha256="a" * 64,
        model_available_at=_LAG - timedelta(days=60),
        prompt_version="p7-prompt",
        calibration_version="p7-calibration",
        calibration_sha256="b" * 64,
        calibration_available_at=_LAG - timedelta(days=30),
        preprocessing_version="p7-preprocessing",
        artifact=b"p7-model",
    )
    text = "Công ty tăng lợi nhuận"
    request = JEVRequest(
        event_id="p7-event",
        revision_id="p7-revision-1",
        issuer="AAA",
        text_ref="p7-article",
        text=text,
        input_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        evidence_mode="retrospective",
        as_of=_LAG - timedelta(days=1),
        source_available_at=_LAG - timedelta(hours=1),
        cutoff_at=_LAG,
        decision_time=_LAG,
        language="vi",
    )
    scorer = TypeSafeJEVScorer(
        ScoringRegistrySnapshot((model,)),
        model.name,
        model.version,
        "p7-run",
        lambda *_: JEVResponse("ok", 0.8, 0.9, 1.0, None),
    )
    return scorer.score(request, score_ready_at=_LAG)


def _macro_row(revision: str, value: float, available_at: datetime, ingested_at: datetime, timespec: str):
    return {
        "indicator": "cpi",
        "value": value,
        "observation_date": "2024-01-01T00:00:00+07:00",
        "published_at": "2024-01-02T09:00:00+07:00",
        "available_at": available_at.isoformat(timespec=timespec),
        "ingested_at": ingested_at.isoformat(timespec=timespec),
        "revision_id": hashlib.sha256(revision.encode()).hexdigest(),
        "source": "p7-fixture",
    }


@pytest.mark.parametrize("timespec", [
    pytest.param("microseconds", id="uniform-precision"),
    pytest.param("auto", id="mixed-precision"),
])
@pytest.mark.parametrize(
    "decision_time",
    [pytest.param(_CUTOFF, id="ict-inclusive"),
     pytest.param(_CUTOFF.astimezone(timezone.utc), id="utc-same-instant")],
)
def test_p7_cross_module_final_verification(tmp_path, decision_time, timespec):
    jev = _jev_result()
    direct = direct_news_features(
        [jev], decision_time=_LAG, session_ages={("AAA", "p7-event"): 0}
    )
    assert direct.loc["AAA", "direct_news"] == pytest.approx(0.72)
    assert jev.historical_eligible is False
    assert direct.attrs["historical_eligible"] is False

    news = pd.DataFrame(
        [
            {
                "issuer": "AAA",
                "observed": direct.loc["AAA", "direct_news"],
                "expected": 0.2,
                "sector": "S",
                "as_of": _LAG - timedelta(days=1),
                "available_at": _LAG,
                "expected_available_at": _LAG - timedelta(days=2),
            },
            {
                "issuer": "BBB",
                "observed": None,
                "expected": 0.0,
                "sector": "T",
                "as_of": _LAG - timedelta(days=1),
                "available_at": _LAG,
                "expected_available_at": _LAG - timedelta(days=2),
            },
        ]
    )
    edges = pd.DataFrame(
        [{
            "source": "AAA",
            "target": "BBB",
            "weight": 0.5,
            "as_of": _LAG - timedelta(days=2),
            "available_at": _LAG,
            "valid_until": None,
        }]
    )
    news_before, edges_before = news.copy(deep=True), edges.copy(deep=True)
    spill = ecosystem_sentiment_spillover(
        news, edges, decision_time=_CUTOFF, lag_time=_LAG, graph_complete=True
    )
    pd.testing.assert_frame_equal(news, news_before)
    pd.testing.assert_frame_equal(edges, edges_before)
    assert spill.loc["BBB", "spillover"] == pytest.approx(0.26)
    assert pd.isna(spill.loc["BBB", "direct_news"])
    assert spill.attrs["historical_eligible"] is False

    announced = datetime(2024, 1, 2, 8, 0, tzinfo=ICT)
    event = EarningsAnnouncement(
        issuer="AAA",
        fiscal_year=2023,
        fiscal_quarter=4,
        release_id="p7-release",
        revision=0,
        actual=100.0,
        basis=AccountingBasis(),
        announced_at=announced,
        available_at=announced + timedelta(minutes=1),
        first_seen_at=announced + timedelta(minutes=2),
        ingested_at=announced + timedelta(minutes=3),
        ready_at=announced + timedelta(minutes=30),
        source_id="p7-source",
        evidence_sha256="c" * 64,
        verified=False,
    )
    ledger = EarningsLedger(events=(event,))
    try:
        engine = PEADDriftEngine(ledger)
        panel = pd.DataFrame(
            {"close": [100.0, 200.0]},
            index=pd.MultiIndex.from_tuples(
                [(_TRADE_DATE, "AAA"), (_TRADE_DATE, "BBB")],
                names=("date", "symbol"),
            ),
        )
        pead = engine.features(panel, as_of=_CUTOFF)
        unverified = pead.loc[(_TRADE_DATE, "AAA")]
        assert unverified["pead_sue_reason"] == "unverified"
        assert not unverified["pead_sue_valid"]
        assert pd.isna(unverified["pead_sue_drift"])
        assert engine.event_surprises(event)["sue"].reason == "unverified"
    finally:
        ledger.close()

    macro_path = tmp_path / "macro.parquet"
    macro_rows = pd.DataFrame(
        [
            _macro_row("visible", 4.5, _CUTOFF, _CUTOFF, timespec),
            _macro_row("future-available", 4.6, _CUTOFF + timedelta(microseconds=1), _CUTOFF, timespec),
            _macro_row("future-ingested", 4.7, _CUTOFF, _CUTOFF + timedelta(microseconds=1), timespec),
        ],
        columns=SCHEMA,
    )
    macro_rows.to_parquet(macro_path, index=False)
    macro = MacroDataPipeline.query_as_of(macro_path, decision_time)
    assert macro["revision_id"].tolist() == [hashlib.sha256(b"visible").hexdigest()]
    assert macro.iloc[0]["value"] == pytest.approx(4.5)

    symbols = pd.Index(["AAA", "BBB"], name="symbol")
    pead_by_symbol = pead.xs(_TRADE_DATE, level="date").reindex(symbols)
    features = pd.DataFrame(
        {
            "direct_news": direct.reindex(symbols)["direct_news"],
            "spillover": spill.reindex(symbols)["spillover"],
            "pead": pead_by_symbol["pead_sue_drift"],
            "feature_as_of": [(_LAG - timedelta(days=1)).isoformat()] * len(symbols),
            "feature_available_at": [_LAG.isoformat()] * len(symbols),
            "lineage": ["p7-unverified-fixture"] * len(symbols),
        },
        index=symbols,
    )
    quant = pd.Series([0.1, -0.2], index=symbols, dtype=float)
    quant_before, features_before = quant.copy(deep=True), features.copy(deep=True)
    # Fixture-only multiplier; no trusted macro-to-multiplier policy exists.
    fixture_macro_multiplier = 0.5
    blended = blend_features(
        quant,
        features,
        weights={"direct_news": 0.04, "spillover": 0.03, "pead": 0.02},
        decision_time=decision_time,
        macro_multiplier=fixture_macro_multiplier,
    )
    pd.testing.assert_series_equal(quant, quant_before)
    pd.testing.assert_frame_equal(features, features_before)
    assert blended["direct_news_valid"].tolist() == [True, False]
    assert blended["pead_valid"].tolist() == [False, False]
    assert blended.loc["AAA", "score_before_macro"] == pytest.approx(0.1198)
    assert blended.loc["BBB", "score_before_macro"] == pytest.approx(-0.1742)
    pd.testing.assert_series_equal(
        blended["score"], blended["score_before_macro"] * fixture_macro_multiplier,
        check_names=False,
    )


@pytest.mark.parametrize(
    "bad_feature",
    [
        pytest.param(True, id="bool"),
        pytest.param("0.2", id="wrong-type"),
        pytest.param(float("inf"), id="non-finite"),
        pytest.param(float("-inf"), id="negative-infinity"),
        pytest.param([], id="list"),
        pytest.param("", id="empty-string"),
        pytest.param(-1.01, id="below-bound"),
        pytest.param(1e13, id="above-bound"),
        pytest.param(10**400, id="integer-overflow"),
    ],
)
def test_p7_blend_rejects_malformed_nonfinite_and_overflow_features(bad_feature):
    index = pd.Index(["AAA"], name="symbol")
    quant = pd.Series([0.0], index=index)
    features = pd.DataFrame(
        {
            "direct_news": pd.Series([bad_feature], index=index, dtype=object),
            "spillover": [None],
            "pead": [None],
            "feature_as_of": [_LAG.isoformat()],
            "feature_available_at": [_LAG.isoformat()],
            "lineage": ["p7-unverified-fixture"],
        },
        index=index,
    )
    before = features.copy(deep=True)
    with pytest.raises(ValueError):
        blend_features(
            quant,
            features,
            weights={"direct_news": 0.04, "spillover": 0.03, "pead": 0.02},
            decision_time=_CUTOFF,
        )
    pd.testing.assert_frame_equal(features, before)


@pytest.mark.parametrize("missing", [None, float("nan"), pd.NA], ids=["none", "nan", "pandas-na"])
def test_p7_missing_is_not_valid_zero(missing):
    index = pd.Index(["AAA", "BBB"], name="symbol")
    quant = pd.Series([0.2, 0.2], index=index)
    features = pd.DataFrame(
        {
            "direct_news": pd.Series([0.0, missing], index=index, dtype=object),
            "spillover": [None, None],
            "pead": [None, None],
            "feature_as_of": [_LAG.isoformat()] * 2,
            "feature_available_at": [_CUTOFF.isoformat()] * 2,
            "lineage": ["p7-unverified-fixture"] * 2,
        }, index=index,
    )
    before = features.copy(deep=True)
    kwargs = dict(weights={"direct_news": 0.04, "spillover": 0.03, "pead": 0.02}, decision_time=_CUTOFF)
    result = blend_features(quant, features, **kwargs)
    assert result.direct_news_valid.tolist() == [True, False]
    assert result.score.tolist() == pytest.approx([0.182, 0.182])
    pd.testing.assert_frame_equal(result, blend_features(quant, features, **kwargs))
    pd.testing.assert_frame_equal(features, before)


@pytest.mark.parametrize("column", SCHEMA[2:6])
@pytest.mark.parametrize("representation", ["iso", "datetime64", "timestamp-object", "mixed-object"])
@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reverse"])
def test_p7_macro_timestamp_representations(tmp_path, column, representation, reverse):
    rows = [
        _macro_row("earlier", 4.5, _CUTOFF, _CUTOFF, "auto"),
        _macro_row("later", 4.6, _CUTOFF, _CUTOFF, "auto"),
    ]
    rows[1]["indicator"] = "gdp_growth"
    # Equal instants, distinct offsets and precision, in either input order.
    rows[1][column] = pd.Timestamp(rows[1][column]).tz_convert("UTC").isoformat(timespec="microseconds")
    frame = pd.DataFrame(rows[::-1] if reverse else rows, columns=SCHEMA)
    if representation == "datetime64":
        frame[column] = frame[column].map(lambda value: pd.Timestamp(value).tz_convert("UTC").tz_localize(None))
    elif representation == "timestamp-object":
        frame[column] = pd.Series([pd.Timestamp(value) for value in frame[column]], dtype=object)
    elif representation == "mixed-object":
        frame.loc[0, column] = pd.Timestamp(frame.loc[0, column])
    before = frame.copy(deep=True)
    MacroDataPipeline._validate_store(frame)
    pd.testing.assert_frame_equal(frame, before)
    # Parquet has no heterogeneous scalar type; persist the equivalent ISO values.
    persisted = frame.copy(deep=True)
    if representation != "datetime64":
        persisted[column] = persisted[column].map(lambda value: value.isoformat() if isinstance(value, pd.Timestamp) else value)
    path = tmp_path / "macro.parquet"
    persisted.to_parquet(path, index=False)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = MacroDataPipeline.query_as_of(path, _CUTOFF.astimezone(timezone.utc))
    assert result.set_index("indicator")["value"].to_dict() == {"cpi": 4.5, "gdp_growth": 4.6}
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("column", SCHEMA[2:6])
@pytest.mark.parametrize("bad_timestamp", [
    pytest.param(None, id="none"),
    pytest.param(pd.NaT, id="pandas-nat"),
    pytest.param(pd.NA, id="pandas-na"),
    pytest.param("", id="empty"),
    pytest.param("not-a-timestamp", id="malformed"),
    pytest.param("2024-13-32T25:61:00+07:00", id="out-of-bounds"),
    pytest.param("01/02/2024", id="non-iso"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
    pytest.param([], id="list"),
])
def test_p7_macro_invalid_timestamps_fail_closed(tmp_path, monkeypatch, column, bad_timestamp):
    frame = pd.DataFrame([
        _macro_row("invalid", 4.5, _CUTOFF + timedelta(days=1), _CUTOFF, "auto"),
    ], columns=SCHEMA)
    frame[column] = pd.Series([bad_timestamp], dtype=object)
    before = frame.copy(deep=True)
    # Even a future-ineligible row must be validated before query filtering.
    monkeypatch.setattr(pd, "read_parquet", lambda _: frame.copy(deep=True))
    with pytest.raises((ValueError, TypeError, OverflowError)):
        MacroDataPipeline.query_as_of(tmp_path / "macro.parquet", _CUTOFF)
    pd.testing.assert_frame_equal(frame, before)


def test_p7_macro_mixed_precision_write_and_revision_selection(tmp_path, monkeypatch):
    path = tmp_path / "macro.parquet"
    original = pd.DataFrame([_macro_row("stored", 4.5, _CUTOFF, _CUTOFF, "auto")], columns=SCHEMA)
    original.to_parquet(path, index=False)
    incoming = pd.DataFrame([_macro_row("revised", 4.6, _CUTOFF, _CUTOFF, "microseconds")], columns=SCHEMA)
    incoming.loc[0, "published_at"] = "2024-01-02T09:00:00.000001+07:00"
    incoming.loc[0, "observation_date"] = "2024-01-01T00:00:00.000000+07:00"
    before = incoming.copy(deep=True)
    pipeline = MacroDataPipeline(urls={})
    monkeypatch.setattr(pipeline, "fetch", lambda: incoming.copy(deep=True))
    assert len(pipeline.run(path)) == 2
    assert len(pipeline.run(path)) == 2
    result = pipeline.query_as_of(path, _CUTOFF)
    assert result["revision_id"].tolist() == [hashlib.sha256(b"revised").hexdigest()]
    assert result["value"].tolist() == [4.6]
    pd.testing.assert_frame_equal(incoming, before)


@pytest.mark.parametrize("column", ["available_at", "ingested_at"])
@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reverse"])
def test_p7_macro_nanosecond_cutoff(tmp_path, column, reverse):
    rows = [
        _macro_row("visible", 4.5, _CUTOFF, _CUTOFF, "auto"),
        _macro_row("future", 4.6, _CUTOFF, _CUTOFF, "auto"),
    ]
    rows[1][column] = "2024-01-03T15:30:00.000000001+07:00"
    path = tmp_path / "macro.parquet"
    pd.DataFrame(rows[::-1] if reverse else rows, columns=SCHEMA).to_parquet(path, index=False)
    result = MacroDataPipeline.query_as_of(path, _CUTOFF)
    assert result["revision_id"].tolist() == [hashlib.sha256(b"visible").hexdigest()]


@pytest.mark.parametrize("column", SCHEMA[2:6])
@pytest.mark.parametrize("fault", ["invalid-incoming", "invalid-staged", "replace-failure"])
def test_p7_macro_write_failure_preserves_store(tmp_path, monkeypatch, fault, column):
    path = tmp_path / "macro.parquet"
    original = pd.DataFrame([_macro_row("stored", 4.5, _CUTOFF, _CUTOFF, "auto")], columns=SCHEMA)
    original.to_parquet(path, index=False)
    original_bytes = path.read_bytes()
    incoming = pd.DataFrame([
        _macro_row("incoming", 4.6, _CUTOFF + timedelta(microseconds=1), _CUTOFF, "auto"),
    ], columns=SCHEMA)
    pipeline = MacroDataPipeline(urls={})
    monkeypatch.setattr(pipeline, "fetch", lambda: incoming.copy(deep=True))
    if fault == "invalid-incoming":
        incoming.loc[0, column] = "not-a-timestamp"
    elif fault == "invalid-staged":
        read_parquet = pd.read_parquet
        def read_staged(target):
            frame = read_parquet(target)
            if target != path:
                frame.loc[0, column] = pd.NaT
            return frame
        monkeypatch.setattr(pd, "read_parquet", read_staged)
    else:
        def fail_replace(*_):
            raise OSError("injected publication failure")
        monkeypatch.setattr("omega.data.macro_pipeline.os.replace", fail_replace)
    with pytest.raises((ValueError, OSError)):
        pipeline.run(path)
    assert path.read_bytes() == original_bytes
    assert not list(tmp_path.glob(".macro-*"))


@pytest.mark.parametrize("fault", ["future", "naive", "reversed-clock", "extra-column", "duplicate-symbol", "reordered-symbol"])
def test_p7_join_rejects_clock_and_schema_faults(fault):
    index = pd.Index(["AAA", "BBB"], name="symbol")
    quant = pd.Series([0.2, -0.2], index=index)
    features = pd.DataFrame(
        {
            "direct_news": [0.0, None], "spillover": [None, None], "pead": [None, None],
            "feature_as_of": [_LAG.isoformat()] * 2,
            "feature_available_at": [_CUTOFF.isoformat()] * 2,
            "lineage": ["p7-unverified-fixture"] * 2,
        }, index=index,
    )
    if fault == "future":
        features.loc["AAA", "feature_available_at"] = (_CUTOFF + timedelta(microseconds=1)).isoformat()
    elif fault == "naive":
        features.loc["AAA", "feature_available_at"] = _CUTOFF.replace(tzinfo=None).isoformat()
    elif fault == "reversed-clock":
        features.loc["AAA", "feature_as_of"] = (_CUTOFF + timedelta(microseconds=1)).isoformat()
    elif fault == "extra-column":
        features["verified"] = True
    elif fault == "duplicate-symbol":
        features.index = pd.Index(["AAA", "AAA"], name="symbol")
    else:
        features = features.iloc[::-1]
    before = features.copy(deep=True)
    with pytest.raises(ValueError):
        blend_features(quant, features, weights={"direct_news": 0.04, "spillover": 0.03, "pead": 0.02}, decision_time=_CUTOFF)
    pd.testing.assert_frame_equal(features, before)
