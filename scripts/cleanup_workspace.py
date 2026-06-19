import shutil
import os
from pathlib import Path

# PATH-01 FIX: Use repo-relative workspace instead of hardcoded .openclaw path
_REPO_ROOT = Path(__file__).resolve().parents[1]
workspace = _REPO_ROOT
archive = workspace / 'archive' / 'WORKSPACE_CLEANUP_20260509'
archive.mkdir(parents=True, exist_ok=True)

# Danh sách thư mục/file cần di chuyển
cleanup_items = [
    'tests', 'tests_v21', 'audit_tmp', '.pytest_tmp', '.pytest_cache',
    'free-code', 'mcp-bridge-api', 'opencode', 'codex', 'OpenSpace', 'state',
    'vnstock_guide_temp', '__pycache__', '~',
    'temp.txt', 'temp_schema.json', 'test_batch2_smoke.py', 'scratch_mcp.py',
    'after_minimize_browsers.png', 'teamviewer_focus.png', 'teamviewer_try.png',
    'V21_QUANT_CORE_GEMINI_ONLY_LAYER01_VNSTOCK_KBS_IMPL.zip',
    'V21_QUANT_MANIFEST.txt', 'V21_QUANT_RCG_MAP.txt'
]

moved_count = 0
for item in cleanup_items:
    src = workspace / item
    if src.exists():
        dst = archive / item
        try:
            if src.is_dir():
                shutil.move(str(src), str(dst))
            else:
                shutil.move(str(src), str(dst))
            moved_count += 1
            print(f"[OK] Moved: {item}")
        except Exception as e:
            print(f"[FAIL] Failed: {item} - {e}")

print(f"\nCleanup complete! Moved {moved_count} items to archive.")
print(f"Archive location: {archive}")
