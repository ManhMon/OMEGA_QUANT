# Phase35 Performance Enhancement Research Plan

## Mục tiêu
Nâng cao hiệu suất Phase35 Walk-Forward Backtest theo 3 hướng độc lập, tuân thủ SOD (L2 impl → L3 audit → gate lock → push).

## Baseline (V5 - current)
- Portfolio IC: +0.0034
- Sharpe: 0.5792
- MaxDD: -8.83%

---

## P4: Feature Engineering từ OHLCV

### Hypothesis
Thêm derived features (log returns, volatility ratios, volume-weighted prices) sẽ cung cấp thêm signal cho GP evolution tìm pattern tốt hơn.

### Implementation Plan
1. **New Features** (trong `_evolve_inline_signal`):
   - `log_ret_1`: log return 1 ngày
   - `log_ret_5`: log return 5 ngày  
   - `vol_ratio`: volume / rolling_mean(volume, 20)
   - `vwap_deviation`: (close - vwap) / vwap
   - `high_low_range`: (high - low) / close
   - `close_open_gap`: (close - open) / open

2. **PIT Safety**:
   - Tất cả features phải T-1 lag per ticker
   - Rolling windows chỉ dùng historical data

3. **Success Criteria**:
   - Portfolio IC > +0.0040 (+18% improvement)
   - MaxDD < -10%

### Risk
- Feature explosion có thể làm GP overfit
- Mitigation: giữ max_depth=3, chỉ thêm 6 features

---

## P5: Multi-horizon Blending

### Hypothesis
Blend signals từ nhiều forward horizons (T+1, T+3, T+5) sẽ capture được cả short-term momentum và medium-term trend.

### Implementation Plan
1. **Multi-horizon GP Evolution**:
   - Chạy GP evolution 3 lần với fwd_ret_1, fwd_ret_3, fwd_ret_5
   - Mỗi horizon tạo 1 ensemble signal (3 trees)

2. **Blending Strategy**:
   - Equal weight: (signal_1 + signal_3 + signal_5) / 3
   - Hoặc IC-weighted dựa trên train IC của mỗi horizon

3. **PIT Safety**:
   - Mỗi GP train trên correct horizon target
   - No cross-contamination between horizons

4. **Success Criteria**:
   - Sharpe > 0.7 (+21% improvement)
   - Portfolio IC stable across horizons

### Risk
- 3x computation time
- Mitigation: reduce GP pop_size từ 150 → 100 cho mỗi horizon

---

## P6: Risk-adjusted Blending

### Hypothesis
Điều chỉnh blend weight dựa trên realized volatility của evolved signal vs handcrafted signal. Khi evolved signal có volatility cao hơn → giảm weight để kiểm soát risk.

### Implementation Plan
1. **Volatility Measurement**:
   - `vol_evo`: std(evolved_signal) over rolling 20 days
   - `vol_hand`: std(handcrafted_signal) over rolling 20 days
   - `vol_ratio`: vol_evo / vol_hand

2. **Dynamic Weight Adjustment**:
   ```python
   if vol_ratio > 1.5:
       w_evo *= 0.5  # reduce evolved weight when too volatile
   elif vol_ratio < 0.5:
       w_evo *= 1.5  # increase evolved weight when stable
   w_evo = clip(w_evo, floor, ceiling)
   ```

3. **PIT Safety**:
   - Volatility tính trên historical signal values (không dùng future data)
   - Rolling window only backward-looking

4. **Success Criteria**:
   - MaxDD < -7% (-21% improvement)
   - Sharpe cải thiện hoặc giữ nguyên

### Risk
- Volatility lag có thể miss regime changes
- Mitigation: dùng EMA(10) thay vì rolling std

---

## Execution Order

1. **P4 → P5 → P6** (tuần tự, không parallel)
2. Mỗi phase: L2 implement → test → L3 audit → gate lock → push
3. Stop nếu bất kỳ phase nào gây regression > 20% trên Sharpe hoặc MaxDD

## Success Metrics
- Final Portfolio IC > +0.0050 (+47% so với V5)
- Final Sharpe > 0.75 (+29% so với V5)
- Final MaxDD < -8% (giữ hoặc cải thiện)
