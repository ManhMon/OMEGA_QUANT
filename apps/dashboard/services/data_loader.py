"""
Data Loader Service
Wraps existing data loading logic from src.omega.data and monitoring_dashboard.py
"""
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

import pandas as pd
import streamlit as st

from config.dashboard_config import (
    REPO_ROOT,
    SESSION_DIR,
    PIPELINE_DIRS,
    DATA_DIR,
    MARKET_DATA_FILE,
    FEATURES_DATA_FILE,
    SECTOR_MAPPING_FILE,
    RISK_STATUS_FILE,
    PHASE_GATES_FILE,
    AUDIT_LOG_FILE,
    EVOLVED_ALPHAS_FILE,
    GOAL_STATE_FILE,
    MARKET_UPDATE_SCRIPT,
    VCI_UNIVERSE_FILE,
    MARKET_UPDATE_RESULT_FILE,
    LEGACY_LOADER_INVENTORY_JSON,
    LEGACY_LOADER_INVENTORY_MD,
    MARKET_UPDATE_LOCK_FILE,
    CACHE_TTL_FAST,
    CACHE_TTL_MEDIUM,
    CACHE_TTL_SLOW,
    MAX_AUDIT_LOG_LINES,
    MAX_BACKTEST_RESULTS,
    PHASE_DEFINITIONS,
    SAFE_COMMAND_CATALOG,
    CLI_TRACE_MAX_LINES,
    COMMAND_CENTER_READ_ONLY,
    SCRIPTS_DIR,
    E2E_COMPONENT_DEFINITIONS,
    E2E_ARTIFACT_CATALOG,
    E2E_COMMAND_CATALOG,
    E2E_DEFAULT_MODE,
    STATUS_MODE_READ_ONLY,
    STATUS_MODE_DRY_RUN,
    STATUS_MODE_MUTATING_BLOCKED,
    WALK_FORWARD_LOG,
    PNL_LATEST_FILE,
    WORKER_HEARTBEAT_FILE,
    AUDIT_REPORTS_DIR,
)

logger = logging.getLogger(__name__)

MARKET_UPDATE_TIMEOUT = 600  # seconds


class DataLoaderService:
    """Service for loading and caching dashboard data"""

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_FAST)
    def load_risk_status() -> Optional[Dict]:
        """Load risk status from risk_status.json"""
        if not RISK_STATUS_FILE.exists():
            return None
        try:
            with open(RISK_STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"Failed to load risk status: {e}")
            return None

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_MEDIUM)
    def load_phase_gates() -> Dict[str, Dict]:
        """Load phase gates from phase_gates.json"""
        if not PHASE_GATES_FILE.exists():
            return {}
        try:
            with open(PHASE_GATES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            st.warning(f"Failed to load phase gates: {e}")
            return {}

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_FAST)
    def load_audit_log(max_lines: int = MAX_AUDIT_LOG_LINES) -> List[Dict]:
        """Load audit log from audit_log.jsonl"""
        if not AUDIT_LOG_FILE.exists():
            return []
        try:
            lines = []
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            lines.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            return lines[-max_lines:]
        except Exception as e:
            st.warning(f"Failed to load audit log: {e}")
            return []

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_MEDIUM)
    def load_evolved_alphas() -> Dict:
        """Load evolved alphas from all_regimes_evolved_alphas.json"""
        if not EVOLVED_ALPHAS_FILE.exists():
            return {}
        try:
            with open(EVOLVED_ALPHAS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"Failed to load evolved alphas: {e}")
            return {}

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_MEDIUM)
    def load_goal_state() -> Optional[Dict]:
        """Load goal runner state"""
        if not GOAL_STATE_FILE.exists():
            return None
        try:
            with open(GOAL_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"Failed to load goal state: {e}")
            return None

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_MEDIUM)
    def load_backtest_results() -> List[Dict]:
        """Load backtest results from pipeline directories"""
        results = []
        for pdir in PIPELINE_DIRS:
            if not pdir.exists():
                continue
            for f in sorted(pdir.glob("*.json")):
                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    if isinstance(data, dict):
                        results.append(data)
                except Exception:
                    continue
                if len(results) >= MAX_BACKTEST_RESULTS:
                    break
            if len(results) >= MAX_BACKTEST_RESULTS:
                break
        return results

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_SLOW)
    def load_market_data() -> Optional[pd.DataFrame]:
        """Load market data from parquet file"""
        if not MARKET_DATA_FILE.exists():
            return None
        try:
            df = pd.read_parquet(MARKET_DATA_FILE)
            return df
        except Exception as e:
            st.warning(f"Failed to load market data: {e}")
            return None

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_SLOW)
    def load_features_data() -> Optional[pd.DataFrame]:
        """Load features data from parquet file"""
        if not FEATURES_DATA_FILE.exists():
            return None
        try:
            df = pd.read_parquet(FEATURES_DATA_FILE)
            return df
        except Exception as e:
            st.warning(f"Failed to load features data: {e}")
            return None

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_SLOW)
    def load_sector_mapping() -> Optional[pd.DataFrame]:
        """Load sector mapping from CSV"""
        if not SECTOR_MAPPING_FILE.exists():
            return None
        try:
            df = pd.read_csv(SECTOR_MAPPING_FILE)
            return df
        except Exception as e:
            st.warning(f"Failed to load sector mapping: {e}")
            return None

    @staticmethod
    def get_data_files_info() -> List[Dict[str, Any]]:
        """Get information about all data files"""
        files_info = []
        
        # Market data
        if MARKET_DATA_FILE.exists():
            stat = MARKET_DATA_FILE.stat()
            files_info.append({
                "File": "Market Data",
                "Path": str(MARKET_DATA_FILE.relative_to(DATA_DIR)),
                "Size (MB)": round(stat.st_size / 1024 / 1024, 2),
                "Last Modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "Status": "✅ OK",
            })
        else:
            files_info.append({
                "File": "Market Data",
                "Path": str(MARKET_DATA_FILE.relative_to(DATA_DIR)),
                "Size (MB)": 0,
                "Last Modified": "N/A",
                "Status": "❌ Missing",
            })

        # Features data
        if FEATURES_DATA_FILE.exists():
            stat = FEATURES_DATA_FILE.stat()
            files_info.append({
                "File": "Features Data",
                "Path": str(FEATURES_DATA_FILE.relative_to(DATA_DIR)),
                "Size (MB)": round(stat.st_size / 1024 / 1024, 2),
                "Last Modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "Status": "✅ OK",
            })
        else:
            files_info.append({
                "File": "Features Data",
                "Path": str(FEATURES_DATA_FILE.relative_to(DATA_DIR)),
                "Size (MB)": 0,
                "Last Modified": "N/A",
                "Status": "❌ Missing",
            })

        # Sector mapping
        if SECTOR_MAPPING_FILE.exists():
            stat = SECTOR_MAPPING_FILE.stat()
            files_info.append({
                "File": "Sector Mapping",
                "Path": str(SECTOR_MAPPING_FILE.relative_to(DATA_DIR)),
                "Size (MB)": round(stat.st_size / 1024 / 1024, 2),
                "Last Modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "Status": "✅ OK",
            })
        else:
            files_info.append({
                "File": "Sector Mapping",
                "Path": str(SECTOR_MAPPING_FILE.relative_to(DATA_DIR)),
                "Size (MB)": 0,
                "Last Modified": "N/A",
                "Status": "⚠️ Optional",
            })

        return files_info

    @staticmethod
    def get_data_quality_summary(df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """Get data quality summary for a DataFrame"""
        if df is None or df.empty:
            return {
                "Rows": 0,
                "Columns": 0,
                "Missing Values": 0,
                "Missing %": 0,
                "Duplicates": 0,
            }

        total_cells = df.size
        missing_cells = df.isna().sum().sum()
        missing_pct = (missing_cells / total_cells * 100) if total_cells > 0 else 0
        duplicates = df.duplicated().sum()

        return {
            "Rows": len(df),
            "Columns": len(df.columns),
            "Missing Values": int(missing_cells),
            "Missing %": round(missing_pct, 2),
            "Duplicates": int(duplicates),
        }

    # ── Canonical Market Summary ──────────────────────────────────────────

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_SLOW)
    def load_canonical_market_summary() -> Dict[str, Any]:
        """Build a rich summary of the canonical market parquet.

        Returns file metadata, row/ticker/date stats, exchange split,
        duplicate counts, OHLCV null counts, sha256 hash, and
        validation status without mutating the canonical file.
        """
        summary: Dict[str, Any] = {"exists": MARKET_DATA_FILE.exists()}
        if not MARKET_DATA_FILE.exists():
            summary["validation_status"] = "MISSING"
            return summary

        stat = MARKET_DATA_FILE.stat()
        summary["size_mb"] = round(stat.st_size / 1024 / 1024, 2)
        summary["modified"] = datetime.fromtimestamp(stat.st_mtime).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # SHA-256
        sha = hashlib.sha256()
        with open(MARKET_DATA_FILE, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        summary["sha256"] = sha.hexdigest()

        # DataFrame stats
        try:
            df = pd.read_parquet(MARKET_DATA_FILE)
            summary["rows"] = len(df)
            summary["columns"] = len(df.columns)
            summary["column_list"] = list(df.columns)

            if "date" in df.columns:
                dates = pd.to_datetime(df["date"])
                summary["date_min"] = str(dates.min().date())
                summary["date_max"] = str(dates.max().date())

            if "ticker" in df.columns:
                summary["ticker_count"] = int(df["ticker"].nunique())

            if "exchange" in df.columns:
                summary["exchange_split"] = df["exchange"].value_counts().to_dict()

            # Duplicate (ticker, date) count
            if "ticker" in df.columns and "date" in df.columns:
                summary["duplicate_ticker_date"] = int(
                    df.duplicated(subset=["ticker", "date"]).sum()
                )
            else:
                summary["duplicate_ticker_date"] = -1

            # OHLCV null counts
            ohlcv_nulls: Dict[str, int] = {}
            for col in ("open", "high", "low", "close", "volume"):
                if col in df.columns:
                    ohlcv_nulls[col] = int(df[col].isna().sum())
            summary["ohlcv_nulls"] = ohlcv_nulls

            total_nulls = sum(ohlcv_nulls.values())
            dup_count = summary.get("duplicate_ticker_date", 0)
            if total_nulls == 0 and dup_count == 0:
                summary["validation_status"] = "PASS"
            else:
                summary["validation_status"] = "WARN"

        except Exception as e:
            logger.warning("Failed to read canonical parquet: %s", e)
            summary["rows"] = -1
            summary["validation_status"] = f"ERROR: {e}"

        return summary

    # ── VCI Universe Summary ──────────────────────────────────────────────

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_SLOW)
    def load_vci_universe_summary() -> Dict[str, Any]:
        """Load VCI universe HSX/HNX counts. Tolerates missing file."""
        result: Dict[str, Any] = {"exists": VCI_UNIVERSE_FILE.exists()}
        if not VCI_UNIVERSE_FILE.exists():
            return result
        try:
            with open(VCI_UNIVERSE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            result["hsx_count"] = data.get(
                "hsx_count", len(data.get("hsx", []))
            )
            result["hnx_count"] = data.get(
                "hnx_count", len(data.get("hnx", []))
            )
            result["total"] = data.get(
                "total", result["hsx_count"] + result["hnx_count"]
            )
        except Exception as e:
            logger.warning("Failed to load VCI universe: %s", e)
            result["error"] = str(e)
        return result

    # ── Legacy Loader Inventory ───────────────────────────────────────────

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_SLOW)
    def load_legacy_loader_inventory() -> Dict[str, Any]:
        """Load legacy loader inventory JSON and markdown from session dir."""
        result: Dict[str, Any] = {
            "json_exists": LEGACY_LOADER_INVENTORY_JSON.exists(),
            "md_exists": LEGACY_LOADER_INVENTORY_MD.exists(),
        }
        if LEGACY_LOADER_INVENTORY_JSON.exists():
            try:
                with open(LEGACY_LOADER_INVENTORY_JSON, "r", encoding="utf-8") as f:
                    result["json_data"] = json.load(f)
            except Exception as e:
                result["json_error"] = str(e)
        if LEGACY_LOADER_INVENTORY_MD.exists():
            try:
                result["md_text"] = LEGACY_LOADER_INVENTORY_MD.read_text(
                    encoding="utf-8"
                )
            except Exception as e:
                result["md_error"] = str(e)
        return result

    # ── Update Market Data Result ─────────────────────────────────────────

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_MEDIUM)
    def load_update_market_data_result() -> Dict[str, Any]:
        """Load the display-only update projection; it never authorizes execution."""
        result: Dict[str, Any] = {"exists": MARKET_UPDATE_RESULT_FILE.exists()}
        if not MARKET_UPDATE_RESULT_FILE.exists():
            return result
        try:
            with open(MARKET_UPDATE_RESULT_FILE, "r", encoding="utf-8") as f:
                result["data"] = json.load(f)
            result["modified"] = datetime.fromtimestamp(
                MARKET_UPDATE_RESULT_FILE.stat().st_mtime
            ).strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            result["error"] = str(e)
        return result

    @staticmethod
    @st.cache_data(ttl=CACHE_TTL_MEDIUM)
    def load_market_data_attempt_ledger() -> Dict[str, Any]:
        """Read ledger state for display only; malformed state remains blocked."""
        receipt_dir = SESSION_DIR / "market_data_receipts"
        result: Dict[str, Any] = {"exists": receipt_dir.is_dir(), "state": "BLOCKED"}
        if not receipt_dir.is_dir():
            return result
        entries = sorted(receipt_dir.glob("*.json"))
        if not entries:
            return result
        latest = entries[-1]
        result["path"] = str(latest.relative_to(REPO_ROOT))
        try:
            record = json.loads(latest.read_text(encoding="utf-8"))
            result.update({"attempt_id": record.get("attempt_id"), "record_state": record.get("state")})
            if latest.name.endswith(".terminal.json"):
                result["execution_allowed"] = record.get("execution_allowed") is True
                result["state"] = "ELIGIBLE" if result["execution_allowed"] else "BLOCKED"
            else:
                result["reason"] = "newest attempt is in progress"
        except Exception as exc:
            result["error"] = str(exc)
        return result

    # ── Run Market Data Update (subprocess) ───────────────────────────────

    @staticmethod
    def build_update_command(
        dry_run: bool = True,
        symbols: Optional[List[str]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[str]:
        """Build the subprocess command list for update_market_data.py."""
        cmd = [sys.executable, str(MARKET_UPDATE_SCRIPT)]
        if dry_run:
            cmd.append("--dry-run")
        if symbols:
            cmd.extend(["--symbols", *symbols])
        if start:
            cmd.extend(["--start", start])
        if end:
            cmd.extend(["--end", end])
        return cmd

    @staticmethod
    def run_market_data_update(
        dry_run: bool = True,
        symbols: Optional[List[str]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute the canonical VCI updater as a subprocess.

        - Uses list args, shell=False for safety.
        - Lock file prevents concurrent updates.
        - Captures stdout/stderr.
        - Clears Streamlit cache after run.
        - Never mutates canonical data when dry_run=True.
        """
        # Lock check
        if MARKET_UPDATE_LOCK_FILE.exists():
            lock_age = datetime.now().timestamp() - MARKET_UPDATE_LOCK_FILE.stat().st_mtime
            if lock_age < MARKET_UPDATE_TIMEOUT:
                return {
                    "status": "LOCKED",
                    "message": (
                        f"Another update is running (lock age: {lock_age:.0f}s). "
                        "Wait or remove the lock file manually."
                    ),
                }

        cmd = DataLoaderService.build_update_command(
            dry_run=dry_run, symbols=symbols, start=start, end=end
        )

        # Create lock
        MARKET_UPDATE_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            MARKET_UPDATE_LOCK_FILE.write_text(
                json.dumps({"pid": os.getpid(), "cmd": cmd, "started": datetime.now().isoformat()}),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to create lock file: %s", e)

        result: Dict[str, Any] = {"cmd": cmd, "dry_run": dry_run}
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=MARKET_UPDATE_TIMEOUT,
                cwd=str(REPO_ROOT),
                shell=False,
            )
            result["returncode"] = proc.returncode
            result["stdout"] = proc.stdout
            result["stderr"] = proc.stderr
            result["status"] = "OK" if proc.returncode == 0 else "FAILED"
        except subprocess.TimeoutExpired:
            result["status"] = "TIMEOUT"
            result["stdout"] = ""
            result["stderr"] = f"Timed out after {MARKET_UPDATE_TIMEOUT}s"
            result["returncode"] = -1
        except Exception as e:
            result["status"] = "ERROR"
            result["stdout"] = ""
            result["stderr"] = str(e)
            result["returncode"] = -1
        finally:
            # Remove lock
            try:
                MARKET_UPDATE_LOCK_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            # Clear caches so page refreshes with new data (safe for non-Streamlit envs)
            for _clear_fn in (
                DataLoaderService.load_canonical_market_summary,
                DataLoaderService.load_update_market_data_result,
                DataLoaderService.load_market_data_attempt_ledger,
            ):
                try:
                    _clear_fn.clear()
                except AttributeError:
                    pass

        return result

    # ══════════════════════════════════════════════════════════════════════
    # Command Center Helpers (read-only, no subprocess execution)
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def parse_phase_gates_flat() -> Dict[str, Dict]:
        """Parse phase_gates.json into a flat dict of gate_name -> gate_info.

        Handles both list-of-dicts and dict-of-dicts shapes produced by
        the gate enforcer.
        """
        if not PHASE_GATES_FILE.exists():
            return {}
        try:
            with open(PHASE_GATES_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.warning("parse_phase_gates_flat: %s", e)
            return {}

        if isinstance(raw, dict):
            flat: Dict[str, Dict] = {}
            for key, val in raw.items():
                if isinstance(val, dict):
                    has_nested = any(
                        isinstance(v, dict) and "phase_name" in v
                        for v in val.values()
                    )
                    if has_nested:
                        for gk, gv in val.items():
                            if isinstance(gv, dict):
                                flat[gk] = gv
                    else:
                        flat[key] = val
            return flat if flat else raw

        if isinstance(raw, list):
            merged: Dict[str, Dict] = {}
            for item in raw:
                if isinstance(item, dict):
                    for k, v in item.items():
                        if isinstance(v, dict):
                            merged[k] = v
                        else:
                            gate_name = item.get(
                                "phase_name",
                                item.get("gate_id", f"gate_{len(merged)}"),
                            )
                            merged[gate_name] = item
                            break
            return merged
        return {}

    @staticmethod
    def get_phase_connectivity() -> List[Dict[str, Any]]:
        """Return Phase 1→5 connectivity status for Command Center map.

        Returns a list of dicts, one per phase, with:
          phase_id, name, short, icon, status (PASS/WARN/MISSING),
          gate_count, approved_count
        """
        gates = DataLoaderService.parse_phase_gates_flat()
        result: List[Dict[str, Any]] = []

        for phase_key, phase_def in PHASE_DEFINITIONS.items():
            matched_gates = []
            approved = 0
            for gk in phase_def.get("gate_keys", []):
                if gk in gates:
                    matched_gates.append(gk)
                    verdict = gates[gk].get("final_verdict", "")
                    if "APPROVED" in str(verdict):
                        approved += 1

            gate_count = len(matched_gates)
            if gate_count == 0:
                status = "MISSING"
            elif approved == gate_count:
                status = "PASS"
            else:
                status = "WARN"

            result.append({
                "phase_id": phase_def["id"],
                "phase_key": phase_key,
                "name": phase_def["name"],
                "short": phase_def["short"],
                "icon": phase_def["icon"],
                "status": status,
                "gate_count": gate_count,
                "approved_count": approved,
                "description": phase_def["description"],
            })
        return result

    @staticmethod
    def get_system_readiness() -> Dict[str, Any]:
        """Compute overall system readiness from available state files.

        Returns a dict with readiness_score (0-100), component statuses.
        """
        components: Dict[str, str] = {}

        risk = DataLoaderService.load_risk_status()
        if risk:
            state = risk.get("system_state", "UNKNOWN")
            if state == "RUNNING" and not risk.get("breached"):
                components["risk_monitor"] = "PASS"
            elif risk.get("breached"):
                components["risk_monitor"] = "ERROR"
            else:
                components["risk_monitor"] = "WARN"
        else:
            components["risk_monitor"] = "MISSING"

        gates = DataLoaderService.parse_phase_gates_flat()
        if gates:
            total = len(gates)
            approved = sum(
                1
                for v in gates.values()
                if isinstance(v, dict)
                and "APPROVED" in str(v.get("final_verdict", ""))
            )
            if approved == total:
                components["phase_gates"] = "PASS"
            elif approved > 0:
                components["phase_gates"] = "WARN"
            else:
                components["phase_gates"] = "MISSING"
        else:
            components["phase_gates"] = "MISSING"

        components["market_data"] = (
            "PASS" if MARKET_DATA_FILE.exists() else "MISSING"
        )

        bt = DataLoaderService.load_backtest_results()
        components["backtest"] = "PASS" if bt else "MISSING"

        alphas = DataLoaderService.load_evolved_alphas()
        components["alphas"] = "PASS" if alphas else "MISSING"

        weights = {
            "risk_monitor": 25, "phase_gates": 25,
            "market_data": 20, "backtest": 15, "alphas": 15,
        }
        score = 0
        for comp, status in components.items():
            w = weights.get(comp, 0)
            if status == "PASS":
                score += w
            elif status == "WARN":
                score += w // 2
        return {
            "readiness_score": score,
            "components": components,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    @staticmethod
    def get_safe_command_catalog() -> List[Dict[str, Any]]:
        """Return the safe command catalog (read-only metadata, no execution)."""
        catalog = []
        for cmd in SAFE_COMMAND_CATALOG:
            entry = dict(cmd)
            entry["full_command"] = " ".join(
                [cmd["script"]] + cmd.get("args", [])
            )
            entry["executed"] = False
            entry["read_only"] = True
            catalog.append(entry)
        return catalog

    @staticmethod
    def get_cli_trace_entries(max_lines: int = CLI_TRACE_MAX_LINES) -> List[Dict[str, str]]:
        """Build CLI trace entries from existing state/log files.

        Purely read-only: reads recent audit log and phase gate data
        to construct simulated CLI trace lines. No commands executed.
        """
        entries: List[Dict[str, str]] = []

        entries.append({
            "type": "info",
            "text": f"OMEGA_QUANT CLI Trace — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        })
        entries.append({"type": "dim", "text": "─" * 60})
        entries.append({
            "type": "prompt",
            "text": "$ sod_gate_enforcer.py --informational",
        })

        gates = DataLoaderService.parse_phase_gates_flat()
        if gates:
            entries.append({"type": "ok", "text": f"[INFO] Loaded {len(gates)} phase gates"})
            for gk, gv in list(gates.items())[:10]:
                if isinstance(gv, dict):
                    verdict = gv.get("final_verdict", "PENDING")
                    ts = gv.get("timestamp", "N/A")
                    cls = "ok" if "APPROVED" in str(verdict) else "warn"
                    entries.append({
                        "type": cls,
                        "text": f"  {gk}: {verdict} ({ts})",
                    })
        else:
            entries.append({"type": "warn", "text": "[WARN] No phase_gates.json found"})

        entries.append({"type": "dim", "text": "─" * 60})

        risk = DataLoaderService.load_risk_status()
        if risk:
            state = risk.get("system_state", "UNKNOWN")
            entries.append({"type": "prompt", "text": "$ risk_status --summary"})
            entries.append({"type": "ok", "text": f"[INFO] System state: {state}"})
            m = risk.get("metrics", {})
            entries.append({
                "type": "info",
                "text": f"  Sharpe={m.get('sharpe_ratio', 0):.3f} "
                        f"MaxDD={m.get('max_drawdown', 0):.4f} "
                        f"VaR95={m.get('var_95', 0):.4f}",
            })
            if risk.get("breached"):
                entries.append({"type": "err", "text": "[CRITICAL] Circuit breaker TRIGGERED"})
                for r in risk.get("breached_reasons", []):
                    entries.append({"type": "err", "text": f"  → {r}"})
        else:
            entries.append({"type": "warn", "text": "[WARN] No risk_status.json found"})

        entries.append({"type": "dim", "text": "─" * 60})

        audit_logs = DataLoaderService.load_audit_log(max_lines=20)
        if audit_logs:
            entries.append({"type": "prompt", "text": "$ audit_log --tail 10"})
            for log in audit_logs[-10:]:
                ts = log.get("timestamp", "?")
                action = log.get("action", log.get("event", "?"))
                role = log.get("role", log.get("agent", "?"))
                entries.append({
                    "type": "info",
                    "text": f"  [{ts}] {action} ({role})",
                })

        entries.append({"type": "dim", "text": "─" * 60})
        entries.append({
            "type": "ok",
            "text": "[DONE] Command Center trace complete. All data read-only.",
        })

        return entries[:max_lines]

    @staticmethod
    def get_data_health_status() -> List[Dict[str, Any]]:
        """Get health and freshness info for all tracked data files."""
        now = datetime.now()

        def _file_entry(path: Path, label: str, required: bool = True) -> Dict[str, Any]:
            if path.exists():
                stat = path.stat()
                age_hours = (now - datetime.fromtimestamp(stat.st_mtime)).total_seconds() / 3600
                size_mb = round(stat.st_size / 1024 / 1024, 2)
                freshness = "FRESH" if age_hours < 24 else "AGING" if age_hours < 72 else "STALE"
                return {
                    "file": label, "path": str(path.relative_to(REPO_ROOT)),
                    "exists": True, "size_mb": size_mb,
                    "age_hours": round(age_hours, 1), "freshness": freshness, "status": "OK",
                }
            return {
                "file": label, "path": str(path.relative_to(REPO_ROOT)),
                "exists": False, "size_mb": 0, "age_hours": -1,
                "freshness": "N/A", "status": "REQUIRED" if required else "OPTIONAL",
            }

        return [
            _file_entry(MARKET_DATA_FILE, "Market Data (canonical)"),
            _file_entry(FEATURES_DATA_FILE, "Features Data"),
            _file_entry(SECTOR_MAPPING_FILE, "Sector Mapping", required=False),
            _file_entry(RISK_STATUS_FILE, "Risk Status"),
            _file_entry(PHASE_GATES_FILE, "Phase Gates"),
            _file_entry(EVOLVED_ALPHAS_FILE, "Evolved Alphas", required=False),
            _file_entry(VCI_UNIVERSE_FILE, "VCI Universe"),
            _file_entry(AUDIT_LOG_FILE, "Audit Log", required=False),
        ]

    @staticmethod
    def get_backtest_summary() -> Dict[str, Any]:
        """Read-only summary of latest backtest results."""
        results = DataLoaderService.load_backtest_results()
        if not results:
            return {"count": 0, "best_sharpe": None, "latest_source": None}
        best_sharpe = 0.0
        for r in results:
            m = r.get("metrics", r)
            s = m.get("sharpe", m.get("sharpe_ratio", 0))
            if isinstance(s, (int, float)) and s > best_sharpe:
                best_sharpe = s
        latest = results[-1] if results else None
        return {
            "count": len(results),
            "best_sharpe": round(best_sharpe, 4),
            "latest_source": latest.get("_source_file", "N/A") if latest else "N/A",
        }

    @staticmethod
    def get_risk_summary() -> Dict[str, Any]:
        """Read-only risk metrics summary."""
        risk = DataLoaderService.load_risk_status()
        if not risk:
            return {"available": False}
        m = risk.get("metrics", {})
        return {
            "available": True,
            "system_state": risk.get("system_state", "UNKNOWN"),
            "breached": risk.get("breached", False),
            "breached_reasons": risk.get("breached_reasons", []),
            "sharpe_ratio": m.get("sharpe_ratio", 0),
            "max_drawdown": m.get("max_drawdown", 0),
            "var_95": m.get("var_95", 0),
            "cvar_95": m.get("cvar_95", 0),
            "portfolio_beta": m.get("portfolio_beta", 0),
            "consecutive_losses": m.get("consecutive_losses", 0),
        }

    @staticmethod
    def get_observability_status() -> Dict[str, Any]:
        """Read-only observability / SRE status from existing state."""
        audit_logs = DataLoaderService.load_audit_log(max_lines=5)
        worker_hb = SESSION_DIR / "worker_heartbeat.jsonl"
        hb_count = 0
        if worker_hb.exists():
            try:
                with open(worker_hb, "r", encoding="utf-8") as f:
                    hb_count = sum(1 for _ in f)
            except Exception:
                pass
        return {
            "audit_log_entries": len(audit_logs),
            "worker_heartbeats": hb_count,
            "dashboard_version": "18.0",
            "command_center_version": "2.0.0",
            "read_only_mode": COMMAND_CENTER_READ_ONLY,
        }

    # ══════════════════════════════════════════════════════════════════════
    # E2E Dashboard Methods (SAFE mode: read-only, no subprocess)
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _resolve_artifact_path(path_key: str) -> Optional[Path]:
        """Resolve an artifact path_key to a Path object."""
        mapping = {
            "MARKET_DATA_FILE": MARKET_DATA_FILE,
            "VCI_UNIVERSE_FILE": VCI_UNIVERSE_FILE,
            "SECTOR_MAPPING_FILE": SECTOR_MAPPING_FILE,
            "FEATURES_DATA_FILE": FEATURES_DATA_FILE,
            "LEGACY_LOADER_INVENTORY_JSON": LEGACY_LOADER_INVENTORY_JSON,
            "EVOLVED_ALPHAS_FILE": EVOLVED_ALPHAS_FILE,
            "PIPELINE_DIRS": PIPELINE_DIRS[0] if PIPELINE_DIRS else None,
            "WALK_FORWARD_LOG": WALK_FORWARD_LOG,
            "PNL_LATEST_FILE": PNL_LATEST_FILE,
            "RISK_STATUS_FILE": RISK_STATUS_FILE,
            "GOAL_STATE_FILE": GOAL_STATE_FILE,
            "AUDIT_LOG_FILE": AUDIT_LOG_FILE,
            "WORKER_HEARTBEAT_FILE": WORKER_HEARTBEAT_FILE,
            "PHASE_GATES_FILE": PHASE_GATES_FILE,
            "AUDIT_REPORTS_DIR": AUDIT_REPORTS_DIR,
        }
        return mapping.get(path_key)

    @staticmethod
    def get_e2e_artifact_status() -> List[Dict[str, Any]]:
        """Return existence/freshness status for all E2E artifacts.

        Purely read-only: probes file existence without mutation.
        Missing artifacts degrade to WARN/MISSING, never crash.
        """
        results: List[Dict[str, Any]] = []
        now = datetime.now()

        for artifact_key, artifact_def in E2E_ARTIFACT_CATALOG.items():
            path = DataLoaderService._resolve_artifact_path(
                artifact_def["path_key"]
            )
            entry: Dict[str, Any] = {
                "key": artifact_key,
                "label": artifact_def["label"],
                "required": artifact_def["required"],
            }

            if path is None:
                entry["exists"] = False
                entry["status"] = "MISSING"
                entry["size_mb"] = 0
                entry["age_hours"] = -1
                results.append(entry)
                continue

            if path.is_dir():
                exists = path.exists()
                entry["exists"] = exists
                if exists:
                    json_files = list(path.glob("*.json"))
                    entry["file_count"] = len(json_files)
                    entry["status"] = "OK" if json_files else "EMPTY"
                else:
                    entry["status"] = "MISSING"
                entry["size_mb"] = 0
                entry["age_hours"] = -1
            elif path.exists():
                stat = path.stat()
                age_hours = (
                    now - datetime.fromtimestamp(stat.st_mtime)
                ).total_seconds() / 3600
                entry["exists"] = True
                entry["size_mb"] = round(stat.st_size / 1024 / 1024, 2)
                entry["age_hours"] = round(age_hours, 1)
                freshness = (
                    "FRESH"
                    if age_hours < 24
                    else "AGING"
                    if age_hours < 72
                    else "STALE"
                )
                entry["freshness"] = freshness
                entry["status"] = "OK"
            else:
                entry["exists"] = False
                entry["status"] = (
                    "MISSING" if artifact_def["required"] else "OPTIONAL"
                )
                entry["size_mb"] = 0
                entry["age_hours"] = -1

            results.append(entry)

        return results

    @staticmethod
    def get_e2e_component_health() -> Dict[str, Dict[str, Any]]:
        """Return health status for each E2E component.

        Rules:
        - No subprocess execution in SAFE mode.
        - Missing artifacts degrade to WARN/MISSING.
        - Risk/execution unknown state is safe/fail-closed.
        """
        artifacts = DataLoaderService.get_e2e_artifact_status()
        artifact_map = {a["key"]: a for a in artifacts}

        health: Dict[str, Dict[str, Any]] = {}

        for comp_key, comp_def in E2E_COMPONENT_DEFINITIONS.items():
            comp_artifact_keys = comp_def.get("artifact_keys", [])
            fail_closed = comp_def.get("fail_closed", False)

            statuses = []
            for ak in comp_artifact_keys:
                art = artifact_map.get(ak, {"status": "MISSING"})
                statuses.append(art["status"])

            if not comp_artifact_keys:
                if comp_key == "dashboard":
                    comp_status = "OK"
                else:
                    comp_status = "UNKNOWN"
            elif all(s == "OK" for s in statuses):
                comp_status = "OK"
            elif any(s == "MISSING" for s in statuses):
                required_missing = any(
                    artifact_map.get(ak, {}).get("required", False)
                    and artifact_map.get(ak, {}).get("status") == "MISSING"
                    for ak in comp_artifact_keys
                )
                if required_missing:
                    comp_status = "MISSING"
                else:
                    comp_status = "WARN"
            elif any(s == "EMPTY" for s in statuses):
                comp_status = "WARN"
            else:
                comp_status = "WARN"

            if fail_closed and comp_status != "OK":
                comp_status = "FAIL_CLOSED"

            health[comp_key] = {
                "name": comp_def["name"],
                "icon": comp_def["icon"],
                "description": comp_def["description"],
                "status": comp_status,
                "fail_closed": fail_closed,
                "artifact_count": len(comp_artifact_keys),
                "artifact_statuses": statuses,
            }

        return health

    @staticmethod
    def get_e2e_topology() -> Dict[str, Any]:
        """Return E2E topology graph data for the Command Center.

        Returns component health plus edge definitions showing data flow.
        """
        health = DataLoaderService.get_e2e_component_health()

        edges = [
            ("data", "feature_store"),
            ("feature_store", "alpha_model"),
            ("alpha_model", "backtest"),
            ("backtest", "portfolio"),
            ("portfolio", "risk"),
            ("risk", "execution"),
            ("execution", "sre"),
            ("sre", "governance"),
            ("governance", "dashboard"),
        ]

        ok_count = sum(
            1 for h in health.values() if h["status"] == "OK"
        )
        warn_count = sum(
            1
            for h in health.values()
            if h["status"] in ("WARN", "OPTIONAL")
        )
        fail_count = sum(
            1
            for h in health.values()
            if h["status"] in ("MISSING", "FAIL_CLOSED", "ERROR")
        )
        total = len(health)

        return {
            "components": health,
            "edges": edges,
            "summary": {
                "total": total,
                "ok": ok_count,
                "warn": warn_count,
                "fail": fail_count,
                "health_pct": round(
                    (ok_count / total * 100) if total > 0 else 0, 1
                ),
            },
            "mode": E2E_DEFAULT_MODE,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    @staticmethod
    def get_e2e_command_catalog() -> List[Dict[str, Any]]:
        """Return the E2E command catalog (read-only metadata, no execution).

        All entries are SAFE mode: status/dry-run/read-only only.
        """
        catalog = []
        for cmd in E2E_COMMAND_CATALOG:
            entry = dict(cmd)
            entry["full_command"] = " ".join(
                [cmd["script"]] + cmd.get("args", [])
            )
            entry["executed"] = False
            entry["read_only"] = True
            entry["mode"] = cmd.get("mode", STATUS_MODE_READ_ONLY)
            catalog.append(entry)
        return catalog

    @staticmethod
    def get_e2e_dashboard_summary() -> Dict[str, Any]:
        """Return overall E2E dashboard summary for the Command Center header.

        Combines topology, risk, gates, and verification into a single
        executive summary dict.
        """
        topology = DataLoaderService.get_e2e_topology()
        risk = DataLoaderService.get_risk_summary()
        gates = DataLoaderService.parse_phase_gates_flat()

        gate_total = len(gates)
        gate_approved = sum(
            1
            for v in gates.values()
            if isinstance(v, dict)
            and "APPROVED" in str(v.get("final_verdict", ""))
        )

        risk_state = "UNKNOWN"
        if risk.get("available"):
            risk_state = risk.get("system_state", "UNKNOWN")
            if risk.get("breached"):
                risk_state = "BREACH"

        return {
            "topology": topology["summary"],
            "risk_state": risk_state,
            "gates_approved": gate_approved,
            "gates_total": gate_total,
            "mode": E2E_DEFAULT_MODE,
            "read_only": COMMAND_CENTER_READ_ONLY,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    @staticmethod
    def get_latest_test_and_audit_trace(
        max_entries: int = 20,
    ) -> List[Dict[str, str]]:
        """Return latest test and audit trace entries (read-only).

        Reads audit log and phase gate data to construct trace lines.
        No commands are executed.
        """
        entries: List[Dict[str, str]] = []

        entries.append({
            "type": "info",
            "text": (
                f"E2E Audit/Test Trace — "
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            ),
        })
        entries.append({"type": "dim", "text": "─" * 60})

        gates = DataLoaderService.parse_phase_gates_flat()
        if gates:
            entries.append({
                "type": "ok",
                "text": f"[INFO] {len(gates)} phase gates loaded",
            })
            for gk, gv in list(gates.items())[:10]:
                if isinstance(gv, dict):
                    verdict = gv.get("final_verdict", "PENDING")
                    ts = gv.get("timestamp", "N/A")
                    cls = (
                        "ok"
                        if "APPROVED" in str(verdict)
                        else "warn"
                    )
                    entries.append({
                        "type": cls,
                        "text": f"  {gk}: {verdict} ({ts})",
                    })
        else:
            entries.append({
                "type": "warn",
                "text": "[WARN] No phase_gates.json found",
            })

        entries.append({"type": "dim", "text": "─" * 60})

        audit_logs = DataLoaderService.load_audit_log(max_lines=max_entries)
        if audit_logs:
            entries.append({
                "type": "prompt",
                "text": "$ audit_log --tail 10",
            })
            for log in audit_logs[-10:]:
                ts = log.get("timestamp", "?")
                action = log.get("action", log.get("event", "?"))
                role = log.get("role", log.get("agent", "?"))
                entries.append({
                    "type": "info",
                    "text": f"  [{ts}] {action} ({role})",
                })
        else:
            entries.append({
                "type": "warn",
                "text": "[WARN] No audit log entries found",
            })

        entries.append({"type": "dim", "text": "─" * 60})

        reports_count = 0
        if AUDIT_REPORTS_DIR.exists():
            reports_count = len(list(AUDIT_REPORTS_DIR.glob("*.md")))
        entries.append({
            "type": "info",
            "text": f"[INFO] Audit reports on disk: {reports_count}",
        })

        entries.append({"type": "dim", "text": "─" * 60})
        entries.append({
            "type": "ok",
            "text": "[DONE] E2E trace complete. All data read-only.",
        })

        return entries[:max_entries * 3]
