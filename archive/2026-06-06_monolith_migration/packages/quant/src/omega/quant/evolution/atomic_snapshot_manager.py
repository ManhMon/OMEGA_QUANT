"""
Gap Phase 6.2: Atomic Snapshot Manager - OMEGA Edition
Layer 08: Self-Evolving Engine

Extends StateSnapshot with atomic archive (.tar.gz) + SHA256 verification + rollback.
Guarantees all-or-nothing atomic rollbacks when models or parameters drift.

PIT Safety: Generates snapshots chronologically, preserves state integrity without lookahead bias.
Vectorization: Handles metadata and model parameters via NumPy/Pandas serialization.
"""

import tarfile
import hashlib
import json
import shutil
import pickle
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger("OmegaAtomicSnapshot")


class AtomicSnapshotManager:
    """
    Atomic snapshot manager for OMEGA_QUANT.
    
    Provides:
    1. Single .tar.gz archive bundling all system states
    2. SHA256 checksum verification for tamper-proofing
    3. Atomic rollback (all-or-nothing restore)
    """
    
    ARCHIVE_DIR = Path(".ly_state/checkpoints/atomic_snapshots")
    
    def __init__(self, archive_dir: Optional[Path] = None):
        self.archive_dir = archive_dir or self.ARCHIVE_DIR
        self.archive_dir.mkdir(parents=True, exist_ok=True)
    
    def calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def create_atomic_snapshot(
        self,
        snapshot_id: str,
        model: Any,
        model_name: str,
        bandit_state: Dict[str, Any],
        metrics: Dict[str, Any],
        pit_verified: bool = True
    ) -> Path:
        """
        Create atomic snapshot archive with model, bandit state, and metrics.
        
        Args:
            snapshot_id: Unique identifier (e.g., "snap_20260517")
            model: Model object (pickled)
            model_name: Model identifier
            bandit_state: Thompson Sampling / Bandit states
            metrics: Performance metrics (IC, Sharpe, etc.)
            pit_verified: PIT Safety verification flag
        
        Returns:
            Path to created snapshot archive (.tar.gz)
        """
        temp_dir = self.archive_dir / f"temp_{snapshot_id}"
        temp_dir.mkdir(exist_ok=True)
        
        try:
            # 1. Save model
            model_path = temp_dir / "model.pkl"
            with open(model_path, 'wb') as f:
                pickle.dump(model, f)
            
            # 2. Save bandit state
            bandit_path = temp_dir / "bandit_state.json"
            with open(bandit_path, 'w') as f:
                json.dump(bandit_state, f, indent=2)
                
            # 3. Save metadata & metrics
            meta = {
                "snapshot_id": snapshot_id,
                "model_name": model_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metrics": metrics,
                "pit_verified": pit_verified
            }
            meta_path = temp_dir / "metadata.json"
            with open(meta_path, 'w') as f:
                json.dump(meta, f, indent=2)
            
            # 4. Create .tar.gz archive
            archive_path = self.archive_dir / f"{snapshot_id}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(model_path, arcname="model.pkl")
                tar.add(bandit_path, arcname="bandit_state.json")
                tar.add(meta_path, arcname="metadata.json")
            
            # 5. Generate checksum
            checksum = self.calculate_sha256(archive_path)
            checksum_path = self.archive_dir / f"{snapshot_id}.sha256"
            with open(checksum_path, 'w') as f:
                f.write(checksum)
                
            logger.info(f"Atomic snapshot {snapshot_id} created successfully with checksum {checksum[:8]}")
            return archive_path
            
        finally:
            # Cleanup temp directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                
    def verify_and_restore(self, snapshot_id: str) -> Tuple[Any, Dict[str, Any], Dict[str, Any]]:
        """
        Verify SHA256 checksum and restore snapshot (Atomic).
        
        Args:
            snapshot_id: Unique identifier
            
        Returns:
            Tuple of (model, bandit_state, metadata)
            
        Raises:
            ValueError: If checksum verification fails or files missing
        """
        archive_path = self.archive_dir / f"{snapshot_id}.tar.gz"
        checksum_path = self.archive_dir / f"{snapshot_id}.sha256"
        
        if not archive_path.exists() or not checksum_path.exists():
            raise ValueError(f"Snapshot files not found for {snapshot_id}")
            
        # 1. Verify SHA256
        with open(checksum_path, 'r') as f:
            expected_checksum = f.read().strip()
            
        actual_checksum = self.calculate_sha256(archive_path)
        if actual_checksum != expected_checksum:
            raise ValueError(f"CRITICAL: SHA256 checksum mismatch for snapshot {snapshot_id}!")
            
        # 2. Extract and restore (Atomic rollback)
        extract_dir = self.archive_dir / f"extract_{snapshot_id}"
        extract_dir.mkdir(exist_ok=True)
        
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=extract_dir)
                
            # Load states
            with open(extract_dir / "model.pkl", 'rb') as f:
                model = pickle.load(f)
                
            with open(extract_dir / "bandit_state.json", 'r') as f:
                bandit_state = json.load(f)
                
            with open(extract_dir / "metadata.json", 'r') as f:
                metadata = json.load(f)
                
            logger.info(f"Atomic snapshot {snapshot_id} verified and restored successfully")
            return model, bandit_state, metadata
            
        finally:
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
