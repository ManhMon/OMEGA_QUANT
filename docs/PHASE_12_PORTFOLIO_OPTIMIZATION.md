# Phase 12: Portfolio Optimization - OMEGA_QUANT
**Version**: 1.0  
**Status**: PLANNING  
**Last Updated**: 2026-05-11 23:26 GMT+7

## Objective
Tối ưu portfolio cho **aggressive individual scale** (NAV 1-5 tỷ VND) với:
- **Target Return**: > 35% annual
- **Max Drawdown**: < 10%
- **Sharpe Ratio**: > 2.0
- **Beta**: 0.5-0.8 (lower risk)

## Deliverables

### 1. Mean-Variance Optimizer (Aggressive)
**Objective Function**:
```
maximize: alpha_score - lambda * risk - kappa * turnover_cost
subject to:
  - sum(weights) <= 1.0 (max 100% equity)
  - weights[i] <= 0.15 (max 15% per stock - STRICT)
  - weights[i] >= 0.0 (long-only)
  - sum(weights * adv_pct) <= 0.30 (liquidity constraint)
  - num_stocks >= 15 (diversification)
  - num_stocks <= 20 (manageable for individual)
  - portfolio_beta <= 0.8 (DD protection)
  - portfolio_beta >= 0.5 (avoid too defensive)
```

**Risk Model**:
- Covariance matrix (60-day rolling)
- Sector exposure limits (max 25% per sector)
- Beta constraint (portfolio beta 0.5-0.8)
- Volatility target: 15% annual

### 2. Transaction Cost Model
**Components**:
- Slippage: 5 bps (buy) + 5 bps (sell) = 10 bps round-trip
- Commission: 0.15% (buy) + 0.15% (sell) = 0.30% round-trip
- Market impact: sqrt(trade_size / ADV) * 8 bps

**Turnover Penalty**:
```
cost = turnover * (slippage + commission + market_impact)
```

### 3. Rebalancing Logic (Daily)
**Frequency**: Daily (after market close)

**Triggers**:
- Scheduled: Every day at 16:00
- Event-driven: Circuit breaker, limit-lock, news

**Thresholds**:
- Min trade size: 100 shares (board lot)
- Min weight change: 3% (avoid tiny trades)
- Max turnover: 150% per day (active management)

## Acceptance Criteria
- [ ] Optimizer respects all constraints (tested 1000+ scenarios)
- [ ] Transaction costs reduce net returns by < 2% annually
- [ ] Turnover 100-150% per month (backtested 2015-2026)
- [ ] Portfolio beta stays 0.5-0.8 (tested daily)
- [ ] Backtest shows 35%+ annual return with <10% max DD

## Estimated Effort
- OpenCode (L2): 30 hours
- Codex (L3): 15 hours audit
- Total: 45 hours

## Dependencies
- ✅ Phase 11 Alpha Discovery (APPROVED)
- ✅ Full market data (2015-2026)
- ⏳ vnstock integration (in progress)

## Next Steps
1. Wait for data loader completion
2. Load `market_2015_2026.parquet`
3. Implement Phase 12 components
4. Run backtest with aggressive targets
5. L3 audit (PIT safety, IC, DD)
