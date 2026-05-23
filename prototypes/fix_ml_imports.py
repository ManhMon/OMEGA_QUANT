import os
from pathlib import Path

# Core MAPPING
CORE_ROOT = Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\core\src\omega\core")
CORE_MAPPING = {
    "omega.core.model_trainer": "omega.core.trainer",
    "omega.core.model_validator": "omega.core.validator",
    "omega.core.promotion_gate": "omega.core.promotion",
    # Data deps
    "omega.core.data_source_config": "omega.data.datasource_config",
    "omega.core.vn_trading_calendar": "omega.data.calendar",
    "omega.core.data_validator": "omega.data.validator",
    "omega.core.vnstock_datasource": "omega.data.vnstock_adapter",
    "omega.core.vnstock_vci_datasource": "omega.data.vnstock_vci",
    "omega.core.vnstock_vci_ingest": "omega.data.vnstock_ingest",
    "omega.core.vn_market_flow_datasource": "omega.data.market_flow",
    "omega.core.vci_integration": "omega.data.vci_bridge",
}

# Quant MAPPING
QUANT_ROOT = Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\quant\src\omega\quant")
QUANT_MAPPING = {
    "omega.core.alpha_discovery": "omega.quant.alpha_discovery",
    "omega.core.model_registry": "omega.core.model_registry",
}
# Merge
QUANT_MAPPING.update(CORE_MAPPING)

def fix_imports(root, mapping):
    print(f"Scanning {root} for legacy imports...")
    count = 0
    if not root.exists():
        return
    for p in root.rglob("*.py"):
        content = p.read_text(encoding="utf-8")
        original = content
        
        for old, new in mapping.items():
            content = content.replace(f"from {old}", f"from {new}")
            content = content.replace(f"import {old}", f"import {new}")
        
        if content != original:
            p.write_text(content, encoding="utf-8")
            print(f"Fixed: {p}")
            count += 1
    print(f"Done. Fixed {count} files.")

fix_imports(CORE_ROOT, CORE_MAPPING)
fix_imports(QUANT_ROOT, QUANT_MAPPING)
