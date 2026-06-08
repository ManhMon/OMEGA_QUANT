"""OMEGA_QUANT Memory & Evolution Engine (Phase 6)"""

from .memory_archive import AlphaMemory, ErrorMemory, create_memory_archive
from .memory_retrieval import AlphaRetriever, create_retriever
from .episodic_memory import EpisodicMemory, Episode
from .semantic_memory import SemanticMemory, KnowledgeEntry
from .policy_memory import PolicyMemory, PolicyEntry
from .failure_memory import FailureMemory, FailureEntry
from .compression import Compression, CompressionResult

__all__ = [
    "AlphaMemory",
    "ErrorMemory",
    "AlphaRetriever",
    "create_memory_archive",
    "create_retriever",
    "EpisodicMemory",
    "Episode",
    "SemanticMemory",
    "KnowledgeEntry",
    "PolicyMemory",
    "PolicyEntry",
    "FailureMemory",
    "FailureEntry",
    "Compression",
    "CompressionResult",
]

try:
    from . import context_assembler
except ImportError:
    pass

try:
    from . import memory_module
except ImportError:
    pass
