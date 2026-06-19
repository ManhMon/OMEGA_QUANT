import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("import_smoke_test")

modules_to_test = [
    # Root modules (still in root)
    "omega.quant.quant_engine",
    "omega.quant.pipeline_factory",
    "omega.quant.ultimate_alpha_arsenal",
    "omega.quant.neutralization",
    "omega.quant.portfolio_optimizer",
    "omega.quant.execution_sim",
    "omega.quant.signal_blender",
    "omega.quant.backtest_engine",
    
    # Reorganized Domain modules
    "omega.quant.alpha.factory",
    "omega.quant.alpha.optimized",
    "omega.quant.alpha.discovery",
    "omega.quant.alpha.promoted",
    "omega.quant.feature.engineering",
    "omega.quant.feature.factory",
    "omega.quant.feature.module",
    "omega.quant.feature.pruning",
    "omega.quant.portfolio.position_sizer",
    "omega.quant.execution.trading_engine",
    "omega.quant.execution.live_bridge",
    "omega.quant.risk.pit_guard",
    "omega.quant.risk.pit_guardian",
    "omega.quant.risk.pit_manager",
    "omega.quant.data.sanitizer",
    "omega.quant.data.validator",
    "omega.quant.strategy.engine",
    "omega.quant.signal.module",
    "omega.quant.signal.sanitizer",
    "omega.quant.backtest.parallel",
    "omega.quant.backtest.cv_splitter",
    "omega.quant.ml.voting_stacking",
    "omega.quant.alpha.phase35",
    
    # Package modules (verification)
    "omega.quant.pipeline",
    "omega.quant.walk_forward",
    "omega.quant.ml.ml_engine",
    "omega.quant.portfolio.portfolio_optimizer"
]

failed_imports = 0

logger.info("Starting import smoke test...")
for mod in modules_to_test:
    try:
        __import__(mod)
        logger.info(f"  ✓ {mod} imported successfully")
    except ImportError as e:
        logger.error(f"  ✗ {mod} failed to import: {e}")
        failed_imports += 1
    except Exception as e:
        logger.error(f"  ✗ {mod} failed with unexpected error: {e}")
        failed_imports += 1

if failed_imports > 0:
    logger.error(f"Import smoke test FAILED with {failed_imports} errors")
    sys.exit(1)
else:
    logger.info("Import smoke test PASSED successfully!")
    sys.exit(0)
