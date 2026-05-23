"""
Phase 9 Test Suite Runner
Backend Engineer (Role 9) - L2 OpenCode

Runs all Phase 9 integration tests and generates a comprehensive report.
"""

import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime


def run_test_suite():
    """Run the complete Phase 9 test suite."""
    
    print("=" * 80)
    print("OMEGA_QUANT Phase 9: End-to-End Test Suite")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    test_files = [
        "tests/phase9/test_layer1_data_ingestion.py",
        "tests/phase9/test_layer2_feature_engineering.py",
        "tests/phase9/test_layer3_alpha_generation.py",
        "tests/phase9/test_layer4_risk_management.py",
        "tests/phase9/test_layer5_portfolio_construction.py",
        "tests/phase9/test_layer6_execution.py",
        "tests/phase9/test_layer7_monitoring.py",
        "tests/phase9/test_pit_safety_boundaries.py",
        "tests/phase9/test_full_data_flow.py",
        "tests/phase9/test_e2e_pipeline.py"
    ]
    
    results = {}
    total_passed = 0
    total_failed = 0
    total_skipped = 0
    
    for test_file in test_files:
        print(f"\nRunning: {test_file}")
        print("-" * 80)
        
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Parse output for pass/fail counts
            output = result.stdout + result.stderr
            
            # Simple parsing (can be improved)
            passed = output.count(" PASSED")
            failed = output.count(" FAILED")
            skipped = output.count(" SKIPPED")
            
            results[test_file] = {
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "return_code": result.returncode
            }
            
            total_passed += passed
            total_failed += failed
            total_skipped += skipped
            
            print(f"  Passed: {passed}, Failed: {failed}, Skipped: {skipped}")
            
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT: Test file took too long to execute")
            results[test_file] = {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "return_code": -1,
                "error": "timeout"
            }
        except Exception as e:
            print(f"  ERROR: {e}")
            results[test_file] = {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "return_code": -1,
                "error": str(e)
            }
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUITE SUMMARY")
    print("=" * 80)
    print(f"Total Passed:  {total_passed}")
    print(f"Total Failed:  {total_failed}")
    print(f"Total Skipped: {total_skipped}")
    print(f"Total Tests:   {total_passed + total_failed + total_skipped}")
    
    if total_failed == 0:
        print("\n✓ ALL TESTS PASSED!")
        pass_rate = 100.0
    else:
        pass_rate = (total_passed / (total_passed + total_failed)) * 100 if (total_passed + total_failed) > 0 else 0
        print(f"\n✗ {total_failed} tests failed")
    
    print(f"Pass Rate: {pass_rate:.1f}%")
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Save results to JSON
    results_file = Path("tests/phase9/test_results.json")
    with open(results_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_passed": total_passed,
                "total_failed": total_failed,
                "total_skipped": total_skipped,
                "pass_rate": pass_rate
            },
            "details": results
        }, f, indent=2)
    
    print(f"\nResults saved to: {results_file}")
    
    return total_failed == 0


if __name__ == "__main__":
    success = run_test_suite()
    sys.exit(0 if success else 1)
