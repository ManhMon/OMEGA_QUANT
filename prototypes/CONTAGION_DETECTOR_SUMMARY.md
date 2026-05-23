# Global Contagion Detector - Implementation Summary

**Date**: 2026-04-26  
**Layer**: Layer 08 (Situational Awareness) + Layer 04 (Risk Management)  
**Status**: ✅ COMPLETE - All tests passing (24/24)

---

## 📋 Implementation Overview

Successfully implemented a Global Contagion Detector that monitors correlation spillover from global markets (S&P 500, Hang Seng, Shanghai Composite) to VN-Index, integrating Country Intelligence Index (CII) scores to weight risk by country instability.

---

## 🎯 Deliverables

### 1. Core Module: `contagion_detector.py`
**Location**: `src/v21_system/layer_08_situational_awareness/contagion_detector.py`

**Key Features**:
- ✅ Correlation monitoring between VN-Index and global indices (SPX, HSI, SSE)
- ✅ Spreading Risk Index (SRI) calculation using rolling volatility and correlation shifts
- ✅ CII integration to weight risk by country instability
- ✅ Market Stress Signal output (GREEN/YELLOW/RED)
- ✅ Vectorized operations (NumPy) for performance
- ✅ Point-in-time (PIT) safe - all timestamps explicit
- ✅ No look-ahead bias

**Classes**:
- `GlobalContagionDetector`: Main detector class
- `MarketStressLevel`: Enum (GREEN/YELLOW/RED)
- `GlobalIndexData`: Input data structure
- `CorrelationMetrics`: Correlation and volatility metrics
- `SpreadingRiskIndex`: SRI score with component breakdown
- `ContagionReport`: Complete risk report

**SRI Methodology** (0-100 points):
1. **Correlation Component** (0-40 points):
   - High correlation (>0.7): +20 points per index
   - Correlation shift (>0.2): +10 points per index

2. **Volatility Component** (0-30 points):
   - High volatility (>25%): +15 points per index
   - Volatility shift (>5pp): +10 points per index

3. **CII Component** (0-30 points):
   - High CII (>60) + High correlation: +15 points per index
   - Medium CII (40-60) + High correlation: +10 points per index

**Stress Levels**:
- GREEN: SRI < 30 (normal conditions)
- YELLOW: SRI 30-60 (elevated risk)
- RED: SRI > 60 (high contagion risk)

---

### 2. Risk Manager Integration: `contagion_risk_validator.py`
**Location**: `V21_QUANT/src/v21_system/layer_04_risk_management/contagion_risk_validator.py`

**Key Features**:
- ✅ Validator interface for Risk Manager
- ✅ Automatic position sizing adjustment based on stress level
- ✅ Risk multipliers: GREEN=1.0, YELLOW=0.7, RED=0.3
- ✅ Mock data provider for testing
- ✅ Integration helpers for Risk Manager

**Classes**:
- `ContagionRiskValidator`: Validator for Risk Manager
- `ContagionRiskGuard`: High-level interface for contagion monitoring
- `ContagionRiskConfig`: Configuration dataclass
- `MockDataProvider`: Testing data provider

**Integration Flow**:
```
Risk Manager → ContagionRiskValidator → GlobalContagionDetector → SRI → Risk Multiplier
```

---

### 3. Comprehensive Test Suite: `test_contagion_detector.py`
**Location**: `tests_v21/test_contagion_detector.py`

**Test Coverage** (24 tests, 100% passing):
- ✅ Correlation calculation accuracy (4 tests)
- ✅ Volatility calculation accuracy (3 tests)
- ✅ SRI component scoring logic (4 tests)
- ✅ CII integration weighting (2 tests)
- ✅ Dominant source detection (1 test)
- ✅ PIT compliance validation (2 tests)
- ✅ Risk narrative generation (2 tests)
- ✅ Edge cases (3 tests)
- ✅ Integration scenarios (2 tests: 2008 crisis, normal market)
- ✅ Convenience functions (1 test)

**Test Results**:
```
======================== 24 passed in 0.44s =========================
```

---

## 📊 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer 08: Situational Awareness           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐         ┌──────────────────┐         │
│  │  CII Module      │────────▶│ Contagion        │         │
│  │  (Country Risk)  │         │ Detector         │         │
│  └──────────────────┘         └──────────────────┘         │
│                                        │                     │
│                                        │ SRI + Signal        │
│                                        ▼                     │
└────────────────────────────────────────┼─────────────────────┘
                                         │
┌────────────────────────────────────────┼─────────────────────┐
│                    Layer 04: Risk Management                 │
├────────────────────────────────────────┼─────────────────────┤
│                                        ▼                     │
│  ┌──────────────────┐         ┌──────────────────┐         │
│  │  Risk Manager    │◀────────│ Contagion Risk   │         │
│  │                  │         │ Validator        │         │
│  └──────────────────┘         └──────────────────┘         │
│           │                                                  │
│           │ Adjusted Weights                                │
│           ▼                                                  │
│  ┌──────────────────┐                                       │
│  │  Portfolio       │                                       │
│  │  (Risk-Adjusted) │                                       │
│  └──────────────────┘                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 Usage Examples

### Basic Usage (Layer 08)
```python
from src.v21_system.layer_08_situational_awareness.contagion_detector import (
    GlobalContagionDetector,
    GlobalIndexData,
    get_market_stress_signal
)

# Create detector
detector = GlobalContagionDetector(
    lookback_days=60,
    correlation_window=30,
    volatility_window=20
)

# Prepare data
vn_returns = get_vn_index_returns(60)  # Your data source
global_indices = [
    GlobalIndexData('SPX', 'US', now, 5200.0, spx_returns),
    GlobalIndexData('HSI', 'HK', now, 18500.0, hsi_returns),
    GlobalIndexData('SSE', 'CN', now, 3100.0, sse_returns)
]
cii_scores = {'US': 28.0, 'HK': 42.0, 'CN': 35.0}

# Detect contagion
report = detector.detect_contagion(vn_returns, global_indices, cii_scores)

print(f"Stress Level: {report.sri.level.value}")
print(f"SRI Score: {report.sri.score:.1f}/100")
print(f"Narrative: {report.risk_narrative}")
```

### Risk Manager Integration (Layer 04)
```python
from V21_QUANT.src.v21_system.layer_04_risk_management.contagion_risk_validator import (
    ContagionRiskGuard,
    apply_contagion_risk_adjustment
)

# Create guard with data provider
guard = ContagionRiskGuard(data_provider)

# Check contagion risk
signal, multiplier, narrative = guard.check_contagion_risk()

# Apply to portfolio
if signal == MarketStressLevel.RED:
    # Reduce positions by 70%
    adjusted_weights = apply_contagion_risk_adjustment(
        original_weights,
        multiplier  # 0.3
    )
```

### Integration in Risk Manager
```python
# In risk_manager.py __init__:
from .contagion_risk_validator import create_contagion_validator

self._contagion_validator = create_contagion_validator(
    enabled=config.enable_contagion_check,
    yellow_multiplier=0.7,
    red_multiplier=0.3
)

# In _validate_portfolio_with_tiers:
if self._contagion_validator.config.enabled:
    is_safe, multiplier, report = self._contagion_validator.validate(
        vn_returns, global_data, cii_scores
    )
    
    if not is_safe:
        if multiplier < trim_factor:
            trim_factor = multiplier
        
        if report.sri.level == MarketStressLevel.RED:
            level = RiskLevel.RED
            violations.append(f"CONTAGION RISK: {report.risk_narrative}")
```

---

## 📁 Files Created/Modified

### Created:
1. `src/v21_system/layer_08_situational_awareness/contagion_detector.py` (603 lines)
2. `V21_QUANT/src/v21_system/layer_04_risk_management/contagion_risk_validator.py` (380 lines)
3. `tests_v21/test_contagion_detector.py` (604 lines)

### Total Lines of Code: 1,587 lines

---

## ✅ Verification

### Test Results
```bash
$ python -m pytest tests_v21/test_contagion_detector.py -v
======================== 24 passed in 0.44s =========================
```

### Demo Output
```
Market Stress Signal: YELLOW
Spreading Risk Index (SRI): 45.0/100

Component Breakdown:
  Correlation: 20.0/40
  Volatility:  25.0/30
  CII Weight:  0.0/30

Dominant Source: SSE
Risk Narrative: Elevated contagion risk (SRI: 45.0/100). 
                Primary risk source: SSE. 
                Key factors: strong correlation, elevated volatility.
```

---

## 🎓 Key Design Principles

1. **Institutional Grade**:
   - Vectorized operations (NumPy/Pandas)
   - Point-in-time (PIT) safe
   - No look-ahead bias
   - Clear data lineage
   - Auditable calculations

2. **Modular Architecture**:
   - Clean separation: Layer 08 (detection) ↔ Layer 04 (risk management)
   - Reusable components
   - Easy to test and maintain

3. **Production Ready**:
   - Comprehensive error handling
   - Edge case coverage
   - Mock data provider for testing
   - Clear documentation and examples

4. **Risk Management Integration**:
   - Automatic position sizing adjustment
   - Three-tier stress levels (GREEN/YELLOW/RED)
   - Risk multipliers configurable
   - Logging and audit trail support

---

## 🚀 Next Steps (Optional Enhancements)

1. **Data Integration**:
   - Connect to real data providers (vnstock, Yahoo Finance, Bloomberg)
   - Implement caching for CII scores
   - Add data quality checks

2. **Advanced Features**:
   - Multi-timeframe analysis (daily, weekly, monthly)
   - Regime detection (crisis vs normal)
   - Tail risk metrics (extreme correlation events)
   - Historical backtesting framework

3. **Monitoring & Alerts**:
   - Real-time monitoring dashboard
   - Email/SMS alerts for RED signals
   - Historical SRI tracking and visualization

4. **Performance Optimization**:
   - Parallel processing for multiple indices
   - Incremental updates (avoid full recalculation)
   - GPU acceleration for large-scale analysis

---

## 📝 Notes

- All timestamps use explicit datetime objects for PIT compliance
- CII scores default to 20.0 (low risk) if not provided
- Correlation and volatility windows are configurable
- Risk multipliers can be adjusted per deployment environment
- Mock data provider included for testing without external dependencies

---

**Implementation completed successfully. All requirements met.**
