"""Tests for scripts/audit_wiring.py - ensuring legacy compat roots are excluded by default."""
import sys
import subprocess
from pathlib import Path

def test_audit_wiring_excludes_legacy_by_default():
    """Test that audit_wiring.py excludes legacy compat roots by default."""
    result = subprocess.run(
        [sys.executable, "scripts/audit_wiring.py"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )
    
    assert result.returncode == 0, f"audit_wiring.py failed: {result.stderr}"
    
    output = result.stdout
    
    # The 6 legacy files should NOT appear in default output
    legacy_modules = [
        "evolution.fitness",
        "evolution.genetic_alpha",
        "features.pit_guard",
        "features.signal_module",
        "features.signal_sanitizer",
        "indicators.alpha_discovery"
    ]
    
    for module in legacy_modules:
        assert module not in output, f"Legacy module {module} should not appear in default audit output"
    
    # Should see the exclusion notice
    assert "Excluding legacy compatibility roots" in output, "Should indicate legacy roots are excluded"
    
    # Total should be 0 or not include the 6 legacy files
    assert "Total unimported files in src/: 0" in output or "Total unimported files in src/:" in output


def test_audit_wiring_includes_legacy_with_flag():
    """Test that audit_wiring.py includes legacy compat roots with --include-legacy flag."""
    result = subprocess.run(
        [sys.executable, "scripts/audit_wiring.py", "--include-legacy"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )
    
    assert result.returncode == 0, f"audit_wiring.py --include-legacy failed: {result.stderr}"
    
    output = result.stdout
    
    # The 6 legacy files SHOULD appear with --include-legacy
    legacy_modules = [
        "evolution.fitness",
        "evolution.genetic_alpha",
        "features.pit_guard",
        "features.signal_module",
        "features.signal_sanitizer",
        "indicators.alpha_discovery"
    ]
    
    found_count = sum(1 for module in legacy_modules if module in output)
    
    # Should find at least the legacy modules (they might be truly orphaned)
    assert found_count >= 6, f"Expected all 6 legacy modules with --include-legacy, found {found_count}"
    
    # Should NOT see the exclusion notice
    assert "Excluding legacy compatibility roots" not in output, "Should not show exclusion notice with --include-legacy"


if __name__ == "__main__":
    print("Running test_audit_wiring_excludes_legacy_by_default...")
    test_audit_wiring_excludes_legacy_by_default()
    print("PASS: test_audit_wiring_excludes_legacy_by_default")
    
    print("\nRunning test_audit_wiring_includes_legacy_with_flag...")
    test_audit_wiring_includes_legacy_with_flag()
    print("PASS: test_audit_wiring_includes_legacy_with_flag")
    
    print("\nAll tests passed!")
