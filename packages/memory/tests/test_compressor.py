import pytest
from omega.memory.compressor import (
    MemoryCompressor,
    SemanticHashingStrategy,
    LosslessCompressionStrategy,
    LossyCompressionStrategy
)

def test_lossless_compression():
    compressor = MemoryCompressor()
    data = {"key1": "value1", "key2": [1, 2, 3] * 100}
    
    compressed = compressor.compress(data, strategy_name="lossless")
    assert compressed["type"] == "lossless"
    assert "data" in compressed
    
    decompressed = compressor.decompress(compressed)
    assert decompressed == data

def test_lossy_compression_string():
    compressor = MemoryCompressor()
    long_string = "A" * 200
    
    compressed = compressor.compress(long_string, strategy_name="lossy")
    assert compressed["type"] == "lossy"
    assert compressed["original_length"] == 200
    assert len(compressed["data"]) == 103 # 100 + "..."
    
    decompressed = compressor.decompress(compressed)
    assert decompressed == "A" * 100 + "..."

def test_lossy_compression_list():
    compressor = MemoryCompressor()
    long_list = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    
    compressed = compressor.compress(long_list, strategy_name="lossy")
    assert compressed["type"] == "lossy"
    
    decompressed = compressor.decompress(compressed)
    assert len(decompressed) == 6
    assert decompressed[-1] == "..."

def test_semantic_hashing():
    compressor = MemoryCompressor()
    text = "This is a large block of text that we want to hash semantically."
    
    compressed = compressor.compress(text, strategy_name="semantic")
    assert compressed["type"] == "semantic_hash"
    assert compressed["hash"].startswith("semhash:")
    assert compressed["original_length"] == len(text)
    
    decompressed = compressor.decompress(compressed)
    assert decompressed == f"<{compressed['hash']}>"

def test_semantic_hashing_non_string():
    compressor = MemoryCompressor()
    data = {"not": "string"}
    
    compressed = compressor.compress(data, strategy_name="semantic")
    assert compressed["type"] == "raw"
    
    decompressed = compressor.decompress(compressed)
    assert decompressed == data

def test_invalid_strategy():
    compressor = MemoryCompressor()
    with pytest.raises(ValueError):
        compressor.compress("data", strategy_name="invalid")
