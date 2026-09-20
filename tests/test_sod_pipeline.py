import shutil

import pytest

import scripts.sod_pipeline as pipeline


pytestmark = pytest.mark.skipif(
    shutil.which("powershell") is None,
    reason="Windows PowerShell is required for subprocess boundary tests",
)


def test_run_powershell_block_propagates_explicit_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    assert pipeline.run("if ($true) { exit 7 }", "fault", check=False) == 7


def test_run_powershell_block_maps_terminating_error_to_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    assert pipeline.run("throw 'fault'", "fault", check=False) == 1


def test_run_powershell_block_clean_exit_is_not_masked_by_stale_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "REPO_ROOT", tmp_path)
    assert pipeline.run(
        "$global:LASTEXITCODE = 9; Write-Output 'clean'",
        "clean",
        check=False,
    ) == 0
