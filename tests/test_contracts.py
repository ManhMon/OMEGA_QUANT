"""Contract schema tests."""

import pytest

from omega.contracts import (
    ArtifactContract,
    DatasetContract,
    ErrorContract,
    EventContract,
    ModelContract,
    OrderContract,
    TaskContract,
)


def test_contracts_can_be_instantiated() -> None:
    task = TaskContract(
        task_id="task-1",
        task_type="coding",
        priority=5,
        status="CREATED",
        created_at="2026-05-26T00:00:00Z",
        updated_at="2026-05-26T00:00:00Z",
        owner_agent="role9-backend",
        retry_policy={"max_retries": 3},
        timeout_policy={"timeout_seconds": 300},
    )
    event = EventContract(
        event_id="event-1",
        event_type="TASK_CREATED",
        event_version="1.0",
        timestamp="2026-05-26T00:00:00Z",
        source="contracts-test",
        target="task-1",
        correlation_id="task-1",
        causation_id="",
        trace_id="trace-1",
        severity="INFO",
    )
    order = OrderContract(
        order_id="order-1",
        strategy_id="strategy-1",
        symbol="SSI",
        side="BUY",
        quantity=100,
        order_type="LIMIT",
        limit_price=25.5,
        time_in_force="DAY",
        status="PENDING",
        created_at="2026-05-26T00:00:00Z",
        updated_at="2026-05-26T00:00:00Z",
        execution_ref="exec-1",
    )
    dataset = DatasetContract(
        dataset_id="dataset-1",
        name="market_data",
        source="vci",
        frequency="1d",
        schema_version="1.0",
        provenance={"vendor": "vci"},
        timestamp_semantics="available_at",
        quality_score=1.0,
        retention_policy={"days": 365},
        version="v1.0.0",
        checksum="sha256:abc",
    )
    model = ModelContract(
        model_id="model-1",
        version="v1.0.0",
        training_data_ref="dataset-1:v1.0.0",
        feature_set_ref="feature-set-1",
        training_config={"seed": 1},
        evaluation_metrics={"sharpe": 1.2},
        deployment_state="trained",
        rollback_ref=None,
        created_by="role9-backend",
        approved_by=None,
    )
    artifact = ArtifactContract(
        artifact_id="artifact-1",
        artifact_type="trained_model",
        checksum="sha256:def",
        version="v1.0.0",
        owner="role9-backend",
        created_at="2026-05-26T00:00:00Z",
        linked_task_id="task-1",
        reproducibility_metadata={"seed": 1},
    )
    error = ErrorContract(
        error_code="BAD_REQUEST",
        error_type="validation",
        severity="ERROR",
        retryable=False,
        message="invalid payload",
        trace_id="trace-1",
        timestamp="2026-05-26T00:00:00Z",
    )

    assert task.task_id == "task-1"
    assert event.event_type == "TASK_CREATED"
    assert order.symbol == "SSI"
    assert dataset.version == "v1.0.0"
    assert model.deployment_state == "trained"
    assert artifact.artifact_type == "trained_model"
    assert error.error_code == "BAD_REQUEST"


def test_task_contract_rejects_invalid_status() -> None:
    with pytest.raises(ValueError, match="status must be one of"):
        TaskContract(
            task_id="task-1",
            task_type="coding",
            priority=5,
            status="DONE",
            created_at="2026-05-26T00:00:00Z",
            updated_at="2026-05-26T00:00:00Z",
            owner_agent="role9-backend",
            retry_policy={"max_retries": 3},
            timeout_policy={"timeout_seconds": 300},
        )
