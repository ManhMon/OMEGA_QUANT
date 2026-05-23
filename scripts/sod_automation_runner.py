"""
SOD Automation Runner for OMEGA_QUANT
Executes L2 -> L3 -> Gate workflow automatically
"""
import json
import subprocess
import time
from pathlib import Path
from datetime import datetime
import sys

class SODAutomation:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.workspace = Path("C:/Users/GHC/.openclaw/workspace/OMEGA_QUANT")
        self.log_path = self.workspace / ".ly_state/logs/sod_automation.jsonl"
        
    def _load_config(self, path: str) -> dict:
        with open(path, 'r') as f:
            return json.load(f)
    
    def _log(self, level: str, message: str, **kwargs):
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
            **kwargs
        }
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(entry) + "\n")
        print(f"[{level}] {message}")
    
    def run_l2_implementation(self, task_description: str, task_id: str) -> dict:
        """Run L2 implementation via OpenCode CLI"""
        self._log("INFO", "Starting L2 implementation", task_id=task_id)
        
        step = self.config["workflow"]["steps"][0]
        command = step["command_template"].format(task_description=task_description)
        
        # Run OpenCode CLI
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(self.workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Poll for completion
        timeout = step["timeout_seconds"]
        start = time.time()
        
        while proc.poll() is None:
            if time.time() - start > timeout:
                proc.kill()
                self._log("ERROR", "L2 timeout", task_id=task_id)
                return {"status": "timeout"}
            time.sleep(self.config["settings"]["poll_interval_seconds"])
        
        # Check evidence
        evidence_path = self.workspace / step["evidence_path"].format(task_id=task_id)
        if not evidence_path.exists():
            self._log("ERROR", "L2 evidence missing", task_id=task_id)
            return {"status": "failed", "reason": "evidence_missing"}
        
        self._log("INFO", "L2 completed", task_id=task_id)
        return {"status": "success", "evidence_path": str(evidence_path)}
    
    def verify_l2_output(self, evidence_path: str) -> dict:
        """Verify L2 output meets criteria"""
        self._log("INFO", "Verifying L2 output", evidence_path=evidence_path)
        
        # Read evidence file
        with open(evidence_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Basic checks
        if "error" in content.lower() and "critical" in content.lower():
            self._log("WARN", "L2 evidence contains critical errors")
            return {"status": "failed", "reason": "critical_errors"}
        
        self._log("INFO", "L2 verification passed")
        return {"status": "success"}
    
    def run_l3_audit(self, audit_description: str, task_id: str) -> dict:
        """Run L3 audit via Codex CLI"""
        self._log("INFO", "Starting L3 audit", task_id=task_id)
        
        step = self.config["workflow"]["steps"][2]
        command = step["command_template"].format(audit_description=audit_description)
        
        # Run Codex CLI
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(self.workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Poll for completion
        timeout = step["timeout_seconds"]
        start = time.time()
        
        while proc.poll() is None:
            if time.time() - start > timeout:
                proc.kill()
                self._log("ERROR", "L3 timeout", task_id=task_id)
                return {"status": "timeout"}
            time.sleep(self.config["settings"]["poll_interval_seconds"])
        
        # Check evidence
        evidence_path = self.workspace / step["evidence_path"].format(task_id=task_id)
        if not evidence_path.exists():
            self._log("ERROR", "L3 evidence missing", task_id=task_id)
            return {"status": "failed", "reason": "evidence_missing"}
        
        # Extract verdict
        with open(evidence_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if "[APPROVED]" in content:
            verdict = "APPROVED"
        elif "[NEEDS_FIX]" in content:
            verdict = "NEEDS_FIX"
        else:
            verdict = "INVALID"
        
        self._log("INFO", "L3 completed", task_id=task_id, verdict=verdict)
        return {
            "status": "success",
            "verdict": verdict,
            "evidence_path": str(evidence_path)
        }
    
    def make_gate_decision(self, l3_result: dict, task_id: str) -> dict:
        """Make gate decision based on L3 audit"""
        self._log("INFO", "Making gate decision", task_id=task_id)
        
        verdict = l3_result.get("verdict")
        
        if verdict == "APPROVED":
            self._log("INFO", "Gate APPROVED", task_id=task_id)
            return {"decision": "APPROVED"}
        elif verdict == "NEEDS_FIX":
            self._log("INFO", "Gate NEEDS_FIX", task_id=task_id)
            return {"decision": "NEEDS_FIX"}
        else:
            self._log("ERROR", "Gate INVALID", task_id=task_id)
            return {"decision": "INVALID"}
    
    def commit_and_push(self, files: list, commit_message: str):
        """Commit and push changes"""
        if not self.config["settings"]["auto_commit"]:
            self._log("INFO", "Auto-commit disabled, skipping")
            return {"status": "skipped"}
        
        self._log("INFO", "Committing changes")
        
        # Git add
        for file in files:
            subprocess.run(["git", "add", file], cwd=str(self.workspace))
        
        # Git commit
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=str(self.workspace)
        )
        
        # Git push
        if self.config["settings"]["auto_push"]:
            subprocess.run(["git", "push", "origin", "main"], cwd=str(self.workspace))
            self._log("INFO", "Pushed to main")
        
        return {"status": "success"}
    
    def run_workflow(self, task_description: str, audit_description: str, task_id: str):
        """Run full SOD workflow"""
        self._log("INFO", "Starting SOD workflow", task_id=task_id)
        
        # Step 1: L2 Implementation
        l2_result = self.run_l2_implementation(task_description, task_id)
        if l2_result["status"] != "success":
            self._log("ERROR", "L2 failed, stopping workflow")
            return {"status": "failed", "step": "l2"}
        
        # Step 2: Verify L2
        verify_result = self.verify_l2_output(l2_result["evidence_path"])
        if verify_result["status"] != "success":
            self._log("ERROR", "L2 verification failed, stopping workflow")
            return {"status": "failed", "step": "l2_verify"}
        
        # Step 3: L3 Audit
        l3_result = self.run_l3_audit(audit_description, task_id)
        if l3_result["status"] != "success":
            self._log("ERROR", "L3 failed, stopping workflow")
            return {"status": "failed", "step": "l3"}
        
        # Step 4: Gate Decision
        gate_result = self.make_gate_decision(l3_result, task_id)
        
        if gate_result["decision"] == "APPROVED":
            self._log("INFO", "Workflow APPROVED", task_id=task_id)
            return {"status": "approved", "l3_evidence": l3_result["evidence_path"]}
        elif gate_result["decision"] == "NEEDS_FIX":
            self._log("INFO", "Workflow NEEDS_FIX, loop back to L2", task_id=task_id)
            return {"status": "needs_fix"}
        else:
            self._log("ERROR", "Workflow INVALID", task_id=task_id)
            return {"status": "invalid"}

if __name__ == "__main__":
    config_path = "C:/Users/GHC/.openclaw/workspace/OMEGA_QUANT/.ly_state/config/sod_automation.json"
    
    automation = SODAutomation(config_path)
    
    # Example usage
    task_id = "production_readiness_checklist"
    task_description = "Fix pytest collection errors"
    audit_description = "Audit production readiness checklist"
    
    result = automation.run_workflow(task_description, audit_description, task_id)
    
    print(f"\nWorkflow result: {result}")
    sys.exit(0 if result["status"] == "approved" else 1)
