"""Fail-closed market dataset loader."""

from datetime import date, datetime
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq
from fastapi import HTTPException

from omega.data.calendar import VNTradingCalendar
from omega.data.vnd_price_contract import VND_FULL


PRIMARY_MARKET_PARQUET_PATH = Path("data/market_2015_now.parquet")
BACKUP_MARKET_PARQUET_PATH = Path(
    "data/market_vci_hsx_hnx_2015_now_20260613.parquet"
)
MARKET_DATASET_SCHEMA = {
    "ticker": "string",
    "date": "datetime",
    "open": "number",
    "high": "number",
    "low": "number",
    "close": "number",
    "volume": "number",
    "exchange": "string",
    "as_of": "timestamp",
    "available_at": "timestamp",
    "source": "string",
    "price_scale": "string",
    "adjusted": "string",
    "rebuild_date": "date",
}
REQUIRED_COLUMNS = ("ticker", "date", "open", "high", "low", "close", "volume", "exchange")
NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume")
MAX_MARKET_ROWS_PER_REQUEST = 100_000
MAX_MARKET_ARTIFACT_ROWS = 2_000_000
MAX_MARKET_ARTIFACT_BYTES = 512 * 1024 * 1024
PIT_COLUMNS = ("as_of", "available_at", "source", "price_scale", "adjusted", "rebuild_date")
PRICE_COLUMNS = ("open", "high", "low", "close")
CANONICAL_COLUMNS = REQUIRED_COLUMNS + PIT_COLUMNS
VALID_EXCHANGES = frozenset({"HOSE", "HNX", "UPCOM"})
VALID_ADJUSTMENTS = frozenset({"raw", "backward_adjusted", "forward_adjusted"})
MAX_VND_FULL_PRICE = 1_000_000_000_000.0
MAX_MARKET_VOLUME = 1_000_000_000_000_000.0
LEGACY_VCI_SOURCES = frozenset({"vnstock_vci", "vci"})
LEGACY_VCI_SIGNATURE = {
    "price_scale": "VND",
    "adjusted": "backward_adjusted",
    "rebuild_date": "2026-06-13",
}
LEGACY_VCI_TIMEZONE = "Asia/Ho_Chi_Minh"
_SECRET_PATTERNS = (
    re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@"),
    re.compile(r"(?i)([?&][^=&#\s]+)=([^&#\s]+)"),
    re.compile(r"(?i)(\b(?:authorization|proxy-authorization)\s*:\s*(?:(?:bearer|basic)\s+)?)[^\s,;]+(?:\s+[^\s,;]+)?"),
    re.compile(r"(?i)(\b(?:bearer|basic)\s+)[^\s,;]+"),
    re.compile(r"(?i)([\"']?(?:x[-_])?(?:api[-_]?key|access[-_]?token|client[-_]?secret|password|token|secret|vnstock[-_]?api[-_]?key)[\"']?\s*[=:]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;}&]+)"),
)


def redact_market_data_error(error: Exception) -> str:
    message = str(error)
    for pattern in _SECRET_PATTERNS:
        message = pattern.sub(r"\1[REDACTED]", message)
    return message


def _dataset_error(detail: str) -> HTTPException:
    return HTTPException(status_code=503, detail=detail)


def _is_timezone_aware(values: pd.Series) -> pd.Series:
    if isinstance(values.dtype, pd.DatetimeTZDtype):
        return pd.Series(True, index=values.index)
    return values.astype("string").str.contains(
        r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True, na=False
    )


def _legacy_vci_rows(dataset: pd.DataFrame) -> pd.Series:
    source = dataset["source"].astype("string").str.strip().str.casefold()
    signature = source.isin(LEGACY_VCI_SOURCES)
    for column, value in LEGACY_VCI_SIGNATURE.items():
        signature &= dataset[column].astype("string").str.strip().eq(value)
    return signature


def _validate_and_normalize_pit(dataset: pd.DataFrame) -> pd.DataFrame:
    if not set(PIT_COLUMNS + ("date",)).issubset(dataset.columns):
        raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")
    normalized = dataset.copy()
    legacy_rows = _legacy_vci_rows(normalized)
    dates = pd.to_datetime(normalized["date"], errors="coerce")
    if dates.isna().any():
        raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")

    as_of_raw = normalized["as_of"]
    available_raw = normalized["available_at"]
    try:
        as_of = pd.to_datetime(as_of_raw, errors="coerce", utc=True, format="mixed")
        available_at = pd.to_datetime(available_raw, errors="coerce", utc=True, format="mixed")
    except (TypeError, ValueError) as error:
        raise _dataset_error("MARKET_DATASET_PIT_INVALID") from error
    as_of_aware = _is_timezone_aware(as_of_raw)
    available_aware = _is_timezone_aware(available_raw)
    now = pd.Timestamp.now(tz="UTC")
    legacy_compatible = pd.Series(False, index=normalized.index)
    legacy_candidates = legacy_rows & ~as_of_aware & ~available_aware
    if legacy_candidates.any():
        legacy_as_of = pd.to_datetime(
            as_of_raw[legacy_candidates], errors="coerce", format="mixed"
        )
        legacy_available = pd.to_datetime(
            available_raw[legacy_candidates], errors="coerce", format="mixed"
        )
        expected_available = dates[legacy_candidates].dt.normalize() + pd.Timedelta(days=1)
        expected_rebuild_date = pd.to_datetime(
            normalized.loc[legacy_candidates, "rebuild_date"], errors="coerce"
        ).dt.date
        valid_legacy = (
            legacy_as_of.notna()
            & legacy_available.notna()
            & legacy_as_of.dt.date.eq(expected_rebuild_date)
            & legacy_available.eq(expected_available)
        )
        if valid_legacy.any():
            valid_index = valid_legacy[valid_legacy].index
            legacy_as_of_utc = legacy_as_of.loc[valid_index].dt.tz_localize(
                LEGACY_VCI_TIMEZONE
            ).dt.tz_convert("UTC")
            legacy_available_utc = legacy_available.loc[valid_index].dt.tz_localize(
                LEGACY_VCI_TIMEZONE
            ).dt.tz_convert("UTC")
            valid_index = valid_index[
                legacy_as_of_utc.le(now)
                & legacy_available_utc.le(now)
            ]
            legacy_compatible.loc[valid_index] = True
            normalized["as_of"] = normalized["as_of"].astype("object")
            normalized["available_at"] = normalized["available_at"].astype("object")
            normalized.loc[valid_index, "as_of"] = legacy_as_of_utc.loc[valid_index]
            normalized.loc[valid_index, "available_at"] = pd.concat(
                [legacy_as_of_utc.loc[valid_index], legacy_available_utc.loc[valid_index]],
                axis=1,
            ).max(axis=1)
    effective_as_of = pd.to_datetime(
        normalized["as_of"], errors="coerce", utc=True, format="mixed"
    )
    if isinstance(dates.dtype, pd.DatetimeTZDtype):
        observation_dates = dates.dt.tz_convert(LEGACY_VCI_TIMEZONE).dt.date
    else:
        observation_dates = dates.dt.date
    authenticated_dates = effective_as_of.dt.tz_convert(LEGACY_VCI_TIMEZONE).dt.date
    observation_after_as_of = pd.Series(False, index=normalized.index)
    comparable_clocks = effective_as_of.notna()
    observation_after_as_of.loc[comparable_clocks] = observation_dates.loc[
        comparable_clocks
    ].gt(authenticated_dates.loc[comparable_clocks])
    invalid = (
        as_of.isna()
        | available_at.isna()
        | effective_as_of.isna()
        | as_of.gt(now)
        | available_at.gt(now)
        | observation_after_as_of
        | (~legacy_compatible & (~as_of_aware | ~available_aware | as_of.gt(available_at)))
    )
    if invalid.any():
        raise _dataset_error("MARKET_DATASET_PIT_INVALID")
    return normalized


def _normalize_price_scale(dataset: pd.DataFrame) -> pd.DataFrame:
    scale = dataset["price_scale"].astype("string").str.strip()
    legacy_rows = _legacy_vci_rows(dataset)
    valid_scale = scale.eq(VND_FULL) | (legacy_rows & scale.eq("VND"))
    if not valid_scale.all():
        raise _dataset_error("MARKET_DATASET_PRICE_SCALE_INVALID")
    if scale.eq(VND_FULL).all():
        return dataset
    normalized = dataset.copy()
    normalized["price_scale"] = VND_FULL
    return normalized


def _schema_matches(
    dataset: pd.DataFrame,
    required_columns: list[str] | None = None,
) -> bool:
    required_columns = required_columns or [
        "ticker", "date", "open", "high", "low", "close", "volume"
    ]
    for column in required_columns:
        kind = MARKET_DATASET_SCHEMA.get(column)
        if kind is None:
            return False
        if column not in dataset:
            return False
        series = dataset[column]
        if column == "ticker" and series.isna().any():
            raise HTTPException(status_code=503, detail="MARKET_DATASET_CORRUPT")
        if kind == "string" and not all(
            isinstance(value, str) for value in series.dropna()
        ):
            return False
        if kind == "datetime" and not pd.api.types.is_datetime64_any_dtype(
            series
        ):
            return False
        if kind == "number" and (
            pd.api.types.is_bool_dtype(series)
            or not pd.api.types.is_numeric_dtype(series)
        ):
            return False
    numeric_columns = [
        column for column in NUMERIC_COLUMNS if column in dataset.columns
    ]
    if numeric_columns and not np.isfinite(
        dataset[numeric_columns].to_numpy()
    ).all():
        return False
    if "volume" in dataset and (dataset["volume"] < 0).any():
        return False
    if "volume" in dataset and (dataset["volume"] > MAX_MARKET_VOLUME).any():
        return False
    ohlc_columns = {"open", "high", "low", "close"}
    if ohlc_columns.issubset(dataset.columns):
        low = dataset["low"]
        high = dataset["high"]
        if not ((low <= dataset["open"]) & (dataset["open"] <= high)).all():
            return False
        if not ((low <= dataset["close"]) & (dataset["close"] <= high)).all():
            return False
        if (dataset[["open", "high", "low", "close"]] <= 0).any().any():
            return False
        prices = dataset[list(PRICE_COLUMNS)].to_numpy(dtype=float)
        if (prices < np.finfo(float).tiny).any() or (prices > MAX_VND_FULL_PRICE).any():
            return False
    if {"ticker", "date"}.issubset(dataset.columns):
        if dataset["date"].isna().any():
            return False
        if dataset.duplicated(["ticker", "date"]).any():
            return False
        if (dataset["date"].dt.date > date.today()).any():
            return False
    return True


def _validate_canonical_metadata(dataset: pd.DataFrame) -> None:
    if any(column not in dataset for column in CANONICAL_COLUMNS):
        raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")
    if dataset.empty:
        return
    if dataset["ticker"].isna().any():
        raise _dataset_error("MARKET_DATASET_CORRUPT")
    if dataset["price_scale"].isna().any() or not all(
        isinstance(value, str) for value in dataset["price_scale"]
    ):
        raise _dataset_error("MARKET_DATASET_PRICE_SCALE_INVALID")
    if any(
        not all(
            value is None or isinstance(value, (str, datetime, pd.Timestamp))
            for value in dataset[column]
        )
        for column in ("as_of", "available_at")
    ):
        raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")
    string_columns = ("ticker", "exchange", "source", "price_scale", "adjusted", "rebuild_date")
    if any(
        dataset[column].isna().any()
        or not all(isinstance(value, str) for value in dataset[column])
        or dataset[column].str.strip().eq("").any()
        for column in string_columns
    ):
        raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")
    if not dataset["exchange"].str.strip().str.upper().isin(VALID_EXCHANGES).all():
        raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")
    if not dataset["ticker"].str.strip().str.fullmatch(r"[A-Za-z0-9_]{1,18}").all():
        raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")
    if not dataset["adjusted"].str.strip().isin(VALID_ADJUSTMENTS).all():
        raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")
    rebuild_dates = pd.to_datetime(dataset["rebuild_date"], format="%Y-%m-%d", errors="coerce")
    if rebuild_dates.isna().any() or rebuild_dates.dt.date.gt(date.today()).any():
        raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")


def validate_market_calendar(value: Any) -> date:
    """Return valid VN trading date; reject invalid non-trading values."""
    if isinstance(value, datetime):
        value = value.date()
    elif isinstance(value, pd.Timestamp):
        value = value.date()
    elif isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail="INVALID_MARKET_DATE",
            ) from error
    if value is pd.NaT or not isinstance(value, date):
        raise HTTPException(status_code=422, detail="INVALID_MARKET_DATE")
    if not VNTradingCalendar.is_trading_day(
        datetime.combine(value, datetime.min.time())
    ):
        raise HTTPException(
            status_code=422,
            detail="MARKET_CALENDAR_NON_TRADING_DAY",
        )
    return value


def _arrow_filter(filters: list[tuple[str, str, Any]]) -> Any:
    expression = None
    for column, operator, value in filters:
        field = ds.field(column)
        if column == "ticker" and operator in {"=", "in"}:
            values = [value] if operator == "=" else value
            variants = {
                variant
                for item in values
                for variant in (str(item).strip().upper(), str(item).strip().lower())
            }
            predicate = field.isin(sorted(variants))
        elif operator == "=":
            predicate = field == value
        elif operator == "in":
            predicate = field.isin(value)
        elif operator == ">=":
            predicate = field >= value
        elif operator == "<=":
            predicate = field <= value
        elif operator == ">":
            predicate = field > value
        elif operator == "<":
            predicate = field < value
        else:
            raise ValueError(f"unsupported filter operator: {operator}")
        expression = predicate if expression is None else expression & predicate
    return expression


def _inspect_market_artifact(
    path: Path,
    filters: list[tuple[str, str, Any]] | None,
) -> list[str]:
    try:
        parquet = pq.ParquetFile(path)
        columns = parquet.schema_arrow.names
        metadata = parquet.metadata
        if len(columns) != len(set(columns)):
            raise _dataset_error("MARKET_DATASET_CORRUPT")
        if not set(REQUIRED_COLUMNS + PIT_COLUMNS).issubset(columns):
            raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")
        if (
            metadata.num_rows > MAX_MARKET_ARTIFACT_ROWS
            or path.stat().st_size > MAX_MARKET_ARTIFACT_BYTES
        ):
            raise _dataset_error("MARKET_DATASET_TOO_LARGE")
        request_rows = (
            ds.dataset(path, format="parquet").count_rows(filter=_arrow_filter(filters))
            if filters
            else metadata.num_rows
        )
    except HTTPException:
        raise
    except Exception as error:
        raise _dataset_error("MARKET_DATASET_CORRUPT") from error
    if request_rows > MAX_MARKET_ROWS_PER_REQUEST:
        raise _dataset_error("MARKET_DATASET_TOO_LARGE")
    return columns


def _resolve_ticker_filters(
    path: Path,
    filters: list[tuple[str, str, Any]] | None,
) -> list[tuple[str, str, Any]] | None:
    if not filters:
        return filters
    ticker_filters = [
        (operator, value)
        for column, operator, value in filters
        if column == "ticker" and operator in {"=", "in"}
    ]
    if not ticker_filters:
        return filters
    try:
        parquet = pq.ParquetFile(path)
        columns = parquet.schema_arrow.names
        if (
            len(columns) != len(set(columns))
            or not set(REQUIRED_COLUMNS + PIT_COLUMNS).issubset(columns)
        ):
            raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")
        if (
            parquet.metadata.num_rows > MAX_MARKET_ARTIFACT_ROWS
            or path.stat().st_size > MAX_MARKET_ARTIFACT_BYTES
        ):
            raise _dataset_error("MARKET_DATASET_TOO_LARGE")
    except HTTPException:
        raise
    except Exception as error:
        raise _dataset_error("MARKET_DATASET_CORRUPT") from error
    requested = {
        str(item).strip().upper()
        for operator, value in ticker_filters
        for item in ([value] if operator == "=" else value)
    }
    non_ticker_filters = [item for item in filters if item[0] != "ticker"]
    variants: set[str] = set()
    try:
        scanner = ds.dataset(path, format="parquet").scanner(
            columns=["ticker"],
            filter=_arrow_filter(non_ticker_filters) if non_ticker_filters else None,
            batch_size=65_536,
        )
        for batch in scanner.to_batches():
            for value in batch.column(0).to_pylist():
                if isinstance(value, str) and value.strip().upper() in requested:
                    variants.add(value)
    except Exception as error:
        raise _dataset_error("MARKET_DATASET_CORRUPT") from error
    # NUL cannot pass the canonical ticker schema, so it is a safe empty pushdown.
    return non_ticker_filters + [("ticker", "in", sorted(variants) or ["\0"])]


def _read_market_dataset(
    path: Path,
    columns: list[str] | None = None,
    filters: list[tuple[str, str, Any]] | None = None,
    allow_empty: bool = False,
) -> pd.DataFrame:
    requested_columns = columns
    resolved_filters = _resolve_ticker_filters(path, filters)
    artifact_columns = _inspect_market_artifact(path, resolved_filters)
    read_columns = list(CANONICAL_COLUMNS)
    if any(column not in artifact_columns for column in read_columns):
        raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")
    try:
        dataset = pd.read_parquet(
            path,
            columns=read_columns,
            filters=resolved_filters,
        )
    except Exception as error:
        raise _dataset_error("MARKET_DATASET_CORRUPT") from error
    if dataset.columns.duplicated().any():
        raise _dataset_error("MARKET_DATASET_CORRUPT")
    if any(
        pd.api.types.is_bool_dtype(dataset[column])
        for column in NUMERIC_COLUMNS
        if column in dataset
    ):
        raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")
    if len(dataset) > MAX_MARKET_ROWS_PER_REQUEST:
        raise _dataset_error("MARKET_DATASET_TOO_LARGE")
    _validate_canonical_metadata(dataset)
    dataset = _validate_and_normalize_pit(dataset)
    dataset = _normalize_price_scale(dataset)
    dataset["ticker"] = dataset["ticker"].str.strip().str.upper()
    dataset["exchange"] = dataset["exchange"].str.strip().str.upper()
    if filters:
        dataset = _apply_canonical_ticker_filters(dataset, filters)
    if not _schema_matches(dataset, list(REQUIRED_COLUMNS)):
        raise _dataset_error("MARKET_DATASET_SCHEMA_MISMATCH")
    trading_days = {
        value
        for value in dataset["date"].dt.date.unique()
        if VNTradingCalendar.is_trading_day(
            datetime.combine(value, datetime.min.time())
        )
    }
    dataset = dataset[dataset["date"].dt.date.isin(trading_days)]
    if dataset.empty and not allow_empty:
        raise _dataset_error("MARKET_DATASET_UNAVAILABLE")
    if requested_columns is not None:
        return dataset.loc[:, requested_columns]
    return dataset


def _apply_canonical_ticker_filters(
    dataset: pd.DataFrame,
    filters: list[tuple[str, str, Any]],
) -> pd.DataFrame:
    result = dataset
    for column, operator, value in filters:
        if column != "ticker" or operator not in {"=", "in"}:
            continue
        requested = [value] if operator == "=" else value
        canonical = {str(item).strip().upper() for item in requested}
        result = result[result["ticker"].isin(canonical)]
    return result


def load_market_dataset(
    columns: list[str] | None = None,
    filters: list[tuple[str, str, Any]] | None = None,
    allow_empty: bool = False,
) -> pd.DataFrame:
    """Load validated primary data, then backup; never synthesize data."""
    if columns == []:
        raise HTTPException(status_code=422, detail="MARKET_DATASET_EMPTY_PROJECTION")
    if columns is not None and (
        not isinstance(columns, list)
        or any(
            not isinstance(column, str) or column not in MARKET_DATASET_SCHEMA
            for column in columns
        )
    ):
        raise HTTPException(
            status_code=503,
            detail="MARKET_DATASET_SCHEMA_MISMATCH",
        )
    existing_paths = [
        path
        for path in (PRIMARY_MARKET_PARQUET_PATH, BACKUP_MARKET_PARQUET_PATH)
        if path.is_file()
    ]
    if not existing_paths:
        raise HTTPException(
            status_code=503,
            detail="MARKET_DATASET_UNAVAILABLE",
        )
    errors: list[HTTPException] = []
    empty_dataset: pd.DataFrame | None = None
    for path in existing_paths:
        try:
            dataset = _read_market_dataset(path, columns, filters, allow_empty=True)
            dataset.attrs["source"] = path.name
            if not dataset.empty:
                return dataset
            empty_dataset = dataset
            errors.clear()
        except HTTPException as error:
            errors.append(error)
    if errors:
        raise errors[-1]
    if empty_dataset is not None:
        if allow_empty:
            return empty_dataset
        raise _dataset_error("MARKET_DATASET_UNAVAILABLE")
    raise _dataset_error("MARKET_DATASET_UNAVAILABLE")
