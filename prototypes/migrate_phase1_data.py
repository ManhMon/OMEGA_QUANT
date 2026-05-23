import os
import shutil
from pathlib import Path

base = Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT")
src_root = base / "packages" / "omega-core" / "src" / "omega" / "core"
data_pkg = base / "packages" / "data" / "src" / "omega" / "data"

mapping = {
    "data_source_config.py": "datasource_config.py",
    "vn_trading_calendar.py": "calendar.py",
    "data_validator.py": "validator.py",
    "vnstock_datasource.py": "vnstock_adapter.py",
    "vnstock_vci_datasource.py": "vnstock_vci.py",
    "vnstock_vci_ingest.py": "vnstock_ingest.py",
    "vn_market_flow_datasource.py": "market_flow.py",
    "vci_integration.py": "vci_bridge.py"
}

for src_name, dst_name in mapping.items():
    src_path = src_root / src_name
    dst_path = data_pkg / dst_name
    if src_path.exists():
        shutil.copy2(src_path, dst_path)
        print(f"Copied {src_name} -> data/{dst_name}")
    else:
        print(f"Source {src_name} not found")

print("Commit 1: Data Infrastructure migration complete")
