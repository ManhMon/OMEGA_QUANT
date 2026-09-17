"""Root conftest.py — ensures src/ is on sys.path and provides writable tmp_path."""
import sys
import os
import re
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


@pytest.fixture
def tmp_path(request):
    """Override pytest built-in tmp_path with repo-local writable directory.

    On Python 3.14 / Windows, pytest's TempPathFactory creates directories
    with mode=0o700 which restricts ACL inheritance. Child directories
    created by tests then fail with PermissionError [WinError 5].

    This fixture creates test directories under
    .ly_state/session/pytest_tmp_paths/<pid>/<testname>/ using default
    mkdir (no mode argument) so Windows permissions are inherited from
    the parent directory.
    """
    repo_root = Path(__file__).resolve().parent
    basetemp_parent = repo_root / ".ly_state" / "session" / "pytest_tmp_paths"
    basetemp_parent.mkdir(parents=True, exist_ok=True)

    pid = os.getpid()
    raw_name = request.node.name
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", raw_name)

    test_dir = basetemp_parent / str(pid) / safe_name
    if test_dir.exists() and any(test_dir.iterdir()):
        counter = 0
        while True:
            candidate = basetemp_parent / str(pid) / f"{safe_name}_{counter}"
            if not candidate.exists() or not any(candidate.iterdir()):
                test_dir = candidate
                break
            counter += 1

    test_dir.mkdir(parents=True, exist_ok=True)

    # Probe: verify child mkdir works with default permissions
    probe = test_dir / ".probe"
    probe.mkdir(exist_ok=True)

    yield test_dir


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    """Guard cleanup_dead_symlinks against PermissionError on Windows."""
    import _pytest.pathlib as _pl
    import _pytest.tmpdir as _td
    _orig = _pl.cleanup_dead_symlinks

    def _guarded(root):
        try:
            _orig(root)
        except PermissionError:
            pass

    _pl.cleanup_dead_symlinks = _guarded
    _td.cleanup_dead_symlinks = _guarded
