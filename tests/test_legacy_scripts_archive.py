"""Verification for Gate 2 legacy script archival."""

import hashlib
import json
import re
import runpy
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = REPO_ROOT / "archive" / "legacy_scripts"
MANIFEST_FILE = ARCHIVE_DIR / "manifest.json"
SCRIPTS_DIR = REPO_ROOT / "scripts"

SCRIPT_NAMES = (
    "_fix_forbidden_scan.py",
    "audit_phase38.py",
    "audit_phase5.py",
    "audit_phase7.py",
    "batch_market_loader_resume.py",
    "call_sov_phase3_4.py",
    "compare_phase10_ensemble.py",
    "compare_phase11_realistic.py",
    "compare_phase310_vs_phase39.py",
    "compare_phase311_vs_phase310.py",
    "compare_phase38_costs.py",
    "compare_phase39_dsr.py",
    "compare_phase5_vs_phase311.py",
    "compare_phase8_h60_capacity.py",
    "compare_phase8_h60_falsification.py",
    "compare_phase8_horizons.py",
    "compare_phase9_horizons.py",
    "live_test_phase21_smoke.py",
    "optuna_phase12.py",
    "phase5_capacity_sweep.py",
    "read_phase12_results.py",
    "reaudit_phase1_18.py",
    "run_l2_hook_ingest_703.py",
    "run_l3_audit_phase2.py",
    "run_phase6_continuous_learning.py",
    "sensitivity_grid_phase34.py",
    "summarize_phase38.py",
    "summarize_phase4.py",
    "test_phase10_pipeline.py",
    "update_market_data_2026.py",
    "verify_phase_gaps.py",
)


def load_manifest():
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))


def test_manifest_schema_and_count():
    manifest = load_manifest()
    assert set(manifest) == {f"{name}.txt" for name in SCRIPT_NAMES}
    for name, metadata in manifest.items():
        assert set(metadata) == {"sha256", "original_path", "line_count", "archived_at"}
        assert len(metadata["sha256"]) == 64
        assert metadata["original_path"] == f"scripts/{name[:-4]}"
        assert isinstance(metadata["line_count"], int)
        assert metadata["line_count"] > 0
        assert metadata["archived_at"]


def test_manifest_entries_match_archived_bytes_and_lines():
    for name, metadata in load_manifest().items():
        archived = ARCHIVE_DIR / name
        content = archived.read_bytes()
        assert hashlib.sha256(content).hexdigest() == metadata["sha256"]
        assert len(content.splitlines()) == metadata["line_count"]


@pytest.mark.parametrize("name", SCRIPT_NAMES)
def test_archived_script_stub_fails_closed(name):
    with pytest.raises(RuntimeError, match=r"^DEPRECATED: Script archived to archive/legacy_scripts/"):
        runpy.run_path(str(SCRIPTS_DIR / name))


def test_archive_isolation_no_imports():
    for root in (REPO_ROOT / "src", SCRIPTS_DIR, REPO_ROOT / "tests"):
        for path in root.rglob("*.py"):
            if path == Path(__file__).resolve():
                continue
            source = path.read_text(encoding="utf-8-sig")
            assert not re.search(r"^\s*(?:from\s+archive(?:\.|\s)|import\s+archive(?:\.|\s|$))", source, re.MULTILINE)


def test_manifest_paths_are_relative_and_confined():
    for name, metadata in load_manifest().items():
        assert Path(name).parts == (name,)
        original = Path(metadata["original_path"])
        assert not original.is_absolute()
        assert original.parts[0] == "scripts"
        assert ".." not in original.parts
