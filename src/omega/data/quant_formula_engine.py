"""
Quant Formula Engine (Component 1).
Evaluates 5 quantitative financial & macro metrics in a PIT-safe manner:
1. Piotroski F-Score (0-9 with corporate action adjustments for F7)
2. Sloan Accrual Ratio ((Net Income - Operating Cash Flow) / Average Total Assets)
3. Altman Z-score (classic public manufacturing, Z-prime, Z-double-prime with sector mapping)
4. Interbank Spread Robust MAD Z-score (window=52, min_obs=26)
5. FX Stress Index (20-session return + realized volatility)

Includes batch ProcessPoolExecutor/vectorized parallelism.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Sector classification mappings
BANK_SECTORS = {"bank", "banking", "ngan_hang", "ngân hàng"}
SECURITIES_SECTORS = {"securities", "chung_khoan", "chứng khoán"}
INSURANCE_SECTORS = {"insurance", "bao_hiem", "bảo hiểm"}
FINANCIAL_SECTORS = BANK_SECTORS | SECURITIES_SECTORS | INSURANCE_SECTORS | {"financial", "tai_chinh", "tài chính"}
MANUFACTURING_SECTORS = {
    "manufacturing", "industrial", "san_xuat", "sản xuất", "materials", "vat_lieu",
    "consumer_goods", "hang_tieu_dung", "chemicals", "hoa_chat", "oil_gas", "dau_khi",
    "construction", "xay_dung", "automobiles", "oto"
}


def _parse_iso_to_utc(dt_val: Any) -> datetime:
    """
    Parse string/timestamp/datetime to UTC timezone-aware datetime.
    Strictly rejects None, pd.NaT, NaN, non-finite, and invalid datetimes fail-closed with ValueError.
    """
    if dt_val is None:
        raise ValueError("Invalid datetime: None")
    if pd.isna(dt_val):
        raise ValueError(f"Invalid datetime (NA/NaT/NaN): {dt_val!r}")
    if isinstance(dt_val, pd.Timestamp):
        if pd.isna(dt_val):
            raise ValueError("Invalid pd.Timestamp: NaT")
        py_dt = dt_val.to_pydatetime()
        if pd.isna(py_dt) or not isinstance(py_dt, datetime):
            raise ValueError(f"Invalid converted pydatetime: {py_dt!r}")
        if py_dt.tzinfo is None:
            return py_dt.replace(tzinfo=timezone.utc)
        return py_dt.astimezone(timezone.utc)
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            return dt_val.replace(tzinfo=timezone.utc)
        return dt_val.astimezone(timezone.utc)
    if isinstance(dt_val, (int, float)):
        if not math.isfinite(dt_val):
            raise ValueError(f"Non-finite numeric datetime not supported: {dt_val}")
        raise ValueError(f"Numeric timestamp not supported: {dt_val}")
    if not isinstance(dt_val, str):
        raise ValueError(f"Unsupported datetime type: {type(dt_val).__name__}")
    str_val = dt_val.strip()
    if not str_val or str_val.lower() in {"nat", "nan", "none", "null", "undefined", "inf", "-inf"}:
        raise ValueError(f"Invalid datetime string: {str_val!r}")
    if str_val.endswith("Z"):
        str_val = str_val[:-1] + "+00:00"
    dt = datetime.fromisoformat(str_val)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def validate_pit_clocks(decision_cutoff: Union[str, datetime], knowledge_cutoff: Union[str, datetime]) -> Tuple[datetime, datetime]:
    """Validate decision_cutoff and knowledge_cutoff. Must satisfy knowledge_cutoff <= decision_cutoff."""
    d_dt = _parse_iso_to_utc(decision_cutoff)
    k_dt = _parse_iso_to_utc(knowledge_cutoff)
    if k_dt > d_dt:
        raise ValueError(f"Clock order violation: knowledge_cutoff ({k_dt.isoformat()}) > decision_cutoff ({d_dt.isoformat()})")
    return d_dt, k_dt


def filter_pit_records(
    records: Sequence[Dict[str, Any]],
    decision_cutoff_dt: datetime,
    knowledge_cutoff_dt: datetime,
) -> List[Dict[str, Any]]:
    """Filter records by available_at <= decision_cutoff and ingested_at <= knowledge_cutoff. Fail-closed on missing clocks."""
    valid: List[Dict[str, Any]] = []
    for r in records:
        if not isinstance(r, dict):
            continue
        avail_raw = r.get("available_at")
        ingest_raw = r.get("ingested_at")
        if avail_raw is None or ingest_raw is None:
            continue
        try:
            avail_dt = _parse_iso_to_utc(avail_raw)
            ingest_dt = _parse_iso_to_utc(ingest_raw)
            if avail_dt <= decision_cutoff_dt and ingest_dt <= knowledge_cutoff_dt:
                valid.append(r)
        except Exception:
            continue
    return valid


def _calculate_business_days_between(dt_start: datetime, dt_end: datetime) -> int:
    """Calculate exact business days between two datetimes using numpy.busday_count."""
    d1 = dt_start.date().isoformat()
    d2 = dt_end.date().isoformat()
    if d2 <= d1:
        return 0
    return int(np.busday_count(d1, d2))


def _filter_financial_dict(
    fin_dict: Optional[Dict[str, Any]],
    decision_cutoff_dt: Optional[datetime] = None,
    knowledge_cutoff_dt: Optional[datetime] = None,
) -> Dict[str, Optional[float]]:
    """Filter financial dict with fail-closed dual-clock enforcement."""
    if not fin_dict or not isinstance(fin_dict, dict):
        return {}
    if decision_cutoff_dt is not None or knowledge_cutoff_dt is not None:
        if "available_at" not in fin_dict or "ingested_at" not in fin_dict:
            return {}  # missing required clocks -> fail-closed
        try:
            avail_dt = _parse_iso_to_utc(fin_dict["available_at"])
            ingest_dt = _parse_iso_to_utc(fin_dict["ingested_at"])
            if decision_cutoff_dt is not None and avail_dt > decision_cutoff_dt:
                return {}  # future clock -> fail-closed
            if knowledge_cutoff_dt is not None and ingest_dt > knowledge_cutoff_dt:
                return {}  # future clock -> fail-closed
            # Validate as_of <= decision_cutoff if as_of is provided
            # If as_of is provided, it must be parseable and valid; fail-closed on NaT/invalid
            if "as_of" in fin_dict and fin_dict["as_of"] is not None:
                as_of_dt = _parse_iso_to_utc(fin_dict["as_of"])
                if decision_cutoff_dt is not None and as_of_dt > decision_cutoff_dt:
                    return {}  # future as_of -> fail-closed
            # Validate date <= decision_cutoff if date is provided
            # If date is provided, it must be parseable and valid; fail-closed on NaT/invalid
            if "date" in fin_dict and fin_dict["date"] is not None:
                date_dt = _parse_iso_to_utc(fin_dict["date"])
                if decision_cutoff_dt is not None and date_dt > decision_cutoff_dt:
                    return {}  # future date -> fail-closed
        except Exception:
            return {}
    clean: Dict[str, Any] = {}
    if "as_of" in fin_dict and fin_dict["as_of"] is not None:
        try:
            clean["as_of"] = _parse_iso_to_utc(fin_dict["as_of"]).isoformat()
        except Exception:
            return {}
    if "date" in fin_dict and fin_dict["date"] is not None:
        try:
            clean["date"] = _parse_iso_to_utc(fin_dict["date"]).isoformat()
        except Exception:
            return {}
    for k, v in fin_dict.items():
        if k in {"available_at", "ingested_at", "as_of", "date", "symbol"}:
            continue
        if v is not None and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            clean[k] = float(v)
        elif v is None:
            clean[k] = None
    return clean


def _extract_market_equity(
    me_val: Any,
    decision_cutoff_dt: Optional[datetime] = None,
    knowledge_cutoff_dt: Optional[datetime] = None,
) -> Optional[float]:
    """Extract and validate market equity with dual-clock support (dict or scalar)."""
    if me_val is None:
        return None
    if decision_cutoff_dt is not None or knowledge_cutoff_dt is not None:
        if not isinstance(me_val, dict):
            return None  # reject raw scalar when cutoffs are present
        avail_raw = me_val.get("available_at")
        ingest_raw = me_val.get("ingested_at")
        if avail_raw is None or ingest_raw is None:
            return None  # fail-closed on missing clock
        try:
            avail_dt = _parse_iso_to_utc(avail_raw)
            ingest_dt = _parse_iso_to_utc(ingest_raw)
            if decision_cutoff_dt is not None and avail_dt > decision_cutoff_dt:
                return None  # fail-closed on future clock
            if knowledge_cutoff_dt is not None and ingest_dt > knowledge_cutoff_dt:
                return None  # fail-closed on future clock
            # Validate as_of <= decision_cutoff if as_of is provided
            # If as_of is present, must be parseable; fail-closed on NaT/invalid
            if "as_of" in me_val and me_val["as_of"] is not None:
                as_of_dt = _parse_iso_to_utc(me_val["as_of"])
                if decision_cutoff_dt is not None and as_of_dt > decision_cutoff_dt:
                    return None  # future as_of -> fail-closed
        except Exception:
            return None
        val = me_val.get("value", me_val.get("market_equity", me_val.get("market_cap", me_val.get("close"))))
        if val is not None and isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val) and val > 0:
            return float(val)
        return None
    # No cutoffs specified: allow scalar or dict
    if isinstance(me_val, (int, float)) and not isinstance(me_val, bool):
        val = float(me_val)
        return val if math.isfinite(val) and val > 0 else None
    if isinstance(me_val, dict):
        if "as_of" in me_val and me_val["as_of"] is not None:
            try:
                _parse_iso_to_utc(me_val["as_of"])
            except Exception:
                return None
        val = me_val.get("value", me_val.get("market_equity", me_val.get("market_cap", me_val.get("close"))))
        if val is not None and isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val) and val > 0:
            return float(val)
    return None


def _hash_macro_series(series: Any) -> str:
    """Compute deterministic SHA256 digest of macro series."""
    serialized = json.dumps(series, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PiotroskiResult:
    f_score: Optional[int]
    partial_score: int
    criteria_available: int
    coverage: float
    criteria: Dict[str, Optional[int]]
    normalized_score: Optional[float]
    missing_reason: Optional[str] = None


@dataclass(frozen=True)
class SloanResult:
    sloan_ratio: Optional[float]
    normalized_score: Optional[float]
    missing_reason: Optional[str] = None


@dataclass(frozen=True)
class AltmanResult:
    z_score: Optional[float]
    variant: str  # "classic", "z_prime", "z_double_prime", "not_applicable"
    zone: Optional[str]  # "distress", "gray", "safe"
    normalized_score: Optional[float]
    missing_reason: Optional[str] = None


@dataclass(frozen=True)
class InterbankResult:
    z_score: Optional[float]
    normalized_score: Optional[float]
    observations_used: int
    missing_reason: Optional[str] = None


@dataclass(frozen=True)
class FXStressResult:
    stress_index: Optional[float]
    normalized_score: Optional[float]
    components: Dict[str, Optional[float]]
    missing_reason: Optional[str] = None


@dataclass
class QuantEvaluationRecord:
    symbol: str
    decision_cutoff: str
    knowledge_cutoff: str
    piotroski: Optional[PiotroskiResult] = None
    sloan: Optional[SloanResult] = None
    altman: Optional[AltmanResult] = None
    interbank: Optional[InterbankResult] = None
    fx: Optional[FXStressResult] = None
    quant_score: Optional[float] = None
    quant_confidence: float = 0.0
    weight_coverage: float = 0.0
    hard_veto: bool = False
    hard_veto_reasons: List[str] = field(default_factory=list)
    missing_reasons: List[str] = field(default_factory=list)
    quant_status: str = "valid"  # "valid", "unscorable", "veto"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "decision_cutoff": self.decision_cutoff,
            "knowledge_cutoff": self.knowledge_cutoff,
            "piotroski_f_score": self.piotroski.f_score if self.piotroski else None,
            "piotroski_partial_score": self.piotroski.partial_score if self.piotroski else None,
            "piotroski_normalized": self.piotroski.normalized_score if self.piotroski else None,
            "sloan_ratio": self.sloan.sloan_ratio if self.sloan else None,
            "sloan_normalized": self.sloan.normalized_score if self.sloan else None,
            "altman_z_score": self.altman.z_score if self.altman else None,
            "altman_variant": self.altman.variant if self.altman else None,
            "altman_zone": self.altman.zone if self.altman else None,
            "altman_normalized": self.altman.normalized_score if self.altman else None,
            "interbank_z_score": self.interbank.z_score if self.interbank else None,
            "interbank_normalized": self.interbank.normalized_score if self.interbank else None,
            "fx_stress_index": self.fx.stress_index if self.fx else None,
            "fx_normalized": self.fx.normalized_score if self.fx else None,
            "quant_score": self.quant_score,
            "quant_confidence": self.quant_confidence,
            "weight_coverage": self.weight_coverage,
            "hard_veto": self.hard_veto,
            "hard_veto_reasons": self.hard_veto_reasons,
            "missing_reasons": self.missing_reasons,
            "quant_status": self.quant_status,
        }


# ---------------------------------------------------------------------------
# Core Formulas (Vectorized & Pure Functions)
# ---------------------------------------------------------------------------

def calculate_piotroski_f_score(
    curr_fin: Dict[str, Optional[Any]],
    prev_fin: Dict[str, Optional[Any]],
    corporate_actions: Optional[List[Dict[str, Any]]] = None,
    decision_cutoff_dt: Optional[datetime] = None,
    prev_fin_date: Optional[Union[str, datetime]] = None,
    curr_fin_date: Optional[Union[str, datetime]] = None,
) -> PiotroskiResult:
    """
    Calculate Piotroski F-Score (0-9) using current and prior fiscal year data.

    Criteria:
    F1: ROA > 0 (Net Income / Avg Total Assets > 0 or Net Income > 0)
    F2: CFO > 0 (Operating Cash Flow > 0)
    F3: Delta ROA > 0 (ROA_t > ROA_t-1)
    F4: Accrual Quality (CFO_t > Net Income_t)
    F5: Delta Leverage < 0 (LTD_t / Assets_t < LTD_t-1 / Assets_t-1)
    F6: Delta Liquidity > 0 (Current Ratio_t > Current Ratio_t-1)
    F7: No Economic Dilution (Shares_t <= PriorSharesAdjusted_t-1)
    F8: Delta Gross Margin > 0 (Gross Margin_t > Gross Margin_t-1)
    F9: Delta Asset Turnover > 0 (Turnover_t > Turnover_t-1)
    """
    criteria: Dict[str, Optional[int]] = {
        "F1_ROA_POS": None,
        "F2_CFO_POS": None,
        "F3_ROA_UP": None,
        "F4_ACCRUAL": None,
        "F5_LTD_DOWN": None,
        "F6_CR_UP": None,
        "F7_NO_DILUTION": None,
        "F8_GM_UP": None,
        "F9_ATO_UP": None,
    }

    # Extract Current Year
    ni_t = curr_fin.get("net_income")
    cfo_t = curr_fin.get("operating_cash_flow")
    ta_t = curr_fin.get("total_assets")
    ltd_t = curr_fin.get("long_term_debt")
    ca_t = curr_fin.get("current_assets")
    cl_t = curr_fin.get("current_liabilities")
    rev_t = curr_fin.get("revenue")
    gp_t = curr_fin.get("gross_profit")
    shares_t = curr_fin.get("shares_outstanding")

    # Extract Prior Year
    ni_tm1 = prev_fin.get("net_income")
    ta_tm1 = prev_fin.get("total_assets")
    ta_tm2 = prev_fin.get("prior_total_assets")  # for avg assets tm1 if available
    ltd_tm1 = prev_fin.get("long_term_debt")
    ca_tm1 = prev_fin.get("current_assets")
    cl_tm1 = prev_fin.get("current_liabilities")
    rev_tm1 = prev_fin.get("revenue")
    gp_tm1 = prev_fin.get("gross_profit")
    shares_tm1 = prev_fin.get("shares_outstanding")

    # Average Total Assets
    avg_ta_t = (ta_t + ta_tm1) / 2.0 if (ta_t is not None and ta_tm1 is not None and (ta_t + ta_tm1) > 0) else ta_t
    avg_ta_tm1 = (ta_tm1 + ta_tm2) / 2.0 if (ta_tm1 is not None and ta_tm2 is not None and (ta_tm1 + ta_tm2) > 0) else ta_tm1

    # F1: Positive ROA
    if ni_t is not None and avg_ta_t is not None and avg_ta_t > 0:
        roa_t = ni_t / avg_ta_t
        criteria["F1_ROA_POS"] = 1 if roa_t > 0 else 0
    elif ni_t is not None:
        criteria["F1_ROA_POS"] = 1 if ni_t > 0 else 0

    # F2: Positive CFO
    if cfo_t is not None:
        criteria["F2_CFO_POS"] = 1 if cfo_t > 0 else 0

    # F3: ROA Growth
    if ni_t is not None and ni_tm1 is not None and avg_ta_t is not None and avg_ta_tm1 is not None and avg_ta_t > 0 and avg_ta_tm1 > 0:
        roa_t = ni_t / avg_ta_t
        roa_tm1 = ni_tm1 / avg_ta_tm1
        criteria["F3_ROA_UP"] = 1 if roa_t > roa_tm1 else 0

    # F4: Accrual Quality (CFO > Net Income)
    if cfo_t is not None and ni_t is not None:
        criteria["F4_ACCRUAL"] = 1 if cfo_t > ni_t else 0

    # F5: Lower Long-Term Debt / Assets (Nullable check - no silent 0 default)
    if ltd_t is not None and ltd_tm1 is not None and ta_t is not None and ta_tm1 is not None and ta_t > 0 and ta_tm1 > 0:
        lev_t = ltd_t / ta_t
        lev_tm1 = ltd_tm1 / ta_tm1
        criteria["F5_LTD_DOWN"] = 1 if lev_t < lev_tm1 else 0

    # F6: Higher Current Ratio
    if ca_t is not None and cl_t is not None and ca_tm1 is not None and cl_tm1 is not None:
        if cl_t > 0 and cl_tm1 > 0:
            cr_t = ca_t / cl_t
            cr_tm1 = ca_tm1 / cl_tm1
            criteria["F6_CR_UP"] = 1 if cr_t > cr_tm1 else 0

    # F7: No Economic Dilution (adjusted for stock split / reverse_split / bonus)
    if shares_t is not None and shares_tm1 is not None and shares_tm1 > 0:
        neutral_factor = 1.0
        lineage_valid = True

        # Extract prev_fin and curr_fin boundary dates if available
        prev_fin_date_dt: Optional[datetime] = None
        curr_fin_date_dt: Optional[datetime] = None

        prev_raw_date = prev_fin_date if prev_fin_date is not None else prev_fin.get("as_of", prev_fin.get("date"))
        if prev_raw_date is not None:
            try:
                prev_fin_date_dt = _parse_iso_to_utc(prev_raw_date)
            except Exception:
                prev_fin_date_dt = None
                lineage_valid = False

        curr_raw_date = curr_fin_date if curr_fin_date is not None else curr_fin.get("as_of", curr_fin.get("date"))
        if curr_raw_date is not None:
            try:
                curr_fin_date_dt = _parse_iso_to_utc(curr_raw_date)
            except Exception:
                curr_fin_date_dt = None
                lineage_valid = False

        # If explicit boundary dates were passed but failed parsing (e.g. pd.NaT), fail closed immediately
        if prev_fin_date is not None and prev_fin_date_dt is None:
            lineage_valid = False
        if curr_fin_date is not None and curr_fin_date_dt is None:
            lineage_valid = False

        if corporate_actions is not None:
            if not isinstance(corporate_actions, list):
                lineage_valid = False
            elif len(corporate_actions) > 0:
                # Corporate actions are supplied: require valid boundary dates with prev_fin_date < curr_fin_date
                if prev_fin_date_dt is None or curr_fin_date_dt is None or prev_fin_date_dt >= curr_fin_date_dt:
                    lineage_valid = False
                else:
                    for ca in corporate_actions:
                        if not isinstance(ca, dict):
                            lineage_valid = False
                            break

                        # action_type check: must be str
                        atype_raw = ca.get("action_type")
                        if not isinstance(atype_raw, str):
                            lineage_valid = False
                            break
                        atype = atype_raw.strip().lower()

                        # params check: must be dict or None
                        params = ca.get("params")
                        if params is not None and not isinstance(params, dict):
                            lineage_valid = False
                            break
                        params_dict = params if isinstance(params, dict) else {}

                        # status check: strictly exact canonical status == 'completed'
                        status = ca.get("status")
                        if not isinstance(status, str) or status != "completed":
                            lineage_valid = False
                            break

                        # effective_date check: must be parseable datetime/Timestamp
                        eff_raw = ca.get("effective_date")
                        if eff_raw is None:
                            lineage_valid = False
                            break
                        try:
                            eff_dt = _parse_iso_to_utc(eff_raw)
                            if decision_cutoff_dt is not None and eff_dt > decision_cutoff_dt:
                                continue  # future effective date -> skip adjustment
                            # Strictly bound actions to the measurement interval between prev_fin date and curr_fin date
                            # (prev_fin_date < effective_date <= curr_fin_date)
                            if eff_dt <= prev_fin_date_dt or eff_dt > curr_fin_date_dt:
                                continue  # outside measurement window
                        except Exception:
                            lineage_valid = False
                            break

                        # Neutralize stock split, reverse split, stock bonus
                        if atype in {"split", "stock_split"}:
                            ratio = ca.get("split_ratio")
                            if ratio is None:
                                ratio = params_dict.get("split_ratio")
                            if ratio is not None and isinstance(ratio, (int, float)) and not isinstance(ratio, bool) and math.isfinite(ratio) and ratio > 0:
                                neutral_factor *= float(ratio)
                            else:
                                lineage_valid = False
                                break
                        elif atype in {"reverse_split", "stock_reverse_split"}:
                            ratio = ca.get("split_ratio")
                            if ratio is None:
                                ratio = params_dict.get("split_ratio")
                            if ratio is not None and isinstance(ratio, (int, float)) and not isinstance(ratio, bool) and math.isfinite(ratio) and ratio > 0:
                                neutral_factor /= float(ratio)
                            elif ca.get("reverse_split_ratio") is not None and isinstance(ca.get("reverse_split_ratio"), (int, float)) and not isinstance(ca.get("reverse_split_ratio"), bool) and math.isfinite(ca.get("reverse_split_ratio")) and ca.get("reverse_split_ratio") > 0:
                                neutral_factor /= float(ca.get("reverse_split_ratio"))
                            elif params_dict.get("reverse_split_ratio") is not None and isinstance(params_dict.get("reverse_split_ratio"), (int, float)) and not isinstance(params_dict.get("reverse_split_ratio"), bool) and math.isfinite(params_dict.get("reverse_split_ratio")) and params_dict.get("reverse_split_ratio") > 0:
                                neutral_factor /= float(params_dict.get("reverse_split_ratio"))
                            elif ca.get("factor") is not None and isinstance(ca.get("factor"), (int, float)) and not isinstance(ca.get("factor"), bool) and math.isfinite(ca.get("factor")) and ca.get("factor") > 0:
                                neutral_factor *= float(ca.get("factor"))
                            elif params_dict.get("factor") is not None and isinstance(params_dict.get("factor"), (int, float)) and not isinstance(params_dict.get("factor"), bool) and math.isfinite(params_dict.get("factor")) and params_dict.get("factor") > 0:
                                neutral_factor *= float(params_dict.get("factor"))
                            else:
                                lineage_valid = False
                                break
                        elif atype in {"bonus", "stock_bonus"}:
                            bonus_ratio = ca.get("bonus_ratio")
                            if bonus_ratio is None:
                                bonus_ratio = params_dict.get("bonus_ratio")
                            if bonus_ratio is not None and isinstance(bonus_ratio, (int, float)) and not isinstance(bonus_ratio, bool) and math.isfinite(bonus_ratio) and bonus_ratio >= 0:
                                neutral_factor *= (1.0 + float(bonus_ratio))
                            else:
                                lineage_valid = False
                                break
                        elif atype in {"rights", "rights_issue", "issuance", "share_issuance", "esop"}:
                            # Economic dilution: left unadjusted in neutral factor
                            pass
                        else:
                            # Ambiguous/unknown action type affecting shares without clear lineage -> fail-closed
                            lineage_valid = False
                            break

        if lineage_valid:
            prior_shares_adj = shares_tm1 * neutral_factor
            # Pass if current shares <= adjusted prior shares (e.g. buyback or no dilution)
            criteria["F7_NO_DILUTION"] = 1 if shares_t <= (prior_shares_adj + 1e-5) else 0
        else:
            criteria["F7_NO_DILUTION"] = None

    # F8: Higher Gross Margin
    if gp_t is not None and rev_t is not None and gp_tm1 is not None and rev_tm1 is not None:
        if rev_t > 0 and rev_tm1 > 0:
            gm_t = gp_t / rev_t
            gm_tm1 = gp_tm1 / rev_tm1
            criteria["F8_GM_UP"] = 1 if gm_t > gm_tm1 else 0

    # F9: Higher Asset Turnover
    if rev_t is not None and rev_tm1 is not None and avg_ta_t is not None and avg_ta_tm1 is not None:
        if avg_ta_t > 0 and avg_ta_tm1 > 0:
            ato_t = rev_t / avg_ta_t
            ato_tm1 = rev_tm1 / avg_ta_tm1
            criteria["F9_ATO_UP"] = 1 if ato_t > ato_tm1 else 0

    valid_vals = [v for v in criteria.values() if v is not None]
    avail_count = len(valid_vals)
    partial_score = sum(valid_vals)
    coverage = avail_count / 9.0

    if avail_count == 9:
        f_score = partial_score
        normalized = (f_score - 4.5) / 4.5
        missing_reason = None
    else:
        f_score = None
        normalized = None
        missing = [k for k, v in criteria.items() if v is None]
        missing_reason = f"missing_criteria:{','.join(missing)}"

    return PiotroskiResult(
        f_score=f_score,
        partial_score=partial_score,
        criteria_available=avail_count,
        coverage=coverage,
        criteria=criteria,
        normalized_score=normalized,
        missing_reason=missing_reason,
    )


def calculate_sloan_accrual_ratio(
    net_income: Optional[float],
    operating_cash_flow: Optional[float],
    total_assets: Optional[float],
    prior_total_assets: Optional[float] = None,
) -> SloanResult:
    """
    Calculate Sloan Accrual Ratio = (Net Income - Operating Cash Flow) / Average Total Assets.
    Normalized score = clip(-Sloan / 0.10, -1, 1).
    Lower accruals (negative Sloan) -> higher quality -> positive score.
    """
    if net_income is None or operating_cash_flow is None:
        return SloanResult(None, None, "financial_item_missing")

    if total_assets is None or total_assets <= 0:
        return SloanResult(None, None, "invalid_total_assets")

    if prior_total_assets is not None and prior_total_assets > 0:
        avg_assets = (total_assets + prior_total_assets) / 2.0
    else:
        avg_assets = total_assets

    if avg_assets <= 0:
        return SloanResult(None, None, "invalid_average_assets")

    sloan = (net_income - operating_cash_flow) / avg_assets
    if not math.isfinite(sloan):
        return SloanResult(None, None, "non_finite_sloan")

    # High accruals are bad -> negative of sloan
    normalized = float(np.clip(-sloan / 0.10, -1.0, 1.0))
    return SloanResult(sloan_ratio=sloan, normalized_score=normalized)


def calculate_altman_z_score(
    working_capital: Optional[float],
    retained_earnings: Optional[float],
    ebit: Optional[float],
    market_equity: Optional[float],
    book_equity: Optional[float],
    total_liabilities: Optional[float],
    total_assets: Optional[float],
    revenue: Optional[float],
    sector: Optional[str] = "manufacturing",
) -> AltmanResult:
    """
    Calculate Altman Z-score with sector mapping and variant resolution:
    - classic public manufacturing: 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4_pub + 1.0*X5
      Zones: Distress < 1.81, Safe > 2.99
    - z_prime (manufacturing without market equity): 0.717*X1 + 0.847*X2 + 3.107*X3 + 0.420*X4_book + 0.998*X5
      Zones: Distress < 1.23, Safe > 2.90
    - z_double_prime (non-manufacturing): 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4_book
      Zones: Distress < 1.10, Safe > 2.60
    - Bank/securities/insurance: Not applicable (returns None).
    """
    if not sector:
        return AltmanResult(None, "unknown", None, None, "no_matching_sector_interval")

    sector_norm = sector.strip().lower()
    if sector_norm in FINANCIAL_SECTORS:
        return AltmanResult(
            z_score=None,
            variant="not_applicable",
            zone=None,
            normalized_score=None,
            missing_reason="altman_not_applicable_financial_sector",
        )

    if total_assets is None or total_assets <= 0:
        return AltmanResult(None, "unknown", None, None, "invalid_total_assets")

    if total_liabilities is None or total_liabilities <= 0:
        return AltmanResult(None, "unknown", None, None, "invalid_total_liabilities")

    # Common ratios
    x1 = (working_capital / total_assets) if working_capital is not None else None
    x2 = (retained_earnings / total_assets) if retained_earnings is not None else None
    x3 = (ebit / total_assets) if ebit is not None else None
    x4_pub = (market_equity / total_liabilities) if (market_equity is not None and market_equity > 0) else None
    x4_book = (book_equity / total_liabilities) if book_equity is not None else None
    x5 = (revenue / total_assets) if revenue is not None else None

    is_mfg = sector_norm in MANUFACTURING_SECTORS or "mfg" in sector_norm or "san_xuat" in sector_norm

    if is_mfg:
        if x1 is not None and x2 is not None and x3 is not None and x5 is not None and x4_pub is not None:
            # Classic public manufacturing
            z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4_pub + 1.0 * x5
            variant = "classic"
            distress_cutoff, safe_cutoff = 1.81, 2.99
        elif x1 is not None and x2 is not None and x3 is not None and x5 is not None and x4_book is not None:
            # Z-prime
            z = 0.717 * x1 + 0.847 * x2 + 3.107 * x3 + 0.420 * x4_book + 0.998 * x5
            variant = "z_prime"
            distress_cutoff, safe_cutoff = 1.23, 2.90
        else:
            return AltmanResult(None, "classic", None, None, "missing_altman_inputs")
    else:
        # Non-manufacturing (Z-double-prime)
        if x1 is not None and x2 is not None and x3 is not None and x4_book is not None:
            z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4_book
            variant = "z_double_prime"
            distress_cutoff, safe_cutoff = 1.10, 2.60
        else:
            return AltmanResult(None, "z_double_prime", None, None, "missing_altman_inputs")

    if not math.isfinite(z):
        return AltmanResult(None, variant, None, None, "non_finite_altman_z")

    # Zone
    if z < distress_cutoff:
        zone = "distress"
    elif z > safe_cutoff:
        zone = "safe"
    else:
        zone = "gray"

    # Normalized score: -1 at distress_cutoff, +1 at safe_cutoff
    midpoint = (distress_cutoff + safe_cutoff) / 2.0
    half_range = (safe_cutoff - distress_cutoff) / 2.0
    norm_score = float(np.clip((z - midpoint) / half_range, -1.0, 1.0))

    return AltmanResult(
        z_score=z,
        variant=variant,
        zone=zone,
        normalized_score=norm_score,
    )


def calculate_interbank_spread_mad_z(
    weekly_interbank_rates: Sequence[Union[float, Dict[str, Any]]],
    window: int = 52,
    min_obs: int = 26,
    as_of_dt: Optional[datetime] = None,
    decision_cutoff_dt: Optional[datetime] = None,
    knowledge_cutoff_dt: Optional[datetime] = None,
) -> InterbankResult:
    """
    Calculate Robust MAD Z-score for overnight interbank spread:
    z = 0.6745 * (current - median) / MAD
    normalized_score = -clip(z, -3, 3) / 3.0 (higher interbank stress is negative for stocks).
    Includes 14-day staleness check and PIT dual-clock filtering with fail-closed missing clock handling.
    Strictly and unconditionally requires EVERY observation to be a dict containing a valid literal
    'observed_at' timestamp (no raw scalars, no fallback to 'date' or 'available_at'), even without cutoffs.
    """
    clean_series: List[Tuple[datetime, float]] = []
    cutoffs_present = decision_cutoff_dt is not None or knowledge_cutoff_dt is not None

    for item in weekly_interbank_rates:
        if not isinstance(item, dict):
            continue  # strictly reject raw scalar / non-dict observations fail-closed

        avail_raw = item.get("available_at")
        ingest_raw = item.get("ingested_at")

        if cutoffs_present:
            if avail_raw is None or ingest_raw is None:
                continue  # fail-closed on missing clock when cutoffs are present
            try:
                avail_dt = _parse_iso_to_utc(avail_raw)
                ingest_dt = _parse_iso_to_utc(ingest_raw)
                if decision_cutoff_dt is not None and avail_dt > decision_cutoff_dt:
                    continue
                if knowledge_cutoff_dt is not None and ingest_dt > knowledge_cutoff_dt:
                    continue
            except Exception:
                continue

        val = item.get("value", item.get("rate"))
        if val is None or not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(val):
            continue

        # Strictly require literal 'observed_at' field unconditionally across all paths
        if "observed_at" not in item or item["observed_at"] is None:
            continue
        try:
            obs_dt = _parse_iso_to_utc(item["observed_at"])
        except Exception:
            continue  # reject malformed/unparseable observed_at fail-closed

        # Filter observed_at <= decision_cutoff if decision_cutoff is present
        if decision_cutoff_dt is not None and obs_dt > decision_cutoff_dt:
            continue

        clean_series.append((obs_dt, float(val)))

    # Sort by observed_at ascending and unconditionally deduplicate by timestamp on all paths
    if clean_series:
        clean_series.sort(key=lambda x: x[0])
        dedup_records: List[Tuple[datetime, float]] = []
        seen_dts = set()
        for dt_key, v in reversed(clean_series):
            if dt_key in seen_dts:
                continue
            seen_dts.add(dt_key)
            dedup_records.append((dt_key, v))
        clean_series = list(reversed(dedup_records))

    n = len(clean_series)
    if n < min_obs:
        return InterbankResult(None, None, n, f"macro_history_short (got {n}, required {min_obs})")

    sample_tuples = clean_series[-window:] if n > window else clean_series
    sample = [val for _, val in sample_tuples]
    latest_dt, current = sample_tuples[-1]

    # Check 14-day staleness if timestamps available
    ref_dt = as_of_dt or decision_cutoff_dt
    if latest_dt is not None and ref_dt is not None:
        staleness_days = (ref_dt - latest_dt).total_seconds() / 86400.0
        if staleness_days > 14.0:
            return InterbankResult(None, None, len(sample), f"macro_stale (last observation {latest_dt.isoformat()} > 14 days)")

    med = float(np.median(sample))
    abs_dev = np.abs(np.array(sample) - med)
    mad = float(np.median(abs_dev))

    if mad <= 1e-8:
        return InterbankResult(None, None, len(sample), "macro_dispersion_zero")

    z = 0.6745 * (current - med) / mad
    z_clipped = float(np.clip(z, -3.0, 3.0))
    # Stress is negative for market
    normalized = -z_clipped / 3.0

    return InterbankResult(
        z_score=z_clipped,
        normalized_score=normalized,
        observations_used=len(sample),
    )


def calculate_fx_stress_index(
    usd_vnd_rates: Sequence[Union[float, Dict[str, Any]]],
    window: int = 20,
    min_baseline_obs: int = 126,
    max_baseline_obs: int = 252,
    as_of_dt: Optional[datetime] = None,
    decision_cutoff_dt: Optional[datetime] = None,
    knowledge_cutoff_dt: Optional[datetime] = None,
) -> FXStressResult:
    """
    Calculate FX Stress Index:
    1. 20-session return: log(USDVND_t / USDVND_t-20)
    2. 20-session realized vol: std(daily_log_returns[-20:]) * sqrt(252)
    Normalized against historical baseline observations strictly prior to current observation.
    Includes exact 5-business-day staleness check (numpy.busday_count).
    fx_score = -clip(weighted_stress, -3, 3) / 3.0 (VND depreciation is stress).
    Strictly and unconditionally requires EVERY observation to be a dict containing a valid literal
    'observed_at' timestamp (no raw scalars, no fallback to 'date' or 'available_at'), even without cutoffs.
    """
    clean_series: List[Tuple[datetime, float]] = []
    cutoffs_present = decision_cutoff_dt is not None or knowledge_cutoff_dt is not None

    for item in usd_vnd_rates:
        if not isinstance(item, dict):
            continue  # strictly reject raw scalar / non-dict observations fail-closed

        avail_raw = item.get("available_at")
        ingest_raw = item.get("ingested_at")

        if cutoffs_present:
            if avail_raw is None or ingest_raw is None:
                continue  # fail-closed on missing clock when cutoffs are present
            try:
                avail_dt = _parse_iso_to_utc(avail_raw)
                ingest_dt = _parse_iso_to_utc(ingest_raw)
                if decision_cutoff_dt is not None and avail_dt > decision_cutoff_dt:
                    continue
                if knowledge_cutoff_dt is not None and ingest_dt > knowledge_cutoff_dt:
                    continue
            except Exception:
                continue

        val = item.get("value", item.get("rate", item.get("close")))
        if val is None or not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(val) or val <= 0:
            continue

        # Strictly require literal 'observed_at' field unconditionally across all paths
        if "observed_at" not in item or item["observed_at"] is None:
            continue
        try:
            obs_dt = _parse_iso_to_utc(item["observed_at"])
        except Exception:
            continue  # reject malformed/unparseable observed_at fail-closed

        # Filter observed_at <= decision_cutoff if decision_cutoff is present
        if decision_cutoff_dt is not None and obs_dt > decision_cutoff_dt:
            continue

        clean_series.append((obs_dt, float(val)))

    # Sort by observed_at ascending and unconditionally deduplicate by timestamp on all paths
    if clean_series:
        clean_series.sort(key=lambda x: x[0])
        dedup_records: List[Tuple[datetime, float]] = []
        seen_dts = set()
        for dt_key, v in reversed(clean_series):
            if dt_key in seen_dts:
                continue
            seen_dts.add(dt_key)
            dedup_records.append((dt_key, v))
        clean_series = list(reversed(dedup_records))

    n = len(clean_series)
    req_total = min_baseline_obs + window + 1
    if n < req_total:
        return FXStressResult(
            stress_index=None,
            normalized_score=None,
            components={},
            missing_reason=f"fx_history_short (got {n}, required {req_total})",
        )

    # Staleness check: exact 5 business days
    latest_dt = clean_series[-1][0]
    ref_dt = as_of_dt or decision_cutoff_dt
    if latest_dt is not None and ref_dt is not None:
        bus_days = _calculate_business_days_between(latest_dt, ref_dt)
        if bus_days > 5:
            return FXStressResult(
                stress_index=None,
                normalized_score=None,
                components={},
                missing_reason=f"fx_stale (last observation {latest_dt.isoformat()} > 5 business days ({bus_days} days))",
            )

    # Compute daily log returns
    clean_rates = [val for _, val in clean_series]
    rates_arr = np.array(clean_rates, dtype=float)
    log_returns = np.diff(np.log(rates_arr))

    # Rolling 20-day returns and 20-day realized volatility
    # Valid realized vol requires 20 daily returns: from index window to len(rates_arr)-1
    rolling_ret_20 = []
    rolling_vol_20 = []
    for i in range(window, len(rates_arr)):
        ret_20 = np.log(rates_arr[i] / rates_arr[i - window])
        vol_slice = log_returns[i - window : i]
        vol_20 = np.std(vol_slice, ddof=1) * np.sqrt(252)
        rolling_ret_20.append(ret_20)
        rolling_vol_20.append(vol_20)

    if len(rolling_ret_20) < min_baseline_obs + 1:
        return FXStressResult(None, None, {}, f"fx_history_short_rolling (got {len(rolling_ret_20)})")

    # Historical baseline excluding the current observation
    curr_ret = rolling_ret_20[-1]
    curr_vol = rolling_vol_20[-1]

    hist_ret = rolling_ret_20[-(max_baseline_obs + 1) : -1]
    hist_vol = rolling_vol_20[-(max_baseline_obs + 1) : -1]

    # Z-scores
    mean_ret, std_ret = np.mean(hist_ret), np.std(hist_ret, ddof=1)
    mean_vol, std_vol = np.mean(hist_vol), np.std(hist_vol, ddof=1)

    z_ret = float((curr_ret - mean_ret) / std_ret) if std_ret > 1e-8 else 0.0
    z_vol = float((curr_vol - mean_vol) / std_vol) if std_vol > 1e-8 else 0.0

    z_ret = float(np.clip(z_ret, -3.0, 3.0))
    z_vol = float(np.clip(z_vol, -3.0, 3.0))

    # Weighted stress: 0.625 return + 0.375 vol
    weighted_stress = 0.625 * z_ret + 0.375 * z_vol
    weighted_stress_clipped = float(np.clip(weighted_stress, -3.0, 3.0))
    fx_score = -weighted_stress_clipped / 3.0

    components = {
        "fx_return_20_z": z_ret,
        "fx_realized_vol_20_z": z_vol,
        "usd_vnd_current": float(rates_arr[-1]),
    }

    return FXStressResult(
        stress_index=weighted_stress_clipped,
        normalized_score=fx_score,
        components=components,
    )


# ---------------------------------------------------------------------------
# Composite & Hard Veto Resolution
# ---------------------------------------------------------------------------

INTENDED_WEIGHTS = {
    "piotroski": 0.35,
    "sloan": 0.20,
    "altman": 0.25,
    "interbank": 0.10,
    "fx": 0.10,
}


def evaluate_quant_composite(
    symbol: str,
    decision_cutoff: str,
    knowledge_cutoff: str,
    piotroski: PiotroskiResult,
    sloan: SloanResult,
    altman: AltmanResult,
    interbank: InterbankResult,
    fx: FXStressResult,
    cfo_curr: Optional[float] = None,
    ni_curr: Optional[float] = None,
) -> QuantEvaluationRecord:
    """
    Evaluates corporate and macro quant components into composite score and determines hard veto.
    Requirements:
    - weight_coverage >= 0.55
    - At least 2 corporate metrics valid out of (Piotroski, Sloan, Altman)
    - Hard veto conditions:
      1. Altman in distress zone AND full Piotroski <= 2
      2. Sloan >= 0.20 AND CFO < 0 AND Net Income > 0 AND full Piotroski <= 3
    """
    weights = INTENDED_WEIGHTS.copy()
    valid_components = {}
    missing_reasons = []

    # Piotroski
    if piotroski.normalized_score is not None:
        valid_components["piotroski"] = (piotroski.normalized_score, weights["piotroski"])
    elif piotroski.missing_reason:
        missing_reasons.append(f"piotroski:{piotroski.missing_reason}")

    # Sloan
    if sloan.normalized_score is not None:
        valid_components["sloan"] = (sloan.normalized_score, weights["sloan"])
    elif sloan.missing_reason:
        missing_reasons.append(f"sloan:{sloan.missing_reason}")

    # Altman
    if altman.normalized_score is not None:
        valid_components["altman"] = (altman.normalized_score, weights["altman"])
    elif altman.missing_reason:
        missing_reasons.append(f"altman:{altman.missing_reason}")

    # Interbank
    if interbank.normalized_score is not None:
        valid_components["interbank"] = (interbank.normalized_score, weights["interbank"])
    elif interbank.missing_reason:
        missing_reasons.append(f"interbank:{interbank.missing_reason}")

    # FX
    if fx.normalized_score is not None:
        valid_components["fx"] = (fx.normalized_score, weights["fx"])
    elif fx.missing_reason:
        missing_reasons.append(f"fx:{fx.missing_reason}")

    weight_coverage = sum(w for _, w in valid_components.values())

    # Count corporate valid metrics
    corp_valid_count = sum(1 for k in ("piotroski", "sloan", "altman") if k in valid_components)

    # Check Hard Veto
    hard_veto = False
    hard_veto_reasons = []

    # Condition 1: Altman distress + Piotroski <= 2
    if altman.zone == "distress" and piotroski.f_score is not None and piotroski.f_score <= 2:
        hard_veto = True
        hard_veto_reasons.append("altman_distress_and_low_piotroski")

    # Condition 2: High accrual distress + negative CFO + positive NI + low Piotroski
    if (
        sloan.sloan_ratio is not None
        and sloan.sloan_ratio >= 0.20
        and cfo_curr is not None
        and cfo_curr < 0
        and ni_curr is not None
        and ni_curr > 0
        and piotroski.f_score is not None
        and piotroski.f_score <= 3
    ):
        hard_veto = True
        hard_veto_reasons.append("severe_accrual_negative_cfo_low_piotroski")

    # Compute Quant Score
    if weight_coverage >= 0.55 and corp_valid_count >= 2:
        total_valid_weight = sum(w for _, w in valid_components.values())
        weighted_sum = sum(score * w for score, w in valid_components.values())
        quant_score = float(np.clip(weighted_sum / total_valid_weight, -1.0, 1.0))
        quant_confidence = float(np.clip(weight_coverage * (corp_valid_count / 3.0), 0.0, 1.0))
        quant_status = "veto" if hard_veto else "valid"
    else:
        quant_score = None
        quant_confidence = 0.0
        quant_status = "unscorable"
        missing_reasons.append("insufficient_quant_coverage")

    return QuantEvaluationRecord(
        symbol=symbol,
        decision_cutoff=decision_cutoff,
        knowledge_cutoff=knowledge_cutoff,
        piotroski=piotroski,
        sloan=sloan,
        altman=altman,
        interbank=interbank,
        fx=fx,
        quant_score=quant_score,
        quant_confidence=quant_confidence,
        weight_coverage=weight_coverage,
        hard_veto=hard_veto,
        hard_veto_reasons=hard_veto_reasons,
        missing_reasons=missing_reasons,
        quant_status=quant_status,
    )


# ---------------------------------------------------------------------------
# Worker Task & Batch Parallelism
# ---------------------------------------------------------------------------

def _evaluate_symbol_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Pure worker function evaluated in batch / ProcessPool."""
    symbol = payload["symbol"]
    decision_cutoff = payload["decision_cutoff"]
    knowledge_cutoff = payload["knowledge_cutoff"]
    d_dt, k_dt = validate_pit_clocks(decision_cutoff, knowledge_cutoff)

    # Fail-closed filtering on financial dictionaries
    curr_fin = _filter_financial_dict(payload.get("curr_fin"), d_dt, k_dt)
    prev_fin = _filter_financial_dict(payload.get("prev_fin"), d_dt, k_dt)
    raw_actions = payload.get("corporate_actions", [])
    interbank_rates = payload.get("interbank_rates", [])
    usd_vnd_rates = payload.get("usd_vnd_rates", [])

    # Filter corporate actions strictly with dual-clock enforcement (filter_pit_records)
    # If corporate actions are supplied but fail PIT filtering or is malformed, pass an invalid marker so F7 fails lineage
    if "corporate_actions" in payload:
        raw_actions = payload.get("corporate_actions")
        if not isinstance(raw_actions, list):
            corporate_actions = [{"invalid_lineage_non_list": True}]
        elif raw_actions:
            filtered_actions = filter_pit_records(raw_actions, d_dt, k_dt)
            if len(filtered_actions) < len(raw_actions):
                # Supplied actions failed dual-clock filtering -> fail lineage closed (F7 becomes None)
                corporate_actions = [{"invalid_lineage_unclocked": True}]
            else:
                corporate_actions = filtered_actions
        else:
            corporate_actions = []
    else:
        corporate_actions = []

    # Resolve sector PIT-safely if sector intervals are passed, or clocked dict/string
    sector_input = payload.get("sector")
    if isinstance(sector_input, list):
        # List of sector interval records: [{sector: ..., effective_from: ..., effective_to: ..., available_at: ..., ingested_at: ...}]
        valid_sec_records = filter_pit_records(sector_input, d_dt, k_dt)
        resolved_sector: Optional[str] = None
        for sr in valid_sec_records:
            eff_from = _parse_iso_to_utc(sr["effective_from"]) if sr.get("effective_from") else None
            eff_to = _parse_iso_to_utc(sr["effective_to"]) if sr.get("effective_to") else None
            if (eff_from is None or eff_from <= d_dt) and (eff_to is None or d_dt < eff_to):
                resolved_sector = sr.get("sector", sr.get("sector_group"))
                break
        sector = resolved_sector
    elif isinstance(sector_input, dict):
        valid_sec_records = filter_pit_records([sector_input], d_dt, k_dt)
        if valid_sec_records:
            sector = valid_sec_records[0].get("sector", valid_sec_records[0].get("sector_group"))
        else:
            sector = None
    else:
        # Unclocked scalar sector when cutoffs present is rejected fail-closed
        sector = None

    # Market equity dual-clock validation
    market_equity = _extract_market_equity(payload.get("market_equity"), d_dt, k_dt)

    piotroski = calculate_piotroski_f_score(
        curr_fin,
        prev_fin,
        corporate_actions=corporate_actions,
        decision_cutoff_dt=d_dt,
    )

    sloan = calculate_sloan_accrual_ratio(
        net_income=curr_fin.get("net_income"),
        operating_cash_flow=curr_fin.get("operating_cash_flow"),
        total_assets=curr_fin.get("total_assets"),
        prior_total_assets=prev_fin.get("total_assets"),
    )

    # Altman: Nullable fields, no silent 0 defaults
    working_capital = curr_fin.get("working_capital")
    if working_capital is None:
        ca = curr_fin.get("current_assets")
        cl = curr_fin.get("current_liabilities")
        if ca is not None and cl is not None:
            working_capital = ca - cl

    book_equity = curr_fin.get("book_equity")
    if book_equity is None:
        ta = curr_fin.get("total_assets")
        tl = curr_fin.get("total_liabilities")
        if ta is not None and tl is not None:
            book_equity = ta - tl

    altman = calculate_altman_z_score(
        working_capital=working_capital,
        retained_earnings=curr_fin.get("retained_earnings"),
        ebit=curr_fin.get("ebit"),
        market_equity=market_equity,
        book_equity=book_equity,
        total_liabilities=curr_fin.get("total_liabilities"),
        total_assets=curr_fin.get("total_assets"),
        revenue=curr_fin.get("revenue"),
        sector=sector,
    )

    # Pre-evaluated macro or compute with dual clock filtering & staleness
    pre_interbank = payload.get("precomputed_interbank")
    if pre_interbank is not None:
        interbank = pre_interbank if isinstance(pre_interbank, InterbankResult) else InterbankResult(**pre_interbank)
    else:
        interbank = calculate_interbank_spread_mad_z(
            interbank_rates,
            decision_cutoff_dt=d_dt,
            knowledge_cutoff_dt=k_dt,
        )

    pre_fx = payload.get("precomputed_fx")
    if pre_fx is not None:
        fx = pre_fx if isinstance(pre_fx, FXStressResult) else FXStressResult(**pre_fx)
    else:
        fx = calculate_fx_stress_index(
            usd_vnd_rates,
            decision_cutoff_dt=d_dt,
            knowledge_cutoff_dt=k_dt,
        )

    record = evaluate_quant_composite(
        symbol=symbol,
        decision_cutoff=decision_cutoff,
        knowledge_cutoff=knowledge_cutoff,
        piotroski=piotroski,
        sloan=sloan,
        altman=altman,
        interbank=interbank,
        fx=fx,
        cfo_curr=curr_fin.get("operating_cash_flow"),
        ni_curr=curr_fin.get("net_income"),
    )

    return record.to_dict()


def _process_batch_worker(batch_payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Evaluates a batch of symbol payloads."""
    return [_evaluate_symbol_payload(item) for item in batch_payloads]


class QuantFormulaEngine:
    """
    Tier 1 Quant Formula Engine orchestrator.
    Supports single worker and multi-process batch parallelism with deterministic output.
    Precomputes macro features once in coordinator and injects into worker payloads.
    """

    def __init__(self, num_workers: int = 0, batch_size: Union[int, float] = 50):
        try:
            int_batch = int(batch_size)
        except Exception:
            int_batch = 50
        if int_batch <= 0:
            self.batch_size = 50
        else:
            self.batch_size = int_batch
        if num_workers <= 0:
            cpu_count = mp.cpu_count() or 2
            self.num_workers = max(1, cpu_count - 1)
        else:
            self.num_workers = num_workers

    def evaluate_symbol(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Direct single-symbol evaluation."""
        return _evaluate_symbol_payload(payload)

    def evaluate_batch(
        self,
        payloads: Sequence[Dict[str, Any]],
        workers: Optional[int] = None,
        batch_size: Optional[Union[int, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Evaluate a sequence of symbol payloads.
        Precomputes macro once per unique (decision_cutoff, knowledge_cutoff).
        Stable sorted by symbol to ensure deterministic outputs.
        """
        if not payloads:
            return []

        effective_batch_size = self.batch_size
        if batch_size is not None:
            try:
                int_bs = int(batch_size)
            except Exception:
                int_bs = 50
            effective_batch_size = 50 if int_bs <= 0 else int_bs

        # Coordinator precomputes macro once per unique (cutoff + series hash)
        macro_cache: Dict[Tuple[str, str, str, str], Tuple[InterbankResult, FXStressResult]] = {}
        enriched_payloads: List[Dict[str, Any]] = []

        for p in payloads:
            p_copy = dict(p)
            d_cut = str(p_copy.get("decision_cutoff"))
            k_cut = str(p_copy.get("knowledge_cutoff"))
            ib_rates = p_copy.get("interbank_rates", [])
            fx_rates = p_copy.get("usd_vnd_rates", [])
            ib_hash = _hash_macro_series(ib_rates)
            fx_hash = _hash_macro_series(fx_rates)
            cache_key = (d_cut, k_cut, ib_hash, fx_hash)

            if cache_key not in macro_cache:
                d_dt, k_dt = validate_pit_clocks(d_cut, k_cut)
                ib_res = calculate_interbank_spread_mad_z(
                    ib_rates,
                    decision_cutoff_dt=d_dt,
                    knowledge_cutoff_dt=k_dt,
                )
                fx_res = calculate_fx_stress_index(
                    fx_rates,
                    decision_cutoff_dt=d_dt,
                    knowledge_cutoff_dt=k_dt,
                )
                macro_cache[cache_key] = (ib_res, fx_res)

            ib, fx = macro_cache[cache_key]
            p_copy["precomputed_interbank"] = ib
            p_copy["precomputed_fx"] = fx
            enriched_payloads.append(p_copy)

        # Stable sort by symbol
        sorted_payloads = sorted(enriched_payloads, key=lambda x: str(x.get("symbol", "")))
        worker_count = workers if workers is not None else self.num_workers

        # Single worker execution path
        if worker_count <= 1 or len(sorted_payloads) <= 1:
            return [_evaluate_symbol_payload(p) for p in sorted_payloads]

        # Chunk into deterministic batches
        batches = [
            sorted_payloads[i : i + effective_batch_size]
            for i in range(0, len(sorted_payloads), effective_batch_size)
        ]

        results: List[Dict[str, Any]] = []
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=min(worker_count, len(batches)), mp_context=ctx) as executor:
            batch_results = executor.map(_process_batch_worker, batches)
            for b_res in batch_results:
                results.extend(b_res)

        # Re-sort to guarantee exact deterministic order
        results.sort(key=lambda x: str(x.get("symbol", "")))
        return results

    @staticmethod
    def compute_result_hash(results: Sequence[Dict[str, Any]]) -> str:
        """Compute canonical SHA-256 hash for deterministic validation."""
        sorted_results = sorted(results, key=lambda x: str(x.get("symbol", "")))
        serialized = json.dumps(sorted_results, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
