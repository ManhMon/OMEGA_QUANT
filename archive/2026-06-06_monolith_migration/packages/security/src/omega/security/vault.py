"""
Secrets Vault - OMEGA_QUANT Phase 8.
Simple encrypted storage for API keys and credentials.
"""

from __future__ import annotations
import base64
import os
from typing import Dict, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class SecretsVault:
    """Encrypted secrets storage using Fernet symmetric encryption."""
    
    def __init__(self, master_key: Optional[bytes] = None):
        """
        Initialize vault.
        
        Args:
            master_key: 32-byte key. If None, generates new key.
        """
        if master_key is None:
            self.master_key = Fernet.generate_key()
        else:
            self.master_key = master_key
            
        self.fernet = Fernet(self.master_key)
        self._secrets: Dict[str, str] = {}
        
    def store_secret(self, name: str, value: str) -> None:
        """Encrypt and store a secret."""
        encrypted = self.fernet.encrypt(value.encode())
        self._secrets[name] = base64.urlsafe_b64encode(encrypted).decode()
        
    def get_secret(self, name: str) -> Optional[str]:
        """Retrieve and decrypt a secret."""
        if name not in self._secrets:
            return None
        encrypted = base64.urlsafe_b64decode(self._secrets[name])
        return self.fernet.decrypt(encrypted).decode()
        
    def list_secrets(self) -> list:
        """List all secret names."""
        return list(self._secrets.keys())
        
    def delete_secret(self, name: str) -> bool:
        """Delete a secret. Returns True if existed."""
        if name in self._secrets:
            del self._secrets[name]
            return True
        return False
