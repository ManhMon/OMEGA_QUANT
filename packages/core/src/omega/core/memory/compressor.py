import zlib
import base64
import json
import hashlib
from typing import Any, Dict, Protocol

class CompressionStrategy(Protocol):
    def compress(self, data: Any) -> Any: ...
    def decompress(self, data: Any) -> Any: ...

class LosslessCompressionStrategy:
    def compress(self, data: Any) -> str:
        json_str = json.dumps(data)
        compressed = zlib.compress(json_str.encode('utf-8'))
        return base64.b64encode(compressed).decode('utf-8')

    def decompress(self, data: str) -> Any:
        compressed = base64.b64decode(data.encode('utf-8'))
        json_str = zlib.decompress(compressed).decode('utf-8')
        return json.loads(json_str)

class LossyCompressionStrategy:
    def __init__(self, max_str_len: int = 100, max_list_items: int = 10):
        self.max_str_len = max_str_len
        self.max_list_items = max_list_items

    def compress(self, data: Any) -> Any:
        if isinstance(data, str):
            return data[:self.max_str_len] + "..." if len(data) > self.max_str_len else data
        elif isinstance(data, list):
            compressed_list = [self.compress(item) for item in data[:self.max_list_items]]
            if len(data) > self.max_list_items:
                compressed_list.append(f"... ({len(data) - self.max_list_items} more items truncated)")
            return compressed_list
        elif isinstance(data, dict):
            return {k: self.compress(v) for k, v in data.items()}
        return data

    def decompress(self, data: Any) -> Any:
        return data

class SemanticHashingStrategy:
    def compress(self, data: Any) -> str:
        json_str = json.dumps(data, sort_keys=True)
        return "hash_ref:" + hashlib.sha256(json_str.encode('utf-8')).hexdigest()

    def decompress(self, data: str) -> Any:
        return data

class MemoryCompressor:
    def __init__(self):
        self.strategies = {
            'lossless': LosslessCompressionStrategy(),
            'lossy': LossyCompressionStrategy(),
            'semantic': SemanticHashingStrategy()
        }

    def compress(self, data: Any, strategy: str = 'lossless') -> Any:
        if strategy not in self.strategies:
            raise ValueError(f"Unknown compression strategy: {strategy}")
        return self.strategies[strategy].compress(data)

    def decompress(self, data: Any, strategy: str = 'lossless') -> Any:
        if strategy not in self.strategies:
            raise ValueError(f"Unknown compression strategy: {strategy}")
        return self.strategies[strategy].decompress(data)