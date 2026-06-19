#!/usr/bin/env python3
"""Aggregate promoted alphas from all regime-specific evolution runs.

GATE: GP_EXPANSION_ALTERNATIVE_REGIMES_20260617

Reads evolved_alphas_<regime>.json for each regime, tags alphas with regime,
and writes aggregated evolved_alphas.json and all_regimes_evolved_alphas.json.
"""
import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SESSION_DIR = PROJECT_ROOT / ".ly_state" / "session"

REGIMES = {
    "bull_20_21": SESSION_DIR / "evolved_alphas_bull_20_21.json",
    "bear_22": SESSION_DIR / "evolved_alphas_bear_22.json",
    "sideways_24_26": SESSION_DIR / "evolved_alphas_sideways_24_26.json",
}


def main():
    all_alphas = []
    regime_summaries = {}

    for regime_name, fpath in REGIMES.items():
        if not fpath.exists():
            print(f"[ERROR] Missing: {fpath}")
            continue
        with open(fpath, "r") as f:
            data = json.load(f)
        alphas = data.get("alphas", [])
        regime_summaries[regime_name] = {
            "total_promoted": data["total_promoted"],
            "run_date": data["run_date"],
        }
        for alpha in alphas:
            alpha["regime"] = regime_name
            # GATE: GP_EXPANSION_ALTERNATIVE_REGIMES_20260617 — ensure globally unique
            # alpha_id by appending regime name to prevent duplicate reuse across regimes.
            # Example: gp_alpha_20260617_000 → gp_alpha_20260617_000_bull_20_21
            alpha["alpha_id"] = f"{alpha['alpha_id']}_{regime_name}"
            all_alphas.append(alpha)
        print(f"  {regime_name}: {len(alphas)} promoted alphas loaded")

    # Verify global alpha_id uniqueness after regime-suffix appending
    all_ids = [a["alpha_id"] for a in all_alphas]
    dup_ids = [aid for aid in all_ids if all_ids.count(aid) > 1]
    if dup_ids:
        print(f"[ERROR] Duplicate alpha_ids remain after aggregation: {set(dup_ids)}")
        raise SystemExit(1)
    print(f"  Uniqueness check PASSED: {len(all_ids)} unique alpha_ids")

    aggregated = {
        "run_date": datetime.now().isoformat(),
        "total_promoted": len(all_alphas),
        "gate": "GP_EXPANSION_ALTERNATIVE_REGIMES_20260617",
        "regimes_executed": list(REGIMES.keys()),
        "config": {
            "generations": 50,
            "population_size": 200,
            "orthogonalize": "momentum",
        },
        "regime_summaries": regime_summaries,
        "target_horizon": 5,
        "multi_target_horizons": [3, 5, 10],
        "multi_target_weights": [0.5, 0.3, 0.2],
        "pit_safety": {
            "t1_lag": True,
            "chronological_split": True,
            "no_lookahead": True,
        },
        "orthogonalization": {"enabled": True, "source": "momentum"},
        "alternative_features": {"enabled": True, "expected_columns": 35},
        "alphas": all_alphas,
    }

    # Write evolved_alphas.json (primary aggregated output)
    out_path = SESSION_DIR / "evolved_alphas.json"
    with open(out_path, "w") as f:
        json.dump(aggregated, f, indent=2)
    print(f"Wrote {out_path} ({len(all_alphas)} alphas)")

    # Write all_regimes_evolved_alphas.json (mirror copy)
    all_regimes_path = SESSION_DIR / "all_regimes_evolved_alphas.json"
    with open(all_regimes_path, "w") as f:
        json.dump(aggregated, f, indent=2)
    print(f"Wrote {all_regimes_path} ({len(all_alphas)} alphas)")

    print(f"\nTOTAL: {len(all_alphas)} promoted alphas from {len(regime_summaries)} regimes")


if __name__ == "__main__":
    main()
