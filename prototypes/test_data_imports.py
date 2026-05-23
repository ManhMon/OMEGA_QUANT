import sys
from pathlib import Path

# Add packages to sys.path to simulate import context
sys.path.insert(0, r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\data\src")

try:
    # Try importing modules directly to verify the updated imports work
    from omega.data import validator
    print("Imports test passed!")
except ModuleNotFoundError as e:
    print(f"Import failed: {e}")
    sys.exit(1)
except Exception as e:
    # Other errors might happen because we're just importing, but ModuleNotFoundError is what we care about
    print(f"Other error during import (expected if package is incomplete): {e}")
