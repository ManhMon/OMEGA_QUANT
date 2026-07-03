import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _import_module_fresh():
    sys.modules.pop("backtest_hybrid_regime", None)
    return importlib.import_module("backtest_hybrid_regime")


def test_thread_env_capped_before_numpy_import():
    module = _import_module_fresh()

    assert module.os.environ["OMP_NUM_THREADS"] == "1"
    assert module.os.environ["MKL_NUM_THREADS"] == "1"
    assert module.os.environ["OPENBLAS_NUM_THREADS"] == "1"


def test_generate_features_downcasts_alpha_and_latent_columns(monkeypatch):
    module = _import_module_fresh()

    panel = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "symbol": ["AAA", "AAA"],
            "close": [10.0, 10.5],
            "volume": [1000.0, 1200.0],
            "returns": [0.01, 0.02],
        }
    )
    precomputed = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "symbol": ["AAA", "AAA"],
            "alpha_value": np.array([0.1, 0.2], dtype=np.float64),
            "alpha_latent_ae_00": np.array([1.1, 1.2], dtype=np.float64),
        }
    )

    precomputed_suffix = Path(module.PRECOMPUTED_FEATURES_PATH).parts
    monkeypatch.setattr(module.Path, "exists", lambda self: self.parts[-len(precomputed_suffix):] == precomputed_suffix)
    monkeypatch.setattr(module.pd, "read_parquet", lambda path: precomputed.copy())

    feat_df = module.generate_features(panel)

    assert feat_df["alpha_value"].dtype == np.float32
    assert feat_df["alpha_latent_ae_00"].dtype == np.float32
    assert feat_df["latent_ae_00"].dtype == np.float32
    assert feat_df["close"].dtype == np.float64


def test_main_parallel_uses_loky_and_matches_serial(monkeypatch):
    module = _import_module_fresh()

    args = module.argparse.Namespace(
        start_date="2024-01-01",
        end_date="2024-01-10",
        capital=1_000_000.0,
        folds=2,
        n_test_folds=1,
        train_window=1,
        test_window=1,
        dynamic_universe=False,
        symbol_count=2,
        quick_mode=False,
        output_tag="",
        embargo_pct=0.01,
        label_horizon=5,
        workers=1,
        top_k=5,
        alpha_group=None,
        model_type="ridge",
    )

    raw_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
            "ticker": ["AAA", "AAA", "BBB", "BBB"],
            "close": [10.0, 10.1, 20.0, 20.2],
            "volume": [1000.0, 1000.0, 1500.0, 1500.0],
        }
    )
    panel_full = raw_df.rename(columns={"ticker": "symbol"}).assign(returns=0.01, adv_vnd=1.0)
    feat_df = panel_full.assign(alpha_value=np.float32(0.5), latent_ae_00=np.float32(1.0))
    pred_lag_df = pd.DataFrame({"x": [1]})
    close_pivot_full = pd.DataFrame({"AAA": [10.0], "BBB": [20.0]})
    fold_specs_seen = []
    parallel_kwargs = {}

    class FakeCPCV:
        def __init__(self, *args, **kwargs):
            pass

        def get_n_folds(self):
            return 2

        def split(self, ts_index):
            yield np.array([0, 1]), np.array([2])
            yield np.array([1, 2]), np.array([3])

    def fake_run_single_fold(**spec):
        fold_specs_seen.append(spec["fold_id"])
        fold_id = spec["fold_id"]
        return {
            "Baseline": {
                "annualized_sharpe": 0.1 * fold_id,
                "max_drawdown": -0.01 * fold_id,
                "total_return": 0.02 * fold_id,
                "n_days": 5,
            }
        }

    def fake_parallel(**kwargs):
        parallel_kwargs.update(kwargs)

        def runner(tasks):
            return [task() for task in list(tasks)]

        return runner

    def fake_delayed(fn):
        def wrapper(*args, **kwargs):
            return lambda: fn(*args, **kwargs)

        return wrapper

    monkeypatch.setattr(module, "parse_args", lambda: args)
    monkeypatch.setattr(module, "load_raw_data", lambda *a, **k: raw_df.copy())
    monkeypatch.setattr(module, "select_static_universe", lambda *a, **k: ["AAA", "BBB"])
    monkeypatch.setattr(module, "prepare_panel", lambda *a, **k: panel_full.copy())
    monkeypatch.setattr(module, "generate_features", lambda *a, **k: feat_df.copy())
    monkeypatch.setattr(module, "precompute_prediction_lags", lambda *a, **k: pred_lag_df.copy())
    monkeypatch.setattr(module, "precompute_close_pivot", lambda *a, **k: close_pivot_full.copy())
    monkeypatch.setattr(module, "CombinatorialPurgedKFold", FakeCPCV)
    monkeypatch.setattr(module, "build_pipeline_config", lambda capital: {"capital": capital})
    monkeypatch.setattr(module, "run_single_fold", fake_run_single_fold)
    monkeypatch.setattr(module, "Parallel", fake_parallel)
    monkeypatch.setattr(module, "delayed", fake_delayed)
    monkeypatch.setattr(module, "print_comparison_table", lambda *a, **k: None)
    monkeypatch.setattr(module, "save_comparison_json", lambda *a, **k: "out.json")
    monkeypatch.setattr(module, "time", type("FakeTime", (), {"time": staticmethod(lambda: 100.0)})())

    serial_result = module.main()
    serial_fold_order = fold_specs_seen[:]

    args.workers = 2
    fold_specs_seen.clear()
    parallel_result = module.main()

    assert serial_fold_order == [1, 2]
    assert fold_specs_seen == [1, 2]
    assert parallel_kwargs["backend"] == "threading"

    monkeypatch.setenv("OMEGA_BACKTEST_BACKEND", "loky")
    fold_specs_seen.clear()
    parallel_kwargs.clear()
    parallel_result_loky = module.main()
    assert parallel_kwargs["backend"] == "loky"

    serial_baseline = serial_result["Baseline"]
    parallel_baseline = parallel_result["Baseline"]
    parallel_baseline_loky = parallel_result_loky["Baseline"]
    assert parallel_baseline["per_fold_sharpe"] == serial_baseline["per_fold_sharpe"]
    assert parallel_baseline["per_fold_max_dd"] == serial_baseline["per_fold_max_dd"]
    assert parallel_baseline["per_fold_return"] == serial_baseline["per_fold_return"]
    assert parallel_baseline["mean_sharpe"] == pytest.approx(serial_baseline["mean_sharpe"])
    assert parallel_baseline["mean_max_dd"] == pytest.approx(serial_baseline["mean_max_dd"])
    assert parallel_baseline["mean_return"] == pytest.approx(serial_baseline["mean_return"])
    assert parallel_baseline_loky["per_fold_sharpe"] == serial_baseline["per_fold_sharpe"]
    assert parallel_baseline_loky["per_fold_max_dd"] == serial_baseline["per_fold_max_dd"]
    assert parallel_baseline_loky["per_fold_return"] == serial_baseline["per_fold_return"]
    assert parallel_baseline_loky["mean_sharpe"] == pytest.approx(serial_baseline["mean_sharpe"])
    assert parallel_baseline_loky["mean_max_dd"] == pytest.approx(serial_baseline["mean_max_dd"])
    assert parallel_baseline_loky["mean_return"] == pytest.approx(serial_baseline["mean_return"])


def test_p2full_cache_roundtrip_and_equivalence(tmp_path, monkeypatch):
    module = _import_module_fresh()

    feat_df = pd.DataFrame(
        {
            "date": pd.to_datetime([
                "2024-01-02", "2024-01-03", "2024-01-04",
                "2024-01-02", "2024-01-03", "2024-01-04",
            ]),
            "symbol": ["AAA", "AAA", "AAA", "BBB", "BBB", "BBB"],
            "close": [10.0, 10.1, 10.2, 20.0, 20.1, 20.2],
            "volume": [1000.0] * 6,
            "returns": [0.0, 0.01, 0.01, 0.0, 0.01, 0.01],
            "alpha_one": np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], dtype=np.float32),
            "alpha_two": np.array([6.0, 5.0, 4.0, 3.0, 2.0, 1.0], dtype=np.float32),
        }
    )
    args = module.argparse.Namespace(
        start_date="2024-01-01",
        end_date="2024-01-31",
        dynamic_universe=True,
        symbol_count=60,
        output_tag="p2full_smoke",
    )

    monkeypatch.setattr(module, "PRECOMPUTE_CACHE_DIR", str(tmp_path.relative_to(module.REPO_ROOT) if tmp_path.is_relative_to(module.REPO_ROOT) else tmp_path))

    uncached_pred = module.precompute_prediction_lags(feat_df)
    uncached_close = module.precompute_close_pivot(feat_df)

    pred_first, close_first, meta_first = module.load_or_create_shared_precomputes(feat_df, args)
    pred_second, close_second, meta_second = module.load_or_create_shared_precomputes(feat_df, args)

    pd.testing.assert_frame_equal(pred_first.sort_index(axis=1), uncached_pred.sort_index(axis=1))
    pd.testing.assert_frame_equal(close_first.sort_index(axis=1), uncached_close.sort_index(axis=1))
    pd.testing.assert_frame_equal(pred_second.sort_index(axis=1), uncached_pred.sort_index(axis=1))
    pd.testing.assert_frame_equal(close_second.sort_index(axis=1), uncached_close.sort_index(axis=1))

    assert meta_first["cache_enabled"] is True
    assert meta_first["cache_hit"] is False
    assert meta_second["cache_hit"] is True


def test_p2full_cache_invalidates_when_panel_values_change(tmp_path, monkeypatch):
    module = _import_module_fresh()

    feat_df = pd.DataFrame(
        {
            "date": pd.to_datetime([
                "2024-01-02", "2024-01-03", "2024-01-04",
                "2024-01-02", "2024-01-03", "2024-01-04",
            ]),
            "symbol": ["AAA", "AAA", "AAA", "BBB", "BBB", "BBB"],
            "close": [10.0, 10.1, 10.2, 20.0, 20.1, 20.2],
            "volume": [1000.0] * 6,
            "returns": [0.0, 0.01, 0.01, 0.0, 0.01, 0.01],
            "alpha_one": np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], dtype=np.float32),
            "alpha_two": np.array([6.0, 5.0, 4.0, 3.0, 2.0, 1.0], dtype=np.float32),
        }
    )
    changed_feat_df = feat_df.copy()
    changed_feat_df["close"] = changed_feat_df["close"] + np.array([0.0, 0.3, 0.0, 0.0, 0.0, 0.0])
    changed_feat_df["alpha_one"] = changed_feat_df["alpha_one"] + np.array([0.0, 0.25, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    args = module.argparse.Namespace(
        start_date="2024-01-01",
        end_date="2024-01-31",
        dynamic_universe=True,
        symbol_count=60,
        output_tag="p2full_smoke",
    )

    monkeypatch.setattr(module, "PRECOMPUTE_CACHE_DIR", str(tmp_path.relative_to(module.REPO_ROOT) if tmp_path.is_relative_to(module.REPO_ROOT) else tmp_path))

    pred_first, close_first, meta_first = module.load_or_create_shared_precomputes(feat_df, args)
    pred_second, close_second, meta_second = module.load_or_create_shared_precomputes(changed_feat_df, args)

    expected_pred_second = module.precompute_prediction_lags(changed_feat_df)
    expected_close_second = module.precompute_close_pivot(changed_feat_df)

    assert meta_first["cache_hit"] is False
    assert meta_second["cache_hit"] is False
    assert meta_first["cache_key"] != meta_second["cache_key"]
    pd.testing.assert_frame_equal(pred_second.sort_index(axis=1), expected_pred_second.sort_index(axis=1))
    pd.testing.assert_frame_equal(close_second.sort_index(axis=1), expected_close_second.sort_index(axis=1))
    with pytest.raises(AssertionError):
        pd.testing.assert_frame_equal(pred_second.sort_index(axis=1), pred_first.sort_index(axis=1))
    with pytest.raises(AssertionError):
        pd.testing.assert_frame_equal(close_second.sort_index(axis=1), close_first.sort_index(axis=1))


def test_non_p2full_skips_disk_cache(monkeypatch):
    module = _import_module_fresh()

    feat_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "symbol": ["AAA", "AAA"],
            "close": [10.0, 10.1],
            "volume": [1000.0, 1000.0],
            "returns": [0.0, 0.01],
            "alpha_one": np.array([1.0, 2.0], dtype=np.float32),
        }
    )
    args = module.argparse.Namespace(
        start_date="2024-01-01",
        end_date="2024-01-31",
        dynamic_universe=False,
        symbol_count=10,
        output_tag="e4a_tcost15",
    )

    calls = {"pred": 0, "close": 0}
    orig_pred = module.precompute_prediction_lags
    orig_close = module.precompute_close_pivot

    def fake_pred(df):
        calls["pred"] += 1
        return orig_pred(df)

    def fake_close(df):
        calls["close"] += 1
        return orig_close(df)

    monkeypatch.setattr(module, "precompute_prediction_lags", fake_pred)
    monkeypatch.setattr(module, "precompute_close_pivot", fake_close)

    _, _, meta = module.load_or_create_shared_precomputes(feat_df, args)

    assert meta["cache_enabled"] is False
    assert calls == {"pred": 1, "close": 1}
