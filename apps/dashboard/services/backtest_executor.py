"""
Backtest Executor Service
Wraps backtest scripts with subprocess isolation and progress streaming.
"""
import subprocess
import threading
import queue
import json
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for backtest execution"""
    script_path: str = ""
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 1_000_000_000
    strategy: str = "multi_factor"
    slippage_bps: float = 10.0
    commission_bps: float = 20.0
    quick_mode: bool = False
    use_xgboost: bool = True
    top_n_symbols: int = 30
    n_folds: int = 8
    train_years: int = 3
    test_years: int = 1
    min_ic_threshold: float = 0.02
    top_n_alphas: int = 5
    return_horizon: int = 5
    stage2_top_n_stocks: int = 8
    stage2_rebalance_freq: int = 7
    stage2_sector_cap_pct: float = 0.30
    drawdown_control: bool = False
    drawdown_threshold: float = 0.05
    
    def to_args(self) -> list:
        """Convert config to command-line arguments with security validation"""
        from config.dashboard_config import SCRIPTS_DIR
        
        # Reject empty script path
        if not self.script_path or not self.script_path.strip():
            raise ValueError("script_path is empty")
        
        # Resolve and validate
        script_path = Path(self.script_path).resolve()
        
        # Must be a file, not a directory
        if not script_path.is_file():
            raise ValueError(f"Script not found or not a file: {self.script_path}")
        
        # Ensure script is within SCRIPTS_DIR to prevent path traversal
        try:
            script_path.relative_to(SCRIPTS_DIR.resolve())
        except ValueError:
            raise ValueError(f"Script must be within {SCRIPTS_DIR}, got {script_path}")
        
        args = ["python", str(script_path)]
        if not self.use_xgboost:
            args.append("--no-xgboost")
            
        # Add remaining configuration parameters
        args.extend([
            "--start-date", self.start_date,
            "--end-date", self.end_date,
            "--initial-capital", str(self.initial_capital),
            "--strategy", self.strategy,
            "--slippage-bps", str(self.slippage_bps),
            "--commission-bps", str(self.commission_bps),
        ])
        if self.quick_mode:
            args.append("--quick-mode")
        if self.drawdown_control:
            args.append("--drawdown-control")
        args.extend([
            "--drawdown-threshold", str(self.drawdown_threshold),
        ])
            
        return args


class BacktestExecutor:
    """Execute backtests in isolated subprocess with progress streaming"""
    
    def __init__(self, lock_file: Optional[Path] = None):
        self.lock_file = lock_file or Path(".ly_state/session/backtest.lock")
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self._process: Optional[subprocess.Popen] = None
        self._output_queue = queue.Queue()
        self._is_running = False
        self._progress_callback: Optional[Callable] = None
    
    def is_locked(self) -> bool:
        """Check if another backtest is running (with stale lock cleanup)"""
        self._cleanup_stale_lock()
        return self.lock_file.exists()
    
    def get_lock_info(self) -> Optional[Dict]:
        """Get information about current lock"""
        if not self.lock_file.exists():
            return None
        
        try:
            with open(self.lock_file, 'r') as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.warning(f"Failed to read lock file: {e}")
            return {"pid": "unknown", "timestamp": "unknown"}
    
    def _cleanup_stale_lock(self):
        """Clean up lock file if the process that created it is no longer running"""
        import os
        import sys
        if not self.lock_file.exists():
            return
        try:
            with open(self.lock_file, 'r') as f:
                data = json.load(f)
            pid = int(data.get("pid", 0))
            if pid > 0:
                running = False
                try:
                    import psutil
                    proc = psutil.Process(pid)
                    # Verify it is actually a python or streamlit dashboard process
                    cmdline = " ".join(proc.cmdline()).lower()
                    name = proc.name().lower()
                    if "python" in name or "python" in cmdline or "streamlit" in cmdline:
                        running = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    running = False
                except ImportError:
                    # Fallback to legacy OS checks if psutil is not available
                    if sys.platform == "win32":
                        import ctypes
                        PROCESS_QUERY_INFORMATION = 0x0400
                        SYNCHRONIZE = 0x00100000
                        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | SYNCHRONIZE, False, pid)
                        if handle != 0:
                            running = True
                            ctypes.windll.kernel32.CloseHandle(handle)
                    else:
                        try:
                            os.kill(pid, 0)
                            running = True
                        except (ProcessLookupError, PermissionError):
                            running = (sys.exc_info()[0] == PermissionError)
                
                if not running:
                    logger.warning(f"Lock file has stale PID {pid}. Cleaning up.")
                    self.lock_file.unlink()
        except Exception as e:
            logger.warning(f"Failed to check/cleanup stale lock: {e}")
            
    def _acquire_lock(self) -> bool:
        """Acquire lock for backtest execution atomically"""
        import os
        self._cleanup_stale_lock()
        
        try:
            # Atomic lock acquisition using O_CREAT | O_EXCL
            fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                lock_data = {
                    "pid": str(os.getpid()),
                    "timestamp": datetime.now().isoformat(),
                    "status": "running"
                }
                with os.fdopen(fd, 'w') as f:
                    json.dump(lock_data, f, indent=2)
                return True
            except Exception as e:
                logger.error(f"Failed to write lock data: {e}")
                try:
                    os.close(fd)
                except:
                    pass
                self._release_lock()
                return False
        except FileExistsError:
            logger.warning("Backtest lock already exists (atomic check)")
            return False
        except Exception as e:
            logger.error(f"Failed to acquire lock atomically: {e}")
            return False
    
    def _release_lock(self):
        """Release backtest lock"""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except Exception as e:
            logger.error(f"Failed to release lock: {e}")
    
    def _stream_output(self, stream):
        """Stream subprocess output to queue (thread-safe, NO Streamlit calls)"""
        try:
            for line in iter(stream.readline, ''):
                if line:
                    self._output_queue.put(line.strip())
        except Exception as e:
            logger.error(f"Stream output error: {e}")
        finally:
            stream.close()
    
    def start(
        self,
        config: BacktestConfig,
        timeout: Optional[int] = None
    ) -> Dict:
        """
        Start backtest in subprocess (non-blocking).
        Use poll_output() and is_complete() for progress tracking.
        
        Args:
            config: Backtest configuration
            timeout: Optional timeout in seconds
            
        Returns:
            Dict with 'started' bool and optional 'error'
        """
        if not self._acquire_lock():
            return {"started": False, "error": "Backtest already running", "lock_info": self.get_lock_info()}
        
        self._is_running = True
        self._output_queue = queue.Queue()  # Reset queue
        
        try:
            logger.info(f"Starting backtest: {config.script_path}")
            self._process = subprocess.Popen(
                config.to_args(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Update lock file with actual child PID
            try:
                lock_data = {
                    "pid": str(self._process.pid),
                    "timestamp": datetime.now().isoformat(),
                    "status": "running"
                }
                with open(self.lock_file, 'w') as f:
                    json.dump(lock_data, f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to update lock file with child PID: {e}")
            
            # Stream output in separate thread (NO callback, queue only)
            self._output_thread = threading.Thread(
                target=self._stream_output,
                args=(self._process.stdout,),
                daemon=True
            )
            self._output_thread.start()
            
            return {"started": True, "pid": self._process.pid}
        
        except Exception as e:
            logger.exception("Backtest start failed")
            self._is_running = False
            self._release_lock()
            return {"started": False, "error": str(e)}
    
    def poll_output(self, max_messages: int = 200) -> list:
        """
        Drain accumulated output messages (call from main thread).
        
        Args:
            max_messages: Maximum messages to drain per call
            
        Returns:
            List of output line strings
        """
        messages = []
        count = 0
        while not self._output_queue.empty() and count < max_messages:
            try:
                messages.append(self._output_queue.get_nowait())
                count += 1
            except queue.Empty:
                break
        return messages
    
    def is_complete(self) -> bool:
        """Check if subprocess has finished"""
        if self._process is None:
            return True
        return self._process.poll() is not None
    
    def get_result(self, use_xgboost: bool = True) -> Dict:
        """
        Collect final result after subprocess completes.
        Call only after is_complete() returns True.
        """
        try:
            # Wait for output thread
            if hasattr(self, '_output_thread') and self._output_thread.is_alive():
                self._output_thread.join(timeout=5)
            
            # Collect remaining output
            output_lines = []
            while not self._output_queue.empty():
                try:
                    output_lines.append(self._output_queue.get_nowait())
                except queue.Empty:
                    break
            
            self._is_running = False
            
            if self._process is None:
                return {"success": False, "error": "No process"}
            
            if self._process.returncode == 0:
                from config.dashboard_config import DATA_DIR
                result_suffix = "xgboost" if use_xgboost else "baseline"
                result_path = DATA_DIR / "phase35_results" / f"phase35_backtest_results_{result_suffix}.json"
                
                if result_path.exists():
                    with open(result_path, 'r') as f:
                        results = json.load(f)
                    return {"success": True, "results": results, "output": "\n".join(output_lines[-20:])}
                else:
                    return {"success": False, "error": f"Results file not found: {result_path}", "output": "\n".join(output_lines[-20:])}
            else:
                return {"success": False, "error": f"Process exited with code {self._process.returncode}", "output": "\n".join(output_lines[-20:])}
        finally:
            self._release_lock()

    
    def stop(self):
        """Stop running backtest"""
        if self._process and self._process.poll() is None:
            logger.info("Stopping backtest...")
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
    
    def get_progress(self, max_messages: int = 100) -> list:
        """
        Get accumulated progress messages.
        
        Args:
            max_messages: Maximum number of messages to drain (default 100).
                          Prevents memory issues with large outputs.
                          
        Returns:
            List of progress message strings
        """
        messages = []
        count = 0
        while not self._output_queue.empty() and count < max_messages:
            messages.append(self._output_queue.get())
            count += 1
        return messages
