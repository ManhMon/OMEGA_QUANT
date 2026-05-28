# KẾ HOẠCH CÂN CHỈNH HỆ THỐNG OMEGA_QUANT

**Ngày**: 2026-05-28  
**Phiên bản**: 1.0  
**Tác giả**: Ly (L1 Orchestrator)  
**Status**: PENDING IMPLEMENTATION

---

## 1. TÓM TẮT ĐÁNH GIÁ

| Backtest | Sharpe | Annual Return | MaxDD | Verdict |
|:---------|:-------|:-------------|:------|:--------|
| E2E Full (U20, 2020-2026) | 1.36 | 3.28% | -5.66% | Acceptable |
| Execution-Aware (U50, 2015-2026) | -1.82 | -7.92% | -4.45% | FAIL |

**Kết luận**: Hệ thống engineering đạt chuẩn institutional. Bottleneck là alpha quality + data utilization.

---

## 2. DANH SÁCH VẤN ĐỀ

### P1 - CRITICAL

| # | Vấn đề | Impact |
|:--|:-------|:-------|
| 1 | Thiếu Validation Set | Overfitting risk - ML Gate không có OOS validation |
| 2 | Thiếu Embargo Gap (10 days) | Label leakage từ fwd_ret_5 |
| 3 | Microstructure alphas Sharpe âm | U50 strategy không profitable |
| 4 | Chưa dùng full data 2015-2020 | 5 năm data bị lãng phí |

### P2 - IMPORTANT

| # | Vấn đề | Impact |
|:--|:-------|:-------|
| 5 | Annual return chỉ 3.28% net | Dưới risk-free rate |
| 6 | Single split thay vì walk-forward | Không robust across regimes |
| 7 | vnstock_ingest thiếu validation/retry | Không production-safe |
| 8 | Benchmark = equal-weight (không phải VN-Index) | IR vô nghĩa |

### P3 - NICE TO HAVE

| # | Vấn đề | Impact |
|:--|:-------|:-------|
| 9 | Worker thiếu heartbeat | Chỉ cần khi multi-process |
| 10 | Task Machine thiếu RLock | Chỉ cần khi concurrent |

---

## 3. TẠI SAO PHẢI DÙNG DATA 2015-2020?

### Hiện trạng
- Data warehouse: **2015-01-05 → 2026-05-14** (11.4 năm, 3.4M rows, 1534 tickers)
- Backtest chỉ dùng: **2020-01-01 → 2026-05-14** (6.4 năm)
- **5 năm data 2015-2020 bị bỏ phí hoàn toàn**

### Lợi ích khi dùng full 2015-2026

| Lợi ích | Chi tiết |
|:--------|:---------|
| Train set lớn hơn | 6.8 năm thay vì 4.5 năm → model robust hơn |
| Nhiều regime hơn | Bear 2018 (-35%), COVID 2020, Bear 2022 (-40%) |
| OOS thực sự | Train cũ, test mới → realistic performance |
| Alpha stability | Kiểm tra alpha qua nhiều market cycles |
| Statistical significance | Nhiều data points → IC estimates chính xác |

### VN Market Regime Coverage (Full Data)

```
2015-2017: Recovery + Bull    (VN-Index 500 → 1000)
2018:      Bear Market        (VN-Index 1000 → 650, -35%)
2019:      Sideways/Recovery
2020:      COVID Crash + V-Recovery
2021:      Bull Market        (VN-Index → 1500)
2022:      Bear Market        (VN-Index 1500 → 900, -40%)
2023-2024: Recovery
2025-2026: Current
```

**Kết luận**: Train trên 2015-2022 bao phủ 2 bear markets + 2 bull markets → alpha phải survive cả 2 chiều mới được dùng.

---

## 4. KẾ HOẠCH TRIỂN KHAI

### PHASE A: Fix Train/Val/Test Split (1 ngày)

**Config mới:**
```python
CONFIG = {
    "start_date": "2015-01-05",   # Full data
    "end_date": "2026-05-14",
    "train_ratio": 0.60,          # 2015-01 → 2021-10 (~6.8 năm)
    "val_ratio": 0.15,            # 2021-10 → 2023-06 (~1.7 năm)
    "embargo_days": 10,           # > fwd_ret_5, tránh label leakage
    # test = remaining 25%        # 2023-06 → 2026-05 (~2.9 năm)
}
```

**Deliverables:**
1. Update `backtest_e2e_full.py` với train/val/test/embargo
2. Validation step: tune IC threshold, verify alpha stability across regimes
3. Embargo gap: skip 10 trading days giữa val và test
4. Re-run backtest với full 2015-2026 data
5. L3 audit kết quả mới

### PHASE B: Alpha Research & Expansion (3-5 ngày)

**Mục tiêu**: Nâng Sharpe từ 1.36 → 2.0+

**Alphas mới:**
| # | Alpha | Rationale |
|:--|:------|:----------|
| 1 | Macro Regime | VN-Index regime detection → position sizing |
| 2 | Sector Rotation | Relative strength across GICS sectors |
| 3 | Liquidity Premium | Amihud illiquidity → small-cap premium |
| 4 | Earnings Momentum | Post-earnings drift (quarterly reports) |
| 5 | Foreign Flow | Net foreign buy/sell → institutional signal |
| 6 | Order Flow Imbalance | Block trades, net buy pressure |

**Deliverables:**
1. Implement 3-5 new alphas
2. IC analysis trên full 2015-2026
3. Walk-forward validation
4. L3 audit

### PHASE C: Execution Hardening (2 ngày)

**Tasks:**
1. Wire `VNTransactionCostModel` vào E2E backtest (limit-lock, T+2.5)
2. Actual board-lot rounding (shares = weight * capital / price, round to 100)
3. Expanding window walk-forward thay vì single split
4. VN-Index as benchmark
5. vnstock_ingest: validation + retry + rate limiting

### PHASE D: Live Integration (2 ngày)

**Tasks:**
1. Wire real vnstock3 API (remove stub)
2. Windows Task Scheduler cho daily oracle
3. Telegram notification
4. Error alerting + data quality checks

---

## 5. TIMELINE

```
Week 1 (28/05 - 01/06):
  Day 1: Phase A - Fix split + re-run backtest
  Day 2-4: Phase B - Alpha research + implementation

Week 2 (02/06 - 08/06):
  Day 5-6: Phase B - Alpha validation + L3 audit
  Day 7-8: Phase C - Execution hardening
  Day 9-10: Phase D - Live integration

Target: Sharpe 2.0+, full live oracle by 08/06/2026
```

---

## 6. METRICS MỤC TIÊU

| Metric | Hiện tại | Target | Gap |
|:-------|:---------|:-------|:----|
| Sharpe | 1.36 | 2.0+ | +0.64 |
| Annual Return | 3.28% | 8-12% | +5-9% |
| Max Drawdown | -5.66% | < -10% | OK |
| Alpha Count | 3 passed | 6-8 passed | +3-5 |
| Data Range | 2020-2026 | 2015-2026 | +5 năm |
| Split | 70/0/30 | 60/15/25 | +validation |
| Embargo | None | 10 days | +10 days |
| Benchmark | Equal-weight | VN-Index | Fix |

---

*Document generated by Ly (L1 Orchestrator) - OMEGA_QUANT Protocol v2.4*
