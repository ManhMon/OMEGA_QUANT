from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import inspect
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from omega.data import pipeline_quality as quality
from omega.data.pipeline_quality import PipelineQualityChecker, SCHEMAS


ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
NOW = datetime(2026, 10, 22, 12, tzinfo=UTC)
DATASETS = ("market", "financials", "news_live", "derivatives")
EXPECTED_SCHEMAS = {
    "market": ("ticker", "date", "exchange", "open", "high", "low", "close", "volume", "as_of", "available_at", "source", "price_scale", "adjusted", "rebuild_date"),
    "financials": ("symbol", "endpoint", "period_type", "fiscal_year", "fiscal_quarter", "item_code", "item_value", "fiscal_period_end", "source_publish_at", "available_at", "is_audited", "is_restated", "version"),
    "news_live": ("symbol", "title", "publish_time", "sentiment_score", "available_at", "url", "source", "fetched_at", "raw_timestamp", "payload_sha256", "parser_version", "legacy_row"),
    "derivatives": ("time", "ticker", "open", "high", "low", "close", "volume", "as_of", "available_at", "source", "price_scale", "adjusted", "rebuild_date", "volume_unit", "historical_pit_verified"),
}
ENTRYPOINTS = {
    "scripts/update_market_data.py": "market",
    "scripts/fetch_financial_statements.py": "financials",
    "scripts/run_macro_news_pipeline.py": "macro_news",
    "scripts/fetch_news_sentiment.py": "news_live",
    "scripts/update_market_flow.py": "flows",
    "scripts/update_recent_portfolio_data.py": "market_subset",
}
# Captured from actual producer bytes, not transcribed summary inventory.
SOURCE_HASHES = {
    "scripts/update_market_data.py": "f9bf45c7" "ad3a416e" "25d78285" "0b6edf00" "00a6d034" "1a47f56a" "42baf102" "44588741",
    "scripts/fetch_financial_statements.py": "329a181f" "64038a80" "8af04eed" "9736af38" "f47c4148" "424dbab4" "bdd87896" "1226ba28",
    "scripts/run_macro_news_pipeline.py": "d6a07253" "7d4916d4" "ce1bacd8" "1751286b" "f7356333" "5209c38f" "5718fba0" "2c3c61b2",
    "scripts/fetch_news_sentiment.py": "dfce1092" "f3986fd2" "abcb43e7" "e0de8f9d" "48d8a97d" "24adde64" "61b8cead" "92a9f001",
    "scripts/update_market_flow.py": "3f1b69f3" "c0e121df" "8ea49837" "4ae231a1" "b56b0029" "f41e9cd6" "b1ca28da" "d99313ac",
    "scripts/update_recent_portfolio_data.py": "449a93d3" "8afe6138" "96e4ac47" "4f2e1ef7" "539bb5c4" "27611290" "10918f2e" "2eb238ff",
}
CLI_HASHES = {
    "scripts/update_market_data.py": "7e197e853f0db830df6b67ea56c44f2999509e4e4d1bca92439ae284b8a8cd66",
    "scripts/fetch_financial_statements.py": "8003e3c7db2faf3392684dda03607acc6d2fa15f2ccae66524c021f91dba51da",
    "scripts/run_macro_news_pipeline.py": "9f2e7401ea6bcd2bae1b4582e977261820d5cc09447eeefc9fd06bb4755c1ed3",
    "scripts/fetch_news_sentiment.py": "aa8e384efbea8ae2fcf38f431cd92dd00306145b69029535cac80ba7178da465",
    "scripts/update_market_flow.py": "78adc17e621b40a2b27a7aa7754f447b81be54a5b171e16487e3b217f8b17af4",
    "scripts/update_recent_portfolio_data.py": "cd53d480239cb65ab71c6b56f03a822846b2dba32143e852c8b7dd3d59f4bef4",
}


def make_frame(dataset: str) -> pd.DataFrame:
    common = {
        "market": {
            "ticker": "AAA", "date": date(2026, 10, 21), "exchange": "HOSE",
            "open": 20.0, "high": 22.0, "low": 19.0, "close": 21.0, "volume": 1000,
            "as_of": datetime(2026, 10, 21, 10, tzinfo=UTC),
            "available_at": datetime(2026, 10, 21, 10, tzinfo=UTC), "source": "SSI",
            "price_scale": "VND_FULL", "adjusted": True, "rebuild_date": None,
        },
        "financials": {
            "symbol": "AAA", "endpoint": "income_statement", "period_type": "quarter",
            "fiscal_year": 2026, "fiscal_quarter": 3, "item_code": "revenue", "item_value": 1e13,
            "fiscal_period_end": date(2026, 9, 30), "source_publish_at": datetime(2026, 10, 1, tzinfo=UTC),
            "available_at": datetime(2026, 10, 1, tzinfo=UTC), "is_audited": False,
            "is_restated": False, "version": 1,
        },
        "news_live": {
            "symbol": "AAA", "title": "Tin tức", "publish_time": datetime(2026, 10, 21, 9, tzinfo=UTC),
            "sentiment_score": 0.5, "available_at": datetime(2026, 10, 21, 10, tzinfo=UTC),
            "url": "https://example.invalid/article", "source": "test",
            "fetched_at": datetime(2026, 10, 21, 10, tzinfo=UTC), "raw_timestamp": None,
            "payload_sha256": "a" * 64, "parser_version": "v1", "legacy_row": False,
        },
        "derivatives": {
            "time": date(2026, 10, 21), "ticker": "VN30F1M", "open": 1300.0,
            "high": 1310.0, "low": 1290.0, "close": 1305.0, "volume": 10,
            "as_of": datetime(2026, 10, 21, 15, 30, tzinfo=UTC),
            "available_at": datetime(2026, 10, 21, 16, tzinfo=UTC), "source": "SSI_MCP",
            "price_scale": "points", "adjusted": "provider_adjusted", "rebuild_date": date(2026, 10, 21),
            "volume_unit": "contracts", "historical_pit_verified": False,
        },
    }
    return pd.DataFrame([{key: common[dataset][key] for key in SCHEMAS[dataset]}])


def source_tree(path):
    return ast.parse((ROOT / path).read_bytes())


def assignment(tree, name):
    return next(node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))


def arrow_fields(node):
    fields = node.args[0].elts
    return tuple((ast.literal_eval(field.elts[0]), ast.unparse(field.elts[1]))
                 if isinstance(field, ast.Tuple)
                 else (ast.literal_eval(field.args[0]), ast.unparse(field.args[1])) for field in fields)


def test_p0_exact_six_source_bytes_mappings_and_plan_acceptance():
    package = json.loads((ROOT / ".ly_state/session/unified_data_pipeline_package_20261022.json").read_text(encoding="utf-8"))
    plan = (ROOT / ".ly_state/session/unified_data_pipeline_master_plan_20261022.md").read_text(encoding="utf-8")
    assert dict(quality.ENTRYPOINTS) == ENTRYPOINTS
    assert {row["path"] for row in package["deprecations"]} == set(ENTRYPOINTS)
    inventory = {row["path"]: row["sha256"] for row in package["source_files"]}
    for path, expected in SOURCE_HASHES.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
        assert inventory[path] == expected
        assert path in plan
    section5 = plan.split("## 5.", 1)[1].split("## 6.", 1)[0]
    section12 = plan.split("## 12.", 1)[1].split("## 13.", 1)[0]
    assert all(text in section5 for text in ("Unknown/missing rule status", "unverified", "15:30"))
    assert all(text in section12 for text in ("P0", "P1", "source hashes", "legacy DTO", "no mutation"))
    assert package["delivery"] == "plan_only" and package["runtime_implemented"] is False
    # External scheduled tasks/runbooks remain UNKNOWN; repository absence cannot prove absence.
    assert "Unknown external schedules/runbooks block deletion" in plan


@pytest.mark.parametrize("path", tuple(ENTRYPOINTS))
def test_p0_cli_flags_and_exit_ast_frozen(path):
    tree = source_tree(path)
    argv = [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument"]
    exits = [ast.unparse(n) for n in ast.walk(tree)
             if (isinstance(n, ast.Return) and isinstance(n.value, ast.Constant) and type(n.value.value) is int)
             or (isinstance(n, ast.Call) and ((isinstance(n.func, ast.Name) and n.func.id == "SystemExit")
                 or (isinstance(n.func, ast.Attribute) and n.func.attr == "exit")))]
    frozen = json.dumps({"argv": argv, "exits": exits}, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(frozen).hexdigest() == CLI_HASHES[path]
    assert exits
    if path.endswith("update_recent_portfolio_data.py"):
        assert not argv
        assert ast.literal_eval(assignment(tree, "SYMS")) == ["VNM", "VIC", "HPG", "TCB", "BID"]


def test_p0_producer_schema_constants_and_immutable_quality_schemas():
    market = source_tree("scripts/update_market_data.py")
    assert tuple(ast.literal_eval(assignment(market, "CANONICAL_COLUMNS"))) == EXPECTED_SCHEMAS["market"]
    assert ast.literal_eval(assignment(market, "PRICE_SCALE_LABEL")) == "VND"
    financial = source_tree("scripts/fetch_financial_statements.py")
    fields = arrow_fields(assignment(financial, "SCHEMA"))
    assert tuple(name for name, _ in fields) == EXPECTED_SCHEMAS["financials"]
    assert tuple(kind for _, kind in fields) == ("pa.string()", "pa.string()", "pa.string()", "pa.int64()", "pa.int64()", "pa.string()", "pa.float64()", "pa.date32()", "pa.timestamp('ns', tz='UTC')", "pa.timestamp('ns', tz='UTC')", "pa.bool_()", "pa.bool_()", "pa.int64()")
    assert ast.literal_eval(assignment(financial, "PRIMARY_KEY")) == ("symbol", "endpoint", "period_type", "fiscal_year", "fiscal_quarter", "item_code")
    news = source_tree("scripts/fetch_news_sentiment.py")
    fields = arrow_fields(assignment(news, "SCHEMA"))
    assert tuple(name for name, _ in fields) == EXPECTED_SCHEMAS["news_live"]
    assert tuple(kind for _, kind in fields) == ("pa.string()", "pa.string()", "pa.timestamp('us', tz='UTC')", "pa.float64()", "pa.timestamp('us', tz='UTC')", "pa.string()", "pa.string()", "pa.timestamp('us', tz='UTC')", "pa.string()", "pa.string()", "pa.string()", "pa.bool_()")
    validator = next(n for n in ast.walk(source_tree("src/omega/data/market_flow.py"))
                     if isinstance(n, ast.FunctionDef) and n.name == "_validate_derivatives")
    assert ast.literal_eval(assignment(validator, "columns")) == set(EXPECTED_SCHEMAS["derivatives"])
    for dataset, fields in EXPECTED_SCHEMAS.items():
        assert SCHEMAS[dataset] == fields
    with pytest.raises(TypeError):
        SCHEMAS["market"] = ()
    with pytest.raises(TypeError):
        quality.ENTRYPOINTS["scripts/unsafe.py"] = "market"


def test_p0_legacy_dto_ast_shape_not_stale_control_file_hash():
    expected = {
        "IngestDataRequest": [
            ("symbols", "List[str]", {"default_factory": "lambda: ['ALL']"}),
            ("sources", "List[Literal['vci', 'kbs', 'tcbs', 'macro', 'news']]", {"default_factory": "lambda: ['vci']"}),
            ("mode", "Optional[Literal['incremental', 'full_history', 'custom_range']]", {"default": "'incremental'"}),
            ("start_date", "Optional[str]", {"default": "None"}), ("end_date", "str", {"default": "'2023-12-31'"}),
            ("as_of_time", "Optional[str]", {"default": "None"}), ("dry_run", "bool", {"default": "False"}),
            ("no_refetch", "bool", {"default": "False"}), ("force_refresh", "bool", {"default": "False"}),
            ("max_concurrency", "Optional[int]", {"default": "None", "ge": "1", "le": "10"}),
        ],
        "PipelineRunRequest": [
            ("universe", "List[str]", {"default_factory": "lambda: ['FPT', 'HPG', 'MBB', 'MWG', 'DGC', 'VNM', 'TCB', 'PNJ']"}),
            ("start_date", "str", {"default": "'2023-01-01'"}), ("end_date", "str", {"default": "'2023-12-31'"}),
            ("as_of_time", "Optional[str]", {"default": "None"}),
            ("rebalance_frequency", "Literal['daily', 'weekly', 'monthly']", {"default": "'weekly'"}),
            ("initial_capital", "float", {"default": "1000000000.0", "ge": "10000000.0", "le": "1000000000000.0"}),
            ("slippage_bps", "float", {"default": "15.0", "ge": "0.0", "le": "1000.0"}),
            ("commission_bps", "float", {"default": "10.0", "ge": "0.0", "le": "1000.0"}),
            ("max_single_weight", "float", {"default": "0.15", "ge": "0.01", "le": "1.0"}),
            ("alpha_families", "List[Literal['MOMENTUM']]", {"default_factory": "lambda: ['MOMENTUM']"}),
            ("mode", "Literal['IN_PROCESS']", {"default": "'IN_PROCESS'"}),
        ],
    }
    for node in source_tree("src/omega/api/routes/control.py").body:
        if isinstance(node, ast.ClassDef) and node.name in expected:
            actual = [(n.target.id, ast.unparse(n.annotation),
                       {k.arg: ast.unparse(k.value) for k in n.value.keywords if k.arg != "description"})
                      for n in node.body if isinstance(n, ast.AnnAssign)]
            assert actual == expected.pop(node.name)
            assert [ast.unparse(base) for base in node.bases] == ["StrictRequest"]
    assert not expected


def test_p0_direct_import_identity_and_existing_safe_helpers():
    sanitizer = importlib.import_module("omega.data.sanitizer")
    assert quality.DataValidator is sanitizer.DataValidator
    for module_name in ("omega.data.validator", "omega.data.data_validator"):
        module = importlib.import_module(module_name)
        assert module.DataValidator is sanitizer.DataValidator
        assert module.ValidationIssue is sanitizer.ValidationIssue
    assert importlib.import_module("omega.data.data_quality").DataQualityChecker is sanitizer.DataQualityChecker
    market = importlib.import_module("scripts.update_market_data")
    assert market.build_symbol_exchange_map({"hsx": ["AAA"], "hnx": ["BBB"]}) == {"AAA": "HOSE", "BBB": "HNX"}
    assert callable(market.run_updater) and callable(market.read_canonical)
    news = importlib.import_module("scripts.fetch_news_sentiment")
    assert news.positive_int("1") == 1
    with pytest.raises(Exception):
        news.positive_int("0")
    assert news.score_sentiment("Tin trung lập") == 0.0
    assert callable(news.build_news_sentiment) and callable(news.migrate_news_sentiment_schema)
    # Never import scripts.update_recent_portfolio_data: top-level canonical writes.


def test_checker_keyword_only_api():
    params = inspect.signature(PipelineQualityChecker.check).parameters
    assert tuple(params) == ("self", "data", "dataset", "run_id", "stage_id", "source_hash", "config_hash", "input_hash", "decision_time", "raw_inputs", "links", "derived_inputs")
    assert all(params[key].kind == inspect.Parameter.KEYWORD_ONLY and params[key].default is None
               for key in tuple(params)[3:])


@pytest.mark.parametrize("dataset", DATASETS)
def test_supported_schema_yields_bounded_unverified_report(dataset):
    report = PipelineQualityChecker().check(make_frame(dataset), dataset, decision_time=NOW)
    assert report["dataset"] == dataset and report["row_count"] == report["partition_count"] == 1
    assert report["output_hash"] == report["input_hash"]
    assert report["pit_status"] == report["coverage_status"] == report["freshness_status"] == "unverified"
    assert report["status"] == "unknown"
    assert report["quarantine"]["required"] is False
    assert report["rule_statuses"] and "passed" not in report["rule_statuses"].values()
    assert len(report["examples"]) <= 20
    assert {"schema_version", "rule_version", "schema_fingerprint", "run_id", "stage_id", "source_hash", "config_hash", "date_bounds", "availability_bounds", "duplicate_count", "null_count", "non_finite_count", "warnings", "validated_at", "output_hash_validation"} <= report.keys()
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("dataset", [None, [], {}, 1, True, float("nan"), "secret-unsupported"])
def test_invalid_and_unsupported_dataset_types_never_crash_or_echo(dataset):
    report = PipelineQualityChecker().check(make_frame("market"), dataset)
    assert report["dataset"] == "unsupported" and report["status"] == "failed"
    assert "unsupported_schema" in report["blocking_rules"]
    assert "secret" not in repr(report)


@pytest.mark.parametrize("value", [None, [], "secret", True, {"secret": "value"}])
def test_malformed_input_fails_without_echo(value):
    report = PipelineQualityChecker().check(value, "market")
    assert "invalid_frame" in report["blocking_rules"]
    assert report["status"] == "failed" and report["output_hash"] is None
    assert "secret" not in repr(report)


@pytest.mark.parametrize("dataset", DATASETS)
def test_rejects_schema_drift_and_empty_output(dataset):
    frame = make_frame(dataset)
    variants = [frame.drop(columns=frame.columns[-1]), frame.assign(secret_extra="secret"),
                frame.rename(columns={frame.columns[-1]: "secret_renamed"}), frame.iloc[:, ::-1],
                pd.concat([frame, frame.iloc[:, :1]], axis=1)]
    for invalid in variants:
        report = PipelineQualityChecker().check(invalid, dataset)
        assert "schema_mismatch" in report["blocking_rules"]
        assert report["status"] == "failed" and "secret" not in repr(report)
    assert "unexpected_empty_output" in PipelineQualityChecker().check(frame.iloc[:0], dataset)["blocking_rules"]


def test_hash_binding_canonicalization_content_and_missing_provenance():
    checker = PipelineQualityChecker()
    frame = make_frame("market")
    unknown = checker.check(frame, "market")
    for name in ("source", "config"):
        assert any(name in rule and status == "unknown" for rule, status in unknown["rule_statuses"].items())
    digest = unknown["output_hash"]
    report = checker.check(frame, "market", source_hash="A" * 64, config_hash="B" * 64, input_hash=digest.upper())
    assert report["source_hash"] == "a" * 64 and report["config_hash"] == "b" * 64
    assert report["input_hash"] == report["output_hash"] == digest
    assert report["status"] == "unknown" and report["pit_status"] != "verified"
    assert checker.check(frame.set_axis([99]), "market")["output_hash"] == digest
    mismatched = checker.check(frame, "market", input_hash="0" * 64)
    assert "input_hash_mismatch" in mismatched["blocking_rules"]
    assert mismatched["input_hash"] == mismatched["output_hash"] == digest
    frame.loc[0, "volume"] += 1
    changed = checker.check(frame, "market", input_hash=digest)
    assert changed["output_hash"] != digest and "input_hash_mismatch" in changed["blocking_rules"]
    assert changed["schema_fingerprint"] == report["schema_fingerprint"]


@pytest.mark.parametrize("field", ["source_hash", "config_hash", "input_hash"])
def test_hash_metadata_rejects_noncanonical_shapes(field):
    for value in (True, [], {}, 1, "a" * 63, "g" * 64, "a" * 64 + "\n", "secret"):
        report = PipelineQualityChecker().check(make_frame("financials"), "financials", **{field: value})
        assert f"invalid_{field}" in report["blocking_rules"]
        assert "secret" not in repr(report)


def test_numeric_boundaries_and_small_vnd_prices_are_not_magnitude_rejected():
    checker = PipelineQualityChecker()
    for prices in ([1, 2, 1, 2], [1.0, 1.2, 0.9, 1.1], [20, 22, 19, 21]):
        frame = make_frame("market")
        frame[["open", "high", "low", "close"]] = [prices]
        assert "invalid_ohlc" not in checker.check(frame, "market")["blocking_rules"]
    for value in (0, -1, 1, 10**13, -10**13, 1e300, -1e300):
        frame = make_frame("financials")
        frame["item_value"] = pd.Series([value], dtype=object)
        assert "invalid_item_value" not in checker.check(frame, "financials")["blocking_rules"]
    for dataset, fields, rule in (("market", ("open", "high", "low", "close"), "invalid_ohlc"),
                                  ("derivatives", ("open", "high", "low", "close"), "invalid_derivative_price"),
                                  ("financials", ("item_value",), "invalid_item_value")):
        for field in fields:
            for value in (True, np.bool_(True), "1", None, float("nan"), float("inf"), float("-inf")):
                frame = make_frame(dataset).astype(object)
                frame.at[0, field] = value
                assert rule in checker.check(frame, dataset)["blocking_rules"], (dataset, field, value)


def test_volume_derivative_domain_limits_and_ohlc_consistency():
    checker = PipelineQualityChecker()
    for dataset, limit, rule in (("market", np.iinfo(np.int64).max, "invalid_volume"),
                                 ("derivatives", 10**12, "invalid_derivative_volume")):
        frame = make_frame(dataset).astype(object)
        frame.at[0, "volume"] = int(limit)
        assert rule not in checker.check(frame, dataset)["blocking_rules"]
        for value in (-1, True, 1.5, float("inf"), int(limit) + 1):
            frame.at[0, "volume"] = value
            assert rule in checker.check(frame, dataset)["blocking_rules"]
    frame = make_frame("derivatives")
    frame[["open", "high", "low", "close"]] = [[10**7] * 4]
    assert "invalid_derivative_price" not in checker.check(frame, "derivatives")["blocking_rules"]
    frame["high"] = 10**7 + 1
    assert "invalid_derivative_price" in checker.check(frame, "derivatives")["blocking_rules"]
    for dataset in ("market", "derivatives"):
        frame = make_frame(dataset)
        frame["high"] = 1
        assert checker.check(frame, dataset)["status"] == "failed"


def test_upcom_legacy_vnd_and_no_silent_unit_conversion():
    frame = make_frame("market")
    frame["exchange"] = "UPCOM"
    frame["price_scale"] = "VND"
    before = frame.copy(deep=True)
    report = PipelineQualityChecker().check(frame, "market")
    assert "unknown_exchange" not in report["blocking_rules"]
    assert "unsupported_price_scale" not in report["blocking_rules"]
    assert "legacy_vnd_scale" in report["warnings"]
    pd.testing.assert_frame_equal(frame, before)
    frame["price_scale"] = "VND_FULL"
    assert "legacy_vnd_scale" not in PipelineQualityChecker().check(frame, "market")["warnings"]
    frame["price_scale"] = "thousand_vnd"
    assert "unsupported_price_scale" in PipelineQualityChecker().check(frame, "market")["blocking_rules"]


def test_cutoff_is_inclusive_and_late_availability_violates_pit():
    checker = PipelineQualityChecker()
    frame = make_frame("news_live")
    frame["available_at"] = NOW
    assert checker.check(frame, "news_live", decision_time=NOW)["pit_status"] == "unverified"
    frame["available_at"] = NOW + timedelta(microseconds=1)
    report = checker.check(frame, "news_live", decision_time=NOW)
    assert report["pit_status"] == "violated" and "pit_after_decision_time" in report["blocking_rules"]
    frame["available_at"] = NOW.astimezone(timezone(timedelta(hours=7)))
    assert checker.check(frame, "news_live", decision_time=NOW)["pit_status"] == "unverified"
    for invalid in (datetime(2026, 10, 22), "secret", True, [], float("nan")):
        report = checker.check(frame, "news_live", decision_time=invalid)
        assert "invalid_decision_time" in report["blocking_rules"]
        assert "secret" not in repr(report)


@pytest.mark.parametrize("dataset,event", [("market", "as_of"), ("financials", "source_publish_at"), ("news_live", "publish_time"), ("derivatives", "as_of")])
def test_existing_nonnull_temporal_values_must_be_aware(dataset, event):
    for field in (event, "available_at"):
        for value in ("secret", "2026-10-21T10:00:00", datetime(2026, 10, 21, 10)):
            frame = make_frame(dataset).astype(object)
            frame.at[0, field] = value
            report = PipelineQualityChecker().check(frame, dataset)
            assert "pit_temporal_violation" in report["blocking_rules"]
            assert report["pit_status"] == "violated" and "secret" not in repr(report)


def test_financial_missing_publication_is_unknown_not_temporal_violation():
    frame = make_frame("financials").astype(object)
    for missing in (None, pd.NaT, float("nan")):
        frame.at[0, "source_publish_at"] = missing
        report = PipelineQualityChecker().check(frame, "financials", decision_time=NOW)
        assert report["pit_status"] == "unverified" and report["status"] == "unknown"
        assert "pit_temporal_violation" not in report["blocking_rules"]


def test_live_fetched_time_required_aware_and_between_publication_availability():
    for value in (None, pd.NaT, "secret", datetime(2026, 10, 21, 10),
                  datetime(2026, 10, 21, 8, tzinfo=UTC), datetime(2026, 10, 21, 11, tzinfo=UTC)):
        frame = make_frame("news_live").astype(object)
        frame.at[0, "fetched_at"] = value
        report = PipelineQualityChecker().check(frame, "news_live")
        assert report["status"] == "failed" and "secret" not in repr(report)
    frame = make_frame("news_live")
    frame["publish_time"] = frame["fetched_at"] = frame["available_at"]
    assert PipelineQualityChecker().check(frame, "news_live")["status"] == "unknown"


def test_news_revision_order_binds_source_url_symbol_not_input_row_order():
    first = make_frame("news_live")
    first["publish_time"] = datetime(2026, 10, 21, 8, tzinfo=UTC)
    first["fetched_at"] = datetime(2026, 10, 21, 9, tzinfo=UTC)
    first["available_at"] = datetime(2026, 10, 21, 11, tzinfo=UTC)
    second = first.copy()
    second["payload_sha256"] = "b" * 64
    second["fetched_at"] = second["available_at"] = datetime(2026, 10, 21, 10, tzinfo=UTC)
    for parts in ((first, second), (second, first)):
        report = PipelineQualityChecker().check(pd.concat(parts, ignore_index=True), "news_live")
        assert "revision_availability_backwards" in report["blocking_rules"]
    for field, value in (("source", "other"), ("symbol", "BBB"), ("url", "https://example.invalid/other")):
        independent = second.copy()
        independent[field] = value
        report = PipelineQualityChecker().check(pd.concat([first, independent], ignore_index=True), "news_live")
        assert "revision_availability_backwards" not in report["blocking_rules"]


def test_forged_historical_derivative_provenance_and_naive_timestamps_block():
    for forged in (True, "false", 0, 1, None):
        frame = make_frame("derivatives").astype(object)
        frame.at[0, "historical_pit_verified"] = forged
        report = PipelineQualityChecker().check(frame, "derivatives")
        assert "forged_pit_provenance" in report["blocking_rules"]
        assert report["pit_status"] != "verified"
    for dataset in DATASETS:
        frame = make_frame(dataset)
        frame.attrs.update(pit_verified=True, historical_pit_verified=True, source_verified=True)
        report = PipelineQualityChecker().check(frame, dataset, source_hash="a" * 64, config_hash="b" * 64)
        assert report["status"] != "passed" and report["pit_status"] != "verified"


def test_financial_boolean_integer_invalid_revision_and_duplicate_key_block():
    checker = PipelineQualityChecker()
    for field, value in (("fiscal_year", True), ("fiscal_quarter", True), ("version", True), ("version", 0),
                         ("is_audited", 1), ("is_restated", "false")):
        frame = make_frame("financials").astype(object)
        frame.at[0, field] = value
        assert checker.check(frame, "financials")["status"] == "failed"
    frame = pd.concat([make_frame("financials")] * 3, ignore_index=True)
    report = checker.check(frame, "financials")
    assert report["duplicate_count"] == 2 and "duplicate_key" in report["blocking_rules"]
    frame = make_frame("financials")
    frame["period_type"], frame["fiscal_quarter"], frame["fiscal_period_end"] = "year", 0, date(2026, 12, 31)
    frame["source_publish_at"] = frame["available_at"] = datetime(2027, 1, 15, tzinfo=UTC)
    assert checker.check(frame, "financials")["status"] == "unknown"
    frame["period_type"] = "quarter"
    assert checker.check(frame, "financials")["status"] == "failed"


@pytest.mark.parametrize("dataset", DATASETS)
def test_per_domain_duplicate_keys_ignore_nonkey_revisions(dataset):
    frame = pd.concat([make_frame(dataset)] * 2, ignore_index=True)
    if dataset == "financials":
        frame.loc[1, "version"] = 2
    elif dataset == "news_live":
        frame.loc[1, "title"] = "Revision title"
    else:
        frame.loc[1, "volume"] += 1
    report = PipelineQualityChecker().check(frame, dataset)
    assert report["duplicate_count"] == 1 and "duplicate_key" in report["blocking_rules"]


@pytest.mark.parametrize("day,rule", [(date(2014, 12, 31), "unsupported_calendar_year"),
                                     (date(2028, 1, 3), "unsupported_calendar_year"),
                                     (date(2026, 10, 24), "non_trading_market_date"),
                                     (date(2026, 1, 1), "non_trading_market_date")])
def test_market_calendar_fails_closed_for_year_weekend_holiday(day, rule):
    frame = make_frame("market")
    frame["date"] = day
    assert rule in PipelineQualityChecker().check(frame, "market")["blocking_rules"]


def test_1530_ict_is_not_source_readiness_or_verified_provenance():
    frame = make_frame("market")
    dispatch = datetime(2026, 10, 21, 15, 30, tzinfo=timezone(timedelta(hours=7)))
    frame["as_of"] = dispatch
    frame["available_at"] = dispatch + timedelta(minutes=30)
    before = PipelineQualityChecker().check(frame, "market", decision_time=dispatch)
    assert before["pit_status"] == "violated" and "pit_after_decision_time" in before["blocking_rules"]
    frame["available_at"] = dispatch
    at = PipelineQualityChecker().check(frame, "market", decision_time=dispatch)
    assert at["pit_status"] == "unverified" and at["status"] == "unknown"


@pytest.mark.parametrize("dataset", DATASETS)
def test_all_fields_adversarial_types_do_not_crash_mutate_or_verify(dataset):
    checker = PipelineQualityChecker()
    for field in EXPECTED_SCHEMAS[dataset]:
        for bad in (None, [], {"nested": ["secret"]}, "secret", float("nan"), float("inf"), float("-inf"), True):
            frame = make_frame(dataset).astype(object)
            frame.at[0, field] = copy.deepcopy(bad)
            before = copy.deepcopy(frame.to_dict("records"))
            report = checker.check(frame, dataset)
            assert report["status"] in ("failed", "unknown") and report["pit_status"] != "verified", (dataset, field, bad)
            assert repr(frame.to_dict("records")) == repr(before), (dataset, field, bad)
            assert "secret" not in repr(report), (dataset, field, bad)
            assert len(report["examples"]) <= 20


@pytest.mark.parametrize("raises", [False, True])
def test_authoritative_validator_receives_detached_values_and_errors_redacted(monkeypatch, raises):
    calls = []
    def validate_rows(self, rows, **kwargs):
        calls.append(rows)
        rows[0]["close"] = -999
        rows[0]["secret"] = {"nested": ["changed"]}
        if raises:
            raise ValueError("secret https://user:password@example.invalid/?token=secret")
        return []
    monkeypatch.setattr(quality.DataValidator, "validate_rows", validate_rows)
    frame = make_frame("market")
    before = frame.copy(deep=True)
    report = PipelineQualityChecker().check(frame, "market")
    assert calls
    pd.testing.assert_frame_equal(frame, before)
    if raises:
        assert report["status"] == "failed"
    assert "secret" not in repr(report) and "password" not in repr(report)


@pytest.mark.parametrize("bound", ["rows", "columns", "cell", "total"])
def test_resource_bounds_reject_before_content_hashing(monkeypatch, bound):
    assert (quality.MAX_ROWS, quality.MAX_COLUMNS, quality.MAX_CELL_BYTES, quality.MAX_TOTAL_BYTES) == (100000, 64, 65536, 16 * 1024 * 1024)
    frames = {
        "rows": lambda: pd.DataFrame({"x": np.zeros(100001, dtype=np.int8)}),
        "columns": lambda: pd.DataFrame([[0] * 65], columns=[f"c{i}" for i in range(65)]),
        "cell": lambda: pd.DataFrame({"title": ["é" * 32769]}),
        "total": lambda: pd.DataFrame({"title": ["x" * 65536] * 257}),
    }
    def forbidden_hash(frame):
        pytest.fail("oversize input reached content hashing")
    monkeypatch.setattr(quality, "_content_hash", forbidden_hash)
    report = PipelineQualityChecker().check(frames[bound](), "news_live")
    assert report["status"] == "failed" and report["quarantine"]["required"] is True
    assert report["input_hash"] is report["output_hash"] is None


def test_diagnostics_are_static_redacted_bounded_and_count_nonfinite():
    frame = pd.concat([make_frame("market")] * 30, ignore_index=True).astype(object)
    frame["close"] = float("inf")
    frame["source"] = "https://user:password@example.invalid/?token=secret"
    report = PipelineQualityChecker().check(frame, "market", run_id="secret invalid", stage_id="../secret", source_hash="secret")
    assert len(report["examples"]) <= 20 and report["non_finite_count"] == 30
    assert report["status"] == "failed" and report["quarantine"]["required"] is True
    assert report["run_id"] is report["stage_id"] is report["source_hash"] is None
    assert all(text not in repr(report) for text in ("secret", "password", "example.invalid", "https://"))
    assert "invalid_run_id" in report["blocking_rules"] and "invalid_source_hash" in report["blocking_rules"]


def test_unknown_domain_stays_unsupported():
    report = PipelineQualityChecker().check(make_frame("news_live"), "unsupported")
    assert report["dataset"] == "unsupported" and report["status"] == "failed"
    assert "unsupported_schema" in report["blocking_rules"] and report["pit_status"] != "verified"


def test_historical_manifest_binding_and_partial_cases():
    rules = []
    metadata = pd.DataFrame([{"sha256": "a" * 64}], columns=quality._HISTORICAL_COLUMNS)
    assert quality._historical_bundle(metadata, NOW, rules.append).empty
    assert rules == ["historical_bundle_invalid"]
    for bad in (b"{}", b'{"x":1,"x":2}', b'{"x":NaN}', b"\\xff"):
        rules.clear()
        assert quality._historical_bundle({"manifest": bad, "shards": {}}, NOW, rules.append).empty
        assert rules == ["historical_bundle_invalid"]
    rules.clear()
    assert quality._historical_bundle({"manifest": b"x" * (8 * 1024 * 1024 + 1), "shards": {}}, NOW, rules.append).empty
    assert rules == ["historical_bundle_bounds"]
    rules.clear()
    assert quality._historical_bundle({"manifest": b"{}", "shards": {"../x.parquet": b"x"}}, NOW, rules.append).empty
    assert rules == ["historical_bundle_bounds"]
    rules.clear()
    assert quality._historical_bundle({"manifest": b"{}", "shards": {}}, NOW, rules.append).empty
    assert rules == ["historical_bundle_invalid"]


def historical_quality_bundle():
    import pyarrow as pa
    import pyarrow.parquet as pq
    from omega.data.macro_news_pipeline import CAFEF_VERSION, SCHEMA as RAW_SCHEMA, _record
    from omega.data.news_aggregator import BEARISH_KEYWORDS, BULLISH_KEYWORDS

    lower = datetime(2016, 1, 1, tzinfo=UTC)
    upper = datetime(2026, 10, 22, tzinfo=UTC)
    raw_record = _record("cafef_historical", "CafeF", "cafef_historical", "lãi tăng", None, "https://cafef.vn/a-188160101000000000.chn", lower, lower, origin_ticker="AAA", origin_exchange="HSX", raw_timestamp="x")
    raw_record["published_at"] = lower - timedelta(hours=7)
    from omega.data.macro_news_pipeline import _hash
    raw_record["payload_sha256"] = _hash({"source_id": "cafef_historical", "title": raw_record["title"], "summary": raw_record["summary"], "url": raw_record["url"], "published_at": raw_record["published_at"], "raw_timestamp": "x"})
    raw_record["available_at"] = lower
    raw_record["adapter_version"] = CAFEF_VERSION
    raw = pa.Table.from_pylist([raw_record], schema=pa.schema([(name, pa.null() if raw_record.get(name) is None else pa.scalar(raw_record[name]).type) for name in RAW_SCHEMA]))
    projected = pa.Table.from_pylist([{"symbol": "AAA", "title": "lãi tăng", "publish_time": raw_record["published_at"], "sentiment_score": 1.0, "available_at": lower, "url": raw_record["canonical_url"], "source": "CafeF", "fetched_at": lower, "raw_timestamp": "x", "payload_sha256": raw_record["payload_sha256"], "parser_version": CAFEF_VERSION, "legacy_row": False}], schema=pa.schema([("symbol", pa.string()), ("title", pa.string()), ("publish_time", pa.timestamp("us", tz="UTC")), ("sentiment_score", pa.float64()), ("available_at", pa.timestamp("us", tz="UTC")), ("url", pa.string()), pa.field("source", pa.string(), nullable=False), pa.field("fetched_at", pa.timestamp("us", tz="UTC"), nullable=False), ("raw_timestamp", pa.string()), pa.field("payload_sha256", pa.string(), nullable=False), pa.field("parser_version", pa.string(), nullable=False), pa.field("legacy_row", pa.bool_(), nullable=False)]))
    def parquet(table):
        out = __import__("io").BytesIO(); pq.write_table(table, out); return out.getvalue()
    pair = {"AAA-HSX-0001-raw.parquet": parquet(raw), "AAA-HSX-0001-v10.parquet": parquet(projected)}
    entries = []
    for name, content in pair.items():
        table = pq.read_table(__import__("io").BytesIO(content))
        entries.append({"path": name, "durable": True, "rows": table.num_rows, "sha256": hashlib.sha256(content).hexdigest(), "schema_sha256": hashlib.sha256(table.schema.serialize().to_pybytes()).hexdigest()})
    manifest = {"schema_version": 2, "status": "results_only", "purpose": "collection_not_investability", "pit_verified": False, "full_history_verified": False, "failures": [], "shard_count": 2, "start": "2016-01-01", "end": "2026-10-21", "as_of": upper.isoformat(), "publication_start": (lower - timedelta(hours=7)).isoformat(), "publication_end": (datetime(2026, 10, 21, 17, tzinfo=UTC)).isoformat(), "universe_id": "u", "universe_version": "v", "universe_sha256": "a" * 64, "universe_generated_at": lower.isoformat(), "cafef_version": CAFEF_VERSION, "scorer_version": "title-substring-clipped-v1", "members": [["AAA", "HSX"]], "cohort_member_count": 1, "shards": entries, "symbols": [{"symbol": "AAA", "exchange": "HSX", "status": "results_only", "pages": 1, "rows": 1, "terminal_reason": "provider_results_only", "full_history_verified": False}]}
    manifest.update(start="2016-01-01", end="2026-10-22", as_of=upper.isoformat(), publication_end=upper.isoformat(),
                    publication_start=(lower - timedelta(hours=7)).isoformat(),
                    universe_id="u", universe_version="v", universe_sha256="a" * 64,
                    universe_generated_at=lower.isoformat(), cafef_version=CAFEF_VERSION,
                    scorer_version="title-substring-clipped-v1",
                    scorer_lexicon_sha256=hashlib.sha256(json.dumps({"bullish": sorted(BULLISH_KEYWORDS), "bearish": sorted(BEARISH_KEYWORDS)}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest())
    data = {"manifest": json.dumps(manifest).encode(), "shards": pair}
    return data


def test_historical_bundle_binds_parquet_bytes_and_partial_outcomes():
    data = historical_quality_bundle()
    before = copy.deepcopy(data)
    report = PipelineQualityChecker().check(data, "news_historical", decision_time=NOW)
    assert report["status"] == "unknown", report
    assert report["pit_status"] == "unverified" and report["row_count"] == 2
    assert data == before
    changed = copy.deepcopy(data)
    manifest = json.loads(changed["manifest"])
    manifest["cohort_rationale"] = "different internally-consistent context"
    changed["manifest"] = json.dumps(manifest).encode()
    assert PipelineQualityChecker().check(changed, "news_historical")["input_hash"] != report["input_hash"]
    changed["shards"]["AAA-HSX-0001-raw.parquet"] = b"tampered"
    assert PipelineQualityChecker().check(changed, "news_historical")["status"] == "failed"


def test_historical_manifest_fault_matrix_and_duplicate_pages():
    data = historical_quality_bundle()
    original = json.loads(data["manifest"])
    mutations = [("status", "running"), ("status", "incomplete"), ("pit_verified", True),
                 ("full_history_verified", True), ("failures", ["secret"]), ("failures", None),
                 ("cohort_member_count", 2), ("shard_count", True), ("cafef_version", "other"),
                 ("scorer_version", "other"), ("scorer_lexicon_sha256", "0" * 64),
                 ("universe_sha256", "bad"), ("publication_end", "bad"),
                 ("members", [["AAA", "HSX"], ["AAA", "HSX"]]), ("symbols", []),
                 ("as_of", "2010-01-01T00:00:00Z")]
    for field, value in mutations:
        manifest = copy.deepcopy(original)
        manifest[field] = value
        report = PipelineQualityChecker().check(dict(manifest=json.dumps(manifest).encode(), shards=data["shards"]), "news_historical", decision_time=NOW)
        assert report["status"] == "failed", (field, report)
        assert "secret" not in repr(report)
    for field, value in (("rows", 100001), ("durable", False), ("sha256", "0" * 64), ("schema_sha256", "0" * 64), ("path", "../secret.parquet")):
        manifest = copy.deepcopy(original)
        manifest["shards"][0][field] = value
        assert PipelineQualityChecker().check(dict(manifest=json.dumps(manifest).encode(), shards=data["shards"]), "news_historical")["status"] == "failed"
    manifest = copy.deepcopy(original)
    manifest["shards"].append(copy.deepcopy(manifest["shards"][0]))
    assert PipelineQualityChecker().check(dict(manifest=json.dumps(manifest).encode(), shards=data["shards"]), "news_historical")["status"] == "failed"
    assert PipelineQualityChecker().check(dict(manifest=data["manifest"], shards={}), "news_historical")["status"] == "failed"


def test_historical_empty_terminal_collection_remains_unverified():
    import io
    import pyarrow.parquet as pq
    data = historical_quality_bundle()
    manifest = json.loads(data["manifest"])
    for entry in manifest["shards"]:
        table = pq.read_table(io.BytesIO(data["shards"][entry["path"]])).slice(0, 0)
        stream = io.BytesIO()
        pq.write_table(table, stream)
        content = stream.getvalue()
        data["shards"][entry["path"]] = content
        entry.update(rows=0, sha256=hashlib.sha256(content).hexdigest())
    manifest["status"] = "incomplete"
    manifest["symbols"][0].update(status="incomplete", rows=0, terminal_reason="no_articles_observed_history_unverified")
    data["manifest"] = json.dumps(manifest).encode()
    report = PipelineQualityChecker().check(data, "news_historical", decision_time=NOW)
    assert report["status"] == "unknown", report
    assert "historical_partial_collection" in report["warnings"] and report["pit_status"] == "unverified"


def test_historical_decoder_fault_and_input_bounds_are_redacted(monkeypatch):
    data = historical_quality_bundle()
    before = copy.deepcopy(data)
    def fail(*args, **kwargs):
        raise ValueError("secret https://user:password@example.invalid")
    monkeypatch.setattr(quality.pq, "ParquetFile", fail)
    report = PipelineQualityChecker().check(data, "news_historical")
    assert report["status"] == "failed" and "secret" not in repr(report)
    assert data == before
    for manifest in (b"[" * 65 + b"]" * 65, b"\xef\xbb\xbf{}", b'{"x":Infinity}'):
        assert PipelineQualityChecker().check(dict(manifest=manifest, shards={}), "news_historical")["status"] == "failed"


@pytest.mark.parametrize("fault", ["raw_universe", "source", "projection_value", "projection_schema", "availability", "duplicate_page"])
def test_historical_rehashed_semantic_corruption_is_rejected(fault):
    import io
    import pyarrow as pa
    import pyarrow.parquet as pq

    data = historical_quality_bundle()
    manifest = json.loads(data["manifest"])
    if fault == "duplicate_page":
        for entry in list(manifest["shards"]):
            duplicate = dict(entry, path=entry["path"].replace("0001", "0002"))
            data["shards"][duplicate["path"]] = data["shards"][entry["path"]]
            manifest["shards"].append(duplicate)
        manifest["shard_count"] = 4
        manifest["symbols"][0].update(pages=2, rows=2)
    else:
        entry = manifest["shards"][0 if fault in {"raw_universe", "source"} else 1]
        table = pq.ParquetFile(io.BytesIO(data["shards"][entry["path"]])).read()
        rows = table.to_pylist()
        schema = table.schema
        if fault == "raw_universe":
            rows[0]["universe_id"] = "forged"
            schema = schema.set(schema.get_field_index("universe_id"), pa.field("universe_id", pa.string()))
        elif fault == "source":
            rows[0]["source_id"] = "other"
        elif fault == "projection_value":
            rows[0]["sentiment_score"] = 0.0
        elif fault == "projection_schema":
            schema = schema.set(schema.get_field_index("sentiment_score"), pa.field("sentiment_score", pa.float32()))
        else:
            rows[0]["available_at"] = rows[0]["publish_time"]
        changed = pa.Table.from_pylist(rows, schema=schema)
        stream = io.BytesIO()
        pq.write_table(changed, stream)
        data["shards"][entry["path"]] = stream.getvalue()
        entry.update(sha256=hashlib.sha256(stream.getvalue()).hexdigest(),
                     schema_sha256=hashlib.sha256(changed.schema.serialize().to_pybytes()).hexdigest())
    data["manifest"] = json.dumps(manifest).encode()
    before = copy.deepcopy(data)
    report = PipelineQualityChecker().check(data, "news_historical", decision_time=NOW)
    assert report["status"] == "failed"
    assert report["pit_status"] != "verified" and data == before


@pytest.mark.parametrize("limit", ["rows", "decoded_bytes"])
def test_historical_aggregate_bounds_precede_parquet_decode(monkeypatch, limit):
    data = historical_quality_bundle()
    from types import SimpleNamespace
    real = quality.pq.ParquetFile
    opened = []
    if limit == "rows":
        manifest = json.loads(data["manifest"])
        for entry in manifest["shards"]:
            entry["rows"] = 2
        data["manifest"] = json.dumps(manifest).encode()
        monkeypatch.setattr(quality, "MAX_ROWS", 1)
    else:
        monkeypatch.setattr(quality, "_HIST_TOTAL_MAX", len(data["manifest"]) + sum(map(len, data["shards"].values())) + 1)
    class MetadataOnly:
        def __init__(self, *args, **kwargs):
            opened.append(True)
            self.file = real(*args, **kwargs)
            md = self.file.metadata
            self.metadata = SimpleNamespace(num_rows=2 if limit == "rows" else md.num_rows,
                serialized_size=md.serialized_size, num_row_groups=1,
                row_group=lambda i: SimpleNamespace(total_byte_size=quality._HIST_SHARD_MAX))
            self.schema_arrow = self.file.schema_arrow
        def read(self):
            pytest.fail("aggregate bound reached Parquet decoding")
    monkeypatch.setattr(quality.pq, "ParquetFile", MetadataOnly)
    assert PipelineQualityChecker().check(data, "news_historical")["status"] == "failed"
    assert opened == [True]


def macro_quality_frames():
    from omega.data.macro_news_pipeline import SCHEMA, _record

    rows = [_record("fixture", "Fixture", "rss", f"Report {i}", None,
                    f"https://example.invalid/{i}", NOW - timedelta(hours=4 - i),
                    NOW - timedelta(hours=2 - i)) for i in range(2)]
    raw = pd.DataFrame(rows, columns=SCHEMA)
    output = dict(news_id="derived-1", extraction_id="extract-1", extracted_at=NOW,
                  published_at=raw.iloc[1]["published_at"], available_at=NOW, title="Reports",
                  sentiment_score=0.5, polarity="BULLISH", category="macro", impact="medium",
                  narrative="Offline narrative", fingerprint="b" * 64)
    derived = pd.DataFrame([output], columns=quality._DERIVED_COLUMNS)
    links = []
    for i, row in enumerate(rows):
        link = {key: row[key] for key in ("raw_record_id", "source_id", "revision_id", "provenance_id", "universe_id", "universe_version", "universe_sha256")}
        link.update(link_id=f"link-{i}", news_id=output["news_id"], extraction_id=output["extraction_id"],
                    extracted_at=NOW, available_at=NOW, fingerprint=output["fingerprint"])
        links.append(link)
    return raw, derived, pd.DataFrame(links, columns=quality._LINK_COLUMNS)


@pytest.mark.parametrize("dataset", ["macro_news_llm", "news_links"])
def test_macro_bound_outputs_and_links_valid_but_pit_unverified(dataset):
    raw, derived, links = macro_quality_frames()
    before = [item.copy(deep=True) for item in (raw, derived, links)]
    kwargs = dict(raw_inputs=raw, decision_time=NOW)
    kwargs.update(links=links) if dataset == "macro_news_llm" else kwargs.update(derived_inputs=derived)
    report = PipelineQualityChecker().check(derived if dataset == "macro_news_llm" else links, dataset, **kwargs)
    assert report["status"] == "unknown", report
    assert report["pit_status"] == "unverified"
    for frame, original in zip((raw, derived, links), before):
        pd.testing.assert_frame_equal(frame, original)


def test_macro_maximum_input_availability_and_extraction_boundaries():
    raw, derived, links = macro_quality_frames()
    checker = PipelineQualityChecker()
    for field in ("available_at", "extracted_at"):
        early = derived.copy(deep=True)
        early.at[0, field] = raw.iloc[0]["available_at"]
        report = checker.check(early, "macro_news_llm", raw_inputs=raw, links=links, decision_time=NOW)
        assert "derived_time_invalid" in report["blocking_rules"], (field, report)
    for field in ("available_at", "extracted_at"):
        early = links.copy(deep=True)
        early.at[1, field] = raw.iloc[0]["available_at"]
        assert checker.check(early, "news_links", raw_inputs=raw, derived_inputs=derived, decision_time=NOW)["status"] == "failed"
    assert checker.check(derived, "macro_news_llm", raw_inputs=raw, links=links, decision_time=NOW - timedelta(microseconds=1))["status"] == "failed"
    ict = timezone(timedelta(hours=7))
    cutoff = datetime(2026, 10, 23, 15, 30, tzinfo=ict)
    derived["extracted_at"] = derived["available_at"] = cutoff
    links["extracted_at"] = links["available_at"] = cutoff
    assert checker.check(derived, "macro_news_llm", raw_inputs=raw, links=links, decision_time=cutoff)["status"] == "unknown"


def test_macro_reference_revision_source_universe_and_extraction_mismatches():
    raw, derived, links = macro_quality_frames()
    for field in ("raw_record_id", "news_id", "source_id", "revision_id", "provenance_id", "universe_id", "universe_version", "universe_sha256", "extraction_id", "fingerprint"):
        changed = links.copy(deep=True)
        changed.at[0, field] = "mismatch"
        report = PipelineQualityChecker().check(derived, "macro_news_llm", raw_inputs=raw, links=changed, decision_time=NOW)
        assert report["status"] == "failed", (field, report)
    for changed in (links.iloc[:0], pd.concat([links, links]), links.assign(news_id="orphan")):
        assert PipelineQualityChecker().check(derived, "macro_news_llm", raw_inputs=raw, links=changed)["status"] == "failed"
    broken_raw = raw.copy(deep=True)
    broken_raw.at[0, "content_hash"] = "0" * 64
    assert PipelineQualityChecker().check(derived, "macro_news_llm", raw_inputs=broken_raw, links=links)["status"] == "failed"


def test_macro_all_input_fields_fault_matrix_nonmutation_and_redaction():
    raw, derived, links = macro_quality_frames()
    for which, original in enumerate((raw, derived, links)):
        for field in original.columns:
            for bad in (None, [], {}, "secret", float("nan"), float("inf"), float("-inf"), True, -1, 10**20):
                frames = [raw.copy(deep=True), derived.copy(deep=True), links.copy(deep=True)]
                frames[which] = frames[which].astype(object)
                frames[which].at[0, field] = copy.deepcopy(bad)
                before = repr([item.to_dict("records") for item in frames])
                report = PipelineQualityChecker().check(frames[1], "macro_news_llm", raw_inputs=frames[0], links=frames[2], decision_time=NOW)
                assert report["status"] in {"unknown", "failed"} and report["pit_status"] != "verified"
                assert "secret" not in repr(report)
                assert repr([item.to_dict("records") for item in frames]) == before


def test_macro_auxiliary_bounds_precede_hash_and_validation(monkeypatch):
    raw, derived, links = macro_quality_frames()
    def forbidden(*args, **kwargs):
        pytest.fail("unbounded dependency reached hashing")
    monkeypatch.setattr(quality, "_content_hash", forbidden)
    for bad in ([], pd.concat([raw] * 50001, ignore_index=True), pd.DataFrame({"x": ["x" * 65537]})):
        report = PipelineQualityChecker().check(derived, "macro_news_llm", raw_inputs=bad, links=links)
        assert report["status"] == "failed" and report["output_hash"] is None


def test_macro_dependency_hash_binds_all_inputs():
    raw, derived, links = macro_quality_frames()
    checker = PipelineQualityChecker()
    digest = checker.check(derived, "macro_news_llm", raw_inputs=raw, links=links)["input_hash"]
    changed = links.copy(deep=True)
    changed.at[0, "source_id"] = "other"
    report = checker.check(derived, "macro_news_llm", raw_inputs=raw, links=changed, input_hash=digest)
    assert report["input_hash"] != digest and "input_hash_mismatch" in report["blocking_rules"]
    assert checker.check(derived, "macro_news_llm", raw_inputs=raw)["status"] == "failed"
    assert checker.check(links, "news_links", raw_inputs=raw)["status"] == "failed"


def test_macro_validator_fault_is_redacted_and_caller_detached(monkeypatch):
    from omega.data.macro_news_pipeline import MacroNewsPipeline
    raw, derived, links = macro_quality_frames()
    before = raw.copy(deep=True)
    def fail(frame):
        frame.at[0, "title"] = "changed"
        raise ValueError("secret https://user:password@example.invalid")
    monkeypatch.setattr(MacroNewsPipeline, "_validate", fail)
    report = PipelineQualityChecker().check(derived, "macro_news_llm", raw_inputs=raw, links=links)
    assert "derived_validator_error" in report["blocking_rules"]
    assert all(value not in repr(report) for value in ("secret", "password", "example.invalid"))
    pd.testing.assert_frame_equal(raw, before)


def test_macro_raw_delegates_identity_validation_without_mutation():
    from omega.data.macro_news_pipeline import SCHEMA, _record

    record = _record("fixture", "Fixture", "rss", "Offline report", None,
                     "https://example.invalid/report", NOW - timedelta(hours=2), NOW)
    frame = pd.DataFrame([record], columns=SCHEMA)
    before = frame.copy(deep=True)
    report = PipelineQualityChecker().check(frame, "macro_news", decision_time=NOW)
    assert report["status"] == "unknown" and "domain_validator_error" not in report["blocking_rules"]
    pd.testing.assert_frame_equal(frame, before)
    frame["content_hash"] = "0" * 64
    assert "domain_validator_error" in PipelineQualityChecker().check(frame, "macro_news")["blocking_rules"]


@pytest.mark.parametrize("kind", ["foreign", "proprietary"])
def test_flow_kinds_reuse_partition_validation_and_preserve_unverified_pit(kind):
    day = date(2026, 10, 21)
    fields = quality.FOREIGN_FLOW_COLUMNS if kind == "foreign" else quality.PROP_FLOW_COLUMNS
    row = {column: (day.isoformat() if column == "trading_date" else 0) for column in fields}
    row.update(ticker="AAA", time=day, as_of=datetime(2026, 10, 21, 8, 30, tzinfo=UTC),
               available_at=datetime(2026, 10, 21, 9, tzinfo=UTC), source="CAFEF" if kind == "foreign" else "PROP_CALL",
               price_scale="VND_FULL", volume_unit="shares", historical_pit_verified=False)
    frame = pd.DataFrame([row], columns=SCHEMAS[kind])
    before = frame.copy(deep=True)
    report = PipelineQualityChecker().check(frame, kind, decision_time=NOW)
    assert "domain_validator_error" not in report["blocking_rules"] and report["status"] == "unknown"
    assert report["pit_status"] == "unverified"
    pd.testing.assert_frame_equal(frame, before)
    frame["historical_pit_verified"] = True
    assert "domain_validator_error" in PipelineQualityChecker().check(frame, kind)["blocking_rules"]
    frame["historical_pit_verified"] = False
    frame[fields[3]] = 1
    assert "domain_validator_error" in PipelineQualityChecker().check(frame, kind)["blocking_rules"]


def test_input_digest_binds_types_nulls_and_duplicate_multiplicity():
    checker = PipelineQualityChecker()
    frame = make_frame("financials")
    digest = checker.check(frame, "financials")["input_hash"]
    assert checker.check(pd.concat([frame, frame]), "financials")["input_hash"] != digest
    frame["item_value"] = frame["item_value"].astype(object)
    assert checker.check(frame, "financials")["input_hash"] != digest
    frame.at[0, "item_value"] = None
    null_hash = checker.check(frame, "financials")["input_hash"]
    frame.at[0, "item_value"] = float("nan")
    assert checker.check(frame, "financials")["input_hash"] != null_hash
    frame = make_frame("market").astype(object)
    typed_date_hash = checker.check(frame, "market")["input_hash"]
    frame.at[0, "date"] = frame.at[0, "date"].isoformat()
    assert checker.check(frame, "market")["input_hash"] != typed_date_hash


def test_mixed_date_representations_cannot_bypass_market_duplicate_key():
    frame = pd.concat([make_frame("market"), make_frame("market")], ignore_index=True).astype(object)
    frame.at[1, "date"] = frame.at[1, "date"].isoformat()
    report = PipelineQualityChecker().check(frame, "market")
    assert report["duplicate_count"] == 1 and "duplicate_key" in report["blocking_rules"]


def test_lossy_numeric_scalar_coercions_cannot_reuse_input_digest():
    from fractions import Fraction

    frame = make_frame("financials").astype(object)
    frame.at[0, "item_value"] = float(1 / 3)
    digest = PipelineQualityChecker().check(frame, "financials")["input_hash"]
    frame.at[0, "item_value"] = Fraction(1, 3)
    report = PipelineQualityChecker().check(frame, "financials", input_hash=digest)
    assert report["status"] == "failed" and report["output_hash"] is None
    assert "input_bounds_or_type" in report["blocking_rules"]


def test_nullable_news_identity_is_valid_but_duplicate_revision_still_blocks():
    frame = make_frame("news_live").astype(object)
    frame.at[0, "symbol"] = frame.at[0, "url"] = None
    report = PipelineQualityChecker().check(frame, "news_live", decision_time=NOW)
    assert report["status"] == "unknown" and "invalid_key_type" not in report["blocking_rules"]
    repeated = PipelineQualityChecker().check(pd.concat([frame, frame]), "news_live")
    assert repeated["duplicate_count"] == 1 and "duplicate_key" in repeated["blocking_rules"]


def test_macro_revisions_cannot_move_availability_backwards():
    from omega.data.macro_news_pipeline import SCHEMA, _record

    first = _record("fixture", "Fixture", "rss", "First version", None,
                    "https://example.invalid/report", NOW - timedelta(hours=4), NOW - timedelta(hours=2))
    second = _record("fixture", "Fixture", "rss", "Revised version", None,
                     "https://example.invalid/report", NOW - timedelta(hours=4), NOW - timedelta(hours=1))
    first["available_at"], second["available_at"] = NOW, NOW - timedelta(minutes=30)
    frame = pd.DataFrame([second, first], columns=SCHEMA)
    report = PipelineQualityChecker().check(frame, "macro_news", decision_time=NOW)
    assert "revision_availability_backwards" in report["blocking_rules"]
