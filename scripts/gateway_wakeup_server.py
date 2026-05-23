#!/usr/bin/env python3
# gateway_wakeup_server.py
# Purpose: HTTP server that acts as OpenClaw gateway callback endpoint
# Listens on localhost:8080 and triggers pending tasks when woken up

import json
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any
import threading

# Setup workspace paths
WORKSPACE = Path("C:/Users/GHC/.openclaw/workspace/omega")
sys.path.insert(0, str(WORKSPACE))

LOG_DIR = WORKSPACE / ".ly_state" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "gateway_server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class WakeupHandler(BaseHTTPRequestHandler):
    """HTTP handler for wakeup endpoint"""
    
    def do_POST(self):
        """Handle POST to /callback/wakeup"""
        if self.path == "/callback/wakeup":
            try:
                # Trigger pending tasks
                result = self.trigger_pending_tasks()
                
                # Send response
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                
                response_body = json.dumps(result)
                self.wfile.write(response_body.encode())
                
                logger.info(f"Wakeup triggered: {result['pending_tasks']} pending tasks")
                
            except Exception as e:
                logger.error(f"Error handling wakeup: {e}")
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def trigger_pending_tasks(self) -> Dict[str, Any]:
        """Check for pending tasks and trigger wakeup events"""
        active_tasks_file = WORKSPACE / ".ly_state" / "session" / "active_tasks.json"
        
        pending_count = 0
        triggered_tasks = []
        
        try:
            if active_tasks_file.exists():
                with open(active_tasks_file) as f:
                    data = json.load(f)
                
                # Handle both dict and list formats
                if isinstance(data, dict):
                    # Single task format
                    if data.get("status") == "in_progress":
                        pending_count = 1
                        triggered_tasks.append(data.get("task_id", "unknown"))
                        logger.info(f"Triggered task: {data.get('task_id')} (Phase: {data.get('phase')})")
                elif isinstance(data, list):
                    # Multiple tasks format
                    for task in data:
                        if isinstance(task, dict) and task.get("status") == "in_progress":
                            pending_count += 1
                            triggered_tasks.append(task.get("task_id", "unknown"))
                            logger.info(f"Triggered task: {task.get('task_id')} (Phase: {task.get('phase')})")
        
        except Exception as e:
            logger.error(f"Error reading active tasks: {e}")
        
        return {
            "status": "OK",
            "pending_tasks": pending_count,
            "triggered": triggered_tasks,
            "timestamp": datetime.now().isoformat(),
        }
    
    def log_message(self, format, *args):
        """Suppress default HTTP logging"""
        pass


def run_server(host="localhost", port=8080):
    """Run HTTP server"""
    server = HTTPServer((host, port), WakeupHandler)
    logger.info(f"Gateway wakeup server listening on {host}:{port}")
    logger.info("Endpoint: POST http://localhost:8080/callback/wakeup")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
        server.shutdown()


if __name__ == "__main__":
    run_server()
