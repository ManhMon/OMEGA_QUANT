import json
r = json.load(open('.ly_state/session/phase13_regime_overlay.json'))
b = r['baseline']
print(f"SR_ann: {b['dsr_sr_ann']:.4f}")
print(f"DSR: {b['dsr']:.4f}")
print(f"Median test IC: {b['median_test_ic']:.4f}")
print(f"Median fold SR: {b['median_fold_sr']:.4f}")
if 'fold_dsr' in b:
    print(f"Fold DSR: {b['fold_dsr']['dsr']:.4f}")
    print(f"Fold SR ann: {b['fold_dsr']['sr_mean_annualized']:.4f}")
if 'cost_breakdown' in b:
    cb = b['cost_breakdown']
    print(f"Costs: avg={cb['avg_cost_per_bar_bps']:.1f}bps, turnover={cb['avg_turnover_per_bar']:.3f}")
print()
print("COMPARISON:")
print("  Without regime (Phase 12): SR_ann=5.87, fold_DSR=0.374")
print(f"  With regime (Phase 13):    SR_ann={b['dsr_sr_ann']:.2f}, fold_DSR={b.get('fold_dsr',{}).get('dsr',0):.4f}")
