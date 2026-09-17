# Hướng Dẫn Chạy GP Evolution V3 - Step by Step

**Version**: Gate 6 Production (Phase 7a-d)  
**Date**: 2026-07-04

---

## 📋 Bước 1: Chuẩn Bị Môi Trường

### 1.1 Kiểm tra Data
```powershell
# Xác nhận data file tồn tại
Get-Item data\market_2015_now.parquet
```

### 1.2 Kiểm tra Dependencies
```powershell
# Python 3.10+
python --version

# Kiểm tra packages
python -c "import pandas, numpy, scipy, joblib; print('Dependencies OK')"
```

### 1.3 Verify Git Branch
```powershell
# Xác nhận đang ở branch đúng
git branch --show-current
# Expected: fix/cost-reduction-isolation (hoặc branch có Gate 6)

# Kiểm tra commit mới nhất
git log -1 --oneline
# Should show: 58f9235c feat(gp): Gate 6 production validation suite
```

---

## 🎯 Bước 2: Hiểu Parameters

### Core Parameters

| Parameter | Mục đích | Khuyến nghị |
|-----------|----------|-------------|
| `--rounds` | Số lần chạy độc lập (seeds khác nhau) | 3-10 |
| `--population-size` | Số individuals per generation | 30-100 |
| `--generations` | Số generations evolution | 10-30 |
| `--workers` | Parallel workers (CPU cores) | 2-8 |

### Advanced Parameters

```powershell
# Liquidity filtering
--min-avg-volume 500000  # Min 500K VND daily volume

# Backend selection
--backend threads        # Default (stable)
--backend loky          # Faster but experimental

# Random seed (reproducibility)
--seed 42               # Fixed seed for debugging
```

---

## 🚀 Bước 3: Chạy GP Evolution

### 3.1 Quick Test Run (15-30 phút)
```powershell
# Test nhanh để verify setup
python scripts/genetic_alpha_evolution_v3.py `
  --rounds 1 `
  --population-size 20 `
  --generations 3 `
  --workers 2
```

**Khi nào dùng**:
- ✅ Test sau khi pull code mới
- ✅ Verify data loading
- ✅ Debug parameters

### 3.2 Production Run (1-2 giờ)
```powershell
# Production-grade evolution
python scripts/genetic_alpha_evolution_v3.py `
  --rounds 5 `
  --population-size 50 `
  --generations 20 `
  --workers 4
```

**Khi nào dùng**:
- ✅ Generate alphas cho backtest
- ✅ Weekly/monthly alpha refresh
- ✅ Production pipeline

### 3.3 Aggressive Deep Search (4-8 giờ)
```powershell
# Deep evolution với large population
python scripts/genetic_alpha_evolution_v3.py `
  --rounds 10 `
  --population-size 100 `
  --generations 30 `
  --workers 8
```

**Khi nào dùng**:
- ✅ Quarterly alpha discovery
- ✅ Research projects
- ✅ Khi có nhiều CPU/time

---

## 📊 Bước 4: Đọc Kết Quả Output

### 4.1 Live Progress Monitor

```
INFO:omega.quant.evolution.genetic_engine:Gen 1: Fold_IR=0.5408, Fitness=0.4453
INFO:omega.quant.evolution.genetic_engine:  Progress: 1/3 (33%) elapsed=5.4s eta=10.7s
```

**Ý nghĩa**:
- `Fold_IR`: Information Ratio trên 3 chronological train folds
- `Fitness`: Combined fitness (IR - penalties)
- `eta`: Estimated time to completion

### 4.2 Gate 6 Production Validation Output

#### Phase 7a: Regime IC Breakdown
```
Gate 6 regime IC breakdown:
  COVID_2020: IC=None rows=0 rationale=COVID shock...
  Bear_2022: IC=0.0065 rows=24895 rationale=VN-Index drawdown...
  Recovery_2023: IC=0.0257 rows=24325 rationale=Post-bear recovery...
```

**Giải thích**:
- `IC`: Information Coefficient (daily cross-sectional Spearman)
- `rows`: Số observations trong regime đó
- `None`: Regime không có data (thường là early regimes trong train window)

**Red flags** 🚨:
- ❌ Bất kỳ regime IC < -0.01 → Alpha unstable across regimes

#### Phase 7b: Net-of-Cost Analysis
```
Gate 6 net-of-cost: gross_ic=0.0100, turnover=0.0230, avg_cost_bps=60.89, net_ic_estimate=0.0099
```

**Giải thích**:
- `gross_ic`: IC trước khi trừ cost
- `turnover`: Tỷ lệ position thay đổi mỗi ngày (0.0230 = 2.3%)
- `avg_cost_bps`: Average transaction cost (basis points)
- `net_ic_estimate`: IC sau khi estimate cost drag

**Red flags** 🚨:
- ❌ `turnover > 0.5` → Quá nhiều churn, cost sẽ ăn hết alpha
- ❌ `net_ic_estimate < 0` → Alpha không profitable sau cost

#### Phase 7c: VN Trading Calendar
```
Train/Val/OOS/Lockbox: 48223/38092/37974/38040 rows
```

**Giải thích**:
- Splits dựa trên VN trading days (exclude weekends + holidays từ `config/vn_holidays.json`)
- 5-trading-day embargo between splits

#### Phase 7d: Permutation Test
```
Gate 6 permutation: observed_ic=0.0100, p_value=0.000000, null_mean=0.000101, null_std=0.002966
```

**Giải thích**:
- `observed_ic`: IC thực tế của alpha
- `p_value`: Statistical significance (< 0.05 = significant)
- `null_mean/std`: Distribution của IC khi shuffle random

**Red flags** 🚨:
- ⚠️ `p_value > 0.05` → Alpha có thể là noise, không statistically significant

### 4.3 Final Ensemble Results

```
#1: Round1 TrainFoldIR=0.5288, ValIC_daily=0.0060, OOSIC_daily=0.0220, LockboxIC_daily=0.0021
     neg(log(oc_range))
```

**Giải thích**:
- `TrainFoldIR`: IR trên 3 train folds (higher = more stable)
- `ValIC_daily`: IC trên validation set (selection criterion)
- `OOSIC_daily`: IC trên out-of-sample test
- `LockboxIC_daily`: IC trên lockbox (final validation)
- Expression: GP tree formula

**Interpretation**:
- ✅ ValIC > 0 → Alpha có signal trên validation
- ✅ OOSIC ≈ ValIC → Alpha generalizes well
- ✅ LockboxIC > 0 → Alpha robust trên unseen data

---

## 🗂️ Bước 5: Kiểm Tra Output Files

### 5.1 Conformal Registry (SQLite)
```powershell
# Check registered alphas
sqlite3 .ly_state/session/conformal_registry.sqlite "SELECT COUNT(*) FROM models;"
```

**Chứa**:
- Evolved alpha expressions
- Metadata (IC, hit rate, complexity)
- Conformal prediction calibration

### 5.2 CSV Results Export
```powershell
# View summary results
Import-Csv data/stable/genetic_alpha_v3_results.csv | Format-Table
```

**Chứa**:
- Best alphas per round
- Train/Val/OOS/Lockbox metrics
- Gate 6 validation results

### 5.3 Session Artifacts
```powershell
# List all session outputs
Get-ChildItem .ly_state/session/ -Filter "*gp*" | Select-Object Name, Length, LastWriteTime
```

---

## 🔧 Bước 6: Troubleshooting

### Issue 1: "KeyError: Timestamp"
**Symptom**: Crash khi build split windows
```
KeyError: Timestamp('2023-01-20 00:00:00')
```

**Cause**: Calendar date không có trong data (market gap)

**Fix**: Claude Code recommendation - replace `dates.index()` với `searchsorted`
```python
# Current (fragile):
idx = dates.index(val_start)

# Better (robust):
idx = np.searchsorted(dates, val_start, side='left')
```

### Issue 2: "No module named 'omega'"
**Symptom**: Import error
```
ModuleNotFoundError: No module named 'omega'
```

**Fix**: Set PYTHONPATH
```powershell
$env:PYTHONPATH = "C:\Users\GHC\repos\OMEGA_QUANT\src"
python scripts/genetic_alpha_evolution_v3.py ...
```

### Issue 3: Low Performance / Slow
**Symptom**: <1 generation per minute

**Causes & Fixes**:
- 🔧 Increase `--workers` (match CPU cores)
- 🔧 Try `--backend loky` (faster but experimental)
- 🔧 Reduce `--population-size` or data size

### Issue 4: Out of Memory
**Symptom**: Process killed / MemoryError

**Fixes**:
- 🔧 Reduce `--population-size`
- 🔧 Reduce `--workers`
- 🔧 Filter data: increase `--min-avg-volume`

---

## 📈 Bước 7: Interpret & Use Results

### 7.1 Alpha Selection Criteria
Chọn alphas dựa trên:
1. ✅ `ValIC_daily > 0.005` (positive validation signal)
2. ✅ `OOSIC_daily > 0` (generalizes to OOS)
3. ✅ `LockboxIC_daily > -0.005` (không collapse trên lockbox)
4. ✅ Gate 6 permutation `p_value < 0.05` (statistically significant)
5. ✅ Gate 6 regime IC không có regime < -0.01 (stable across regimes)

### 7.2 Next Steps: Backtest
```powershell
# Load evolved alphas vào backtest
python scripts/run_phase35_backtest.py `
  --evolved-alphas .ly_state/session/conformal_registry.sqlite `
  --start-date 2020-01-01 `
  --end-date 2026-05-01
```

### 7.3 Production Deployment
1. ✅ Verify all Gate 6 checks passed
2. ✅ Run full backtest với transaction costs
3. ✅ Paper trading 1-2 weeks
4. ✅ Deploy to production portfolio

---

## 📚 Tài Liệu Tham Khảo

### Gate 6 Implementation Details
- **Plan**: `.ly_state/session/gate6_production_validation_plan_revised.md`
- **L2 Report**: `.ly_state/session/l2_role16_gp_gate6_20260704.md`
- **L3 Audit**: `.ly_state/session/audit_reports/role23_gp_gate6_20260704.md`

### SOD Protocol
- **AGENTS.md**: `.agents/AGENTS.md` (Lines 1-400)
- **Phase Gates**: `.ly_state/session/phase_gates.json`

### Code Reference
- **Main Script**: `scripts/genetic_alpha_evolution_v3.py`
- **Tests**: `tests/test_genetic_alpha_evolution_v3_gate6.py`

---

## ✅ Quick Checklist

Trước khi chạy production:
- [ ] Data file exists (`data/market_2015_now.parquet`)
- [ ] Git branch correct (có Gate 6: commit `58f9235c`)
- [ ] Dependencies installed
- [ ] Đã test với quick run (1 round, 20 pop, 3 gen)
- [ ] CPU/RAM đủ cho production run
- [ ] Có ít nhất 2 giờ runtime

Sau khi chạy xong:
- [ ] Check Gate 6 regime IC (không có regime < -0.01)
- [ ] Check Gate 6 permutation p-value (< 0.05)
- [ ] Check net-of-cost (turnover < 0.5, net_ic > 0)
- [ ] Verify output files created (`conformal_registry.sqlite`, CSV)
- [ ] Alphas registered (> 0 evolved models)

---

**Lưu ý quan trọng**: Gate 6 production validation là **advisory** (không hard-fail pipeline). Nhưng nếu có red flags (regime IC negative, p-value > 0.05, high turnover), cần investigate trước khi deploy production.

**Support**: Check logs tại `.system_generated/tasks/` nếu có issues.
