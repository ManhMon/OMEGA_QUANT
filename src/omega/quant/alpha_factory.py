"""Facade for V21 alpha computation and neutralization."""

import logging

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from .ultimate_alpha_arsenal import compute_ultimate_alphas, get_alpha_metadata
    from .vn_alphas import compute_vn_alphas
    from .microstructure_alphas import compute_microstructure_alphas
    from .promoted_alphas import compute_promoted_alphas

    ARSENAL_AVAILABLE = True
    _ARSENAL_IMPORT_ERROR = None
except ImportError as exc:
    ARSENAL_AVAILABLE = False
    _ARSENAL_IMPORT_ERROR = exc
    logger.warning("Could not import alpha modules: %s", exc)


class AlphaFactory:
    """Backward-compatible facade for the canonical alpha arsenal."""

    def __init__(self, config=None):
        self.config = config
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def calculate_elite_alphas(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        if not ARSENAL_AVAILABLE:
            raise RuntimeError(f"Alpha arsenal not available: {_ARSENAL_IMPORT_ERROR}")
        return compute_ultimate_alphas(df, **kwargs)

    def compute_all_alphas(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        return self.calculate_elite_alphas(df, **kwargs)


def compute_core_alphas(
    df: pd.DataFrame,
    symbol_col: str = "ticker",
    apply_neutralization: bool = True,
) -> pd.DataFrame:
    """Compute alphas via the canonical arsenal, with a legacy fallback."""
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()

    required_cols = ["date", symbol_col, "open", "high", "low", "close", "volume"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    if ARSENAL_AVAILABLE:
        df_out = compute_ultimate_alphas(df, symbol_col=symbol_col)
    else:
        logger.warning("Using legacy alpha computation (ultimate_alpha_arsenal not available)")
        from .alpha_factory_legacy import compute_core_alphas as compute_legacy_core_alphas

        df_out = compute_legacy_core_alphas(df, symbol_col=symbol_col, apply_neutralization=False)

    if apply_neutralization:
        df_out = _apply_neutralization(df_out, symbol_col=symbol_col)

    return df_out


def _apply_neutralization(df: pd.DataFrame, symbol_col: str = "ticker") -> pd.DataFrame:
    try:
        from omega.quant.neutralization import NeutralizationEngine

        required_neutral_cols = ["sector", "price_bucket", "liquidity_bucket"]
        existing_neutral_cols = [col for col in required_neutral_cols if col in df.columns]

        if existing_neutral_cols:
            logger.info(
                "Validating PIT safety for existing neutralization columns: %s",
                existing_neutral_cols,
            )
            if "date" in df.columns and symbol_col in df.columns:
                df_sorted = df.sort_values(["date", symbol_col])
                for col in existing_neutral_cols:
                    grouped = df_sorted.groupby(symbol_col)[col]
                    nunique_per_symbol = grouped.nunique()
                    if (nunique_per_symbol > 1).any() and col in {"price_bucket", "liquidity_bucket"}:
                        logger.warning(
                            "PIT VALIDATION WARNING: Column '%s' already exists and varies over time.",
                            col,
                        )
                        logger.warning(
                            "  Ensure '%s' uses T-1 lagged data. Current implementation assumes it's PIT-safe.",
                            col,
                        )
                        logger.warning(
                            "  If '%s' uses same-day data, this violates PIT safety!",
                            col,
                        )
                    else:
                        logger.info("Column '%s' appears static (no time variation) - PIT safe", col)

        missing_neutral_cols = [col for col in required_neutral_cols if col not in df.columns]
        if missing_neutral_cols:
            logger.info("Creating missing neutralization columns: %s", missing_neutral_cols)

            if "sector" not in df.columns:
                df["sector"] = "Unknown"
                logger.warning(
                    "Created 'sector' column with default value 'Unknown'. Consider adding real sector data."
                )

            if "price_bucket" not in df.columns:
                if "close" in df.columns and "date" in df.columns and symbol_col in df.columns:
                    df = df.sort_values(["date", symbol_col]).reset_index(drop=True)
                    close_lagged = df.groupby(symbol_col)["close"].shift(1)
                    if close_lagged.isna().all():
                        logger.critical(
                            "PIT VIOLATION BLOCKED: No T-1 close data available for price_bucket creation"
                        )
                        df["price_bucket"] = "P3"
                        logger.warning(
                            "Created 'price_bucket' column with default value 'P3' due to missing T-1 data"
                        )
                    else:
                        def create_price_buckets(group):
                            try:
                                return pd.qcut(
                                    group,
                                    q=5,
                                    labels=["P1", "P2", "P3", "P4", "P5"],
                                    duplicates="drop",
                                )
                            except (ValueError, TypeError):
                                return pd.Series(["P3"] * len(group), index=group.index)

                        df["_close_lagged_temp"] = close_lagged
                        df["price_bucket"] = df.groupby("date")["_close_lagged_temp"].transform(
                            create_price_buckets
                        )
                        df = df.drop(columns=["_close_lagged_temp"])
                        na_count = df["price_bucket"].isna().sum()
                        if na_count > 0:
                            logger.warning(
                                "PIT validation: %s rows have NaN price_bucket due to missing T-1 data",
                                na_count,
                            )
                            df["price_bucket"] = df["price_bucket"].fillna("P3")
                elif "close" in df.columns:
                    logger.critical(
                        "PIT VIOLATION BLOCKED: 'date' or symbol column missing, cannot lag close price"
                    )
                    df["price_bucket"] = "P3"
                else:
                    df["price_bucket"] = "P3"
                    logger.warning("Created 'price_bucket' column with default value 'P3'")

            if "liquidity_bucket" not in df.columns:
                if "volume" in df.columns and "date" in df.columns and symbol_col in df.columns:
                    volume_lagged = df.groupby(symbol_col)["volume"].shift(1)
                    if volume_lagged.isna().all():
                        logger.critical(
                            "PIT VIOLATION BLOCKED: No T-1 volume data available for liquidity_bucket creation"
                        )
                        df["liquidity_bucket"] = "L3"
                        logger.warning(
                            "Created 'liquidity_bucket' column with default value 'L3' due to missing T-1 data"
                        )
                    else:
                        def create_liquidity_buckets(group):
                            try:
                                return pd.qcut(
                                    group,
                                    q=5,
                                    labels=["L1", "L2", "L3", "L4", "L5"],
                                    duplicates="drop",
                                )
                            except (ValueError, TypeError):
                                return pd.Series(["L3"] * len(group), index=group.index)

                        df["_volume_lagged_temp"] = volume_lagged
                        df["liquidity_bucket"] = df.groupby("date")["_volume_lagged_temp"].transform(
                            create_liquidity_buckets
                        )
                        df = df.drop(columns=["_volume_lagged_temp"])
                        na_count = df["liquidity_bucket"].isna().sum()
                        if na_count > 0:
                            logger.warning(
                                "PIT validation: %s rows have NaN liquidity_bucket due to missing T-1 data",
                                na_count,
                            )
                            df["liquidity_bucket"] = df["liquidity_bucket"].fillna("L3")
                elif "volume" in df.columns:
                    logger.critical(
                        "PIT VIOLATION BLOCKED: 'date' or symbol column missing, cannot lag volume"
                    )
                    df["liquidity_bucket"] = "L3"
                else:
                    df["liquidity_bucket"] = "L3"
                    logger.warning("Created 'liquidity_bucket' column with default value 'L3'")

        if "date" in df.columns or "timestamp" in df.columns:
            date_col = "date" if "date" in df.columns else "timestamp"
            if df[date_col].nunique() > 1:
                logger.info("PIT validation: Neutralization features should be computed from T-1 data")
                logger.info("Sample dates in neutralization: %s", df[date_col].unique()[:3])

        alpha_cols = [col for col in df.columns if col.startswith("alpha_")]
        if not alpha_cols:
            logger.warning("No alpha columns found for neutralization")
            return df

        if not isinstance(df.index, pd.MultiIndex):
            df_indexed = df.set_index(["date", symbol_col])
        else:
            df_indexed = df

        engine = NeutralizationEngine(
            min_l3_size=5,
            min_l2_size=10,
            winsorize_lower=0.01,
            winsorize_upper=0.99,
        )
        df_neutralized = engine.neutralize_panel(
            df_indexed,
            alpha_cols=alpha_cols,
            sector_col="sector",
            price_level_col="price_bucket",
            liquidity_col="liquidity_bucket",
        )

        for alpha_col in alpha_cols:
            neutral_col = f"{alpha_col}_neutral"
            if neutral_col in df_neutralized.columns:
                df_neutralized[alpha_col] = df_neutralized[neutral_col]
                df_neutralized = df_neutralized.drop(columns=[neutral_col])

        logger.info("Neutralization applied to %s alpha columns (raw alphas replaced)", len(alpha_cols))

        if not isinstance(df.index, pd.MultiIndex):
            df_neutralized = df_neutralized.reset_index()

        return df_neutralized
    except ImportError as exc:
        logger.warning("NeutralizationEngine not available: %s. Skipping neutralization.", exc)
        return df
    except Exception as exc:
        logger.error("Error during neutralization: %s. Returning unneutralized alphas.", exc)
        return df
