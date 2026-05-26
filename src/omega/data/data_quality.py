from typing import List, Dict, Any

class DataQualityChecker:
    """
    Kiểm tra chất lượng dữ liệu đầu vào.
    Bỏ qua xử lý chia tách (vì data sàn đã adjusted).
    Tập trung vào phát hiện lỗi: NaN, Outliers, Gaps.
    """
    def __init__(self, max_missing_pct: float = 0.05, price_jump_threshold: float = 0.15):
        # Mặc định price jump 15% (UPCOM max biên độ 15%), nếu vượt quá trong 1 phiên có thể là lỗi data
        self.max_missing_pct = max_missing_pct
        self.price_jump_threshold = price_jump_threshold

    def check_missing_values(self, values: List[float]) -> bool:
        """Trả về True nếu tỷ lệ missing values <= ngưỡng cho phép."""
        if not values: 
            return False
        missing = sum(1 for v in values if v is None)
        return (missing / len(values)) <= self.max_missing_pct

    def check_outliers(self, values: List[float]) -> bool:
        """Trả về True nếu không có price jump nào vượt ngưỡng (phát hiện data bẩn/outliers)."""
        if len(values) < 2: 
            return True
        valid_vals = [v for v in values if v is not None]
        for i in range(1, len(valid_vals)):
            prev, curr = valid_vals[i-1], valid_vals[i]
            if prev == 0: 
                continue
            pct_change = abs((curr - prev) / prev)
            if pct_change > self.price_jump_threshold:
                return False
        return True
        
    def validate(self, prices: List[float]) -> Dict[str, Any]:
        """Validate toàn diện 1 chuỗi giá."""
        missing_ok = self.check_missing_values(prices)
        outliers_ok = self.check_outliers(prices)
        return {
            "is_valid": missing_ok and outliers_ok,
            "missing_pass": missing_ok,
            "outliers_pass": outliers_ok
        }
