import os
import re
from pathlib import Path

ROOT = Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\data\src\omega\data")

MAPPING = {
    "omega.core.data_source_config": "omega.data.datasource_config",
    "omega.core.vn_trading_calendar": "omega.data.calendar",
    "omega.core.data_validator": "omega.data.validator",
    "omega.core.vnstock_datasource": "omega.data.vnstock_adapter",
    "omega.core.vnstock_vci_datasource": "omega.data.vnstock_vci",
    "omega.core.vnstock_vci_ingest": "omega.data.vnstock_ingest",
    "omega.core.vn_market_flow_datasource": "omega.data.market_flow",
    "omega.core.vci_integration": "omega.data.vci_bridge",
}

def fix_imports():
    print(f"Scanning {ROOT} for legacy imports...")
    count = 0
    for p in ROOT.rglob("*.py"):
        content = p.read_text(encoding="utf-8")
        original = content
        
        for old, new in MAPPING.items():
            # Match 'from omega.core.xxx'
            content = content.replace(f"from {old}", f"from {new}")
            # Match 'import omega.core.xxx'
            content = content.replace(f"import {old}", f"import {new}")
        
        if content != original:
            p.write_text(content, encoding="utf-8")
            print(f"Fixed: {p}")
            count += 1
            
    print(f"Done. Fixed {count} files.")

if __name__ == "__main__":
    fix_imports()
