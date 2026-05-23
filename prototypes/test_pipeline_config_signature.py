#!/usr/bin/env python3
"""Test PipelineConfig signature enforcement."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "packages" / "core" / "src"))
sys.path.insert(0, str(Path.cwd() / "packages" / "data" / "src"))

# Mock imports
import types
sys.modules['omega.data'] = types.ModuleType('omega.data')
sys.modules['omega.data.loader'] = types.ModuleType('omega.data.loader')
sys.modules['omega.features'] = types.ModuleType('omega.features')
sys.modules['omega.features.feature_factory'] = types.ModuleType('omega.features.feature_factory')
sys.modules['omega.quant'] = types.ModuleType('omega.quant')
sys.modules['omega.quant.alpha_generator'] = types.ModuleType('omega.quant.alpha_generator')
sys.modules['omega.quant.portfolio_optimizer'] = types.ModuleType('omega.quant.portfolio_optimizer')
sys.modules['omega.quant.execution_sim'] = types.ModuleType('omega.quant.execution_sim')
sys.modules['omega.risk'] = types.ModuleType('omega.risk')
sys.modules['omega.risk.individual_risk_guard'] = types.ModuleType('omega.risk.individual_risk_guard')
sys.modules['omega.observability'] = types.ModuleType('omega.observability')
sys.modules['omega.observability.logger'] = types.ModuleType('omega.observability.logger')

class DataLoader: pass
class FeatureFactory: pass
class AlphaGenerator: pass
class PortfolioOptimizer: pass
class ExecutionSimulator: pass
class IndividualRiskGuard: pass
def get_logger(name): return None

sys.modules['omega.data.loader'].DataLoader = DataLoader
sys.modules['omega.features.feature_factory'].FeatureFactory = FeatureFactory
sys.modules['omega.quant.alpha_generator'].AlphaGenerator = AlphaGenerator
sys.modules['omega.quant.portfolio_optimizer'].PortfolioOptimizer = PortfolioOptimizer
sys.modules['omega.quant.execution_sim'].ExecutionSimulator = ExecutionSimulator
sys.modules['omega.risk.individual_risk_guard'].IndividualRiskGuard = IndividualRiskGuard
sys.modules['omega.observability.logger'].get_logger = get_logger

import inspect
from omega.core.pipeline import PipelineConfig

print("=" * 60)
print("PipelineConfig Signature Test")
print("=" * 60)

# Test 1: Try to instantiate without args
print("\nTest 1: Try PipelineConfig() without args")
try:
    config = PipelineConfig()
    print("FAIL: Should require arguments")
except TypeError as e:
    print(f"PASS: Raises TypeError: {e}")

# Test 2: Check signature
sig = inspect.signature(PipelineConfig)
print(f"\nSignature: {sig}")
params = list(sig.parameters.keys())
print(f"Parameters: {params}")

# Check for defaults
print("\nParameter defaults:")
for param_name, param in sig.parameters.items():
    if param.default == inspect.Parameter.empty:
        print(f"  {param_name}: MANDATORY (no default)")
    else:
        print(f"  {param_name}: optional (default={param.default})")

# Test 3: Verify as_of_time is mandatory
print("\nTest 2: Verify as_of_time is mandatory")
sig = inspect.signature(PipelineConfig)
as_of_time_param = sig.parameters.get('as_of_time')
if as_of_time_param and as_of_time_param.default == inspect.Parameter.empty:
    print("PASS: as_of_time has no default")
else:
    print("FAIL: as_of_time has default or missing")

print("\n" + "=" * 60)
