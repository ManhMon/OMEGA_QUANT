"""Automated Alpha Discovery Factory — PIT-safe, opt-in, deterministic.

GATE: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615
Version: 1.0.0
Date: 2026-06-15

Research-only, opt-in automated alpha candidate discovery factory.
Generates alpha candidates from expression templates, screens on
train-only data, applies correlation filtering, and produces evidence
metadata.  Never promotes to live or changes default behavior.

COMPLIANCE:
  - PIT Safe: all screening uses T-1 lagged data only
  - Default Off: factory disabled unless explicitly enabled
  - Deterministic: same inputs + seed produce same candidates
  - Candidate Cap: max 200 candidates (configurable)
  - Correlation Filter: rejects redundant candidates above threshold
  - Train-Only Screening: no OOS/test data used for selection
  - No Live Promotion: candidates are research artifacts only
  - Evidence Metadata: per-fold evidence persisted for audit
  - Dynamic-Universe Compatible: works with per-rebalance universes
"""
from __future__ import annotations

import logging
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GATE: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615
# Research-only opt-in automated alpha discovery factory.
# Generates deterministic candidate expressions, screens on train-only
# data with PIT-safe T-1 lag, applies correlation filtering, and
# produces evidence metadata.  Default off, no live promotion.
# ---------------------------------------------------------------------------
AUTOMATED_DISCOVERY_GATE_ID = "AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615"

# Default candidate cap
DEFAULT_CANDIDATE_CAP = 200

# Default correlation filter threshold
DEFAULT_CORR_THRESHOLD = 0.85

# Default minimum IC threshold for screening
DEFAULT_MIN_IC = 0.01

# Default minimum train samples
DEFAULT_MIN_TRAIN_SAMPLES = 30

# Expression templates: deterministic seed expressions.
# PIT-safe: every template is ticker-grouped and T-1 lagged.
# Post-shift pct_change / diff / rolling are computed WITHIN ticker group
# via groupby().transform() — never on the flat post-shift Series.
# Same-row OHLCV columns (close, volume, high, low, open) are accessed
# only through groupby().shift(1+) or helper functions that shift
# internally, ensuring T-1 or earlier data.
_EXPRESSION_TEMPLATES: List[Tuple[str, str]] = [
    # Momentum family — T-1 close, ticker-grouped pct_change
    ("mom_ret_5", "df.groupby('ticker')['close'].transform(lambda x: x.shift(1).pct_change(5))"),
    ("mom_ret_10", "df.groupby('ticker')['close'].transform(lambda x: x.shift(1).pct_change(10))"),
    ("mom_ret_20", "df.groupby('ticker')['close'].transform(lambda x: x.shift(1).pct_change(20))"),
    ("mom_ret_60", "df.groupby('ticker')['close'].transform(lambda x: x.shift(1).pct_change(60))"),
    # Mean reversion family — T-1 close vs T-1 rolling stats, all within group
    ("mr_zscore_10", "_compute_mr_zscore(df, 10)"),
    ("mr_zscore_20", "_compute_mr_zscore(df, 20)"),
    # Volume family — T-1 volume, ticker-grouped rolling
    ("vol_ratio_5_20", "df.groupby('ticker')['volume'].transform(lambda x: x.shift(1).rolling(5).mean()) / (df.groupby('ticker')['volume'].transform(lambda x: x.shift(1).rolling(20).mean()) + 1e-9)"),
    ("vol_zscore_20", "_compute_vol_zscore(df, 20)"),
    # Volatility family — T-1 OHLC, ticker-grouped shift
    ("vol_range_pct", "(df.groupby('ticker')['high'].shift(1) - df.groupby('ticker')['low'].shift(1)) / (df.groupby('ticker')['close'].shift(1) + 1e-9)"),
    ("vol_close_loc", "(df.groupby('ticker')['close'].shift(1) - df.groupby('ticker')['low'].shift(1)) / (df.groupby('ticker')['high'].shift(1) - df.groupby('ticker')['low'].shift(1) + 1e-9)"),
    # Turnover family — T-1 volume, ticker-grouped rolling
    ("turnover_5", "df.groupby('ticker')['volume'].transform(lambda x: x.shift(1).rolling(5).mean()) / (df.groupby('ticker')['volume'].transform(lambda x: x.shift(1).rolling(20).mean()) + 1e-9)"),
    ("turnover_ratio", "df.groupby('ticker')['volume'].shift(1) / (df.groupby('ticker')['volume'].transform(lambda x: x.shift(1).rolling(20).mean()) + 1e-9)"),
    # Price action family — T-1 OHLC via helper functions
    ("body_pct", "_compute_body_pct(df)"),
    ("upper_shadow", "_compute_upper_shadow(df)"),
    ("lower_shadow", "_compute_lower_shadow(df)"),
    # RSI family — T-1 close, ticker-grouped diff/rolling
    ("rsi_14", "_compute_rsi_safe(df, 14)"),
    ("rsi_7", "_compute_rsi_safe(df, 7)"),
    # Volatility ratio family
    ("vol_atr_ratio_5_20", "_compute_atr_ratio(df, 5, 20)"),
    ("vol_std_ratio_10_30", "df.groupby('ticker')['close'].transform(lambda x: x.shift(1).pct_change().rolling(10).std()) / (df.groupby('ticker')['close'].transform(lambda x: x.shift(1).pct_change().rolling(30).std()) + 1e-9)"),
    # Momentum acceleration — T-1 close, ticker-grouped pct_change
    ("mom_accel_5_10", "df.groupby('ticker')['close'].transform(lambda x: x.shift(1).pct_change(5)) - df.groupby('ticker')['close'].transform(lambda x: x.shift(1).pct_change(10))"),
]


def _compute_rsi_safe(df: pd.DataFrame, period: int) -> pd.Series:
    """Compute RSI using T-1 lagged close, fully ticker-grouped (PIT-safe).

    All shift/diff/rolling operations execute inside groupby().transform()
    so that no cross-ticker row leakage can occur.
    """
    def _rsi_within_group(close_series: pd.Series) -> pd.Series:
        shifted = close_series.shift(1)
        delta = shifted.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(period, min_periods=period).mean()
        avg_loss = loss.rolling(period, min_periods=period).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        return 100.0 - (100.0 / (1.0 + rs))

    return df.groupby('ticker')['close'].transform(_rsi_within_group)


def _compute_mr_zscore(df: pd.DataFrame, period: int) -> pd.Series:
    """Mean-reversion z-score: (close[T-1] - rolling_mean[T-1]) / rolling_std[T-1].

    All operations within ticker group (PIT-safe).
    """
    def _zscore_within_group(close_series: pd.Series) -> pd.Series:
        shifted = close_series.shift(1)
        roll_mean = shifted.rolling(period, min_periods=period).mean()
        roll_std = shifted.rolling(period, min_periods=period).std()
        return (shifted - roll_mean) / (roll_std + 1e-9)

    return df.groupby('ticker')['close'].transform(_zscore_within_group)


def _compute_vol_zscore(df: pd.DataFrame, period: int) -> pd.Series:
    """Volume z-score: (volume[T-1] - rolling_mean[T-1]) / rolling_std[T-1].

    All operations within ticker group (PIT-safe).
    """
    def _zscore_within_group(vol_series: pd.Series) -> pd.Series:
        shifted = vol_series.shift(1)
        roll_mean = shifted.rolling(period, min_periods=period).mean()
        roll_std = shifted.rolling(period, min_periods=period).std()
        return (shifted - roll_mean) / (roll_std + 1e-9)

    return df.groupby('ticker')['volume'].transform(_zscore_within_group)


def _compute_body_pct(df: pd.DataFrame) -> pd.Series:
    """Candle body percentage using T-1 close and T-1 open (PIT-safe).

    Element-wise ops on aligned shifted Series — no cross-ticker leakage.
    """
    c = df.groupby('ticker')['close'].shift(1)
    o = df.groupby('ticker')['open'].shift(1)
    return (c - o) / (o + 1e-9)


def _compute_upper_shadow(df: pd.DataFrame) -> pd.Series:
    """Upper shadow ratio using T-1 OHLC (PIT-safe)."""
    h = df.groupby('ticker')['high'].shift(1)
    o = df.groupby('ticker')['open'].shift(1)
    c = df.groupby('ticker')['close'].shift(1)
    lo = df.groupby('ticker')['low'].shift(1)
    return (h - pd.concat([o, c], axis=1).max(axis=1)) / (h - lo + 1e-9)


def _compute_lower_shadow(df: pd.DataFrame) -> pd.Series:
    """Lower shadow ratio using T-1 OHLC (PIT-safe)."""
    h = df.groupby('ticker')['high'].shift(1)
    o = df.groupby('ticker')['open'].shift(1)
    c = df.groupby('ticker')['close'].shift(1)
    lo = df.groupby('ticker')['low'].shift(1)
    return (pd.concat([o, c], axis=1).min(axis=1) - lo) / (h - lo + 1e-9)


def _compute_atr_ratio(df: pd.DataFrame, short: int, long: int) -> pd.Series:
    """Compute ATR ratio using T-1 lagged OHLC (PIT-safe)."""
    high = df.groupby('ticker')['high'].shift(1)
    low = df.groupby('ticker')['low'].shift(1)
    prev_close = df.groupby('ticker')['close'].shift(2)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    tr_grouped = tr.groupby(df['ticker'])
    atr_short = tr_grouped.transform(
        lambda x: x.rolling(short, min_periods=short).mean()
    )
    atr_long = tr_grouped.transform(
        lambda x: x.rolling(long, min_periods=long).mean()
    )
    return atr_short / (atr_long + 1e-9)


@dataclass
class AlphaCandidate:
    """A single discovered alpha candidate."""
    name: str
    expression_id: str
    train_ic: float = 0.0
    train_icir: float = 0.0
    corr_cluster_id: int = -1
    selected: bool = False
    metadata: Dict = field(default_factory=dict)


@dataclass
class DiscoveryResult:
    """Result of automated alpha discovery run."""
    gate_id: str = AUTOMATED_DISCOVERY_GATE_ID
    enabled: bool = False
    candidates_generated: int = 0
    candidates_after_screening: int = 0
    candidates_after_corr_filter: int = 0
    selected_candidates: List[AlphaCandidate] = field(default_factory=list)
    candidate_cap: int = DEFAULT_CANDIDATE_CAP
    corr_threshold: float = DEFAULT_CORR_THRESHOLD
    min_ic: float = DEFAULT_MIN_IC
    seed: int = 42
    evidence: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Serialize to dict for JSON persistence."""
        return {
            "gate_id": self.gate_id,
            "enabled": self.enabled,
            "candidates_generated": self.candidates_generated,
            "candidates_after_screening": self.candidates_after_screening,
            "candidates_after_corr_filter": self.candidates_after_corr_filter,
            "candidate_cap": self.candidate_cap,
            "corr_threshold": self.corr_threshold,
            "min_ic": self.min_ic,
            "seed": self.seed,
            "n_selected": len(self.selected_candidates),
            "selected_names": [c.name for c in self.selected_candidates],
            "selected_ics": {c.name: round(c.train_ic, 6) for c in self.selected_candidates},
            "evidence": self.evidence,
        }


class AutomatedAlphaDiscoveryFactory:
    """PIT-safe automated alpha discovery factory.

    Parameters
    ----------
    enabled : bool
        If True, factory generates and screens candidates. Default False.
    candidate_cap : int
        Maximum number of candidates to generate. Default 200.
    corr_threshold : float
        Correlation threshold for filtering redundant candidates. Default 0.85.
    min_ic : float
        Minimum absolute IC for a candidate to pass screening. Default 0.01.
    seed : int
        Random seed for deterministic behavior. Default 42.
    min_train_samples : int
        Minimum number of training samples required. Default 30.
    return_col : str
        Forward return column name. Default 'fwd_ret_5'.
    extra_templates : list of tuple, optional
        Additional (name, expression_fn_string) templates.
    """

    def __init__(
        self,
        enabled: bool = False,
        candidate_cap: int = DEFAULT_CANDIDATE_CAP,
        corr_threshold: float = DEFAULT_CORR_THRESHOLD,
        min_ic: float = DEFAULT_MIN_IC,
        seed: int = 42,
        min_train_samples: int = DEFAULT_MIN_TRAIN_SAMPLES,
        return_col: str = "fwd_ret_5",
        extra_templates: Optional[List[Tuple[str, str]]] = None,
    ):
        if not isinstance(enabled, bool):
            raise ValueError(f"enabled must be a boolean, got {enabled}")
        if not isinstance(candidate_cap, int) or candidate_cap < 1:
            raise ValueError(
                f"candidate_cap must be a positive integer, got {candidate_cap}"
            )
        if not 0.0 <= corr_threshold <= 1.0:
            raise ValueError(
                f"corr_threshold must be in [0, 1], got {corr_threshold}"
            )
        if not isinstance(seed, int):
            raise ValueError(f"seed must be an integer, got {seed}")

        self.enabled = enabled
        self.candidate_cap = candidate_cap
        self.corr_threshold = corr_threshold
        self.min_ic = min_ic
        self.seed = seed
        self.min_train_samples = min_train_samples
        self.return_col = return_col

        # Build template list (base + extra), capped
        self._templates = list(_EXPRESSION_TEMPLATES)
        if extra_templates:
            self._templates.extend(extra_templates)

    def generate_candidates(self, df: pd.DataFrame) -> List[AlphaCandidate]:
        """Generate alpha candidates from expression templates.

        PIT-safe: all expressions use T-1 lagged data.
        Deterministic: same df + seed produces same candidates.

        Parameters
        ----------
        df : pd.DataFrame
            Training data with OHLCV columns and forward returns.
            Must contain 'ticker', 'date', 'open', 'high', 'low',
            'close', 'volume', and the return_col column.

        Returns
        -------
        list of AlphaCandidate
            Generated candidates (may be empty if disabled or no data).
        """
        if not self.enabled:
            return []

        if df is None or df.empty:
            return []

        if self.return_col not in df.columns:
            logger.warning(
                f"Return column '{self.return_col}' not found in data"
            )
            return []

        rng = np.random.RandomState(self.seed)
        candidates: List[AlphaCandidate] = []

        for name, expr_str in self._templates[:self.candidate_cap]:
            try:
                signal = self._evaluate_expression(df, expr_str)
            except Exception as exc:
                logger.debug(f"Expression '{name}' failed: {exc}")
                continue

            if signal is None or signal.isna().all():
                continue

            # Sanitize: replace inf/nan with 0
            signal = signal.replace([np.inf, -np.inf], np.nan).fillna(0.0)

            expr_id = hashlib.md5(
                f"{name}:{expr_str}".encode()
            ).hexdigest()[:12]

            candidates.append(AlphaCandidate(
                name=f"auto_{name}",
                expression_id=expr_id,
                metadata={"expression": expr_str, "template": name},
            ))

        return candidates

    def screen_candidates(
        self,
        candidates: List[AlphaCandidate],
        df: pd.DataFrame,
    ) -> List[AlphaCandidate]:
        """Screen candidates using train-only IC.

        PIT-safe: uses only training data, no OOS/test leakage.
        Computes per-date cross-sectional IC, then mean and ICIR.

        Parameters
        ----------
        candidates : list of AlphaCandidate
            Candidates to screen.
        df : pd.DataFrame
            Training data only (no test/OOS data).

        Returns
        -------
        list of AlphaCandidate
            Candidates that pass IC threshold.
        """
        if not candidates or df is None or df.empty:
            return []

        if self.return_col not in df.columns:
            return []

        passed: List[AlphaCandidate] = []
        for candidate in candidates:
            try:
                signal = self._evaluate_expression(
                    df, candidate.metadata.get("expression", "")
                )
            except Exception:
                continue

            if signal is None:
                continue

            signal = signal.replace([np.inf, -np.inf], np.nan)

            # Compute daily cross-sectional IC
            temp_df = df.copy()
            temp_df["_auto_signal"] = signal.values if hasattr(signal, 'values') else signal

            daily_ics = self._compute_daily_cs_ic(
                temp_df, "_auto_signal", self.return_col
            )

            if len(daily_ics) < self.min_train_samples:
                continue

            mean_ic = float(np.mean(daily_ics))
            std_ic = float(np.std(daily_ics)) if len(daily_ics) > 1 else 1.0
            icir = mean_ic / (std_ic + 1e-9)

            if abs(mean_ic) >= self.min_ic:
                candidate.train_ic = mean_ic
                candidate.train_icir = icir
                candidate.selected = True
                passed.append(candidate)

        return passed

    def correlation_filter(
        self,
        candidates: List[AlphaCandidate],
        df: pd.DataFrame,
    ) -> List[AlphaCandidate]:
        """Filter out redundant candidates by pairwise correlation.

        Keeps the candidate with highest absolute IC from each
        correlated cluster. Uses only training data.

        Parameters
        ----------
        candidates : list of AlphaCandidate
            Screened candidates.
        df : pd.DataFrame
            Training data only.

        Returns
        -------
        list of AlphaCandidate
            Non-redundant candidates.
        """
        if len(candidates) <= 1:
            return candidates

        # Build signal matrix
        signals = {}
        for c in candidates:
            try:
                sig = self._evaluate_expression(
                    df, c.metadata.get("expression", "")
                )
                if sig is not None:
                    sig = sig.replace([np.inf, -np.inf], np.nan).fillna(0.0)
                    signals[c.name] = sig.values if hasattr(sig, 'values') else sig
            except Exception:
                continue

        if len(signals) <= 1:
            return candidates

        signal_df = pd.DataFrame(signals)

        # Pairwise correlation
        corr_matrix = signal_df.corr().abs()

        # Greedy selection: pick highest IC, remove correlated
        sorted_cands = sorted(
            candidates, key=lambda c: abs(c.train_ic), reverse=True
        )
        selected_names = set()
        removed_names = set()

        for c in sorted_cands:
            if c.name in removed_names or c.name not in corr_matrix.columns:
                continue
            selected_names.add(c.name)
            c.selected = True

            # Remove correlated candidates
            if c.name in corr_matrix.columns:
                corr_row = corr_matrix[c.name]
                for other_name in corr_row.index:
                    if other_name != c.name and corr_row[other_name] > self.corr_threshold:
                        removed_names.add(other_name)

        # Mark removed candidates
        result = []
        for c in candidates:
            if c.name in selected_names:
                result.append(c)
            else:
                c.selected = False

        return result

    def run_discovery(
        self,
        train_df: pd.DataFrame,
    ) -> DiscoveryResult:
        """Run full discovery pipeline on training data.

        PIT-safe: only uses train_df, never test/OOS data.
        Deterministic: same inputs produce same outputs.

        Parameters
        ----------
        train_df : pd.DataFrame
            Training data with OHLCV + forward returns.

        Returns
        -------
        DiscoveryResult
            Discovery results with evidence metadata.
        """
        result = DiscoveryResult(
            gate_id=AUTOMATED_DISCOVERY_GATE_ID,
            enabled=self.enabled,
            candidate_cap=self.candidate_cap,
            corr_threshold=self.corr_threshold,
            min_ic=self.min_ic,
            seed=self.seed,
        )

        if not self.enabled:
            result.evidence = {
                "status": "disabled",
                "reason": "Automated alpha discovery is opt-in and disabled by default",
            }
            return result

        # Step 1: Generate candidates
        candidates = self.generate_candidates(train_df)
        result.candidates_generated = len(candidates)

        if not candidates:
            result.evidence = {
                "status": "no_candidates",
                "reason": "No candidates generated from templates",
            }
            return result

        # Step 2: Screen by train IC
        screened = self.screen_candidates(candidates, train_df)
        result.candidates_after_screening = len(screened)

        if not screened:
            result.evidence = {
                "status": "no_screened",
                "reason": f"No candidates passed IC threshold {self.min_ic}",
            }
            return result

        # Step 3: Correlation filter
        filtered = self.correlation_filter(screened, train_df)
        result.candidates_after_corr_filter = len(filtered)
        result.selected_candidates = [c for c in filtered if c.selected]

        # Cap final selection
        if len(result.selected_candidates) > self.candidate_cap:
            result.selected_candidates = sorted(
                result.selected_candidates,
                key=lambda c: abs(c.train_ic),
                reverse=True,
            )[:self.candidate_cap]

        # Build evidence metadata
        result.evidence = {
            "status": "completed",
            "candidates_generated": result.candidates_generated,
            "candidates_screened": result.candidates_after_screening,
            "candidates_filtered": result.candidates_after_corr_filter,
            "n_selected": len(result.selected_candidates),
            "selected_names": [c.name for c in result.selected_candidates],
            "selected_ics": {
                c.name: round(c.train_ic, 6)
                for c in result.selected_candidates
            },
            "selected_icirs": {
                c.name: round(c.train_icir, 4)
                for c in result.selected_candidates
            },
            "config": {
                "candidate_cap": self.candidate_cap,
                "corr_threshold": self.corr_threshold,
                "min_ic": self.min_ic,
                "seed": self.seed,
                "return_col": self.return_col,
            },
            "pit_safe": True,
            "train_only": True,
            "no_live_promotion": True,
        }

        logger.info(
            f"[AutoDiscovery] Generated {result.candidates_generated}, "
            f"screened {result.candidates_after_screening}, "
            f"filtered {result.candidates_after_corr_filter}, "
            f"selected {len(result.selected_candidates)}"
        )

        return result

    def compute_candidate_signals(
        self,
        df: pd.DataFrame,
        candidates: List[AlphaCandidate],
    ) -> pd.DataFrame:
        """Compute signal columns for selected candidates.

        PIT-safe: uses T-1 lagged expressions.

        Parameters
        ----------
        df : pd.DataFrame
            Data with OHLCV columns.
        candidates : list of AlphaCandidate
            Candidates to compute signals for.

        Returns
        -------
        pd.DataFrame
            Original df with candidate signal columns added.
        """
        result = df.copy()
        for c in candidates:
            expr = c.metadata.get("expression", "")
            if not expr:
                continue
            try:
                signal = self._evaluate_expression(df, expr)
                if signal is not None:
                    signal = signal.replace([np.inf, -np.inf], np.nan).fillna(0.0)
                    result[c.name] = signal.values if hasattr(signal, 'values') else signal
            except Exception as exc:
                logger.debug(f"Failed to compute signal {c.name}: {exc}")
        return result

    def _evaluate_expression(
        self, df: pd.DataFrame, expr_str: str
    ) -> Optional[pd.Series]:
        """Safely evaluate an expression template.

        Only allows a restricted set of operations for safety.
        Helper functions are dispatched by regex or via eval namespace.
        """
        if not expr_str:
            return None

        # Handle parameterised helper functions via regex dispatch
        import re

        if expr_str.startswith("_compute_rsi_safe"):
            match = re.search(r'_compute_rsi_safe\(df,\s*(\d+)\)', expr_str)
            if match:
                return _compute_rsi_safe(df, int(match.group(1)))
            return None

        if expr_str.startswith("_compute_atr_ratio"):
            match = re.search(
                r'_compute_atr_ratio\(df,\s*(\d+),\s*(\d+)\)', expr_str
            )
            if match:
                return _compute_atr_ratio(df, int(match.group(1)), int(match.group(2)))
            return None

        if expr_str.startswith("_compute_mr_zscore"):
            match = re.search(r'_compute_mr_zscore\(df,\s*(\d+)\)', expr_str)
            if match:
                return _compute_mr_zscore(df, int(match.group(1)))
            return None

        if expr_str.startswith("_compute_vol_zscore"):
            match = re.search(r'_compute_vol_zscore\(df,\s*(\d+)\)', expr_str)
            if match:
                return _compute_vol_zscore(df, int(match.group(1)))
            return None

        # For simple expressions, use eval with restricted namespace.
        # Helper functions for price-action templates are injected.
        try:
            local_ns = {
                "df": df,
                "np": np,
                "pd": pd,
                "_compute_body_pct": _compute_body_pct,
                "_compute_upper_shadow": _compute_upper_shadow,
                "_compute_lower_shadow": _compute_lower_shadow,
            }
            result = eval(expr_str, {"__builtins__": {}}, local_ns)
            if isinstance(result, pd.Series):
                return result
            return None
        except Exception:
            return None

    @staticmethod
    def _compute_daily_cs_ic(
        df: pd.DataFrame,
        signal_col: str,
        return_col: str,
        min_cross_section: int = 5,
    ) -> np.ndarray:
        """Compute daily cross-sectional IC array.

        Parameters
        ----------
        df : pd.DataFrame
            Data with date, signal_col, return_col.
        signal_col : str
            Signal column name.
        return_col : str
            Return column name.
        min_cross_section : int
            Minimum pairs per date.

        Returns
        -------
        np.ndarray
            Array of daily IC values.
        """
        if signal_col not in df.columns or return_col not in df.columns:
            return np.array([])

        def _cs_ic(group: pd.DataFrame) -> float:
            mask = ~(group[signal_col].isna() | group[return_col].isna())
            if mask.sum() < min_cross_section:
                return np.nan
            try:
                ic, _ = spearmanr(
                    group.loc[mask, signal_col].values,
                    group.loc[mask, return_col].values,
                )
                return ic if not np.isnan(ic) else np.nan
            except Exception:
                return np.nan

        daily_ics = df.groupby('date').apply(_cs_ic, include_groups=False)
        valid = daily_ics.dropna()
        return valid.values if not valid.empty else np.array([])
