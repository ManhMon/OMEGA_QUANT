import os
from pathlib import Path

ROOTS = [
    Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\core\src\omega\core"),
    Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\data\src\omega\data"),
    Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\quant\src\omega\quant"),
    Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\tests")
]

MAPPING = {
    # Core mappings
    "omega.core.model_trainer": "omega.core.trainer",
    "omega.core.model_validator": "omega.core.validator",
    "omega.core.promotion_gate": "omega.core.promotion",
    
    # Data mappings
    "omega.core.data_source_config": "omega.data.datasource_config",
    "omega.core.vn_trading_calendar": "omega.data.calendar",
    "omega.core.data_validator": "omega.data.validator",
    "omega.core.vnstock_datasource": "omega.data.vnstock_adapter",
    "omega.core.vnstock_vci_datasource": "omega.data.vnstock_vci",
    "omega.core.vnstock_vci_ingest": "omega.data.vnstock_ingest",
    "omega.core.vn_market_flow_datasource": "omega.data.market_flow",
    "omega.core.vci_integration": "omega.data.vci_bridge",
    "omega.data.loader": "omega.data.loader", # for completeness
    
    # Quant mappings
    "omega.core.alpha_discovery": "omega.quant.alpha_discovery",
}

def fix_imports():
    count = 0
    for root in ROOTS:
        if not root.exists():
            continue
        print(f"Scanning {root}...")
        for p in root.rglob("*.py"):
            content = p.read_text(encoding="utf-8")
            original = content
            
            # Additional generic fix for omega-core style
            content = content.replace("from omega.core import", "from omega.core.event_bus import") # heuristic, needs care
            
            for old, new in MAPPING.items():
                content = content.replace(f"from {old}", f"from {new}")
                content = content.replace(f"import {old}", f"import {new}")
            
            if content != original:
                p.write_text(content, encoding="utf-8")
                print(f"Fixed: {p}")
                count += 1
    print(f"Done. Fixed {count} files.")

if __name__ == "__main__":
    fix_imports()
