import pytest
import shutil
import uuid
from pathlib import Path

@pytest.fixture
def workspace_tmp(tmp_path_factory):
    # Use .ly_state/test_tmp/ instead of system temp
    base = Path(".ly_state/test_tmp")
    base.mkdir(parents=True, exist_ok=True)
    tmp = base / f"test_{uuid.uuid4().hex[:8]}"
    tmp.mkdir()
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)

@pytest.fixture(scope="session", autouse=True)
def cleanup_test_tmp():
    yield
    shutil.rmtree(".ly_state/test_tmp", ignore_errors=True)
