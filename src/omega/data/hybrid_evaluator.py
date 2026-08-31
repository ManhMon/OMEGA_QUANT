"""
Hybrid Evaluator (Component 3).

Combines quantitative and LLM evaluation into an ensemble hybrid alpha score:
- Initial raw weights: Quant base = 0.75, LLM maximum = 0.25
- Scaled LLM weight: raw_llm_weight = 0.25 * llm_confidence (when valid and llm_confidence >= 0.40)
- Renormalized effective weights summing to 1.0 (effective_llm_weight <= 0.25)
- Fallback to quant-only (effective weights 1.0 / 0.0) when LLM missing, invalid, or llm_confidence < 0.40
- Hard veto precedence: hard veto forces hybrid_score = -1.0, decision = 'reject', effective_llm_weight = 0.0
- Quant null handling: quant score null yields hybrid null (LLM cannot generate independent score)
- Decision bands:
    * reject: hard veto or score <= -0.60
    * avoid: -0.60 < score < -0.20
    * neutral: -0.20 <= score < 0.20
    * positive: 0.20 <= score < 0.60
    * strong_positive: score >= 0.60
- Disagreement logging: abs(llm_score - quant_score) >= 0.50 logged as 'llm_quant_disagreement'
- Pre-publish fail-safe validator with fail-closed integrity checks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

HYBRID_EVALUATOR_VERSION = "hybrid_evaluator_v1"

# Decision band constants
DECISION_REJECT = "reject"
DECISION_AVOID = "avoid"
DECISION_NEUTRAL = "neutral"
DECISION_POSITIVE = "positive"
DECISION_STRONG_POSITIVE = "strong_positive"

# Weight & threshold constants
MANDATORY_RAW_QUANT_WEIGHT = 0.75
MANDATORY_RAW_LLM_MAX_WEIGHT = 0.25
MANDATORY_LLM_CONFIDENCE_FLOOR = 0.40
RAW_QUANT_BASE_WEIGHT = MANDATORY_RAW_QUANT_WEIGHT
RAW_LLM_MAX_WEIGHT = MANDATORY_RAW_LLM_MAX_WEIGHT
LLM_CONFIDENCE_THRESHOLD = MANDATORY_LLM_CONFIDENCE_FLOOR
DISAGREEMENT_THRESHOLD = 0.50


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _parse_iso_to_utc(dt_val: Any) -> datetime:
    """Parse string/timestamp/datetime to UTC timezone-aware datetime."""
    if dt_val is None:
        raise ValueError("Invalid datetime: None")
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            return dt_val.replace(tzinfo=timezone.utc)
        return dt_val.astimezone(timezone.utc)
    if not isinstance(dt_val, str):
        raise ValueError(f"Unsupported datetime type: {type(dt_val).__name__}")
    str_val = dt_val.strip()
    if not str_val or str_val.lower() in {"nat", "nan", "none", "null", "undefined", "inf", "-inf"}:
        raise ValueError(f"Invalid datetime string: {str_val!r}")
    if str_val.endswith("Z"):
        str_val = str_val[:-1] + "+00:00"
    dt = datetime.fromisoformat(str_val)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class HybridEvaluationResult:
    """Immutable result of HybridEvaluator per-symbol ensemble evaluation."""
    symbol: str
    decision_cutoff: str
    knowledge_cutoff: str
    hybrid_score: Optional[float]
    decision: Optional[str]
    effective_quant_weight: float
    effective_llm_weight: float
    quant_score: Optional[float]
    quant_confidence: float
    llm_score: Optional[float]
    llm_confidence: float
    is_veto: bool
    is_fallback: bool
    fallback_reason: Optional[str] = None
    has_disagreement: bool = False
    disagreement_magnitude: Optional[float] = None
    lineage_identity_hash: str = ""
    evaluator_version: str = HYBRID_EVALUATOR_VERSION
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HybridEvaluator:
    """
    Ensemble evaluator combining Quant and LLM fundamental signals.
    """

    def __init__(
        self,
        raw_quant_weight: float = RAW_QUANT_BASE_WEIGHT,
        raw_llm_max_weight: float = RAW_LLM_MAX_WEIGHT,
        llm_confidence_threshold: float = LLM_CONFIDENCE_THRESHOLD,
        disagreement_threshold: float = DISAGREEMENT_THRESHOLD,
        evaluator_version: str = HYBRID_EVALUATOR_VERSION,
    ):
        if raw_quant_weight != RAW_QUANT_BASE_WEIGHT:
            raise ValueError(
                f"raw_quant_weight must be exactly {RAW_QUANT_BASE_WEIGHT}, got {raw_quant_weight} (constructor bypass forbidden)"
            )
        if raw_llm_max_weight != RAW_LLM_MAX_WEIGHT:
            raise ValueError(
                f"raw_llm_max_weight must be exactly {RAW_LLM_MAX_WEIGHT}, got {raw_llm_max_weight} (constructor bypass forbidden)"
            )
        if not (0.0 <= llm_confidence_threshold <= 1.0):
            raise ValueError(f"llm_confidence_threshold must be in [0, 1], got {llm_confidence_threshold}")
        if disagreement_threshold < 0:
            raise ValueError(f"disagreement_threshold must be non-negative, got {disagreement_threshold}")

        self.raw_quant_weight = RAW_QUANT_BASE_WEIGHT
        self.raw_llm_max_weight = RAW_LLM_MAX_WEIGHT
        self.llm_confidence_threshold = llm_confidence_threshold
        self.disagreement_threshold = disagreement_threshold
        self.evaluator_version = evaluator_version

    @staticmethod
    def map_decision_band(score: Optional[float], is_veto: bool = False) -> Optional[str]:
        """
        Maps continuous score to decision band:
        - is_veto or score <= -0.60 -> reject
        - -0.60 < score < -0.20 -> avoid
        - -0.20 <= score < 0.20 -> neutral
        - 0.20 <= score < 0.60 -> positive
        - score >= 0.60 -> strong_positive
        If score is None (and not veto), returns None.
        """
        if is_veto:
            return DECISION_REJECT
        if score is None:
            return None
        if not math.isfinite(score):
            return None

        s = float(score)
        if s <= -0.60:
            return DECISION_REJECT
        elif s < -0.20:
            return DECISION_AVOID
        elif s < 0.20:
            return DECISION_NEUTRAL
        elif s < 0.60:
            return DECISION_POSITIVE
        else:
            return DECISION_STRONG_POSITIVE

    def compute_weights(
        self,
        llm_score: Optional[float],
        llm_confidence: Optional[float],
        llm_valid: bool = True,
    ) -> Tuple[float, float, bool, Optional[str]]:
        """
        Computes effective weights (quant_weight, llm_weight, is_fallback, fallback_reason).
        Validates LLM score range in [-1.0, 1.0] and confidence in [0.40, 1.0].
        If outside range, falls back to exact quant-only (weights 1.0/0.0).
        """
        if (
            not llm_valid
            or llm_score is None
            or not math.isfinite(llm_score)
            or llm_confidence is None
            or not math.isfinite(llm_confidence)
        ):
            return 1.0, 0.0, True, "llm_missing_or_invalid"

        score_val = float(llm_score)
        if score_val < -1.0 or score_val > 1.0:
            return 1.0, 0.0, True, f"llm_score_out_of_range ({score_val:.4f} not in [-1.0, 1.0])"

        effective_conf_threshold = max(MANDATORY_LLM_CONFIDENCE_FLOOR, self.llm_confidence_threshold)
        conf = float(llm_confidence)
        if conf > 1.0 or conf < effective_conf_threshold:
            return 1.0, 0.0, True, f"llm_confidence_out_of_range ({conf:.4f} not in [{effective_conf_threshold:.2f}, 1.0])"

        # Scale LLM raw weight by confidence
        conf_clamped = min(max(conf, 0.0), 1.0)
        raw_llm = MANDATORY_RAW_LLM_MAX_WEIGHT * conf_clamped
        raw_quant = MANDATORY_RAW_QUANT_WEIGHT

        total_raw = raw_quant + raw_llm
        if total_raw <= 0:
            return 1.0, 0.0, True, "zero_total_raw_weight"

        eff_llm = min(raw_llm / total_raw, MANDATORY_RAW_LLM_MAX_WEIGHT)
        eff_quant = 1.0 - eff_llm

        return eff_quant, eff_llm, False, None

    def evaluate_symbol(
        self,
        symbol: str,
        decision_cutoff: str,
        knowledge_cutoff: str,
        quant_score: Optional[float],
        quant_confidence: float,
        is_veto: bool = False,
        llm_score: Optional[float] = None,
        llm_confidence: float = 0.0,
        llm_valid: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HybridEvaluationResult:
        """
        Performs hybrid evaluation for a single symbol.
        Evaluation order:
        1. If unscorable (quant_score is None and not veto): alpha null, no ensemble.
        2. If hard veto: hybrid_score = -1.0, decision = 'reject', llm_weight = 0.0.
        3. If quant valid: compute effective weights, check disagreement, calculate hybrid score.
        """
        meta = dict(metadata or {})

        # Check PIT clock integrity
        d_dt = _parse_iso_to_utc(decision_cutoff)
        k_dt = _parse_iso_to_utc(knowledge_cutoff)
        if k_dt > d_dt:
            raise ValueError(f"Clock order violation: knowledge_cutoff ({knowledge_cutoff}) > decision_cutoff ({decision_cutoff})")

        d_iso = d_dt.isoformat()
        k_iso = k_dt.isoformat()

        # 1. Hard veto precedence
        if is_veto:
            hybrid_score = -1.0
            decision = DECISION_REJECT
            eff_quant = 1.0
            eff_llm = 0.0
            is_fallback = False
            fallback_reason = "hard_veto_override"
            has_disagreement = False
            disagreement_mag = None

            if (
                quant_score is not None
                and math.isfinite(quant_score)
                and llm_score is not None
                and math.isfinite(llm_score)
            ):
                q_val = float(quant_score)
                l_val = float(llm_score)
                disagreement_mag = abs(l_val - q_val)
                if disagreement_mag >= self.disagreement_threshold:
                    has_disagreement = True
                    logger.warning(
                        "llm_quant_disagreement detected on veto for %s: quant=%.4f, llm=%.4f, diff=%.4f",
                        symbol,
                        q_val,
                        l_val,
                        disagreement_mag,
                    )

            lineage_dict = {
                "symbol": symbol,
                "decision_cutoff": d_iso,
                "knowledge_cutoff": k_iso,
                "quant_score": quant_score,
                "quant_confidence": quant_confidence,
                "llm_score": llm_score,
                "llm_confidence": llm_confidence,
                "is_veto": True,
                "evaluator_version": self.evaluator_version,
            }
            lineage_hash = _sha256(_canonical_bytes(lineage_dict))

            return HybridEvaluationResult(
                symbol=symbol,
                decision_cutoff=d_iso,
                knowledge_cutoff=k_iso,
                hybrid_score=hybrid_score,
                decision=decision,
                effective_quant_weight=eff_quant,
                effective_llm_weight=eff_llm,
                quant_score=quant_score,
                quant_confidence=quant_confidence,
                llm_score=llm_score,
                llm_confidence=llm_confidence,
                is_veto=True,
                is_fallback=is_fallback,
                fallback_reason=fallback_reason,
                has_disagreement=has_disagreement,
                disagreement_magnitude=disagreement_mag,
                lineage_identity_hash=lineage_hash,
                evaluator_version=self.evaluator_version,
                metadata=meta,
            )

        # 2. Unscorable quant (quant_score is None)
        if quant_score is None or not math.isfinite(quant_score):
            lineage_dict = {
                "symbol": symbol,
                "decision_cutoff": d_iso,
                "knowledge_cutoff": k_iso,
                "quant_score": None,
                "quant_confidence": quant_confidence,
                "llm_score": llm_score,
                "llm_confidence": llm_confidence,
                "is_veto": False,
                "evaluator_version": self.evaluator_version,
            }
            lineage_hash = _sha256(_canonical_bytes(lineage_dict))

            return HybridEvaluationResult(
                symbol=symbol,
                decision_cutoff=d_iso,
                knowledge_cutoff=k_iso,
                hybrid_score=None,
                decision=None,
                effective_quant_weight=1.0,
                effective_llm_weight=0.0,
                quant_score=None,
                quant_confidence=quant_confidence,
                llm_score=llm_score,
                llm_confidence=llm_confidence,
                is_veto=False,
                is_fallback=True,
                fallback_reason="unscorable_quant",
                has_disagreement=False,
                disagreement_magnitude=None,
                lineage_identity_hash=lineage_hash,
                evaluator_version=self.evaluator_version,
                metadata=meta,
            )

        # 3. Valid Quant Score: Determine weights & ensemble
        eff_quant, eff_llm, is_fallback, fallback_reason = self.compute_weights(
            llm_score=llm_score,
            llm_confidence=llm_confidence,
            llm_valid=llm_valid,
        )

        q_score = float(quant_score)
        has_disagreement = False
        disagreement_mag = None

        if is_fallback:
            hybrid_score = q_score
        else:
            l_score = float(llm_score)  # type: ignore[arg-type]
            disagreement_mag = abs(l_score - q_score)
            if disagreement_mag >= self.disagreement_threshold:
                has_disagreement = True
                logger.info(
                    "llm_quant_disagreement detected for %s: quant=%.4f, llm=%.4f, diff=%.4f",
                    symbol,
                    q_score,
                    l_score,
                    disagreement_mag,
                )

            raw_ensemble = eff_quant * q_score + eff_llm * l_score
            hybrid_score = float(min(max(raw_ensemble, -1.0), 1.0))

        decision = self.map_decision_band(hybrid_score, is_veto=False)

        lineage_dict = {
            "symbol": symbol,
            "decision_cutoff": d_iso,
            "knowledge_cutoff": k_iso,
            "quant_score": quant_score,
            "quant_confidence": quant_confidence,
            "llm_score": llm_score,
            "llm_confidence": llm_confidence,
            "is_veto": False,
            "evaluator_version": self.evaluator_version,
        }
        lineage_hash = _sha256(_canonical_bytes(lineage_dict))

        return HybridEvaluationResult(
            symbol=symbol,
            decision_cutoff=d_iso,
            knowledge_cutoff=k_iso,
            hybrid_score=hybrid_score,
            decision=decision,
            effective_quant_weight=eff_quant,
            effective_llm_weight=eff_llm,
            quant_score=quant_score,
            quant_confidence=quant_confidence,
            llm_score=llm_score,
            llm_confidence=llm_confidence,
            is_veto=False,
            is_fallback=is_fallback,
            fallback_reason=fallback_reason,
            has_disagreement=has_disagreement,
            disagreement_magnitude=disagreement_mag,
            lineage_identity_hash=lineage_hash,
            evaluator_version=self.evaluator_version,
            metadata=meta,
        )

    def evaluate_batch(
        self,
        records: Sequence[Dict[str, Any]],
        decision_cutoff: str,
        knowledge_cutoff: str,
    ) -> List[HybridEvaluationResult]:
        """
        Evaluates a batch of candidate records deterministically.
        """
        results: List[HybridEvaluationResult] = []
        for rec in records:
            res = self.evaluate_symbol(
                symbol=rec["symbol"],
                decision_cutoff=decision_cutoff,
                knowledge_cutoff=knowledge_cutoff,
                quant_score=rec.get("quant_score"),
                quant_confidence=rec.get("quant_confidence", 0.0),
                is_veto=rec.get("is_veto", False),
                llm_score=rec.get("llm_score"),
                llm_confidence=rec.get("llm_confidence", 0.0),
                llm_valid=rec.get("llm_valid", True),
                metadata=rec.get("metadata"),
            )
            results.append(res)
        return results


def validate_pre_publish_records(
    records: Sequence[HybridEvaluationResult],
    tolerance: float = 1e-6,
) -> Tuple[bool, List[str]]:
    """
    Fail-safe pre-publish validation:
    1. Lineage identity uniqueness across candidate set.
    2. Recomputed canonical lineage hash matches stored lineage_identity_hash.
    3. Score/confidence bounds: score in [-1.0, 1.0] when not None, confidences in [0.0, 1.0].
    4. Hard veto rows have effective_llm_weight == 0.0, hybrid_score == -1.0, and decision == 'reject'.
    5. Fallback rows have hybrid_score == quant_score (within tolerance) when quant_score is not None.
    6. Effective weights sum to 1.0 (within tolerance) for valid/scorable rows.
    7. Effective LLM weight <= 0.25 (capped).
    8. knowledge_cutoff <= decision_cutoff for every row.
    9. Quant score None must have hybrid_score None and decision None.
    10. Decision matches expected band.
    11. Recomputes expected mandatory weights from inputs independently.
    """
    # Hardcode strict fixed tolerance tol=1e-6, never relaxing for caller parameter
    tol = 1e-6

    errors: List[str] = []
    seen_identities: set[str] = set()

    for idx, r in enumerate(records):
        prefix = f"Row {idx} ({r.symbol})"

        # 1. Uniqueness
        if r.lineage_identity_hash in seen_identities:
            errors.append(f"{prefix}: duplicate lineage_identity_hash {r.lineage_identity_hash}")
        seen_identities.add(r.lineage_identity_hash)

        # 2. Recomputed hash match
        recomp_dict = {
            "symbol": r.symbol,
            "decision_cutoff": r.decision_cutoff,
            "knowledge_cutoff": r.knowledge_cutoff,
            "quant_score": r.quant_score,
            "quant_confidence": r.quant_confidence,
            "llm_score": r.llm_score,
            "llm_confidence": r.llm_confidence,
            "is_veto": r.is_veto,
            "evaluator_version": r.evaluator_version,
        }
        expected_hash = _sha256(_canonical_bytes(recomp_dict))
        if r.lineage_identity_hash != expected_hash:
            errors.append(
                f"{prefix}: hash mismatch (stored={r.lineage_identity_hash}, computed={expected_hash})"
            )

        # 8. Clocks
        try:
            d_dt = _parse_iso_to_utc(r.decision_cutoff)
            k_dt = _parse_iso_to_utc(r.knowledge_cutoff)
            if k_dt > d_dt:
                errors.append(f"{prefix}: knowledge_cutoff > decision_cutoff")
        except Exception as e:
            errors.append(f"{prefix}: invalid clocks ({e})")

        # 3. Bounds
        if r.hybrid_score is not None:
            if not math.isfinite(r.hybrid_score) or not (-1.0 - tol <= r.hybrid_score <= 1.0 + tol):
                errors.append(f"{prefix}: hybrid_score out of bounds: {r.hybrid_score}")
        if r.quant_score is not None:
            if not math.isfinite(r.quant_score) or not (-1.0 - tol <= r.quant_score <= 1.0 + tol):
                errors.append(f"{prefix}: quant_score out of bounds: {r.quant_score}")
        if r.llm_score is not None:
            if not math.isfinite(r.llm_score) or not (-1.0 - tol <= r.llm_score <= 1.0 + tol):
                errors.append(f"{prefix}: llm_score out of bounds: {r.llm_score}")
        if not (0.0 - tol <= r.quant_confidence <= 1.0 + tol):
            errors.append(f"{prefix}: quant_confidence out of bounds: {r.quant_confidence}")
        if not (0.0 - tol <= r.llm_confidence <= 1.0 + tol):
            errors.append(f"{prefix}: llm_confidence out of bounds: {r.llm_confidence}")

        # Independent weight recomputation from inputs
        if r.is_veto or r.quant_score is None:
            exp_eff_quant = 1.0
            exp_eff_llm = 0.0
        else:
            # Check LLM validity and bounds
            llm_valid = (
                r.llm_score is not None
                and math.isfinite(r.llm_score)
                and -1.0 <= r.llm_score <= 1.0
                and r.llm_confidence is not None
                and math.isfinite(r.llm_confidence)
                and MANDATORY_LLM_CONFIDENCE_FLOOR <= r.llm_confidence <= 1.0
            )
            if not llm_valid:
                exp_eff_quant = 1.0
                exp_eff_llm = 0.0
            else:
                raw_llm = MANDATORY_RAW_LLM_MAX_WEIGHT * r.llm_confidence
                raw_quant = MANDATORY_RAW_QUANT_WEIGHT
                tot_raw = raw_quant + raw_llm
                exp_eff_llm = min(raw_llm / tot_raw, MANDATORY_RAW_LLM_MAX_WEIGHT)
                exp_eff_quant = 1.0 - exp_eff_llm

        if abs(r.effective_quant_weight - exp_eff_quant) > tol:
            errors.append(
                f"{prefix}: effective_quant_weight mismatch (stored={r.effective_quant_weight}, expected={exp_eff_quant})"
            )
        if abs(r.effective_llm_weight - exp_eff_llm) > tol:
            errors.append(
                f"{prefix}: effective_llm_weight mismatch (stored={r.effective_llm_weight}, expected={exp_eff_llm})"
            )

        # 4. Hard Veto
        if r.is_veto:
            if abs(r.effective_llm_weight - 0.0) > tol:
                errors.append(f"{prefix}: veto row has non-zero LLM weight {r.effective_llm_weight}")
            if r.hybrid_score is None or abs(r.hybrid_score - (-1.0)) > tol:
                errors.append(f"{prefix}: veto row hybrid_score != -1.0 ({r.hybrid_score})")
            if r.decision != DECISION_REJECT:
                errors.append(f"{prefix}: veto row decision != reject ({r.decision})")

        # 5. Fallback
        if r.is_fallback and not r.is_veto and r.quant_score is not None:
            if r.hybrid_score is None or abs(r.hybrid_score - r.quant_score) > tol:
                errors.append(f"{prefix}: fallback row hybrid_score ({r.hybrid_score}) != quant_score ({r.quant_score})")
            if abs(r.effective_llm_weight - 0.0) > tol:
                errors.append(f"{prefix}: fallback row has non-zero LLM weight {r.effective_llm_weight}")

        # 6. Weight sum and bounds
        if not (0.0 - tol <= r.effective_quant_weight <= 1.0 + tol):
            errors.append(f"{prefix}: effective_quant_weight out of [0, 1] bounds: {r.effective_quant_weight}")
        if not (0.0 - tol <= r.effective_llm_weight <= 0.25 + tol):
            errors.append(f"{prefix}: effective_llm_weight out of [0, 0.25] bounds: {r.effective_llm_weight}")

        weight_sum = r.effective_quant_weight + r.effective_llm_weight
        if abs(weight_sum - 1.0) > tol:
            errors.append(f"{prefix}: effective weights sum != 1.0 ({weight_sum})")

        # 7. Recompute formula verification for hybrid_score
        if r.hybrid_score is not None and not r.is_veto:
            if r.quant_score is not None:
                if r.is_fallback:
                    expected_hybrid = float(r.quant_score)
                else:
                    if r.llm_score is not None:
                        expected_raw = r.effective_quant_weight * float(r.quant_score) + r.effective_llm_weight * float(r.llm_score)
                        expected_hybrid = float(min(max(expected_raw, -1.0), 1.0))
                    else:
                        expected_hybrid = float(r.quant_score)
                if abs(r.hybrid_score - expected_hybrid) > tol:
                    errors.append(
                        f"{prefix}: recomputed formula mismatch (stored={r.hybrid_score}, expected={expected_hybrid})"
                    )

        # 8. LLM Weight Cap
        if r.effective_llm_weight > 0.25 + tol:
            errors.append(f"{prefix}: effective_llm_weight exceeds 0.25 cap: {r.effective_llm_weight}")

        # 9. Quant score None check
        if r.quant_score is None and not r.is_veto:
            if r.hybrid_score is not None:
                errors.append(f"{prefix}: quant_score is None but hybrid_score is {r.hybrid_score}")
            if r.decision is not None:
                errors.append(f"{prefix}: quant_score is None but decision is {r.decision}")

        # 10. Decision band check
        if r.hybrid_score is not None:
            expected_decision = HybridEvaluator.map_decision_band(r.hybrid_score, is_veto=r.is_veto)
            if r.decision != expected_decision:
                errors.append(f"{prefix}: decision mismatch (got {r.decision}, expected {expected_decision})")

    return (len(errors) == 0), errors
