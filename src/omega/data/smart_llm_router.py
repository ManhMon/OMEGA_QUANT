"""SmartLLMRouter and Token Ledger (Component 2).

Manages LLM admission control, token budget reservation, deterministic 90/10 exploit/exploration queues,
and thread/async-safe token ledger for OMEGA_QUANT Hybrid Fundamental Alpha pipeline.
Achieves >= 80% token savings relative to naive all-symbol baseline policy.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import threading
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

ROUTER_VERSION = "smart_llm_router_v1"

# Reason Codes
REASON_SELECTED_EXPLOIT = "selected_exploit"
REASON_SELECTED_EXPLORATION = "selected_exploration"
REASON_FILTERED_VETO = "filtered_veto"
REASON_FILTERED_LOW_QUALITY = "filtered_low_quality"
REASON_FILTERED_LOW_SCORE = "filtered_low_score"
REASON_FILTERED_LOW_CONFIDENCE = "filtered_low_confidence"
REASON_FILTERED_INVALID = "filtered_invalid"
REASON_BUDGET_EXHAUSTED = "budget_exhausted"
REASON_LLM_MODE_OFF = "llm_mode_off"
REASON_UNSUPPORTED_SECURITY_SECTOR = "filtered_unsupported_security_sector"
REASON_STALE_OR_UNRESOLVED_REVISION = "filtered_stale_or_unresolved_revision"
REASON_EMPTY_PROMPT_FACTS = "filtered_empty_prompt_facts"
REASON_NO_TOKENIZER_OR_MAX_TOKENS = "filtered_no_tokenizer_or_max_tokens"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class CandidateRecord:
    """Record input to SmartLLMRouter."""
    symbol: str
    quant_score: Optional[float]
    quant_confidence: Optional[float]
    is_valid: bool
    is_veto: bool
    as_of: str
    prompt_payload: Optional[Dict[str, Any]] = None
    exact_prompt_tokens: int = 0
    max_tokens: int = 0
    data_quality_severe: bool = False
    stale_financials: bool = False
    unsupported_sector: bool = False
    empty_prompt_facts: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def request_reservation(self) -> int:
        return self.exact_prompt_tokens + self.max_tokens


@dataclass(frozen=True)
class RoutingDecision:
    """Per-symbol routing output from SmartLLMRouter."""
    symbol: str
    is_eligible: bool
    selected_for_llm: bool
    queue_type: Optional[str]  # 'exploit', 'exploration', or None
    priority_rank: Optional[int]
    reservation_tokens: int
    reason_code: str
    payload_sha256: Optional[str] = None
    as_of: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutingPlan:
    """Deterministic routing plan created before any provider network calls."""
    router_version: str
    as_of: str
    llm_mode: str
    macro_request_reservation: int
    macro_payload_sha256: Optional[str]
    baseline_reserved_tokens: int
    hard_token_cap: int
    total_planned_reservation: int
    decisions: List[RoutingDecision]
    selected_decisions: List[RoutingDecision]
    manifest_sha256: str
    exploit_budget_tokens: int
    exploration_budget_tokens: int
    exact_savings_ratio: float


class TokenLedger:
    """
    Thread/Async-safe Token Ledger using threading.RLock.
    Enforces invariant:
    committed_tokens + inflight_reserved_tokens + next_request_reservation <= hard_token_cap.
    """

    def __init__(self, hard_token_cap: int, baseline_tokens: int = 0):
        if hard_token_cap < 0:
            raise ValueError(f"hard_token_cap cannot be negative: {hard_token_cap}")
        self.hard_token_cap = int(hard_token_cap)
        self.baseline_tokens = int(baseline_tokens)
        self.committed_tokens: int = 0
        self.inflight_reserved_tokens: int = 0
        self.released_tokens: int = 0
        self.cached_tokens: int = 0
        self.skipped_tokens: int = 0
        self._lock = threading.RLock()
        self._reservations: Dict[str, int] = {}  # attempt_id -> reserved_tokens

    @property
    def remaining_cap(self) -> int:
        with self._lock:
            return self.hard_token_cap - (self.committed_tokens + self.inflight_reserved_tokens)

    async def reserve(self, attempt_id: str, tokens: int) -> bool:
        """
        Attempt to reserve tokens for an in-flight request.
        Exact equality to remaining_cap is accepted; 1 token over is rejected.
        """
        if tokens < 0:
            raise ValueError(f"Reservation tokens must be non-negative: {tokens}")
        if not attempt_id:
            raise ValueError("attempt_id must not be empty")

        with self._lock:
            if attempt_id in self._reservations:
                raise ValueError(f"Attempt ID {attempt_id} already has an active reservation")

            if self.committed_tokens + self.inflight_reserved_tokens + tokens <= self.hard_token_cap:
                self.inflight_reserved_tokens += tokens
                self._reservations[attempt_id] = tokens
                return True
            else:
                self.skipped_tokens += tokens
                return False

    async def commit_actual(self, attempt_id: str, actual_tokens: int) -> Tuple[int, int]:
        """
        Convert reservation to actual committed tokens upon successful response.
        Releases unused tokens.
        Validates actual_tokens <= reservation and (committed_tokens - reserved + actual_tokens) <= cap
        BEFORE removing reservation or mutating state.
        Returns (committed, released).
        """
        if actual_tokens < 0:
            raise ValueError(f"actual_tokens must be non-negative: {actual_tokens}")

        with self._lock:
            if attempt_id not in self._reservations:
                raise KeyError(f"No active reservation found for attempt {attempt_id}")

            reserved = self._reservations[attempt_id]
            if actual_tokens > reserved:
                raise ValueError(
                    f"Contract violation: actual provider tokens ({actual_tokens}) exceeded reservation ({reserved})"
                )

            projected_committed = self.committed_tokens + actual_tokens
            if projected_committed > self.hard_token_cap:
                raise ValueError(
                    f"Contract violation: committing {actual_tokens} tokens would exceed hard_token_cap ({self.hard_token_cap})"
                )

            # Mutation occurs strictly after all validation passes
            self._reservations.pop(attempt_id)
            released = reserved - actual_tokens
            self.inflight_reserved_tokens -= reserved
            self.committed_tokens += actual_tokens
            self.released_tokens += released
            return actual_tokens, released

    async def commit_full_timeout(self, attempt_id: str) -> int:
        """
        For timeouts or ambiguous network terminations after send,
        commit full reservation because actual token usage on server is unknown.
        """
        with self._lock:
            if attempt_id not in self._reservations:
                raise KeyError(f"No active reservation found for attempt {attempt_id}")

            reserved = self._reservations.pop(attempt_id)
            self.inflight_reserved_tokens -= reserved
            self.committed_tokens += reserved
            return reserved

    async def release_unattempted(self, attempt_id: str) -> int:
        """
        Release full reservation if failure occurred strictly before network send.
        """
        with self._lock:
            if attempt_id not in self._reservations:
                raise KeyError(f"No active reservation found for attempt {attempt_id}")

            reserved = self._reservations.pop(attempt_id)
            self.inflight_reserved_tokens -= reserved
            self.released_tokens += reserved
            return reserved

    async def record_cache_hit(self, tokens_saved: int) -> None:
        """Record exact cache hit tokens (0 provider cost)."""
        with self._lock:
            self.cached_tokens += int(tokens_saved)

    def snapshot(self) -> Dict[str, Any]:
        """Snapshot current accounting state."""
        with self._lock:
            return {
                "hard_token_cap": self.hard_token_cap,
                "baseline_tokens": self.baseline_tokens,
                "committed_tokens": self.committed_tokens,
                "inflight_reserved_tokens": self.inflight_reserved_tokens,
                "released_tokens": self.released_tokens,
                "cached_tokens": self.cached_tokens,
                "skipped_tokens": self.skipped_tokens,
                "remaining_cap": self.remaining_cap,
                "exact_savings_ratio": (
                    1.0 - (self.committed_tokens + self.inflight_reserved_tokens) / self.baseline_tokens
                    if self.baseline_tokens > 0 else 0.0
                ),
            }


class AsyncRouterPool:
    """
    Async concurrency controller using asyncio.Semaphore to cap active provider attempts.
    Each attempt executes inside semaphore and uses TokenLedger for reservation.
    """

    def __init__(self, ledger: TokenLedger, max_workers: int = 5):
        if max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {max_workers}")
        self.ledger = ledger
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)

    async def execute_attempt(
        self,
        attempt_id: str,
        reservation_tokens: int,
        worker_coro_fn: Callable[[], Any],
        is_pre_send_failure: Callable[[Exception], bool] = lambda _: False,
    ) -> Tuple[bool, Any, Optional[str]]:
        """
        Execute worker call within semaphore and token ledger reservation.
        Returns (success, result_or_none, error_msg_or_none).
        """
        async with self.semaphore:
            # 1. Acquire reservation in ledger
            reserved = await self.ledger.reserve(attempt_id, reservation_tokens)
            if not reserved:
                return False, None, REASON_BUDGET_EXHAUSTED

            # 2. Execute network worker coroutine (ledger lock is released during I/O)
            try:
                result = await worker_coro_fn()
                # If result provides actual tokens, commit actual; else commit reserved
                actual_tokens = getattr(result, "total_tokens", None)
                if actual_tokens is not None and isinstance(actual_tokens, int):
                    await self.ledger.commit_actual(attempt_id, actual_tokens)
                else:
                    await self.ledger.commit_actual(attempt_id, reservation_tokens)
                return True, result, None
            except asyncio.CancelledError:
                # Ambiguous state -> commit full timeout reservation
                await self.ledger.commit_full_timeout(attempt_id)
                raise
            except Exception as exc:
                if is_pre_send_failure(exc):
                    await self.ledger.release_unattempted(attempt_id)
                else:
                    # Ambiguous/network exception after send -> commit full
                    await self.ledger.commit_full_timeout(attempt_id)
                return False, None, str(exc)


class SmartLLMRouter:
    """
    SmartLLMRouter (Component 2).
    Evaluates hard exclusion filters, sorts deterministic exploit & exploration queues (90/10 split),
    calculates naive baseline & hard cap (<=20% baseline, >=80% savings),
    and produces an immutable RoutingPlan before any external provider calls.
    """

    def __init__(
        self,
        router_version: str = ROUTER_VERSION,
        token_cap_ratio: float = 0.20,
        exploit_ratio: float = 0.90,
        regular_min_score: float = -0.20,
        regular_min_confidence: float = 0.70,
    ):
        if not (0.0 < token_cap_ratio <= 0.20):
            raise ValueError(f"token_cap_ratio must be in (0.0, 0.20], got {token_cap_ratio}")
        if not (0.0 <= exploit_ratio <= 1.0):
            raise ValueError(f"exploit_ratio must be in [0.0, 1.0], got {exploit_ratio}")

        self.router_version = router_version
        self.token_cap_ratio = token_cap_ratio
        self.exploit_ratio = exploit_ratio
        self.regular_min_score = regular_min_score
        self.regular_min_confidence = regular_min_confidence

    @staticmethod
    def _exploration_hash(symbol: str, as_of: str, router_version: str) -> str:
        """Stable SHA256 hash for exploration queue sorting (no process-random seeds)."""
        key = f"{symbol}|{as_of}|{router_version}".encode("utf-8")
        return hashlib.sha256(key).hexdigest()

    def plan_routing(
        self,
        records: Sequence[CandidateRecord],
        as_of: str,
        llm_mode: str = "auto",
        macro_payload: Optional[Dict[str, Any]] = None,
        macro_exact_prompt_tokens: int = 0,
        macro_max_tokens: int = 0,
    ) -> RoutingPlan:
        """
        Build immutable RoutingPlan with hard exclusions, naive baseline, hard token cap,
        and deterministic 90/10 exploit/exploration selection.
        """
        if llm_mode not in {"off", "auto", "required"}:
            raise ValueError(f"Invalid llm_mode: {llm_mode}. Must be off, auto, or required.")

        macro_res = (macro_exact_prompt_tokens + macro_max_tokens) if macro_payload else 0
        macro_sha256 = _sha256(_canonical_bytes(macro_payload)) if macro_payload else None

        # 1. Deduplicate/Validate input records by (symbol, as_of)
        unique_records_dict: Dict[Tuple[str, str], CandidateRecord] = {}
        for r in records:
            key = (r.symbol, r.as_of)
            if key not in unique_records_dict:
                unique_records_dict[key] = r
            else:
                logger.warning("Duplicate candidate record found for %s on %s; keeping first occurrence.", r.symbol, r.as_of)
        unique_records = list(unique_records_dict.values())

        # 2. Compute Naive Micro Set baseline
        # Naive set is every quant-scorable symbol (is_valid=True)
        naive_micro_set = [r for r in unique_records if r.is_valid and r.quant_score is not None]
        naive_micro_tokens = sum(r.request_reservation for r in naive_micro_set)
        baseline_reserved_tokens = macro_res + naive_micro_tokens

        # Hard token cap: floor(token_cap_ratio * baseline_reserved_tokens)
        hard_token_cap = math.floor(self.token_cap_ratio * baseline_reserved_tokens)

        # If llm_mode == 'off', reject all
        if llm_mode == "off":
            decisions = [
                RoutingDecision(
                    symbol=r.symbol,
                    is_eligible=False,
                    selected_for_llm=False,
                    queue_type=None,
                    priority_rank=None,
                    reservation_tokens=r.request_reservation,
                    reason_code=REASON_LLM_MODE_OFF,
                    payload_sha256=_sha256(_canonical_bytes(r.prompt_payload)) if r.prompt_payload else None,
                    as_of=r.as_of or as_of,
                )
                for r in unique_records
            ]
            # Deterministic ordering: sort all output decisions canonically by (symbol, as_of, payload_sha256) ascending
            decisions.sort(key=lambda d: (d.symbol, str(d.as_of), d.payload_sha256 or ""))
            manifest_bytes = _canonical_bytes([asdict(d) for d in decisions])
            return RoutingPlan(
                router_version=self.router_version,
                as_of=as_of,
                llm_mode=llm_mode,
                macro_request_reservation=macro_res,
                macro_payload_sha256=macro_sha256,
                baseline_reserved_tokens=baseline_reserved_tokens,
                hard_token_cap=hard_token_cap,
                total_planned_reservation=0,
                decisions=decisions,
                selected_decisions=[],
                manifest_sha256=_sha256(manifest_bytes),
                exploit_budget_tokens=0,
                exploration_budget_tokens=0,
                exact_savings_ratio=1.0,
            )

        # 3. Hard Exclusion Filtering & Candidate Partitioning
        exploit_candidates: List[CandidateRecord] = []
        exploration_candidates: List[CandidateRecord] = []
        rejected_map: Dict[Tuple[str, str], Tuple[str, Optional[str]]] = {}  # (symbol, as_of) -> (reason_code, payload_sha)

        effective_min_score = max(-0.20, self.regular_min_score)
        effective_min_confidence = max(0.70, self.regular_min_confidence)

        for r in unique_records:
            p_sha = _sha256(_canonical_bytes(r.prompt_payload)) if r.prompt_payload else None
            key = (r.symbol, r.as_of)

            # Hard exclusions:
            if not r.is_valid or r.quant_score is None or r.quant_confidence is None:
                rejected_map[key] = (REASON_FILTERED_INVALID, p_sha)
                continue
            if r.is_veto:
                rejected_map[key] = (REASON_FILTERED_VETO, p_sha)
                continue
            if r.stale_financials:
                rejected_map[key] = (REASON_STALE_OR_UNRESOLVED_REVISION, p_sha)
                continue
            if r.unsupported_sector:
                rejected_map[key] = (REASON_UNSUPPORTED_SECURITY_SECTOR, p_sha)
                continue
            if r.empty_prompt_facts or not r.prompt_payload:
                rejected_map[key] = (REASON_EMPTY_PROMPT_FACTS, p_sha)
                continue
            if r.exact_prompt_tokens <= 0 or r.max_tokens <= 0:
                rejected_map[key] = (REASON_NO_TOKENIZER_OR_MAX_TOKENS, p_sha)
                continue
            if r.quant_score < effective_min_score:
                rejected_map[key] = (REASON_FILTERED_LOW_SCORE, p_sha)
                continue
            if r.quant_confidence < effective_min_confidence:
                rejected_map[key] = (REASON_FILTERED_LOW_CONFIDENCE, p_sha)
                continue

            # Regular eligibility V1 checks:
            # - quant_score >= effective_min_score (>= -0.20)
            # - quant_confidence >= effective_min_confidence (>= 0.70)
            # - no severe data quality flag
            if not r.data_quality_severe:
                exploit_candidates.append(r)
            else:
                # Scorable, valid, non-veto candidates that meet score & confidence but have data_quality_severe enter exploration
                exploration_candidates.append(r)

        # 4. Deterministic Sorting
        # Exploit sort:
        # 1. quant_score desc (-quant_score)
        # 2. quant_confidence desc (-quant_confidence)
        # 3. request_reservation asc (exact_prompt_tokens + max_tokens)
        # 4. symbol asc
        # 5. as_of asc
        exploit_candidates.sort(
            key=lambda x: (
                -(x.quant_score if x.quant_score is not None else -999.0),
                -(x.quant_confidence if x.quant_confidence is not None else -999.0),
                x.request_reservation,
                x.symbol,
                str(x.as_of),
            )
        )

        # Exploration sort:
        # Stable hash of (symbol + as_of + router_version) asc, tie-break symbol asc, as_of asc
        exploration_candidates.sort(
            key=lambda x: (
                self._exploration_hash(x.symbol, x.as_of or as_of, self.router_version),
                x.symbol,
                str(x.as_of),
            )
        )

        # 5. Token Budget Allocation & Selection
        # Available budget for micro candidates = hard_token_cap - macro_res
        available_micro_cap = max(0, hard_token_cap - macro_res)
        exploration_budget = math.floor(available_micro_cap * 0.10)
        exploit_budget = min(
            math.floor(available_micro_cap * self.exploit_ratio),
            available_micro_cap - exploration_budget,
        )

        selected_exploit: List[CandidateRecord] = []
        unselected_exploit: List[CandidateRecord] = []
        spent_exploit = 0

        for r in exploit_candidates:
            if (
                spent_exploit + r.request_reservation <= exploit_budget
                and (spent_exploit + r.request_reservation + macro_res) <= hard_token_cap
            ):
                spent_exploit += r.request_reservation
                selected_exploit.append(r)
            else:
                unselected_exploit.append(r)

        # Exploration budget cap: strict 10% ceiling on exploration tokens (never exceed exploration_budget)
        # Unselected exploit candidates that meet score & confidence can be considered for remaining exploration budget
        full_exploration_pool = exploration_candidates + unselected_exploit
        full_exploration_pool.sort(
            key=lambda x: (
                self._exploration_hash(x.symbol, x.as_of or as_of, self.router_version),
                x.symbol,
                str(x.as_of),
            )
        )

        selected_exploration: List[CandidateRecord] = []
        spent_exploration = 0

        for r in full_exploration_pool:
            if (
                spent_exploration + r.request_reservation <= exploration_budget
                and (spent_exploit + spent_exploration + r.request_reservation + macro_res) <= hard_token_cap
            ):
                spent_exploration += r.request_reservation
                selected_exploration.append(r)
            else:
                p_sha = _sha256(_canonical_bytes(r.prompt_payload)) if r.prompt_payload else None
                key = (r.symbol, r.as_of)
                if key not in rejected_map:
                    if r.data_quality_severe:
                        rejected_map[key] = (REASON_FILTERED_LOW_QUALITY, p_sha)
                    else:
                        rejected_map[key] = (REASON_BUDGET_EXHAUSTED, p_sha)

        total_micro_spent = spent_exploit + spent_exploration
        total_planned_reservation = (macro_res if (selected_exploit or selected_exploration) else 0) + total_micro_spent

        # 6. Build Decision List for All Unique Records
        decisions: List[RoutingDecision] = []
        selected_decisions: List[RoutingDecision] = []

        selected_exploit_keys = {(r.symbol, r.as_of) for r in selected_exploit}
        selected_exploration_keys = {(r.symbol, r.as_of) for r in selected_exploration}

        # Build rank lookups keyed by (symbol, as_of)
        rank_map: Dict[Tuple[str, str], int] = {}
        for rank, r in enumerate(selected_exploit, start=1):
            rank_map[(r.symbol, r.as_of)] = rank
        for rank, r in enumerate(selected_exploration, start=len(selected_exploit) + 1):
            rank_map[(r.symbol, r.as_of)] = rank

        for r in unique_records:
            p_sha = _sha256(_canonical_bytes(r.prompt_payload)) if r.prompt_payload else None
            key = (r.symbol, r.as_of)
            if key in selected_exploit_keys:
                d = RoutingDecision(
                    symbol=r.symbol,
                    is_eligible=True,
                    selected_for_llm=True,
                    queue_type="exploit",
                    priority_rank=rank_map[key],
                    reservation_tokens=r.request_reservation,
                    reason_code=REASON_SELECTED_EXPLOIT,
                    payload_sha256=p_sha,
                    as_of=r.as_of or as_of,
                )
                decisions.append(d)
                selected_decisions.append(d)
            elif key in selected_exploration_keys:
                d = RoutingDecision(
                    symbol=r.symbol,
                    is_eligible=True,
                    selected_for_llm=True,
                    queue_type="exploration",
                    priority_rank=rank_map[key],
                    reservation_tokens=r.request_reservation,
                    reason_code=REASON_SELECTED_EXPLORATION,
                    payload_sha256=p_sha,
                    as_of=r.as_of or as_of,
                )
                decisions.append(d)
                selected_decisions.append(d)
            else:
                reason, _ = rejected_map.get(key, (REASON_BUDGET_EXHAUSTED, p_sha))
                d = RoutingDecision(
                    symbol=r.symbol,
                    is_eligible=False,
                    selected_for_llm=False,
                    queue_type=None,
                    priority_rank=None,
                    reservation_tokens=r.request_reservation,
                    reason_code=reason,
                    payload_sha256=p_sha,
                    as_of=r.as_of or as_of,
                )
                decisions.append(d)

        # Deterministic ordering: sort all output decisions canonically by (symbol, as_of, payload_sha256) ascending
        decisions.sort(key=lambda d: (d.symbol, str(d.as_of), d.payload_sha256 or ""))
        selected_decisions.sort(key=lambda d: (d.symbol, str(d.as_of), d.payload_sha256 or ""))

        manifest_bytes = _canonical_bytes([asdict(d) for d in decisions])
        exact_savings_ratio = (
            1.0 - (total_planned_reservation / baseline_reserved_tokens)
            if baseline_reserved_tokens > 0 else 1.0
        )

        return RoutingPlan(
            router_version=self.router_version,
            as_of=as_of,
            llm_mode=llm_mode,
            macro_request_reservation=macro_res,
            macro_payload_sha256=macro_sha256,
            baseline_reserved_tokens=baseline_reserved_tokens,
            hard_token_cap=hard_token_cap,
            total_planned_reservation=total_planned_reservation,
            decisions=decisions,
            selected_decisions=selected_decisions,
            manifest_sha256=_sha256(manifest_bytes),
            exploit_budget_tokens=exploit_budget,
            exploration_budget_tokens=exploration_budget,
            exact_savings_ratio=exact_savings_ratio,
        )
