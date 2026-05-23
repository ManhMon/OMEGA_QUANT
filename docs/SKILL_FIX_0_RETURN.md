# SKILL: Fix 0% Backtest Return (/fix-0-return)

Sá» dá»¥ng khi Backtest tráº£ vá»  0.00% Return hoáº·c khÃ´ng cÃ³ giao dá»‹ch phÃ¡t sinh.

## 🔍 QUY TRÃŒNH DIAGNOSTIC (CHECKLIST)

### 1. Signal Integrity (Táº§ng TÃ­n hiá»‡u)
- Kiá»ƒm tra log XGBoost: CÃ³ bÃ¡o `0 alpha columns` khÃ´ng?
- Xem `TOP 5 SIGNALS`: Giá»›i háº¡n raw prediction pháº£i > 0.001. Náº¿u < 0.0001 -> Model bá»‹ underfit.

### 2. ADV & Liquidity (Táº§ng Thanh khoáº£n)
- XÃ¡c nhận `adv_unit` lÃ  `vnd`.
- TÃ­nh toÃ¡n Capacity: `Vá»‘n x Asset_Cap` pháº£i `< ADV_20d x Max_ADV_Pct`.
- Náº¿u `2B x 15% (300M) > ADV x 20% (10-20M)` -> Cháº¯c cháº¯n bá»‹ clamp vá»  0.

### 3. Notional Clamping (Táº§ng Khá»‘i lÆ°á»£ng)
- Kiá»ƒm tra `max_notional_value_per_trade`. Vá»›i vá»‘n 2 tá»·, ngÆ°á»¡ng nÃ y pháº£i >= 300M.

## 🛠️ RESOLUTION STEPS (FIX)

1. **Ná»›i lá» ng thanh khoáº£n**: TÄƒng `max_adv_percentage` lÃªn 0.4 - 0.5 cho Diagnostic run.
2. **Äá»“ng bá»™ Unit**: Ã‰p kiá»ƒu `adv_vnd / price` trong Rebalancer.
3. **Log Preflight**: LuÃ´n in ra danh sÃ¡ch mÃ£ thá» a mÃ£n Capacity trÆ°á»›c khi cháº¡y.

---
*Created: 2026-04-29 | Role: Orchestrator Expert*
