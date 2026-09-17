# Khắc phục lỗ hổng PIT an toàn theo Advisory Deep Audit (v7)

Codex Advisory Deep Audit đã trả về `[NEEDS_FIX]` trên bản v6 do các lỗ hổng về Point-in-Time (PIT) safety và tính toán revision. Kế hoạch v7 này được lập ra để đóng kín các điểm yếu này.

## User Review Required

> [!IMPORTANT]
> Cần phê duyệt từ Codex L3 CLI model (`cx/gpt-5.6-sol`) đối với kế hoạch này trước khi L2 tiến hành lập trình, theo đúng `Plan Approval Rule` trong `AGENTS.md`.

## Proposed Changes

### [Component: Macro Data Pipeline]

#### [MODIFY] [macro_pipeline.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/data/macro_pipeline.py)

**1. Sửa lỗ hổng PIT Leak trong `query_as_of`**:
Sửa truy vấn để bảo vệ khỏi dữ liệu chưa được công bố. Hiện tại, một giá trị ingest vào ngày T nhưng `available_at` (ngày hiệu lực) là T+3 thì tại T+1 nó đã lọt qua lưới lọc nếu chỉ kiểm tra `ingested_at`.
- Thêm điều kiện: `(table.column("ingested_at") <= pa.scalar(as_of_dt)) & (table.column("available_at") <= pa.scalar(as_of_dt))`

**2. Vá `revision_id` để tránh đụng độ**:
Bổ sung `published_at` vào hash để định danh duy nhất các vintage.
- Sửa thành: `hashlib.sha256(f"{indicator}|{observed.isoformat()}|{numeric_value}|{published.isoformat()}|{source}".encode()).hexdigest()[:16]`

### [Component: Sentiment Alpha]

#### [MODIFY] [sentiment_alpha.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/signal/sentiment_alpha.py)

**3. Ngăn chặn lan truyền NaN từ `base_signals`**:
- Thêm logic báo lỗi nếu `base_signals.isna().any() == True`.
- Đảm bảo các mảng đưa vào hàm tính toán allocation đều chứa dữ liệu finite và hợp lệ.

**4. Xác thực chặt chẽ `available_at` trên từng symbol**:
- Sửa hàm `_validate_pit` để hỗ trợ `available_at` ở dạng `pd.Series` ngoài dạng vô hướng (scalar).
- Nếu `available_at` là `pd.Series`, kiểm tra: `if not (as_of <= available_at).all(): raise ValueError("as_of must be <= available_at for all symbols")`.
- Xác thực `available_at` không có `NaN` trước khi thực hiện.

### [Component: Tests]

#### [MODIFY] [test_macro_pipeline.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/test_macro_pipeline.py)
- Thêm adversarial test: `test_query_as_of_enforces_available_at_not_just_ingested_at`
- Thêm test: `test_revision_id_distinguishes_published_at_vintages`

#### [MODIFY] [test_sentiment_alpha_opt.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/test_sentiment_alpha_opt.py)
- Thêm test: `test_base_signals_with_nan_rejected`
- Thêm test: `test_per_symbol_available_at_validation`

## Verification Plan

### Automated Tests
- Chạy toàn bộ pytest suite cho hai file để khẳng định coverage:
  `python -m pytest tests/test_macro_pipeline.py tests/test_sentiment_alpha_opt.py -v`

### SoD Gate
- Kế hoạch v7 sẽ được Codex L3 duyệt, sau đó OpenCode L2 thi công. Codex L3 sẽ độc lập audit lại kết quả thực thi của L2.
