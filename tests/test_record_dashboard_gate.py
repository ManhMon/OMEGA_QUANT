"""
Tests for scripts/record_dashboard_gate.py
Tests both legacy format and Gate Contract format parsing.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path to import the module
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestRecordDashboardGate(unittest.TestCase):
    """Test suite for record_dashboard_gate.py"""
    
    def setUp(self):
        """Set up test fixtures"""
        import uuid
        self.test_dir = os.path.join(tempfile.gettempdir(), f"tmp_gate_test_{uuid.uuid4().hex}")
        os.makedirs(self.test_dir, exist_ok=True)
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir)
        
        # Create .ly_state/session directory structure
        os.makedirs('.ly_state/session', exist_ok=True)
        
        # Create mock provenance file with a valid session ID
        self.valid_uuid = 'b78faef6-5251-4238-bfb2-b04209df2e1e'
        loaded_skills = {
            'session_id': self.valid_uuid,
            'loaded_at': '2026-06-09T08:00:00Z',
            'skills': []
        }
        with open('.ly_state/session/loaded_skills.json', 'w') as f:
            json.dump(loaded_skills, f)
    
    def tearDown(self):
        """Clean up test fixtures"""
        os.chdir(self.original_dir)
        if os.path.exists(self.test_dir):
            import shutil
            import stat
            def _onerror(func, path, exc_info):
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception:
                    pass
            shutil.rmtree(self.test_dir, onerror=_onerror)
    
    def create_audit_report(self, filename, content):
        """Helper to create an audit report file"""
        report_path = Path(self.test_dir) / filename
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return report_path
    
    @patch('subprocess.run')
    def test_legacy_format_approved(self, mock_subprocess):
        """Test that legacy uppercase VERDICT format is accepted"""
        mock_subprocess.return_value = MagicMock(returncode=0, stdout='PASS')
        
        report_content = f"""
# Legacy Audit Report

VERDICT: [APPROVED]

Session ID: {self.valid_uuid}
Session Key: role21_audit_legacy_20260609
L2 Session ID: {self.valid_uuid}

## Details
Everything looks good.
"""
        report_path = self.create_audit_report('legacy_report.md', report_content)
        
        # Import and run the verification
        from scripts.record_dashboard_gate import verify_and_record
        
        with patch('sys.argv', ['record_dashboard_gate.py', '--report-path', str(report_path)]):
            try:
                verify_and_record()
                # Check that phase_gates.json was created
                self.assertTrue(Path('.ly_state/session/phase_gates.json').exists())
                with open('.ly_state/session/phase_gates.json', 'r') as f:
                    gates = json.load(f)
                    self.assertEqual(len(gates), 1)
                    self.assertEqual(gates[0]['final_verdict'], '[APPROVED]')
                    self.assertEqual(gates[0]['l3_session_id'], self.valid_uuid)
                print("✓ Legacy format test PASSED")
            except SystemExit as e:
                self.fail(f"Legacy format test failed with exit code {e.code}")
    
    @patch('subprocess.run')
    def test_gate_contract_format_approved(self, mock_subprocess):
        """Test that Gate Contract format is accepted"""
        mock_subprocess.return_value = MagicMock(returncode=0, stdout='PASS')
        
        report_content = f"""
# Role 21 Audit: Gate Contract Format

- Role: Code Reviewer / Role 21
- Verdict: [APPROVED]
- PIT Safety: N/A
- Role Compliance: PASS
- Gate Contract:
  - l3_session_id: {self.valid_uuid}
  - l3_session_key: role21_audit_gatecontract_20260609
  - audit_report_path: .ly_state/session/audit_reports/test_report.md
  - final_verdict: [APPROVED]

## Findings
No blockers found.
"""
        report_path = self.create_audit_report('gate_contract_report.md', report_content)
        
        from scripts.record_dashboard_gate import verify_and_record
        
        with patch('sys.argv', ['record_dashboard_gate.py', '--report-path', str(report_path)]):
            try:
                verify_and_record()
                self.assertTrue(Path('.ly_state/session/phase_gates.json').exists())
                with open('.ly_state/session/phase_gates.json', 'r') as f:
                    gates = json.load(f)
                    self.assertEqual(len(gates), 1)
                    self.assertEqual(gates[0]['final_verdict'], '[APPROVED]')
                    self.assertEqual(gates[0]['l3_session_id'], self.valid_uuid)
                    # L2 session ID should be marked as not provided
                    self.assertEqual(gates[0]['l2_session_id'], 'not_provided_in_audit_report')
                print("✓ Gate Contract format test PASSED")
            except SystemExit as e:
                self.fail(f"Gate Contract format test failed with exit code {e.code}")
    
    def test_needs_fix_rejected(self):
        """Test that [NEEDS_FIX] verdict is rejected"""
        report_content = f"""
# Audit Report

VERDICT: [NEEDS_FIX]

Session ID: {self.valid_uuid}
Session Key: role21_audit_needsfix_20260609
L2 Session ID: {self.valid_uuid}

## Issues Found
Several problems need to be addressed.
"""
        report_path = self.create_audit_report('needs_fix_report.md', report_content)
        
        from scripts.record_dashboard_gate import verify_and_record
        
        with patch('sys.argv', ['record_dashboard_gate.py', '--report-path', str(report_path)]):
            with self.assertRaises(SystemExit) as cm:
                verify_and_record()
            self.assertEqual(cm.exception.code, 1)
            print("✓ NEEDS_FIX rejection test PASSED")
    
    def test_synthetic_session_rejected(self):
        """Test that synthetic/fake session IDs are rejected"""
        report_content = """
# Audit Report

VERDICT: [APPROVED]

Session ID: fake-session-id-12345
Session Key: synthetic-key
L2 Session ID: test-session

## Details
This should be rejected due to synthetic IDs.
"""
        report_path = self.create_audit_report('synthetic_report.md', report_content)
        
        from scripts.record_dashboard_gate import verify_and_record
        
        with patch('sys.argv', ['record_dashboard_gate.py', '--report-path', str(report_path)]):
            with self.assertRaises(SystemExit) as cm:
                verify_and_record()
            self.assertEqual(cm.exception.code, 1)
            print("✓ Synthetic session rejection test PASSED")
    
    def test_missing_verdict_rejected(self):
        """Test that reports without verdict are rejected"""
        report_content = f"""
# Audit Report

Session ID: {self.valid_uuid}
Session Key: role21_audit_noverdict_20260609
L2 Session ID: {self.valid_uuid}

## Details
No verdict line present.
"""
        report_path = self.create_audit_report('no_verdict_report.md', report_content)
        
        from scripts.record_dashboard_gate import verify_and_record
        
        with patch('sys.argv', ['record_dashboard_gate.py', '--report-path', str(report_path)]):
            with self.assertRaises(SystemExit) as cm:
                verify_and_record()
            self.assertEqual(cm.exception.code, 1)
            print("✓ Missing verdict rejection test PASSED")
    
    def test_conflicting_verdict_rejected(self):
        """Test that conflicting Verdict and final_verdict are rejected (negative regression test)"""
        report_content = f"""
# Role 21 Audit Report: Conflicting Verdicts

- Role: Code Reviewer / Role 21
- Verdict: [APPROVED]
- PIT Safety: N/A
- Role Compliance: PASS
- Gate Contract:
  - l3_session_id: {self.valid_uuid}
  - l3_session_key: role21_audit_conflict_20260609
  - audit_report_path: .ly_state/session/audit_reports/test_conflict.md
  - final_verdict: [NEEDS_FIX]

## Findings
This report has conflicting verdicts and should be rejected.
"""
        report_path = self.create_audit_report('conflict_report.md', report_content)
        
        from scripts.record_dashboard_gate import verify_and_record
        
        with patch('sys.argv', ['record_dashboard_gate.py', '--report-path', str(report_path)]):
            with self.assertRaises(SystemExit) as cm:
                verify_and_record()
            # Must exit with code 1
            self.assertEqual(cm.exception.code, 1)
            
            # Must NOT record a gate
            if Path('.ly_state/session/phase_gates.json').exists():
                with open('.ly_state/session/phase_gates.json', 'r') as f:
                    gates = json.load(f)
                    # Should be empty or not contain this conflicting gate
                    for gate in gates:
                        if isinstance(gate, dict):
                            self.assertNotEqual(gate.get('l3_session_key'), 'role21_audit_conflict_20260609')
            
            print("✓ Conflicting verdict rejection test PASSED")
    
    @patch('subprocess.run')
    def test_real_audit_report_format(self, mock_subprocess):
        """Test the actual audit report format from role21_audit_wiring_fix_reaudit_20260609.md"""
        mock_subprocess.return_value = MagicMock(returncode=0, stdout='PASS')
        
        # This is the exact format from the real audit report
        report_content = f"""# Role 21 Re-Audit: audit_wiring legacy false positives

- Role: Code Reviewer / Role 21
- Verdict: [APPROVED]
- PIT Safety: N/A
- Role Compliance: PASS
- Gate Contract:
  - l3_session_id: {self.valid_uuid}
  - l3_session_key: role21_audit_wiring_fix_reaudit_20260609
  - audit_report_path: .ly_state/session/audit_reports/role21_audit_wiring_fix_reaudit_20260609.md
  - final_verdict: [APPROVED]

## Scope

Inputs reviewed:
- .ly_state/session/l2_audit_wiring_fix_report_20260609.md
- .ly_state/session/audit_wiring_l2_opencode_retry_20260609.jsonl

Files audited:
- scripts/audit_wiring.py
- tests/test_audit_wiring.py

## Findings

No blockers found.
"""
        report_path = self.create_audit_report('real_audit_report.md', report_content)
        
        from scripts.record_dashboard_gate import verify_and_record
        
        with patch('sys.argv', ['record_dashboard_gate.py', '--report-path', str(report_path)]):
            try:
                verify_and_record()
                self.assertTrue(Path('.ly_state/session/phase_gates.json').exists())
                with open('.ly_state/session/phase_gates.json', 'r') as f:
                    gates = json.load(f)
                    self.assertEqual(len(gates), 1)
                    self.assertEqual(gates[0]['final_verdict'], '[APPROVED]')
                    self.assertEqual(gates[0]['l3_session_id'], self.valid_uuid)
                    self.assertEqual(gates[0]['l3_session_key'], 'role21_audit_wiring_fix_reaudit_20260609')
                print("✓ Real audit report format test PASSED")
            except SystemExit as e:
                self.fail(f"Real audit report format test failed with exit code {e.code}")


if __name__ == '__main__':
    print("Running record_dashboard_gate tests...\n")
    unittest.main(verbosity=2)
