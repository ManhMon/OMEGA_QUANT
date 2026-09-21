#!/usr/bin/env python3
"""Unit tests for Macro Risk Alert Monitor."""
import json
import pytest
import pandas as pd
import numpy as np

from scripts.check_macro_risk_alerts import (
    compute_macro_risk_metrics,
    evaluate_macro_regime,
    run_monitor,
)


def frame(zero=False, on=4.0, omo=10.0, with_timestamps=False):
    usd = [23000.0 + float(i) for i in range(80)]
    if zero:
        usd = [23000.0] * 80
    data = {
        "usd_vnd": usd,
        "omo_net": [omo] * 20 + [0.0] * 60,
        "on_rate": [on] * 80,
        "rate_1m": [on + 0.2] * 80,
    }
    if with_timestamps:
        dates = pd.date_range("2026-01-01", periods=80, freq="D", tz="UTC")
        data["timestamp"] = dates
    return pd.DataFrame(data)


def test_normal_regime():
    code, name, _ = evaluate_macro_regime(compute_macro_risk_metrics(frame(zero=True)))
    assert code == 0
    assert name == "NORMAL"


def test_caution_regime():
    metrics = {"fx_zscore": 1.2, "on_rate": 4.0, "omo_net_20d": 10.0}
    code, name, _ = evaluate_macro_regime(metrics)
    assert code == 1
    assert name == "CAUTION"


def test_alert_regime():
    metrics = {"fx_zscore": 2.0, "on_rate": 4.0, "omo_net_20d": 10.0}
    code, name, _ = evaluate_macro_regime(metrics)
    assert code == 2
    assert name == "ALERT/RISK-OFF"


def test_dual_stress_alert():
    metrics = {"fx_zscore": 1.1, "on_rate": 4.0, "omo_net_20d": -500.0}
    code, name, _ = evaluate_macro_regime(metrics)
    assert code == 2
    assert name == "ALERT/RISK-OFF"


def test_insufficient_window_fail_closed():
    with pytest.raises(ValueError, match="insufficient_pit_window"):
        compute_macro_risk_metrics(frame().iloc[:30])


def test_missing_schema_fail_closed():
    with pytest.raises(ValueError, match="missing_schema"):
        compute_macro_risk_metrics(pd.DataFrame({"invalid": [1, 2, 3]}))


def test_invalid_numeric_fail_closed():
    df = frame()
    df["usd_vnd"] = df["usd_vnd"].astype(object)
    df.loc[0, "usd_vnd"] = "invalid_string"
    with pytest.raises(ValueError, match="invalid_numeric"):
        compute_macro_risk_metrics(df)


def test_future_row_rejection_pit():
    """F-001 regression test: reject rows exceeding explicit as_of cutoff."""
    df = frame(with_timestamps=True)
    cutoff = "2026-03-01T00:00:00Z"
    with pytest.raises(ValueError, match="future_rows_exceed_cutoff"):
        compute_macro_risk_metrics(df, as_of=cutoff)


def test_as_of_without_timestamp_fail_closed():
    """BLOCKING PIT regression test: as_of without timestamp column must fail closed."""
    df = frame(with_timestamps=False)
    cutoff = "2026-03-01T00:00:00Z"
    with pytest.raises(ValueError, match="as_of_requires_timestamp_column"):
        compute_macro_risk_metrics(df, as_of=cutoff)


def test_zero_volatility_div0_guard():
    """F-002 regression test: constant series produces zero std with no div0 warning."""
    df = frame(zero=True)
    metrics = compute_macro_risk_metrics(df)
    assert metrics["fx_zscore"] == 0.0
    assert metrics["fx_vol_20d"] == 0.0
    assert metrics["regime"] == 0
    assert np.isfinite(metrics["fx_zscore"])
    assert np.isfinite(metrics["fx_vol_20d"])


def test_non_positive_window_fail_closed():
    """F-004 regression test: non-positive z_window or vol_window must fail closed."""
    df = frame()
    with pytest.raises(ValueError, match="z_window_must_be_positive"):
        compute_macro_risk_metrics(df, z_window=0)
    with pytest.raises(ValueError, match="z_window_must_be_positive"):
        compute_macro_risk_metrics(df, z_window=-5)
    with pytest.raises(ValueError, match="vol_window_must_be_positive"):
        compute_macro_risk_metrics(df, vol_window=0)
    with pytest.raises(ValueError, match="vol_window_must_be_positive"):
        compute_macro_risk_metrics(df, vol_window=-1)


def test_run_monitor_threshold_forwarding(tmp_path):
    """F-001 regression test: custom thresholds must control regime evaluation."""
    df = frame(zero=False)
    p = tmp_path / "macro.parquet"
    df.to_parquet(p)
    # With low alert_z, should evaluate to ALERT (code 2)
    code = run_monitor(str(p), alert_z=0.01, silent=True)
    assert code == 2

    # With high caution_z and alert_z, should evaluate to NORMAL (code 0)
    code = run_monitor(str(p), caution_z=99.0, alert_z=100.0, on_caution=99.0, on_alert=100.0, silent=True)
    assert code == 0


def test_run_monitor_json_only_output(tmp_path, capsys):
    """F-002 regression test: as_json=True must emit exactly one JSON document."""
    df = frame(zero=True)
    p = tmp_path / "macro.parquet"
    df.to_parquet(p)
    code = run_monitor(str(p), as_json=True, silent=False)
    captured = capsys.readouterr().out.strip()
    assert "\n" not in captured
    payload = json.loads(captured)
    assert payload["code"] == 0
    assert payload["regime"] == "NORMAL"
    assert "metrics" in payload


def test_exit_code_separation(tmp_path):
    """F-003 regression test: operational failure returns code 3 distinct from alert code 2."""
    non_existent = tmp_path / "non_existent.parquet"
    assert run_monitor(str(non_existent), silent=True) == 3
