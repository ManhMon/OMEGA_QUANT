import os
import shutil
from pathlib import Path

base = Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT")
src_root = base / "packages" / "omega-core" / "src" / "omega" / "core"
core_pkg = base / "packages" / "core" / "src" / "omega" / "core"
quant_pkg = base / "packages" / "quant" / "src" / "omega" / "quant"

# Setup namespace __init__ files
for pkg_dir in [core_pkg.parent, quant_pkg.parent]:
    pkg_dir.mkdir(parents=True, exist_ok=True)
    init_file = pkg_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("import pkgutil\n__path__ = pkgutil.extend_path(__path__, __name__)\n", encoding="utf-8")

mapping = {
    # Alpha -> quant package
    "alpha_discovery.py": (quant_pkg, "alpha_discovery.py"),
    # ML Core -> core package
    "model_registry.py": (core_pkg, "model_registry.py"),
    "model_trainer.py": (core_pkg, "trainer.py"),
    "model_validator.py": (core_pkg, "validator.py"),
    "promotion_gate.py": (core_pkg, "promotion.py"),
}

for src_name, (dst_dir, dst_name) in mapping.items():
    src_path = src_root / src_name
    dst_path = dst_dir / dst_name
    dst_dir.mkdir(parents=True, exist_ok=True)
    if src_path.exists():
        shutil.copy2(src_path, dst_path)
        print(f"Copied {src_name} -> {dst_dir.parent.name}/{dst_name}")
    else:
        print(f"Source {src_name} not found")

print("Commit 2: Alpha & ML Core migration complete")
