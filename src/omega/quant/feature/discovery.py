"""V21 Alpha Discovery Engine - Phase 2.
Leak-safe candidate generation + IC ranking on aligned symbol/timestamp panel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Any
import numpy as np
import pandas as pd

from omega.quant.evolution.alpha_to_execution_bridge import CANONICAL_METRIC_KEY


@dataclass
class DiscoveredFeature:
    name: str
    ic: float
    coverage: float
    signal_pnl_score: float = 0.0


class AlphaDiscoveryEngine:
    """Engine tự động phát hiện alpha factors mới."""

    def __init__(self, min_ic: float = 0.02, max_features: int = 10):
        self.min_ic = float(min_ic)
        self.max_features = int(max_features)
        self.discovered_features: List[DiscoveredFeature] = []

    @staticmethod
    def _build_flat_panel(clean_df: Dict[str, Any], target_vector: Dict[str, Any]) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []

        data = clean_df.get("data", {})
        tdata = target_vector.get("data", {})

        for sym, sym_map in data.items():
            tgt_map = tdata.get(sym, {})
            for ts, vals in sym_map.items():
                if ts not in tgt_map:
                    continue
                target = tgt_map[ts].get("target")
                if target is None:
                    continue
                rows.append(
                    {
                        "symbol": sym,
                        "timestamp": int(ts),
                        "open": float(vals.get("open", vals.get("close", 0.0))),
                        "high": float(vals.get("high", vals.get("close", 0.0))),
                        "low": float(vals.get("low", vals.get("close", 0.0))),
                        "close": float(vals.get("close", 0.0)),
                        "volume": float(vals.get("volume", 0.0)),
                        "target": float(target),
                    }
                )

        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        return df

    @staticmethod
    def _safe_rsi(s: pd.Series, window: int) -> pd.Series:
        delta = s.diff()
        up = delta.clip(lower=0)
        down = (-delta).clip(lower=0)
        up_ma = up.rolling(window).mean()
        down_ma = down.rolling(window).mean()
        rs = up_ma / (down_ma + 1e-12)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi

    def _generate_candidates(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        g = df.groupby("symbol", group_keys=False)
        cands: Dict[str, pd.Series] = {}

        # momentum (leak-safe via shift(1))
        for lag in (1, 2, 3, 5, 10, 20):
            cands[f"mom_{lag}d"] = g["close"].pct_change(lag).shift(1)

        # moving-average distance
        for w in (5, 10, 20):
            ma = g["close"].transform(lambda s: s.rolling(w).mean())
            cands[f"rma_{w}"] = (df["close"] / (ma + 1e-12) - 1.0).groupby(df["symbol"]).shift(1)

        # normalized volatility
        for w in (5, 10, 20):
            vol = g["close"].transform(lambda s: s.rolling(w).std())
            mean_ = g["close"].transform(lambda s: s.rolling(w).mean())
            cands[f"vol_{w}"] = (vol / (mean_ + 1e-12)).groupby(df["symbol"]).shift(1)

        # RSI
        for w in (5, 10, 14):
            rsi = g["close"].transform(lambda s: self._safe_rsi(s, w))
            cands[f"rsi_{w}"] = (rsi / 100.0 - 0.5).groupby(df["symbol"]).shift(1)

        # volume-adjusted momentum
        for lag in (1, 5):
            vm = g["close"].pct_change(lag) * df["volume"]
            cands[f"volmom_{lag}"] = vm.groupby(df["symbol"]).shift(1)

        return cands

    @staticmethod
    def _calculate_ic(feature: pd.Series, target: pd.Series) -> tuple[float, float]:
        m = pd.DataFrame({"f": feature, "t": target}).dropna()
        if len(m) < 200:
            return 0.0, 0.0
        ic = m["f"].corr(m["t"], method="spearman")
        coverage = float(len(m)) / float(len(feature)) if len(feature) else 0.0
        if pd.isna(ic):
            return 0.0, coverage
        return float(ic), coverage

    def discover(self, clean_df: Dict[str, Any], target_vector: Dict[str, Any]) -> List[Dict[str, Any]]:
        panel = self._build_flat_panel(clean_df, target_vector)
        if panel.empty:
            print("  ⚠️ No aligned data for discovery")
            self.discovered_features = []
            return []

        print(f"  📦 Discovery panel rows: {len(panel)}")
        cands = self._generate_candidates(panel)
        print(f"  🔬 Generated {len(cands)} leak-safe candidates")

        results: List[DiscoveredFeature] = []
        for name, series in cands.items():
            ic, cov = self._calculate_ic(series, panel["target"])
            if abs(ic) >= self.min_ic:
                results.append(DiscoveredFeature(name=name, ic=ic, coverage=cov, signal_pnl_score=ic))

        results.sort(key=lambda x: abs(x.ic), reverse=True)
        top = results[: self.max_features]
        self.discovered_features = top

        print(f"  ✅ Discovered {len(top)} alpha features (|IC| >= {self.min_ic})")
        for f in top:
            print(f"     - {f.name}: IC={f.ic:.4f}, coverage={f.coverage:.2%}")

        return [{"name": f.name, "ic": f.ic, "coverage": f.coverage, CANONICAL_METRIC_KEY: f.signal_pnl_score} for f in top]


def run_discovery(clean_df: Dict[str, Any], target_vector: Dict[str, Any]) -> List[Dict[str, Any]]:
    engine = AlphaDiscoveryEngine(min_ic=0.02, max_features=10)
    return engine.discover(clean_df, target_vector)
