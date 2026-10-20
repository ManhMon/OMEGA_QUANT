import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
import pandas as pd

from omega.quant.signal.sentiment_alpha import SentimentAlphaEngine, direct_news_features
from omega.data.registry import ScoringModel, ScoringRegistrySnapshot
from omega.data.llm_sentiment_scorer import (
    FROZEN_LEXICON_SHA256,
    FROZEN_LEXICON_VERSION,
    JEVRequest,
    JEVResponse,
    LEXICON_V10,
    TypeSafeJEVScorer,
    frozen_lexicon_score,
)


def test_sentiment_alpha_combination_vectorized():
    engine = SentimentAlphaEngine(sentiment_scale=0.1)

    base = pd.Series([0.05, 0.12, -0.04], index=["VNM", "HPG", "VIC"])
    sentiment = pd.Series([0.5, -0.8, 1.2], index=["VNM", "HPG", "VIC"])

    as_of = datetime(2026, 5, 18, 19, 0, 0, tzinfo=timezone.utc)
    available_at = datetime(2026, 5, 18, 18, 0, 0, tzinfo=timezone.utc)
    timestamp = datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc)

    # VIC's sentiment 1.2 is clamped to 1.0. Scale = 0.1
    # VNM expected: 0.05 + 0.5 * 0.1 = 0.10
    # HPG expected: 0.12 + -0.8 * 0.1 = 0.04
    # VIC expected: -0.04 + 1.0 * 0.1 = 0.06
    combined = engine.combine_sentiment_alpha(
        base_signals=base,
        sentiment_scores=sentiment,
        as_of=as_of,
        available_at=available_at,
        timestamp=timestamp,
    )

    assert abs(combined["VNM"] - 0.10) < 1e-6
    assert abs(combined["HPG"] - 0.04) < 1e-6
    assert abs(combined["VIC"] - 0.06) < 1e-6


def test_compute_weighted_allocation_positive_only():
    engine = SentimentAlphaEngine()

    signals = pd.Series([-0.05, 0.08, 0.04], index=["VIC", "VNM", "HPG"])

    # Sum of positives: 0.08 + 0.04 = 0.12
    # VNM expected weight: 0.08 / 0.12 * 1.0 = 0.66667
    # HPG expected weight: 0.04 / 0.12 * 1.0 = 0.33333
    # VIC expected weight: 0.0 (negative)
    weights = engine.compute_weighted_allocation(signals, target_sum=1.0)

    assert weights["VIC"] == 0.0
    assert abs(weights["VNM"] - 0.6666666) < 1e-5
    assert abs(weights["HPG"] - 0.3333333) < 1e-5


def test_sentiment_alpha_engine_pit_violation_available_at_raises():
    engine = SentimentAlphaEngine()

    base = pd.Series([0.05], index=["VNM"])
    sentiment = pd.Series([0.5], index=["VNM"])

    as_of = datetime(2026, 5, 18, 16, 0, 0, tzinfo=timezone.utc)
    # available_at after timestamp => violation
    available_at = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    timestamp = datetime(2026, 5, 19, 9, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="PIT violation"):
        engine.combine_sentiment_alpha(
            base_signals=base,
            sentiment_scores=sentiment,
            as_of=as_of,
            available_at=available_at,
            timestamp=timestamp,
        )


_JEV_CUTOFF = datetime(2026, 10, 20, 8, 30, tzinfo=timezone.utc)


def _pinned_jev_model(version, revision, artifact):
    return ScoringModel(
        name="sentiment",
        version=version,
        provider="local",
        model_revision=revision,
        artifact_sha256=hashlib.sha256(artifact).hexdigest(),
        languages=("vi",),
        task="sentiment",
        schema_version="jev-sentiment-v1",
        rights="research-only",
        training_cutoff_at=_JEV_CUTOFF - timedelta(days=90),
        training_evidence_sha256="a" * 64,
        model_available_at=_JEV_CUTOFF - timedelta(days=60),
        prompt_version="prompt-v1",
        calibration_version="calibration-v1",
        calibration_sha256="b" * 64,
        calibration_available_at=_JEV_CUTOFF - timedelta(days=30),
        preprocessing_version="preprocessing-v1",
        artifact=artifact,
    )


def test_pinned_model_swap_preserves_jev_contract_and_old_result():
    text = "Công ty tăng lợi nhuận tích cực"
    request = JEVRequest(
        event_id="event-1", revision_id="revision-1", issuer="VNM",
        text_ref="article-1", text=text,
        input_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        evidence_mode="retrospective", as_of=_JEV_CUTOFF - timedelta(days=1),
        source_available_at=_JEV_CUTOFF - timedelta(hours=1),
        cutoff_at=_JEV_CUTOFF, decision_time=_JEV_CUTOFF, language="vi",
    )
    first_model = _pinned_jev_model("v1.0.0", "revision-1", b"model-one")
    second_model = _pinned_jev_model("v2.0.0", "revision-2", b"model-two")

    def run(model, score, run_id):
        snapshot = ScoringRegistrySnapshot((model,))
        scorer = TypeSafeJEVScorer(
            snapshot, model.name, model.version, run_id,
            lambda *_: JEVResponse("ok", score, 0.9, 0.8, None),
        )
        return scorer.score(request, score_ready_at=_JEV_CUTOFF)

    first = run(first_model, 0.4, "run-1")
    second = run(second_model, -0.3, "run-1")
    assert first.outcome.status == second.outcome.status == "ok"
    assert -1.0 <= first.outcome.score <= 1.0
    assert -1.0 <= second.outcome.score <= 1.0
    assert first.request.request_sha256 == second.request.request_sha256
    assert first.replay_key != second.replay_key
    assert first.model.version == "v1.0.0"
    assert first.outcome.score == 0.4
    assert set(vars(first.outcome)) == set(vars(second.outcome)) == {
        "status", "score", "confidence", "attribution", "reason_code",
    }

    historical_request = replace(request, evidence_mode="historical")
    historical = [
        TypeSafeJEVScorer(
            ScoringRegistrySnapshot((model,)), model.name, model.version, "run-1",
            lambda *_: pytest.fail("historical request must not call the model"),
        ).score(historical_request, score_ready_at=_JEV_CUTOFF)
        for model in (first_model, second_model)
    ]
    assert [item.outcome for item in historical] == [
        JEVResponse("unavailable", None, None, None, "historical_readiness_unavailable"),
    ] * 2
    assert historical[0].request.request_sha256 == historical[1].request.request_sha256
    assert historical[0].replay_key != historical[1].replay_key


def test_frozen_lexicon_counts_unique_terms_and_clips_without_legacy_dict():
    assert frozen_lexicon_score("TĂNG tăng tích cực lợi nhuận") == 1.0
    assert frozen_lexicon_score("tăng tăng giảm") == 0.0
    assert frozen_lexicon_score("TĂNG giảm") == 0.0
    assert frozen_lexicon_score("giảm tiêu cực thua lỗ") == -1.0
    assert frozen_lexicon_score("Tăng") == 1.0
    assert frozen_lexicon_score("không tăng") == 1.0
    assert frozen_lexicon_score("TANG") == 0.0


def test_frozen_lexicon_input_guards():
    for text in (None, 1, "", " \t"):
        with pytest.raises(ValueError):
            frozen_lexicon_score(text)
    for text in ("﻿tăng", "a\rb", "a" * (1024 * 1024 + 1), "\ud800"):
        with pytest.raises(ValueError):
            frozen_lexicon_score(text)
    assert frozen_lexicon_score("a" * (1024 * 1024)) == 0.0


def test_frozen_lexicon_version_digest_and_legacy_mutation_isolation():
    original = LEXICON_V10.copy()
    before = frozen_lexicon_score("tăng giảm")
    try:
        LEXICON_V10.clear()
        LEXICON_V10["tăng"] = -100
        assert frozen_lexicon_score("tăng giảm") == before == 0.0
    finally:
        LEXICON_V10.clear()
        LEXICON_V10.update(original)
    assert FROZEN_LEXICON_VERSION == "count-lexicon-v1"
    assert FROZEN_LEXICON_SHA256 == "ea0ab99215eaf9278b841333568129f1ce26d65f794d9515b7fcb66459d68f8b"
    assert len(FROZEN_LEXICON_SHA256) == 64


def _direct_result(event="event-1", revision="revision-1", score=0.4,
                   confidence=1.0, attribution=1.0, version="v1.0.0",
                   source=None, ready=None, text="tăng", evidence_mode="retrospective",
                   outcome=None, issuer="VNM"):
    model = _pinned_jev_model(version, "revision-" + version, version.encode())
    source = source or _JEV_CUTOFF - timedelta(hours=1)
    request = JEVRequest(
        event_id=event, revision_id=revision, issuer=issuer, text_ref="article-1", text=text,
        input_sha256=hashlib.sha256(text.encode()).hexdigest(), evidence_mode=evidence_mode,
        as_of=source, source_available_at=source, cutoff_at=_JEV_CUTOFF,
        decision_time=_JEV_CUTOFF, language="vi",
    )
    return TypeSafeJEVScorer(
        ScoringRegistrySnapshot((model,)), model.name, model.version, "direct-run",
        lambda *_: outcome or JEVResponse("ok", score, confidence, attribution, None),
    ).score(request, score_ready_at=ready or _JEV_CUTOFF)


def _direct(results, ages=None, **kwargs):
    return direct_news_features(
        results, decision_time=_JEV_CUTOFF,
        session_ages=ages if ages is not None else {("VNM", "event-1"): 0}, **kwargs,
    )


def test_direct_news_half_life_retains_mass_and_paired_baseline():
    event = _direct_result(score=0.8, confidence=0.5)
    fresh = _direct([event])
    aged = _direct([event], {("VNM", "event-1"): 3})
    assert fresh.loc["VNM", "direct_news"] == pytest.approx(0.4)
    assert aged.loc["VNM", "direct_news"] == pytest.approx(0.2)
    assert aged.loc["VNM", "effective_weight"] == pytest.approx(0.25)
    assert aged.loc["VNM", "lexicon_news"] == pytest.approx(0.25)
    many = _direct([event, _direct_result(event="event-2", score=0.8)],
                   {("VNM", "event-1"): 0, ("VNM", "event-2"): 0})
    assert many.loc["VNM", "direct_news"] == pytest.approx(0.8)
    assert aged.attrs["historical_eligible"] is False
    assert aged.attrs["lexicon_sha256"] == FROZEN_LEXICON_SHA256


def test_direct_news_unique_events_revisions_and_input_order():
    old = _direct_result(source=_JEV_CUTOFF - timedelta(days=1))
    new = _direct_result(revision="revision-2", score=-0.6, text="giảm")
    a = _direct([new, old, new])
    b = _direct([old, new])
    pd.testing.assert_frame_equal(a, b)
    assert a.loc["VNM", "news_count"] == 1
    assert a.loc["VNM", "direct_news"] == pytest.approx(-0.6)
    assert a.loc["VNM", "lexicon_news"] == -1
    with pytest.raises(ValueError, match="conflicting_direct_news_revision"):
        _direct([old, _direct_result(score=-0.1)])
    with pytest.raises(ValueError, match="ambiguous_direct_news_revision"):
        _direct([new, _direct_result()])


def test_direct_news_model_swap_invariant_panel_and_immutable_lineage():
    first = _direct_result(score=0.4)
    second = _direct_result(score=-0.3, version="v2.0.0")
    before = _direct([first])
    swapped = _direct([second])
    assert list(before.columns) == list(swapped.columns)
    for column in ("news_count", "scored_count", "effective_weight", "lexicon_mass", "lexicon_news", "coverage"):
        pd.testing.assert_series_equal(before[column], swapped[column])
    assert before.attrs["result_bindings"] != swapped.attrs["result_bindings"]
    assert before.attrs["pinned_run"] != swapped.attrs["pinned_run"]
    assert first.outcome.score == 0.4
    with pytest.raises(ValueError, match="mixed_direct_news_run"):
        _direct([first, second])


@pytest.mark.parametrize("outcome", [
    JEVResponse("unavailable", None, None, None, "provider_unavailable"),
    JEVResponse("error", None, None, None, "provider_error"),
])
def test_direct_news_failure_coverage_never_falls_back(outcome):
    result = _direct([_direct_result(outcome=outcome)], {})
    assert result.loc["VNM", "news_count"] == 1
    assert result.loc["VNM", "scored_count"] == 0
    assert result.loc["VNM", "status"] == "unavailable"
    assert pd.isna(result.loc["VNM", "direct_news"])
    assert pd.isna(result.loc["VNM", "lexicon_news"])


def test_direct_news_boundary_readiness_history_and_zero_weight():
    exact = _direct_result(source=_JEV_CUTOFF)
    assert _direct([exact]).loc["VNM", "direct_news"] == 0.4
    late = _direct_result(ready=_JEV_CUTOFF + timedelta(microseconds=1))
    assert _direct([late], {}).loc["VNM", "status"] == "unavailable"
    historical = _direct_result(evidence_mode="historical")
    assert _direct([historical], {}).attrs["historical_eligible"] is False
    assert _direct([historical], {}).attrs["evidence_mode"] == "historical"
    with pytest.raises(ValueError, match="mixed_direct_news_run"):
        _direct([exact, _direct_result(event="event-2", evidence_mode="historical")])
    assert _direct([historical], {}).loc["VNM", "status"] == "unavailable"
    assert pd.isna(_direct([_direct_result(confidence=0)]).loc["VNM", "direct_news"])
    assert pd.isna(_direct([exact], {("VNM", "event-1"): 1e12}, half_life_sessions=1e-300).loc["VNM", "direct_news"])
    assert _direct([]).empty


@pytest.mark.parametrize("value", [None, "3", [], True, float("nan"), float("inf"), float("-inf"), -1, 0.5, 1e13, pytest.param(10**400, id="integer-overflow")])
def test_direct_news_invalid_age_and_half_life(value):
    with pytest.raises(ValueError):
        _direct([_direct_result()], {("VNM", "event-1"): value})
    if value != 0.5:
        with pytest.raises(ValueError):
            _direct([], half_life_sessions=value)


def test_direct_news_rejects_bad_binding_missing_age_and_cutoff():
    with pytest.raises(ValueError, match="missing_session_age"):
        _direct([_direct_result()], {})
    with pytest.raises(ValueError):
        _direct([], half_life_sessions=0)
    with pytest.raises(ValueError):
        _direct([None])
    with pytest.raises(ValueError):
        direct_news_features([], decision_time=datetime(2026, 10, 20), session_ages={})
    event = _direct_result()
    object.__setattr__(event, "binding_sha256", "a" * 64)
    with pytest.raises(ValueError, match="invalid_jev_result_binding"):
        _direct([event])


def test_direct_news_latest_failure_does_not_revive_old_success():
    older = _direct_result(source=_JEV_CUTOFF - timedelta(days=1))
    failed = _direct_result(revision="revision-2", outcome=JEVResponse(
        "error", None, None, None, "invalid_response"))
    result = _direct([older, failed])
    assert result.loc["VNM", "news_count"] == 1
    assert result.loc["VNM", "scored_count"] == 0
    assert result.loc["VNM", "status"] == "unavailable"


def test_direct_news_multi_issuer_negative_and_attribution_bounds():
    events = [_direct_result(score=-1, attribution=0.5),
              _direct_result(issuer="DELISTED", score=1)]
    result = _direct(events, {("VNM", "event-1"): 0, ("DELISTED", "event-1"): 0})
    assert result.loc["VNM", "direct_news"] == -0.5
    assert result.loc["DELISTED", "direct_news"] == 1
    with pytest.raises(ValueError, match="invalid_direct_news_results"):
        _direct([None] * 100_001)
    for confidence in (float("nan"), float("inf"), -0.1, 1.1, True):
        with pytest.raises(ValueError, match="invalid_jev_number"):
            JEVResponse("ok", 0, confidence, 1, None)


def test_direct_news_concurrent_calls_are_isolated():
    from concurrent.futures import ThreadPoolExecutor

    event = _direct_result()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(lambda _: _direct([event]), range(4)))
    for output in outputs[1:]:
        pd.testing.assert_frame_equal(outputs[0], output)
    outputs[0].loc["VNM", "direct_news"] = 1
    assert outputs[1].loc["VNM", "direct_news"] == 0.4
    assert event.outcome.score == 0.4


def test_direct_news_no_graph_macro_dependency():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for relative in ("src/omega/quant/signal/sentiment_alpha.py", "src/omega/data/llm_sentiment_scorer.py"):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not any("graph" in name or "macro" in name for name in names)
