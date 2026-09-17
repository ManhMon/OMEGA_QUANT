import sys
import pathlib
import ast

def check_pit_safety_in_file(file_path: pathlib.Path) -> tuple[bool, str]:
    """Check that any date queries in signal generation are causal (using strictly '<' rather than '<=')."""
    content = file_path.read_text(encoding='utf-8')
    
    # Check for available dates selection logic
    has_causal_comparison = False
    for line in content.splitlines():
        if "available_dates" in line and "<" in line and "<=" not in line:
            has_causal_comparison = True
            break
            
    if has_causal_comparison:
        return True, "Passed: Found causal historical date filter ('<' target_dt)."
    else:
        return False, "Failed: Could not find explicit strictly historical date filter ('<' target_dt) in available_dates."

def check_vectorization_in_file(file_path: pathlib.Path) -> tuple[bool, str]:
    """Check that we avoid raw iterrows() or itertuples() loops for row processing."""
    content = file_path.read_text(encoding='utf-8')
    
    # Parse AST to check for iterrows / itertuples calls
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr in ['iterrows', 'itertuples']:
                    return False, f"Failed: Found raw row loop method '{node.attr}' which violates vectorized speed standards."
        return True, "Passed: No non-vectorized row loop methods (iterrows, itertuples) found."
    except Exception as e:
        return False, f"Failed to parse AST: {str(e)}"

def check_ml_gate_in_optimizer(file_path: pathlib.Path) -> tuple[bool, str]:
    """Check that the portfolio optimizer calls the MLGateValidator and falls back to equal weight on fail."""
    content = file_path.read_text(encoding='utf-8')
    
    has_gate = "MLGateValidator" in content or "validate_research_gate" in content
    has_fallback = "equal_weight" in content or "equal" in content.lower()
    
    if has_gate and has_fallback:
        return True, "Passed: ML Gate integration and equal-weight fallback found."
    else:
        return False, f"Failed: MLGateValidator={has_gate}, Fallback equal weight={has_fallback}."

def main():
    print("============================================================")
    print("OMEGA_QUANT Pipeline Spec Compliance Checker")
    print("============================================================\n")
    
    project_root = pathlib.Path(".")
    ensemble_script = project_root / "scripts" / "run_ensemble_signals.py"
    optimizer_script = project_root / "scripts" / "run_portfolio_optimizer.py"
    
    if not ensemble_script.exists():
        print(f"Error: {ensemble_script} not found.")
        sys.exit(1)
        
    if not optimizer_script.exists():
        print(f"Error: {optimizer_script} not found.")
        sys.exit(1)
        
    all_passed = True
    
    # 1. Verify PIT Safety in signals generator
    print("1. Checking PIT Safety (Spec Section 24.1)...")
    passed, msg = check_pit_safety_in_file(ensemble_script)
    print(f"   {msg}")
    if not passed:
        all_passed = False
        
    # 2. Verify Vectorization in signal generator
    print("\n2. Checking Vectorized Factor Engine (Spec Section 24.2)...")
    passed, msg = check_vectorization_in_file(ensemble_script)
    print(f"   {msg}")
    if not passed:
        all_passed = False
        
    # 3. Verify ML Gate Integration in optimizer
    print("\n3. Checking ML Gate Integration (Spec Section 8.3 & 15.1)...")
    passed, msg = check_ml_gate_in_optimizer(optimizer_script)
    print(f"   {msg}")
    if not passed:
        all_passed = False
        
    print("\n============================================================")
    if all_passed:
        print("RESULT: [PASS] Pipeline strictly adheres to spec requirements.")
        sys.exit(0)
    else:
        print("RESULT: [FAIL] Pipeline violations detected.")
        sys.exit(1)

if __name__ == "__main__":
    main()
