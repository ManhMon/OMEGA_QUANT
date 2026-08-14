from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.run_hybrid_alpha_evolution import (
    ALT_DATA_FEATURE_COLUMNS,
    BASE_FEATURE_COLUMNS,
    DEFAULT_PROMOTION_THRESHOLDS,
    LOCKBOX_END,
    LOCKBOX_START,
    REQUIRED_FEATURE_COUNT,
    SUPPORTED_LLM_PROVIDERS,
    TRADING_COST_BPS,
    add_next_session_return,
    add_target_h5,
    build_walk_forward_splits,
    compute_candidate_metrics,
    compute_daily_ic_series,
    compute_signal_pnl_series,
    enrich_with_unified_features,
    filter_model_panel,
    load_market_panel,
    neutralize_alpha_by_date,
    persist_promoted_hybrid_alphas,
    resolve_llm_provider,
    run_hybrid_real_market_integration,
    select_promoted_candidates,
    validate_candidate_node,
)
from omega.core.registry.persistence import DatabaseRegistry
from omega.quant.evolution.hybrid_alpha_miner import (
    CandidateRecord,
    CandidateSource,
    HybridAlphaMiner,
    HybridAlphaMinerConfig,
    NestedCVObjective,
)
from omega.quant.evolution.llm_symbolic_synthesizer import LLMSymbolicSynthesizer
from omega.quant.evolution.genetic_programming import GPNode


@dataclass
class _FakeSource:
    value: str


@dataclass
class _FakeCandidate:
    formula_str: str
    formula_hash: str
    source: _FakeSource
    node: GPNode


def _make_business_day_panel() -> pd.DataFrame:
    dates = pd.bdate_range("2015-01-05", "2026-07-07")
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ"]
    rows = []
    for ticker_idx, ticker in enumerate(tickers):
        for day_idx, date in enumerate(dates):
            close = 10.0 + ticker_idx + day_idx
            rows.append(
                {
                    "ticker": ticker,
                    "date": date,
                    "open": close - 0.2,
                    "high": close + 0.3,
                    "low": close - 0.4,
                    "close": close,
                    "volume": 1000 + ticker_idx * 10 + day_idx,
                    "exchange": "HOSE",
                    "as_of": date,
                    "available_at": date + pd.Timedelta(days=1),
                    "source": "VCI",
                    "price_scale": "VND",
                    "adjusted": "backward_adjusted",
                    "rebuild_date": date,
                }
            )
    return pd.DataFrame(rows)


def _make_feature_panel() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=8)
    tickers = [f"T{idx:02d}" for idx in range(10)]
    sector_map = {ticker: ("Tech" if idx < 5 else "Finance") for idx, ticker in enumerate(tickers)}
    volume_pattern = [1000, 1800, 1200, 1700, 1300, 1100, 1900, 1400, 1600, 1500]
    rows = []
    for day_idx, date in enumerate(dates):
        for ticker_idx, ticker in enumerate(tickers):
            close = 20.0 + ticker_idx + day_idx
            rows.append(
                {
                    "ticker": ticker,
                    "date": date,
                    "open": close - 0.2,
                    "high": close + 0.3,
                    "low": close - 0.4,
                    "close": close,
                    "volume": volume_pattern[ticker_idx] + day_idx * 10,
                    "as_of": date,
                    "available_at": date + pd.Timedelta(days=1),
                    "price_scale": "VND",
                    "adjusted": "backward_adjusted",
                    "sector": sector_map[ticker],
                }
            )
    return pd.DataFrame(rows)


def _make_market_file(tmp_path: Path, panel: pd.DataFrame) -> Path:
    path = tmp_path / "market.parquet"
    panel.to_parquet(path, index=False)
    return path


def test_target_h5_is_per_ticker_sorted():
    df = pd.DataFrame(
        {
            "ticker": ["AAA", "AAA", "AAA", "AAA", "AAA", "AAA", "BBB", "BBB", "BBB", "BBB", "BBB", "BBB"],
            "date": pd.to_datetime([
                "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
                "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
            ]),
            "close": [10, 11, 12, 13, 14, 15, 20, 21, 22, 23, 24, 25],
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "volume": 1.0,
            "as_of": pd.to_datetime(["2024-01-01"] * 12),
            "available_at": pd.to_datetime(["2024-01-02"] * 12),
            "price_scale": ["VND"] * 12,
            "adjusted": ["backward_adjusted"] * 12,
        }
    )
    out = add_target_h5(df)
    assert np.isclose(out.loc[0, "target_h5"], 0.5)
    assert np.isclose(out.loc[6, "target_h5"], 0.25)
    assert pd.isna(out.loc[1, "target_h5"])
    assert pd.isna(out.loc[5, "target_h5"])


def test_build_walk_forward_splits_enforces_five_session_boundaries():
    panel = add_next_session_return(add_target_h5(_make_business_day_panel()))
    folds, lockbox = build_walk_forward_splits(panel)
    assert [fold["name"] for fold in folds] == ["fold_1", "fold_2", "fold_3"]
    assert all(len(fold["purge_dates"]) == 5 for fold in folds)
    assert all(len(fold["post_validation_embargo_dates"]) == 5 for fold in folds)
    assert lockbox["start"] == LOCKBOX_START
    assert lockbox["end"] == LOCKBOX_END
    assert lockbox["evaluation_end"] == pd.Timestamp("2026-06-23")
    assert len(lockbox["pre_start_purge"]) == 5
    assert len(lockbox["terminal_purge"]) == 5


def test_daily_ic_and_signal_pnl_metrics_are_reproducible():
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    rows = []
    for date in dates:
        for idx in range(10):
            rows.append(
                {
                    "date": date,
                    "ticker": f"T{idx:02d}",
                    "target_h5": float(idx) / 100.0,
                    "next_session_return": float(idx) / 200.0,
                }
            )
    panel = pd.DataFrame(rows)
    alpha = np.tile(np.arange(10, dtype=float), 2)

    ic = compute_daily_ic_series(panel, alpha)
    pnl = compute_signal_pnl_series(panel, alpha)
    metrics = compute_candidate_metrics(panel, alpha, n_trials=5)

    assert len(ic) == 2
    assert np.allclose(ic.to_numpy(), 1.0)
    assert len(pnl) == 2
    assert metrics["mean_ic"] >= 0.99
    assert metrics["icir"] == 0.0
    assert metrics["signal_pnl_score"] > 0.0


def test_signal_pnl_uses_next_session_return_not_target_h5():
    panel = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"] * 10),
            "ticker": [f"T{idx:02d}" for idx in range(10)],
            "target_h5": np.full(10, 0.99),
            "next_session_return": np.linspace(-0.02, 0.02, 10),
        }
    )
    alpha = np.arange(10, dtype=float)

    pnl = compute_signal_pnl_series(panel, alpha)
    centered = alpha - np.median(alpha)
    weights = centered / np.abs(centered).sum()
    expected = float(np.dot(weights, panel["next_session_return"].to_numpy()) - np.abs(weights).sum() * TRADING_COST_BPS)

    assert np.isclose(pnl.iloc[0], expected)


def test_filter_model_panel_applies_t_minus_1_feature_lag():
    panel = add_next_session_return(add_target_h5(_make_business_day_panel().query("ticker == 'AAA'").head(8).copy()))
    filtered = filter_model_panel(panel)

    assert filtered.iloc[0]["date"] == pd.Timestamp("2015-01-05")
    assert filtered.iloc[0]["close"] == 0.0
    assert filtered.iloc[0]["volume"] == 0.0
    assert filtered.iloc[1]["close"] == panel.iloc[0]["close"]
    assert filtered.iloc[1]["volume"] == panel.iloc[0]["volume"]


def test_enrich_with_unified_features_requires_35_feature_schema(monkeypatch: pytest.MonkeyPatch):
    panel = _make_business_day_panel().head(20).copy()

    class _BadAdapter:
        def __init__(self, **_kwargs):
            pass

        def generate_all(self, frame):
            return frame.assign(foreign_flow=1.0)

        def get_feature_groups(self):
            return {"alt_features": ["intraday_range"], "alt_data": ["foreign_flow"]}

    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.UnifiedFeatureAdapter", _BadAdapter)

    with pytest.raises(ValueError, match="feature schema mismatch"):
        enrich_with_unified_features(panel)


def test_enrich_with_unified_features_loads_expected_35_columns():
    panel = _make_feature_panel()
    enriched, feature_columns = enrich_with_unified_features(panel)

    assert len(feature_columns) == len(BASE_FEATURE_COLUMNS) + REQUIRED_FEATURE_COUNT
    assert len(set(feature_columns) - set(BASE_FEATURE_COLUMNS)) == REQUIRED_FEATURE_COUNT
    assert set(ALT_DATA_FEATURE_COLUMNS).issubset(enriched.columns)


def test_filter_model_panel_shifts_all_35_features_t_minus_1():
    panel = add_next_session_return(add_target_h5(_make_feature_panel()))
    panel, feature_columns = enrich_with_unified_features(panel)
    filtered = filter_model_panel(panel)
    shifted_features = [col for col in feature_columns if col not in BASE_FEATURE_COLUMNS]

    sample = filtered[filtered["ticker"] == "T00"].sort_values("date").reset_index(drop=True)
    source = panel[panel["ticker"] == "T00"].sort_values("date").reset_index(drop=True)
    assert len(shifted_features) == REQUIRED_FEATURE_COUNT
    for col in shifted_features[:5] + ALT_DATA_FEATURE_COLUMNS:
        assert np.isclose(sample.loc[0, col], 0.0, equal_nan=False)
        expected = 0.0 if pd.isna(source.loc[0, col]) else source.loc[0, col]
        assert np.isclose(sample.loc[1, col], expected, equal_nan=False)


def test_neutralize_alpha_by_date_reduces_sector_and_size_exposure():
    panel = _make_feature_panel().copy()
    panel["log_market_cap"] = np.log1p(panel["close"] * panel["volume"])
    alpha = np.where(panel["sector"] == "Tech", 3.0, -3.0) + 2.0 * panel["log_market_cap"].to_numpy()

    residual = neutralize_alpha_by_date(panel, alpha, enabled=True)
    work = panel.assign(residual=residual)
    sector_means = work.groupby(["date", "sector"])["residual"].mean().abs().max()
    residual_abs_max = work.groupby("date")["residual"].apply(lambda group: float(np.max(np.abs(group.to_numpy(dtype=float)))))

    assert sector_means < 1e-9
    assert residual_abs_max.max() < 1e-9


def test_compute_metrics_can_disable_neutralization():
    panel = _make_feature_panel().copy()
    panel["target_h5"] = np.where(panel["sector"] == "Tech", 1.0, -1.0)
    panel["next_session_return"] = panel["target_h5"]
    panel["log_market_cap"] = np.log1p(panel["close"] * panel["volume"])
    alpha = panel["target_h5"].to_numpy(dtype=float)

    raw_ic = compute_daily_ic_series(panel, alpha, neutralize=False)
    neutral_ic = compute_daily_ic_series(panel, alpha, neutralize=True)

    assert raw_ic.mean() > 0.9
    assert abs(neutral_ic.mean()) < 1e-9


def test_load_market_panel_fails_closed_on_pit_metadata(tmp_path: Path):
    panel = _make_business_day_panel().head(10).copy()
    panel.loc[0, "available_at"] = pd.NaT
    path = _make_market_file(tmp_path, panel)

    with pytest.raises(ValueError, match="PIT violation: missing as_of or available_at metadata"):
        load_market_panel(path)


def test_selection_applies_thresholds_and_pairwise_corr_gate():
    strong = {
        "alpha_id": "a1",
        "formula_hash": "001",
        "ast_depth": 2,
        "metrics": {"mean_ic": 0.02, "icir": 0.4, "signal_pnl_score": 0.2, "dsr": 0.8},
        "_alpha_values": np.arange(10, dtype=float),
    }
    duplicate = {
        "alpha_id": "a2",
        "formula_hash": "002",
        "ast_depth": 3,
        "metrics": {"mean_ic": 0.02, "icir": 0.4, "signal_pnl_score": 0.2, "dsr": 0.7},
        "_alpha_values": np.arange(10, dtype=float),
    }
    weak = {
        "alpha_id": "a3",
        "formula_hash": "003",
        "ast_depth": 1,
        "metrics": {"mean_ic": 0.001, "icir": 0.4, "signal_pnl_score": 0.2, "dsr": 0.7},
        "_alpha_values": np.arange(9, -1, -1, dtype=float),
    }

    promoted = select_promoted_candidates([duplicate, weak, strong])
    assert [candidate["alpha_id"] for candidate in promoted] == ["a1"]
    assert promoted[0]["metrics"]["pairwise_corr"] == 0.0


def test_candidate_record_clear_signals_releases_cached_arrays():
    record = CandidateRecord(
        node=GPNode(operator="terminal", value="close"),
        source=CandidateSource.TEMPLATE,
        formula_str="close",
        formula_hash="cleanup_001",
    )
    record._fold_values[0] = np.arange(5, dtype=float)
    record._alpha_values = np.arange(3, dtype=float)

    record.clear_signals()

    assert record._fold_values == {}
    assert record._alpha_values.size == 0


def test_nested_objective_scores_candidate_with_production_signature():
    scorer = NestedCVObjective(HybridAlphaMinerConfig())
    panel = _make_feature_panel().head(20).copy()
    panel["ret_1d"] = panel.groupby("ticker")["close"].pct_change().fillna(0.0)
    labels = np.linspace(0.0, 1.0, len(panel), dtype=float)
    inner_splits = [{"inner_fold": 0, "train": np.arange(10), "val": np.arange(10, len(panel))}]
    record = CandidateRecord(
        node=GPNode(operator="terminal", value="close"),
        source=CandidateSource.TEMPLATE,
        formula_str="close",
        formula_hash="reuse_001",
    )

    scored = scorer.score_candidate(
        candidate=record,
        panel=panel,
        feat_cols=["close", "open", "high", "low", "volume", "ret_1d"],
        labels=labels,
        inner_splits=inner_splits,
    )

    assert np.isfinite(scored.objective_score)


def test_execute_node_grouped_caches_duplicate_subtrees_in_memory(monkeypatch: pytest.MonkeyPatch):
    synth = LLMSymbolicSynthesizer(provider="mock")
    panel = _make_feature_panel().head(12).copy()
    node = GPNode(
        operator="+",
        children=[
            GPNode(operator="ts_mean", children=[GPNode(operator="terminal", value="close"), GPNode(operator="terminal", value="3")]),
            GPNode(operator="ts_mean", children=[GPNode(operator="terminal", value="close"), GPNode(operator="terminal", value="3")]),
        ],
    )
    cache_sizes: list[int] = []
    original = synth._execute_tree_cached

    def _wrapped(node_arg, features_arg, cache_key):
        value = original(node_arg, features_arg, cache_key)
        cache_sizes.append(len(synth._subtree_cache))
        return value

    monkeypatch.setattr(synth, "_execute_tree_cached", _wrapped)

    result = synth.execute_node_grouped(node, panel, ["close", "open", "high", "low", "volume"])

    assert len(result) == len(panel)
    assert max(cache_sizes) < sum(1 for _ in node._collect_nodes()) * panel["ticker"].nunique()


def test_hybrid_alpha_miner_clears_non_selected_candidate_buffers_after_top_k(monkeypatch: pytest.MonkeyPatch):
    config = HybridAlphaMinerConfig(candidate_budget=2, top_k=1, n_outer_folds=2, n_inner_folds=2)
    miner = HybridAlphaMiner(config)
    panel = _make_feature_panel().copy()
    panel["ret_1d"] = panel.groupby("ticker")["close"].pct_change().fillna(0.0)
    labels = np.linspace(0.0, 1.0, len(panel), dtype=float)
    good = CandidateRecord(
        node=GPNode(operator="terminal", value="close"),
        source=CandidateSource.TEMPLATE,
        formula_str="close",
        formula_hash="good_001",
    )
    bad = CandidateRecord(
        node=GPNode(operator="terminal", value="open"),
        source=CandidateSource.TEMPLATE,
        formula_str="open",
        formula_hash="bad_001",
    )
    runner_up = CandidateRecord(
        node=GPNode(operator="terminal", value="high"),
        source=CandidateSource.TEMPLATE,
        formula_str="high",
        formula_hash="runner_001",
    )

    class _FakeGenerator:
        def __init__(self, **_kwargs):
            pass

        def generate_all_sources(self):
            return [good, runner_up, bad]

    def _fake_score(candidate, panel, feat_cols, labels, inner_splits, selected_values=None, ticker_col="ticker", date_col="date", outer_fold_idx=0, synth=None):
        candidate._fold_values[outer_fold_idx] = np.arange(len(panel), dtype=float)
        candidate._fold_metrics[outer_fold_idx] = {
            "ic": 0.2 if candidate is good else 0.15 if candidate is runner_up else -0.1,
            "signed_ic": 0.2 if candidate is good else 0.15 if candidate is runner_up else 0.0,
            "sign_consistency": 1.0 if candidate is not bad else 0.0,
            "dsr_proxy": 1.0 if candidate is good else 0.8 if candidate is runner_up else 0.0,
            "coverage": 0.95 if candidate is not bad else 0.10,
            "max_correlation": 0.0,
            "n_inner_folds_scored": 1,
        }
        candidate.inner_metrics = dict(candidate._fold_metrics[outer_fold_idx])
        candidate.objective_score = 1.0 if candidate is good else 0.9 if candidate is runner_up else float("-inf")
        return candidate

    monkeypatch.setattr(
        "omega.quant.evolution.hybrid_alpha_miner.HybridCandidateGenerator",
        _FakeGenerator,
    )
    monkeypatch.setattr(
        miner.scorer,
        "score_candidate",
        _fake_score,
    )

    selected, _evidence = miner.run(panel, ["close", "open", "high", "low", "volume", "ret_1d"], labels)

    assert [candidate.formula_hash for candidate in selected] == ["good_001"]
    assert bad._fold_values == {}
    assert runner_up._fold_values == {}
    assert good._fold_values


def test_execute_node_grouped_clears_subtree_cache_when_panel_data_changes(monkeypatch: pytest.MonkeyPatch):
    synth = LLMSymbolicSynthesizer(provider="mock")
    dates = pd.bdate_range("2024-01-02", periods=5)
    panel_a = pd.DataFrame(
        {
            "ticker": ["AAA"] * 5,
            "date": dates,
            "close": [10.0, 11.0, 12.0, 13.0, 14.0],
            "open": [10.0, 11.0, 12.0, 13.0, 14.0],
            "high": [10.0, 11.0, 12.0, 13.0, 14.0],
            "low": [10.0, 11.0, 12.0, 13.0, 14.0],
            "volume": [100.0, 101.0, 102.0, 103.0, 104.0],
        }
    )
    panel_b = panel_a.copy(deep=True)
    panel_b.index = panel_a.index
    panel_b.loc[2, "close"] = 120.0
    panel_b.loc[2, "open"] = 120.0
    panel_b.loc[2, "high"] = 120.0
    panel_b.loc[2, "low"] = 120.0

    node = GPNode(
        operator="ts_mean",
        children=[
            GPNode(operator="terminal", value="close"),
            GPNode(operator="terminal", value="3"),
        ],
    )
    cleared: list[int] = []
    original_clear = synth.clear_execution_cache

    def _wrapped_clear():
        cleared.append(1)
        original_clear()

    monkeypatch.setattr(synth, "clear_execution_cache", _wrapped_clear)

    result_a = synth.execute_node_grouped(node, panel_a, ["close", "open", "high", "low", "volume"])
    result_b = synth.execute_node_grouped(node, panel_b, ["close", "open", "high", "low", "volume"])

    expected_b = LLMSymbolicSynthesizer(provider="mock").execute_node_grouped(
        node,
        panel_b,
        ["close", "open", "high", "low", "volume"],
    )

    assert cleared == [1]
    assert not np.allclose(result_a, result_b)
    assert np.allclose(result_b, expected_b)


def test_persist_promoted_hybrid_alphas_writes_to_conformal_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.REPO_ROOT", tmp_path)
    expected_metric_keys = ("mean_ic", "icir", "signal_pnl_score", "dsr", "coverage", "pairwise_corr")
    promoted = [
        {
            "alpha_id": "alpha_001",
            "formula": "close",
            "formula_hash": "abc123def456",
            "source": "llm",
            "ast_depth": 1,
            "selection_window": {"start": pd.Timestamp("2024-01-01"), "end": pd.Timestamp("2024-02-01")},
            "metrics": {"mean_ic": 0.02, "icir": 0.4, "signal_pnl_score": 0.15, "dsr": 0.8, "coverage": 0.95, "pairwise_corr": 0.1},
        }
    ]
    lockbox_report = [
        {
            "alpha_id": "alpha_001",
            "formula_hash": "abc123def456",
            "metrics": {"mean_ic": 0.015, "icir": 0.35, "signal_pnl_score": 0.12, "dsr": 0.7, "coverage": 0.9},
        }
    ]

    persisted = persist_promoted_hybrid_alphas(
        promoted,
        lockbox_report=lockbox_report,
        thresholds=DEFAULT_PROMOTION_THRESHOLDS,
        feature_columns=["open", "close"],
        provider="mock",
        neutralize=True,
        registry_path=Path("tmp/conformal_registry.sqlite"),
        artifact_dir=Path("tmp/hybrid_alpha_registry"),
        pit_embargo=pd.Timestamp("2026-06-30"),
    )

    registry = DatabaseRegistry(database_url=f"sqlite:///{(tmp_path / 'tmp' / 'conformal_registry.sqlite').as_posix()}")
    records = registry.list_models(name_prefix="hybrid_alpha_llm_", status="ready")

    assert len(persisted) == 1
    assert len(records) == 1
    assert records[0].name == "hybrid_alpha_llm_alpha_001"
    assert records[0].metrics["formula"] == "close"
    assert records[0].metrics["lockbox_metrics"]["dsr"] == 0.7
    assert records[0].metrics["lockbox_metrics"]["coverage"] == 0.9
    for key in expected_metric_keys:
        assert records[0].metrics[key] == promoted[0]["metrics"][key]

    artifact_path = tmp_path / persisted[0]["path"]
    assert artifact_path.exists()
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    for key in expected_metric_keys:
        assert artifact_payload["validation_metrics"][key] == promoted[0]["metrics"][key]
    assert artifact_payload["lockbox_metrics"]["coverage"] == 0.9


def test_selection_accepts_custom_thresholds():
    candidate = {
        "alpha_id": "a1",
        "formula_hash": "001",
        "ast_depth": 2,
        "metrics": {"mean_ic": 0.02, "icir": 0.15, "signal_pnl_score": 0.05, "dsr": 0.2},
        "_alpha_values": np.arange(10, dtype=float),
    }

    promoted = select_promoted_candidates(
        [candidate],
        thresholds={"mean_ic": 0.01, "icir": 0.10, "signal_pnl_score": 0.04, "dsr": 0.1, "pairwise_corr": 0.5},
    )

    assert [item["alpha_id"] for item in promoted] == ["a1"]


def test_resolve_llm_provider_defaults_to_mock_without_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OMEGA_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OMEGA_LLM_API_KEY", raising=False)

    assert resolve_llm_provider() == "mock"


def test_resolve_llm_provider_uses_env_provider_first(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OMEGA_LLM_PROVIDER", "openai-compatible")
    monkeypatch.delenv("OMEGA_LLM_API_KEY", raising=False)

    assert resolve_llm_provider() == "openai-compatible"


def test_resolve_llm_provider_falls_back_to_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OMEGA_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OMEGA_LLM_API_KEY", "test-key")

    assert resolve_llm_provider() == "openai-compatible"


def test_resolve_llm_provider_cli_override_wins(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OMEGA_LLM_PROVIDER", "mock")
    monkeypatch.setenv("OMEGA_LLM_API_KEY", "test-key")

    assert resolve_llm_provider("openai-compatible") == "openai-compatible"


def test_run_hybrid_real_market_records_requested_and_effective_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    market_path = _make_market_file(tmp_path, _make_business_day_panel())
    captured: dict[str, object] = {}

    class _FakeMiner:
        def __init__(self, config):
            self.config = config
            captured["candidate_budget"] = config.candidate_budget
            captured["top_k"] = config.top_k

        def run(self, *_args, **_kwargs):
            return [], {"total_generated": 0, "total_selected": 0}

    class _FakeSynthesizer:
        def __init__(self, **kwargs):
            self.requested_provider = kwargs["provider"]
            self.effective_provider = "mock"

        def execute_node_grouped(self, *_args, **_kwargs):
            raise AssertionError("should not execute when no selected candidates")

    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.HybridAlphaMiner", _FakeMiner)
    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.LLMSymbolicSynthesizer", _FakeSynthesizer)
    monkeypatch.setattr(
        "scripts.run_hybrid_alpha_evolution.enrich_with_unified_features",
        lambda df: (df.assign(sector="Other", log_market_cap=np.log1p(df["close"] * df["volume"])), BASE_FEATURE_COLUMNS),
    )

    payload = run_hybrid_real_market_integration(market_path, tmp_path / "out.json", provider="mock")

    assert payload["requested_provider"] == "mock"
    assert payload["effective_provider"] == "mock"
    assert captured == {"candidate_budget": 40, "top_k": 10}
    assert payload["thresholds"] == DEFAULT_PROMOTION_THRESHOLDS
    assert payload["lockbox_oos_report"]["top_candidates_diagnostic"] == []


def test_resolve_llm_provider_rejects_unsupported_values(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OMEGA_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OMEGA_LLM_API_KEY", raising=False)

    with pytest.raises(ValueError, match="Unsupported provider"):
        resolve_llm_provider("bad-provider")

    with pytest.raises(ValueError, match="Unsupported provider in OMEGA_LLM_PROVIDER"):
        monkeypatch.setenv("OMEGA_LLM_PROVIDER", "bad-provider")
        resolve_llm_provider()


def test_lockbox_selection_isolation_uses_only_pre_lockbox_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    market_path = _make_market_file(tmp_path, _make_business_day_panel())
    captured: dict[str, object] = {}

    class _FakeMiner:
        def __init__(self, config):
            captured["config_provider"] = config.llm_provider

        def run(self, *_args, **_kwargs):
            return [
                _FakeCandidate(
                    formula_str="close",
                    formula_hash="strong_validation_weak_lockbox",
                    source=_FakeSource("mock"),
                    node=GPNode(operator="terminal", value="close"),
                )
            ], {"total_generated": 1, "total_selected": 1}

    class _FakeSynthesizer:
        def __init__(self, **kwargs):
            captured["synth_provider"] = kwargs["provider"]
            captured["synth_use_mock"] = kwargs["use_mock"]

        def execute_node_grouped(self, node, panel, *_args, **_kwargs):
            if node.value != "close":
                raise AssertionError("unexpected node")
            if panel["date"].min() >= LOCKBOX_START:
                return -panel["next_session_return"].to_numpy(dtype=float)
            return panel["target_h5"].to_numpy(dtype=float)

    def _fake_metrics(panel, alpha_values, n_trials):
        if panel["date"].min() >= LOCKBOX_START:
            return {"mean_ic": -0.2, "icir": -0.4, "signal_pnl_score": -0.3, "dsr": 0.1, "n_ic_days": 1, "n_pnl_days": 1}
        return {"mean_ic": 0.02, "icir": 0.4, "signal_pnl_score": 0.2, "dsr": 0.8, "n_ic_days": 1, "n_pnl_days": 1}

    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.HybridAlphaMiner", _FakeMiner)
    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.LLMSymbolicSynthesizer", _FakeSynthesizer)
    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.compute_candidate_metrics", _fake_metrics)
    monkeypatch.setattr(
        "scripts.run_hybrid_alpha_evolution.enrich_with_unified_features",
        lambda df: (df.assign(sector="Other", log_market_cap=np.log1p(df["close"] * df["volume"])), BASE_FEATURE_COLUMNS),
    )

    payload = run_hybrid_real_market_integration(market_path, tmp_path / "out.json", provider="openai-compatible")

    promoted = payload["risk_adjusted_selection_evidence"]["promoted"]
    assert payload["alphas"] == promoted
    assert [candidate["formula_hash"] for candidate in promoted] == ["strong_validation_weak_lockbox"]
    assert payload["risk_adjusted_selection_evidence"]["selection_source"] == "pre_lockbox_validation_only"
    assert payload["lockbox_oos_report"]["candidates"][0]["metrics"]["mean_ic"] < 0.0
    diagnostic = payload["lockbox_oos_report"]["top_candidates_diagnostic"]
    assert diagnostic == [
        {
            "alpha_id": "hybrid_alpha_000",
            "formula": "close",
            "formula_hash": "strong_validation_weak_lockbox",
            "source": "mock",
            "ast_depth": 1,
            "oos_mean_ic": -0.2,
            "oos_icir": -0.4,
            "oos_signal_pnl_score": -0.3,
            "oos_dsr": 0.1,
        }
    ]
    assert payload["pit_safety"]["lockbox_selection_excluded"] is True
    assert payload["provider"] == "openai-compatible"
    assert captured == {
        "config_provider": "openai-compatible",
        "synth_provider": "openai-compatible",
        "synth_use_mock": False,
    }


def test_terminal_evaluation_end_assertion():
    panel = add_next_session_return(add_target_h5(_make_business_day_panel()))
    _, lockbox = build_walk_forward_splits(panel)

    assert lockbox["evaluation_end"] == pd.Timestamp("2026-06-23")


def test_validate_candidate_node_accepts_infix_serialized_tree_shape():
    node = GPNode(
        operator="-",
        children=[
            GPNode(
                operator="+",
                children=[
                    GPNode(operator="sigmoid", children=[GPNode(operator="terminal", value="low")]),
                    GPNode(operator="terminal", value="low"),
                ],
            ),
            GPNode(operator="terminal", value="close"),
        ],
    )
    validate_candidate_node(node)


def test_validate_candidate_node_allows_subtree_lookback_child():
    node = GPNode(
        operator="ts_mean",
        children=[
            GPNode(operator="terminal", value="close"),
            GPNode(
                operator="+",
                children=[
                    GPNode(operator="terminal", value="2.0"),
                    GPNode(operator="terminal", value="3.0"),
                ],
            ),
        ],
    )

    validate_candidate_node(node)


def test_validate_candidate_node_rejects_out_of_range_leaf_lookback_child():
    node = GPNode(
        operator="ts_mean",
        children=[
            GPNode(operator="terminal", value="close"),
            GPNode(operator="terminal", value="61.0"),
        ],
    )

    with pytest.raises(ValueError, match=r"Lookback 61 outside range \[2, 60\]"):
        validate_candidate_node(node)


def test_parse_args_accepts_supported_provider_values(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", ["prog", "--provider", "mock"])
    from scripts.run_hybrid_alpha_evolution import _parse_args

    args = _parse_args()

    assert args.provider in SUPPORTED_LLM_PROVIDERS


def test_run_hybrid_real_market_propagates_custom_budget_and_top_k(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    market_path = _make_market_file(tmp_path, _make_business_day_panel())
    captured: dict[str, object] = {}

    class _FakeMiner:
        def __init__(self, config):
            captured["candidate_budget"] = config.candidate_budget
            captured["top_k"] = config.top_k

        def run(self, *_args, **_kwargs):
            return [], {"total_generated": 0, "total_selected": 0}

    class _FakeSynthesizer:
        def __init__(self, **kwargs):
            self.requested_provider = kwargs["provider"]
            self.effective_provider = kwargs["provider"]

        def execute_node_grouped(self, *_args, **_kwargs):
            raise AssertionError("should not execute when no selected candidates")

    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.HybridAlphaMiner", _FakeMiner)
    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.LLMSymbolicSynthesizer", _FakeSynthesizer)

    run_hybrid_real_market_integration(market_path, tmp_path / "out.json", provider="mock", budget=64, top_k=17)

    assert captured == {"candidate_budget": 64, "top_k": 17}


def test_run_hybrid_real_market_propagates_max_depth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    market_path = _make_market_file(tmp_path, _make_business_day_panel())
    captured: dict[str, object] = {}

    class _FakeMiner:
        def __init__(self, config):
            self.config = config

        def run(self, *_args, **_kwargs):
            return [
                _FakeCandidate(
                    formula_str="close",
                    formula_hash="depth_007",
                    source=_FakeSource("mock"),
                    node=GPNode(
                        operator="+",
                        children=[
                            GPNode(operator="terminal", value="close"),
                            GPNode(
                                operator="+",
                                children=[
                                    GPNode(operator="terminal", value="open"),
                                    GPNode(
                                        operator="+",
                                        children=[
                                            GPNode(operator="terminal", value="high"),
                                            GPNode(
                                                operator="+",
                                                children=[
                                                    GPNode(operator="terminal", value="low"),
                                                    GPNode(
                                                        operator="+",
                                                        children=[
                                                            GPNode(operator="terminal", value="volume"),
                                                            GPNode(operator="terminal", value="1.0"),
                                                        ],
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                )
            ], {"total_generated": 1, "total_selected": 1}

    class _FakeSynthesizer:
        def __init__(self, **kwargs):
            self.requested_provider = kwargs["provider"]
            self.effective_provider = kwargs["provider"]

        def execute_node_grouped(self, _node, panel, *_args, **_kwargs):
            return np.arange(len(panel), dtype=float)

    def _fake_build_formula_parser(max_depth: int = 10):
        captured["parser_max_depth"] = max_depth

        class _Parser:
            def __init__(self, depth: int):
                self.max_depth = depth

        return _Parser(max_depth)

    def _fake_validate_candidate_node(node, max_depth: int = 10):
        captured["validated_depth"] = node.depth()
        captured["validator_max_depth"] = max_depth

    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.HybridAlphaMiner", _FakeMiner)
    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.LLMSymbolicSynthesizer", _FakeSynthesizer)
    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.build_formula_parser", _fake_build_formula_parser)
    monkeypatch.setattr("scripts.run_hybrid_alpha_evolution.validate_candidate_node", _fake_validate_candidate_node)

    run_hybrid_real_market_integration(market_path, tmp_path / "out.json", provider="mock", max_depth=10)

    assert captured == {"parser_max_depth": 10, "validated_depth": 6, "validator_max_depth": 10}


def test_parse_args_accepts_budget_and_top_k(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", ["prog", "--provider", "mock", "--budget", "64", "--top-k", "17"])
    from scripts.run_hybrid_alpha_evolution import _parse_args

    args = _parse_args()

    assert args.provider == "mock"
    assert args.budget == 64
    assert args.top_k == 17


def test_parse_args_accepts_threshold_flags(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--provider",
            "mock",
            "--min-ic",
            "0.02",
            "--min-icir",
            "0.4",
            "--min-pnl-score",
            "0.12",
            "--min-dsr",
            "0.7",
            "--max-corr",
            "0.3",
        ],
    )
    from scripts.run_hybrid_alpha_evolution import _parse_args

    args = _parse_args()

    assert args.min_ic == 0.02
    assert args.min_icir == 0.4
    assert args.min_pnl_score == 0.12
    assert args.min_dsr == 0.7
    assert args.max_corr == 0.3


def test_parse_args_accepts_neutralize_toggle(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", ["prog", "--no-neutralize"])
    from scripts.run_hybrid_alpha_evolution import _parse_args

    args = _parse_args()

    assert args.neutralize is False


def test_parse_args_rejects_invalid_threshold_flags(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", ["prog", "--min-ic", "-0.01"])
    from scripts.run_hybrid_alpha_evolution import _parse_args

    with pytest.raises(SystemExit):
        _parse_args()

    monkeypatch.setattr("sys.argv", ["prog", "--max-corr", "1.1"])
    with pytest.raises(SystemExit):
        _parse_args()


def test_parse_args_accepts_max_depth(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.argv", ["prog", "--provider", "mock", "--max-depth", "12"])
    from scripts.run_hybrid_alpha_evolution import _parse_args

    args = _parse_args()

    assert args.provider == "mock"
    assert args.max_depth == 12
