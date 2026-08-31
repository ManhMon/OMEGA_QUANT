"""Micro LLM Interpretation module for OMEGA_QUANT."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from filelock import FileLock
import pandas as pd
import requests

from omega.core.llm_config import resolve_alpha_llm_config

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_VERSION = "micro_llm_v1"
OUTPUT_COLUMNS = [
    "extraction_id",
    "prompt_version",
    "model",
    "provider",
    "request_sha256",
    "response_sha256",
    "symbol",
    "fiscal_year",
    "fiscal_quarter",
    "period_type",
    "quality",
    "growth_signal",
    "cash_signal",
    "narrative",
    "micro_score",
    "extracted_at",
    "available_at",
]

ALLOWED_QUALITIES = {"strong", "neutral", "weak", "distressed"}

SYSTEM_PROMPT = (
    "You are a fundamental equity analyst for Vietnam stock markets. "
    "Analyze the provided financial statement items (income statement, cash flow, ratios) for a specific company period "
    "and output a strict JSON object with fields: "
    "\"quality\": \"strong\" | \"neutral\" | \"weak\" | \"distressed\", "
    "\"growth_signal\": float between -1.0 and 1.0, "
    "\"cash_signal\": float between -1.0 and 1.0, "
    "\"narrative\": string (maximum 300 characters), "
    "\"micro_score\": float between -1.0 and 1.0 (positive = fundamentally robust/improving, negative = deteriorating/distressed). "
    "Return JSON only without markdown or commentary."
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalized_endpoint(base_url: str) -> str:
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid OpenAI-compatible endpoint") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("invalid OpenAI-compatible endpoint")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("remote LLM endpoint must use HTTPS")
    host = parsed.hostname.lower()
    default_port = 80 if parsed.scheme == "http" else 443
    authority = f"[{host}]" if ":" in host else host
    netloc = authority if port in {None, default_port} else f"{authority}:{port}"
    return urlunsplit((parsed.scheme, netloc, f"{parsed.path.rstrip('/')}/chat/completions", "", ""))


class MicroLLMInterpreter:
    def __init__(
        self,
        repo_root: Path = REPO_ROOT,
        llm_config: dict[str, Any] | None = None,
        max_concurrency: int = 5,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ) -> None:
        self.repo_root = Path(repo_root)
        config = llm_config or resolve_alpha_llm_config(self.repo_root)
        self.config = config
        self.provider = config.get("provider", "mock")
        if self.provider not in {"mock", "openai-compatible"}:
            raise ValueError(f"unsupported provider: {self.provider}")
        if self.provider == "openai-compatible":
            if not all(isinstance(config.get(k), str) and config[k].strip() for k in ("api_key", "base_url", "model")):
                raise ValueError("invalid OpenAI-compatible LLM configuration")
            self.endpoint = _normalized_endpoint(config["base_url"])
        else:
            self.endpoint = "mock://endpoint"
        self.model = config.get("model", "mock-model")
        self.max_concurrency = max(1, min(max_concurrency, 5))
        self.timeout = float(config.get("timeout", timeout))
        self.max_retries = max(1, int(config.get("max_retries", max_retries)))
        self.backoff_factor = float(config.get("backoff_factor", backoff_factor))

    def _post(self, body_bytes: bytes) -> dict[str, Any]:
        if self.provider == "mock":
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "quality": "neutral",
                                    "growth_signal": 0.0,
                                    "cash_signal": 0.0,
                                    "narrative": "Mock fundamental interpretation.",
                                    "micro_score": 0.0,
                                }
                            )
                        }
                    }
                ]
            }

        headers = {"Authorization": f"Bearer {self.config['api_key']}", "Content-Type": "application/json"}
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    self.endpoint,
                    headers=headers,
                    data=body_bytes,
                    timeout=self.timeout,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                return response.json()
            except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.HTTPError) as exc:
                is_retryable = False
                if isinstance(exc, (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout)):
                    is_retryable = True
                elif isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
                    if exc.response.status_code == 429 or exc.response.status_code >= 500:
                        is_retryable = True

                last_exc = exc
                if is_retryable and attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                    logger.warning(
                        "MicroLLMInterpreter POST attempt %d/%d failed with %s; retrying in %.2fs...",
                        attempt,
                        self.max_retries,
                        exc,
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                    continue
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("MicroLLMInterpreter _post failed unexpectedly")

    @staticmethod
    def _validate_result(result: Any) -> dict[str, Any]:
        if not isinstance(result, dict) or not {"quality", "growth_signal", "cash_signal", "narrative", "micro_score"}.issubset(result.keys()):
            raise ValueError("invalid LLM interpretation response")
        quality = str(result["quality"]).strip().lower()
        growth_signal = result["growth_signal"]
        cash_signal = result["cash_signal"]
        narrative = str(result["narrative"]).strip()
        micro_score = result["micro_score"]

        if quality not in ALLOWED_QUALITIES:
            raise ValueError(f"invalid quality: {quality}")
        for val, name in [(growth_signal, "growth_signal"), (cash_signal, "cash_signal"), (micro_score, "micro_score")]:
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or not -1.0 <= val <= 1.0:
                raise ValueError(f"{name} must be a float in [-1.0, 1.0]")
        if len(narrative) > 300:
            narrative = narrative[:300]

        return {
            "quality": quality,
            "growth_signal": float(growth_signal),
            "cash_signal": float(cash_signal),
            "narrative": narrative,
            "micro_score": float(micro_score),
        }

    @staticmethod
    def build_pivot_data(df_group: pd.DataFrame) -> dict[str, Any]:
        """Pivots item_code and item_value into a compact dictionary grouped by endpoint."""
        pivoted: dict[str, dict[str, float]] = {}
        for row in df_group.itertuples(index=False):
            ep = str(getattr(row, "endpoint", "unknown"))
            code = str(getattr(row, "item_code", ""))
            val = getattr(row, "item_value", None)
            if code and pd.notna(val):
                try:
                    val_float = float(val)
                    if math.isfinite(val_float):
                        pivoted.setdefault(ep, {})[code] = val_float
                except (ValueError, TypeError):
                    pass
        return pivoted

    async def _process_single(
        self,
        symbol: str,
        fiscal_year: int,
        fiscal_quarter: int,
        period_type: str,
        pivot_data: dict[str, Any],
        request_sha256: str,
        extraction_id: str,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any] | None:
        context = {
            "symbol": symbol,
            "fiscal_year": int(fiscal_year),
            "fiscal_quarter": int(fiscal_quarter),
            "period_type": period_type,
            "financials": pivot_data,
        }
        context_bytes = _canonical_bytes(context)

        request_payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context_bytes.decode("utf-8")},
            ],
        }
        body_bytes = _canonical_bytes(request_payload)

        try:
            async with semaphore:
                raw_resp = await asyncio.to_thread(self._post, body_bytes)

            resp_bytes = _canonical_bytes(raw_resp)
            response_sha256 = _sha256(resp_bytes)
            content = raw_resp["choices"][0]["message"]["content"]
            parsed_json = json.loads(content)
            validated = self._validate_result(parsed_json)

            now_utc = datetime.now(timezone.utc)
            return {
                "extraction_id": extraction_id,
                "prompt_version": PROMPT_VERSION,
                "model": self.model,
                "provider": self.provider,
                "request_sha256": request_sha256,
                "response_sha256": response_sha256,
                "symbol": symbol,
                "fiscal_year": int(fiscal_year),
                "fiscal_quarter": int(fiscal_quarter),
                "period_type": period_type,
                "quality": validated["quality"],
                "growth_signal": validated["growth_signal"],
                "cash_signal": validated["cash_signal"],
                "narrative": validated["narrative"],
                "micro_score": validated["micro_score"],
                "extracted_at": now_utc,
                "available_at": now_utc,  # Available from inference receipt (C-02)
            }
        except Exception as exc:
            logger.error(
                "MicroLLMInterpreter failed processing symbol=%s period=%s_%dQ%d: %s",
                symbol,
                period_type,
                fiscal_year,
                fiscal_quarter,
                exc,
                exc_info=True,
            )
            return None

    @staticmethod
    def _filter_output(
        df: pd.DataFrame,
        as_of_ts: pd.Timestamp | None = None,
        symbol: str | None = None,
        period_type: str | None = None,
    ) -> pd.DataFrame:
        res = df.copy()
        if as_of_ts is not None and "available_at" in res.columns and not res.empty:
            res_avail = pd.to_datetime(res["available_at"], utc=True, errors="coerce")
            res = res.loc[res_avail.notna() & (res_avail <= as_of_ts)].copy()
        if symbol and "symbol" in res.columns and not res.empty:
            res = res.loc[res["symbol"] == symbol].copy()
        if period_type and "period_type" in res.columns and not res.empty:
            res = res.loc[res["period_type"] == period_type].copy()
        return res

    async def interpret(
        self,
        as_of: str | datetime | pd.Timestamp | None = None,
        symbol: str | None = None,
        period_type: str = "quarter",
        financial_statements_path: Path | str = "data/financial_statements_2015_now.parquet",
        output_path: Path | str = "data/micro_llm_interpretation.parquet",
    ) -> pd.DataFrame:
        fs_path = Path(self.repo_root / financial_statements_path if not Path(financial_statements_path).is_absolute() else financial_statements_path)
        out_path = Path(self.repo_root / output_path if not Path(output_path).is_absolute() else output_path)

        if not fs_path.exists():
            raise FileNotFoundError(f"financial statements file not found: {fs_path}")

        try:
            df = pd.read_parquet(fs_path)
        except Exception as exc:
            raise ValueError(f"failed to read financial statements parquet: {fs_path} ({exc})") from exc

        if "endpoint" in df.columns:
            df = df.loc[df["endpoint"].isin(["income_statement", "cash_flow", "ratios"])].copy()

        if symbol:
            df = df.loc[df["symbol"] == symbol].copy()

        if period_type:
            df = df.loc[df["period_type"] == period_type].copy()

        # Strict PIT eligibility: strictly require available_at and ingested_at; reject missing/nulls (H-01)
        if "available_at" not in df.columns or "ingested_at" not in df.columns:
            raise ValueError("financial statements must contain PIT available_at and ingested_at columns")

        df_avail = pd.to_datetime(df["available_at"], utc=True, errors="coerce")
        df_ingest = pd.to_datetime(df["ingested_at"], utc=True, errors="coerce")
        if df_avail.isna().any() or df_ingest.isna().any():
            raise ValueError("invalid or missing available_at/ingested_at timestamps in financial statements")

        if as_of is not None:
            as_of_ts = pd.to_datetime(as_of, utc=True)
            df = df.loc[(df_avail <= as_of_ts) & (df_ingest <= as_of_ts)].copy()
        else:
            as_of_ts = None
            now_utc = datetime.now(timezone.utc)
            df = df.loc[(df_avail <= now_utc) & (df_ingest <= now_utc)].copy()

        # Deterministic latest revision selection per (symbol, fiscal_year, fiscal_quarter, endpoint, item_code) (H-01)
        if not df.empty:
            df["_avail_dt"] = pd.to_datetime(df["available_at"], utc=True)
            df["_ingest_dt"] = pd.to_datetime(df["ingested_at"], utc=True)
            df["_rev_id"] = df["revision_id"].astype(str) if "revision_id" in df.columns else ""

            sort_keys = [c for c in ["symbol", "fiscal_year", "fiscal_quarter", "endpoint", "item_code"] if c in df.columns]
            sort_cols = sort_keys + ["_avail_dt", "_ingest_dt", "_rev_id"]
            df = df.sort_values(sort_cols, ascending=[True] * len(sort_cols))
            df = df.drop_duplicates(subset=sort_keys, keep="last")
            df = df.drop(columns=["_avail_dt", "_ingest_dt", "_rev_id"], errors="ignore")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = f"{out_path}.lock"

        # Check cache under lock
        cached_ids: set[str] = set()
        existing = pd.DataFrame(columns=OUTPUT_COLUMNS)
        with FileLock(lock_path, timeout=60):
            if out_path.exists():
                try:
                    existing = pd.read_parquet(out_path)
                except Exception as exc:
                    raise ValueError(f"corrupt micro LLM interpretation store: {out_path} ({exc})") from exc

                # Fail-closed on missing/invalid required OUTPUT_COLUMNS (H-03)
                missing_cols = set(OUTPUT_COLUMNS) - set(existing.columns)
                if missing_cols:
                    raise ValueError(f"invalid schema in micro LLM interpretation store: missing columns {missing_cols}")

            if df.empty:
                return self._filter_output(existing, as_of_ts, symbol, period_type)

            if not existing.empty and "extraction_id" in existing.columns:
                cached_ids = set(existing["extraction_id"].dropna().unique())

        group_cols = [c for c in ["symbol", "fiscal_year", "fiscal_quarter", "period_type"] if c in df.columns]
        groups = df.groupby(group_cols, as_index=False)
        semaphore = asyncio.Semaphore(self.max_concurrency)

        tasks = []
        for group_keys, group_df in groups:
            if not isinstance(group_keys, tuple):
                group_keys = (group_keys,)
            key_dict = dict(zip(group_cols, group_keys))
            sym = str(key_dict.get("symbol", ""))
            yr = int(key_dict.get("fiscal_year", 0))
            qtr = int(key_dict.get("fiscal_quarter", 0))
            p_type = str(key_dict.get("period_type", period_type or "quarter"))

            pivot_data = self.build_pivot_data(group_df)
            if not pivot_data:
                continue

            context = {
                "symbol": sym,
                "fiscal_year": int(yr),
                "fiscal_quarter": int(qtr),
                "period_type": p_type,
                "financials": pivot_data,
            }
            context_bytes = _canonical_bytes(context)
            request_payload = {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": context_bytes.decode("utf-8")},
                ],
            }
            body_bytes = _canonical_bytes(request_payload)
            request_sha256 = _sha256(body_bytes)

            # Include endpoint in cache envelope extraction_id hash (H-02)
            cache_envelope = {
                "prompt_version": PROMPT_VERSION,
                "provider": self.provider,
                "endpoint": self.endpoint,
                "model": self.model,
                "request_sha256": request_sha256,
            }
            extraction_id = _sha256(_canonical_bytes(cache_envelope))
            if extraction_id in cached_ids:
                continue

            tasks.append(
                self._process_single(
                    symbol=sym,
                    fiscal_year=int(yr),
                    fiscal_quarter=int(qtr),
                    period_type=p_type,
                    pivot_data=pivot_data,
                    request_sha256=request_sha256,
                    extraction_id=extraction_id,
                    semaphore=semaphore,
                )
            )

        # H-04: Perform LLM inference call outside FileLock
        if tasks:
            results = await asyncio.gather(*tasks)
            valid_results = [r for r in results if r is not None]

            if valid_results:
                incoming = pd.DataFrame(valid_results, columns=OUTPUT_COLUMNS)

                # H-04: Acquire FileLock only during read-modify-write
                with FileLock(lock_path, timeout=60):
                    current_existing = pd.DataFrame(columns=OUTPUT_COLUMNS)
                    if out_path.exists():
                        try:
                            current_existing = pd.read_parquet(out_path)
                        except Exception as exc:
                            raise ValueError(f"corrupt micro LLM interpretation store: {out_path} ({exc})") from exc

                        missing_cols = set(OUTPUT_COLUMNS) - set(current_existing.columns)
                        if missing_cols:
                            raise ValueError(f"invalid schema in micro LLM interpretation store: missing columns {missing_cols}")

                    combined = pd.concat([current_existing, incoming], ignore_index=True) if not current_existing.empty else incoming
                    combined = combined.drop_duplicates(subset=["extraction_id"], keep="last")

                    with tempfile.NamedTemporaryFile(dir=out_path.parent, suffix=".parquet", delete=False) as handle:
                        temp_file = Path(handle.name)
                    try:
                        combined.to_parquet(temp_file, index=False)
                        os.replace(temp_file, out_path)
                    finally:
                        temp_file.unlink(missing_ok=True)
            else:
                with FileLock(lock_path, timeout=60):
                    if out_path.exists():
                        try:
                            combined = pd.read_parquet(out_path)
                        except Exception as exc:
                            raise ValueError(f"corrupt micro LLM interpretation store: {out_path} ({exc})") from exc

                        missing_cols = set(OUTPUT_COLUMNS) - set(combined.columns)
                        if missing_cols:
                            raise ValueError(f"invalid schema in micro LLM interpretation store: missing columns {missing_cols}")
                    else:
                        combined = existing
        else:
            with FileLock(lock_path, timeout=60):
                if out_path.exists():
                    try:
                        combined = pd.read_parquet(out_path)
                    except Exception as exc:
                        raise ValueError(f"corrupt micro LLM interpretation store: {out_path} ({exc})") from exc

                    missing_cols = set(OUTPUT_COLUMNS) - set(combined.columns)
                    if missing_cols:
                        raise ValueError(f"invalid schema in micro LLM interpretation store: missing columns {missing_cols}")
                else:
                    combined = existing

        return self._filter_output(combined, as_of_ts, symbol, period_type)
