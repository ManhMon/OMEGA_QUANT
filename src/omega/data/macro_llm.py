"""Macro LLM Interpretation module for OMEGA_QUANT."""

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

from filelock import FileLock, Timeout
import pandas as pd
import requests

from omega.core.llm_config import classify_jev, resolve_alpha_llm_config

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_VERSION = "macro_llm_v1"
OUTPUT_COLUMNS = [
    "extraction_id",
    "prompt_version",
    "model",
    "provider",
    "request_sha256",
    "response_sha256",
    "indicator_set",
    "as_of",
    "trend",
    "regime",
    "narrative",
    "macro_score",
    "extracted_at",
    "available_at",
]

ALLOWED_TRENDS = {"tightening", "neutral", "easing", "improving", "stable", "deteriorating"}
ALLOWED_REGIMES = {"inflation", "deflation", "stagflation", "other", "risk_on", "risk_off", "neutral"}

SYSTEM_PROMPT = (
    "You are a macroeconomic analyst for Vietnam equity markets. "
    "Analyze the provided 12-month rolling macro indicators and output a strict JSON object with fields: "
    "\"trend\": \"tightening\" | \"neutral\" | \"easing\", "
    "\"regime\": \"inflation\" | \"deflation\" | \"stagflation\" | \"other\", "
    "\"narrative\": string (maximum 200 characters), "
    "\"macro_score\": float between -1.0 and 1.0 (positive = expansionary/bullish, negative = contractionary/bearish). "
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


class MacroLLMInterpreter:
    def __init__(
        self,
        repo_root: Path = REPO_ROOT,
        llm_config: dict[str, Any] | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ) -> None:
        self.repo_root = Path(repo_root)
        config = llm_config or resolve_alpha_llm_config(self.repo_root)
        self.config = config
        self.provider = config.get("provider", "mock")
        if self.provider not in {"mock", "openai-compatible", "jev"}:
            raise ValueError(f"unsupported provider: {self.provider}")
        if self.provider == "openai-compatible":
            if not all(isinstance(config.get(k), str) and config[k].strip() for k in ("api_key", "base_url", "model")):
                raise ValueError("invalid OpenAI-compatible LLM configuration")
            self.endpoint = _normalized_endpoint(config["base_url"])
        else:
            self.endpoint = "mock://endpoint"
        self.model = config.get("model", "mock-model")
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
                                    "trend": "neutral",
                                    "regime": "other",
                                    "narrative": "Mock macro regime interpretation.",
                                    "macro_score": 0.0,
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
                        "MacroLLMInterpreter POST attempt %d/%d failed with %s; retrying in %.2fs...",
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
        raise RuntimeError("MacroLLMInterpreter _post failed unexpectedly")

    @staticmethod
    def _validate_result(result: Any) -> dict[str, Any]:
        if not isinstance(result, dict) or not {"trend", "regime", "narrative", "macro_score"}.issubset(result.keys()):
            raise ValueError("invalid LLM interpretation response")
        trend = str(result["trend"]).strip().lower()
        regime = str(result["regime"]).strip().lower()
        narrative = str(result["narrative"]).strip()
        score = result["macro_score"]

        if trend not in ALLOWED_TRENDS:
            raise ValueError(f"invalid trend: {trend}")
        if regime not in ALLOWED_REGIMES:
            raise ValueError(f"invalid regime: {regime}")
        if len(narrative) > 200:
            narrative = narrative[:200]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not -1.0 <= score <= 1.0:
            raise ValueError("macro_score must be a float in [-1.0, 1.0]")

        return {
            "trend": trend,
            "regime": regime,
            "narrative": narrative,
            "macro_score": float(score),
        }

    def build_context(self, df_indicators: pd.DataFrame, as_of_ts: pd.Timestamp) -> dict[str, Any]:
        df = df_indicators.copy()
        if "available_at" not in df.columns or "ingested_at" not in df.columns:
            raise ValueError("macro indicators must contain PIT available_at and ingested_at columns")

        avail_dt = pd.to_datetime(df["available_at"], utc=True, errors="coerce")
        ingest_dt = pd.to_datetime(df["ingested_at"], utc=True, errors="coerce")
        if avail_dt.isna().any() or ingest_dt.isna().any():
            raise ValueError("invalid or missing available_at/ingested_at timestamps")

        # Strict PIT eligibility: both available_at and ingested_at must be <= as_of_ts
        df = df.loc[(avail_dt <= as_of_ts) & (ingest_dt <= as_of_ts)].copy()
        if df.empty:
            return {
                "as_of": str(as_of_ts.isoformat()),
                "indicator_set": [],
                "records": [],
            }

        if "observation_date" not in df.columns or "indicator" not in df.columns:
            raise ValueError("macro indicators must contain indicator and observation_date columns")

        obs_date = pd.to_datetime(df["observation_date"], utc=True, errors="coerce")
        if obs_date.isna().any():
            raise ValueError("invalid observation_date in macro indicators")

        window_start = as_of_ts - pd.DateOffset(months=12)
        df = df.loc[(obs_date >= window_start) & (obs_date <= as_of_ts)].copy()
        if df.empty:
            return {
                "as_of": str(as_of_ts.isoformat()),
                "indicator_set": [],
                "records": [],
            }

        # Deterministic latest revision selection per (indicator, observation_date)
        df["_avail_dt"] = pd.to_datetime(df["available_at"], utc=True)
        df["_ingest_dt"] = pd.to_datetime(df["ingested_at"], utc=True)
        df["_rev_id"] = df["revision_id"].astype(str) if "revision_id" in df.columns else ""
        df = df.sort_values(
            ["indicator", "observation_date", "_avail_dt", "_ingest_dt", "_rev_id"],
            ascending=[True, True, True, True, True],
        )
        df = df.drop_duplicates(subset=["indicator", "observation_date"], keep="last")

        records = []
        for row in df.itertuples(index=False):
            val = getattr(row, "value", None)
            if val is None or not math.isfinite(float(val)):
                continue
            records.append({
                "indicator": str(getattr(row, "indicator", "")),
                "value": float(val),
                "observation_date": str(getattr(row, "observation_date", "")),
            })

        indicator_set = sorted({r["indicator"] for r in records if r["indicator"]})
        return {
            "as_of": str(as_of_ts.isoformat()),
            "indicator_set": indicator_set,
            "records": records,
        }

    async def interpret_as_of(
        self,
        as_of: str | datetime | pd.Timestamp | None = None,
        indicators_path: Path | str = "data/macro_indicators.parquet",
        output_path: Path | str = "data/macro_llm_interpretation.parquet",
    ) -> pd.DataFrame:
        if as_of is not None:
            as_of_ts = pd.to_datetime(as_of, utc=True)
            filter_as_of = True
        else:
            as_of_ts = pd.Timestamp.now(tz=timezone.utc)
            filter_as_of = False

        ind_path = Path(self.repo_root / indicators_path if not Path(indicators_path).is_absolute() else indicators_path)
        out_path = Path(self.repo_root / output_path if not Path(output_path).is_absolute() else output_path)

        if not ind_path.exists():
            raise FileNotFoundError(f"indicators file not found: {ind_path}")

        try:
            df_ind = pd.read_parquet(ind_path)
        except Exception as exc:
            raise ValueError(f"failed to read macro indicators parquet: {exc}") from exc

        context = self.build_context(df_ind, as_of_ts)
        if self.provider == "jev":
            eligible = df_ind.loc[(pd.to_datetime(df_ind["available_at"], utc=True) <= as_of_ts) & (pd.to_datetime(df_ind["ingested_at"], utc=True) <= as_of_ts)]
            available_at = pd.to_datetime(eligible["available_at"], utc=True).max()
            if not context["records"] or pd.isna(available_at):
                raise ValueError("no PIT-eligible macro evidence for JEV")
            decision = await asyncio.to_thread(
                classify_jev, domain="macro", facts=context,
                choices={"regime": ("risk_on", "neutral", "risk_off"), "trend": ("improving", "stable", "deteriorating")},
                cache_path=self.repo_root / "data" / "jev_decisions.sqlite",
                as_of=as_of_ts.to_pydatetime(), available_at=available_at.to_pydatetime(), model=self.model,
            )
            labels = decision["selected"]
            if (not isinstance(labels, dict) or type(labels.get("trend")) is not str
                    or type(labels.get("regime")) is not str
                    or labels["trend"] not in ("improving", "stable", "deteriorating")
                    or labels["regime"] not in ("risk_on", "neutral", "risk_off")):
                raise ValueError("invalid JEV macro labels")
            result = pd.DataFrame([{
                "extraction_id": decision["fingerprint"], "prompt_version": "macro_jev_v1",
                "model": self.model, "provider": "jev", "request_sha256": decision["fingerprint"],
                "response_sha256": _sha256(_canonical_bytes(labels)), "indicator_set": json.dumps(context["indicator_set"]),
                "as_of": as_of_ts, "trend": labels["trend"], "regime": labels["regime"],
                "narrative": "", "macro_score": round(({"risk_on": 1.0, "neutral": 0.0, "risk_off": -1.0}[labels["regime"]] + {"improving": 1.0, "stable": 0.0, "deteriorating": -1.0}[labels["trend"]]) / 2, 6), "extracted_at": pd.Timestamp(decision["decided_at"]),
                "available_at": pd.Timestamp(decision["decided_at"]),
            }], columns=OUTPUT_COLUMNS)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with FileLock(f"{out_path}.lock", timeout=60):
                existing = pd.read_parquet(out_path) if out_path.exists() else pd.DataFrame(columns=OUTPUT_COLUMNS)
                if set(OUTPUT_COLUMNS) - set(existing.columns):
                    raise ValueError("invalid schema in macro LLM interpretation store")
                existing = existing[OUTPUT_COLUMNS]
                combined = pd.concat([existing, result], ignore_index=True).drop_duplicates("extraction_id", keep="first")
                with tempfile.NamedTemporaryFile(dir=out_path.parent, suffix=".parquet", delete=False) as handle:
                    temp_file = Path(handle.name)
                try:
                    combined.to_parquet(temp_file, index=False)
                    os.replace(temp_file, out_path)
                finally:
                    temp_file.unlink(missing_ok=True)
            return combined if not filter_as_of else combined.loc[pd.to_datetime(combined["available_at"], utc=True) <= as_of_ts].copy()
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

        # Cache namespace includes model, prompt_version, provider, endpoint, and request_sha256 (H-02)
        cache_envelope = {
            "prompt_version": PROMPT_VERSION,
            "provider": self.provider,
            "endpoint": self.endpoint,
            "model": self.model,
            "request_sha256": request_sha256,
        }
        extraction_id = _sha256(_canonical_bytes(cache_envelope))

        out_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = f"{out_path}.lock"

        # Check cache under lock
        cached_result = None
        with FileLock(lock_path, timeout=60):
            if out_path.exists():
                try:
                    existing = pd.read_parquet(out_path)
                except Exception as exc:
                    raise ValueError(f"corrupt macro LLM interpretation store: {out_path} ({exc})") from exc

                # Fail-closed on missing/invalid required OUTPUT_COLUMNS (H-03)
                missing_cols = set(OUTPUT_COLUMNS) - set(existing.columns)
                if missing_cols:
                    raise ValueError(f"invalid schema in macro LLM interpretation store: missing columns {missing_cols}")
                existing = existing[OUTPUT_COLUMNS]

                if not existing.empty and "extraction_id" in existing.columns:
                    cached = existing.loc[existing["extraction_id"] == extraction_id]
                    if not cached.empty:
                        cached_result = existing.copy()

        if cached_result is not None:
            # C-02 & C-01: Filter return to requested as_of where available_at <= as_of_ts
            res = cached_result
            if filter_as_of and "available_at" in res.columns:
                res_avail = pd.to_datetime(res["available_at"], utc=True, errors="coerce")
                res = res.loc[res_avail.notna() & (res_avail <= as_of_ts)].copy()
            return res

        # H-04: Perform LLM inference call outside FileLock
        raw_resp = await asyncio.to_thread(self._post, body_bytes)
        resp_bytes = _canonical_bytes(raw_resp)
        response_sha256 = _sha256(resp_bytes)
        content = raw_resp["choices"][0]["message"]["content"]
        parsed_json = json.loads(content)
        validated = self._validate_result(parsed_json)

        now_utc = datetime.now(timezone.utc)
        new_row = {
            "extraction_id": extraction_id,
            "prompt_version": PROMPT_VERSION,
            "model": self.model,
            "provider": self.provider,
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
            "indicator_set": json.dumps(context["indicator_set"]),
            "as_of": as_of_ts,
            "trend": validated["trend"],
            "regime": validated["regime"],
            "narrative": validated["narrative"],
            "macro_score": validated["macro_score"],
            "extracted_at": now_utc,
            "available_at": now_utc,  # Available from inference receipt (C-02)
        }

        # H-04: Acquire FileLock only during read-modify-write
        with FileLock(lock_path, timeout=60):
            existing = pd.DataFrame(columns=OUTPUT_COLUMNS)
            if out_path.exists():
                try:
                    existing = pd.read_parquet(out_path)
                except Exception as exc:
                    raise ValueError(f"corrupt macro LLM interpretation store: {out_path} ({exc})") from exc

                missing_cols = set(OUTPUT_COLUMNS) - set(existing.columns)
                if missing_cols:
                    raise ValueError(f"invalid schema in macro LLM interpretation store: missing columns {missing_cols}")
                existing = existing[OUTPUT_COLUMNS]

            incoming = pd.DataFrame([new_row], columns=OUTPUT_COLUMNS)
            combined = pd.concat([existing, incoming], ignore_index=True) if not existing.empty else incoming
            combined = combined.drop_duplicates(subset=["extraction_id"], keep="last")

            with tempfile.NamedTemporaryFile(dir=out_path.parent, suffix=".parquet", delete=False) as handle:
                temp_file = Path(handle.name)
            try:
                combined.to_parquet(temp_file, index=False)
                os.replace(temp_file, out_path)
            finally:
                temp_file.unlink(missing_ok=True)

        # C-02 & C-01: Filter return to requested as_of where available_at <= as_of_ts
        ret = combined.copy()
        if filter_as_of and "available_at" in ret.columns:
            ret_avail = pd.to_datetime(ret["available_at"], utc=True, errors="coerce")
            ret = ret.loc[ret_avail.notna() & (ret_avail <= as_of_ts)].copy()
        return ret
