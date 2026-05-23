from pathlib import Path

base = Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT")
packages_dir = base / "packages"
canonical_packages = [
    "core", "contracts", "quant", "backtest", "execution",
    "risk", "data", "infra", "observability", "security", "governance"
]

for pkg in canonical_packages:
    pkg_path = packages_dir / pkg
    (pkg_path / "src" / "omega" / pkg).mkdir(parents=True, exist_ok=True)
    (pkg_path / "tests").mkdir(parents=True, exist_ok=True)

    (pkg_path / "src" / "omega" / pkg / "__init__.py").touch(exist_ok=True)
    (pkg_path / "tests" / "__init__.py").touch(exist_ok=True)

    toml_path = pkg_path / "pyproject.toml"
    if not toml_path.exists():
        toml_path.write_text(
            """[build-system]
requires = [\"setuptools>=61.0\"]
build-backend = \"setuptools.build_meta\"

[project]
name = \"omega-""" + pkg + """\"
version = \"0.1.0\"
description = \"OMEGA_QUANT """ + pkg.title() + """ Module\"
authors = [{ name = \"OMEGA Engineering\" }]
""",
            encoding="utf-8"
        )

print("Canonical packages baseline created")
