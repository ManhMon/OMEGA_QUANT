import pandas as pd
import pytest

from omega.quant.graph.loader import FinancialStatementLoader


@pytest.fixture
def statements():
    return pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "AAA", "AAA", "BBB"],
            "item_code": ["revenue", "revenue", "assets", "assets", "revenue"],
            "item_value": [100.0, 200.0, 50.0, 75.0, 300.0],
            "fiscal_period_end": ["2025-03-31"] * 5,
            "available_at": ["2025-05-15", "2025-08-15", "2025-05-15", "2025-08-15", "2025-05-15"],
        }
    )


def test_load_raw_rejects_statement_available_before_period_end():
    statements = pd.DataFrame(
        {"symbol": ["AAA"], "item_code": ["revenue"], "item_value": [1.0], "fiscal_period_end": ["2025-03-31"], "available_at": ["2025-03-30"]}
    )
    with pytest.raises(ValueError, match="PIT violation"):
        FinancialStatementLoader(statements).load_raw()


def test_load_raw_requires_fiscal_period_end():
    statements = pd.DataFrame({"symbol": ["AAA"], "item_code": ["revenue"], "item_value": [1.0], "available_at": ["2025-05-15"]})
    with pytest.raises(ValueError, match=r"Missing financial statement columns: \['fiscal_period_end'\]"):
        FinancialStatementLoader(statements).load_raw()


def test_load_raw_rejects_null_fiscal_period_end(statements):
    statements.loc[0, "fiscal_period_end"] = None
    with pytest.raises(ValueError, match="fiscal_period_end cannot be null"):
        FinancialStatementLoader(statements).load_raw()


def test_asof_join_uses_only_available_statement_per_symbol(statements):
    loader = FinancialStatementLoader(statements)
    joined = loader.asof_join_market(pd.DataFrame({"symbol": ["AAA", "AAA", "BBB"], "date": ["2025-05-14", "2025-08-16", "2025-05-16"]}))
    values = joined.set_index(["symbol", "date", "item_code"])["item_value"]
    assert pd.isna(values[("AAA", pd.Timestamp("2025-05-14", tz="UTC"), "revenue")])
    assert values[("AAA", pd.Timestamp("2025-08-16", tz="UTC"), "revenue")] == 200.0
    assert values[("BBB", pd.Timestamp("2025-05-16", tz="UTC"), "revenue")] == 300.0


def test_asof_join_matches_available_at_market_date_boundary(statements):
    joined = FinancialStatementLoader(statements).asof_join_market(pd.DataFrame({"symbol": ["AAA"], "date": ["2025-05-15"]}))
    values = joined.set_index("item_code")["item_value"]
    assert values["revenue"] == 100.0
    assert values["assets"] == 50.0


def test_asof_join_rejects_null_market_date(statements):
    with pytest.raises(ValueError, match="market date cannot be null"):
        FinancialStatementLoader(statements).asof_join_market(pd.DataFrame({"symbol": ["AAA"], "date": [None]}))


def test_factor_matrix_pivots_asof_financial_factors(statements):
    loader = FinancialStatementLoader(statements)
    loader.asof_join_market(pd.DataFrame({"symbol": ["AAA", "AAA"], "date": ["2025-05-16", "2025-08-16"]}))
    matrix = loader.get_factor_matrix(["AAA"], "2025-05-16", "2025-08-16")
    assert matrix.loc[(pd.Timestamp("2025-05-16", tz="UTC"), "AAA"), "assets"] == 50.0
    assert matrix.loc[(pd.Timestamp("2025-08-16", tz="UTC"), "AAA"), "revenue"] == 200.0
