"""
Compression Layer - Context Compression
Compresses context while preserving core decisions, contracts, and metrics.
Removes noise while maintaining critical information.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class CompressionResult:
    """Result of context compression."""
    original_size: int
    compressed_size: int
    compression_ratio: float
    preserved_elements: List[str]
    removed_elements: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class Compression:
    """
    Context Compression Layer.
    Keeps core decisions, contracts, metrics while removing noise.
    """

    # Critical keywords that should always be preserved
    CRITICAL_KEYWORDS = {
        'contract', 'metric', 'decision', 'policy', 'constraint',
        'requirement', 'violation', 'error', 'failure', 'success',
        'rollback', 'commit', 'audit', 'compliance', 'sod',
        'separation', 'duty', 'approval', 'verification'
    }

    # Noise patterns to remove
    NOISE_PATTERNS = {
        'debug', 'trace', 'verbose', 'info', 'log',
        'temporary', 'temp', 'scratch', 'draft'
    }

    def __init__(self):
        pass

    def _is_critical(self, text: str) -> bool:
        """Check if text contains critical keywords."""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.CRITICAL_KEYWORDS)

    def _is_noise(self, text: str) -> bool:
        """Check if text is likely noise."""
        text_lower = text.lower()
        return any(pattern in text_lower for pattern in self.NOISE_PATTERNS)

    def compress_episode(self, episode_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compress episode data, keeping critical information.
        """
        compressed = {
            'episode_id': episode_data.get('episode_id'),
            'task_type': episode_data.get('task_type'),
            'outcome': episode_data.get('outcome'),
            'timestamp': episode_data.get('timestamp'),
            'duration_seconds': episode_data.get('duration_seconds')
        }

        # Preserve critical context
        context = episode_data.get('context', {})
        compressed['context'] = self._compress_dict(context)

        # Compress actions - keep only critical ones
        actions = episode_data.get('actions', [])
        compressed['actions'] = [
            action for action in actions
            if self._is_critical(json.dumps(action))
        ]

        # Always preserve metrics
        compressed['metrics'] = episode_data.get('metrics', {})

        # Compress metadata
        metadata = episode_data.get('metadata', {})
        compressed['metadata'] = self._compress_dict(metadata)

        return compressed

    def compress_knowledge(self, knowledge_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compress knowledge entry, keeping core content.
        """
        compressed = {
            'entry_id': knowledge_data.get('entry_id'),
            'content': knowledge_data.get('content'),
            'category': knowledge_data.get('category'),
            'confidence': knowledge_data.get('confidence'),
            'timestamp': knowledge_data.get('timestamp')
        }

        # Keep only high-value tags
        tags = knowledge_data.get('tags', [])
        compressed['tags'] = [
            tag for tag in tags
            if not self._is_noise(tag)
        ]

        # Compress metadata
        metadata = knowledge_data.get('metadata', {})
        compressed['metadata'] = self._compress_dict(metadata)

        return compressed

    def compress_policy(self, policy_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compress policy entry, preserving decision logic.
        """
        # Policies are already compact - preserve most fields
        compressed = {
            'policy_id': policy_data.get('policy_id'),
            'policy_type': policy_data.get('policy_type'),
            'context': self._compress_dict(policy_data.get('context', {})),
            'action': policy_data.get('action'),
            'rationale': policy_data.get('rationale'),
            'applied_count': policy_data.get('applied_count'),
            'success_count': policy_data.get('success_count'),
            'failure_count': policy_data.get('failure_count'),
            'last_applied': policy_data.get('last_applied')
        }

        return compressed

    def compress_failure(self, failure_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compress failure entry, keeping error details.
        """
        compressed = {
            'failure_id': failure_data.get('failure_id'),
            'failure_type': failure_data.get('failure_type'),
            'error_message': failure_data.get('error_message'),
            'timestamp': failure_data.get('timestamp'),
            'task_type': failure_data.get('task_type'),
            'recurrence_count': failure_data.get('recurrence_count'),
            'resolved': failure_data.get('resolved')
        }

        # Compress stack trace - keep first and last lines
        stack_trace = failure_data.get('stack_trace', '')
        if stack_trace:
            lines = stack_trace.split('\n')
            if len(lines) > 10:
                compressed['stack_trace'] = '\n'.join(lines[:3] + ['...'] + lines[-3:])
            else:
                compressed['stack_trace'] = stack_trace

        # Compress context
        context = failure_data.get('context', {})
        compressed['context'] = self._compress_dict(context)

        return compressed

    def _compress_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compress dictionary by removing noise and keeping critical fields.
        """
        compressed = {}

        for key, value in data.items():
            # Always keep if key is critical
            if self._is_critical(key):
                compressed[key] = value
                continue

            # Skip if key is noise
            if self._is_noise(key):
                continue

            # For string values, check content
            if isinstance(value, str):
                if self._is_critical(value):
                    compressed[key] = value
                elif not self._is_noise(value):
                    # Keep non-noise strings
                    compressed[key] = value
            # Keep non-string values (numbers, bools, etc.)
            elif isinstance(value, (int, float, bool)):
                compressed[key] = value
            # Recursively compress nested dicts
            elif isinstance(value, dict):
                nested = self._compress_dict(value)
                if nested:
                    compressed[key] = nested
            # Keep lists if they contain critical info
            elif isinstance(value, list):
                if any(self._is_critical(str(item)) for item in value):
                    compressed[key] = value

        return compressed

    def compress_context(
        self,
        context_data: Dict[str, Any],
        preserve_keys: Optional[Set[str]] = None
    ) -> CompressionResult:
        """
        Compress arbitrary context data.
        
        Args:
            context_data: Context to compress
            preserve_keys: Additional keys to always preserve
        
        Returns:
            CompressionResult with compression statistics
        """
        preserve_keys = preserve_keys or set()
        
        original_json = json.dumps(context_data)
        original_size = len(original_json)

        compressed = {}
        preserved = []
        removed = []

        for key, value in context_data.items():
            # Always preserve specified keys
            if key in preserve_keys:
                compressed[key] = value
                preserved.append(key)
                continue

            # Check if critical
            if self._is_critical(key) or self._is_critical(str(value)):
                compressed[key] = value
                preserved.append(key)
            # Check if noise
            elif self._is_noise(key) or self._is_noise(str(value)):
                removed.append(key)
            # Keep structured data
            elif isinstance(value, (dict, list)):
                if isinstance(value, dict):
                    nested = self._compress_dict(value)
                    if nested:
                        compressed[key] = nested
                        preserved.append(key)
                    else:
                        removed.append(key)
                else:
                    compressed[key] = value
                    preserved.append(key)
            # Keep primitive values
            else:
                compressed[key] = value
                preserved.append(key)

        compressed_json = json.dumps(compressed)
        compressed_size = len(compressed_json)
        compression_ratio = (
            1.0 - (compressed_size / original_size)
            if original_size > 0 else 0.0
        )

        return CompressionResult(
            original_size=original_size,
            compressed_size=compressed_size,
            compression_ratio=compression_ratio,
            preserved_elements=preserved,
            removed_elements=removed,
            metadata={
                'compression_timestamp': datetime.utcnow().isoformat(),
                'preserved_count': len(preserved),
                'removed_count': len(removed)
            }
        )

    def batch_compress(
        self,
        items: List[Dict[str, Any]],
        item_type: str
    ) -> tuple[List[Dict[str, Any]], CompressionResult]:
        """
        Compress a batch of items.
        
        Args:
            items: List of items to compress
            item_type: Type of items (episode, knowledge, policy, failure)
        
        Returns:
            Tuple of (compressed_items, compression_result)
        """
        compress_func = {
            'episode': self.compress_episode,
            'knowledge': self.compress_knowledge,
            'policy': self.compress_policy,
            'failure': self.compress_failure
        }.get(item_type, lambda x: x)

        original_json = json.dumps(items)
        original_size = len(original_json)

        compressed_items = [compress_func(item) for item in items]

        compressed_json = json.dumps(compressed_items)
        compressed_size = len(compressed_json)
        compression_ratio = (
            1.0 - (compressed_size / original_size)
            if original_size > 0 else 0.0
        )

        result = CompressionResult(
            original_size=original_size,
            compressed_size=compressed_size,
            compression_ratio=compression_ratio,
            preserved_elements=[item_type],
            removed_elements=[],
            metadata={
                'item_type': item_type,
                'item_count': len(items),
                'compression_timestamp': datetime.utcnow().isoformat()
            }
        )

        logger.info(
            f"Compressed {len(items)} {item_type} items: "
            f"{original_size} -> {compressed_size} bytes "
            f"({compression_ratio:.1%} reduction)"
        )

        return compressed_items, result

    def extract_core_decisions(self, context_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract only core decisions from context.
        """
        decisions = []

        def extract_recursive(data: Any, path: str = "") -> None:
            if isinstance(data, dict):
                for key, value in data.items():
                    current_path = f"{path}.{key}" if path else key
                    if 'decision' in key.lower() or 'policy' in key.lower():
                        decisions.append({
                            'path': current_path,
                            'value': value
                        })
                    extract_recursive(value, current_path)
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    extract_recursive(item, f"{path}[{i}]")

        extract_recursive(context_data)
        return decisions

    def extract_metrics(self, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract all metrics from context.
        """
        metrics = {}

        def extract_recursive(data: Any, path: str = "") -> None:
            if isinstance(data, dict):
                for key, value in data.items():
                    current_path = f"{path}.{key}" if path else key
                    if 'metric' in key.lower() or isinstance(value, (int, float)):
                        metrics[current_path] = value
                    extract_recursive(value, current_path)
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    extract_recursive(item, f"{path}[{i}]")

        extract_recursive(context_data)
        return metrics
