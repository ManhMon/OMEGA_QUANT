import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from vnstock import Reference
import inspect

ref = Reference()
methods = [m for m in dir(ref) if not m.startswith('_')]
print(f"Available methods: {methods}")

# Check for listing/stock methods
for m in methods:
    attr = getattr(ref, m)
    if callable(attr):
        try:
            sig = inspect.signature(attr)
            print(f"✓ {m}{sig}")
        except:
            print(f"✓ {m}(...)")