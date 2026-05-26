"""REST API Routes - OMEGA_QUANT API Server (stdlib only).

Purpose:
    REST API routes for OMEGA_QUANT system using only Python stdlib.
    No Flask/FastAPI dependencies - pure http.server implementation.

Endpoints:
    GET  /health              - Health check
    POST /tasks               - Submit task
    GET  /tasks/{id}          - Task status
    GET  /portfolio           - Portfolio snapshot
    GET  /risk                - Risk metrics
    GET  /signals             - Alpha signals
    POST /backtest            - Run backtest

Architecture:
    - Uses http.server.BaseHTTPRequestHandler
    - JSON request/response
    - State read from .ly_state/
    - Task submission to PriorityTaskQueue

Contract:
    - Input: HTTP requests (GET/POST)
    - Output: JSON responses

Reference:
    - Spec Section 3: Repository Layout (apps/api/)
    - TEAM_ARCHITECTURE.md: Backend Engineer (Role 9)

Author: Backend Engineer (Role 9)
Date: 2026-05-26
Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

# Add src to path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

from omega.infra.task_queue import PriorityTaskQueue, TaskPriority

logger = logging.getLogger(__name__)


class APIConfig:
    """API server configuration."""
    
    HOST = "0.0.0.0"
    PORT = 5000
    STATE_DIR = WORKSPACE_ROOT / ".ly_state"
    SESSION_DIR = STATE_DIR / "session"


class APIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OMEGA_QUANT API.
    
    Routes:
        GET  /health              - Health check
        POST /tasks               - Submit task
        GET  /tasks/{id}          - Task status
        GET  /portfolio           - Portfolio snapshot
        GET  /risk                - Risk metrics
        GET  /signals             - Alpha signals
        POST /backtest            - Run backtest
    """
    
    # Shared task queue (set by server)
    task_queue: Optional[PriorityTaskQueue] = None
    
    def _set_headers(self, status_code: int = 200, content_type: str = "application/json") -> None:
        """Set response headers."""
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def _send_json(self, data: Any, status_code: int = 200) -> None:
        """Send JSON response."""
        self._set_headers(status_code)
        response = json.dumps(data, indent=2)
        self.wfile.write(response.encode("utf-8"))
    
    def _send_error_json(self, message: str, status_code: int = 400) -> None:
        """Send JSON error response."""
        self._send_json({"error": message}, status_code)
    
    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        """Read and parse JSON request body."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                return {}
            
            body = self.rfile.read(content_length)
            return json.loads(body.decode("utf-8"))
        except Exception as exc:
            logger.error("Failed to parse JSON body: %s", exc)
            return None
    
    def _read_state_file(self, filename: str) -> Optional[Dict[str, Any]]:
        """Read JSON state file from .ly_state/session/."""
        filepath = APIConfig.SESSION_DIR / filename
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception as exc:
            logger.error("Failed to read state file %s: %s", filename, exc)
            return None
    
    def do_OPTIONS(self) -> None:
        """Handle OPTIONS request (CORS preflight)."""
        self._set_headers(204)
    
    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        
        # Route: GET /health
        if path == "/health":
            self._handle_health()
        
        # Route: GET /tasks
        elif path == "/tasks":
            self._handle_list_tasks()
        
        # Route: GET /tasks/{id}
        elif path.startswith("/tasks/"):
            task_id = path.split("/")[-1]
            self._handle_get_task(task_id)
        
        # Route: GET /portfolio
        elif path == "/portfolio":
            self._handle_get_portfolio()
        
        # Route: GET /risk
        elif path == "/risk":
            self._handle_get_risk()
        
        # Route: GET /signals
        elif path == "/signals":
            self._handle_get_signals()
        
        else:
            self._send_error_json("Not Found", 404)
    
    def do_POST(self) -> None:
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        
        # Route: POST /tasks
        if path == "/tasks":
            self._handle_submit_task()
        
        # Route: POST /backtest
        elif path == "/backtest":
            self._handle_run_backtest()
        
        else:
            self._send_error_json("Not Found", 404)
    
    def _handle_health(self) -> None:
        """GET /health - Health check endpoint."""
        response = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": "1.0.0",
            "service": "OMEGA_QUANT API",
        }
        self._send_json(response)
    
    def _handle_list_tasks(self) -> None:
        """GET /tasks - List active tasks."""
        tasks_data = self._read_state_file("active_tasks.json")
        
        if tasks_data is None:
            self._send_json([])
            return
        
        # Convert to list format
        tasks_list = [
            {
                "task_id": task_id,
                **task_info,
            }
            for task_id, task_info in tasks_data.items()
        ]
        
        self._send_json(tasks_list)
    
    def _handle_get_task(self, task_id: str) -> None:
        """GET /tasks/{id} - Get task status."""
        tasks_data = self._read_state_file("active_tasks.json")
        
        if tasks_data is None or task_id not in tasks_data:
            self._send_error_json(f"Task not found: {task_id}", 404)
            return
        
        task_info = tasks_data[task_id]
        task_info["task_id"] = task_id
        
        self._send_json(task_info)
    
    def _handle_submit_task(self) -> None:
        """POST /tasks - Submit a new task."""
        body = self._read_json_body()
        
        if body is None:
            self._send_error_json("Invalid JSON body", 400)
            return
        
        # Validate required fields
        task_type = body.get("task_type")
        if not task_type:
            self._send_error_json("Missing required field: task_type", 400)
            return
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Determine priority
        priority_str = body.get("priority", "NORMAL")
        try:
            priority = TaskPriority[priority_str]
        except KeyError:
            priority = TaskPriority.NORMAL
        
        # Submit to task queue
        if self.task_queue is not None:
            try:
                payload = {
                    "task_type": task_type,
                    "params": body.get("params", {}),
                    "submitted_at": time.time(),
                }
                
                queue_task_id = self.task_queue.put(
                    payload=payload,
                    priority=priority,
                )
                
                response = {
                    "task_id": queue_task_id,
                    "status": "submitted",
                    "task_type": task_type,
                    "priority": priority_str,
                    "submitted_at": datetime.utcnow().isoformat() + "Z",
                }
                
                self._send_json(response, 201)
                
            except Exception as exc:
                logger.error("Failed to submit task: %s", exc)
                self._send_error_json(f"Failed to submit task: {exc}", 500)
        else:
            # Queue not available, return placeholder
            response = {
                "task_id": task_id,
                "status": "submitted",
                "task_type": task_type,
                "priority": priority_str,
                "submitted_at": datetime.utcnow().isoformat() + "Z",
                "note": "Task queue not initialized (placeholder mode)",
            }
            self._send_json(response, 201)
    
    def _handle_get_portfolio(self) -> None:
        """GET /portfolio - Get portfolio snapshot."""
        # Placeholder: In production, read from portfolio state
        portfolio = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total_value": 2_000_000_000.0,
            "positions": [
                {"ticker": "VNM", "weight": 0.15, "value": 300_000_000.0},
                {"ticker": "VCB", "weight": 0.12, "value": 240_000_000.0},
                {"ticker": "HPG", "weight": 0.10, "value": 200_000_000.0},
            ],
            "cash": 1_260_000_000.0,
            "num_positions": 3,
        }
        
        self._send_json(portfolio)
    
    def _handle_get_risk(self) -> None:
        """GET /risk - Get risk metrics."""
        # Placeholder: In production, read from risk state
        risk_metrics = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "portfolio_volatility": 0.025,
            "max_drawdown": 0.08,
            "sharpe_ratio": 1.85,
            "var_95": 0.032,
            "concentration_risk": {
                "max_single_position": 0.15,
                "top_5_concentration": 0.55,
            },
            "risk_limits": {
                "max_concentration_per_stock": 0.25,
                "max_adv_percentage": 0.40,
                "alert_drawdown_threshold": 0.10,
            },
            "status": "within_limits",
        }
        
        self._send_json(risk_metrics)
    
    def _handle_get_signals(self) -> None:
        """GET /signals - Get alpha signals."""
        # Placeholder: In production, read from alpha state
        signals = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "num_signals": 42,
            "top_signals": [
                {"ticker": "VNM", "alpha_score": 0.085, "ic": 0.042},
                {"ticker": "VCB", "alpha_score": 0.072, "ic": 0.038},
                {"ticker": "HPG", "alpha_score": 0.068, "ic": 0.035},
                {"ticker": "VHM", "alpha_score": 0.061, "ic": 0.032},
                {"ticker": "GAS", "alpha_score": 0.058, "ic": 0.030},
            ],
            "mean_ic": 0.035,
            "signal_quality": "high",
        }
        
        self._send_json(signals)
    
    def _handle_run_backtest(self) -> None:
        """POST /backtest - Run backtest."""
        body = self._read_json_body()
        
        if body is None:
            self._send_error_json("Invalid JSON body", 400)
            return
        
        # Validate required fields
        start_date = body.get("start_date")
        end_date = body.get("end_date")
        
        if not start_date or not end_date:
            self._send_error_json("Missing required fields: start_date, end_date", 400)
            return
        
        # Submit backtest task
        if self.task_queue is not None:
            try:
                payload = {
                    "task_type": "backtest",
                    "params": {
                        "start_date": start_date,
                        "end_date": end_date,
                        "initial_capital": body.get("initial_capital", 2_000_000_000.0),
                        "allocation_method": body.get("allocation_method", "ic_weighted"),
                    },
                    "submitted_at": time.time(),
                }
                
                task_id = self.task_queue.put(
                    payload=payload,
                    priority=TaskPriority.HIGH,
                )
                
                response = {
                    "task_id": task_id,
                    "status": "submitted",
                    "backtest_params": {
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                    "submitted_at": datetime.utcnow().isoformat() + "Z",
                }
                
                self._send_json(response, 202)
                
            except Exception as exc:
                logger.error("Failed to submit backtest: %s", exc)
                self._send_error_json(f"Failed to submit backtest: {exc}", 500)
        else:
            # Queue not available, return placeholder
            response = {
                "task_id": str(uuid.uuid4()),
                "status": "submitted",
                "backtest_params": {
                    "start_date": start_date,
                    "end_date": end_date,
                },
                "submitted_at": datetime.utcnow().isoformat() + "Z",
                "note": "Task queue not initialized (placeholder mode)",
            }
            self._send_json(response, 202)
    
    def log_message(self, format: str, *args: Any) -> None:
        """Override to use logger instead of stderr."""
        logger.info("%s - %s", self.address_string(), format % args)


def run_server(
    host: str = APIConfig.HOST,
    port: int = APIConfig.PORT,
    task_queue: Optional[PriorityTaskQueue] = None,
) -> None:
    """Run the API server.
    
    Args:
        host: Host to bind to
        port: Port to bind to
        task_queue: Optional PriorityTaskQueue for task submission
    """
    # Set task queue on handler class
    APIHandler.task_queue = task_queue
    
    # Create server
    server = HTTPServer((host, port), APIHandler)
    
    logger.info("=" * 80)
    logger.info("OMEGA_QUANT API Server")
    logger.info("=" * 80)
    logger.info("Listening on http://%s:%d", host, port)
    logger.info("State directory: %s", APIConfig.STATE_DIR)
    logger.info("Task queue: %s", "enabled" if task_queue else "disabled (placeholder mode)")
    logger.info("=" * 80)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
        server.shutdown()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Create task queue
    task_queue = PriorityTaskQueue(max_workers=4)
    
    # Run server
    run_server(task_queue=task_queue)
