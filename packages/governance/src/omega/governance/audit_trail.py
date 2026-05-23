"""
Immutable Audit Trail - OMEGA_QUANT Phase 8.
"""

import json
import hashlib
import time
from typing import Dict, Any, List
from pathlib import Path

class AuditLogger:
    """Immutable audit logger with hash chaining."""
    
    def __init__(self, log_dir: str = ".ly_state/logs/audit"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_file = self.log_dir / "audit.jsonl"
        
        # Initialize hash chain
        self.last_hash = "INIT"
        self._load_last_hash()
        
    def _load_last_hash(self):
        if not self.current_file.exists():
            return
            
        try:
            with open(self.current_file, "r") as f:
                lines = f.readlines()
                if lines:
                    last_entry = json.loads(lines[-1])
                    self.last_hash = last_entry.get("hash", "INIT")
        except Exception:
            pass
            
    def log_action(self, actor: str, action: str, resource: str, details: Dict[str, Any] = None) -> str:
        """Log an action and return its hash."""
        entry = {
            "timestamp": time.time(),
            "actor": actor,
            "action": action,
            "resource": resource,
            "details": details or {},
            "prev_hash": self.last_hash
        }
        
        # Compute hash
        entry_str = json.dumps(entry, sort_keys=True)
        current_hash = hashlib.sha256(entry_str.encode()).hexdigest()
        entry["hash"] = current_hash
        
        # Append to file
        with open(self.current_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
            
        self.last_hash = current_hash
        return current_hash
        
    def verify_chain(self) -> bool:
        """Verify the integrity of the audit log."""
        if not self.current_file.exists():
            return True
            
        expected_prev = "INIT"
        
        with open(self.current_file, "r") as f:
            for line in f:
                entry = json.loads(line)
                
                if entry.get("prev_hash") != expected_prev:
                    return False
                    
                # Recompute hash
                saved_hash = entry.pop("hash")
                entry_str = json.dumps(entry, sort_keys=True)
                recomputed_hash = hashlib.sha256(entry_str.encode()).hexdigest()
                
                if recomputed_hash != saved_hash:
                    return False
                    
                expected_prev = saved_hash
                entry["hash"] = saved_hash  # Restore
                
        return True
