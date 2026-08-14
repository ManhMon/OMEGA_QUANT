"""
Tests for dashboard data control integration (Gate: DASHBOARD_DATA_CONTROL_INTEGRATION_20260613)
Scoped tests for DataLoaderService helpers, command construction, dry-run, lock behavior.
Uses mocks so canonical parquet is never mutated.
"""
import hashlib
import json
import os
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import pandas as pd

# Mock streamlit before importing the service module
_st_mock = MagicMock()
_st_mock.cache_data = lambda ttl=0: (lambda fn: fn)
sys.modules["streamlit"] = _st_mock

# Ensure dashboard root is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = REPO_ROOT / "apps" / "dashboard"
sys.path.insert(0, str(DASHBOARD_ROOT))

from config.dashboard_config import (
    MARKET_UPDATE_SCRIPT,
    VCI_UNIVERSE_FILE,
    MARKET_UPDATE_RESULT_FILE,
    LEGACY_LOADER_INVENTORY_JSON,
    LEGACY_LOADER_INVENTORY_MD,
    MARKET_UPDATE_LOCK_FILE,
    MARKET_DATA_FILE,
    PHASE_DEFINITIONS,
    SAFE_COMMAND_CATALOG,
    COMMAND_CENTER_READ_ONLY,
    COMMAND_CENTER_SECTIONS,
    COMMAND_CENTER_TABS,
    CLI_TRACE_MAX_LINES,
    PHASE6_EXCLUDED,
    E2E_COMPONENT_DEFINITIONS,
    E2E_ARTIFACT_CATALOG,
    E2E_COMMAND_CATALOG,
    E2E_DEFAULT_MODE,
    STATUS_MODE_READ_ONLY,
    STATUS_MODE_DRY_RUN,
    STATUS_MODE_MUTATING_BLOCKED,
)
from services.data_loader import DataLoaderService


# ══════════════════════════════════════════════════════════════════════════════
# Config Path Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigPaths:
    """Verify new config paths are correctly defined."""

    def test_market_update_script_path(self):
        assert MARKET_UPDATE_SCRIPT.name == "update_market_data.py"
        assert "scripts" in str(MARKET_UPDATE_SCRIPT)

    def test_vci_universe_file_path(self):
        assert VCI_UNIVERSE_FILE.name == "vci_universe_hsx_hnx.json"
        assert ".ly_state" in str(VCI_UNIVERSE_FILE)

    def test_market_update_result_file_path(self):
        assert MARKET_UPDATE_RESULT_FILE.name == "update_market_data_result.json"

    def test_legacy_loader_inventory_json_path(self):
        assert LEGACY_LOADER_INVENTORY_JSON.name == "legacy_data_loader_inventory_20260613.json"

    def test_legacy_loader_inventory_md_path(self):
        assert LEGACY_LOADER_INVENTORY_MD.name == "legacy_data_loader_inventory_20260613.md"

    def test_market_update_lock_file_path(self):
        assert MARKET_UPDATE_LOCK_FILE.name == "market_update.lock"


# ══════════════════════════════════════════════════════════════════════════════
# Command Construction Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildUpdateCommand:
    """Test build_update_command produces correct argument lists."""

    def test_dry_run_default(self):
        cmd = DataLoaderService.build_update_command(dry_run=True)
        assert "--dry-run" in cmd
        assert str(MARKET_UPDATE_SCRIPT) in cmd[1]

    def test_dry_run_false(self):
        cmd = DataLoaderService.build_update_command(dry_run=False)
        assert "--dry-run" not in cmd

    def test_symbols_appended(self):
        cmd = DataLoaderService.build_update_command(
            dry_run=True, symbols=["VCB", "HPG", "FPT"]
        )
        assert "--symbols" in cmd
        idx = cmd.index("--symbols")
        assert cmd[idx + 1: idx + 4] == ["VCB", "HPG", "FPT"]

    def test_start_end_dates(self):
        cmd = DataLoaderService.build_update_command(
            dry_run=True, start="2026-06-01", end="2026-06-13"
        )
        assert "--start" in cmd
        assert "--end" in cmd
        idx_s = cmd.index("--start")
        idx_e = cmd.index("--end")
        assert cmd[idx_s + 1] == "2026-06-01"
        assert cmd[idx_e + 1] == "2026-06-13"

    def test_no_optional_args(self):
        cmd = DataLoaderService.build_update_command(dry_run=True)
        assert "--symbols" not in cmd
        assert "--start" not in cmd
        assert "--end" not in cmd

    def test_uses_sys_executable(self):
        cmd = DataLoaderService.build_update_command(dry_run=True)
        assert cmd[0] == sys.executable

    def test_shell_false_safe(self):
        """Command is a list, not a string - safe for shell=False."""
        cmd = DataLoaderService.build_update_command(dry_run=True)
        assert isinstance(cmd, list)
        assert all(isinstance(arg, str) for arg in cmd)


# ══════════════════════════════════════════════════════════════════════════════
# Lock Behavior Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestLockBehavior:
    """Test that the lock file prevents concurrent updates."""

    @patch("services.data_loader.MARKET_UPDATE_LOCK_FILE")
    def test_locked_returns_blocked(self, mock_lock_path):
        """When lock exists and is fresh, return LOCKED status."""
        mock_lock_path.exists.return_value = True
        mock_lock_path.stat.return_value = MagicMock(
            st_mtime=datetime.now().timestamp()
        )
        mock_lock_path.parent = MagicMock()

        result = DataLoaderService.run_market_data_update(dry_run=True)
        assert result["status"] == "LOCKED"
        assert "Another update is running" in result["message"]

    @patch("services.data_loader.subprocess.run")
    @patch("services.data_loader.MARKET_UPDATE_LOCK_FILE")
    def test_lock_created_and_removed(self, mock_lock_path, mock_subprocess_run):
        """Lock file is created before run and removed after."""
        mock_lock_path.exists.return_value = False
        mock_lock_path.parent = MagicMock()
        mock_lock_path.write_text = MagicMock()
        mock_lock_path.unlink = MagicMock()

        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="OK", stderr=""
        )

        DataLoaderService.run_market_data_update(dry_run=True)

        mock_lock_path.write_text.assert_called_once()
        mock_lock_path.unlink.assert_called_once()

    @patch("services.data_loader.subprocess.run")
    @patch("services.data_loader.MARKET_UPDATE_LOCK_FILE")
    def test_lock_removed_on_error(self, mock_lock_path, mock_subprocess_run):
        """Lock file is removed even if subprocess raises."""
        mock_lock_path.exists.return_value = False
        mock_lock_path.parent = MagicMock()
        mock_lock_path.write_text = MagicMock()
        mock_lock_path.unlink = MagicMock()

        mock_subprocess_run.side_effect = RuntimeError("boom")

        result = DataLoaderService.run_market_data_update(dry_run=True)
        assert result["status"] == "ERROR"
        mock_lock_path.unlink.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# Subprocess Run Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRunMarketDataUpdate:
    """Test subprocess execution behavior."""

    @patch("services.data_loader.subprocess.run")
    @patch("services.data_loader.MARKET_UPDATE_LOCK_FILE")
    def test_subprocess_called_with_correct_args(self, mock_lock, mock_run):
        mock_lock.exists.return_value = False
        mock_lock.parent = MagicMock()
        mock_lock.write_text = MagicMock()
        mock_lock.unlink = MagicMock()
        mock_run.return_value = MagicMock(returncode=0, stdout="done", stderr="")

        DataLoaderService.run_market_data_update(
            dry_run=True, symbols=["VCB"], start="2026-06-01", end="2026-06-13"
        )

        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
        assert isinstance(cmd, list)
        assert "--dry-run" in cmd
        assert "--symbols" in cmd
        assert "VCB" in cmd
        assert call_args[1].get("shell") is False
        assert call_args[1].get("capture_output") is True

    @patch("services.data_loader.subprocess.run")
    @patch("services.data_loader.MARKET_UPDATE_LOCK_FILE")
    def test_timeout_returns_timeout_status(self, mock_lock, mock_run):
        import subprocess as sp
        mock_lock.exists.return_value = False
        mock_lock.parent = MagicMock()
        mock_lock.write_text = MagicMock()
        mock_lock.unlink = MagicMock()
        mock_run.side_effect = sp.TimeoutExpired(cmd="test", timeout=600)

        result = DataLoaderService.run_market_data_update(dry_run=True)
        assert result["status"] == "TIMEOUT"
        assert result["returncode"] == -1


# ══════════════════════════════════════════════════════════════════════════════
# Canonical Market Summary Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestCanonicalMarketSummary:
    """Test load_canonical_market_summary with mocked files."""

    @patch("services.data_loader.MARKET_DATA_FILE")
    def test_missing_file(self, mock_path):
        mock_path.exists.return_value = False
        result = DataLoaderService.load_canonical_market_summary()
        assert result["exists"] is False
        assert result["validation_status"] == "MISSING"

    @patch("services.data_loader.pd.read_parquet")
    @patch("services.data_loader.MARKET_DATA_FILE")
    def test_summary_fields(self, mock_path, mock_read):
        mock_path.exists.return_value = True
        mock_path.stat.return_value = MagicMock(st_size=1024 * 1024, st_mtime=1000000)

        # Create a small test DataFrame matching canonical schema
        df = pd.DataFrame({
            "ticker": ["VCB", "VCB", "HPG"],
            "date": pd.to_datetime(["2026-06-01", "2026-06-02", "2026-06-01"]),
            "exchange": ["HOSE", "HOSE", "HNX"],
            "open": [50000.0, 51000.0, 30000.0],
            "high": [51000.0, 52000.0, 31000.0],
            "low": [49000.0, 50000.0, 29000.0],
            "close": [50500.0, 51500.0, 30500.0],
            "volume": [100000, 120000, 80000],
            "as_of": ["2026-06-13", "2026-06-13", "2026-06-13"],
            "available_at": pd.to_datetime(["2026-06-02", "2026-06-03", "2026-06-02"]),
            "source": ["vnstock_vci"] * 3,
            "price_scale": ["VND"] * 3,
            "adjusted": ["backward_adjusted"] * 3,
            "rebuild_date": ["2026-06-13"] * 3,
        })
        mock_read.return_value = df

        # Mock open for sha256
        import builtins
        real_open = builtins.open

        def mock_open_fn(path, *args, **kwargs):
            if str(path) == str(mock_path) and "rb" in args:
                return MagicMock(
                    __enter__=lambda s: MagicMock(
                        read=MagicMock(side_effect=[b"testdata", b""])
                    ),
                    __exit__=MagicMock(return_value=False),
                )
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_fn):
            result = DataLoaderService.load_canonical_market_summary()

        assert result["exists"] is True
        assert result["rows"] == 3
        assert result["columns"] == 14
        assert result["ticker_count"] == 2
        assert result["date_min"] == "2026-06-01"
        assert result["date_max"] == "2026-06-02"
        assert "HOSE" in result["exchange_split"]
        assert result["duplicate_ticker_date"] == 0
        assert result["validation_status"] == "PASS"


# ══════════════════════════════════════════════════════════════════════════════
# VCI Universe Summary Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestVCIUniverseSummary:
    """Test load_vci_universe_summary."""

    @patch("services.data_loader.VCI_UNIVERSE_FILE")
    def test_missing_file(self, mock_path):
        mock_path.exists.return_value = False
        result = DataLoaderService.load_vci_universe_summary()
        assert result["exists"] is False

    @patch("builtins.open")
    @patch("services.data_loader.VCI_UNIVERSE_FILE")
    def test_loads_counts(self, mock_path, mock_open):
        mock_path.exists.return_value = True
        universe_data = {"hsx": ["VCB", "HPG"], "hnx": ["ABC"], "total": 3}
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        with patch("json.load", return_value=universe_data):
            result = DataLoaderService.load_vci_universe_summary()

        assert result["exists"] is True
        assert result["total"] == 3


# ══════════════════════════════════════════════════════════════════════════════
# Legacy Loader Inventory Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestLegacyLoaderInventory:
    """Test load_legacy_loader_inventory."""

    @patch("services.data_loader.LEGACY_LOADER_INVENTORY_MD")
    @patch("services.data_loader.LEGACY_LOADER_INVENTORY_JSON")
    def test_both_missing(self, mock_json, mock_md):
        mock_json.exists.return_value = False
        mock_md.exists.return_value = False
        result = DataLoaderService.load_legacy_loader_inventory()
        assert result["json_exists"] is False
        assert result["md_exists"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Update Result Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateMarketDataResult:
    """Test load_update_market_data_result."""

    @patch("services.data_loader.MARKET_UPDATE_RESULT_FILE")
    def test_missing_file(self, mock_path):
        mock_path.exists.return_value = False
        result = DataLoaderService.load_update_market_data_result()
        assert result["exists"] is False

    def test_projection_remains_display_only_while_ledger_is_surfaced(self, tmp_path):
        projection = tmp_path / "update_market_data_result.json"
        projection.write_text(json.dumps({"status": "published"}), encoding="utf-8")
        ledger = tmp_path / "market_data_receipts"
        ledger.mkdir()
        (ledger / "20260729T090000000000Z_a.terminal.json").write_text(
            json.dumps({"attempt_id": "20260729T090000000000Z_a", "state": "terminal", "execution_allowed": False}),
            encoding="utf-8",
        )
        with patch("services.data_loader.MARKET_UPDATE_RESULT_FILE", projection):
            with patch("services.data_loader.SESSION_DIR", tmp_path):
                assert DataLoaderService.load_update_market_data_result()["data"]["status"] == "published"
                assert DataLoaderService.load_market_data_attempt_ledger()["state"] == "BLOCKED"


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: Phase Definitions Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestPhaseDefinitions:
    """Verify Phase 1-5 definitions exist; Phase 6 excluded."""

    def test_five_phases_defined(self):
        assert len(PHASE_DEFINITIONS) == 5

    def test_phase_ids_are_1_through_5(self):
        ids = sorted(p["id"] for p in PHASE_DEFINITIONS.values())
        assert ids == [1, 2, 3, 4, 5]

    def test_phase6_excluded(self):
        assert PHASE6_EXCLUDED is True
        for p in PHASE_DEFINITIONS.values():
            assert p["id"] != 6
            assert "phase 6" not in p["name"].lower()
            assert "phase6" not in p.get("phase_key", "")

    def test_each_phase_has_required_keys(self):
        required = {"id", "name", "short", "description", "gate_keys", "icon"}
        for key, p in PHASE_DEFINITIONS.items():
            assert required.issubset(set(p.keys())), f"Phase {key} missing keys"

    def test_each_phase_has_gate_keys(self):
        for key, p in PHASE_DEFINITIONS.items():
            assert isinstance(p["gate_keys"], list)
            assert len(p["gate_keys"]) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: Safe Command Catalog Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestSafeCommandCatalog:
    """Verify safe command catalog is entirely read-only."""

    def test_catalog_not_empty(self):
        assert len(SAFE_COMMAND_CATALOG) >= 5

    def test_all_commands_are_read_only(self):
        for cmd in SAFE_COMMAND_CATALOG:
            assert cmd.get("read_only") is True, (
                f"Command {cmd['id']} is NOT read-only"
            )

    def test_no_dangerous_commands(self):
        """No command should execute live trading or mutation."""
        dangerous_keywords = [
            "--live", "--execute", "--mutate", "--trade",
            "--submit-order", "--deploy",
        ]
        for cmd in SAFE_COMMAND_CATALOG:
            all_args = " ".join(cmd.get("args", []))
            for kw in dangerous_keywords:
                assert kw not in all_args, (
                    f"Command {cmd['id']} contains dangerous arg: {kw}"
                )

    def test_catalog_has_required_fields(self):
        required = {"id", "label", "description", "script", "category", "read_only"}
        for cmd in SAFE_COMMAND_CATALOG:
            assert required.issubset(set(cmd.keys())), (
                f"Command {cmd['id']} missing fields"
            )

    def test_get_safe_command_catalog_returns_read_only(self):
        catalog = DataLoaderService.get_safe_command_catalog()
        assert len(catalog) == len(SAFE_COMMAND_CATALOG)
        for entry in catalog:
            assert entry["read_only"] is True
            assert entry["executed"] is False
            assert "full_command" in entry


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: CLI Trace Tests (no subprocess execution)
# ══════════════════════════════════════════════════════════════════════════════

class TestCLITrace:
    """CLI trace must be read-only metadata, never executing commands."""

    def test_trace_returns_list(self):
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
            with patch.object(DataLoaderService, "load_risk_status", return_value=None):
                with patch.object(DataLoaderService, "load_audit_log", return_value=[]):
                    entries = DataLoaderService.get_cli_trace_entries()
        assert isinstance(entries, list)
        assert len(entries) > 0

    def test_trace_respects_max_lines(self):
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
            with patch.object(DataLoaderService, "load_risk_status", return_value=None):
                with patch.object(DataLoaderService, "load_audit_log", return_value=[]):
                    entries = DataLoaderService.get_cli_trace_entries(max_lines=5)
        assert len(entries) <= 5

    def test_trace_entries_have_type_and_text(self):
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
            with patch.object(DataLoaderService, "load_risk_status", return_value=None):
                with patch.object(DataLoaderService, "load_audit_log", return_value=[]):
                    entries = DataLoaderService.get_cli_trace_entries()
        for entry in entries:
            assert "type" in entry
            assert "text" in entry
            assert entry["type"] in ("info", "ok", "warn", "err", "prompt", "dim")

    @patch("services.data_loader.subprocess.run")
    def test_trace_does_not_call_subprocess(self, mock_subprocess):
        """CLI trace must NEVER call subprocess.run."""
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
            with patch.object(DataLoaderService, "load_risk_status", return_value=None):
                with patch.object(DataLoaderService, "load_audit_log", return_value=[]):
                    DataLoaderService.get_cli_trace_entries()
        mock_subprocess.assert_not_called()

    def test_trace_with_gates_data(self):
        fake_gates = {
            "GATE_A": {"final_verdict": "[APPROVED]", "timestamp": "2026-06-13"},
            "GATE_B": {"final_verdict": "PENDING", "timestamp": "2026-06-12"},
        }
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value=fake_gates):
            with patch.object(DataLoaderService, "load_risk_status", return_value=None):
                with patch.object(DataLoaderService, "load_audit_log", return_value=[]):
                    entries = DataLoaderService.get_cli_trace_entries()
        texts = [e["text"] for e in entries]
        assert any("2 phase gates" in t for t in texts)

    def test_trace_with_risk_data(self):
        fake_risk = {
            "system_state": "RUNNING",
            "metrics": {"sharpe_ratio": 1.5, "max_drawdown": 0.05, "var_95": 0.02},
            "breached": False,
        }
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
            with patch.object(DataLoaderService, "load_risk_status", return_value=fake_risk):
                with patch.object(DataLoaderService, "load_audit_log", return_value=[]):
                    entries = DataLoaderService.get_cli_trace_entries()
        texts = [e["text"] for e in entries]
        assert any("RUNNING" in t for t in texts)


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: Phase Connectivity Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestPhaseConnectivity:
    """Phase connectivity returns expected states per phase."""

    def test_returns_list_of_five(self):
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
            result = DataLoaderService.get_phase_connectivity()
        assert len(result) == 5

    def test_all_missing_when_no_gates(self):
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
            result = DataLoaderService.get_phase_connectivity()
        for phase in result:
            assert phase["status"] == "MISSING"
            assert phase["gate_count"] == 0

    def test_all_pass_when_all_approved(self):
        fake_gates = {}
        for pdef in PHASE_DEFINITIONS.values():
            for gk in pdef["gate_keys"]:
                fake_gates[gk] = {"final_verdict": "[APPROVED]"}
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value=fake_gates):
            result = DataLoaderService.get_phase_connectivity()
        for phase in result:
            assert phase["status"] == "PASS"

    def test_warn_when_partial_approval(self):
        # Phase 1 has 2 gate keys; approve only 1
        p1_keys = PHASE_DEFINITIONS["phase1"]["gate_keys"]
        fake_gates = {}
        if len(p1_keys) >= 1:
            fake_gates[p1_keys[0]] = {"final_verdict": "[APPROVED]"}
        if len(p1_keys) >= 2:
            fake_gates[p1_keys[1]] = {"final_verdict": "NEEDS_FIX"}
        # All other phases approved
        for pdef in PHASE_DEFINITIONS.values():
            if pdef["id"] == 1:
                continue
            for gk in pdef["gate_keys"]:
                fake_gates[gk] = {"final_verdict": "[APPROVED]"}
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value=fake_gates):
            result = DataLoaderService.get_phase_connectivity()
        phase1 = [p for p in result if p["phase_id"] == 1][0]
        assert phase1["status"] == "WARN"

    def test_result_structure(self):
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
            result = DataLoaderService.get_phase_connectivity()
        required_keys = {
            "phase_id", "phase_key", "name", "short", "icon",
            "status", "gate_count", "approved_count", "description",
        }
        for phase in result:
            assert required_keys.issubset(set(phase.keys()))


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: Required Sections Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRequiredSections:
    """Verify required Command Center sections and tabs are defined."""

    def test_sections_defined(self):
        assert len(COMMAND_CENTER_SECTIONS) >= 5
        assert "executive_header" in COMMAND_CENTER_SECTIONS
        assert "phase_connectivity_map" in COMMAND_CENTER_SECTIONS
        assert "action_buttons" in COMMAND_CENTER_SECTIONS
        assert "cli_trace_panel" in COMMAND_CENTER_SECTIONS
        assert "detail_tabs" in COMMAND_CENTER_SECTIONS

    def test_tabs_defined(self):
        assert len(COMMAND_CENTER_TABS) >= 8


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: Read-Only Mode Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestReadOnlyMode:
    """Verify Command Center operates in read-only mode."""

    def test_read_only_flag_is_true(self):
        assert COMMAND_CENTER_READ_ONLY is True

    @patch("services.data_loader.subprocess.run")
    def test_no_subprocess_in_get_safe_command_catalog(self, mock_subprocess):
        DataLoaderService.get_safe_command_catalog()
        mock_subprocess.assert_not_called()

    @patch("services.data_loader.subprocess.run")
    def test_no_subprocess_in_get_system_readiness(self, mock_subprocess):
        with patch.object(DataLoaderService, "load_risk_status", return_value=None):
            with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
                with patch("services.data_loader.MARKET_DATA_FILE") as mock_mf:
                    mock_mf.exists.return_value = False
                    with patch.object(DataLoaderService, "load_backtest_results", return_value=[]):
                        with patch.object(DataLoaderService, "load_evolved_alphas", return_value={}):
                            DataLoaderService.get_system_readiness()
        mock_subprocess.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: System Readiness Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestSystemReadiness:
    """Test system readiness scoring."""

    def test_readiness_returns_score(self):
        with patch.object(DataLoaderService, "load_risk_status", return_value=None):
            with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
                with patch("services.data_loader.MARKET_DATA_FILE") as mock_mf:
                    mock_mf.exists.return_value = False
                    with patch.object(DataLoaderService, "load_backtest_results", return_value=[]):
                        with patch.object(DataLoaderService, "load_evolved_alphas", return_value={}):
                            result = DataLoaderService.get_system_readiness()
        assert "readiness_score" in result
        assert 0 <= result["readiness_score"] <= 100
        assert "components" in result
        assert "timestamp" in result

    def test_readiness_all_pass_is_100(self):
        fake_risk = {"system_state": "RUNNING", "breached": False}
        fake_gates = {"G1": {"final_verdict": "[APPROVED]"}}
        with patch.object(DataLoaderService, "load_risk_status", return_value=fake_risk):
            with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value=fake_gates):
                with patch("services.data_loader.MARKET_DATA_FILE") as mock_mf:
                    mock_mf.exists.return_value = True
                    with patch.object(DataLoaderService, "load_backtest_results", return_value=[{"sharpe": 1.0}]):
                        with patch.object(DataLoaderService, "load_evolved_alphas", return_value={"r1": {}}):
                            result = DataLoaderService.get_system_readiness()
        assert result["readiness_score"] == 100


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: Data Health Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDataHealth:
    """Test data health status helper."""

    def test_returns_list(self):
        result = DataLoaderService.get_data_health_status()
        assert isinstance(result, list)
        assert len(result) >= 5

    def test_each_entry_has_required_fields(self):
        result = DataLoaderService.get_data_health_status()
        for entry in result:
            assert "file" in entry
            assert "exists" in entry
            assert "freshness" in entry
            assert "status" in entry


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: Backtest Summary Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestBacktestSummary:
    """Test backtest summary helper."""

    def test_empty_when_no_results(self):
        with patch.object(DataLoaderService, "load_backtest_results", return_value=[]):
            result = DataLoaderService.get_backtest_summary()
        assert result["count"] == 0

    def test_counts_results(self):
        fake = [{"metrics": {"sharpe": 1.5}}, {"metrics": {"sharpe": 2.0}}]
        with patch.object(DataLoaderService, "load_backtest_results", return_value=fake):
            result = DataLoaderService.get_backtest_summary()
        assert result["count"] == 2
        assert result["best_sharpe"] == 2.0


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: Risk Summary Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRiskSummary:
    """Test risk summary helper."""

    def test_unavailable_when_no_data(self):
        with patch.object(DataLoaderService, "load_risk_status", return_value=None):
            result = DataLoaderService.get_risk_summary()
        assert result["available"] is False

    def test_available_with_data(self):
        fake = {
            "system_state": "RUNNING", "breached": False,
            "breached_reasons": [],
            "metrics": {
                "sharpe_ratio": 1.2, "max_drawdown": 0.08,
                "var_95": 0.02, "cvar_95": 0.03,
                "portfolio_beta": 0.95, "consecutive_losses": 2,
            },
        }
        with patch.object(DataLoaderService, "load_risk_status", return_value=fake):
            result = DataLoaderService.get_risk_summary()
        assert result["available"] is True
        assert result["sharpe_ratio"] == 1.2
        assert result["breached"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: Observability Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestObservability:
    """Test observability status helper."""

    def test_returns_dict(self):
        with patch.object(DataLoaderService, "load_audit_log", return_value=[]):
            result = DataLoaderService.get_observability_status()
        assert isinstance(result, dict)
        assert "read_only_mode" in result
        assert result["read_only_mode"] is True
        assert "dashboard_version" in result
        assert "command_center_version" in result


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: Gate Parsing Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestParsePhaseGatesFlat:
    """Test parse_phase_gates_flat handles various JSON shapes."""

    def test_missing_file_returns_empty(self):
        with patch("services.data_loader.PHASE_GATES_FILE") as mock_path:
            mock_path.exists.return_value = False
            result = DataLoaderService.parse_phase_gates_flat()
        assert result == {}

    def test_dict_of_dicts(self):
        fake = {
            "gate_a": {"phase_name": "gate_a", "final_verdict": "[APPROVED]"},
            "gate_b": {"phase_name": "gate_b", "final_verdict": "PENDING"},
        }
        with patch("services.data_loader.PHASE_GATES_FILE") as mock_path:
            mock_path.exists.return_value = True
            with patch("builtins.open", MagicMock()):
                with patch("json.load", return_value=fake):
                    result = DataLoaderService.parse_phase_gates_flat()
        assert "gate_a" in result
        assert "gate_b" in result

    def test_list_of_dicts(self):
        fake = [
            {
                "gate_x": {"phase_name": "gate_x", "final_verdict": "[APPROVED]"},
                "gate_y": {"phase_name": "gate_y", "final_verdict": "PENDING"},
            }
        ]
        with patch("services.data_loader.PHASE_GATES_FILE") as mock_path:
            mock_path.exists.return_value = True
            with patch("builtins.open", MagicMock()):
                with patch("json.load", return_value=fake):
                    result = DataLoaderService.parse_phase_gates_flat()
        assert "gate_x" in result
        assert "gate_y" in result

    def test_nested_dict_with_gate_entries(self):
        """Shape: {outer_key: {gate_name: {gate_info, ...}, ...}}"""
        fake = {
            "wrapper": {
                "GATE_1": {"phase_name": "GATE_1", "final_verdict": "[APPROVED]"},
                "GATE_2": {"phase_name": "GATE_2", "final_verdict": "NEEDS_FIX"},
            }
        }
        with patch("services.data_loader.PHASE_GATES_FILE") as mock_path:
            mock_path.exists.return_value = True
            with patch("builtins.open", MagicMock()):
                with patch("json.load", return_value=fake):
                    result = DataLoaderService.parse_phase_gates_flat()
        assert "GATE_1" in result
        assert "GATE_2" in result


# ══════════════════════════════════════════════════════════════════════════════
# Command Center: No Subprocess from Action Buttons (Integration)
# ══════════════════════════════════════════════════════════════════════════════

class TestNoSubprocessFromButtons:
    """Integration: prove no subprocess execution from new helpers."""

    @patch("services.data_loader.subprocess.run")
    def test_all_read_only_helpers_no_subprocess(self, mock_subprocess):
        """Every new Command Center helper must NOT call subprocess."""
        with patch.object(DataLoaderService, "load_risk_status", return_value=None):
            with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
                with patch("services.data_loader.MARKET_DATA_FILE") as mock_mf:
                    mock_mf.exists.return_value = False
                    with patch.object(DataLoaderService, "load_backtest_results", return_value=[]):
                        with patch.object(DataLoaderService, "load_evolved_alphas", return_value={}):
                            with patch.object(DataLoaderService, "load_audit_log", return_value=[]):
                                DataLoaderService.get_system_readiness()
                                DataLoaderService.get_safe_command_catalog()
                                DataLoaderService.get_cli_trace_entries()
                                DataLoaderService.get_data_health_status()
                                DataLoaderService.get_backtest_summary()
                                DataLoaderService.get_risk_summary()
                                DataLoaderService.get_observability_status()
                                DataLoaderService.get_phase_connectivity()
        mock_subprocess.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# E2E Component Definitions Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestE2EComponentDefinitions:
    """Verify E2E component definitions cover all major subsystems."""

    def test_e2e_components_not_empty(self):
        assert len(E2E_COMPONENT_DEFINITIONS) >= 10

    def test_required_subsystems_present(self):
        required = {
            "data", "feature_store", "alpha_model", "backtest",
            "portfolio", "risk", "execution", "sre", "governance",
            "dashboard",
        }
        assert required.issubset(set(E2E_COMPONENT_DEFINITIONS.keys()))

    def test_each_component_has_required_keys(self):
        required = {"name", "icon", "description", "artifact_keys", "fail_closed"}
        for ck, cv in E2E_COMPONENT_DEFINITIONS.items():
            assert required.issubset(set(cv.keys())), (
                f"E2E component {ck} missing keys"
            )

    def test_risk_and_execution_fail_closed(self):
        assert E2E_COMPONENT_DEFINITIONS["risk"]["fail_closed"] is True
        assert E2E_COMPONENT_DEFINITIONS["execution"]["fail_closed"] is True

    def test_non_critical_not_fail_closed(self):
        assert E2E_COMPONENT_DEFINITIONS["data"]["fail_closed"] is False
        assert E2E_COMPONENT_DEFINITIONS["dashboard"]["fail_closed"] is False


# ══════════════════════════════════════════════════════════════════════════════
# E2E Artifact Catalog Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestE2EArtifactCatalog:
    """Verify E2E artifact catalog is correctly defined."""

    def test_catalog_not_empty(self):
        assert len(E2E_ARTIFACT_CATALOG) >= 10

    def test_each_artifact_has_required_keys(self):
        required = {"label", "path_key", "required"}
        for ak, av in E2E_ARTIFACT_CATALOG.items():
            assert required.issubset(set(av.keys())), (
                f"Artifact {ak} missing keys"
            )

    def test_required_artifacts_marked(self):
        assert E2E_ARTIFACT_CATALOG["market_data"]["required"] is True
        assert E2E_ARTIFACT_CATALOG["risk_status"]["required"] is True
        assert E2E_ARTIFACT_CATALOG["phase_gates"]["required"] is True

    def test_optional_artifacts_marked(self):
        assert E2E_ARTIFACT_CATALOG["sector_mapping"]["required"] is False
        assert E2E_ARTIFACT_CATALOG["walk_forward_log"]["required"] is False


# ══════════════════════════════════════════════════════════════════════════════
# E2E Command Catalog Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestE2ECommandCatalog:
    """Verify E2E command catalog is entirely SAFE mode."""

    def test_catalog_not_empty(self):
        assert len(E2E_COMMAND_CATALOG) >= 4

    def test_all_commands_read_only(self):
        for cmd in E2E_COMMAND_CATALOG:
            assert cmd.get("read_only") is True, (
                f"E2E command {cmd['id']} is NOT read-only"
            )

    def test_no_mutating_commands(self):
        dangerous = ["--live", "--execute", "--mutate", "--trade",
                     "--submit-order", "--deploy"]
        for cmd in E2E_COMMAND_CATALOG:
            all_args = " ".join(cmd.get("args", []))
            for kw in dangerous:
                assert kw not in all_args, (
                    f"E2E command {cmd['id']} contains dangerous arg: {kw}"
                )

    def test_all_modes_are_safe(self):
        safe_modes = {STATUS_MODE_READ_ONLY, STATUS_MODE_DRY_RUN}
        for cmd in E2E_COMMAND_CATALOG:
            assert cmd.get("mode") in safe_modes, (
                f"E2E command {cmd['id']} mode is not safe: {cmd.get('mode')}"
            )

    def test_get_e2e_command_catalog_returns_read_only(self):
        catalog = DataLoaderService.get_e2e_command_catalog()
        assert len(catalog) == len(E2E_COMMAND_CATALOG)
        for entry in catalog:
            assert entry["read_only"] is True
            assert entry["executed"] is False
            assert "full_command" in entry


# ══════════════════════════════════════════════════════════════════════════════
# E2E Artifact Status Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestE2EArtifactStatus:
    """Test get_e2e_artifact_status returns valid results."""

    def test_returns_list(self):
        result = DataLoaderService.get_e2e_artifact_status()
        assert isinstance(result, list)
        assert len(result) >= 10

    def test_each_entry_has_required_fields(self):
        result = DataLoaderService.get_e2e_artifact_status()
        for entry in result:
            assert "key" in entry
            assert "label" in entry
            assert "required" in entry
            assert "status" in entry
            assert "exists" in entry

    def test_missing_files_degrade_gracefully(self):
        """Missing artifacts degrade to WARN/MISSING, not crash."""
        result = DataLoaderService.get_e2e_artifact_status()
        valid_statuses = {"OK", "MISSING", "OPTIONAL", "EMPTY", "WARN"}
        for entry in result:
            assert entry["status"] in valid_statuses, (
                f"Artifact {entry['key']} has invalid status: {entry['status']}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# E2E Component Health Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestE2EComponentHealth:
    """Test get_e2e_component_health returns correct health per component."""

    def test_returns_dict(self):
        result = DataLoaderService.get_e2e_component_health()
        assert isinstance(result, dict)
        assert len(result) >= 10

    def test_each_component_has_status(self):
        result = DataLoaderService.get_e2e_component_health()
        for ck, cv in result.items():
            assert "status" in cv
            assert "name" in cv
            assert "fail_closed" in cv

    def test_risk_fail_closed_when_missing(self):
        """Risk component must FAIL_CLOSED when evidence missing; WARN is not acceptable."""
        with patch.object(
            DataLoaderService, "get_e2e_artifact_status",
            return_value=[
                {"key": "risk_status", "label": "Risk Status JSON",
                 "required": True, "exists": False, "status": "MISSING",
                 "size_mb": 0, "age_hours": -1},
            ],
        ):
            result = DataLoaderService.get_e2e_component_health()
        risk = result.get("risk", {})
        assert risk["status"] == "FAIL_CLOSED", (
            f"Risk must FAIL_CLOSED when evidence missing, got: {risk['status']}"
        )

    def test_execution_fail_closed_when_missing(self):
        """Execution component must FAIL_CLOSED when evidence missing; WARN is not acceptable."""
        with patch.object(
            DataLoaderService, "get_e2e_artifact_status",
            return_value=[
                {"key": "goal_state", "label": "Goal Runner State",
                 "required": False, "exists": False, "status": "OPTIONAL",
                 "size_mb": 0, "age_hours": -1},
            ],
        ):
            result = DataLoaderService.get_e2e_component_health()
        execution = result.get("execution", {})
        assert execution["status"] == "FAIL_CLOSED", (
            f"Execution must FAIL_CLOSED when evidence missing/optional, "
            f"got: {execution['status']}"
        )

    def test_execution_warn_not_acceptable_for_missing_evidence(self):
        """Execution WARN must never be the result when goal_state is missing/optional."""
        with patch.object(
            DataLoaderService, "get_e2e_artifact_status",
            return_value=[
                {"key": "goal_state", "label": "Goal Runner State",
                 "required": False, "exists": False, "status": "OPTIONAL",
                 "size_mb": 0, "age_hours": -1},
            ],
        ):
            result = DataLoaderService.get_e2e_component_health()
        execution = result.get("execution", {})
        assert execution["status"] != "WARN", (
            "Execution must not degrade to WARN for missing evidence"
        )
        assert execution["status"] == "FAIL_CLOSED"

    def test_risk_warn_not_acceptable_for_missing_evidence(self):
        """Risk WARN must never be the result when risk_status is missing."""
        with patch.object(
            DataLoaderService, "get_e2e_artifact_status",
            return_value=[
                {"key": "risk_status", "label": "Risk Status JSON",
                 "required": True, "exists": False, "status": "MISSING",
                 "size_mb": 0, "age_hours": -1},
            ],
        ):
            result = DataLoaderService.get_e2e_component_health()
        risk = result.get("risk", {})
        assert risk["status"] != "WARN", (
            "Risk must not degrade to WARN for missing evidence"
        )
        assert risk["status"] == "FAIL_CLOSED"


# ══════════════════════════════════════════════════════════════════════════════
# E2E Topology Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestE2ETopology:
    """Test get_e2e_topology returns valid topology data."""

    def test_returns_dict_with_components_and_edges(self):
        result = DataLoaderService.get_e2e_topology()
        assert "components" in result
        assert "edges" in result
        assert "summary" in result
        assert "mode" in result

    def test_summary_has_counts(self):
        result = DataLoaderService.get_e2e_topology()
        summary = result["summary"]
        assert "total" in summary
        assert "ok" in summary
        assert "warn" in summary
        assert "fail" in summary
        assert "health_pct" in summary
        assert 0 <= summary["health_pct"] <= 100

    def test_mode_is_read_only(self):
        result = DataLoaderService.get_e2e_topology()
        assert result["mode"] == STATUS_MODE_READ_ONLY

    def test_edges_reference_valid_components(self):
        result = DataLoaderService.get_e2e_topology()
        comp_keys = set(result["components"].keys())
        for src, dst in result["edges"]:
            assert src in comp_keys, f"Edge source {src} not in components"
            assert dst in comp_keys, f"Edge dest {dst} not in components"


# ══════════════════════════════════════════════════════════════════════════════
# E2E Dashboard Summary Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestE2EDashboardSummary:
    """Test get_e2e_dashboard_summary returns executive summary."""

    def test_returns_dict(self):
        with patch.object(DataLoaderService, "load_risk_status", return_value=None):
            with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
                result = DataLoaderService.get_e2e_dashboard_summary()
        assert isinstance(result, dict)
        assert "topology" in result
        assert "risk_state" in result
        assert "gates_approved" in result
        assert "gates_total" in result
        assert "mode" in result
        assert "read_only" in result

    def test_read_only_is_true(self):
        with patch.object(DataLoaderService, "load_risk_status", return_value=None):
            with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
                result = DataLoaderService.get_e2e_dashboard_summary()
        assert result["read_only"] is True

    def test_mode_is_safe(self):
        with patch.object(DataLoaderService, "load_risk_status", return_value=None):
            with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
                result = DataLoaderService.get_e2e_dashboard_summary()
        assert result["mode"] == STATUS_MODE_READ_ONLY


# ══════════════════════════════════════════════════════════════════════════════
# E2E Test and Audit Trace Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestE2ETestAndAuditTrace:
    """Test get_latest_test_and_audit_trace."""

    def test_returns_list(self):
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
            with patch.object(DataLoaderService, "load_audit_log", return_value=[]):
                entries = DataLoaderService.get_latest_test_and_audit_trace()
        assert isinstance(entries, list)
        assert len(entries) > 0

    def test_entries_have_type_and_text(self):
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
            with patch.object(DataLoaderService, "load_audit_log", return_value=[]):
                entries = DataLoaderService.get_latest_test_and_audit_trace()
        for entry in entries:
            assert "type" in entry
            assert "text" in entry

    @patch("services.data_loader.subprocess.run")
    def test_trace_does_not_call_subprocess(self, mock_subprocess):
        """E2E trace must NEVER call subprocess.run."""
        with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
            with patch.object(DataLoaderService, "load_audit_log", return_value=[]):
                DataLoaderService.get_latest_test_and_audit_trace()
        mock_subprocess.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# E2E: No Subprocess from E2E Helpers (Integration)
# ══════════════════════════════════════════════════════════════════════════════

class TestE2ENoSubprocess:
    """Integration: prove no subprocess execution from E2E helpers."""

    @patch("services.data_loader.subprocess.run")
    def test_all_e2e_helpers_no_subprocess(self, mock_subprocess):
        """Every E2E helper must NOT call subprocess."""
        with patch.object(DataLoaderService, "load_risk_status", return_value=None):
            with patch.object(DataLoaderService, "parse_phase_gates_flat", return_value={}):
                with patch("services.data_loader.MARKET_DATA_FILE") as mock_mf:
                    mock_mf.exists.return_value = False
                    with patch.object(DataLoaderService, "load_backtest_results", return_value=[]):
                        with patch.object(DataLoaderService, "load_evolved_alphas", return_value={}):
                            with patch.object(DataLoaderService, "load_audit_log", return_value=[]):
                                DataLoaderService.get_e2e_artifact_status()
                                DataLoaderService.get_e2e_component_health()
                                DataLoaderService.get_e2e_topology()
                                DataLoaderService.get_e2e_command_catalog()
                                DataLoaderService.get_e2e_dashboard_summary()
                                DataLoaderService.get_latest_test_and_audit_trace()
        mock_subprocess.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# E2E: Status Mode Constants Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestE2EStatusModes:
    """Verify E2E status mode constants are defined correctly."""

    def test_read_only_mode_defined(self):
        assert STATUS_MODE_READ_ONLY == "READ_ONLY"

    def test_dry_run_mode_defined(self):
        assert STATUS_MODE_DRY_RUN == "DRY_RUN"

    def test_mutating_blocked_mode_defined(self):
        assert STATUS_MODE_MUTATING_BLOCKED == "MUTATING_BLOCKED"

    def test_default_mode_is_read_only(self):
        assert E2E_DEFAULT_MODE == STATUS_MODE_READ_ONLY


# ══════════════════════════════════════════════════════════════════════════════
# E2E: Updated Sections and Tabs Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestE2ESectionsAndTabs:
    """Verify updated Command Center sections include E2E."""

    def test_e2e_topology_in_sections(self):
        assert "e2e_topology_map" in COMMAND_CENTER_SECTIONS

    def test_tabs_include_e2e_topology(self):
        assert "E2E Topology" in COMMAND_CENTER_TABS

    def test_tabs_include_governance(self):
        assert "Governance" in COMMAND_CENTER_TABS

    def test_tab_count(self):
        assert len(COMMAND_CENTER_TABS) >= 9
