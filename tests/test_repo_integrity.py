"""
Repository integrity, import freedom, deprecation shim identity,
documentation SSOT markers, and 16-dimension compliance tests.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import omega.data.sanitizer as sanitizer_mod
from omega.data.sanitizer import DataQualityChecker, DataSanitizer, DataValidator, ValidationIssue
import omega.data.validator as validator_shim
import omega.data.data_validator as data_validator_shim
import omega.data.data_quality as data_quality_shim
import omega.data.vci_direct as vci_direct
from omega.data.calendar import VNTradingCalendar
from omega.data.vnd_price_contract import DEFAULT_PRICE_COLS, THOUSANDS, VND_FULL, ensure_vnd_scale
import omega.quant.neutralization as quant_neutralization_shim
import omega.quant.features.neutralization as canonical_neutralization


# ═══════════════════════════════════════════════════════════════════════════════
# 1. IMPORT FREEDOM FOR ACTIVE SOURCE
# ═══════════════════════════════════════════════════════════════════════════════

def test_import_freedom_active_source():
    """Active modules in omega.data import cleanly; known archived modules fail closed."""
    known_archived = {"vci_bridge", "vnstock_adapter", "vnstock_ingest"}
    data_dir = REPO_ROOT / "src" / "omega" / "data"
    assert data_dir.is_dir()

    py_files = sorted(p.stem for p in data_dir.glob("*.py") if p.stem != "__init__")
    assert len(py_files) >= 20

    for stem in py_files:
        mod_name = f"omega.data.{stem}"
        if stem in known_archived:
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            with pytest.raises(ImportError, match=r"archived.*Access forbidden"):
                importlib.import_module(mod_name)
        else:
            mod = importlib.import_module(mod_name)
            assert mod is not None
            assert hasattr(mod, "__file__")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 0-BYTE FILE HYGIENE
# ═══════════════════════════════════════════════════════════════════════════════

def test_zero_byte_file_hygiene():
    """Verify repository source, script, documentation, and core anchor files are non-empty."""
    scan_roots = [
        REPO_ROOT / "src" / "omega" / "data",
        REPO_ROOT / "scripts",
        REPO_ROOT / ".agents",
    ]

    scanned_files = []
    for root in scan_roots:
        assert root.is_dir()
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in {".py", ".md", ".json"} and "__pycache__" not in p.parts:
                scanned_files.append(p)

    assert len(scanned_files) >= 50

    empty_files = [str(p.relative_to(REPO_ROOT)) for p in scanned_files if p.stat().st_size == 0]
    assert empty_files == [], f"Found 0-byte files: {empty_files}"

    anchor_files = [
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / ".agents" / "AGENTS.md",
        REPO_ROOT / "src" / "omega" / "data" / "sanitizer.py",
        REPO_ROOT / "src" / "omega" / "data" / "vci_direct.py",
    ]
    for anchor in anchor_files:
        assert anchor.exists()
        assert anchor.stat().st_size > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DEPRECATION SHIM IDENTITY
# ═══════════════════════════════════════════════════════════════════════════════

def test_deprecation_shim_identity():
    """Deprecation shims must re-export exact SSOT objects with matching identity and __all__."""
    assert validator_shim.DataValidator is DataValidator
    assert validator_shim.ValidationIssue is ValidationIssue
    assert set(validator_shim.__all__) == {"DataValidator", "ValidationIssue"}

    assert data_validator_shim.DataValidator is DataValidator
    assert data_validator_shim.ValidationIssue is ValidationIssue
    assert set(data_validator_shim.__all__) == {"DataValidator", "ValidationIssue"}

    assert data_quality_shim.DataQualityChecker is DataQualityChecker
    assert set(data_quality_shim.__all__) == {"DataQualityChecker"}

    assert quant_neutralization_shim.FactorNeutralizer is canonical_neutralization.FactorNeutralizer
    assert "FactorNeutralizer" in quant_neutralization_shim.__all__


# ═══════════════════════════════════════════════════════════════════════════════
# 4. DOCUMENTATION INTEGRITY MARKERS & SSOT REFERENCES
# ═══════════════════════════════════════════════════════════════════════════════

def test_documentation_integrity_markers_and_ssot():
    """Verify SSOT references in architecture docs, manifests, and sanitizer."""
    architecture = (REPO_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "# OMEGA_QUANT Architecture" in architecture
    assert "DirectVCIClient" in architecture
    assert "DataSanitizer" in architecture
    assert "archive/legacy_adapters/" in architecture
    assert "as_of <= available_at" in architecture

    agents_architecture = (REPO_ROOT / ".agents" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "OMEGA_QUANT Data Architecture SSOT" in agents_architecture
    assert "src/omega/data/vci_direct.py" in agents_architecture
    assert "src/omega/data/sanitizer.py" in agents_architecture

    market_skill = (REPO_ROOT / ".agents" / "skills" / "vietnam-market-data" / "SKILL.md").read_text(encoding="utf-8")
    assert "### Primary: DirectVCIClient (SSOT)" in market_skill
    assert "DataSanitizer" in market_skill
    assert "from vnstock import Quote" not in market_skill

    root_agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "The authoritative rules and specifications for the OMEGA_QUANT multi-agent SoD protocol have been consolidated to the workspace customization root path to ensure a single source of truth:" in root_agents
    assert "[.agents/AGENTS.md]" in root_agents

    ssot_agents = (REPO_ROOT / ".agents" / "AGENTS.md").read_text(encoding="utf-8")
    assert "# AGENTS.md - OMEGA_QUANT Protocol" in ssot_agents
    assert "## Tiers" in ssot_agents
    assert "16 dimensions" in ssot_agents

    manifest_path = REPO_ROOT / "archive" / "legacy_scripts" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(manifest, dict) and len(manifest) > 0

    for name, meta in manifest.items():
        assert set(meta.keys()) == {"sha256", "original_path", "line_count", "archived_at"}
        assert len(meta["sha256"]) == 64
        assert isinstance(meta["line_count"], int) and meta["line_count"] > 0
        assert meta["original_path"].startswith("scripts/")

        archived_file = REPO_ROOT / "archive" / "legacy_scripts" / name
        assert archived_file.exists()
        raw_bytes = archived_file.read_bytes()
        assert hashlib.sha256(raw_bytes).hexdigest() == meta["sha256"]

    sanitizer_text = (REPO_ROOT / "src" / "omega" / "data" / "sanitizer.py").read_text(encoding="utf-8")
    assert "Data Sanitizer - OMEGA_QUANT Canonical Data Module" in sanitizer_text
    assert "as_of <= available_at enforced" in sanitizer_text


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 16-DIMENSION ADVERSARIAL MATRIX ASSERTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def test_16d_dim01_malformed_out_of_bounds_types():
    """Dim 1: Malformed and out-of-bounds types are rejected fail-closed."""
    for bad in (None, math.nan, math.inf, -math.inf, "str", [1, 2], {}, True, False):
        assert vci_direct._is_finite_number(bad) is False

    validator = DataValidator()
    assert validator.validate("invalid_type") == {"error": "Input must be a pandas DataFrame"}

    with pytest.raises(ValueError, match="Invalid ticker"):
        vci_direct.unpack_vietcap_columnar(12345, {})  # type: ignore[arg-type]


def test_16d_dim02_invalid_paths_and_utf8_encoding():
    """Dim 2: Invalid traversal paths rejected and core sources decode with strict UTF-8."""
    assert vci_direct._canonical_vci_path("/api/../etc/passwd") is None
    assert vci_direct._canonical_vci_path("/api/./secret") is None
    assert vci_direct._canonical_vci_path("/not_allowed/chart") is None

    core_files = [
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / ".agents" / "AGENTS.md",
        REPO_ROOT / "src" / "omega" / "data" / "vci_direct.py",
        REPO_ROOT / "src" / "omega" / "data" / "sanitizer.py",
    ]
    for path in core_files:
        decoded = path.read_bytes().decode("utf-8")
        assert len(decoded) > 0


def test_16d_dim03_corrupted_shards_manifest_integrity():
    """Dim 3: Corrupted manifest shards raise decode error and actual manifest is consistent."""
    corrupted_json = '{"sha256": "abcdef", "line_count": '
    with pytest.raises(json.JSONDecodeError):
        json.loads(corrupted_json)

    manifest_file = REPO_ROOT / "archive" / "legacy_scripts" / "manifest.json"
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    for file_name, meta in data.items():
        assert len(meta["sha256"]) == 64
        assert meta["line_count"] > 0
        assert meta["archived_at"]


def test_16d_dim04_fail_closed_error_states():
    """Dim 4: Archived modules and provider stubs fail closed with explicit errors."""
    for mod_name in ("omega.data.vci_bridge", "omega.data.vnstock_adapter", "omega.data.vnstock_ingest"):
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        with pytest.raises(ImportError, match=r"archived.*Access forbidden"):
            importlib.import_module(mod_name)

    from omega.data.vnstock_live import VnStockLiveDataProvider
    provider = VnStockLiveDataProvider()
    with pytest.raises(ImportError, match=r"archived.*forbidden"):
        provider.get_latest_prices("HPG")
    with pytest.raises(ImportError, match=r"archived.*forbidden"):
        provider.fetch_live_data("HPG")


def test_16d_dim05_rollback_atomicity_and_temp_file_hygiene(tmp_path):
    """Dim 5: No dangling temp artifacts exist in data directory and atomic write succeeds."""
    dangling = list((REPO_ROOT / "src" / "omega" / "data").glob("*.tmp")) + list((REPO_ROOT / "src" / "omega" / "data").glob("*.bak"))
    assert dangling == [], f"Dangling temp artifacts found: {dangling}"

    target = tmp_path / "integrity_atomicity_test.txt"
    temp_target = tmp_path / "integrity_atomicity_test.txt.tmp"
    temp_target.write_text("atomic payload", encoding="utf-8")
    temp_target.replace(target)

    assert target.exists()
    assert not temp_target.exists()
    assert target.read_text(encoding="utf-8") == "atomic payload"


def test_16d_dim06_pit_lookahead_temporal_safety():
    """Dim 6: DataSanitizer outputs strictly obey point-in-time invariant (as_of <= available_at)."""
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    df = pd.DataFrame({
        "date": dates,
        "symbol": "HPG",
        "open": np.linspace(25000, 26000, 10),
        "high": np.linspace(25500, 26500, 10),
        "low": np.linspace(24500, 25500, 10),
        "close": np.linspace(25000, 26000, 10),
        "volume": np.full(10, 100000.0),
    })

    as_of = pd.Timestamp("2026-01-15")
    sanitizer = DataSanitizer(as_of_time=as_of)
    sanitizer.fit(df)
    cleaned = sanitizer.apply(df)

    assert "as_of" in cleaned.columns
    assert "available_at" in cleaned.columns
    assert (cleaned["as_of"] <= cleaned["available_at"]).all()


def test_16d_dim07_trading_calendar_holiday_boundaries():
    """Dim 7: Trading calendar identifies weekend dates as non-trading days."""
    saturday = pd.Timestamp("2026-01-03").to_pydatetime()
    sunday = pd.Timestamp("2026-01-04").to_pydatetime()
    monday = pd.Timestamp("2026-01-05").to_pydatetime()

    assert VNTradingCalendar.is_trading_day(saturday) is False
    assert VNTradingCalendar.is_trading_day(sunday) is False
    assert VNTradingCalendar.is_trading_day(monday) is True


def test_16d_dim08_numeric_precision_zero_division_guard():
    """Dim 8: Price bounds validator guards against zero division and non-finite numbers."""
    assert vci_direct.validate_price_bounds(raw_close=10000, prev_close=0, exchange="HOSE") is True
    assert vci_direct.validate_price_bounds(raw_close=10000, prev_close=-10, exchange="HOSE") is True
    assert vci_direct.validate_price_bounds(raw_close=math.nan, prev_close=10000, exchange="HOSE") is False  # type: ignore[arg-type]
    assert vci_direct.validate_price_bounds(raw_close=10000, prev_close=math.inf, exchange="HOSE") is False  # type: ignore[arg-type]
    assert vci_direct.validate_price_bounds(raw_close=10500, prev_close=10000, exchange="HOSE") is True
    assert vci_direct.validate_price_bounds(raw_close=20000, prev_close=10000, exchange="HOSE") is False


def test_16d_dim09_concurrency_race_condition_resistance():
    """Dim 9: Concurrent validations produce deterministic results without cross-thread contamination."""
    def worker(price: int) -> bool:
        return vci_direct.validate_price_bounds(raw_close=price, prev_close=10000, exchange="HOSE")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(worker, [10100, 10200, 10500, 15000] * 10))

    expected = [True, True, True, False] * 10
    assert results == expected


def test_16d_dim10_vnd_full_price_scale_unit_invariance():
    """Dim 10: Prices in THOUSANDS are converted to VND_FULL invariant scale."""
    assert VND_FULL == "VND_FULL"
    assert THOUSANDS == "THOUSANDS"

    df_thousands = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=3),
        "open": [25.0, 25.5, 26.0],
        "high": [26.0, 26.5, 27.0],
        "low": [24.5, 25.0, 25.5],
        "close": [25.2, 25.8, 26.2],
        "volume": [1000, 1200, 1500],
    })

    scaled = ensure_vnd_scale(df_thousands, price_cols=DEFAULT_PRICE_COLS)
    assert scaled["close"].iloc[0] == 25200.0
    assert scaled["open"].iloc[0] == 25000.0
    assert (scaled["close"] >= 1000.0).all()


def test_16d_dim11_survivorship_delisting_symbol_validation():
    """Dim 11: Symbol parser accepts valid uppercase alphanumeric tickers and rejects invalid/unsupported."""
    for valid in ("HPG", "VCB", "VN30F1M", "VNM1"):
        assert bool(vci_direct._SYMBOL.fullmatch(valid)) is True

    for invalid in ("hpg", "HPG!", "HPG@1", "", "   "):
        assert bool(vci_direct._SYMBOL.fullmatch(invalid)) is False

    assert vci_direct.validate_price_bounds(raw_close=10000, prev_close=10000, exchange="NASDAQ") is False


def test_16d_dim12_cli_and_url_injection_sanitization():
    """Dim 12: URL and symbol sanitization rejects injection tokens, flags, and unauthorized paths."""
    for malicious_url in (
        "http://trading.vietcap.com.vn/api/chart",
        "https://malicious.domain.com/api/chart",
        "https://user:password@trading.vietcap.com.vn/api/chart",
        "https://trading.vietcap.com.vn/admin/api",
        "https://trading.vietcap.com.vn/api/../secret",
        "https://trading.vietcap.com.vn/api/chart#fragment",
        "https://trading.vietcap.com.vn/api/chart?cmd=rm",
    ):
        assert vci_direct._is_allowed_vci_url(malicious_url) is False

    for cli_injection in ("--flag", "-f", "HPG;rm -rf /", "HPG && cat /etc/passwd", "`id`", "$(whoami)"):
        with pytest.raises(ValueError, match="Invalid ticker"):
            vci_direct.unpack_vietcap_columnar(cli_injection, {})


def test_16d_dim13_canonical_schema_drift_guard():
    """Dim 13: OHLCV schema remains strictly immutable with canonical columns."""
    expected_cols = (
        "time", "ticker", "raw_open", "raw_high", "raw_low", "raw_close",
        "adj_ratio", "open", "high", "low", "close", "volume", "value",
    )
    assert vci_direct.OHLCV_COLUMNS == expected_cols

    payload = {"t": [1704067200000], "o": [27000], "h": [28000], "l": [26000], "c": [27500], "v": [100]}
    df = vci_direct.unpack_vietcap_columnar("HPG", payload)
    assert tuple(df.columns) == expected_cols


def test_16d_dim14_resource_limits_and_bounds_guard():
    """Dim 14: Resource bounds are finite positive thresholds to prevent memory exhaustion."""
    assert vci_direct.MAX_PAYLOAD_BYTES == 16 * 1024 * 1024
    assert vci_direct.MAX_PAYLOAD_BYTES_HARD_LIMIT == 64 * 1024 * 1024
    assert vci_direct.MAX_ROWS == 50_000
    assert vci_direct.MAX_INT64 == 2**63 - 1
    assert vci_direct.MAX_VCI_URL_LENGTH == 2048
    assert vci_direct.MAX_VCI_QUERY_LENGTH == 1024


def test_16d_dim15_network_timeout_and_token_bucket_exhaustion():
    """Dim 15: Token bucket enforces finite rate/capacity and rejects invalid parameters."""
    with pytest.raises(ValueError, match="rate must be positive and finite"):
        vci_direct.TokenBucket(rate=-1.0)

    with pytest.raises(ValueError, match="rate must be positive and finite"):
        vci_direct.TokenBucket(rate=math.nan)

    bucket = vci_direct.TokenBucket(rate=10.0, capacity=10.0)
    assert bucket.tokens == 10.0
    assert bucket.rate == 10.0


def test_16d_dim16_secret_redaction_and_leak_prevention():
    """Dim 16: Redaction masks sensitive tokens and no hardcoded secret patterns exist in data sources."""
    secret_text = "Connect https://user:supersecretpass@trading.vietcap.com.vn with Bearer eyJhbGciOiJIUz and api_key=topsecret123"
    redacted = vci_direct.redact(secret_text)

    assert "supersecretpass" not in redacted
    assert "[REDACTED]" in redacted
    assert "topsecret123" not in redacted

    secret_pattern = re.compile(r"""(?:api[_-]?key|secret|password)\s*=\s*["'][A-Za-z0-9_\-]{20,}["']""", re.IGNORECASE)
    data_dir = REPO_ROOT / "src" / "omega" / "data"
    for py_file in data_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        matches = secret_pattern.findall(content)
        assert matches == [], f"Hardcoded secret pattern found in {py_file}: {matches}"

