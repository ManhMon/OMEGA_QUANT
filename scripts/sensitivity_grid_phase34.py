#!/usr/bin/env python3
"""Sensitivity grid for Phase 3.4 tail controls.

Per L3 audit recommendation (audit_phase3_4.md): if (0.15, 0.05, 0.08, 20)
is a clear local DSR maximum, params are overfit to 2020-2024 sample.

Reduced 9-cell grid: target_vol_ann x dd_threshold (held: max_abs=0.05, dd_window=20).
"""
from __future__ import annotations
import argparse, importlib.util, json, logging, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sensitivity_grid")
REPO_ROOT = Path(__file__).resolve().parent.parent
QUANT_SRC = REPO_ROOT / "src"

def _import(name, rel):
    spec = importlib.util.spec_from_file_location(name, str(QUANT_SRC / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# Lazy import scripts/backtest_v2_cpcv.py modules using its private functions.
import importlib.util as iu
spec = iu.spec_from_file_location("_bt", str(REPO_ROOT / "scripts/backtest_v2_cpcv.py"))
bt = iu.module_from_spec(spec)
sys.modules["_bt"] = bt
spec.loader.exec_module(bt)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=".ly_state/session/sensitivity_grid_9cell.json")
    args = p.parse_args()

    cpcv_mod = _import("_cpcv", "omega/quant/validation/cpcv.py")
    dsr_mod = _import("_dsr", "omega/quant/validation/dsr.py")
    feat_mod = _import("_feat", "omega/quant/evolution/feature_adapter.py")
    tail_mod = _import("_tc", "omega/quant/portfolio/tail_controls.py")

    # Load data ONCE (avoid 5 reloads)
    wf = bt.load_universe_walk_forward(2020, 2024)
    panel = bt.load_panel_walk_forward(wf, 2020, 2024)
    target = bt.compute_target(panel, horizon=5)
    feat_dict = feat_mod.GPFeatureAdapter().compute_all(panel, top_n_features=125)
    feat_names = list(feat_dict.keys())
    feat_df = pd.DataFrame(feat_dict, index=panel.index)
    feat_df["ticker"] = panel["ticker"].values
    feat_df["date"] = panel["date"].values
    feat_df["target"] = target.values
    feat_df = feat_df.sort_values(["date", "ticker"]).reset_index(drop=True)
    valid = ~feat_df["target"].isna() & ~feat_df[feat_names].isna().any(axis=1)
    feat_df = feat_df[valid].reset_index(drop=True)
    X = feat_df[feat_names].to_numpy()
    y = feat_df["target"].to_numpy()
    max_per_date = int(feat_df.groupby("date").size().max())
    bar_horizon = 5 * max_per_date
    ts = pd.Series(np.arange(len(y)))
    dates = feat_df["date"].to_numpy()
    tickers = feat_df["ticker"].to_numpy()
    logger.info("Data ready: %d samples, %d feats", len(y), X.shape[1])

    # 3x3 grid
    target_vols = [0.10, 0.15, 0.20]
    dd_thresholds = [0.05, 0.08, 0.12]
    results = []
    for tv in target_vols:
        for ddt in dd_thresholds:
            t0 = time.time()
            # Patch tail kwargs via monkey-patch on tail_mod
            original_apply = tail_mod.apply_tail_controls
            def patched_apply(daily_w, daily_y, **kw):
                kw["target_vol_ann"] = tv
                kw["dd_threshold"] = ddt
                kw["max_abs_weight"] = 0.05
                kw["dd_window"] = 20
                return original_apply(daily_w, daily_y, **kw)
            tail_mod.apply_tail_controls = patched_apply

            summary = bt.run_pipeline(X, y, ts, dates, cpcv_mod, dsr_mod,
                                       f"tv{tv}_dd{ddt}",
                                       label_horizon=bar_horizon,
                                       tickers=tickers, tail_mod=tail_mod)
            tail_mod.apply_tail_controls = original_apply  # restore

            cell = {
                "target_vol_ann": tv,
                "dd_threshold": ddt,
                "dsr": summary["dsr"],
                "dsr_sr_ann": summary["dsr_sr_ann"],
                "median_fold_sr": summary["median_fold_sr"],
                "skew": summary["skew"],
                "kurt": summary["kurt"],
                "pass": summary["pass"],
                "runtime_s": round(time.time() - t0, 1),
            }
            results.append(cell)
            logger.info("[tv=%.2f, dd=%.2f] DSR=%.4f, ann_SR=%.3f, skew=%.2f, kurt=%.1f (%.0fs)",
                        tv, ddt, cell["dsr"], cell["dsr_sr_ann"], cell["skew"], cell["kurt"], cell["runtime_s"])

    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({"grid": results, "baseline_cell": [0.15, 0.08]}, f, indent=2, default=str)
    logger.info("Saved: %s", out)
    return 0

if __name__ == "__main__":
    sys.exit(main())
