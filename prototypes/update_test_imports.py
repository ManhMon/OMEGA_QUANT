import os
import re
from pathlib import Path

# Mapping of old imports to new imports
MAPPING = {
    r'omega\.core\.data_source_config': 'omega.data.datasource_config',
    r'omega\.core\.vn_trading_calendar': 'omega.data.calendar',
    r'omega\.core\.data_validator': 'omega.data.validator',
    r'omega\.core\.vnstock_datasource': 'omega.data.vnstock_adapter',
    r'omega\.core\.model_trainer': 'omega.core.trainer',
    r'omega\.core\.model_validator': 'omega.core.validator',
    r'omega\.core\.promotion_gate': 'omega.core.promotion',
    r'omega\.core\.alpha_discovery': 'omega.quant.alpha_discovery',
}

def update_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    changes_made = False

    for old, new in MAPPING.items():
        # Match 'from old import' or 'import old' safely, handling boundaries
        # We can just do string replace for simplicity but regex is safer to avoid partial matches
        # but string replace is probably fine here since these are full package names.
        if re.search(old, content):
            content = re.sub(old, new, content)
            changes_made = True

    if changes_made:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated: {filepath}")
        return True
    return False

def main():
    test_dir = Path("OMEGA_QUANT/tests")
    if not test_dir.exists():
        print(f"Directory not found: {test_dir.absolute()}")
        return

    updated_count = 0
    total_count = 0

    for py_file in test_dir.rglob("*.py"):
        total_count += 1
        if update_file(py_file):
            updated_count += 1

    print(f"Finished. Updated {updated_count} out of {total_count} files.")

if __name__ == "__main__":
    main()