"""
Neural Memory - Error Learning and Recommendation Engine.
Migrated to OMEGA_QUANT Phase 6.
"""

import json
import os
import re
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger("OmegaNeuralMemory")

class NeuralMemory:
    """Learns from past errors and provides fix recommendations using semantic hashing."""
    
    def __init__(
        self,
        audit_logs_dir: str = ".ly_state/logs",
        resolution_log_file: str = "OMEGA_ERROR_RESOLUTIONS_LOG.md"
    ):
        self.audit_logs_dir = Path(audit_logs_dir)
        self.resolution_log_file = Path(resolution_log_file)
        self.embeddings_cache: Dict[str, List[float]] = {}
        self.error_database: List[Dict[str, Any]] = []
        
        # Ensure directories exist
        self.audit_logs_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.resolution_log_file.exists():
            self._initialize_resolution_log()
        
        self._load_error_database()
    
    def _initialize_resolution_log(self) -> None:
        """Initialize empty resolution log file."""
        initial_content = """# OMEGA Error Resolutions Log
## Purpose: Institutional memory for error recovery.
---
## Error Entries
"""
        with open(self.resolution_log_file, 'w', encoding='utf-8') as f:
            f.write(initial_content)
    
    def _load_error_database(self) -> None:
        """Load error patterns from audit logs."""
        self.error_database.clear()
        if not self.audit_logs_dir.exists():
            return
            
        for audit_file in self.audit_logs_dir.glob("audit_*.json"):
            try:
                with open(audit_file, 'r', encoding='utf-8') as f:
                    audit_data = json.load(f)
                findings = audit_data.get("findings", [])
                
                # Extract audit date (try top-level first, then finding-level)
                audit_date = audit_data.get("audit_date")
                
                for finding in findings:
                    # Fallback to finding-level date if top-level missing
                    finding_date = finding.get("audit_date", audit_date)
                    
                    self.error_database.append({
                        "error_id": finding.get("id", "UNKNOWN"),
                        "title": finding.get("title", ""),
                        "description": finding.get("fix_description", finding.get("title", "")),
                        "severity": finding.get("severity", "UNKNOWN"),
                        "date": finding_date or "UNKNOWN"
                    })
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON in {audit_file}: {e}")
            except Exception as e:
                logger.error(f"Failed to load audit log {audit_file}: {e}")
    
    def _compute_embedding(self, text: str) -> List[float]:
        """Compute 128-dim hash-based embedding."""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if text_hash in self.embeddings_cache:
            return self.embeddings_cache[text_hash]
            
        tokens = re.findall(r'\w+', text.lower())
        embedding = [0.0] * 128
        for token in tokens:
            token_hash = int(hashlib.md5(token.encode()).hexdigest(), 16)
            embedding[token_hash % 128] += 1.0
            
        magnitude = sum(x * x for x in embedding) ** 0.5
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]
        self.embeddings_cache[text_hash] = embedding
        return embedding
    
    def suggest_fix(self, error_description: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Suggest fixes based on cosine similarity."""
        if not self.error_database:
            return []
            
        query_vec = self._compute_embedding(error_description)
        results = []
        for error in self.error_database:
            if "embedding" not in error:
                error["embedding"] = self._compute_embedding(f"{error['title']} {error['description']}")
            
            sim = sum(a * b for a, b in zip(query_vec, error["embedding"]))
            results.append((sim, error))
            
        results.sort(key=lambda x: x[0], reverse=True)
        return [{"similarity": round(sim, 3), "error": err["error_id"], "title": err["title"]} 
                for sim, err in results[:top_k]]
