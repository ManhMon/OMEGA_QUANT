import json
from pathlib import Path

base = Path("data/phase35_results")
files = sorted(base.glob("hybrid_regime_cpcv_comparison_*.json"))

print("| Experiment/File | Scenario | Sharpe | Return | MaxDD | TO | Folds | Sym | Dyn | tcost | top_k | min_trade | rebal | bear_damp |")
print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")

for p in files:
    d = json.loads(p.read_text(encoding="utf-8"))
    cfg = d.get("config", {})
    agg = d.get("aggregated", {})
    
    # Try to extract parameters from config or metadata
    folds = cfg.get("folds", 10)
    sym = cfg.get("symbol_count", 30)
    dyn = cfg.get("dynamic_universe", False)
    
    # Extract scenarios
    for sc in ["Baseline", "Hybrid"]:
        if sc not in agg:
            continue
        sc_data = agg[sc]
        diag = sc_data.get("profitability_diag", {})
        
        # We can extract some parameters from the filename tags or defaults
        fn = p.name
        tcost = "15" if "tcost15" in fn or "e1" in fn or "e3" in fn else ("20" if "tcost20" in fn else ("50" if "tcost50" in fn else "35 (def)"))
        top_k = "3" if "topk3" in fn else ("7" if "topk7" in fn or "e4" in fn or "p2" in fn else "5 (def)")
        min_trade = "250 (def)"
        rebal = "15 (def)"
        bear_damp = "0.45" if "p2" in fn or "e4" in fn else "0.15 (def)"
        
        sharpe = sc_data.get("mean_sharpe", float("nan"))
        ret = sc_data.get("mean_return", float("nan"))
        mdd = sc_data.get("mean_max_dd", float("nan"))
        to = diag.get("mean_turnover_avg", float("nan"))
        
        print(f"| {p.name} | {sc} | {sharpe:.4f} | {ret:.4f} | {mdd:.4f} | {to:.4f} | {folds} | {sym} | {dyn} | {tcost} | {top_k} | {min_trade} | {rebal} | {bear_damp} |")
