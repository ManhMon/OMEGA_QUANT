from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import math
import re
from typing import Callable, Optional

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
