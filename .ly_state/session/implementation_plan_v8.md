# Khắc phục lỗ hổng PIT an toàn theo Phản hồi Codex L3 (v8)

Kế hoạch v8 bổ sung đầy đủ các yêu cầu kiểm soát PIT và dữ liệu theo phản hồi trực tiếp từ Codex L3:

## User Review Required

> [!IMPORTANT]
> Cần gửi lại Codex L3 model (`cx/gpt-5.6-sol`) để lấy phê duyệt `[APPROVED]` trước khi bàn giao cho L2 OpenCode triển khai thực tế.

## Proposed Changes

### [Component: Macro Data Pipeline]

#### [MODIFY] [macro_pipeline.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/data/macro_pipeline.py)

**1. Lọc PIT Leak trong `query_as_of`**:
- Sửa điều kiện lọc PyArrow:
  ```python
  (table.column("ingested_at") <= pa.scalar(as_of_dt)) & (table.column("available_at") <= pa.scalar(as_of_dt))
  ```

**2. Bổ sung `published_at` vào `revision_id`**:
- Đổi công thức SHA256:
  ```python
  f"{indicator}|{observed.isoformat()}|{numeric_value}|{published.isoformat()}|{source}"
  ```

### [Component: Sentiment Alpha]

#### [MODIFY] [sentiment_alpha.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/signal/sentiment_alpha.py)

**3. Chặn triệt để non-finite values trong `base_signals`**:
- Báo `ValueError` nếu `base_signals` chứa `NaN`, `inf`, `-inf` (`not np.isfinite(base_signals.to_numpy(dtype=float)).all()`).

**4. Xác thực đồng bộ per-symbol PIT (`available_at` & `timestamp`)**:
- Hỗ trợ cả `available_at` và `timestamp` là scalar hoặc `pd.Series`.
- Chuẩn hóa về `pd.Series` trên toàn bộ universe (`base_signals.index`).
- Kiểm tra `NaT`, index trùng lặp, timezone compatibility.
- Xác thực điều kiện ngặt trên từng symbol:
  ```python
  # as_of <= available_at < timestamp
  if (available_at < as_of).any():
      raise ValueError("PIT violation: as_of must not exceed available_at")
  if (available_at >= timestamp).any():
      raise ValueError("PIT violation: available_at must be strictly less than timestamp")
  ```

### [Component: Tests]

#### [MODIFY] [test_macro_pipeline.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/test_macro_pipeline.py)
- Adversarial test `test_query_as_of_enforces_available_at_not_just_ingested_at`.
- Test `test_revision_id_distinguishes_published_at_vintages`.

#### [MODIFY] [test_sentiment_alpha_opt.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/test_sentiment_alpha_opt.py)
- Test từ chối `base_signals` chứa `NaN` và `±inf`.
- Test per-symbol `available_at` và per-symbol `timestamp` (bao gồm vi phạm cục bộ, timezone mismatch, `NaT`).

## Verification Plan

### Automated Tests
- `python -m pytest tests/test_macro_pipeline.py tests/test_sentiment_alpha_opt.py -v`
