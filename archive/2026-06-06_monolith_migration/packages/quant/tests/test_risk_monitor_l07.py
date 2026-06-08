import json
from datetime import datetime, timedelta, timezone

from omega.quant.risk.advanced_circuit_breaker import RiskBreachStatus
from omega.quant.risk.risk_monitor_l07 import RiskMonitorConfig, RiskMonitorL07, RiskSeverity


def test_risk_monitor_l07_config_defaults(tmp_path):
    config = RiskMonitorConfig(event_log_path=tmp_path / "risk_events.jsonl")

    assert config.evaluation_interval == timedelta(minutes=30)
    assert config.var_limit == 0.025
    assert config.cvar_limit == 0.045


def test_risk_monitor_l07_emits_breaches_and_persists_jsonl(tmp_path):
    log_path = tmp_path / "state" / "risk_events.jsonl"
    monitor = RiskMonitorL07(RiskMonitorConfig(event_log_path=log_path))
    event_time = datetime(2026, 5, 17, 9, 0, tzinfo=timezone.utc)

    statuses = [
        RiskBreachStatus(
            metric_name="VaR",
            metric_value=0.031,
            limit=0.03,
            is_breached=True,
            breach_severity=0.006,
            action="warn",
            message="VaR breach",
            timestamp=event_time,
            var_value=0.031,
        ),
        RiskBreachStatus(
            metric_name="CVaR",
            metric_value=0.057,
            limit=0.08,
            is_breached=True,
            breach_severity=0.012,
            action="reduce_exposure",
            message="CVaR breach",
            timestamp=event_time,
            cvar_value=0.057,
        ),
        RiskBreachStatus(
            metric_name="Beta",
            metric_value=1.2,
            limit=1.5,
            is_breached=False,
            breach_severity=0.0,
            action="allow",
            message="Beta OK",
            timestamp=event_time,
            beta_value=1.2,
        ),
    ]

    events = monitor.monitor_breaches(statuses, evaluation_time=event_time)

    assert len(events) == 2
    assert events[0].severity == RiskSeverity.WARNING
    assert events[0].limit == 0.025
    assert events[1].severity == RiskSeverity.CRITICAL
    assert events[1].limit == 0.045
    assert all(event.monitor_layer == "L07" for event in events)
    assert all(event.metadata["source"] == "AdvancedCircuitBreaker" for event in events)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    first_record = json.loads(lines[0])
    second_record = json.loads(lines[1])
    assert first_record["severity"] == "warning"
    assert first_record["limit"] == 0.025
    assert second_record["severity"] == "critical"
    assert second_record["limit"] == 0.045
    assert first_record["metadata"]["interval_minutes"] == 30


def test_risk_monitor_l07_should_evaluate_uses_30_minute_cadence(tmp_path):
    monitor = RiskMonitorL07(RiskMonitorConfig(event_log_path=tmp_path / "risk_events.jsonl"))
    base_time = datetime(2026, 5, 17, 9, 0, tzinfo=timezone.utc)

    assert monitor.should_evaluate(base_time) is True

    monitor.monitor_breaches([], evaluation_time=base_time)

    assert monitor.should_evaluate(base_time + timedelta(minutes=29)) is False
    assert monitor.should_evaluate(base_time + timedelta(minutes=30)) is True
