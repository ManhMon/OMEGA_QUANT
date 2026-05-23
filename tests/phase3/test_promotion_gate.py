import datetime
import pytest

from omega.quant.promotion import PromotionGate


def test_evaluate_model_passes_all_thresholds():
    gate = PromotionGate()
    metrics = {"IC": 0.12, "Sharpe": 1.8, "MDD": 0.08}
    criteria = {"IC": 0.1, "Sharpe": 1.5, "MDD": 0.1}
    assert gate.evaluate_model(metrics, criteria) is True


def test_evaluate_model_fails_ic_threshold():
    gate = PromotionGate()
    metrics = {"IC": 0.09, "Sharpe": 1.8, "MDD": 0.08}
    criteria = {"IC": 0.1, "Sharpe": 1.5, "MDD": 0.1}
    assert gate.evaluate_model(metrics, criteria) is False


def test_evaluate_model_fails_sharpe_threshold():
    gate = PromotionGate()
    metrics = {"IC": 0.12, "Sharpe": 1.4, "MDD": 0.08}
    criteria = {"IC": 0.1, "Sharpe": 1.5, "MDD": 0.1}
    assert gate.evaluate_model(metrics, criteria) is False


def test_evaluate_model_fails_mdd_threshold():
    gate = PromotionGate()
    metrics = {"IC": 0.12, "Sharpe": 1.8, "MDD": 0.12}
    criteria = {"IC": 0.1, "Sharpe": 1.5, "MDD": 0.1}
    assert gate.evaluate_model(metrics, criteria) is False


def test_apply_embargo_true_after_horizon_plus_one():
    gate = PromotionGate()
    model_date = datetime.datetime(2026, 1, 1)
    current_date = datetime.datetime(2026, 1, 7)
    assert gate.apply_embargo(model_date, current_date, horizon=5) is True


def test_apply_embargo_false_before_horizon_plus_one():
    gate = PromotionGate()
    model_date = datetime.datetime(2026, 1, 1)
    current_date = datetime.datetime(2026, 1, 6)
    assert gate.apply_embargo(model_date, current_date, horizon=5) is False


def test_promote_to_tier_requires_available_at_and_embargo():
    gate = PromotionGate()
    model_id = "model_1"
    available_at = datetime.datetime(2026, 1, 10)

    # before available_at should fail
    assert gate.promote_to_tier(
        model_id=model_id,
        tier="Shadow",
        current_date=datetime.datetime(2026, 1, 9),
        available_at=available_at,
        horizon=1,
    ) is False

    # at available_at + horizon + 1 should pass to Shadow
    assert gate.promote_to_tier(
        model_id=model_id,
        tier="Shadow",
        current_date=datetime.datetime(2026, 1, 12),
        available_at=available_at,
        horizon=1,
    ) is True


def test_promote_to_tier_enforces_transition_order_shadow_to_production():
    gate = PromotionGate()
    model_id = "model_2"
    available_at = datetime.datetime(2026, 1, 1)

    # direct Paper -> Production fails
    assert gate.promote_to_tier(
        model_id=model_id,
        tier="Production",
        current_date=datetime.datetime(2026, 1, 3),
        available_at=available_at,
        horizon=1,
    ) is False

    # Paper -> Shadow succeeds
    assert gate.promote_to_tier(
        model_id=model_id,
        tier="Shadow",
        current_date=datetime.datetime(2026, 1, 3),
        available_at=available_at,
        horizon=1,
    ) is True

    # Shadow -> Production succeeds
    assert gate.promote_to_tier(
        model_id=model_id,
        tier="Production",
        current_date=datetime.datetime(2026, 1, 3),
        available_at=available_at,
        horizon=1,
    ) is True
