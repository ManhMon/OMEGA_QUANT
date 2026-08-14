import numpy as np
import pandas as pd
from itertools import combinations

from omega.quant.portfolio.barra_factor_model import build_barra_exposure_matrix
from omega.quant.portfolio.execution_sim import build_hrp_barra_portfolio
from omega.quant.portfolio.hrp_optimizer import _fallback_rank_weights, estimate_shrunk_covariance


def _make_market_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp, list[str]]:
    rng = np.random.default_rng(7)
    symbols = [f"S{i:02d}" for i in range(12)]
    dates = pd.bdate_range("2024-01-02", periods=320)
    sector_map = {symbol: f"Sector{idx % 4}" for idx, symbol in enumerate(symbols)}
    base = rng.normal(0.0002, 0.008, size=(len(dates), len(symbols)))
    returns = pd.DataFrame(base, index=dates, columns=symbols)

    rows: list[dict[str, object]] = []
    close = pd.Series(np.linspace(18.0, 30.0, len(symbols)), index=symbols)
    shares = pd.Series(np.linspace(40e6, 90e6, len(symbols)), index=symbols)
    for date in dates:
        gross = 1.0 + returns.loc[date]
        close = (close * gross).clip(lower=5.0)
        volume = pd.Series(rng.integers(150_000, 500_000, size=len(symbols)), index=symbols)
        market_cap = close * shares
        for idx, symbol in enumerate(symbols):
            rows.append(
                {
                    "date": date,
                    "symbol": symbol,
                    "close": float(close[symbol]),
                    "volume": float(volume[symbol]),
                    "market_cap": float(market_cap[symbol]),
                    "sector": sector_map[symbol],
                    "book_value": float(12.0 + rng.normal(0.0, 0.8)),
                    "period_end": pd.Timestamp("2024-09-30"),
                    "available_at": pd.Timestamp("2024-12-29"),
                }
            )
    market_data = pd.DataFrame(rows)
    as_of_date = dates[300]
    return market_data, returns, as_of_date, symbols


def _make_alpha(market_data: pd.DataFrame, as_of_date: pd.Timestamp, symbols: list[str]) -> pd.Series:
    exposures = build_barra_exposure_matrix(market_data, as_of_date).reindex(symbols).fillna(0.0)
    half = len(symbols) // 2
    best_combo: tuple[int, ...] | None = None
    best_score = float("inf")
    for longs in combinations(range(len(symbols)), half):
        weights = -np.ones(len(symbols), dtype=float) / len(symbols)
        weights[list(longs)] = 1.0 / len(symbols)
        score = float(np.max(np.abs(exposures.to_numpy().T @ weights)))
        if score < best_score:
            best_score = score
            best_combo = longs
    alpha = pd.Series(-1.0, index=symbols, dtype=float)
    assert best_combo is not None
    alpha.iloc[list(best_combo)] = 1.0
    return alpha


def test_covariance_is_symmetric_and_psd() -> None:
    _, returns, _, _ = _make_market_data()
    cov = estimate_shrunk_covariance(returns.iloc[:252])
    assert np.allclose(cov, cov.T, atol=1e-8)
    assert np.linalg.eigvalsh(cov.to_numpy()).min() >= -1e-8


def test_hrp_barra_projection_enforces_constraints() -> None:
    market_data, returns, as_of_date, symbols = _make_market_data()
    alpha = _make_alpha(market_data, as_of_date, symbols)
    weights, diagnostics = build_hrp_barra_portfolio(
        alpha_scores=alpha,
        returns_window=returns.loc[: as_of_date - pd.Timedelta(days=1)].tail(252),
        market_data=market_data,
        as_of_date=as_of_date,
    )
    exposures = diagnostics["exposures"]
    assert not weights.empty
    assert np.isclose(weights.sum(), 0.0, atol=1e-6)
    assert np.isclose(weights.abs().sum(), 1.0, atol=1e-5)
    assert weights.abs().max() <= 0.10 + 1e-8
    assert np.max(np.abs(exposures.T @ weights)) <= 0.05 + 1e-6


def test_barra_builder_is_t_minus_1_pit_safe() -> None:
    market_data, returns, as_of_date, symbols = _make_market_data()
    alpha = _make_alpha(market_data, as_of_date, symbols)
    original_weights, _ = build_hrp_barra_portfolio(
        alpha_scores=alpha,
        returns_window=returns.loc[: as_of_date - pd.Timedelta(days=1)].tail(252),
        market_data=market_data,
        as_of_date=as_of_date,
    )
    mutated = market_data.copy()
    future_mask = mutated["date"] == as_of_date
    mutated.loc[future_mask, "close"] *= 25.0
    mutated.loc[future_mask, "market_cap"] *= 25.0
    mutated.loc[future_mask, "volume"] *= 10.0
    mutated.loc[future_mask, "book_value"] *= 50.0
    future_weights, _ = build_hrp_barra_portfolio(
        alpha_scores=alpha,
        returns_window=returns.loc[: as_of_date - pd.Timedelta(days=1)].tail(252),
        market_data=mutated,
        as_of_date=as_of_date,
    )
    assert np.allclose(original_weights.sort_index(), future_weights.sort_index(), atol=1e-8)


def test_hrp_builder_ignores_future_returns_in_covariance() -> None:
    market_data, returns, as_of_date, symbols = _make_market_data()
    alpha = _make_alpha(market_data, as_of_date, symbols)
    baseline_weights, baseline_diagnostics = build_hrp_barra_portfolio(
        alpha_scores=alpha,
        returns_window=returns.tail(252),
        market_data=market_data,
        as_of_date=as_of_date,
    )
    mutated_returns = returns.copy()
    mutated_returns.loc[as_of_date] = np.linspace(-0.9, 1.5, len(symbols))
    mutated_weights, mutated_diagnostics = build_hrp_barra_portfolio(
        alpha_scores=alpha,
        returns_window=mutated_returns.tail(252),
        market_data=market_data,
        as_of_date=as_of_date,
    )
    assert np.allclose(baseline_weights.sort_index(), mutated_weights.sort_index(), atol=1e-8)
    assert np.allclose(
        baseline_diagnostics["covariance"].sort_index().sort_index(axis=1),
        mutated_diagnostics["covariance"].sort_index().sort_index(axis=1),
        atol=1e-8,
    )


def test_value_factor_respects_fundamental_availability_lag() -> None:
    market_data, _, as_of_date, symbols = _make_market_data()
    delayed = pd.concat(
        [
            market_data,
            pd.DataFrame(
                [
                    {
                        "date": as_of_date + pd.Timedelta(days=1),
                        "symbol": symbols[0],
                        "close": float(market_data.loc[market_data["symbol"] == symbols[0], "close"].iloc[-1]),
                        "volume": float(market_data.loc[market_data["symbol"] == symbols[0], "volume"].iloc[-1]),
                        "market_cap": float(market_data.loc[market_data["symbol"] == symbols[0], "market_cap"].iloc[-1]),
                        "sector": str(market_data.loc[market_data["symbol"] == symbols[0], "sector"].iloc[-1]),
                        "book_value": 1_000.0,
                        "period_end": as_of_date - pd.Timedelta(days=30),
                        "available_at": as_of_date + pd.Timedelta(days=10),
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    exposures = build_barra_exposure_matrix(delayed, as_of_date)
    baseline = build_barra_exposure_matrix(market_data, as_of_date)
    assert np.isclose(exposures.loc[symbols[0], "value"], baseline.loc[symbols[0], "value"])


def test_fallback_rank_weights_respect_ten_percent_cap_without_renorm() -> None:
    initial = pd.Series(np.linspace(-1.0, 1.0, 8), index=[f"S{i:02d}" for i in range(8)], dtype=float)
    weights = _fallback_rank_weights(initial, max_position=0.10)
    assert np.isclose(weights.abs().max(), 0.10)
    assert np.isclose(weights.abs().sum(), 0.8)
    assert np.isclose(weights[weights > 0].sum(), 0.4)
    assert np.isclose(weights[weights < 0].abs().sum(), 0.4)


def test_available_at_nulls_fall_back_to_period_end_plus_ninety_days_per_row() -> None:
    market_data, _, as_of_date, symbols = _make_market_data()
    period_end = as_of_date - pd.Timedelta(days=45)
    symbol = symbols[1]
    latest_row = market_data.loc[market_data["symbol"] == symbol].sort_values("date").iloc[-1]
    mixed = pd.concat(
        [
            market_data,
            pd.DataFrame(
                [
                    {
                        "date": as_of_date - pd.Timedelta(days=1),
                        "symbol": symbol,
                        "close": float(latest_row["close"]),
                        "volume": float(latest_row["volume"]),
                        "market_cap": float(latest_row["market_cap"]),
                        "sector": str(latest_row["sector"]),
                        "book_value": 25.0,
                        "period_end": period_end,
                        "available_at": pd.NaT,
                    },
                    {
                        "date": as_of_date - pd.Timedelta(days=1),
                        "symbol": symbol,
                        "close": float(latest_row["close"]),
                        "volume": float(latest_row["volume"]),
                        "market_cap": float(latest_row["market_cap"]),
                        "sector": str(latest_row["sector"]),
                        "book_value": 200.0,
                        "period_end": period_end,
                        "available_at": as_of_date + pd.Timedelta(days=5),
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    exposures_with_null_fill = build_barra_exposure_matrix(mixed, as_of_date)
    expected = build_barra_exposure_matrix(
        mixed.assign(
            available_at=mixed["available_at"].where(
                mixed["available_at"].notna(),
                mixed["period_end"] + pd.Timedelta(days=90),
            )
        ),
        as_of_date,
    )
    assert np.isclose(exposures_with_null_fill.loc[symbol, "value"], expected.loc[symbol, "value"])
