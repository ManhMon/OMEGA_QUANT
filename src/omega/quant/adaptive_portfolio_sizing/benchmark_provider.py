"""
Benchmark Data Provider
=======================

Provides benchmark data for APSE optimization:
- Bank interest rates
- VN-Index returns
- Inflation rates

PIT SAFETY ENFORCEMENT:
    All functions that access time-sensitive data REQUIRE an explicit date
    or pit_cutoff_date parameter. No default None is allowed — callers must
    consciously specify the point-in-time boundary to prevent future data leakage.

Author: OMEGA_QUANT Team (migrated from V21_QUANT)
Date: 2026-05-27
Version: 2.0 (PIT-strict)
"""

from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Vietnam bank interest rates (historical)
# Source: State Bank of Vietnam (SBV)
# ---------------------------------------------------------------------------
_BANK_INTEREST_RATES: dict[str, float] = {
    "2015": 0.065,
    "2016": 0.065,
    "2017": 0.065,
    "2018": 0.070,
    "2019": 0.070,
    "2020": 0.055,  # COVID-19 rate cuts
    "2021": 0.055,
    "2022": 0.060,
    "2023": 0.065,
    "2024": 0.065,
    "2025": 0.065,
    "2026": 0.065,
}

# ---------------------------------------------------------------------------
# Vietnam inflation rates (historical)
# Source: General Statistics Office of Vietnam (GSO)
# ---------------------------------------------------------------------------
_INFLATION_RATES: dict[str, float] = {
    "2015": 0.006,  # 0.6%
    "2016": 0.027,  # 2.7%
    "2017": 0.035,  # 3.5%
    "2018": 0.035,  # 3.5%
    "2019": 0.028,  # 2.8%
    "2020": 0.032,  # 3.2%
    "2021": 0.018,  # 1.8%
    "2022": 0.032,  # 3.2%
    "2023": 0.033,  # 3.3%
    "2024": 0.035,  # 3.5%
    "2025": 0.035,  # 3.5%
    "2026": 0.035,  # 3.5%
}

# Default fallback values when year not found in lookup tables
_DEFAULT_BANK_RATE: float = 0.065
_DEFAULT_INFLATION_RATE: float = 0.035
_DEFAULT_VNINDEX_RETURN: float = 0.12


def get_bank_interest_rate(date: str) -> float:
    """
    Get Vietnam bank interest rate for a given date.

    Args:
        date: Date string in YYYY-MM-DD format. MANDATORY — no default.

    Returns:
        Annual bank interest rate (e.g., 0.065 for 6.5%).

    Raises:
        ValueError: If date is empty or cannot be parsed.
    """
    if not date:
        raise ValueError(
            "PIT SAFETY: 'date' parameter is mandatory. "
            "Pass an explicit date string (YYYY-MM-DD)."
        )

    try:
        year = str(pd.to_datetime(date).year)
        return _BANK_INTEREST_RATES.get(year, _DEFAULT_BANK_RATE)
    except Exception as exc:
        raise ValueError(
            f"PIT SAFETY: Cannot parse date '{date}'. "
            f"Expected YYYY-MM-DD format. Original error: {exc}"
        ) from exc


def get_vnindex_return(
    start_date: str,
    end_date: str,
    pit_cutoff_date: str,
    data_source: Optional[pd.DataFrame] = None,
) -> float:
    """
    Calculate VN-Index return for a given period.

    Args:
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        pit_cutoff_date: PIT safety cutoff — only use data BEFORE this date.
            MANDATORY — no default. Prevents future data leakage during
            parameter optimization.
        data_source: Optional DataFrame with VN-Index data (columns: date, close).

    Returns:
        Annualized return (e.g., 0.12 for 12%).

    Raises:
        ValueError: If any date parameter is empty or cannot be parsed.
    """
    # --- PIT Safety Gate ---
    if not pit_cutoff_date:
        raise ValueError(
            "PIT SAFETY: 'pit_cutoff_date' parameter is mandatory. "
            "Pass an explicit cutoff date (YYYY-MM-DD) to prevent look-ahead bias."
        )
    if not start_date:
        raise ValueError("PIT SAFETY: 'start_date' parameter is mandatory.")
    if not end_date:
        raise ValueError("PIT SAFETY: 'end_date' parameter is mandatory.")

    # Validate dates parse correctly
    try:
        pit_cutoff = pd.to_datetime(pit_cutoff_date)
    except Exception as exc:
        raise ValueError(
            f"PIT SAFETY: Cannot parse pit_cutoff_date '{pit_cutoff_date}'. "
            f"Expected YYYY-MM-DD. Original error: {exc}"
        ) from exc

    if data_source is None:
        # Return historical average for Vietnam market
        # VN-Index average annual return 2015-2025: ~12%
        return _DEFAULT_VNINDEX_RETURN

    try:
        df = data_source.copy()
        df["date"] = pd.to_datetime(df["date"])

        # PIT SAFETY: Enforce cutoff date — never use data past this point
        df = df[df["date"] < pit_cutoff]

        # Filter for the requested date range (within PIT-safe data)
        mask = (df["date"] >= pd.to_datetime(start_date)) & (
            df["date"] <= pd.to_datetime(end_date)
        )
        df_period = df[mask].sort_values("date")

        if len(df_period) < 2:
            return _DEFAULT_VNINDEX_RETURN

        # Calculate return
        start_price = df_period.iloc[0]["close"]
        end_price = df_period.iloc[-1]["close"]

        total_return = (end_price - start_price) / start_price

        # Annualize
        days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days
        years = days / 365.25

        if years > 0:
            annualized_return = (1 + total_return) ** (1 / years) - 1
        else:
            annualized_return = total_return

        return annualized_return

    except ValueError:
        raise  # Re-raise our own validation errors
    except Exception:
        # Fallback to historical average on unexpected errors
        return _DEFAULT_VNINDEX_RETURN


def get_inflation_rate(date: str) -> float:
    """
    Get Vietnam inflation rate for a given date.

    Args:
        date: Date string in YYYY-MM-DD format. MANDATORY — no default.

    Returns:
        Annual inflation rate (e.g., 0.035 for 3.5%).

    Raises:
        ValueError: If date is empty or cannot be parsed.
    """
    if not date:
        raise ValueError(
            "PIT SAFETY: 'date' parameter is mandatory. "
            "Pass an explicit date string (YYYY-MM-DD)."
        )

    try:
        year = str(pd.to_datetime(date).year)
        return _INFLATION_RATES.get(year, _DEFAULT_INFLATION_RATE)
    except Exception as exc:
        raise ValueError(
            f"PIT SAFETY: Cannot parse date '{date}'. "
            f"Expected YYYY-MM-DD format. Original error: {exc}"
        ) from exc


def get_risk_free_rate(date: str) -> float:
    """
    Get risk-free rate (typically bank interest rate).

    Args:
        date: Date string in YYYY-MM-DD format. MANDATORY — no default.

    Returns:
        Annual risk-free rate.
    """
    return get_bank_interest_rate(date)


def get_benchmark_summary(
    start_date: str,
    end_date: str,
    pit_cutoff_date: str,
    vnindex_data: Optional[pd.DataFrame] = None,
) -> dict:
    """
    Get summary of all benchmark rates for a period.

    Args:
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        pit_cutoff_date: PIT safety cutoff — only use data BEFORE this date.
            MANDATORY — no default.
        vnindex_data: Optional DataFrame with VN-Index data.

    Returns:
        Dictionary with all benchmark rates.

    Raises:
        ValueError: If any date parameter is empty or cannot be parsed.
    """
    if not start_date:
        raise ValueError("PIT SAFETY: 'start_date' parameter is mandatory.")
    if not end_date:
        raise ValueError("PIT SAFETY: 'end_date' parameter is mandatory.")
    if not pit_cutoff_date:
        raise ValueError("PIT SAFETY: 'pit_cutoff_date' parameter is mandatory.")

    bank_rate = get_bank_interest_rate(end_date)
    vnindex_return = get_vnindex_return(
        start_date, end_date, pit_cutoff_date, vnindex_data
    )
    inflation_rate = get_inflation_rate(end_date)

    return {
        "bank_interest_rate": bank_rate,
        "vnindex_return": vnindex_return,
        "inflation_rate": inflation_rate,
        "risk_free_rate": bank_rate,
        "benchmark_threshold": max(bank_rate, vnindex_return),
        "real_return_threshold": max(bank_rate, vnindex_return) - inflation_rate,
        "period": f"{start_date} to {end_date}",
        "pit_cutoff_date": pit_cutoff_date,
    }
