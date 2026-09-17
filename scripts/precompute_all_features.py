"""Pre-compute all alpha features for hybrid regime backtest optimization.

Gate: HYBRID_REGIME_BACKTEST_PERF_20260621

Generates a single precomputed feature parquet that includes:
  1. Core features from UnifiedFeatureAdapter (arsenal + alt + alt_data)
  2. Latent AE components (renamed alpha_latent_ae_XX)
  3. Top-3 GP alpha expressions compiled and executed per-ticker
  4. Synthetic LLM alpha expressions (mock/synthetic via GPNode)

Output: data/precomputed_alpha_features.parquet
"""

import sys
import os
import logging
import ast
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
os.chdir(str(REPO_ROOT))

from omega.core.registry.persistence import DatabaseRegistry
from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
from omega.quant.evolution.genetic_programming import (
    GPNode,
    GPIndividual,
    _ts_std,
    _ts_mean,
    _ts_rank,
    _decay_linear,
    _protected_div,
)
from omega.quant.alpha.hybrid_regime_alpha import (
    compute_all_hybrid_regime_alphas,
    HYBRID_REGIME_ALPHA_COLUMNS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("precompute_all_features")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RAW_DATA_PATH = REPO_ROOT / "data" / "market_2015_now.parquet"
LATENT_AE_PATH = REPO_ROOT / "data" / "latent_alphas_components.parquet"
STABLE_GP_RESULTS_PATH = REPO_ROOT / "data" / "stable" / "genetic_alpha_v3_results.csv"
LEGACY_GP_RESULTS_PATH = REPO_ROOT / "data" / "phase35_results" / "genetic_alpha_v3_results.csv"
OUTPUT_PATH = REPO_ROOT / "data" / "precomputed_alpha_features.parquet"
REGISTRY_DB_URL = f"sqlite:///{(REPO_ROOT / '.ly_state' / 'session' / 'conformal_registry.sqlite').as_posix()}"

DYNAMIC_UNIVERSE_COUNT = 104
TOP_GP_EXPRESSIONS = 3


def _load_gp_registry_rows() -> pd.DataFrame:
    registry = DatabaseRegistry(database_url=REGISTRY_DB_URL)
    records = registry.list_models(name_prefix="genetic_alpha_v3_rank_", status="ready")
    rows = []
    for record in records:
        metrics = record.metrics or {}
        rows.append(
            {
                "rank": metrics.get("rank"),
                "round": metrics.get("round"),
                "train_IC": metrics.get("train_IC"),
                "test_IC": metrics.get("test_IC"),
                "hit_rate": metrics.get("hit_rate"),
                "expression": metrics.get("expression"),
                "serialized_tree": metrics.get("serialized_tree"),
                "name": record.name,
                "version": record.version,
                "path": record.path,
                "created_at": record.created_at,
            }
        )
    if not rows:
        return pd.DataFrame()
    gp_df = pd.DataFrame(rows)
    gp_df = gp_df.sort_values(["created_at", "version"], ascending=[False, False])
    gp_df = gp_df.drop_duplicates(subset=["name"], keep="first")
    return gp_df.sort_values(["rank", "created_at"], ascending=[True, False]).reset_index(drop=True)


def load_raw_data() -> pd.DataFrame:
    """Load and validate raw market data."""
    logger.info("Loading raw data from %s", RAW_DATA_PATH)
    raw_df = pd.read_parquet(RAW_DATA_PATH)
    raw_df["date"] = pd.to_datetime(raw_df["date"])
    logger.info(
        "Raw data: %d rows, %d tickers, date range %s to %s",
        len(raw_df),
        raw_df["ticker"].nunique(),
        raw_df["date"].min().date(),
        raw_df["date"].max().date(),
    )
    return raw_df


def select_dynamic_universe(raw_df: pd.DataFrame, top_n: int = DYNAMIC_UNIVERSE_COUNT) -> List[str]:
    """Select top-N tickers by total volume (dynamic universe proxy).

    Uses total volume across the entire period as a simple dynamic universe
    selection — matches the static universe selection in backtest_hybrid_regime.py
    but with a larger count (104) to cover the full dynamic rebalance schedule.
    """
    ticker_volumes = raw_df.groupby("ticker")["volume"].sum()
    selected = ticker_volumes.nlargest(top_n).index.tolist()
    logger.info(
        "Dynamic universe: selected %d tickers (top %d by volume). Sample: %s",
        len(selected), top_n, selected[:10],
    )
    return selected


def prepare_panel(raw_df: pd.DataFrame, tickers: List[str]) -> pd.DataFrame:
    """Prepare feature panel from raw data for selected tickers."""
    panel = raw_df[raw_df["ticker"].isin(tickers)].copy()
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    panel = panel.rename(columns={"ticker": "symbol"})
    panel["returns"] = panel.groupby("symbol")["close"].pct_change()
    panel["adv_vnd"] = (
        panel.groupby("symbol")["volume"]
        .rolling(20, min_periods=5)
        .mean()
        .reset_index(level=0, drop=True)
    ) * panel["close"]
    logger.info(
        "Panel prepared: %d rows, %d symbols",
        len(panel), panel["symbol"].nunique(),
    )
    return panel


def generate_core_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Run UnifiedFeatureAdapter to generate core alpha features."""
    logger.info("Generating core features via UnifiedFeatureAdapter...")
    panel_mi = panel.set_index(["date", "symbol"]).sort_index()
    adapter = UnifiedFeatureAdapter(
        use_arsenal=True,
        use_alt_features=True,
        use_alt_data=True,
        use_llm_synth=False,
    )
    feat_panel = adapter.generate_all(panel_mi)
    feat_df = feat_panel.reset_index()
    alpha_cols = [c for c in feat_df.columns if c.startswith("alpha_")]
    logger.info(
        "Core features generated: %d alpha columns, %d total columns",
        len(alpha_cols), len(feat_df.columns),
    )
    return feat_df


def inject_latent_ae_components(feat_df: pd.DataFrame) -> pd.DataFrame:
    """Inject latent AE components, renamed as alpha_latent_ae_XX.

    Loads from data/latent_alphas_components.parquet and renames
    latent_ae_XX columns to alpha_latent_ae_XX so they appear as
    alpha features for Ridge blending.
    """
    if not LATENT_AE_PATH.exists():
        logger.warning("Latent AE path not found: %s — skipping", LATENT_AE_PATH)
        return feat_df

    logger.info("Loading latent AE components from %s", LATENT_AE_PATH)
    latent_df = pd.read_parquet(LATENT_AE_PATH)

    # Identify latent columns
    latent_cols = [c for c in latent_df.columns if c.startswith("latent_ae_")]
    if not latent_cols:
        logger.warning("No latent_ae_* columns found in %s", LATENT_AE_PATH)
        return feat_df

    # Determine symbol column name
    symbol_col = "symbol" if "symbol" in latent_df.columns else "ticker"
    if symbol_col not in latent_df.columns:
        logger.warning("No symbol/ticker column in latent AE file")
        return feat_df

    # Rename latent_ae_XX -> alpha_latent_ae_XX
    rename_map = {c: f"alpha_{c}" for c in latent_cols}
    latent_renamed = latent_df[["date", symbol_col] + latent_cols].copy()
    latent_renamed = latent_renamed.rename(columns=rename_map)
    if symbol_col != "symbol":
        latent_renamed = latent_renamed.rename(columns={symbol_col: "symbol"})

    # Merge with feat_df
    renamed_cols = list(rename_map.values())
    feat_df = feat_df.merge(
        latent_renamed[["date", "symbol"] + renamed_cols],
        on=["date", "symbol"],
        how="left",
    )
    logger.info(
        "Injected %d latent AE columns (renamed as alpha_latent_ae_XX): %s",
        len(renamed_cols), renamed_cols[:5],
    )
    return feat_df


def compute_hybrid_regime_alphas(feat_df: pd.DataFrame) -> pd.DataFrame:
    """Compute 7 v1 hybrid regime alpha signals and inject into feat_df.

    Gate: HYBRID_REGIME_BACKTEST_PERF_20260621

    Calls compute_all_hybrid_regime_alphas() from hybrid_regime_alpha.py
    which produces 7 PIT-safe alpha signals (T-1 lagged, vectorized).

    The panel must contain columns: close, high, low, volume, date, symbol.
    All 7 alphas are added as alpha_hr_* columns matching
    HYBRID_REGIME_ALPHA_COLUMNS.

    PIT-safe: each signal function applies groupby(symbol).shift(1)
    internally, so no look-ahead bias is introduced.
    """
    logger.info("Computing 7 hybrid regime v1 alpha signals...")

    # The hybrid regime alpha functions expect a symbol column; our panel
    # uses "symbol" (renamed from "ticker" in prepare_panel).
    panel_sorted = feat_df.sort_values(["symbol", "date"])

    alpha_dict = compute_all_hybrid_regime_alphas(
        panel_sorted, symbol_col="symbol"
    )

    n_added = 0
    for col_name, series in alpha_dict.items():
        # Reindex to feat_df's index to align properly
        feat_df[col_name] = series.reindex(feat_df.index).values
        n_added += 1

    # Verify all expected columns are present
    cols_present = [c for c in HYBRID_REGIME_ALPHA_COLUMNS if c in feat_df.columns]
    cols_missing = [c for c in HYBRID_REGIME_ALPHA_COLUMNS if c not in feat_df.columns]
    logger.info(
        "Hybrid regime alphas: %d/%d columns added. Missing: %s",
        len(cols_present), len(HYBRID_REGIME_ALPHA_COLUMNS),
        cols_missing if cols_missing else "none",
    )
    return feat_df


def _parse_gp_expression(expr_str: str) -> Optional[GPNode]:
    """Parse canonical GP tree payload from serialized_tree."""
    if not isinstance(expr_str, str) or not expr_str.strip():
        return None
    expr_str = expr_str.strip()
    try:
        node = eval(expr_str, {"GPNode": GPNode, "__builtins__": {}})
        return node if isinstance(node, GPNode) else None
    except Exception as exc:
        logger.debug("Structured GP parse failed: %s", exc)
    logger.warning("Unsupported GP payload; canonical serialized_tree required: %s", expr_str[:80])
    return None


def _execute_gp_expression_per_ticker(
    node: GPNode,
    ticker_df: pd.DataFrame,
    alpha_name: str,
) -> pd.Series:
    """Execute a GP expression on a single ticker's data.

    Builds a features dict from the ticker's OHLCV + derived columns,
    then uses GPIndividual._execute_tree() for evaluation.
    """
    individual = GPIndividual(tree=node)

    # Build features dict from ticker data
    features: Dict[str, np.ndarray] = {}
    feature_columns = ["open", "high", "low", "close", "volume", "returns"]
    for col in feature_columns:
        if col in ticker_df.columns:
            features[col] = ticker_df[col].values.astype(float)

    # Additional derived features that GP expressions may reference
    if "close" in features and len(features["close"]) > 1:
        features["ret_1d"] = pd.Series(features["close"]).pct_change().fillna(0).values
    if "volume" in features and "close" in features:
        features["vol_ratio"] = (
            pd.Series(features["volume"]) / (pd.Series(features["volume"]).rolling(20).mean() + 1e-9)
        ).fillna(1.0).values

    if not features:
        return pd.Series(np.nan, index=ticker_df.index, name=alpha_name)

    try:
        result = individual._execute_tree(node, features)
        result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
        return pd.Series(result, index=ticker_df.index, name=alpha_name)
    except Exception as exc:
        logger.debug("GP execution failed for %s: %s", alpha_name, exc)
        return pd.Series(np.nan, index=ticker_df.index, name=alpha_name)


def compile_and_execute_gp_alphas(feat_df: pd.DataFrame) -> pd.DataFrame:
    """Load top-3 GP expressions from CSV, compile, and execute per-ticker.

    Reads canonical DB registry rows, parses the top TOP_GP_EXPRESSIONS
    expressions by rank, and executes each per-ticker
    on the feature panel to produce alpha_gp_00, alpha_gp_01, alpha_gp_02.
    """
    gp_df = _load_gp_registry_rows()
    if gp_df.empty:
        logger.warning("GP registry rows not found in canonical DB: %s — skipping", REGISTRY_DB_URL)
        return feat_df

    # Select top-N by rank
    gp_top = gp_df.nsmallest(TOP_GP_EXPRESSIONS, "rank")
    logger.info("Selected top %d GP expressions (ranks: %s)", len(gp_top), gp_top["rank"].tolist())

    for i, (_, row) in enumerate(gp_top.iterrows()):
        alpha_name = f"alpha_gp_{i:02d}"
        expr_str = row.get("serialized_tree") or row.get("expression")
        node = _parse_gp_expression(expr_str)

        if node is None:
            logger.warning(
                "Skipping GP expression %d with unsupported payload (rank=%s, version=%s)",
                i,
                row.get("rank"),
                row.get("version"),
            )
            feat_df[alpha_name] = np.nan
            continue

        logger.info(
            "Executing GP alpha %d (rank=%d, test_IC=%.4f): %s",
            i, row["rank"], row["test_IC"], node.to_string()[:60],
        )

        # Execute per-ticker
        results = []
        for ticker, ticker_df in feat_df.groupby("symbol"):
            ticker_sorted = ticker_df.sort_values("date")
            alpha_series = _execute_gp_expression_per_ticker(
                node, ticker_sorted, alpha_name,
            )
            results.append(alpha_series)

        if results:
            combined = pd.concat(results)
            feat_df[alpha_name] = combined.reindex(feat_df.index)
            non_null = feat_df[alpha_name].notna().sum()
            logger.info("  GP alpha %d: %d non-null values", i, non_null)

    return feat_df


def generate_synthetic_llm_alphas(feat_df: pd.DataFrame) -> pd.DataFrame:
    """Generate mock/synthetic LLM alpha expressions via GPNode.

    These simulate LLM-discovered alpha patterns:
      - alpha_llm_0: decay_linear(ret_1d, 5) — momentum decay signal
      - alpha_llm_1: ts_rank(volume, 20) — volume rank signal
      - alpha_llm_2: div(ts_std(close, 20), ts_mean(volume, 10)) — vol/liquidity ratio
    """
    logger.info("Generating synthetic LLM alphas via GPNode...")

    llm_trees = {
        "alpha_llm_0": GPNode(
            operator="decay_linear",
            children=[
                GPNode(operator="terminal", value="ret_1d"),
                GPNode(operator="terminal", value="5"),
            ],
        ),
        "alpha_llm_1": GPNode(
            operator="ts_rank",
            children=[
                GPNode(operator="terminal", value="volume"),
                GPNode(operator="terminal", value="20"),
            ],
        ),
        "alpha_llm_2": GPNode(
            operator="/",
            children=[
                GPNode(
                    operator="ts_std",
                    children=[
                        GPNode(operator="terminal", value="close"),
                        GPNode(operator="terminal", value="20"),
                    ],
                ),
                GPNode(
                    operator="ts_mean",
                    children=[
                        GPNode(operator="terminal", value="volume"),
                        GPNode(operator="terminal", value="10"),
                    ],
                ),
            ],
        ),
    }

    for alpha_name, tree in llm_trees.items():
        logger.info("  %s: %s", alpha_name, tree.to_string())

        results = []
        for ticker, ticker_df in feat_df.groupby("symbol"):
            ticker_sorted = ticker_df.sort_values("date")
            alpha_series = _execute_gp_expression_per_ticker(
                tree, ticker_sorted, alpha_name,
            )
            results.append(alpha_series)

        if results:
            combined = pd.concat(results)
            feat_df[alpha_name] = combined.reindex(feat_df.index)
            non_null = feat_df[alpha_name].notna().sum()
            logger.info("    %s: %d non-null values", alpha_name, non_null)

    return feat_df


def finalize_and_save(feat_df: pd.DataFrame) -> Path:
    """Clean up and save precomputed features to parquet."""
    # Drop rows missing essential columns
    required = ["close", "volume", "returns"]
    feat_df = feat_df.dropna(subset=required)
    feat_df = feat_df.sort_values(["symbol", "date"]).reset_index(drop=True)

    alpha_cols = [c for c in feat_df.columns if c.startswith("alpha_")]
    latent_cols = [c for c in feat_df.columns if c.startswith("latent_")]
    logger.info(
        "Final precomputed features: %d rows, %d symbols, "
        "%d alpha columns, %d latent columns, %d total columns",
        len(feat_df),
        feat_df["symbol"].nunique(),
        len(alpha_cols),
        len(latent_cols),
        len(feat_df.columns),
    )
    logger.info("Alpha columns: %s", sorted(alpha_cols)[:20])

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    feat_df.to_parquet(OUTPUT_PATH, index=False, engine="pyarrow")
    logger.info("Saved precomputed features to %s (%.1f MB)", OUTPUT_PATH,
                OUTPUT_PATH.stat().st_size / 1e6)
    return OUTPUT_PATH


def main() -> Path:
    """Execute the full precomputation pipeline."""
    logger.info("=" * 60)
    logger.info("PRECOMPUTE ALL ALPHA FEATURES")
    logger.info("Gate: HYBRID_REGIME_BACKTEST_PERF_20260621")
    logger.info("=" * 60)

    # 1. Load raw data
    raw_df = load_raw_data()

    # 2. Select dynamic universe (104 tickers)
    tickers = select_dynamic_universe(raw_df, DYNAMIC_UNIVERSE_COUNT)

    # 3. Prepare panel
    panel = prepare_panel(raw_df, tickers)

    # 4. Generate core features via UnifiedFeatureAdapter
    feat_df = generate_core_features(panel)

    # 5. Inject latent AE components (renamed as alpha_latent_ae_XX)
    feat_df = inject_latent_ae_components(feat_df)

    # 5b. Compute 7 hybrid regime v1 alphas (Gate: HYBRID_REGIME_BACKTEST_PERF_20260621)
    feat_df = compute_hybrid_regime_alphas(feat_df)

    # 6. Compile and execute top-3 GP expressions per-ticker
    feat_df = compile_and_execute_gp_alphas(feat_df)

    # 7. Generate synthetic LLM alphas
    feat_df = generate_synthetic_llm_alphas(feat_df)

    # 8. Save
    out_path = finalize_and_save(feat_df)

    logger.info("=" * 60)
    logger.info("PRECOMPUTE COMPLETE: %s", out_path)
    logger.info("=" * 60)
    return out_path


if __name__ == "__main__":
    main()
