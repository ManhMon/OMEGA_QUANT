"""
Tests for Phase 2 UI component lifecycle patterns and 16-Dimension Master Matrix.
Verifies all 10 Phase 2 components implement:
1. 500ms debounce
2. requestAnimationFrame (RAF)
3. cancelAnimationFrame (cleanup)
4. AbortController / abort() signal cancellation
5. setData(null) / stale state reset
"""

from pathlib import Path
import json
import re
import pytest


PHASE2_COMPONENTS = [
    "omega-ui/src/modules/chart_station/VpinToxicityPanel.tsx",
    "omega-ui/src/modules/chart_station/OrderbookDepthWaterfall.tsx",
    "omega-ui/src/modules/chart_station/MarketImpactCurve.tsx",
    "omega-ui/src/modules/chart_station/FracDiffMemoryIndicator.tsx",
    "omega-ui/src/modules/barra_risk_tca/CircuitBreakerStatusStrip.tsx",
    "omega-ui/src/modules/barra_risk_tca/HistoricalStressScenarioPicker.tsx",
    "omega-ui/src/modules/barra_risk_tca/ContagionGraphCanvas.tsx",
    "omega-ui/src/modules/barra_risk_tca/LiquidityConstraintTable.tsx",
    "omega-ui/src/modules/fundamental_matrix/OwnershipSupplyChainGraph.tsx",
    "omega-ui/src/modules/fundamental_matrix/CorporateGraphDrawer.tsx",
]


def test_package_json_has_test_script():
    """Verify omega-ui/package.json contains 'test' script."""
    pkg_path = Path("omega-ui/package.json")
    assert pkg_path.exists(), "omega-ui/package.json not found"
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    assert "scripts" in pkg, "scripts section missing in package.json"
    assert "test" in pkg["scripts"], "'test' script missing in package.json"
    assert len(pkg["scripts"]["test"]) > 0


@pytest.mark.parametrize("comp_path", PHASE2_COMPONENTS)
def test_component_lifecycle_500ms_debounce(comp_path):
    """Verify component has 500ms debounce timeout."""
    p = Path(comp_path)
    assert p.exists(), f"Component file {comp_path} does not exist"
    code = p.read_text(encoding="utf-8")
    assert "500" in code, f"{comp_path} missing 500ms debounce"
    assert "setTimeout" in code, f"{comp_path} missing setTimeout debounce"
    assert "clearTimeout" in code, f"{comp_path} missing clearTimeout cleanup"


@pytest.mark.parametrize("comp_path", PHASE2_COMPONENTS)
def test_component_lifecycle_raf_and_cancel(comp_path):
    """Verify component has requestAnimationFrame and cancelAnimationFrame cleanup."""
    p = Path(comp_path)
    assert p.exists(), f"Component file {comp_path} does not exist"
    code = p.read_text(encoding="utf-8")
    assert "requestAnimationFrame" in code, f"{comp_path} missing requestAnimationFrame"
    assert "cancelAnimationFrame" in code, f"{comp_path} missing cancelAnimationFrame"
    assert "rafRef" in code, f"{comp_path} missing rafRef"


@pytest.mark.parametrize("comp_path", PHASE2_COMPONENTS)
def test_component_lifecycle_abort_controller(comp_path):
    """Verify component uses AbortController and abort() on unmount / re-fetch."""
    p = Path(comp_path)
    assert p.exists(), f"Component file {comp_path} does not exist"
    code = p.read_text(encoding="utf-8")
    assert "AbortController" in code, f"{comp_path} missing AbortController"
    assert ".abort()" in code, f"{comp_path} missing abort() invocation"
    assert "abortControllerRef" in code or "controller" in code, f"{comp_path} missing controller ref"


@pytest.mark.parametrize("comp_path", PHASE2_COMPONENTS)
def test_component_lifecycle_set_data_null_reset(comp_path):
    """Verify component clears stale data with setData(null) on parameter change."""
    p = Path(comp_path)
    assert p.exists(), f"Component file {comp_path} does not exist"
    code = p.read_text(encoding="utf-8")
    assert "setData(null)" in code, f"{comp_path} missing setData(null) reset"

