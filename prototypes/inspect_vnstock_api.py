import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from vnstock import Trading
import inspect

print("=" * 70)
print("VNSTOCK v4.0.2 - AVAILABLE METHODS")
print("=" * 70)

t = Trading()

# Get all public methods
methods = [m for m in dir(t) if not m.startswith('_')]
print(f"\nTotal public methods: {len(methods)}\n")

for method in sorted(methods):
    attr = getattr(t, method)
    if callable(attr):
        try:
            sig = inspect.signature(attr)
            print(f"✓ {method}{sig}")
        except:
            print(f"✓ {method}(...)")
    else:
        print(f"  {method} (property)")

print("\n" + "=" * 70)
print("CHECKING price_history IMPLEMENTATION")
print("=" * 70)

try:
    import inspect
    source = inspect.getsource(t.price_history)
    print("Source code:")
    print(source[:500])
except Exception as e:
    print(f"Cannot get source: {e}")
