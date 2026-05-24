import hashlib
import zlib
import json
from typing import Any, Dict, Protocol


class MemoryCompressorStrategy(Protocol):
    def compress(self, data: Any) -> Dict[str, Any]:
        ...

    def decompress(self, compressed_data: Dict[str, Any]) -> Any:
        ...


class SemanticHashingStrategy(MemoryCompressorStrategy):
    """Compresses large text by storing a semantic hash and a reference."""
    def __init__(self, prefix: str = "semhash:"):
        self.prefix = prefix

    def compress(self, data: Any) -> Dict[str, Any]:
        if not isinstance(data, str):
            return {"type": "raw", "data": data}
        
        # In a real system, this would use an embedding model or LSH.
        # Here we use SHA256 as a placeholder for a semantic signature.
        hash_obj = hashlib.sha256(data.encode('utf-8'))
        sig = f"{self.prefix}{hash_obj.hexdigest()}"
        
        return {
            "type": "semantic_hash",
            "hash": sig,
            "original_length": len(data)
        }

    def decompress(self, compressed_data: Dict[str, Any]) -> Any:
        if compressed_data.get("type") == "raw":
             return compressed_data.get("data")
        # Semantic hashing is inherently lossy for decompression without a store.
        # We return the hash reference.
        return f"<{compressed_data.get('hash')}>"


class LosslessCompressionStrategy(MemoryCompressorStrategy):
    """Compresses data losslessly using zlib."""
    def compress(self, data: Any) -> Dict[str, Any]:
        if isinstance(data, dict) or isinstance(data, list):
            data_str = json.dumps(data)
        elif isinstance(data, str):
            data_str = data
        else:
             data_str = str(data)

        compressed_bytes = zlib.compress(data_str.encode('utf-8'))
        import base64
        b64_str = base64.b64encode(compressed_bytes).decode('utf-8')
        return {
            "type": "lossless",
            "data": b64_str
        }

    def decompress(self, compressed_data: Dict[str, Any]) -> Any:
        if compressed_data.get("type") != "lossless":
            raise ValueError("Invalid compression type for LosslessStrategy")
            
        import base64
        b64_str = compressed_data["data"]
        compressed_bytes = base64.b64decode(b64_str)
        decompressed_bytes = zlib.decompress(compressed_bytes)
        
        try:
            return json.loads(decompressed_bytes.decode('utf-8'))
        except json.JSONDecodeError:
            return decompressed_bytes.decode('utf-8')


class LossyCompressionStrategy(MemoryCompressorStrategy):
    """Compresses data by summarizing or truncating (lossy)."""
    def __init__(self, max_length: int = 100):
        self.max_length = max_length

    def compress(self, data: Any) -> Dict[str, Any]:
        if isinstance(data, str):
            if len(data) > self.max_length:
                 truncated = data[:self.max_length] + "..."
                 return {"type": "lossy", "data": truncated, "original_length": len(data)}
            return {"type": "lossy", "data": data, "original_length": len(data)}
        
        if isinstance(data, list):
             if len(data) > 5:
                  return {"type": "lossy", "data": data[:5] + ["..."], "original_length": len(data)}
             return {"type": "lossy", "data": data, "original_length": len(data)}

        # Fallback for dicts/other
        return {"type": "lossy", "data": str(data)[:self.max_length], "original_length": len(str(data))}

    def decompress(self, compressed_data: Dict[str, Any]) -> Any:
        return compressed_data.get("data")


class MemoryCompressor:
    """Facade for applying different compression strategies."""
    def __init__(self):
        self.strategies: Dict[str, MemoryCompressorStrategy] = {
            "semantic": SemanticHashingStrategy(),
            "lossless": LosslessCompressionStrategy(),
            "lossy": LossyCompressionStrategy()
        }

    def compress(self, data: Any, strategy_name: str = "lossless") -> Dict[str, Any]:
        if strategy_name not in self.strategies:
            raise ValueError(f"Unknown strategy: {strategy_name}")
        
        result = self.strategies[strategy_name].compress(data)
        result["strategy"] = strategy_name
        return result

    def decompress(self, compressed_data: Dict[str, Any]) -> Any:
        strategy_name = compressed_data.get("strategy")
        if not strategy_name or strategy_name not in self.strategies:
             raise ValueError(f"Unknown or missing strategy in compressed data: {strategy_name}")
        return self.strategies[strategy_name].decompress(compressed_data)
