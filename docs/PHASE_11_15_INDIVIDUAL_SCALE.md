# OMEGA_QUANT PHASE 11-15 PLAN
**Target**: Individual Scale (NAV 1-5 tỷ VND)
**Version**: 1.0
**Date**: 2026-05-11

---

## EXECUTIVE SUMMARY

**Scope**: Phase 11-15 tối ưu cho **Individual Traders** với vốn 1-5 tỷ VND.

**Key Constraints**:
- **Liquidity**: Max 40% ADV per stock (tránh market impact)
- **Concentration**: Max 25% per stock (risk management)
- **Universe**: Top 50-100 stocks thanh khoản cao (HOSE + HNX)
- **Frequency**: Daily rebalance (không HFT)
- **Costs**: Slippage 5-10 bps, commission 1-2 bps

**Goals**:
- **Annual Return: > 35%** (aggressive target)
- **Sharpe > 2.0** (high risk-adjusted return)
- **Max Drawdown < 10%** (strict risk control)
- **Win Rate > 60%** (high accuracy)

---

## PHASE 11: ADVANCED ALPHA DISCOVERY (Week 11-12)

### Objective
Phát triển high-conviction alphas với strict drawdown control cho target 35%+ annual return.

### Key Strategy Changes
**To achieve 35%+ return with <10% DD:**
1. **Higher alpha quality**: IC > 0.15 (vs 0.10 baseline)
2. **Tighter risk control**: Beta 0.5-0.8 (vs 0.8-1.2)
3. **Active rebalancing**: Daily (vs weekly)
4. **Smaller positions**: 15% max (vs 25%)
5. **Faster exits**: Stop-loss at -5% (vs -10%)

### Deliverables

#### 1. High-Conviction Alpha Engine
**Horizons** (Optimized for 35%+ return):
- **T+1**: Intraday momentum + mean reversion (High frequency, low holding)
- **T+3**: Short-term reversal (Capture oversold/overbought)
- **T+5**: Trend following (Ride momentum waves)

**Alpha Scoring** (Composite):
```python
alpha_score = (
    0.4 * momentum_score +      # 40% momentum
    0.3 * reversal_score +      # 30% mean reversion
    0.2 * trend_score +         # 20% trend following
    0.1 * sentiment_score       # 10% sentiment (if available)
)

# Only trade if alpha_score > 0.7 (high conviction)
if alpha_score > 0.7:
    position_size = kelly_fraction * nav
else:
    position_size = 0  # Skip low-conviction trades
```

**Features** (Aggressive):
- Technical: RSI (14), MACD (12,26,9), Bollinger Bands (20,2)
- Volume: Volume spike (>2x avg), accumulation/distribution
- Microstructure: Bid-ask spread, order imbalance, large trades
- Sentiment: News sentiment, social media (if available)
- Volatility: ATR, historical vol, implied vol

#### 2. Regime Detection (Enhanced)
**Regimes** (4-state machine):
- **Bull Trend**: VN-Index > 50-day MA, vol < 2%
  - Action: Increase momentum/trend alphas (80% weight)
  - Position size: 100% of limit
  - Stop-loss: -5%
  
- **Bear Trend**: VN-Index < 50-day MA, vol > 2%
  - Action: Increase reversal alphas (80% weight)
  - Position size: 50% of limit (defensive)
  - Stop-loss: -3% (tighter)
  
- **Sideways**: VN-Index ±2% of 50-day MA, vol 1-2%
  - Action: Mean reversion only (100% weight)
  - Position size: 75% of limit
  - Stop-loss: -4%
  
- **High Volatility**: 60-day vol > 3% OR VN-Index gap > 2%
  - Action: Reduce exposure (30% of limit)
  - Position size: 30% of limit
  - Stop-loss: -2% (emergency)

**Implementation**:
```python
def detect_regime(vn_index_prices, volatility):
    ma50 = vn_index_prices[-50:].mean()
    vol60 = volatility[-60:].std()
    
    if vol60 > 0.03:
        return "HIGH_VOL"
    elif vn_index_prices[-1] > ma50 * 1.02 and vol60 < 0.02:
        return "BULL"
    elif vn_index_prices[-1] < ma50 * 0.98 and vol60 > 0.02:
        return "BEAR"
    else:
        return "SIDEWAYS"
```

#### 3. Liquidity Filter (Stricter)
**Rules** (For 35%+ return):
- Only trade stocks with ADV > 10B VND (vs 5B)
- Max position size = min(15% NAV, 30% ADV) (vs 25%, 40%)
- Skip stocks with bid-ask spread > 1% (high friction)
- Avoid stocks with foreign room < 5% (liquidity risk)
- Skip limit-up/limit-down stocks

**Implementation**:
```python
def filter_universe_aggressive(df_universe, nav, max_adv_pct=0.30):
    # Filter by ADV (stricter)
    df = df_universe[df_universe['adv_vnd'] > 10_000_000_000]
    
    # Filter by spread
    df = df[df['bid_ask_spread_pct'] < 0.01]
    
    # Filter by foreign room
    df = df[df['foreign_room_pct'] > 0.05]
    
    # Calculate max position size (stricter)
    df['max_position_vnd'] = df['adv_vnd'] * max_adv_pct
    df['max_weight'] = df['max_position_vnd'] / nav
    df['max_weight'] = df['max_weight'].clip(upper=0.15)
    
    return df
```

### Acceptance Criteria
- [ ] Multi-horizon alphas generate IC > 0.15 on walk-forward test (vs 0.10)
- [ ] Regime detection accuracy > 75% (backtested 2015-2026)
- [ ] Liquidity filter reduces market impact to < 3 bps (vs 5 bps)
- [ ] All alphas pass PIT safety audit (no T+0 leakage)
- [ ] Backtest shows 35%+ annual return with <10% max DD

### Estimated Effort
- OpenCode (L2): 40 hours (vs 30h - more complex alpha logic)
- Codex (L3): 15 hours audit (vs 10h - stricter validation)
- Total: 55 hours (vs 40h)

---

## PHASE 12: PORTFOLIO OPTIMIZATION (Week 12-13)

### Objective
Tối ưu portfolio cho **aggressive individual scale** với strict DD control.

### Key Strategy Changes
**To achieve 35%+ return with <10% DD:**
1. **Lower beta**: Portfolio beta 0.5-0.8 (vs 0.8-1.2)
2. **Tighter constraints**: Max 15% per stock (vs 25%)
3. **Active turnover**: 100-150% per month (vs <100%)
4. **Faster exits**: Stop-loss at -5% (vs -10%)

### Deliverables

#### 1. Mean-Variance Optimizer (Aggressive)
**Objective Function**:
```
maximize: alpha_score - lambda * risk - kappa * turnover_cost
subject to:
  - sum(weights) <= 1.0 (max 100% equity)
  - weights[i] <= 0.15 (max 15% per stock - STRICT)
  - weights[i] >= 0.0 (long-only)
  - sum(weights * adv_pct) <= 0.30 (liquidity constraint - STRICTER)
  - num_stocks >= 15 (diversification)
  - num_stocks <= 20 (manageable for individual)
  - portfolio_beta <= 0.8 (NEW - DD protection)
  - portfolio_beta >= 0.5 (NEW - avoid too defensive)
```

**Risk Model** (Aggressive):
- Covariance matrix (60-day rolling)
- Sector exposure limits (max 25% per sector - vs 40%)
- Beta constraint (portfolio beta 0.5-0.8 - NEW)
- Volatility target: 15% annual (NEW)

#### 2. Transaction Cost Model (Optimized)
**Components**:
- Slippage: 5 bps (buy) + 5 bps (sell) = 10 bps round-trip
- Commission: 0.15% (buy) + 0.15% (sell) = 0.30% round-trip
- Market impact: sqrt(trade_size / ADV) * 8 bps (lower for liquid stocks)

**Turnover Penalty** (Aggressive):
```
cost = turnover * (slippage + commission + market_impact)
```

**Optimization**:
```
maximize: alpha_score - lambda * risk - kappa * turnover_cost
```

#### 3. Rebalancing Logic (Daily)
**Frequency**: Daily (after market close)

**Triggers**:
- Scheduled: Every day at 16:00
- Event-driven: Circuit breaker, limit-lock, news

**Thresholds**:
- Min trade size: 100 shares (board lot)
- Min weight change: 3% (vs 2% - avoid tiny trades)
- Max turnover: 150% per day (active management)
- Rebalance if alpha_score change > 0.1 (NEW)

### Acceptance Criteria
- [ ] Optimizer respects all constraints (tested 1000+ scenarios)
- [ ] Transaction costs reduce net returns by < 2% annually
- [ ] Turnover 100-150% per month (backtested 2015-2026)
- [ ] Portfolio beta stays 0.5-0.8 (tested daily)
- [ ] Backtest shows 35%+ annual return with <10% max DD

### Estimated Effort
- OpenCode (L2): 30 hours (vs 25h - more complex constraints)
- Codex (L3): 15 hours audit (vs 10h - stricter validation)
- Total: 45 hours (vs 35h)

---

## PHASE 13: RISK MANAGEMENT (Week 13-14)

### Objective
Bảo vệ vốn với **strict risk controls** cho target <10% max DD.

### Key Strategy Changes
**To achieve <10% DD:**
1. **Lower beta target**: 0.5-0.8
2. **Tighter stop-loss**: -5% stock, -3% portfolio
3. **Hard drawdown cap**: -10% life-to-date
4. **Liquidity guard**: Exit if volume drops > 50%

### Deliverables

#### 1. Advanced Position Sizing
**Rules**:
- Max 15% per stock (vs 25%)
- Max 25% per sector (vs 40%)
- Max 100% equity (long-only)
- Min 15 stocks (vs 10)

**Volatility-Adjusted Sizing**:
```python
def calculate_position_size_aggressive(alpha_score, volatility, nav):
    # Adjust target volatility for <10% DD
    target_vol = 0.15 / np.sqrt(252)  # 15% annual vol target
    
    # Sizing = target_vol / stock_vol
    vol_scaling = target_vol / volatility
    
    # Kelly fraction (conservative scaling)
    kelly_fraction = (alpha_score / (volatility ** 2)) * 0.3  # 1/3 Kelly
    
    # Final weight = min(vol_scaling, kelly_fraction, 0.15)
    weight = min(vol_scaling, kelly_fraction, 0.15)
    
    return weight * nav
```

#### 2. Strict Stop-Loss & Take-Profit
**Stop-Loss** (STRICT):
- Individual stock: -5% from entry (vs -10%)
- Portfolio: -3% daily drawdown (vs -5%)
- Hard stop: -10% from peak (NEW - DD protection)

**Take-Profit** (Trailing):
- Individual stock: +15% from entry (trigger trailing stop)
- Trailing stop: 2.5% from peak (NEW)

**Implementation**:
```python
def check_stop_loss_strict(current_price, entry_price, peak_price):
    # Fixed stop-loss
    loss = (current_price - entry_price) / entry_price
    if loss < -0.05:
        return True, "FIXED_STOP"
        
    # Trailing stop-loss
    trailing_loss = (current_price - peak_price) / peak_price
    if current_price > entry_price * 1.15 and trailing_loss < -0.025:
        return True, "TRAILING_STOP"
        
    return False, None
```

#### 3. Advanced Circuit Breaker
**Triggers**:
- VN-Index drops > 2% intraday (vs 3%)
- Portfolio drawdown > 3% daily (vs 5%)
- Individual stock limit-down
- Correlation spike > 0.8 among portfolio assets (NEW)

**Actions**:
- Halt all trading
- Reduce exposure to 0-30% (emergency exit)
- Real-time alert to user

### Acceptance Criteria
- [ ] Position sizing maintains portfolio beta 0.5-0.8 (backtested)
- [ ] Stop-loss limits max DD to < 10% on stress tests
- [ ] Circuit breaker triggers within 30s
- [ ] Stress tests show <10% DD in all historical crashes (2015, 2018, 2020, 2022)

### Estimated Effort
- OpenCode (L2): 30 hours (vs 20h - more complex sizing/stops)
- Codex (L3): 15 hours audit (vs 10h - critical risk audit)
- Total: 45 hours (vs 30h)

---

## PHASE 14: EXECUTION & MONITORING (Week 14-15)

### Objective
Thực thi orders và monitor real-time với high accuracy.

### Deliverables

#### 1. Precision Execution (VWAP/TWAP)
**Strategy**: Adaptive VWAP

**Logic**:
- Split large orders (>5% ADV) into 10+ chunks
- Use mid-point pricing for small orders
- Real-time slippage monitoring

**Broker Integration**:
- Full API integration (SSI/VNDirect)
- Auto-retry on rejection
- Partial fill handling

#### 2. Risk Dashboard (Enhanced)
**Real-Time Metrics**:
- Rolling 60-day Sharpe, Sortino, Calmar
- Real-time Drawdown vs peak
- Component contribution to risk
- Alpha decay monitor

#### 3. Automatic Alerts
- Real-time Telegram/Push notifications
- Emergency kill-switch via Telegram

### Acceptance Criteria
- [ ] Execution slippage < 3 bps (avg)
- [ ] Dashboard displays all risk metrics accurately
- [ ] Kill-switch response time < 500ms

### Estimated Effort
- OpenCode (L2): 30 hours
- Codex (L3): 10 hours audit
- Total: 40 hours

---

## PHASE 15: VALIDATION & DEPLOYMENT (Week 15-16)

### Objective
Final validation for **aggressive target** deployment.

### Deliverables

#### 1. Stress Test (Historical Crashes)
- Verify max DD < 10% in 2015, 2018, 2020, 2022 periods.
- Tuning stop-loss/beta to ensure compliance.

#### 2. Monte Carlo Simulation
- 10,000 simulations to verify probability of >35% return and <10% DD.
- Target: Prob(DD < 10%) > 95%.

#### 3. Live Paper Trading (1 Month)
- Final check of system stability and execution accuracy.

### Acceptance Criteria
- [ ] Backtest (2015-2026) shows:
  - **Annual Return > 35%**
  - **Max Drawdown < 10%**
  - **Sharpe Ratio > 2.0**
- [ ] 0 PIT violations detected.

### Estimated Effort
- OpenCode (L2): 40 hours
- Codex (L3): 20 hours audit
- Total: 60 hours (vs 45h)

---

## TOTAL EFFORT ESTIMATE

| Phase | OpenCode (L2) | Codex (L3) | Total |
|:------|:--------------|:-----------|:------|
| Phase 11 | 30h | 10h | 40h |
| Phase 12 | 25h | 10h | 35h |
| Phase 13 | 20h | 10h | 30h |
| Phase 14 | 25h | 10h | 35h |
| Phase 15 | 30h | 15h | 45h |
| **TOTAL** | **130h** | **55h** | **185h** |

**Timeline**: 5 weeks (assuming 40h/week)

---

## SUCCESS CRITERIA (AGGRESSIVE NAV 1-5 TỶ)

### Performance
- **Annual Return: > 35%**
- **Sharpe Ratio: > 2.0**
- **Max Drawdown: < 10%**
- **Win Rate: > 60%**

### Risk
- Portfolio Beta: 0.5-0.8 (Lower beta for DD protection)
- Max Position: 15% (Strict concentration limit for DD protection)
- Max Sector: 30%
- Turnover: < 150%/month (Active management for alpha)

### Execution
- Slippage: < 10 bps
- Fill Rate: > 95%
- Uptime: > 99%

### Costs
- Total Costs: < 2% annually
- Commission: 0.30% round-trip
- Slippage: 10 bps round-trip

---

## NEXT STEPS

1. **Anh approve plan này** → Em bắt đầu Phase 11
2. **Data loader hoàn tất** (~30 phút nữa) → Em có 11 năm data để backtest
3. **Phase 11 implementation** → Multi-horizon alphas + regime detection
4. **Phase 11 audit** → Codex verify PIT safety
5. **Phase 12-15** → Portfolio optimization → Risk → Execution → Backtest

**ETA**: 5 tuần để hoàn tất Phase 11-15, sẵn sàng paper trading.

---

**Document Owner**: Ly (L1)
**Target User**: Individual Trader (NAV 1-5 tỷ VND)
**Last Updated**: 2026-05-11 22:05 GMT+7
