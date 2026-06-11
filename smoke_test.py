"""Smoke test for monolith migration verification."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

tests = [
    ("omega.core.pipeline", "OmegaPipeline"),
    ("omega.core.event_bus", "EventBus"),
    ("omega.core.database", None),
    ("omega.quant.alpha.discovery", None),       # was: omega.quant.alpha_discovery (deprecated)
    ("omega.quant.portfolio_optimizer", None),
    ("omega.quant.risk.pit_guard", None),         # was: omega.quant.pit_guard (deprecated)
    ("omega.risk.risk_manager", None),
    ("omega.risk.circuit_breaker", None),
    ("omega.data.loader", None),
    ("omega.data.registry", None),
    ("omega.execution.execution_engine", None),
    ("omega.execution.order_router", None),
    ("omega.memory.memory_archive", None),
    ("omega.observability.metrics", None),
    ("omega.security.core", None),
    ("omega.governance.audit_trail", None),
    ("omega.contracts.schemas", None),
    ("omega.backtest.walk_forward_engine", None),
    ("omega.quant.evolution.genetic_engine", None),
    ("omega.quant.portfolio.adaptive_sizing_overlay", None),
    ("omega.quant.universe.xgb_classifier", None),
    ("omega.quant.validation.cpcv", None),
]

results = []
for mod, cls in tests:
    try:
        m = __import__(mod, fromlist=[cls] if cls else [""])
        if cls:
            getattr(m, cls)
        results.append(("OK", mod, None))
    except Exception as e:
        results.append(("ERR", mod, f"{type(e).__name__}: {e}"))

for status, mod, err in results:
    if status == "OK":
        print(f"OK  {mod}")
    else:
        print(f"ERR {mod}")
        print(f"    {err}")

ok = sum(1 for s, _, _ in results if s == "OK")
err = sum(1 for s, _, _ in results if s == "ERR")
print()
print(f"PASS: {ok}/{len(results)}, FAIL: {err}")
sys.exit(0 if err == 0 else 1)
