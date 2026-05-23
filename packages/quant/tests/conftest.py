import sys
import os
from pathlib import Path

# Add all src directories to sys.path
repo_root = Path(__file__).parent.parent.parent.parent
packages_dir = repo_root / "packages"

for p in packages_dir.iterdir():
    if p.is_dir():
        src_dir = p / "src"
        if src_dir.exists():
            sys.path.append(str(src_dir))

