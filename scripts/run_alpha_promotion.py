"""Alpha Promotion Governance Script.

Role 9 (Backend Engineer) - L2 Implementation.

Wires PromotionGate (decides which evolved alphas go to production).
PIT-safe, vectorized, with proper logging and graceful degradation.

Usage:
    python scripts/run_alpha_promotion.py --date 2026-05-29
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- Path setup -------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_SRC = REPO_ROOT / "packages" / "quant" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

# --- Logging ----------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("alpha_promotion")

# --- Optional PromotionGate import (graceful degradation) -------------------
try:
    from omega.quant.utils.promotion import PromotionGate  # type: ignore
    _HAS_GATE = True
except Exception as exc:  # pragma: no cover - import-time fallback
    logger.warning("PromotionGate unavailable (%s); using fallback evaluator.", exc)
    PromotionGate = None  # type: ignore[assignment]
    _HAS_GATE = False


# --- Promotion criteria (institutional baseline) ----------------------------
PROMOTION_CRITERIA: dict[str, float] = {
    "ic_min": 0.05,            # 5% minimum IC
    "sharpe_min": 0.5,         # Minimum Sharpe ratio
    "oos_ratio_min": 0.5,      # OOS performance >= IS * 0.5 (overfitting guard)
    "corr_max": 0.7,           # Diversity: correlation with existing alphas
    "ic_drop_threshold": 0.5,  # Demote if IC dropped > 50%
}

# --- State paths ------------------------------------------------------------
LY_STATE = REPO_ROOT / ".ly_state" / "session"
EVOLVED_PATH = LY_STATE / "evolved_alphas.json"
ACTIVE_PATH = LY_STATE / "active_alphas.json"


def _load_json(path: Path, default: Any) -> Any:
    """Read JSON file with graceful fallback to default."""
    if not path.exists():
        logger.warning("State file missing: %s -> using default.", path)
        return default
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to read %s: %s", path, exc)
        return default


def _write_json(path: Path, payload: Any) -> None:
    """Write JSON file atomically (temp + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    tmp.replace(path)


def _safe_get(d: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    """Get nested numeric value with default."""
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    try:
        return float(d)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _max_correlation(candidate: dict[str, Any], actives: list[dict[str, Any]]) -> float:
    """Max abs correlation between candidate and any active alpha.

    Looks for `correlations` map: {alpha_id: rho}. Falls back to 0 if absent.
    """
    corr_map = candidate.get("correlations") or {}
    if not isinstance(corr_map, dict) or not actives:
        return 0.0
    active_ids = {a.get("id") or a.get("alpha_id") for a in actives}
    rhos = [
        abs(float(v))
        for k, v in corr_map.items()
        if k in active_ids and isinstance(v, (int, float))
    ]
    return max(rhos) if rhos else 0.0


def _fallback_evaluate(
    candidate: dict[str, Any],
    actives: list[dict[str, Any]],
    criteria: dict[str, float],
) -> dict[str, Any]:
    """Pure-Python evaluator used when PromotionGate is unavailable."""
    ic = _safe_get(candidate, "metrics", "ic")
    sharpe = _safe_get(candidate, "metrics", "sharpe")
    is_perf = _safe_get(candidate, "metrics", "is_perf", default=1.0) or 1.0
    oos_perf = _safe_get(candidate, "metrics", "oos_perf")
    corr = _max_correlation(candidate, actives)

    oos_ratio = oos_perf / is_perf if is_perf else 0.0
    reasons: list[str] = []
    if ic < criteria["ic_min"]:
        reasons.append(f"ic<{criteria['ic_min']:.3f} (got {ic:.4f})")
    if sharpe < criteria["sharpe_min"]:
        reasons.append(f"sharpe<{criteria['sharpe_min']:.2f} (got {sharpe:.3f})")
    if oos_ratio < criteria["oos_ratio_min"]:
        reasons.append(f"oos_ratio<{criteria['oos_ratio_min']:.2f} (got {oos_ratio:.3f})")
    if corr > criteria["corr_max"]:
        reasons.append(f"corr>{criteria['corr_max']:.2f} (got {corr:.3f})")

    return {
        "passed": not reasons,
        "ic": ic,
        "sharpe": sharpe,
        "oos_ratio": oos_ratio,
        "max_corr": corr,
        "reasons": reasons,
    }


def _evaluate(
    candidate: dict[str, Any],
    actives: list[dict[str, Any]],
    criteria: dict[str, float],
) -> dict[str, Any]:
    """Evaluate using PromotionGate if available, else fallback."""
    if _HAS_GATE:
        try:
            gate = PromotionGate(criteria=criteria)  # type: ignore[call-arg]
            result = gate.evaluate(candidate=candidate, actives=actives)
            if isinstance(result, dict):
                return result
            # Coerce non-dict verdicts (e.g. bool)
            return {"passed": bool(result), "reasons": []}
        except Exception as exc:
            logger.warning("PromotionGate.evaluate failed (%s); fallback.", exc)
    return _fallback_evaluate(candidate, actives, criteria)


def _check_demotions(
    actives: list[dict[str, Any]],
    evolved: list[dict[str, Any]],
    criteria: dict[str, float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Identify actives whose IC dropped > threshold vs latest evolved metrics.

    Returns (kept_actives, demoted_actives).
    """
    evolved_by_id = {
        (e.get("id") or e.get("alpha_id")): e for e in evolved if isinstance(e, dict)
    }
    kept: list[dict[str, Any]] = []
    demoted: list[dict[str, Any]] = []
    drop = criteria["ic_drop_threshold"]
    for active in actives:
        aid = active.get("id") or active.get("alpha_id")
        baseline_ic = _safe_get(active, "metrics", "ic")
        latest = evolved_by_id.get(aid)
        if latest is None or baseline_ic <= 0:
            kept.append(active)
            continue
        latest_ic = _safe_get(latest, "metrics", "ic")
        rel_drop = (baseline_ic - latest_ic) / baseline_ic if baseline_ic else 0.0
        if rel_drop > drop:
            demoted.append(
                {
                    **active,
                    "demoted_at": datetime.now(timezone.utc).isoformat(),
                    "baseline_ic": baseline_ic,
                    "latest_ic": latest_ic,
                    "rel_drop": rel_drop,
                }
            )
            logger.info(
                "DEMOTE %s ic %.4f -> %.4f (drop=%.1f%%)",
                aid, baseline_ic, latest_ic, rel_drop * 100,
            )
        else:
            kept.append(active)
    return kept, demoted


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alpha promotion governance.")
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="Promotion run date (YYYY-MM-DD).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    run_date = args.date
    logger.info("Alpha promotion run | date=%s | gate=%s", run_date, _HAS_GATE)

    evolved_doc = _load_json(EVOLVED_PATH, default={"alphas": []})
    active_doc = _load_json(ACTIVE_PATH, default={"alphas": []})

    evolved: list[dict[str, Any]] = (
        evolved_doc.get("alphas", []) if isinstance(evolved_doc, dict) else []
    )
    actives: list[dict[str, Any]] = (
        active_doc.get("alphas", []) if isinstance(active_doc, dict) else []
    )
    logger.info("Loaded %d evolved, %d active alphas.", len(evolved), len(actives))

    promoted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    active_ids = {a.get("id") or a.get("alpha_id") for a in actives}

    for cand in evolved:
        if not isinstance(cand, dict):
            continue
        cid = cand.get("id") or cand.get("alpha_id")
        if cid in active_ids:
            # Already in production; skip promotion eval here (handled in demotion).
            continue
        verdict = _evaluate(cand, actives, PROMOTION_CRITERIA)
        if verdict.get("passed"):
            promoted.append(
                {
                    **cand,
                    "promoted_at": datetime.now(timezone.utc).isoformat(),
                    "verdict": verdict,
                }
            )
            logger.info("PROMOTE %s | ic=%.4f sharpe=%.3f corr=%.3f",
                        cid,
                        verdict.get("ic", 0.0),
                        verdict.get("sharpe", 0.0),
                        verdict.get("max_corr", 0.0))
        else:
            rejected.append(
                {
                    "id": cid,
                    "reasons": verdict.get("reasons", []),
                    "verdict": verdict,
                }
            )
            logger.info("REJECT  %s | reasons=%s", cid, verdict.get("reasons"))

    kept_actives, demoted = _check_demotions(actives, evolved, PROMOTION_CRITERIA)

    # New active set = kept + promoted (dedup by id, promoted wins)
    new_active_ids = {p.get("id") or p.get("alpha_id") for p in promoted}
    merged: list[dict[str, Any]] = [
        a for a in kept_actives
        if (a.get("id") or a.get("alpha_id")) not in new_active_ids
    ] + promoted

    active_payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "date": run_date,
        "alphas": merged,
        "status": "PROPOSAL_AWAITING_GATE"
    }
    # SOD compliance: do NOT write directly to active_alphas.json (production state)
    # Instead write to proposed_active_alphas_{date}.json for Ly L1 gate review
    PROPOSAL_PATH = LY_STATE / f"proposed_active_alphas_{run_date}.json"
    _write_json(PROPOSAL_PATH, active_payload)

    promotion_log = {
        "date": run_date,
        "criteria": PROMOTION_CRITERIA,
        "gate_backend": "PromotionGate" if _HAS_GATE else "fallback",
        "promoted": promoted,
        "demoted": demoted,
        "rejected": rejected,
        "totals": {
            "evolved_evaluated": len(evolved),
            "promoted": len(promoted),
            "demoted": len(demoted),
            "rejected": len(rejected),
            "active_after": len(merged),
        },
    }
    log_path = LY_STATE / f"promotion_{run_date}.json"
    _write_json(log_path, promotion_log)

    print("=" * 60)
    print(f"Alpha Promotion Summary ({run_date})")
    print("-" * 60)
    print(f"  Evaluated : {len(evolved)}")
    print(f"  Promoted  : {len(promoted)}")
    print(f"  Demoted   : {len(demoted)}")
    print(f"  Rejected  : {len(rejected)}")
    print(f"  Active    : {len(merged)}")
    print(f"  Log file  : {log_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
