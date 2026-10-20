from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
from typing import Callable, Optional

from .registry import (
    ScoringModel,
    ScoringRegistrySnapshot,
    _scoring_identifier,
    _scoring_timestamp,
)

LEXICON_V10 = {
    # UTF-8 Vietnamese lexicon entries are intentionally stored as native Unicode.
    # Regression coverage: real Vietnamese diacritics must survive UTF-8 roundtrip.
    "tăng": 0.6,
    "tích cực": 0.7,
    "lợi nhuận": 0.5,
    "giảm": -0.6,
    "tiêu cực": -0.7,
    "thua lỗ": -0.8,
}


def _verify_lexicon_utf8() -> None:
    for term in LEXICON_V10:
        term.encode("utf-8").decode("utf-8")


_verify_lexicon_utf8()


FROZEN_LEXICON_VERSION = "count-lexicon-v1"
_FROZEN_LEXICON_TERMS = (
    ("tăng", 1),
    ("tích cực", 1),
    ("lợi nhuận", 1),
    ("giảm", -1),
    ("tiêu cực", -1),
    ("thua lỗ", -1),
)
_FROZEN_LEXICON_CANONICAL = json.dumps(
    {
        "algorithm": "count_each_matching_term_once;sum_signs;clip_to_unit_interval",
        "normalization": "str.lower;unicode_substring;no_tokenization",
        "terms": _FROZEN_LEXICON_TERMS,
        "version": FROZEN_LEXICON_VERSION,
    },
    sort_keys=True,
    ensure_ascii=False,
    separators=(",", ":"),
).encode("utf-8")
FROZEN_LEXICON_SHA256 = hashlib.sha256(_FROZEN_LEXICON_CANONICAL).hexdigest()


def frozen_lexicon_score(text: str) -> float:
    if type(text) is not str or not text.strip():
        raise ValueError("invalid_jev_text")
    try:
        raw = text.encode("utf-8")
    except UnicodeError:
        raise ValueError("invalid_jev_text_encoding") from None
    if len(raw) > 1024 * 1024 or text.startswith("﻿") or "\r" in text:
        raise ValueError("invalid_jev_text_encoding_or_size")
    lowered = text.lower()
    score = sum(polarity for term, polarity in _FROZEN_LEXICON_TERMS if term in lowered)
    return float(max(-1, min(1, score)))


@dataclass(frozen=True)
class SentimentProvenance:
    schema_version: int
    tier: str
    model: str
    source: str
    parser_version: str
    scored_at: str
    cutoff_at: str
    event_time: str
    fallback_reason: Optional[str]
    input_sha256: str


@dataclass(frozen=True)
class SentimentResult:
    score: float
    label: str
    provenance: SentimentProvenance


class LLMSentimentScorer:
    def __init__(self, llm: Optional[Callable[[str], float]] = None):
        self.llm = llm
        self._seen: dict[str, datetime] = {}

    def _fingerprint(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text.lower()).strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def is_duplicate(self, text: str, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        digest = self._fingerprint(text)
        previous = self._seen.get(digest)
        self._seen[digest] = now
        return previous is not None and now - previous <= timedelta(hours=48)

    def is_semantic_duplicate(
        self, text: str, event_time: datetime, now: datetime
    ) -> bool:
        digest = self._fingerprint(text)
        previous = self._seen.get(digest)
        self._seen[digest] = event_time
        return previous is not None and now - previous <= timedelta(hours=48)

    def _lexicon_score(self, text: str) -> float:
        lowered = text.lower()
        hits = [score for term, score in LEXICON_V10.items() if term in lowered]
        return sum(hits) / len(hits) if hits else 0.0

    def score(
        self,
        text: str,
        event_time: Optional[datetime] = None,
        cutoff_at: Optional[datetime] = None,
        scored_at: Optional[datetime] = None,
    ) -> SentimentResult:
        digest = self._fingerprint(text)
        score = self._lexicon_score(text)
        tier = "lexicon"
        model = "lexicon-v10"
        fallback_reason = None
        source = "lexicon_v10"
        scored_at = scored_at or datetime.now(timezone.utc)
        event_time = event_time or scored_at
        cutoff_at = cutoff_at or scored_at
        if event_time > cutoff_at:
            raise ValueError("event_time_after_cutoff")

        if self.llm is not None:
            try:
                candidate = float(self.llm(text))
                if not math.isfinite(candidate) or not -1.0 <= candidate <= 1.0:
                    raise ValueError("invalid_llm_score")
                score = candidate
                tier = "llm"
                model = "configured"
                source = "llm"
            except Exception as exc:
                fallback_reason = type(exc).__name__

        label = "positive" if score > 0.2 else "negative" if score < -0.2 else "neutral"
        return SentimentResult(
            score=score,
            label=label,
            provenance=SentimentProvenance(
                schema_version=1,
                tier=tier,
                model=model,
                source=source,
                parser_version="sentiment-v10",
                scored_at=scored_at.isoformat(),
                cutoff_at=cutoff_at.isoformat(),
                event_time=event_time.isoformat(),
                fallback_reason=fallback_reason,
                input_sha256=digest,
            ),
        )


def _jev_digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _jev_number(value: object, lower: float, upper: float) -> None:
    if type(value) not in (int, float) or not lower <= value <= upper:
        raise ValueError("invalid_jev_number")


@dataclass(frozen=True)
class JEVRequest:
    event_id: str
    revision_id: str
    issuer: str
    text_ref: str
    text: str = field(repr=False)
    input_sha256: str
    evidence_mode: str
    as_of: datetime
    source_available_at: datetime
    cutoff_at: datetime
    decision_time: datetime
    language: str

    def __post_init__(self) -> None:
        for field in ("event_id", "revision_id", "issuer", "text_ref", "language"):
            _scoring_identifier(getattr(self, field), field)
        if type(self.text) is not str or not self.text.strip():
            raise ValueError("invalid_jev_text")
        try:
            raw = self.text.encode("utf-8")
        except UnicodeError:
            raise ValueError("invalid_jev_text_encoding") from None
        if len(raw) > 1024 * 1024 or self.text.startswith("﻿") or "\r" in self.text:
            raise ValueError("invalid_jev_text_encoding_or_size")
        if (type(self.input_sha256) is not str
                or self.input_sha256 != hashlib.sha256(raw).hexdigest()):
            raise ValueError("jev_input_digest_mismatch")
        if type(self.evidence_mode) is not str or self.evidence_mode not in (
            "retrospective", "historical",
        ):
            raise ValueError("invalid_jev_evidence_mode")
        for field in ("as_of", "source_available_at", "cutoff_at", "decision_time"):
            object.__setattr__(self, field, _scoring_timestamp(getattr(self, field), field))
        if not self.as_of <= self.source_available_at <= self.cutoff_at <= self.decision_time:
            raise ValueError("invalid_jev_time_order")

    @property
    def request_sha256(self) -> str:
        return _jev_digest({
            field: value.isoformat() if isinstance(value, datetime) else value
            for field, value in vars(self).items() if field != "text"
        })

    @classmethod
    def from_payload(cls, payload: dict) -> JEVRequest:
        fields = set(cls.__dataclass_fields__)
        if type(payload) is not dict or set(payload) != fields:
            raise ValueError("invalid_jev_request_schema")
        return cls(**payload)


@dataclass(frozen=True)
class JEVResponse:
    status: str
    score: Optional[float]
    confidence: Optional[float]
    attribution: Optional[float]
    reason_code: Optional[str]

    def __post_init__(self) -> None:
        if type(self.status) is not str or self.status not in ("ok", "unavailable", "error"):
            raise ValueError("invalid_jev_status")
        if self.status == "ok":
            _jev_number(self.score, -1.0, 1.0)
            _jev_number(self.confidence, 0.0, 1.0)
            _jev_number(self.attribution, 0.0, 1.0)
            if self.reason_code is not None:
                raise ValueError("invalid_jev_reason")
        elif (any(value is not None for value in (
                self.score, self.confidence, self.attribution))
                or type(self.reason_code) is not str
                or self.reason_code not in (
                    "provider_unavailable", "provider_error", "invalid_response",
                    "historical_readiness_unavailable", "not_ready",
                )):
            raise ValueError("invalid_jev_failure")

    @classmethod
    def from_payload(cls, payload: dict) -> JEVResponse:
        if type(payload) is not dict or set(payload) != set(cls.__dataclass_fields__):
            raise ValueError("invalid_jev_response_schema")
        return cls(**payload)


def _jev_binding(run_id: str, request: JEVRequest, model: ScoringModel,
                 snapshot: ScoringRegistrySnapshot, outcome: JEVResponse,
                 score_ready_at: datetime, available_at: datetime) -> str:
    return _jev_digest({
        "run_id": run_id, "request": request.request_sha256,
        "registry": snapshot.snapshot_sha256, "model": model.lineage_sha256,
        "outcome": vars(outcome), "score_ready_at": score_ready_at.isoformat(),
        "available_at": available_at.isoformat(), "schema": "jev-sentiment-v1",
    })


@dataclass(frozen=True)
class JEVResult:
    run_id: str
    request: JEVRequest
    model: ScoringModel
    snapshot: ScoringRegistrySnapshot
    score_ready_at: datetime
    available_at: datetime
    outcome: JEVResponse
    binding_sha256: str

    def __post_init__(self) -> None:
        _scoring_identifier(self.run_id, "run_id")
        if (type(self.request) is not JEVRequest or type(self.model) is not ScoringModel
                or type(self.outcome) is not JEVResponse):
            raise ValueError("invalid_jev_result_schema")
        if (type(self.snapshot) is not ScoringRegistrySnapshot
                or self.snapshot.get_model(self.model.name, self.model.version) != self.model):
            raise ValueError("invalid_jev_registry_binding")
        for field in ("score_ready_at", "available_at"):
            object.__setattr__(self, field, _scoring_timestamp(getattr(self, field), field))
        if (type(self.binding_sha256) is not str or self.binding_sha256 != _jev_binding(
                self.run_id, self.request, self.model, self.snapshot, self.outcome,
                self.score_ready_at, self.available_at)):
            raise ValueError("invalid_jev_result_binding")
        expected = max(
            self.request.source_available_at, self.score_ready_at,
            self.model.model_available_at, self.model.calibration_available_at,
        )
        if (self.available_at != expected
                or self.score_ready_at < self.request.source_available_at):
            raise ValueError("invalid_jev_availability")
        if self.request.language not in self.model.languages:
            raise ValueError("jev_language_not_supported")
        if self.outcome.status == "ok" and (
                self.request.evidence_mode != "retrospective"
                or self.available_at > self.request.cutoff_at):
            raise ValueError("jev_result_not_eligible")

    @property
    def registry_sha256(self) -> str:
        return self.snapshot.snapshot_sha256

    @property
    def historical_eligible(self) -> bool:
        # ponytail: no trusted calendar/readiness authority here; add only with its ledger.
        return False

    @property
    def replay_key(self) -> str:
        return self.binding_sha256


@dataclass(frozen=True)
class TypeSafeJEVScorer:
    snapshot: ScoringRegistrySnapshot
    model_name: str
    model_version: str
    run_id: str
    adapter: Callable[[JEVRequest, ScoringModel], JEVResponse]

    def __post_init__(self) -> None:
        if type(self.snapshot) is not ScoringRegistrySnapshot or not callable(self.adapter):
            raise ValueError("invalid_jev_scorer")
        _scoring_identifier(self.run_id, "run_id")
        self.snapshot.get_model(self.model_name, self.model_version)

    def score(self, request: JEVRequest, *, score_ready_at: datetime) -> JEVResult:
        if type(request) is not JEVRequest:
            raise ValueError("invalid_jev_request_schema")
        score_ready_at = _scoring_timestamp(score_ready_at, "score_ready_at")
        if score_ready_at < request.source_available_at:
            raise ValueError("invalid_jev_readiness_order")
        model = self.snapshot.get_model(self.model_name, self.model_version)
        if request.language not in model.languages:
            raise ValueError("jev_language_not_supported")
        available_at = max(
            request.source_available_at, score_ready_at,
            model.model_available_at, model.calibration_available_at,
        )
        if request.evidence_mode == "historical":
            outcome = JEVResponse("unavailable", None, None, None, "historical_readiness_unavailable")
        elif available_at > request.cutoff_at:
            outcome = JEVResponse("unavailable", None, None, None, "not_ready")
        else:
            try:
                outcome = self.adapter(request, model)
                if type(outcome) is not JEVResponse:
                    raise ValueError("invalid_jev_response_schema")
            except (TimeoutError, ConnectionError):
                outcome = JEVResponse("unavailable", None, None, None, "provider_unavailable")
            except ValueError:
                outcome = JEVResponse("error", None, None, None, "invalid_response")
            except Exception:
                outcome = JEVResponse("error", None, None, None, "provider_error")
        return JEVResult(
            self.run_id, request, model, self.snapshot,
            score_ready_at, available_at, outcome,
            _jev_binding(self.run_id, request, model, self.snapshot, outcome, score_ready_at, available_at),
        )
