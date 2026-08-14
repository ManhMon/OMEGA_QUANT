from __future__ import annotations

import pandas as pd
import pytest

from omega.quant.alpha.automated_alpha_discovery import (
    AutomatedAlphaDiscoveryFactory,
    CandidateStatus,
    UnsafeExpressionError,
)
from omega.quant.alpha.discovery_universe import AlphaPromoter, FeatureUniverseManager


def _panel() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=6, freq="D")
    rows = []
    for ticker, base in (("AAA", 10.0), ("BBB", 20.0)):
        for idx, date in enumerate(dates):
            rows.append(
                {
                    "ticker": ticker,
                    "date": date,
                    "open": base + idx,
                    "high": base + idx + 1,
                    "low": base + idx - 1,
                    "close": base + idx,
                    "volume": 100 + idx,
                    "fwd_ret_5": 0.01 * idx,
                }
            )
    return pd.DataFrame(rows)


def test_evaluate_expression_allows_safe_ast_expression() -> None:
    factory = AutomatedAlphaDiscoveryFactory(enabled=True)
    result = factory._evaluate_expression(_panel(), "add(rank(close), ts_delay(volume, 1))")
    assert isinstance(result, pd.Series)
    assert len(result) == len(_panel())


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('whoami')",
        "open('x')",
        "abs(1000001)",
        "rank(rank(rank(rank(rank(rank(rank(rank(rank(rank(rank(close)))))))))))",
        "foo(close)",
        "add(close)",
    ],
)
def test_evaluate_expression_rejects_unsafe_input(expression: str) -> None:
    factory = AutomatedAlphaDiscoveryFactory(enabled=True)
    with pytest.raises(UnsafeExpressionError):
        factory._evaluate_expression(_panel(), expression)


def test_generate_candidates_marks_unsafe_expression_rejected() -> None:
    factory = AutomatedAlphaDiscoveryFactory(
        enabled=True,
        extra_templates=[("unsafe", "__import__('os').system('whoami')")],
    )
    candidates = factory.generate_candidates(_panel())
    rejected = [candidate for candidate in candidates if candidate.status == CandidateStatus.REJECTED_UNSAFE_EXPRESSION]
    assert rejected
    assert any(candidate.metadata["template"] == "unsafe" for candidate in rejected)


def test_feature_universe_rejects_invalid_symbol_name(tmp_path) -> None:
    manager = FeatureUniverseManager(state_path=str(tmp_path / "feature_universe.json"))
    with pytest.raises(ValueError, match="Invalid feature name"):
        manager.add_feature("__bad__", 0.1, 1.0, expression="rank(close)")


def test_generate_promoted_code_uses_direct_expression_not_eval(tmp_path) -> None:
    state_path = tmp_path / "feature_universe.json"
    manager = FeatureUniverseManager(state_path=str(state_path))
    manager.add_feature("alpha_ok", 0.1, 1.0, category="momentum", expression="rank(close) - rank(ma(close, 2))", status="active")

    code = AlphaPromoter(manager).generate_promoted_code()

    assert "eval(" not in code
    assert 'out["alpha_ok"] = (rank(close) - rank(ma(close, 2)))' in code
