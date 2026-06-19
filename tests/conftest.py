"""
OMEGA_QUANT Test Configuration
===============================
TEST-01 FIX3: ACL-safe temp handling for L3 Windows environments.

Root cause (Fix2→Fix3): tempfile.TemporaryDirectory() creates child dirs
via tempfile.mkdtemp with mode 0o700, which on Windows L3 produces
restrictive inherited ACLs.  Child dirs cannot be written to, read from,
or deleted — shutil.rmtree in TemporaryDirectory.__exit__ raises
PermissionError, and Get-Acl on children raises UnauthorizedAccessException.

Fix strategy:
  1. Grant explicit full-control ACL on .omega_test_tmp via icacls (Windows).
  2. Replace tempfile.TemporaryDirectory() in affected tests with pytest's
     tmp_path fixture.  tmp_path creates dirs via os.makedirs which inherits
     parent ACLs correctly, and pytest manages cleanup at session end (not
     immediately in __exit__), avoiding PermissionError during test teardown.
  3. Provide _safe_rmtree for session-end cleanup with permission fix+retry.
  4. Keep env-var overrides and tempfile.tempdir patch for any remaining
     tempfile usage in non-scoped tests.
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Repo-local temp directory (avoids Windows AppData ACL issues)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_REPO_TMP = _REPO_ROOT / ".omega_test_tmp"


def _grant_full_control_win32(path: str) -> None:
    """On Windows, run icacls to grant Everyone full control (best-effort)."""
    if sys.platform != "win32":
        return
    try:
        subprocess.run(
            ["icacls", path, "/grant", "Everyone:(OI)(CI)F", "/T", "/Q"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass  # best-effort; not fatal


def _safe_rmtree(path: str | Path) -> None:
    """Remove directory tree, fixing read-only/ACL errors on Windows."""
    path = str(path)

    def _onerror(func, fpath, exc_info):
        try:
            os.chmod(fpath, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        except Exception:
            pass
        try:
            func(fpath)
        except Exception:
            if sys.platform == "win32":
                _grant_full_control_win32(fpath)
                try:
                    func(fpath)
                except Exception:
                    pass

    try:
        shutil.rmtree(path, onerror=_onerror)
    except Exception:
        pass


def _ensure_repo_tmp():
    """Create repo-local temp dir with explicit ACL on Windows."""
    _REPO_TMP.mkdir(parents=True, exist_ok=True)
    _grant_full_control_win32(str(_REPO_TMP))
    return str(_REPO_TMP)


# Force-set environment variables — setdefault was insufficient because
# TEMP/TMP are already set by the Windows shell to AppData\\Local\\Temp.
_repo_tmp_str = _ensure_repo_tmp()
os.environ["TMPDIR"] = _repo_tmp_str
os.environ["TEMP"] = _repo_tmp_str
os.environ["TMP"] = _repo_tmp_str

# Directly patch tempfile.tempdir so that tempfile.mkdtemp(), TemporaryDirectory(),
# NamedTemporaryFile(), etc. all resolve under the repo-local path regardless
# of the OS-level environment.
tempfile.tempdir = _repo_tmp_str

# Force joblib to use single-threaded mode by default on Windows
# to avoid multiprocessing pipe creation permission errors.
if sys.platform == "win32":
    os.environ["JOBLIB_TEMP_FOLDER"] = _repo_tmp_str
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")


@pytest.fixture(autouse=True)
def _omega_test_tmp(monkeypatch, tmp_path):
    """
    Auto-use fixture: every test gets a repo-local temp directory.
    Force-patches env vars and tempfile.tempdir to the repo-local path.
    Also grants full-control ACL on pytest's tmp_path for L3 Windows.
    """
    monkeypatch.setenv("TMPDIR", _repo_tmp_str)
    monkeypatch.setenv("TEMP", _repo_tmp_str)
    monkeypatch.setenv("TMP", _repo_tmp_str)
    monkeypatch.setattr(tempfile, "tempdir", _repo_tmp_str)
    # Ensure pytest's own tmp_path has proper ACL inheritance on Windows
    if sys.platform == "win32" and tmp_path.exists():
        _grant_full_control_win32(str(tmp_path))


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "live_safety: live trading safety tests")


def pytest_sessionfinish(session, exitstatus):
    """Clean up repo-local temp directory after test session."""
    try:
        if _REPO_TMP.exists():
            _safe_rmtree(_REPO_TMP)
    except Exception:
        pass
