#!/usr/bin/env python3
"""Automates Restructuring Phase 3: Domain Reorganization for OMEGA_QUANT."""
import os
import re
import shutil
import subprocess
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
SRC_ROOT = WORKSPACE / "src" / "omega" / "quant"
TESTS_ROOT = WORKSPACE / "tests"

# 1. Define directory structure
DOMAINS = [
    "alpha",
    "feature",
    "ml",
    "portfolio",
    "execution",
    "risk",
    "data",
    "strategy",
    "signal",
    "backtest",
    "evolution",
    "monitoring",
    "utils",
]

# 2. Define exact file move mapping (source filename -> destination subpath)
MOVES = {
    # Alpha
    "alpha_factory.py": "alpha/factory.py",
    "alpha_factory_optimized.py": "alpha/optimized.py",
    "alpha_registry.py": "alpha/registry.py",
    "alpha_discovery.py": "alpha/discovery.py",
    "alpha_discovery_integration.py": "alpha/discovery_integration.py",
    "alpha_preprocessing.py": "alpha/preprocessing.py",
    "alpha_sanitizer.py": "alpha/sanitizer.py",
    "core_alphas.py": "alpha/core.py",
    "macro_alphas.py": "alpha/macro.py",
    "microstructure_alphas.py": "alpha/microstructure.py",
    "vn_alphas.py": "alpha/vn.py",
    "phase34_microstructure_alphas.py": "alpha/phase34.py",
    "phase35_walk_forward.py": "alpha/phase35.py",
    "phase6_evolution_engine.py": "alpha/phase6.py",
    "high_alpha_filter.py": "alpha/high_alpha_filter.py",
    "promoted_alphas.py": "alpha/promoted.py",
    "alpha_decay.py": "alpha/decay.py",

    # Feature
    "feature_engineering.py": "feature/engineering.py",
    "feature_factory.py": "feature/factory.py",
    "feature_module.py": "feature/module.py",
    "feature_pruning.py": "feature/pruning.py",
    "feature_discovery.py": "feature/discovery.py",
    "advanced_features.py": "feature/advanced.py",

    # ML
    "ml_gate_validator.py": "ml/gate_validator.py",
    "model_module.py": "ml/model_module.py",
    "alpha_ensemble_xgboost.py": "ml/ensemble_xgboost.py",
    "voting_stacking_ensemble.py": "ml/voting_stacking.py",
    "ab_tester.py": "ml/ab_tester.py",
    "autotune_optimizer.py": "ml/autotune.py",
    "hyperopt_layer.py": "ml/hyperopt.py",

    # Portfolio
    "position_sizer.py": "portfolio/position_sizer.py",
    "adaptive_portfolio_sizing.py": "portfolio/position_sizer_adaptive.py",
    "decorrelation_engine.py": "portfolio/decorrelation.py",
    "covariance_estimator.py": "portfolio/covariance.py",
    "markowitz_optimizer.py": "portfolio/markowitz.py",
    "constraint_solver.py": "portfolio/constraint_solver.py",
    "rebalancer.py": "portfolio/rebalancer.py",
    "sector_classifier.py": "portfolio/sector_classifier.py",
    "_portfolio_legacy.py": "portfolio/legacy.py",

    # Execution
    "trading_engine.py": "execution/trading_engine.py",
    "live_execution_bridge.py": "execution/live_bridge.py",
    "live_ingestor.py": "execution/live_ingestor.py",
    "paper_trading_engine.py": "execution/paper_trading.py",
    "multi_symbol_router.py": "execution/multi_symbol_router.py",
    "transaction_cost.py": "execution/transaction_cost.py",
    "transaction_cost_optimizer.py": "execution/transaction_cost_optimizer.py",

    # Risk
    "pit_guard.py": "risk/pit_guard.py",
    "pit_guardian.py": "risk/pit_guardian.py",
    "pit_manager.py": "risk/pit_manager.py",
    "realtime_risk_guard.py": "risk/realtime_risk.py",
    "stress_testing.py": "risk/stress_testing.py",

    # Data
    "data_sanitizer.py": "data/sanitizer.py",
    "data_validator.py": "data/validator.py",
    "data_source_config.py": "data/source_config.py",
    "vnstock_datasource.py": "data/vnstock.py",
    "vnstock_vci_datasource.py": "data/vnstock_vci.py",
    "vnstock_vci_ingest.py": "data/vci_ingest.py",
    "vci_integration.py": "data/vci_integration.py",
    "vn_market_flow_datasource.py": "data/vn_market.py",
    "vn_trading_calendar.py": "data/vn_trading_calendar.py",
    "dynamic_universe.py": "data/dynamic_universe.py",
    "corporate_action.py": "data/corporate_action.py",
    "data_module.py": "data/data_module.py",

    # Strategy
    "strategy_engine.py": "strategy/engine.py",
    "regime_detector_hmm.py": "strategy/regime_detector.py",
    "regime_switcher.py": "strategy/regime_switcher.py",
    "regime_aware_walk_forward.py": "strategy/regime_aware_wf.py",
    "market_microstructure.py": "strategy/market_microstructure.py",
    "market_regime.py": "strategy/market_regime.py",
    "macro_context.py": "strategy/macro_context.py",

    # Signal
    "signal_module.py": "signal/module.py",
    "signal_sanitizer.py": "signal/sanitizer.py",
    "smart_money_features.py": "signal/smart_money.py",
    "smart_money_microstructure.py": "signal/smart_money_micro.py",
    "sentiment_alpha.py": "signal/sentiment_alpha.py",

    # Backtest
    "parallel_backtest.py": "backtest/parallel.py",
    "cv_splitter.py": "backtest/cv_splitter.py",
    "target_module.py": "backtest/target_module.py",
    "label_engine.py": "backtest/label_engine.py",
    "multi_horizon_labels.py": "backtest/multi_horizon_labels.py",
    "walk_forward_engine.py": "backtest/walk_forward_engine.py",
    "walk_forward_ensemble.py": "backtest/walk_forward_ensemble.py",
    "walk_forward_alpha_ensemble_integration.py": "backtest/walk_forward_alpha_ensemble_integration.py",

    # Evolution
    "genetic_programming.py": "evolution/genetic_programming.py",
    "evolution_engine.py": "evolution/evolution_engine.py",
    "expression_generator.py": "evolution/expression_generator.py",
    "ensemble_builder.py": "evolution/ensemble_builder.py",

    # Monitoring
    "dashboard.py": "monitoring/dashboard.py",
    "attribution.py": "monitoring/attribution.py",
    "pnl_monitor.py": "monitoring/pnl_monitor.py",
    "performance_tracker.py": "monitoring/performance_tracker.py",
    "observability.py": "monitoring/observability.py",
    "experiment_tracker.py": "monitoring/experiment_tracker.py",

    # Utils
    "sanitization.py": "utils/sanitization.py",
    "math_utils.py": "utils/math_utils.py",
    "structure_features.py": "utils/structure_features.py",
    "midas_filters.py": "utils/midas_filters.py",
    "registry.py": "utils/registry.py",
    "promotion.py": "utils/promotion.py",
}

# 3. Create mapping of old import module names to new module names
# Note: we strip the ".py" extension for the module names
IMPORT_MAPPING = {}
for src_file, dest_path in MOVES.items():
    old_mod = f"omega.quant.{src_file[:-3]}"
    # e.g., alpha/factory.py -> alpha.factory
    new_sub = dest_path[:-3].replace("/", ".")
    new_mod = f"omega.quant.{new_sub}"
    IMPORT_MAPPING[old_mod] = new_mod


def run_git_mv(src: Path, dest: Path) -> bool:
    """Run git mv command."""
    if not src.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(["git", "mv", str(src), str(dest)], capture_output=True, text=True)
    if res.returncode == 0:
        return True
    else:
        # Fallback to standard move if not in git or error
        shutil.move(str(src), str(dest))
        return True


def create_init_files():
    """Ensure __init__.py exists in all domain directories."""
    for d in DOMAINS:
        init_file = SRC_ROOT / d / "__init__.py"
        if not init_file.exists():
            init_file.write_text(f'"""{d.capitalize()} domain package."""\n')


def update_exports_in_init():
    """Update __init__.py exports with the new subpackage paths."""
    init_path = SRC_ROOT / "__init__.py"
    if not init_path.exists():
        return

    content = init_path.read_text(encoding="utf-8")
    
    # Replace the legacy imports in _EXPORTS
    replacements = {
        '"AlphaRegistry": (_Q + "alpha_registry"': '"AlphaRegistry": (_Q + "alpha.registry"',
        '"AlphaRegistryConfig": (_Q + "alpha_registry"': '"AlphaRegistryConfig": (_Q + "alpha.registry"',
        '"AlphaMetadata": (_Q + "alpha_registry"': '"AlphaMetadata": (_Q + "alpha.registry"',
        '"AlphaFactory": (_Q + "alpha_factory"': '"AlphaFactory": (_Q + "alpha.factory"',
        '"ModelModule": (_Q + "model_module"': '"ModelModule": (_Q + "ml.model_module"',
        '"ModelConfig": (_Q + "model_module"': '"ModelConfig": (_Q + "ml.model_module"',
        '"SignalModule": (_Q + "signal_module"': '"SignalModule": (_Q + "signal.module"',
        '"SignalModuleConfig": (_Q + "signal_module"': '"SignalModuleConfig": (_Q + "signal.module"',
        '"FeatureFactory": (_Q + "feature_factory"': '"FeatureFactory": (_Q + "feature.factory"',
        '"GeneticProgrammingEngine": (\n        _Q + "genetic_programming"': '"GeneticProgrammingEngine": (\n        _Q + "evolution.genetic_programming"',
        '"GPConfig": (_Q + "genetic_programming"': '"GPConfig": (_Q + "evolution.genetic_programming"',
        '"EnsembleOptimizer": (_Q + "ensemble_optimizer"': '"EnsembleOptimizer": (_Q + "evolution.ensemble_optimizer"',
        '"WeightsConfig": (_Q + "ensemble_optimizer"': '"WeightsConfig": (_Q + "evolution.ensemble_optimizer"',
        '"ExperimentTracker": (_Q + "experiment_tracker"': '"ExperimentTracker": (_Q + "monitoring.experiment_tracker"',
        '"PITManager": (_Q + "pit_manager"': '"PITManager": (_Q + "risk.pit_manager"',
    }

    for target, replacement in replacements.items():
        content = content.replace(target, replacement)
        
    init_path.write_text(content, encoding="utf-8")
    print("Updated src/omega/quant/__init__.py _EXPORTS mapping.")


def update_imports_in_file(file_path: Path):
    """Scan and replace old imports in a single python file."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    original = content
    
    # 1. Update absolute imports: omega.quant.XXX -> omega.quant.domain.XXX
    # Sort keys by length descending to avoid partial matches
    sorted_old_mods = sorted(IMPORT_MAPPING.keys(), key=len, reverse=True)
    for old_mod in sorted_old_mods:
        new_mod = IMPORT_MAPPING[old_mod]
        # Match from omega.quant.XXX import ...
        content = re.sub(rf"\bfrom {re.escape(old_mod)}\b", f"from {new_mod}", content)
        # Match import omega.quant.XXX as ... or import omega.quant.XXX
        content = re.sub(rf"\bimport {re.escape(old_mod)}\b", f"import {new_mod}", content)
        
    # 2. Update relative imports inside the quant directory
    # If the file is inside src/omega/quant
    if SRC_ROOT in file_path.parents:
        # Match: from .alpha_registry import ... -> from omega.quant.alpha.registry import ...
        for src_file, dest_path in MOVES.items():
            base_name = src_file[:-3]
            new_sub = dest_path[:-3].replace("/", ".")
            # Case A: from .module import ...
            content = re.sub(rf"\bfrom \.{re.escape(base_name)}\b", f"from omega.quant.{new_sub}", content)
            # Case B: from ..module import ...
            content = re.sub(rf"\bfrom \.\.{re.escape(base_name)}\b", f"from omega.quant.{new_sub}", content)
            # Case C: from . import module -> from omega.quant.domain import module
            # Let's map e.g. from . import alpha_registry
            # to: from omega.quant.alpha import registry as alpha_registry (or just import from path)
            # Simplest and safest translation: replace with absolute import
            content = re.sub(rf"\bfrom \. import {re.escape(base_name)}\b", f"from omega.quant.{new_sub.rsplit('.', 1)[0]} import {new_sub.rsplit('.', 1)[1]} as {base_name}", content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        # Validate syntax to catch regex replacement issues
        res = subprocess.run(["python", "-m", "py_compile", str(file_path)], capture_output=True)
        if res.returncode != 0:
            print(f"WARNING: Syntax check failed for {file_path} after updates:\n{res.stderr.decode()}")
            # Revert to original on syntax failure
            file_path.write_text(original, encoding="utf-8")


def update_all_codebase_imports():
    """Scan and update imports across the whole codebase."""
    print("Updating imports in src/ ...")
    for root, _, files in os.walk(WORKSPACE / "src"):
        for file in files:
            if file.endswith(".py"):
                update_imports_in_file(Path(root) / file)
                
    print("Updating imports in tests/ ...")
    for root, _, files in os.walk(TESTS_ROOT):
        for file in files:
            if file.endswith(".py"):
                update_imports_in_file(Path(root) / file)

    print("Updating imports in scripts/ ...")
    for root, _, files in os.walk(WORKSPACE / "scripts"):
        for file in files:
            if file.endswith(".py"):
                update_imports_in_file(Path(root) / file)


def main():
    print("=" * 60)
    print("OMEGA_QUANT Restructuring Phase 3: Domain Reorganization")
    print("=" * 60)

    # 1. Create domain directories
    print("Creating domain directories...")
    for d in DOMAINS:
        (SRC_ROOT / d).mkdir(parents=True, exist_ok=True)
    create_init_files()

    # 2. Perform file moves
    print("Moving files to domain subdirectories...")
    moved_count = 0
    for src_name, dest_rel in MOVES.items():
        src_path = SRC_ROOT / src_name
        dest_path = SRC_ROOT / dest_rel
        if run_git_mv(src_path, dest_path):
            print(f"  [MOVE] {src_name} -> {dest_rel}")
            moved_count += 1

    print(f"Successfully moved {moved_count} files.")

    # 3. Update __init__.py exports
    update_exports_in_init()

    # 4. Update imports across the codebase
    print("Updating imports across codebase...")
    update_all_codebase_imports()
    print("Imports update complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
