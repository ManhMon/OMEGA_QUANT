# Repo Architecture Map — 2026-06-04

## Verdict
Repo hiện là **hybrid modular monolith**.

- `src/omega/...` = monolith chính, phạm vi rộng nhất
- `packages/quant/src/omega/quant/...` = có một cụm con đang sống thật, không thể coi là skeleton rỗng
- chưa nên dọn bằng cách xóa mù `packages/`

## Bucket 1 — Duplicate between `src` and `packages`
Có **70** module quant xuất hiện ở cả hai nơi.

Ví dụ nổi bật:
- `quant/execution_sim.py`
- `quant/pipeline.py`
- `quant/live_trading_pipeline.py`
- `quant/realtime_risk_guard.py`
- `quant/portfolio/portfolio_optimizer.py`
- `quant/feature_module.py`
- `quant/label_engine.py`
- `quant/ml/ml_engine.py`
- `quant/execution/order_router.py`
- `quant/risk/risk_monitor.py`

### Recommendation
- Tạm coi `src/omega/...` là **canonical mặc định** cho nhóm duplicate.
- Không cho agent tạo thêm mirror mới vào `packages/` nếu đã có file tương ứng trong `src`.
- Với từng module duplicate, chỉ refactor/move khi có migration plan rõ.

## Bucket 2 — Package-only but actively used
Có **26** module chỉ nằm trong `packages/quant/...`, nhưng đang được dùng thật bởi scripts/tests/audit/docs.

### 2.1 Validation / research core
- `quant/validation/cpcv.py`
- `quant/validation/dsr.py`

### 2.2 Universe selection
- `quant/universe/feature_computer.py`
- `quant/universe/xgb_classifier.py`

### 2.3 Portfolio overlay / execution stack
- `quant/portfolio/execution_sim.py`
- `quant/portfolio/tail_controls.py`
- `quant/portfolio/adaptive_sizing_overlay.py`
- `quant/portfolio/advanced_breaker_overlay.py`
- `quant/portfolio/black_litterman_overlay.py`
- `quant/portfolio/contagion_overlay.py`
- `quant/portfolio/continuous_learning_overlay.py`
- `quant/portfolio/drift_overlay.py`
- `quant/portfolio/hmm_regime_overlay.py`
- `quant/portfolio/regime_aware_wf_overlay.py`
- `quant/portfolio/regime_overlay.py`
- `quant/portfolio/sentiment_overlay.py`
- `quant/portfolio/smart_money_overlay.py`
- `quant/portfolio/tcost_optimizer_overlay.py`
- `quant/portfolio/thompson_sampling_overlay.py`

### 2.4 Evolution / models
- `quant/evolution/feature_adapter.py`
- `quant/evolution/pareto_hof.py`
- `quant/models/lstm_alpha.py`

### Recommendation
- Coi nhóm này là **package-canonical tạm thời**.
- Không tự ý move về `src` nếu chưa kiểm hết import/test/script.
- Mọi thay đổi mới trên các module này nên tiếp tục viết tại `packages/quant/...` cho đến khi hợp nhất kiến trúc.

## Bucket 3 — Src-only modules
Có **115** module chỉ có ở `src/omega/quant/...`.

Đây là vùng monolith chính, gồm nhiều nhóm:
- alpha factory / feature pipeline
- macro / microstructure / datasource
- live / paper trading engine
- evolution orchestration
- strategy modules
- sentiment subpackage

### Recommendation
- Coi đây là **monolith canonical zone**.
- Nếu module mới không thuộc 26 package-only active modules ở trên, mặc định viết vào `src/omega/...`.

## Decision rule for future coding
### Write into `packages/quant/...` only when:
- sửa đúng một file đang package-canonical ở Bucket 2
- hoặc sửa test/script đang trỏ thẳng tới package path đó

### Write into `src/omega/...` when:
- module đã tồn tại ở `src`
- module duplicate mà team quyết định `src` là source-of-truth
- module mới thuộc monolith chính, chưa có package-canonical precedent

## Practical next step
Trước khi dọn repo lớn, nên làm 1 bảng quyết định chính thức cho 70 duplicate modules:
- `src canonical`
- `packages canonical`
- `merge/remove later`

Hiện tại, safe operating mode là:
- `src` = canonical mặc định
- ngoại lệ: 26 module package-only active ở trên = canonical trong `packages/quant`
