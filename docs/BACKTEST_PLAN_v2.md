# BACKTEST PLAN v2.0 — L2/L3 Consensus (Final)

**Date**: 2026-05-31
**Reviewed by**: L2 System Architect (Role 06) + L3 Code Reviewer (Role 21)
**Status**: APPROVED (Consensus)

---

## Đồng thuận L2 + L3

### 🔴 Critical Fixes (từ L3 — PIT Safety)

| Issue | Risk | Mitigation |
|-------|------|------------|
| GP fitness dùng test IC | **Leakage** — GP "thấy" OOS data qua selection | **3-way split**: Train (evolve) / Validation (promote) / Test (final OOS). GP chỉ thấy train IC. Promote dùng validation IC. Test hoàn toàn untouched. |
| Universe filter dùng ADV tĩnh | **Survivorship bias** | **Point-in-time universe**: Tại mỗi rebalance date, dùng trailing 60-day ADV tính đến ngày đó. Include delisted stocks đến ngày delist. |
| Không có purge gap | **Autocorrelation leakage** | **Purge 20 trading days** giữa train/validation/test boundaries. |
| Multiple testing (2000+ alphas) | **False discovery** | **Benjamini-Hochberg FDR** q=0.05 trước promotion. Report raw + adjusted p-values. |

---

### 📐 Tham số Final (L2 + L3 đồng thuận)

| Parameter | Original | Final | Lý do |
|-----------|----------|-------|-------|
| GP population | 100 | **150** | Diversity tốt hơn, +50MB RAM acceptable |
| GP generations | 20 | **25** | Marginal improvement, diminishing >30 |
| GP depth | 4 | **5** (parsimony coeff 0.001) | Depth 4 quá hạn chế; depth 6 bloat risk |
| IC threshold | 0.03 | **0.05** | 0.03 quá gần noise floor cho VN 100 symbols |
| Hit rate threshold | 52% | **53%** + profit factor ≥1.3 | Hit rate alone không đủ; cần profit factor |
| Turnover cap | 30%/month | **25%/month** | VN liquidity thinner than assumed |
| Walk-forward OOS | 6-month | **12-month OOS / 6-month step** | VN regime cycles dài hơn US |
| Purge gap | 0 | **20 trading days** | Decontamination buffer |
| Slippage | 3bps uniform | **5bps top-30 / 10bps rank 30-100** | 3bps optimistic cho HOSE |
| Max single-name | 10% | **5%** | Concentration risk in illiquid names |
| Fitness metric | Raw IC | **Cost-adjusted IC** (net after 0.25% round-trip) | Alphas phải survive after costs |

---

### 📊 Time Split (3-Way, Chronological)

```
|--- TRAIN (Evolve) ---|-- VALIDATION (Promote) --|--- TEST (Final OOS) ---|
|   2015-01 → 2022-06  |   2022-07 → 2024-06     |   2024-07 → 2026-05   |
|   ~7.5 years          |   ~2 years               |   ~2 years            |
|                       |                          |                       |
|   GP sees this only   |   Promote gate here      |   NEVER touched until |
|   for IC fitness      |   IC>0.05, hit>53%,      |   final report         |
|                       |   profit factor>1.3      |                       |
```

**Purge**: 20 trading days gap at each boundary.

---

### 🏗️ Architecture Flow (Revised)

```
Phase A: Data Pipeline
  └─ Load OHLCV → Sanitize (PIT) → Corp Action → PIT Universe (trailing 60d ADV)

Phase B: Alpha Evolution (TRAIN period only)
  └─ GP (150 pop × 25 gen × depth 5) → Cost-adjusted IC fitness
  └─ Orthogonality filter (corr < 0.7)
  └─ FDR correction (q=0.05)

Phase C: Promotion Gate (VALIDATION period)
  └─ IC > 0.05 on validation
  └─ Hit rate > 53%
  └─ Profit factor > 1.3
  └─ Max 10-15 active alphas

Phase D: Portfolio Construction
  └─ IC-weighted signal combination
  └─ Max single-name 5%
  └─ Board-lot rounding (100 shares)
  └─ Turnover cap 25%/month

Phase E: Parallel Backtest (TEST period — untouched)
  └─ 4 workers, symbol chunking
  └─ Costs: fee 0.15%, tax 0.1%, slippage 5-10bps
  └─ VN constraints: T+2.5, limit-lock, foreign room
  └─ Risk: max DD -15%, position limit 5%

Phase F: Walk-Forward Validation
  └─ 12-month OOS / 6-month step (rolling)
  └─ Metrics: Sharpe, Sortino, MaxDD, Calmar, Turnover
  └─ Decay monitoring (scheduler 1 cycle)
  └─ Report: equity curve + alpha attribution

Phase G: SOD Audit (L3 Codex)
  └─ Full audit of implementation
  └─ Gate lock with evidence
```

---

### ⚠️ Scalability (16GB RAM)

| Component | Est. RAM | Notes |
|-----------|----------|-------|
| 100 symbols × 10yr OHLCV | ~500MB | Panel format |
| GP evolution (150 pop) | ~200MB | Tree structures + signals |
| Backtest (4 workers) | ~2GB peak | 500MB/worker |
| Total peak | **~3GB** | Well within 16GB |

---

### ✅ Checklist trước Implementation

- [ ] Verify `data/market_2015_now.parquet` exists và có đủ data
- [ ] Implement 3-way split with purge gap
- [ ] Add cost-adjusted IC to GP fitness
- [ ] Add FDR correction post-evolution
- [ ] Implement PIT universe reconstruction
- [ ] Add profit factor gate
- [ ] Tiered slippage model (5/10 bps)
- [ ] Max single-name 5% constraint
- [ ] SOD audit after implementation

---

**Consensus**: L2 và L3 đồng thuận kế hoạch này sound sau khi apply fixes. Sẵn sàng implement.
