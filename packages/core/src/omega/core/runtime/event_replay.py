#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Event Replay & Idempotency Store
For OMEGA_QUANT Event Bus.

Stores all events in SQLite. Drops duplicate `event_id`s to ensure idempotency.
Supports time-based replay of historical events.

Author: DevOps Engineer (Role 11)
Date: 2026-05-24
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class EventStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    event_type TEXT,
                    payload TEXT
                )
            ''')
            
    def store_and_check_duplicate(self, event_id: str, timestamp: str, event_type: str, payload: Dict[str, Any]) -> bool:
        """
        Stores event. Returns True if successfully stored (new), False if duplicate (idempotent drop).
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO events (event_id, timestamp, event_type, payload) VALUES (?, ?, ?, ?)",
                    (event_id, timestamp, event_type, json.dumps(payload))
                )
                return True
        except sqlite3.IntegrityError:
            logger.warning(f"Idempotency Guard: Dropping duplicate event {event_id}")
            return False

    def replay_from(self, timestamp: str) -> List[Dict[str, Any]]:
        """Retrieve all events after a certain timestamp for replay."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM events WHERE timestamp >= ? ORDER BY timestamp ASC",
                (timestamp,)
            )
            return [dict(r) for r in cursor.fetchall()]