import sys
import os

# Add all package src paths
paths = [
    r'C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\omega-core\src',
    r'C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\omega-core',
    r'C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\core\src',
    r'C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\data\src',
    r'C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\packages\quant\src',
]

for p in paths:
    if p not in sys.path:
        sys.path.insert(0, p)

# Now run pytest
import pytest
sys.exit(pytest.main(['-q', 'tests/phase1', 'tests/phase2']))
