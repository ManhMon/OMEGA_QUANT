from vnstock.api.quote import Quote
import inspect

# Get signature
sig = inspect.signature(Quote.history)
print(f"Quote.history signature: {sig}")

# Get docstring
print(f"\nDocstring:\n{Quote.history.__doc__}")
