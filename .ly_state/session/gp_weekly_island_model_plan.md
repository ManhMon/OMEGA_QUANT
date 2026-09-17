# GP Weekly Island Model Plan

## Goal Description

Mở rộng kịch bản tiến hóa GP tuần (`scripts/run_weekly_evolution.py`) để hỗ trợ tùy chọn Island Model (`DiverseAlphaEvolution`) thay thế cho `GeneticEngine` tiêu chuẩn thông qua tham số CLI `--engine`. Việc này cho phép chạy tiến hóa song song chéo 4 phân đảo độc lập, phân bổ chéo các họ alphas hạt giống khác nhau và di cư định kỳ, nâng cao tính đa dạng và tỷ lệ phát hiện alpha chất lượng cao.

## Proposed Changes

### scripts/run_weekly_evolution.py

#### [MODIFY] [run_weekly_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)

- **Cấu hình CLI**:
  - Thêm tham số `--engine` trong hàm `main()`:
    ```python
    parser.add_argument("--engine", type=str, default="standard", choices=["standard", "diverse"],
                        help="GP Engine type: standard or diverse (island model)")
    ```
- **Chữ ký `run_evolution()`**:
  - Thay đổi chữ ký để chấp nhận `val_df` và `engine_type`:
    ```python
    def run_evolution(
        train_df: pd.DataFrame,
        val_df: pd.DataFrame = None,
        engine_type: str = "standard",
        generations: int = 30,
        population_size: int = 100,
        ...
    )
    ```
- **Điều hướng Engine trong `run_evolution()`**:
  - Nếu `engine_type == "diverse"`:
    - Khởi tạo cấu hình `DiverseEvolutionConfig` từ `omega.quant.evolution.diverse_alpha_evolution`.
    - Gọi `DiverseAlphaEvolution(config=diverse_config).run(train_df, val_df, target_col='target')` (Lưu ý: dùng cột mục tiêu `'target'` tương thích với DataFrame đầu vào của kịch bản tuần thay vì `'fwd_ret_5'`).
    - Chuyển đổi danh sách `AlphaCandidate` trả về sang đối tượng tương thích `GPIndividual` (sử dụng hàm chuyển đổi cấu trúc cây từ `Node` sang `GPNode`).
- **Gọi hàm trong `main()`**:
  - Truyền thêm `val_df=val_df` và `engine_type=args.engine` vào lời gọi `run_evolution()`.

## Verification Plan

### Automated Tests
- Chạy biên dịch trực tiếp file thay đổi: `python -m py_compile scripts/run_weekly_evolution.py`.
- Chạy thử nghiệm nhanh tiến hóa GP với Island Model (1 thế hệ, quy mô 40 cá thể):
  ```powershell
  $env:SKIP_LESSON_EXTRACTION='1'
  python scripts/run_weekly_evolution.py --regime sideways --engine diverse --generations 1 --population-size 40 --workers 4
  ```
- Xác nhận kết quả ghi nhận thành công.
