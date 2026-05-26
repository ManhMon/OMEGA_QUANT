"""Root conftest.py — ensures src/ is on sys.path for all tests."""
import sys
import os

# Add src/ to path so `omega.*` imports resolve correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
