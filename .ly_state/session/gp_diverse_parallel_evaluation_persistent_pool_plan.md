# Kế hoạch tối ưu hóa hiệu năng song song động cơ Diverse GP (Persistent Worker Pool)

Kế hoạch này loại bỏ hoàn toàn việc liên tục tạo và hủy các tiến trình con (Loky workers) ở mỗi thế hệ. Chúng ta sẽ khởi tạo Joblib `Parallel` pool đúng 1 lần duy nhất ở cấp ngoài cùng (`DiverseAlphaEvolution.run()`) và tái sử dụng qua toàn bộ quá trình tiến hóa.

## Proposed Changes

### Component 1: Động cơ tiến hóa Diverse Alpha

#### [MODIFY] src/omega/quant/evolution/diverse_alpha_evolution.py

- **Khôi phục Node.TERMINALS trong `_evolve_island_job()` để tránh rò rỉ**:
  - Khi thực hiện kiểm thử hoặc gọi song song qua helper `_evolve_island_job()`, các đặc trưng thay thế được thêm vào `Node.TERMINALS` qua `_register_island_terminals()` mà không được thu hồi.
  - Thêm cơ chế lưu trữ và phục hồi danh sách gốc trong khối `finally` của `_evolve_island_job()`:

```python
def _evolve_island_job(
    config: DiverseEvolutionConfig,
    population: List[Genome],
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    target_col: str,
    train_features: Dict[str, np.ndarray],
    train_target: np.ndarray,
    val_features: Dict[str, np.ndarray],
    val_target: np.ndarray,
    seed: int,
) -> tuple[List[Genome], List[AlphaCandidate]]:
    orig_terminals = list(Node.TERMINALS)
    try:
        with _temporary_random_seed(seed):
            _register_island_terminals()
            return DiverseAlphaEvolution(config=config)._evolve_island(
                population,
                train_df,
                val_df,
                target_col,
                train_features,
                train_target,
                val_features,
                val_target,
            )
    finally:
        ge.clear_grouped_ts_cache()
        Node.TERMINALS[:] = orig_terminals
```

- **Thay đổi hàm `run()` và Quản lý Vòng đời Parallel**:
  - Trực tiếp chạy vòng lặp đảo trên cùng một thực thể `self` để kế thừa `self._parallel`.
  - Tách hàm `run()` thành hàm wrapper quản lý ngữ cảnh và `_run_evolution()` thực thi logic.
  - Mã nguồn thay thế chi tiết cho hàm `run()` và vòng lặp đảo mới:

```python
    def run(
        self,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        target_col: str = "fwd_ret_5",
    ) -> List[AlphaCandidate]:
        n_jobs = _resolve_parallel_jobs(self.config)
        ge.clear_grouped_ts_cache()
        try:
            if n_jobs == 1:
                self._parallel = None
                return self._run_evolution(train_df, val_df, target_col)
            
            with Parallel(n_jobs=n_jobs, backend="loky", initializer=ge.clear_grouped_ts_cache) as parallel:
                self._parallel = parallel
                return self._run_evolution(train_df, val_df, target_col)
        finally:
            self._parallel = None
            ge.clear_grouped_ts_cache()
```

- **Vòng lặp tiến hóa mới trong `_run_evolution()`**:
  - Gọi trực tiếp `self._evolve_island()` thay vì helper `_evolve_island_job()`:

```python
            # Evolution loop
            for gen in range(self.config.generations):
                generation_results = []
                for i in range(n_islands):
                    seed = _island_seed(self.config.random_seed, generation=gen + 1, island_id=i, phase=7)
                    with _temporary_random_seed(seed):
                        _register_island_terminals()
                        res = self._evolve_island(
                            islands[i],
                            train_df,
                            val_df,
                            target_col,
                            train_features,
                            train_target,
                            val_features,
                            val_target,
                        )
                        generation_results.append(res)
```

- **Khởi tạo Định danh Bộ dữ liệu (Dataset ID Setup & Contiguous Array Normalization)**:
  - Ở đầu hàm `run()`, tạo các định danh UUID ngẫu nhiên duy nhất cho tập train và validation.
  - Chuẩn hóa các mảng trong `train_features` và `val_features` thành contiguous và read-only (chặn hoàn toàn đột biến và loại bỏ sai lệch view/strides):
    ```python
    # Thực hiện trong DiverseAlphaEvolution.run()
    for features in [train_features, val_features]:
        for k, v in list(features.items()):
            if isinstance(v, np.ndarray):
                arr = np.ascontiguousarray(v)
                arr.flags.writeable = False
                features[k] = arr
    ```
  - Gán các định danh này vào các từ điển đặc trưng tương ứng:
    ```python
    import uuid
    train_features['__dataset_id__'] = f"train_{uuid.uuid4()}"
    val_features['__dataset_id__'] = f"val_{uuid.uuid4()}"
    ```

- **Thay thế khối khởi tạo Parallel trong `_evaluate_population()`**:
  - Tái sử dụng `self._parallel` nếu khả dụng:

```python
    def _evaluate_population(
        self,
        population: List[Genome],
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        target_col: str,
        train_features: Dict[str, np.ndarray],
        train_target: np.ndarray,
        val_features: Dict[str, np.ndarray],
        val_target: np.ndarray,
    ) -> List[AlphaCandidate]:
        n_jobs = min(_resolve_parallel_jobs(self.config), len(population)) if population else 1
        parallel = getattr(self, "_parallel", None)
        if parallel is None or n_jobs == 1:
            evaluated = [
                _evaluate_genome_job(
                    genome,
                    train_df,
                    val_df,
                    target_col,
                    self.config,
                    train_features,
                    train_target,
                    val_features,
                    val_target,
                )
                for genome in population
            ]
        else:
            evaluated = parallel(
                delayed(_evaluate_genome_job)(
                    genome,
                    train_df,
                    val_df,
                    target_col,
                    self.config,
                    train_features,
                    train_target,
                    val_features,
                    val_target,
                )
                for genome in population
            )
        
        candidates = [candidate for candidate in evaluated if candidate is not None]
        candidates.sort(key=_candidate_score, reverse=True)
        gc.collect()
        return candidates
```

- **Chặn dọn dẹp cache cục bộ**:
  - Loại bỏ hoàn toàn khối `finally: ge.clear_grouped_ts_cache()` trong `_evaluate_genome_job` để bộ nhớ đệm tồn tại xuyên suốt vòng đời của worker.

#### [MODIFY] src/omega/quant/evolution/genetic_engine.py

- **Trạng thái Active Dataset ID chéo các luồng tính toán (Process-Active Dataset ID)**:
  - Định nghĩa biến toàn cục và các hàm setter/getter trong `genetic_engine.py` để theo dõi tập dữ liệu đang được xử lý trong tiến trình:
    ```python
    _ACTIVE_DATASET_ID: Optional[str] = None

    def set_active_dataset_id(dataset_id: Optional[str]) -> None:
        global _ACTIVE_DATASET_ID
        _ACTIVE_DATASET_ID = dataset_id

    def get_active_dataset_id() -> Optional[str]:
        return _ACTIVE_DATASET_ID
    ```

- **Đồng bộ thiết lập Active Dataset ID trong quá trình đánh giá cá thể**:
  - Trong hàm `_candidate_from_genome_standard()`, thiết lập ID tương ứng trước khi thực thi tín hiệu trên tập train và tập val:
    ```python
    # Trước khi tính toán trên tập train
    ge.set_active_dataset_id(train_features.get('__dataset_id__') if train_features else None)
    try:
        # Thực thi signal và tính IC tập train
        ...
    finally:
        ge.set_active_dataset_id(None)

    # Trước khi tính toán trên tập val
    ge.set_active_dataset_id(val_features.get('__dataset_id__') if val_features else None)
    try:
        # Thực thi signal và tính IC tập val
        ...
    finally:
        ge.set_active_dataset_id(None)
    ```

- **Khóa Cache Định Danh Dữ liệu Bất biến (Collision-Free Dataset-ID Cache Keys)**:
  - Trong hàm `_apply_grouped_ts_transform`, kiểm tra xem active dataset ID có được thiết lập hay không:
    - Nếu có, sử dụng chuỗi định danh đó làm khóa cache: `cache_key = dataset_id`.
    - Nếu không (tương thích ngược), rơi về khóa mặc định dựa trên con trỏ mảng cũ.
  - Sử dụng `collections.OrderedDict` quản lý `_GROUPED_TS_CACHE`.
  - Áp dụng chính sách loại bỏ FIFO nghiêm ngặt để đảm bảo dung lượng cache luôn nhỏ hơn hoặc bằng 4:
    ```python
    if cache_key not in _GROUPED_TS_CACHE:
        if len(_GROUPED_TS_CACHE) >= 4:
            _GROUPED_TS_CACHE.popitem(last=False)
        _GROUPED_TS_CACHE[cache_key] = cached
    ```
  - Cơ chế này hoàn toàn ổn định chéo Loky worker, không bị ảnh hưởng bởi memmapping, kiểu dữ liệu, hay lỗi cắt lát (views) của NumPy.

#### [MODIFY] scripts/run_weekly_evolution.py
- **Bỏ giới hạn n_jobs trên Windows cho Loky**:
  - Sửa đổi hàm `_resolve_job_count()` để hỗ trợ chạy song song thực tế trên Windows sử dụng Loky, cho phép thực thi đa tiến trình ổn định thông qua persistent pool:
  ```python
      if sys.platform == "win32" and backend in {"loky", "multiprocessing"}:
          # Bỏ cưỡng bức n_jobs=1 cho Loky để kiểm thử persistent pool song song trên Windows
          logger.info(f"Using Windows parallel execution for {backend} backend with resolved n_jobs={requested}")
          return requested
  ```

---

## Verification Plan

### Automated Tests
- Cập nhật và viết thêm các unit tests trong `tests/test_diverse_alpha_evolution_parallel.py` để kiểm thử:
  1. Khởi tạo Parallel pool 1 lần duy nhất và tái sử dụng qua các thế hệ.
  2. Tắt Parallel pool khi chạy chế độ serial `n_jobs == 1`.
  3. Định danh chính xác và an toàn của khóa cache dùng Dataset ID chéo Loky worker serialization.
  4. Độc lập an toàn không lồng Parallel (no-nested pools).
  5. Giới hạn dung lượng cache tối đa (eviction policy <= 4).
  6. So sánh parity kết quả tuyệt đối giữa chạy tuần tự và chạy song song.
  7. **Kiểm thử tái sử dụng worker PID của Loky Parallel (warm-up)**:
     - Chạy làm nóng (warm-up) với quần thể 20 genomes để kích hoạt toàn bộ workers trong pool trước khi ghi nhận PID chéo 2 thế hệ kế tiếp, đảm bảo so sánh PID ổn định 100%.
- Thực thi kiểm thử:
  ```powershell
  python -m pytest tests/test_diverse_alpha_evolution_parallel.py -q
  ```

### Manual Verification & Benchmarks
- Khởi chạy thử nghiệm quy mô nhỏ trên môi trường Windows bản địa với Loky song song thực sự:
  ```powershell
  python scripts/run_weekly_evolution.py --regime sideways --engine diverse --generations 2 --population-size 40 --workers 4 --backend loky
  ```
