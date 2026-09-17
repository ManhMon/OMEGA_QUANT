# Tối ưu hóa Threading Backend cho DiverseAlphaEvolution

Khắc phục tình trạng nghẽn nặng nề trong việc tuần tự hóa (serialization/pickling) dữ liệu lớn khi truyền qua IPC giữa các tiến trình của Joblib Loky trong môi trường WSL/Linux.

## Động cơ & Lý do thay đổi

Hiện tại, khi chạy động cơ tiến hóa `diverse` với 12 workers trên WSL, mỗi generation tiến hóa phải đánh giá 4000 cá thể. 
Do `DiverseAlphaEvolution` được thiết kế cứng backend `"loky"`, Joblib buộc phải serialize (pickle) toàn bộ tham số đầu vào của hàm đánh giá (`train_df`, `val_df`, `train_features`, `val_features` - với tổng dung lượng lên tới ~180MB mỗi lần gửi) cho từng tác vụ trong số 4000 tác vụ đánh giá. 
Điều này dẫn tới hiện tượng nghẽn serialization cực kỳ nghiêm trọng, chiếm tới 42 phút trước khi các workers bắt đầu tính toán thực tế.

Trong khi đó, trình đánh giá biểu thức GP của chúng ta sử dụng JIT VM (Numba JIT) và các hàm Vectorized giải phóng GIL rất tốt. Việc sử dụng backend luồng (`prefer="threads"`) giống như `GeneticEngine` tiêu chuẩn sẽ chia sẻ trực tiếp bộ nhớ mà không có bất kỳ overhead serialization nào, giúp giảm thời gian chạy từ hàng chục phút xuống còn vài giây mỗi generation.

Để đảm bảo an toàn đa luồng tuyệt đối, chúng ta cần chuyển đổi các biến trạng thái toàn cục `_ACTIVE_DATASET_ID` và `_GROUPED_TS_CACHE` thành thread-local bằng cách sử dụng `threading.local()`.

## Thay đổi đề xuất

### 1. [omega] (C:\Users\GHC\repos\OMEGA_QUANT\src\omega)

#### [MODIFY] [genetic_engine.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/genetic_engine.py)

- Chuyển `_ACTIVE_DATASET_ID` và `_GROUPED_TS_CACHE` thành thread-local bằng `threading.local()`.
- Định nghĩa hàm trợ giúp `_get_grouped_ts_cache()` và cập nhật mọi lệnh truy cập cache.

#### [MODIFY] [diverse_alpha_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/diverse_alpha_evolution.py)

- Cập nhật hàm `_ensure_parallel_pool` để truyền `backend=self.config.parallel_backend` vào constructor của `Parallel`.
- Cập nhật log khởi động tại `run()` để phản ánh chính xác backend được cấu hình.

### 2. [scripts] (C:\Users\GHC\repos\OMEGA_QUANT\scripts)

#### [MODIFY] [run_weekly_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)

- Cập nhật hàm `_resolve_diverse_backend` để không tự động chuyển đổi sang `"loky"` trên các hệ thống phi Windows (Linux/WSL) khi yêu cầu backend luồng (`"threads"`).

---

## Chi tiết mã nguồn sửa đổi

### 1. `src/omega/quant/evolution/genetic_engine.py`

Thay đổi định nghĩa các biến toàn cục:
```python
import threading

_local = threading.local()

def set_active_dataset_id(dataset_id: Optional[str]) -> None:
    _local.active_dataset_id = dataset_id

def get_active_dataset_id() -> Optional[str]:
    return getattr(_local, "active_dataset_id", None)

def _get_grouped_ts_cache() -> "OrderedDict[Any, Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Optional[np.ndarray]]]":
    if not hasattr(_local, "grouped_ts_cache"):
        _local.grouped_ts_cache = OrderedDict()
    return _local.grouped_ts_cache
```

Cập nhật các hàm sử dụng:
- Thay thế `_GROUPED_TS_CACHE.clear()` bằng `_get_grouped_ts_cache().clear()`.
- Thay thế `_GROUPED_TS_CACHE.get(...)` bằng `_get_grouped_ts_cache().get(...)`.
- Thay thế `_GROUPED_TS_CACHE.popitem(...)` bằng `_get_grouped_ts_cache().popitem(...)`.

### 2. `src/omega/quant/evolution/diverse_alpha_evolution.py`

Thay thế đoạn khởi tạo pool tại dòng 451-455:
```python
        pool = Parallel(
            n_jobs=n_jobs,
            backend=self.config.parallel_backend,
            initializer=ge.clear_grouped_ts_cache,
        )
```

Thay thế đoạn log tại dòng 663-666:
```python
        logger.info(
            "Diverse evaluation parallelism: backend=%s requested_n_jobs=%d seed=%d",
            self.config.parallel_backend,
            self.config.n_jobs,
            self.config.random_seed,
        )
```

### 3. `scripts/run_weekly_evolution.py`

Thay thế đoạn giải quyết backend tại dòng 81-86:
```python
def _resolve_diverse_backend(backend: str, workers: int) -> str:
    if workers == 1:
        return "threading" if backend == "threads" else backend
    if backend == "threads":
        return "threading"
    return backend

```

---

## Kế hoạch kiểm thử & Xác minh

### Tự động
1. Chạy bộ unit test song song để kiểm tra thread-safety:
   ```bash
   wsl pytest tests/test_diverse_alpha_evolution_parallel.py
   ```
2. Chạy thử tiến trình tiến hóa GP quy mô nhỏ trong môi trường WSL bằng backend `threads`:
   ```bash
   wsl python3 scripts/run_weekly_evolution.py --regime sideways --engine diverse --generations 2 --population-size 40 --workers 12 --backend threads --orthogonalize promoted
   ```
3. Kiểm tra log để xác nhận backend được dùng là `threading` và thời gian hoàn thành dưới 30 giây.
