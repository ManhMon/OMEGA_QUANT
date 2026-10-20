"""16-Dimension resilience and unit tests for direct macro and rates client."""

from datetime import date, datetime, time, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from omega.data.calendar import VNTradingCalendar, get_statutory_available_at
from omega.data.macro_rates import (
    DirectMacroClient,
    MacroRateSource,
    canonical_tenor,
    parse_hnx_yield_curve,
    parse_macro_rate_vintages,
    parse_rates,
    parse_sbv_interbank_rates,
    parse_sbv_omo_operations,
    parse_usd_vnd_rates,
    statutory_available_at,
)
from omega.quant.strategy.macro_context import LiquidityState, macro_liquidity_overlay


_ICT = timezone(timedelta(hours=7))


def _macro_source(count=90, *, source_id="sbv-test", max_age=1):
    dates = []
    current = date(2024, 1, 2)
    while len(dates) < count:
        if VNTradingCalendar.is_trading_day(datetime.combine(current, time(), _ICT)):
            dates.append(current)
        current += timedelta(days=1)
    schedule = tuple(
        (day, datetime.combine(day, time(9), _ICT)) for day in dates
    )
    return MacroRateSource(
        source_id, "ACT/365", -0.1, 0.2, max_age, schedule, dates[-1]
    )


def _macro_row(
    source, index, tenor="overnight", source_value=None, *,
    source_unit="annual_percent", as_of=None, available_at=None,
    vintage_at=None, revision_at=None, release_id=None,
):
    day, publication = source.schedule[index]
    as_of = as_of or publication - timedelta(minutes=30)
    available_at = available_at or publication
    vintage_at = vintage_at or publication - timedelta(minutes=5)
    row = {
        "observation_date": day.isoformat(),
        "tenor": tenor,
        "source_value": 4.0 if source_value is None else source_value,
        "source_unit": source_unit,
        "as_of": as_of,
        "available_at": available_at,
        "vintage_at": vintage_at,
        "release_id": release_id or f"release-{index}-{tenor}",
    }
    if revision_at is not None:
        row["revision_at"] = revision_at
    return row


def _macro_vintages(source, indices=None, *, stress_dates=()):
    if indices is None:
        indices = range(len(source.schedule) - 1)
    stress = {day: rank + 1 for rank, day in enumerate(stress_dates)}
    rows = []
    for index in indices:
        day = source.schedule[index][0]
        level = 0.04 + 0.00001 * ((index * index + 3 * index) % 17)
        spread = 0.01 + 0.00001 * ((index * index + 5 * index) % 19)
        if day in stress:
            level += 0.01 * stress[day]
            spread += 0.01 * stress[day]
        rows.extend((
            _macro_row(source, index, source_value=level * 100),
            _macro_row(
                source, index, "1w", source_value=(level - spread) * 100
            ),
        ))
    return parse_macro_rate_vintages(rows, source)


def _decision(source, index, hour=16):
    return datetime.combine(source.schedule[index][0], time(hour), _ICT)


def _overlay(source, vintages, index, state=None, hour=16):
    return macro_liquidity_overlay(
        vintages, source, _decision(source, index, hour), state
    )


def test_macro_vintage_units_normalize_percent_and_decimal():
    source = _macro_source()
    rows = [
        _macro_row(source, 5, source_value=4.25),
        _macro_row(
            source, 6, source_value=0.0425, source_unit="annual_decimal"
        ),
        _macro_row(source, 7, source_value=-0.025, source_unit="annual_decimal"),
    ]
    vintages = parse_macro_rate_vintages(rows, source)
    assert [row.rate for row in vintages] == pytest.approx([0.0425, 0.0425, -0.025])


@pytest.mark.parametrize("bounds", [
    (True, 0.2), (None, 0.2), ([], 0.2), (float("nan"), 0.2),
    (float("inf"), 0.2), (-1e13, 0.2),
])
def test_macro_source_rejects_invalid_numeric_bounds(bounds):
    source = _macro_source()
    with pytest.raises((TypeError, ValueError)):
        MacroRateSource(
            source.source_id, source.day_count, bounds[0], bounds[1],
            source.max_age_sessions, source.schedule, source.coverage_through,
        )


@pytest.mark.parametrize("value", [
    True, None, [], float("nan"), float("inf"), 1e13, -20.0,
])
def test_macro_vintage_parser_rejects_invalid_or_unbounded_values(value):
    source = _macro_source()
    row = _macro_row(source, 5)
    row["source_value"] = value
    with pytest.raises((TypeError, ValueError)):
        parse_macro_rate_vintages([row], source)


def test_macro_vintage_rejects_bad_temporal_order_and_unscheduled_dates():
    source = _macro_source()
    row = _macro_row(source, 5, as_of=source.schedule[5][1])
    row["available_at"] = source.schedule[5][1] - timedelta(seconds=1)
    with pytest.raises(ValueError, match="as_of"):
        parse_macro_rate_vintages([row], source)

    row = _macro_row(source, 5, vintage_at=source.schedule[5][1] - timedelta(days=1))
    with pytest.raises(ValueError, match="vintage_at"):
        parse_macro_rate_vintages([row], source)

    row = _macro_row(source, 5)
    row["observation_date"] = "2024-01-01"
    with pytest.raises(ValueError, match="schedule"):
        parse_macro_rate_vintages([row], source)


def test_macro_overlay_requires_forty_prior_nonconstant_observations():
    source = _macro_source(72)
    enough_prior = _macro_vintages(source, range(10, 71))
    thirty_nine_prior = _macro_vintages(source, range(32, 71))
    complete = _overlay(source, enough_prior, 71)
    incomplete = _overlay(source, thirty_nine_prior, 71)
    assert complete.reason == "ok"
    assert all(value is not None for value in complete.components)
    assert incomplete.reason == "incomplete_components"
    assert incomplete.status == "UNKNOWN"
    assert incomplete.state.entry_count == incomplete.state.exit_count == 0


def test_macro_overlay_enforces_cutoff_and_economic_t_minus_one():
    source = _macro_source()
    vintages = _macro_vintages(source)
    decision = _decision(source, len(source.schedule) - 1)
    baseline = macro_liquidity_overlay(vintages, source, decision)
    latest = len(source.schedule) - 2

    future_revision = _macro_row(
        source, latest, source_value=20.0,
        vintage_at=decision + timedelta(seconds=1), release_id="future-revision",
    )
    future = parse_macro_rate_vintages([future_revision], source)
    ignored = macro_liquidity_overlay((*vintages, *future), source, decision)
    assert ignored.components == baseline.components

    inclusive_revision = _macro_row(
        source, latest, source_value=7.0, vintage_at=decision,
        release_id="inclusive-revision",
    )
    inclusive = parse_macro_rate_vintages([inclusive_revision], source)
    accepted = macro_liquidity_overlay((*vintages, *inclusive), source, decision)
    assert accepted.observation_date == source.schedule[latest][0]
    assert accepted.components != baseline.components

    same_day = parse_macro_rate_vintages([
        _macro_row(source, len(source.schedule) - 1, source_value=20.0),
    ], source)
    excluded = macro_liquidity_overlay((*vintages, *same_day), source, decision)
    assert excluded.components == baseline.components


def test_macro_overlay_stale_or_missing_data_is_unknown_and_resets_counters():
    source = _macro_source(max_age=1)
    stale_vintages = _macro_vintages(source, range(len(source.schedule) - 5))
    prior_decision = len(source.schedule) - 2
    state = LiquidityState(
        source.fingerprint, "STRESS", exit_count=2,
        last_decision=_decision(source, prior_decision),
        last_batch=source.schedule[prior_decision - 1][0],
    )
    stale = _overlay(source, stale_vintages, len(source.schedule) - 1, state)
    assert stale.status == "UNKNOWN"
    assert stale.reason == "stale_source"
    assert stale.state.regime == "STRESS"
    assert stale.state.exit_count == 0

    missing = _overlay(source, (), len(source.schedule) - 1)
    assert missing.status == "UNKNOWN"
    assert missing.reason == "missing_overnight"


def test_macro_overlay_hysteresis_counts_distinct_batches_only():
    source = _macro_source()
    stress_dates = [source.schedule[-10][0], source.schedule[-9][0]]
    vintages = _macro_vintages(source, stress_dates=stress_dates)
    first = _overlay(source, vintages, len(source.schedule) - 9)
    repeated = _overlay(
        source, vintages, len(source.schedule) - 9, first.state, hour=17
    )
    second = _overlay(source, vintages, len(source.schedule) - 8, repeated.state)
    assert first.stress_index >= 2
    assert first.state.entry_count == 1
    assert repeated.state.entry_count == 1
    assert second.status == "STRESS"

    recovery = second
    for index in range(len(source.schedule) - 7, len(source.schedule) - 1):
        recovery = _overlay(source, vintages, index, recovery.state)
        if index == len(source.schedule) - 5:
            assert recovery.stress_index >= 1
            assert recovery.state.exit_count == 0
    assert recovery.status == "NORMAL"
    assert recovery.state.exit_count == 0


def test_macro_overlay_state_roundtrip_source_binding_and_exposure_limits():
    source = _macro_source()
    vintages = _macro_vintages(source)
    normal = _overlay(source, vintages, len(source.schedule) - 1)
    restored = LiquidityState.from_json(normal.state.to_json())
    assert restored == normal.state
    with pytest.raises(ValueError, match="checksum"):
        LiquidityState.from_json(normal.state.to_json().replace('"NORMAL"', '"STRESS"'))

    other_source = _macro_source(source_id="other-sbv")
    with pytest.raises(ValueError, match="source mismatch"):
        macro_liquidity_overlay(vintages, other_source, _decision(other_source, 89), normal.state)

    assert normal.target_exposure(0.8, 0.3) == pytest.approx(0.8)
    assert normal.target_exposure(0.0, 0.3) == 0.0
    unknown = _overlay(source, (), len(source.schedule) - 1)
    assert unknown.target_exposure(0.8, 0.3) == pytest.approx(0.3)
    for base, current in [(True, 0.2), (0.2, float("nan")), (1.1, 0.2)]:
        with pytest.raises(ValueError):
            unknown.target_exposure(base, current)


def test_macro_overlay_coverage_and_decision_order_fail_closed():
    source = _macro_source()
    vintages = _macro_vintages(source)
    with pytest.raises(ValueError, match="does not cover"):
        macro_liquidity_overlay(
            vintages, source, _decision(source, len(source.schedule) - 1) + timedelta(days=1)
        )
    decision = _decision(source, len(source.schedule) - 1)
    state = _overlay(source, vintages, len(source.schedule) - 1).state
    with pytest.raises(ValueError, match="must advance"):
        macro_liquidity_overlay(vintages, source, decision, state)


def test_macro_overlay_stress_exposure_is_half_target():
    source = _macro_source()
    stress_dates = [source.schedule[-10][0], source.schedule[-9][0]]
    vintages = _macro_vintages(source, stress_dates=stress_dates)
    first = _overlay(source, vintages, len(source.schedule) - 9)
    stressed = _overlay(source, vintages, len(source.schedule) - 8, first.state)
    assert stressed.status == "STRESS"
    assert stressed.multiplier == 0.5
    assert stressed.target_exposure(0.8, 0.3) == pytest.approx(0.4)
    assert stressed.target_exposure(0.0, 0.3) == 0.0


def test_macro_schedule_and_vintage_reject_boolean_and_naive_metadata():
    source = _macro_source()
    with pytest.raises((TypeError, ValueError)):
        MacroRateSource(
            source.source_id, source.day_count, -0.1, 0.2, True,
            source.schedule, source.coverage_through,
        )
    row = _macro_row(source, 5, available_at=datetime(2024, 1, 2, 9))
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_macro_rate_vintages([row], source)
    with pytest.raises(TypeError):
        parse_macro_rate_vintages([_macro_row(source, 5, source_value=True)], source)



def test_circular96_q4_and_annual_pit_deadlines():
    assert statutory_available_at("2023-Q4").date().isoformat() == "2024-01-30"
    assert statutory_available_at("2023", is_audited=True).date().isoformat() == "2024-03-31"
    assert statutory_available_at("2024-Q2", is_audited=True).date().isoformat() == "2024-08-29"
    assert get_statutory_available_at("2023-Q4").isoformat() == "2024-01-30T15:30:00+07:00"







def test_rates_reject_malformed_or_out_of_bounds_rows():
    with pytest.raises(ValueError):
        parse_rates([{"date": "2024-01-01", "rate": float("nan")}])
    with pytest.raises(ValueError):
        parse_rates([{"date": "2024-01-01"}])


def test_rates_are_utc_independent_and_deterministic():
    rows = [{"date": "2024-01-01T00:00:00+07:00", "rate": 4.5}]
    assert DirectMacroClient().parse(rows) == [{"date": "2023-12-31", "rate": 4.5}]
    assert statutory_available_at("2023-Q4").tzinfo == timezone.utc


def test_direct_sbv_parser_normalizes_aliases_and_provider():
    rows = [{"ngay": "2024-01-02T00:00:00+00:00", "ky_han": "ON", "lai_suat": "4.25"}]
    assert parse_sbv_interbank_rates(rows)[0] == {
        "date": "2024-01-02", "tenor": "overnight", "rate": 4.25,
        "available_at": "2024-01-02T09:00:00+00:00", "provider": "SBV",
    }


def test_direct_hnx_parser_normalizes_aliases_and_provider():
    rows = [{"date": "2024-01-02T00:00:00+00:00", "ky_han": "10Y", "loi_suat": 2.45}]
    assert parse_hnx_yield_curve(rows)[0]["maturity"] == "10Y"
    assert parse_hnx_yield_curve(rows)[0]["provider"] == "HNX"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 101, [], "bad"])
def test_direct_parsers_reject_malformed_rates(value):
    with pytest.raises((TypeError, ValueError)):
        parse_sbv_interbank_rates([{"date": "2024-01-01", "rate": value}])


def test_direct_parsers_fail_closed_on_pit_lookahead():
    with pytest.raises(ValueError, match="as_of exceeds available_at"):
        parse_sbv_interbank_rates([{
            "date": "2024-01-01", "rate": 4,
            "as_of": "2024-01-02T00:00:00Z",
            "available_at": "2024-01-01T09:00:00Z",
        }])


def test_direct_parsers_preserve_bitemporal_revision_fields():
    result = parse_sbv_interbank_rates([{
        "date": "2024-01-01T00:00:00Z", "rate": 4,
        "as_of": "2024-01-02T08:00:00Z",
        "available_at": "2024-01-02T09:00:00Z",
        "vintage_at": "2024-01-02T08:30:00Z",
        "revision_at": "2024-01-03T09:00:00+00:00",
    }])[0]
    assert result["vintage_at"] == "2024-01-02T08:30:00+00:00"
    assert result["revision_at"] == "2024-01-03T09:00:00+00:00"


def test_direct_parsers_reject_naive_temporal_metadata():
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_sbv_interbank_rates([{
            "date": "2024-01-01T00:00:00Z", "rate": 4,
            "available_at": "2024-01-01T09:00:00",
        }])


@pytest.mark.parametrize("period", ["", "2024-Q0", "2024-Q5", "2024-Q", "not-a-period"])
def test_circular96_rejects_invalid_periods(period):
    with pytest.raises(ValueError):
        get_statutory_available_at(period)


def test_circular96_rejects_invalid_types_and_audited_combinations():
    with pytest.raises(TypeError):
        get_statutory_available_at(2024)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        get_statutory_available_at("2024-Q1", is_audited=True)


def test_client_exposes_both_direct_parsers():
    client = DirectMacroClient()
    assert client.parse_sbv_interbank([{"date": "2024-01-01", "rate": 4}])[0]["provider"] == "SBV"
    assert client.parse_hnx_yield_curve([{"date": "2024-01-01", "maturity": "5Y", "yield": 2}])[0]["provider"] == "HNX"


def test_tenor_aliases_are_canonical():
    assert canonical_tenor("ON") == "overnight"
    assert canonical_tenor("1Y") == "12m"


def test_macro_feature_fx_omo_aliases_align_independently_with_pit(monkeypatch):
    import importlib

    fetcher_module = importlib.import_module(
        "omega.quant.evolution.alternative_data_fetcher"
    )
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    observed = {}

    def indicators(frame):
        observed["frame"] = frame.copy()
        return pd.DataFrame(
            {
                "usd_vnd_zscore": frame["usd_vnd"] / 24000.0,
                "usd_vnd_vol_20d": float("nan"),
                "omo_net_injection_20d_sum": frame["omo_net_injection"],
                "macro_fx_liquidity_regime": pd.Series(0.0, index=frame.index).where(
                    frame["usd_vnd"].notna() & frame["omo_net_injection"].notna()
                ),
            },
            index=frame.index,
        )

    monkeypatch.setattr(fetcher_module, "get_fx_omo_indicators", indicators)
    dates = pd.to_datetime(
        ["2024-01-02", "2024-01-02", "2024-01-03"], utc=True
    ).tz_convert("Asia/Ho_Chi_Minh")
    panel = pd.DataFrame(
        index=pd.MultiIndex.from_arrays(
            [dates, ["AAA", "BBB", "AAA"]], names=["date", "symbol"]
        )
    )
    original = panel.copy(deep=True)
    rows = [
        {
            "date": "2024-01-02",
            "usd_vnd_rate": 24000.0,
            "available_at": "2024-01-01T00:00:00Z",
            "vintage_at": "2024-01-01T00:00:00Z",
        },
        {
            "date": "2024-01-02",
            "usd_vnd_rate": 25000.0,
            "available_at": "2024-01-01T00:00:00Z",
            "vintage_at": "2024-01-01T00:00:00Z",
            "revision_at": "2024-01-02T10:00:00Z",
        },
        {
            "date": "2024-01-03",
            "usd_vnd_rate": 25000.0,
            "omo_net_injection": 10.0,
            "available_at": "2024-01-01T00:00:00Z",
            "vintage_at": "2024-01-01T00:00:00Z",
        },
    ]

    output = AlternativeDataFetcher().get_macro_bitemporal_features(
        panel, rows, as_of="2024-01-02T00:00:00Z"
    )
    frame = observed["frame"]
    jan2, jan3 = pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")
    assert list(frame.index) == [jan2, jan3]
    assert frame.loc[jan2, "usd_vnd"] == 24000.0
    assert frame.loc[jan3, "usd_vnd"] == 24000.0
    assert pd.isna(frame.loc[jan2, "omo_net_injection"])
    assert pd.isna(frame.loc[jan3, "omo_net_injection"])
    assert output.loc[jan2, "usd_vnd_zscore"] == 1.0
    assert pd.isna(output.loc[jan2, "macro_fx_liquidity_regime"])
    assert output.loc[jan3, "usd_vnd_zscore"] == 1.0
    assert panel.equals(original)


@pytest.mark.parametrize("date_kind", ["string", "date", "datetime", "UTC", "Asia/Ho_Chi_Minh"])
def test_generate_all_aligns_macro_to_string_date_sessions(monkeypatch, date_kind):
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    index = pd.MultiIndex.from_tuples(
        [
            ("2024-01-03", "BBB"),
            ("2024-01-02", "AAA"),
            ("2024-01-02", "BBB"),
        ],
        names=["date", "symbol"],
    )
    panel = pd.DataFrame(
        {name: 1.0 for name in ("open", "high", "low", "close", "volume")},
        index=index,
    )
    if date_kind != "string":
        dates = pd.to_datetime(panel.index.get_level_values("date"))
        if date_kind == "date":
            dates = dates.date
        elif date_kind != "datetime":
            dates = dates.tz_localize(date_kind)
        panel.index = pd.MultiIndex.from_arrays(
            [dates, panel.index.get_level_values("symbol")], names=["date", "symbol"]
        )
    original = panel.copy(deep=True)
    fetcher = AlternativeDataFetcher()
    zero = lambda frame: pd.Series(0.0, index=frame.index)
    for name in (
        "get_foreign_flow_proxy",
        "get_margin_proxy",
        "get_sector_rotation_proxy",
        "get_order_imbalance_proxy",
        "get_liquidity_shock_proxy",
    ):
        monkeypatch.setattr(fetcher, name, zero)
    monkeypatch.setattr(
        fetcher,
        "_derive_sentiment_indicators",
        lambda frame: (zero(frame), zero(frame)),
    )
    macro_dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    monkeypatch.setattr(
        fetcher,
        "get_macro_bitemporal_features",
        lambda panel, rows=None: pd.DataFrame(
            {"interbank_on_spread": [1.0, 2.0]}, index=macro_dates
        ),
    )

    result = fetcher.generate_all(panel)

    pd.testing.assert_index_equal(result.index, original.sort_index().index)
    assert result["interbank_on_spread"].tolist() == [1.0, 1.0, 2.0]
    assert len(result) == len(panel)
    pd.testing.assert_frame_equal(panel, original)


def test_macro_features_allow_default_none_rows():
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    panel = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-02"]), "symbol": ["AAA"]}
    ).set_index(["date", "symbol"])
    output = AlternativeDataFetcher().get_macro_bitemporal_features(panel)
    assert output.shape == (1, 8)
    assert output.isna().all().all()


def test_macro_features_choose_revision_deterministically():
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    panel = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-02"]), "symbol": ["AAA"]}
    ).set_index(["date", "symbol"])
    rows = [
        {"tenor": "overnight", "rate": 4.0, "available_at": "2024-01-01T09:00:00Z", "vintage_at": "2024-01-01T10:00:00Z", "provider": "B"},
        {"tenor": "overnight", "rate": 3.0, "available_at": "2024-01-01T09:00:00Z", "vintage_at": "2024-01-01T10:00:00Z", "provider": "A"},
        {"tenor": "refinancing_rate", "rate": 1.0, "available_at": "2024-01-01T09:00:00Z", "vintage_at": "2024-01-01T10:00:00Z", "provider": "A"},
    ]
    output = AlternativeDataFetcher().get_macro_bitemporal_features(panel, rows)
    assert output.loc[pd.Timestamp("2024-01-02"), "interbank_on_spread"] == 3.0


def test_macro_prior_only_robust_window_zero_mad_and_clipping():
    from omega.quant.strategy.macro_context import _robust_component
    from statistics import median

    past = [i / 1000 for i in range(80)]
    window = past[-60:]
    center = median(window)
    mad = median(abs(x - center) for x in window)
    assert _robust_component(0.06, past) == pytest.approx((0.06 - center) / (1.4826 * mad))
    assert _robust_component(100, past) == 5
    assert _robust_component(-100, past) == -5
    assert _robust_component(1, [0.04] * 60) is None
    assert _robust_component(1, [0.04 + i * 1e-15 for i in range(60)]) is None
    assert _robust_component(1, past[:39]) is None
    for bad in (float("nan"), float("inf"), float("-inf"), True, "1"):
        with pytest.raises(ValueError):
            _robust_component(bad, past)
        with pytest.raises(ValueError):
            _robust_component(1, [*past, bad])
    with pytest.raises(ValueError, match="overflow"):
        _robust_component(1e308, [-1e308, 1e308] * 30)


def test_macro_vintage_strict_schema_tenors_conflicts_and_legacy_provenance():
    source = _macro_source()
    row = _macro_row(source, 5)
    assert len(parse_macro_rate_vintages([row, row], source)) == 1
    with pytest.raises(ValueError, match="conflicting"):
        parse_macro_rate_vintages([row, dict(row, source_value=5)], source)
    for payload in (dict(row, unexpected=1), dict(row, tenor="12m"), dict(row, source_unit="VND_FULL"),
                    {"date": row["observation_date"], "rate": 4, "available_at": row["available_at"]},
                    dict(row, release_id="https://user:secret@example.test")):
        with pytest.raises((TypeError, ValueError)):
            parse_macro_rate_vintages([payload], source)
    with pytest.raises(ValueError, match="as_of ICT"):
        parse_macro_rate_vintages([dict(row, as_of=row["as_of"] - timedelta(days=1))], source)


def test_macro_matched_tenor_delta_sessions_and_unknown_not_consumed():
    source = _macro_source()
    vintages = _macro_vintages(source)
    decision = _decision(source, 89)
    latest = source.schedule[88][0]
    full = macro_liquidity_overlay(vintages, source, decision)
    missing = tuple(v for v in vintages if not (v.observation_date == latest and v.tenor == "1w"))
    unknown = macro_liquidity_overlay(missing, source, decision)
    assert unknown.status == "UNKNOWN"
    assert unknown.components[2] is None
    assert unknown.state.last_batch is None
    repaired = macro_liquidity_overlay(vintages, source, decision + timedelta(minutes=1), unknown.state)
    assert repaired.components == full.components
    assert repaired.state.last_batch == latest
    endpoint = source.schedule[83][0]
    no_endpoint = tuple(v for v in vintages if not (v.observation_date == endpoint and v.tenor == "overnight"))
    delta_missing = macro_liquidity_overlay(no_endpoint, source, decision)
    assert delta_missing.components[1] is None
    assert delta_missing.status == "UNKNOWN"
    regressed = macro_liquidity_overlay(vintages[:-2], source, decision + timedelta(minutes=1), full.state)
    assert regressed.status == "UNKNOWN"
    assert regressed.reason == "batch_regression"


def test_macro_weekend_holiday_staleness_and_inclusive_ict_close():
    from dataclasses import replace

    source = _macro_source(85, max_age=0)
    friday = next(i for i, (d, _) in enumerate(source.schedule) if i >= 60 and d.weekday() == 4)
    day = source.schedule[friday][0]
    source = replace(source, coverage_through=source.schedule[-1][0])
    vintages = _macro_vintages(source, range(friday + 1))
    saturday = datetime.combine(day + timedelta(days=1), time(15, 30), _ICT)
    weekend = macro_liquidity_overlay(vintages, source, saturday)
    assert weekend.stale_age_sessions == 0
    assert weekend.reason == "ok"
    monday = datetime.combine(source.schedule[friday + 1][0], time(15, 30), _ICT)
    assert macro_liquidity_overlay(vintages, source, monday).stale_age_sessions == 0
    release_row = _macro_row(source, friday, source_value=7, vintage_at=saturday,
                             revision_at=saturday, release_id="close-correction")
    correction = parse_macro_rate_vintages([release_row], source)
    before = macro_liquidity_overlay((*vintages, *correction), source, saturday - timedelta(microseconds=1))
    equal = macro_liquidity_overlay((*vintages, *correction), source, saturday)
    assert before.components != equal.components
    assert not any(d == date(2024, 2, 12) for d, _ in source.schedule)


def test_macro_checkpoint_strict_replay_boundaries_and_exposure_endpoints():
    import json
    import hashlib
    from omega.quant.strategy.macro_context import _advance_liquidity, LiquidityOverlay

    source = _macro_source()
    state = LiquidityState(source.fingerprint)
    for i, score in enumerate([2, 2, 1, 0.9, 0.9, 0.9], 60):
        state = _advance_liquidity(state, score, source.schedule[i - 1][0], _decision(source, i))
        restored = LiquidityState.from_json(state.to_json())
        assert restored == state
        assert state.regime == ("STRESS" if 61 <= i <= 64 else "NORMAL")
    text = state.to_json()
    for malformed in ("", "[]", "﻿" + text, text[:-1], text.replace('"sha256":', '"sha256":"bad","sha256":'), "x" * 4097):
        with pytest.raises(ValueError):
            LiquidityState.from_json(malformed)
    for key, value in (("version", 2), ("entry_count", True), ("last_batch", "bad"), ("regime", "UNKNOWN")):
        envelope = json.loads(text)
        envelope["payload"][key] = value
        canonical = json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":"))
        envelope["sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
        with pytest.raises(ValueError):
            LiquidityState.from_json(json.dumps(envelope))
    normal = _overlay(source, _macro_vintages(source), 89)
    unknown = _overlay(source, (), 89)
    for base in (0, 1):
        assert normal.target_exposure(base, 0) == base
        assert unknown.target_exposure(base, 0) == 0
        assert unknown.target_exposure(base, 1) == base
    for bad in (None, [], "0.5", float("-inf"), -1, 1e13):
        with pytest.raises(ValueError):
            normal.target_exposure(bad, 0)
    with pytest.raises(ValueError):
        LiquidityOverlay(normal.state, "UNKNOWN", 1.0, (1.0, 1.0, 1.0), normal.observation_date, 0, "invalid")


def test_macro_bounded_rows_and_source_schedule_validation():
    from dataclasses import replace
    import itertools

    source = _macro_source()
    row = _macro_row(source, 5)
    with pytest.raises(ValueError, match="100000"):
        parse_macro_rate_vintages(itertools.repeat(row, 100001), source)
    for payload in (None, "rows", {}, [None]):
        with pytest.raises((TypeError, ValueError)):
            parse_macro_rate_vintages(payload, source)
    with pytest.raises(ValueError, match="cover"):
        macro_liquidity_overlay((), source, _decision(source, 89) + timedelta(days=100))
    with pytest.raises(ValueError):
        replace(source, schedule=source.schedule[::-1])
    with pytest.raises(ValueError):
        replace(source, schedule=((source.schedule[0][0], source.schedule[0][1] - timedelta(days=1)),))


@pytest.mark.parametrize("field,value", [
    ("available_at", None), ("available_at", "NaT"),
    ("vintage_at", "2024-01-01"), ("revision_at", "bad"),
    ("date", "NaT"), ("usd_vnd", None), ("usd_vnd", []),
    ("usd_vnd", float("nan")), ("usd_vnd", float("inf")),
    ("usd_vnd", float("-inf")), ("usd_vnd", True),
    ("usd_vnd", 0), ("usd_vnd", -1), ("usd_vnd", 1e309),
])
def test_macro_feature_rejects_invalid_fx_payloads(field, value):
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    panel = pd.DataFrame(index=pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2024-01-02"), "AAA")], names=["date", "symbol"]
    ))
    row = {"date": "2024-01-01", "usd_vnd": 24000.0,
           "available_at": "2024-01-01T00:00:00Z"}
    row[field] = value
    with pytest.raises((TypeError, ValueError, OverflowError)):
        AlternativeDataFetcher().get_macro_bitemporal_features(panel, [row])


def test_macro_feature_real_indicators_lag_and_duplicate_revisions():
    from copy import deepcopy
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher
    from omega.quant.strategy.macro_context import get_fx_omo_indicators

    dates = pd.bdate_range("2024-03-04", periods=30)
    panel = pd.DataFrame(index=pd.MultiIndex.from_product(
        [dates, ["AAA", "BBB"]], names=["date", "symbol"]
    ))
    rows = [{"date": day.tz_localize("Asia/Ho_Chi_Minh"),
             "usd_vnd": 24000.0 + i * 10, "net_injection": float(i - 15),
             "available_at": day.tz_localize("Asia/Ho_Chi_Minh") + pd.Timedelta(hours=8)}
            for i, day in enumerate(dates)]
    original = deepcopy(rows)
    fetcher = AlternativeDataFetcher()
    expected = get_fx_omo_indicators(pd.DataFrame(
        {"usd_vnd": [row["usd_vnd"] for row in rows],
         "omo_net_injection": [row["net_injection"] for row in rows]}, index=dates
    ))
    output = fetcher.get_macro_bitemporal_features(panel, rows)
    expected["macro_fx_liquidity_regime"] = expected["macro_fx_liquidity_regime"].where(
        expected["usd_vnd_zscore"].notna() & expected["omo_net_injection_20d_sum"].notna()
    )
    pd.testing.assert_frame_equal(output[expected.columns], expected.astype(float), check_freq=False)
    assert output["macro_fx_liquidity_regime"].iloc[:20].isna().all()
    sparse = fetcher.get_macro_bitemporal_features(panel, [
        {key: value for key, value in row.items() if key != "net_injection"} for row in rows
    ])
    assert sparse["macro_fx_liquidity_regime"].isna().all()
    assert output["usd_vnd_zscore"].notna().any()
    future = dict(rows[-1], usd_vnd=99999.0,
                  revision_at=dates[-1].tz_localize("Asia/Ho_Chi_Minh") + pd.Timedelta(hours=10))
    shuffled = fetcher.get_macro_bitemporal_features(panel, list(reversed(rows + [rows[0], future])))
    pd.testing.assert_frame_equal(output, shuffled)
    changed = deepcopy(rows)
    changed[-1]["usd_vnd"] = 50000.0
    changed[-1]["net_injection"] = -1e13
    pd.testing.assert_frame_equal(output, fetcher.get_macro_bitemporal_features(panel, changed))
    assert rows == original


def test_macro_feature_session_cutoff_inclusive_and_empty_schema():
    import importlib
    from unittest.mock import patch
    module = importlib.import_module("omega.quant.evolution.alternative_data_fetcher")
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    panel = pd.DataFrame(index=pd.MultiIndex.from_product(
        [dates, ["AAA"]], names=["date", "symbol"]
    ))
    cutoff = pd.Timestamp("2024-01-02T09:00:00+07:00")
    rows = [{"date": "2024-01-02", "usd_vnd": 24000.0, "net_injection": 0,
             "available_at": cutoff}]
    captured = []
    def indicators(frame):
        captured.append(frame.copy())
        return pd.DataFrame({"usd_vnd_zscore": frame["usd_vnd"]}, index=frame.index)
    with patch.object(module, "get_fx_omo_indicators", indicators):
        fetcher = module.AlternativeDataFetcher()
        fetcher.get_macro_bitemporal_features(panel, rows, as_of=cutoff)
        assert captured[-1]["usd_vnd"].tolist() == [24000.0, 24000.0]
        fetcher.get_macro_bitemporal_features(panel, rows, as_of=cutoff - pd.Timedelta(nanoseconds=1))
        assert captured[-1].isna().all().all()
        empty = fetcher.get_macro_bitemporal_features(panel.iloc[:0], rows)
        assert empty.shape == (0, 8)
        with pytest.raises(ValueError, match="timezone-aware"):
            fetcher.get_macro_bitemporal_features(panel, rows, as_of="2024-01-02")


@pytest.mark.parametrize("alias", ["net_injection", "omo_net_injection", "sbv_omo_net"])
def test_omo_magnitude_boundaries_and_overflow_probe(alias):
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher
    from omega.quant.strategy.macro_context import get_fx_omo_indicators

    dates = pd.bdate_range("2026-10-01", periods=30)
    panel = pd.DataFrame(index=pd.MultiIndex.from_product(
        [dates, ["AAA"]], names=["date", "symbol"]
    ))
    fetcher = AlternativeDataFetcher()
    for amount in (-1e308, 1e308, -1e12, 1e12, -1e9 - 1, 1e9 + 1):
        row = {"date": "2026-10-01", "available_at": "2026-10-01T00:00:00Z", alias: amount}
        result = fetcher.get_macro_bitemporal_features(panel, [row])
        assert not np.isinf(result.to_numpy(dtype=float)).any()
        assert result["omo_net_injection_20d_sum"].isna().all()
        assert result["macro_fx_liquidity_regime"].isna().all()
        direct = get_fx_omo_indicators(pd.DataFrame(
            {"usd_vnd": np.arange(30) + 24000.0, alias: amount}, index=dates
        ))
        assert direct["omo_net_injection_20d_sum"].isna().all()
        assert direct["macro_fx_liquidity_regime"].isna().all()
        with pytest.raises(ValueError, match="bounds"):
            parse_sbv_omo_operations([{**row, "net_injection": amount}])

    for amount in (-1e9, -1.0, 0.0, 1.0, 1e9):
        row = {"date": "2026-10-01", "available_at": "2026-10-01T00:00:00Z", alias: str(amount)}
        parsed = parse_sbv_omo_operations([{**row, "net_injection": str(amount)}])
        assert parsed[0]["net_injection"] == amount
        result = fetcher.get_macro_bitemporal_features(panel, [row])
        sums = result["omo_net_injection_20d_sum"]
        assert sums.iloc[:5].isna().all()
        assert sums.iloc[5] == 5 * amount
        assert sums.iloc[20] == 20 * amount
        direct = get_fx_omo_indicators(pd.DataFrame(
            {"usd_vnd": 24000.0, alias: str(amount)}, index=dates
        ))
        pd.testing.assert_series_equal(sums, direct["omo_net_injection_20d_sum"])


@pytest.mark.parametrize("alias", ["net_injection", "omo_net_injection", "sbv_omo_net"])
def test_omo_invalid_revision_is_not_replaced_by_older_valid_data(alias):
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    dates = pd.bdate_range("2026-10-01", periods=10)
    panel = pd.DataFrame(index=pd.MultiIndex.from_product(
        [dates, ["AAA"]], names=["date", "symbol"]
    ))
    rows = [{"date": "2026-10-01", "available_at": "2026-10-01T00:00:00Z", alias: 10.0},
            {"date": "2026-10-01", "available_at": "2026-10-01T01:00:00Z", alias: 1e308}]
    fetcher = AlternativeDataFetcher()
    output = fetcher.get_macro_bitemporal_features(panel, rows)
    assert output["omo_net_injection_20d_sum"].isna().all()
    pd.testing.assert_frame_equal(output, fetcher.get_macro_bitemporal_features(panel, rows[::-1]))
    prior = fetcher.get_macro_bitemporal_features(panel, rows, as_of="2026-10-01T00:00:00Z")
    assert prior["omo_net_injection_20d_sum"].iloc[5] == 50.0


@pytest.mark.parametrize("amount", [-1e308, 1e308])
def test_omo_equal_provenance_outlier_cannot_be_hidden(amount):
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    dates = pd.bdate_range("2026-10-01", periods=10)
    panel = pd.DataFrame(index=pd.MultiIndex.from_product(
        [dates, ["AAA"]], names=["date", "symbol"]
    ))
    row = {"date": "2026-10-01", "available_at": "2026-10-01T00:00:00Z", "net_injection": 10.0}
    rows = [row, {**row, "net_injection": amount}]
    fetcher = AlternativeDataFetcher()
    result = fetcher.get_macro_bitemporal_features(panel, rows)
    assert result["omo_net_injection_20d_sum"].isna().all()
    pd.testing.assert_frame_equal(result, fetcher.get_macro_bitemporal_features(panel, rows[::-1]))


@pytest.mark.parametrize("value", [None, "", [], {}, float("nan"), float("inf"), float("-inf"), True, np.bool_(True)])
def test_omo_malformed_inputs_still_fail_closed(value):
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    panel = pd.DataFrame(index=pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2026-10-01"), "AAA")], names=["date", "symbol"]
    ))
    for alias in ("net_injection", "omo_net_injection", "sbv_omo_net"):
        row = {"date": "2026-10-01", "available_at": "2026-10-01T00:00:00Z", alias: value}
        with pytest.raises((TypeError, ValueError)):
            AlternativeDataFetcher().get_macro_bitemporal_features(panel, [row])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 1e308, -1e308])
def test_omo_direct_invalid_data_remains_missing(value):
    from omega.quant.strategy.macro_context import get_fx_omo_indicators

    dates = pd.bdate_range("2026-10-01", periods=30)
    frame = pd.DataFrame({"usd_vnd": np.arange(30) + 24000.0, "net_injection": value}, index=dates)
    original = frame.copy(deep=True)
    result = get_fx_omo_indicators(frame)
    assert result["omo_net_injection_20d_sum"].isna().all()
    assert result["macro_fx_liquidity_regime"].isna().all()
    assert not np.isinf(result.to_numpy(dtype=float)).any()
    pd.testing.assert_frame_equal(frame, original)


def test_macro_publication_quarantines_injected_nonfinite_features(monkeypatch):
    import omega.quant.evolution.alternative_data_fetcher as module

    dates = pd.bdate_range("2026-10-01", periods=30)
    panel = pd.DataFrame(index=pd.MultiIndex.from_product(
        [dates, ["AAA"]], names=["date", "symbol"]
    ))
    def indicators(frame):
        return pd.DataFrame({"usd_vnd_zscore": np.inf, "usd_vnd_vol_20d": -np.inf,
                             "omo_net_injection_20d_sum": 100.0,
                             "macro_fx_liquidity_regime": 0.0}, index=frame.index)

    monkeypatch.setattr(module, "get_fx_omo_indicators", indicators)
    rows = [{"date": "2026-10-01", "available_at": "2026-10-01T00:00:00Z", "net_injection": 1.0}]
    result = module.AlternativeDataFetcher().get_macro_bitemporal_features(panel, rows)
    assert result["usd_vnd_zscore"].isna().all()
    assert result["usd_vnd_vol_20d"].isna().all()
    assert result["macro_fx_liquidity_regime"].isna().all()
    assert result["omo_net_injection_20d_sum"].eq(100.0).all()


def test_macro_derived_extreme_arithmetic_and_missing_divisors():
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher
    from omega.quant.strategy.macro_context import get_fx_omo_indicators, get_macro_indicators

    dates = pd.bdate_range("2026-10-01", periods=70)
    for divisor in (0.0, -1e-308, 1e-308):
        frame = pd.DataFrame({"usd_vnd": [1e-308, 1e308] * 35,
                              "net_injection": 1e9, "gold_vn": 1e308,
                              "vn_index": divisor, "corp_bond_yield": 1e308,
                              "policy_rate": -1e308}, index=dates)
        original = frame.copy(deep=True)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            fx = get_fx_omo_indicators(frame)
            macro = get_macro_indicators(frame)
        assert not np.isinf(fx.to_numpy(dtype=float)).any()
        assert not np.isinf(macro.to_numpy(dtype=float)).any()
        assert macro["gold_vn_ratio"].isna().all()
        pd.testing.assert_frame_equal(frame, original)

    panel = pd.DataFrame(index=pd.MultiIndex.from_product(
        [dates, ["AAA"]], names=["date", "symbol"]
    ))
    rows = [{"date": day.date().isoformat(), "available_at": day.tz_localize("UTC"),
             "tenor": tenor, "rate": rate} for day in dates
            for tenor, rate in (("overnight", 1e308), ("refinancing", -1e308), ("12m", -1e308))]
    with np.errstate(over="ignore", invalid="ignore"):
        result = AlternativeDataFetcher().get_macro_bitemporal_features(panel, rows)
    assert not np.isinf(result.to_numpy(dtype=float)).any()
    assert result[["interbank_on_spread", "term_structure_slope"]].isna().all().all()
    assert result["macro_monetary_regime"].isna().all()


@pytest.mark.parametrize("overflow_kind", ["spread", "delta"])
def test_macro_regime_cannot_classify_overflow(overflow_kind):
    from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

    dates = pd.bdate_range("2026-10-01", periods=20)
    panel = pd.DataFrame(index=pd.MultiIndex.from_product(
        [dates, ["AAA"]], names=["date", "symbol"]
    ))
    rows = []
    for i, day in enumerate(dates):
        overnight = 1e308 if overflow_kind == "spread" or i == 19 else -1e308
        policy = -1e308 if overflow_kind == "spread" and i == 19 else 0.0
        for tenor, rate in (("overnight", overnight), ("refinancing", policy)):
            rows.append({"date": day.date().isoformat(), "available_at": day.tz_localize("UTC"),
                         "tenor": tenor, "rate": rate})
    with np.errstate(over="ignore", invalid="ignore"):
        result = AlternativeDataFetcher().get_macro_bitemporal_features(panel, rows)
    assert pd.isna(result["macro_monetary_regime"].iloc[-1])
    assert not np.isinf(result.to_numpy(dtype=float)).any()
