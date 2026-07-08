# Kế Hoạch Sửa Lỗi Hoán Đổi Index Của AlternativeDataFetcher

## Mục Tiêu
Khắc phục lỗi hoán đổi cột (date <-> ticker) nguy hiểm gây ra bởi việc đổi cấu trúc MultiIndex của `AlternativeDataFetcher.generate_all()` sang `['symbol', 'date']` mà không khôi phục về thứ tự gốc `['date', 'symbol']` trước khi trả về.

## Chi Tiết Thay Đổi

### 1. Alternative Data Fetcher

#### [MODIFY] [alternative_data_fetcher.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/alternative_data_fetcher.py)
Khôi phục lại thứ tự MultiIndex `['date', 'symbol']` và thực hiện `sort_index()` ngay trước khi trả về DataFrame kết quả từ hàm `generate_all()`.

```python
        # Join all features back to original panel
        result = panel.join(features)
        
        # Restore index levels order to prevent silent column swap in unified_feature_adapter.py
        result = result.reorder_levels(['date', 'symbol']).sort_index()
        
        logger.info("Generated 10 alternative data signals")
        return result
```

## Kế Hoạch Thử Nghiệm & Thẩm Định
1. L2 triển khai thay thế dòng mã trên.
2. Chạy test suite để kiểm tra tính tương hợp.
3. L3 kiểm duyệt tính đúng đắn và an toàn (sắp xếp chính xác, không Look-ahead bias, loại bỏ hoàn toàn bug hoán đổi cột).
