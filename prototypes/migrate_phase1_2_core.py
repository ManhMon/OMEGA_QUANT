import os
import shutil
from pathlib import Path

base = Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT")
src_root = base / "packages" / "omega-core" / "omega" / "core"
core_pkg = base / "packages" / "core" / "src" / "omega" / "core"
data_pkg = base / "packages" / "data" / "src" / "omega" / "data"
quant_pkg = base / "packages" / "quant" / "src" / "omega" / "quant"

# Setup namespace __init__ files
for pkg_dir in [core_pkg.parent, data_pkg.parent, quant_pkg.parent]:
    pkg_dir.mkdir(parents=True, exist_ok=True)
    init_file = pkg_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("import pkgutil\n__path__ = pkgutil.extend_path(__path__, __name__)\n", encoding="utf-8")

# Core modules
core_mapping = {
    "event_bus.py": (core_pkg, "event_bus.py"),
    "task_state_machine.py": (core_pkg, "task_state_machine.py"),
    "scheduler.py": (core_pkg, "scheduler.py"),
    "feature_factory.py": (core_pkg, "feature_factory.py"),
    "neutralization.py": (core_pkg, "neutralization.py"),
}

for src_name, (dst_dir, dst_name) in core_mapping.items():
    src_path = src_root / src_name
    dst_path = dst_dir / dst_name
    dst_dir.mkdir(parents=True, exist_ok=True)
    if src_path.exists():
        shutil.copy2(src_path, dst_path)
        print(f"Copied {src_name} -> {dst_dir.parent.name}/{dst_name}")
    else:
        print(f"Source {src_name} not found")

print("Phase 1 & 2 core modules migration complete")
