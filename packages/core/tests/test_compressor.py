import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from omega.core.memory.compressor import MemoryCompressor

def test_lossless_compression():
    compressor = MemoryCompressor()
    original_data = {"key": "value", "numbers": [1, 2, 3]}
    compressed = compressor.compress(original_data, strategy="lossless")
    decompressed = compressor.decompress(compressed, strategy="lossless")
    assert original_data == decompressed

def test_lossy_compression():
    compressor = MemoryCompressor()
    original_data = {"long_str": "a" * 200, "long_list": list(range(20))}
    compressed = compressor.compress(original_data, strategy="lossy")
    assert len(compressed["long_str"]) == 103 # 100 chars + "..."
    assert len(compressed["long_list"]) == 11 # 10 items + "truncated"

def test_semantic_hashing():
    compressor = MemoryCompressor()
    original_data = {"key": "value"}
    compressed1 = compressor.compress(original_data, strategy="semantic")
    compressed2 = compressor.compress(original_data, strategy="semantic")
    assert compressed1 == compressed2
    assert compressed1.startswith("hash_ref:")

def test_invalid_strategy():
    compressor = MemoryCompressor()
    with pytest.raises(ValueError):
        compressor.compress({"data": "test"}, strategy="invalid")
