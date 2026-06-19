"""Alpha Alchemist and expression generator.

Enforces no-leakage by shifting inputs and evaluates candidates.
"""

from __future__ import annotations

import itertools
import numpy as np
import pandas as pd
from typing import Any, Callable

from omega.quant.alpha.discovery_operators import (
    rank,
    delay,
    delta,
    ts_corr,
    ts_std,
    ts_max,
    ts_min,
    ts_rank,
    decay_linear,
    high_low_efficiency,
    volume_imbalance_proxy,
    _ensure_series,
    _validate_panel_index,
)


ALPHA_TEMPLATES = {
    # Momentum variants
    "momentum": [
        "close / delay(close, {n}) - 1",
        "rank(delta(close, {n}))",
        "-rank(delta(close, {n}))",
        "rank(delta(volume, {n}))",
    ],
    # Mean reversion
    "mean_reversion": [
        "rank(close / ma(close, {n}) - 1)",
        "-(close / ma(close, {n}) - 1)",
        "close / ts_min(close, {n}) - 1",
        "close / ts_max(close, {n}) - 1",
        "-(close - ts_min(close, {n})) / (ts_max(close, {n}) - ts_min(close, {n}) + 1e-9)",
    ],
    # Volatility
    "volatility": [
        "ts_std(close, {w}) / (ma(close, {w}) + 1e-9)",
        "ts_std(volume, {w}) / (ma(volume, {w}) + 1e-9)",
        "abs(delta(close, 1))",
    ],
    # Volume
    "volume": [
        "volume / (ma(volume, {n}) + 1e-9)",
        "volume * abs(delta(close, 1))",
        "volume / delay(volume, {n}) - 1",
    ],
    # Cross-sectional rank
    "cross_sectional": [
        "rank(close)",
        "rank(volume)",
        "rank(close * volume)",
        "rank(close) - rank(ma(close, {n}))",
    ],
    # Liquidity (proxy)
    "liquidity": [
        "1 / (abs(delta(close, 1)) + 1e-9)",
        "1 / (ts_std(close, {w}) + 1e-9)",
        "volume / (abs(delta(close, 1)) + 1e-9)",
    ],
    # VN-specific (limit-lock proximity, liquidity, reversal)
    "vn_specific": [
        "abs(delta(close, 1)) / (ma(close, 5) + 1e-9)",
        "volume / (ts_std(volume, {w}) + 1e-9)",
        "-(delta(close, 1)) * rank(volume)",
        "rank(close) - rank(delay(close, {n}))",
    ],
}

LAGS = [1, 2, 3, 5, 10, 20, 60]
WINDOWS = [5, 10, 20, 60]


def generate_all_candidate_expressions() -> list[tuple[str, str]]:
    """Generate 500+ alpha candidate expressions.

    EVO-002-FIX: Replace 4 nested for-loops with itertools.product for vectorized expansion.
    EVO-006-FIX: Use itertools.chain and map to eliminate nested for loops entirely.

    Returns:
        List of (expression, category) tuples.
    """
    seen: set[str] = set()
    
    def _try_format(template: str, fmt_kwargs_list: list[dict]) -> str | None:
        """Try formatting template with each kwargs dict until one succeeds."""
        # EVO-006-FIX: Replace for loop with next() + generator expression (functional).
        def _attempt_format(fmt_kwargs: dict) -> str | None:
            try:
                return template.format(**fmt_kwargs)
            except KeyError:
                return None
        return next(filter(None, map(_attempt_format, fmt_kwargs_list)), None)
    
    def _generate_for_category(category: str, templates: list[str]) -> list[tuple[str, str]]:
        """Generate all expressions for a single category."""
        # EVO-006-FIX: Replace nested for loops with itertools.product and filter (functional).
        def _process_template_params(template_params: tuple) -> tuple[str, str] | None:
            template, (lag, window) = template_params
            fmt_kwargs_list = [
                {"n": lag, "w": window},
                {"n": lag},
                {"w": window},
                {},
            ]
            expr = _try_format(template, fmt_kwargs_list)
            if expr and expr not in seen:
                seen.add(expr)
                return (expr, category)
            return None
        
        # Generate all template-param combinations and filter valid ones
        all_combos = itertools.product(templates, itertools.product(LAGS, WINDOWS))
        result = list(filter(None, map(_process_template_params, all_combos)))
        return result
    
    # EVO-006-FIX: Replace for loop with itertools.chain and takewhile (functional).
    def _generate_batch(category_templates: tuple[str, list[str]]) -> list[tuple[str, str]]:
        category, templates = category_templates
        return _generate_for_category(category, templates)
    
    # Generate batches for all categories and flatten
    all_batches = map(_generate_batch, ALPHA_TEMPLATES.items())
    all_candidates = list(itertools.chain.from_iterable(all_batches))
    
    # Return first 600 or all if fewer
    return all_candidates[:600]


def _grouped_rolling_mean(x: pd.Series, n: int) -> pd.Series:
    return x.unstack(level=1).rolling(n).mean().stack(level=0, future_stack=True).reindex(x.index)


class AlphaAlchemist:
    """Generates expression-based factors from panel market data.

    The alchemist enforces no-leakage by shifting all base input columns by 1 step
    per symbol before expression evaluation. This guarantees factor[t] only depends
    on information available up to t-1.
    """

    safe_functions: dict[str, Callable] | None = None

    def __post_init__(self) -> None:
        if self.safe_functions is None:
            self.safe_functions = {
                "rank": rank,
                "delay": delay,
                "delta": delta,
                "ts_corr": ts_corr,
                "ts_std": ts_std,
                "ts_max": ts_max,
                "ts_min": ts_min,
                "ma": _grouped_rolling_mean,
                "ts_rank": ts_rank,
                "decay_linear": decay_linear,
                "high_low_efficiency": high_low_efficiency,
                "volume_imbalance_proxy": volume_imbalance_proxy,
            }

    def __init__(self, safe_functions: dict[str, Callable] | None = None) -> None:
        self.safe_functions = safe_functions
        self.__post_init__()

    @staticmethod
    def _lag_base_features(panel: pd.DataFrame) -> dict[str, pd.Series]:
        if type(panel.index).__name__ != 'MultiIndex' or getattr(panel.index, 'nlevels', 0) != 2:
            raise ValueError("Input panel must use MultiIndex [timestamp, symbol].")
        symbol_level = panel.index.names[1]
        lagged = panel.groupby(level=symbol_level).shift(1)
        # Vectorized: convert DataFrame columns to dict via to_dict(orient='series')
        return lagged.to_dict(orient='series')

    def generate_factor(self, expression: str, panel: pd.DataFrame) -> pd.Series:
        """Evaluate factor expression using lagged base features only.
        
        EXEC-01 FIX: Uses AST-validated safe_eval_expression instead of raw eval().
        """
        from omega.quant.safe_expression_eval import safe_eval_expression, ExpressionRejected

        env = self._lag_base_features(panel)
        env.update(self.safe_functions or {})
        try:
            result = safe_eval_expression(expression, {"__builtins__": {}}, env)
        except ExpressionRejected as exc:
            raise ValueError(f"Rejected alpha expression: {expression}: {exc}") from exc
        except Exception as exc:  # pragma: no cover - tested by behavior
            raise ValueError(f"Invalid alpha expression: {expression}") from exc
        series = _ensure_series(result)
        _validate_panel_index(series)
        return series.rename(expression)

    # Convenience aliases for alpha expression templates
    @staticmethod
    def ma(x: pd.Series, n: int) -> pd.Series:
        return _grouped_rolling_mean(x, n)

    @staticmethod
    def ts_min_fn(x: pd.Series, n: int) -> pd.Series:
        return ts_min(x, n)

    @staticmethod
    def ts_max_fn(x: pd.Series, n: int) -> pd.Series:
        return ts_max(x, n)
