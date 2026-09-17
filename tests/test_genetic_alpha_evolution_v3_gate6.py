import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from genetic_alpha_evolution_v3 import (
    EMBARGO_TRADING_DAYS,
    VN_REGIME_DEFINITIONS,
    GATE6_PERMUTATION_P_THRESHOLD,
    _searchsorted_date_index,
    apply_trading_day_embargo,
    build_feature_fingerprint,
    build_split_windows,
    build_vn_trading_days,
    compute_regime_ic,
    compute_turnover,
    export_gp_views,
    permutation_test_ic,
    validate_and_register_models,
)


def test_regime_ic_computes_per_regime_with_rationale():
    dates = pd.to_datetime([
        "2020-03-02", "2020-03-02", "2020-03-02", "2020-03-02", "2020-03-02", "2020-03-02",
        "2022-01-04", "2022-01-04", "2022-01-04", "2022-01-04", "2022-01-04", "2022-01-04",
    ])
    signal = np.array([1, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1], dtype=float)
    target = np.array([1, 2, 3, 4, 5, 6, 1, 2, 3, 4, 5, 6], dtype=float)

    regime_ic = compute_regime_ic(signal, target, dates.to_numpy(), VN_REGIME_DEFINITIONS)

    assert regime_ic["COVID_2020"]["ic"] == 1.0
    assert regime_ic["Bear_2022"]["ic"] == -1.0
    assert regime_ic["COVID_2020"]["rationale"]
    assert regime_ic["Lockbox_2025"]["ic"] is None


def test_turnover_computes_mean_cross_sectional_position_change():
    dates = pd.to_datetime([
        "2024-01-02", "2024-01-02", "2024-01-02",
        "2024-01-03", "2024-01-03", "2024-01-03",
    ])
    tickers = np.array(["AAA", "BBB", "CCC", "AAA", "BBB", "CCC"])
    signal = np.array([0.0, 0.5, 1.0, 0.5, 0.0, 1.0], dtype=float)

    turnover = compute_turnover(signal, dates.to_numpy(), tickers)

    assert turnover == 1.0 / 3.0


def test_vn_calendar_excludes_holidays_and_applies_trading_day_embargo():
    trading_days = build_vn_trading_days(pd.Timestamp("2025-01-20"), pd.Timestamp("2025-02-10"))

    assert pd.Timestamp("2025-01-29") not in trading_days
    assert pd.Timestamp("2025-02-03") not in trading_days

    cutoff = apply_trading_day_embargo(pd.Timestamp("2025-02-10"), EMBARGO_TRADING_DAYS, trading_days)
    assert cutoff == pd.Timestamp("2025-01-24")


def test_permutation_test_uses_seeded_per_date_shuffling():
    dates = pd.to_datetime([
        "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02",
        "2024-01-03", "2024-01-03", "2024-01-03", "2024-01-03", "2024-01-03", "2024-01-03",
    ])
    signal = np.array([1, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1], dtype=float)
    target = np.array([1, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1], dtype=float)

    result_a = permutation_test_ic(signal, target, dates.to_numpy(), n_permutations=32, random_seed=7)
    result_b = permutation_test_ic(signal, target, dates.to_numpy(), n_permutations=32, random_seed=7)
    result_c = permutation_test_ic(signal, target, dates.to_numpy(), n_permutations=32, random_seed=9)

    assert result_a == result_b
    assert result_a["observed_ic"] == 1.0
    assert result_a["n_permutations"] == 32
    assert result_a["random_seed"] == 7
    assert result_c["random_seed"] == 9


def test_feature_fingerprint_changes_when_features_change():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-02"]),
            "ticker": ["AAA", "BBB"],
            "close": [10000.0, 20000.0],
            "volume": [1_000_000.0, 2_000_000.0],
            "fwd_ret_5": [0.01, 0.02],
            "returns_1d": [0.1, 0.2],
            "returns_5d": [0.3, 0.4],
            "vol_ratio": [1.0, 1.1],
            "hl_range": [0.02, 0.03],
            "oc_range": [0.01, 0.02],
            "hl_range_cs_z": [-1.0, 1.0],
            "oc_range_cs_z": [-1.0, 1.0],
        }
    )

    fingerprint_a = build_feature_fingerprint(frame)
    frame.loc[0, "returns_1d"] = 0.9
    fingerprint_b = build_feature_fingerprint(frame)

    assert fingerprint_a != fingerprint_b


class _FakeRecord:
    def __init__(self, name, version, rank, created_at=None):
        self.name = name
        self.version = version
        self.path = f"/tmp/{version}.json"
        self.status = "ready"
        self.created_at = created_at or pd.Timestamp("2024-01-01T00:00:00Z")
        self.pit_embargo = pd.Timestamp("2024-01-02T00:00:00Z")
        self.metrics = {
            "rank": rank,
            "round": 1,
            "train_FoldIR": 0.1,
            "train_IC_daily": 0.1,
            "val_IC_daily": 0.1,
            "oos_IC_daily": 0.1,
            "lockbox_IC_daily": 0.1,
            "hit_rate": 0.5,
            "id": version,
            "expression": version,
            "serialized_tree": version,
        }


class _FakeRegistry:
    def __init__(self, records):
        self._records = records

    def list_models(self, **_kwargs):
        return list(self._records)


def test_stable_sorting(tmp_path, monkeypatch):
    monkeypatch.setattr("genetic_alpha_evolution_v3.STABLE_RESULTS_DIR", tmp_path / "stable")
    monkeypatch.setattr("genetic_alpha_evolution_v3.LEGACY_RESULTS_DIR", tmp_path / "legacy")
    registry = _FakeRegistry(
        [
            _FakeRecord("m2", "20240101T000002_r01", 1),
            _FakeRecord("m1", "20240101T000001_r01", 1),
            _FakeRecord("m3", "20240101T000003_r02", 2),
        ]
    )

    rows = export_gp_views(registry)

    assert [(row["rank"], row["version"]) for row in rows] == [
        (1, "20240101T000002_r01"),
        (1, "20240101T000001_r01"),
        (2, "20240101T000003_r02"),
    ]


def test_searchsorted_split_handling():
    dates = list(pd.date_range("2019-01-01", periods=360, freq="B"))
    gap_start = pd.Timestamp("2019-12-21")

    idx = _searchsorted_date_index(dates, gap_start)
    windows = build_split_windows(dates)

    assert gap_start not in dates
    assert dates[idx] > gap_start
    assert windows["train"][1] < windows["val"][0] < windows["oos"][0] < windows["lockbox"][0]
    assert _searchsorted_date_index(dates, dates[-1] + pd.Timedelta(days=30)) == len(dates) - 1


def test_no_register_on_gate_fail(monkeypatch):
    called = {"register": 0}

    def _fail_register(_results, _embargo):
        called["register"] += 1
        return []

    monkeypatch.setattr("genetic_alpha_evolution_v3.register_top_models", _fail_register)

    with pytest.raises(ValueError, match="Gate 6 failed"):
        validate_and_register_models(
            [{"rank": 1}],
            pd.Timestamp("2024-01-01T00:00:00Z").to_pydatetime(),
            {
                "failing_regimes": ["Bear_2022"],
                "permutation_failed": False,
                "permutation": {"p_value": 0.01},
            },
        )

    assert called["register"] == 0


def test_p_value_hard_fail(monkeypatch):
    called = {"register": 0}

    def _fail_register(_results, _embargo):
        called["register"] += 1
        return []

    monkeypatch.setattr("genetic_alpha_evolution_v3.register_top_models", _fail_register)

    with pytest.raises(ValueError, match="permutation p-value"):
        validate_and_register_models(
            [{"rank": 1}],
            pd.Timestamp("2024-01-01T00:00:00Z").to_pydatetime(),
            {
                "failing_regimes": [],
                "permutation_failed": True,
                "permutation": {"p_value": GATE6_PERMUTATION_P_THRESHOLD + 0.001},
            },
        )

    assert called["register"] == 0


def test_unrounded_val_ic_sorting():
    all_hof = [
        {"id": "b", "val_IC_daily_raw": 0.12344},
        {"id": "a", "val_IC_daily_raw": 0.12346},
        {"id": "c", "val_IC_daily_raw": 0.12346},
    ]

    all_hof.sort(key=lambda x: (-float(x["val_IC_daily_raw"]), str(x["id"])))

    assert [entry["id"] for entry in all_hof] == ["a", "c", "b"]
