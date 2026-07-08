# Audit Report: Memory-Optimization & Worker-Config Changes
**Date:** 2026-07-08
**Scope:**
1. `src/omega/quant/sentiment/focal_point_detector.py`
2. `src/omega/quant/evolution/alternative_data_fetcher.py`
3. `scripts/run_weekly_evolution.py`

**Method:** Full diff review against `HEAD`, cross-repo caller trace for every touched public function,
static reasoning on PIT-safety and index-alignment invariants, and live reproduction of suspected defects
with `python -c` scripts. All 3 target test files (`test_focal_point_detector.py`,
`test_vn_features_targeted.py`) plus adjacent GP-engine suites were executed.

---

## TÓM TẮT ĐIỀU HÀNH

| # | Hạng mục | Kết quả |
|---|----------|---------|
| 1 | MultiIndex reorder `['symbol','date']` trong `alternative_data_fetcher.py` | 🔴 **BUG NGHIÊM TRỌNG đã xác nhận bằng thực nghiệm** — làm hỏng dữ liệu ở module khác (`unified_feature_adapter.py`), ảnh hưởng `paper_trading_daily.py` (live) và nhiều script backtest |
| 2 | Pre-grouping theo ngày / vectorized date-map (`_derive_sentiment_indicators`) | 🟢 An toàn — tương đương ngữ nghĩa với code cũ, có regression test bảo vệ, test hiện tại PASS |
| 3 | PIT safety (T-1 lag, không look-ahead) | 🟢 Không phát hiện look-ahead mới. Fast-path 1 cấp index trong `focal_point_detector.analyze()` an toàn vì bất biến gọi hàm được đảm bảo |
| 4 | "Loại bỏ giới hạn worker trên Windows" | ⚠️ **Sai lệch so với thực tế code** — diff **THÊM MỚI** một cap cho Windows (`min(cpu_count, 4)`), không hề gỡ bỏ giới hạn nào |
| 5 | Direct-assignment thay merge cho VN alphas | 🟡 Chấp nhận được nhưng có giả định ẩn (không có (ticker,date) trùng lặp) chưa được assert đầy đủ |
| 6 | `__liquidity_mask__` rolling window | 🟡 **Boundary bleed giữa các ticker** — thiếu `.groupby("ticker")` trước `.rolling()`, lặp lại ở 3 nơi |
| 7 | CLI flags `--min-avg-volume`, `--avg-volume-window` | 🟡 Dead code — khai báo nhưng không bao giờ được dùng |

---

## 1. 🔴 PHÁT HIỆN NGHIÊM TRỌNG: MultiIndex reorder làm hỏng dữ liệu ở `unified_feature_adapter.py`

### Vị trí lỗi
`src/omega/quant/evolution/alternative_data_fetcher.py:208`
```python
panel = panel.reorder_levels(['symbol', 'date']).sort_index()
...
result = panel.join(features)
return result
```
Hàm `generate_all()` nhận panel với MultiIndex `['date', 'symbol']` (theo đúng docstring) nhưng **trả về** panel với thứ tự level đã đảo ngược thành `['symbol', 'date']`. Đây là thay đổi hợp đồng (contract) ngầm của hàm public, không được phản ánh trong docstring "Returns: Panel with additional alt data columns."

### Vì sao đây là lỗi thật, không chỉ là rủi ro lý thuyết
`AlternativeDataFetcher.generate_all()` được gọi tại **7 nơi khác** ngoài `run_weekly_evolution.py` (đã audit), bao gồm:
- `src/omega/quant/evolution/unified_feature_adapter.py` (shared adapter dùng bởi nhiều pipeline)
- `scripts/paper_trading_daily.py` — **pipeline paper-trading đang chạy sống**, `use_arsenal=True` mặc định
- `scripts/backtest_v30_full.py`, `backtest_v31_unified.py`, `backtest_v33_optuna.py`, `backtest_hybrid_regime.py`, `precompute_all_features.py`, `profile_bottlenecks.py`, v.v.

Trong `unified_feature_adapter.py::generate_all()`, ngay sau bước gọi `AlternativeDataFetcher`, có đoạn dùng **giả định vị trí cột** (không dùng tên):
```python
flat = result.reset_index()
flat.columns = ['date', 'ticker'] + list(flat.columns[2:])   # ép tên cột theo VỊ TRÍ
...
arsenal_df = compute_ultimate_alphas(flat[required], symbol_col='ticker')
```
Đoạn tương tự lặp lại ở bước "Microstructure alphas" ngay sau đó.

### Đã tái hiện bằng thực nghiệm (100% xác nhận)
Chạy trực tiếp `AlternativeFeatureGenerator.generate_all()` → `AlternativeDataFetcher.generate_all()` → `reset_index()` → ép tên cột, kết quả:
```
after alt_features index names: ['date', 'symbol']
after alt_data index names:     ['symbol', 'date']   # <-- đã bị đảo bởi thay đổi audit
flat[date] head (phải là ngày, thực tế là?):   ['AAA', 'AAA', 'AAA']              # <-- là SYMBOL
flat[ticker] head (phải là symbol, thực tế là?): [Timestamp('2026-01-01'), ...]    # <-- là DATE
```
Chạy full `UnifiedFeatureAdapter(use_arsenal=True).generate_all(panel)`:
```
arsenal features: 152    # KHÔNG throw exception, KHÔNG log warning
```
→ `compute_ultimate_alphas()` chạy "thành công" nhưng với cột `date` chứa symbol-string và cột `ticker`
(symbol_col) chứa timestamp. Điều này **tệ hơn crash**: 152 cột alpha (`alpha_roc_5`, `alpha_rsi_14`,
`alpha_vn_*`, …) được tính toán với ngữ nghĩa nhóm ("group by symbol") thực chất là "group by date", và
mọi phép biến đổi liên quan đến cột `date` (rolling theo thời gian, sort theo thời gian…) sẽ vận hành trên
dữ liệu symbol-string. Kết quả là **corrupt âm thầm, không có log/exception nào cảnh báo** — nguy hiểm nhất
trong các dạng lỗi vì không ai biết để điều tra.

### Mức độ ảnh hưởng
- **`scripts/paper_trading_daily.py`**: gọi `UnifiedFeatureAdapter(use_arsenal=True).generate_all(panel)` làm
  đường chính (không phải fallback), nghĩa là tín hiệu giao dịch paper trading hiện tại có thể đang dùng
  152 cột alpha bị lệch symbol/date hoàn toàn.
- Các script backtest dùng `UnifiedFeatureAdapter`/`adapter.generate_all` (v30/v31/v33/hybrid_regime, …)
  chịu rủi ro tương tự nếu chúng bật `use_arsenal=True` hoặc dùng logic reset_index theo vị trí tương tự.
- `run_weekly_evolution.py` (file được audit) **không bị ảnh hưởng** vì nó luôn truy cập cột bằng tên
  (`.rename(columns={"symbol": "ticker"})`, `merge(..., on=["date","ticker"])`) — nhưng đây chính là lý do
  lỗi không bị phát hiện trong phạm vi 3 file được yêu cầu audit.

### Khuyến nghị sửa (surgical, tối thiểu)
Khôi phục thứ tự level ban đầu trước khi `return` trong `generate_all()` của
`alternative_data_fetcher.py`, giữ nguyên lợi ích hiệu năng của việc reorder nội bộ:
```python
result = panel.join(features)
result = result.reorder_levels(['date', 'symbol']).sort_index()  # khôi phục hợp đồng ban đầu
return result
```
Đây là thay đổi 1 dòng, không ảnh hưởng đến lợi ích hiệu năng (groupby(level='symbol') contiguous) vì việc
reorder-để-tính-toán chỉ cần áp dụng **trong lúc tính**, không cần giữ ở giá trị trả về.
(Việc sửa `unified_feature_adapter.py` để dùng tên cột thay vì vị trí cũng nên làm, nhưng nằm ngoài phạm vi
3 file được yêu cầu — nêu ra để theo dõi riêng.)

---

## 2. Pre-grouping chéo ngày trong `_derive_sentiment_indicators` — ĐÁNH GIÁ: AN TOÀN

`alternative_data_fetcher.py:126-134`:
```python
market_by_date = {}
for date_str, group in panel.groupby(level='date'):
    market_by_date[date_str] = group.droplevel('date')
```
- Dict key (`date_str`, thực chất là giá trị gốc của level 'date', không phải string ép kiểu) và key tra cứu
  `prev_date_str = dates[i-1]` đều lấy từ cùng một nguồn (`panel.index.get_level_values('date')`), nên type
  nhất quán — tra cứu dict luôn hit, không có KeyError tiềm ẩn.
- `prev_date_str` **luôn** tồn tại trong `market_by_date` vì nó được lấy trực tiếp từ danh sách ngày duy nhất
  của chính `panel` — do đó nhánh fallback "tìm ngày gần nhất" trong code cũ (`historical_panel[...]`) trên
  thực tế **chưa bao giờ được kích hoạt** ở call-site này (đã verify). Việc bỏ nhánh fallback trong fast-path
  mới không làm mất hành vi thực tế nào.
- Vectorized `date_index.map(vsi_map/fss_map).fillna(...)` tương đương chính xác với vòng lặp
  `mask = ...; series[mask] = val` cũ (đã kiểm chứng bằng lập luận + test hiện có
  `test_vectorized_date_mapping_equivalence` — **PASS**).

## 3. PIT-safety / look-ahead bias — ĐÁNH GIÁ: KHÔNG PHÁT HIỆN LOOK-AHEAD MỚI

### `focal_point_detector.py::analyze()` — nhánh `nlevels == 1`
```python
if market_panel.index.nlevels == 1:
    market_slice = market_panel  # dùng trực tiếp, KHÔNG kiểm tra as_of_time
```
- Nhánh này **tin tưởng hoàn toàn (trust-by-contract)** rằng caller đã cắt lát đúng ngày `as_of_time` trước
  khi truyền vào — đây là một *bất biến ẩn (implicit invariant)*, không có assertion nào bảo vệ nếu trong
  tương lai có caller khác truyền nhầm một single-index DataFrame không tương ứng với `as_of_time`.
- Với call site hiện tại duy nhất (`alternative_data_fetcher.py:175`, truyền `prev_slice` ứng với
  `prev_date_str` và `as_of_time=prev_datetime` cùng ngày), bất biến này được thỏa mãn chính xác → **không có
  look-ahead bias**.
- Có test `test_pit_equivalence_full_vs_historical_panel` chứng minh việc truyền full panel vs. panel đã cắt
  lát cho kết quả giống hệt nhau — **PASS**.
- **Khuyến nghị nhẹ**: thêm một dòng comment/docstring nêu rõ bất biến "single-index input phải tương ứng
  đúng as_of_time" để tránh vi phạm trong tương lai khi có thêm caller mới.

### `run_weekly_evolution.py::prepare_features()`
- T-1 lag (`groupby("ticker")[col].shift(1)`) và target forward-return
  (`groupby("ticker")["close"].pct_change(h).shift(-h)`) không bị thay đổi bởi các tối ưu hoá bộ nhớ — vẫn
  strictly per-ticker, đúng như comment "PIT SAFETY" khẳng định.
- Thay `reset_index(drop=True)` bằng gán `result.index = pd.RangeIndex(len(result))`: **tương đương chức
  năng 100%**, chỉ nhanh hơn nhẹ vì tránh tạo DataFrame trung gian — không có rủi ro.

---

## 4. Direct-assignment VN alphas thay vì `merge` — 🟡 CHẤP NHẬN ĐƯỢC, có giả định chưa được assert đầy đủ

```python
assert (result["ticker"].values == vn_features_df["ticker"].values).all()
assert (result["date"].values == vn_features_df["date"].values).all()
result[col] = vn_features_df[col].values   # gán theo VỊ TRÍ, không theo key
```
- Đã verify `compute_all_vn_alphas()` (trong `vn.py`) luôn trả về đúng số dòng, đúng tập (ticker,date) như
  input, và thứ tự sort cuối cùng (`groupby("ticker")` mặc định sort ascending + `sort_values("date")` trong
  từng nhóm) khớp với `result.sort_values(["ticker","date"])` ở `run_weekly_evolution.py` — trong điều kiện
  **không có (ticker, date) trùng lặp**.
- **Giả định ẩn**: nếu tồn tại dòng trùng (ticker, date) — một lỗi chất lượng dữ liệu upstream — 2 assert
  hiện tại (`ticker` khớp, `date` khớp) sẽ **PASS giả** vì các dòng trùng có cùng giá trị khoá, trong khi giá
  trị feature ở vị trí đó có thể bị hoán đổi sai giữa 2 dòng trùng lặp. Đây không phải regression so với
  `merge` cũ (merge với key trùng còn tệ hơn — nhân bản dòng), nhưng asserts hiện tại tạo cảm giác an toàn
  giả tạo.
- **Khuyến nghị**: thêm 1 assert duy nhất, rẻ, ở đầu hàm:
  ```python
  assert not result.duplicated(subset=["ticker", "date"]).any(), "Duplicate (ticker,date) rows detected"
  ```

## 5. ⚠️ Windows worker "limit" — CHỈNH SỬA TIỀN ĐỀ AUDIT

Yêu cầu audit nêu "việc loại bỏ giới hạn worker trên Windows". Sau khi rà soát toàn bộ diff và
`genetic_engine.py` (không có bất kỳ đoạn `platform.system()`/cap Windows nào tồn tại trước đây trong cả 3
file lẫn `genetic_engine.py`), kết luận: **thay đổi này KHÔNG loại bỏ giới hạn nào — nó THÊM MỚI một giới
hạn Windows**:

```python
if platform.system() == "Windows":
    n_jobs = min(cpu_count, 4)   # <-- cap MỚI, chỉ áp dụng khi workers <= 0 (auto-detect)
```

- Trước thay đổi này: `run_weekly_evolution.py` **chưa từng** truyền `n_jobs` vào `GPConfig`, nên
  `GeneticEngine` luôn dùng default `n_jobs = -1` (dataclass field tại `genetic_engine.py:580`) — tức là
  **không giới hạn**, dùng toàn bộ core CPU trên mọi hệ điều hành kể cả Windows.
- Sau thay đổi: mặc định CLI `--workers 4` (không phải `-1`/auto) → `n_jobs=4` áp dụng **trên mọi nền tảng**,
  không riêng Windows. Chỉ khi người dùng chủ động truyền `--workers -1` hoặc `0`, logic auto-detect mới
  chạy, và lúc đó Windows bị cap còn Linux/Mac thì không.
- **Đề xuất hành động**: nếu ý định thực sự là "gỡ giới hạn", cần xác nhận lại với đội phát triển xem có phải
  đang nhầm giữa "thêm cấu hình worker" và "gỡ giới hạn cứng" hay không. Bản thân cap `min(cpu_count, 4)` là
  một safeguard hợp lý (tránh over-subscription bộ nhớ trên máy Windows RAM hạn chế), **không phải lỗi**,
  chỉ là mô tả trong yêu cầu audit không khớp code thực tế.
- Backend `"threads"` (joblib `threading`) hợp lý nếu core evaluation (Numba JIT stack VM, theo các commit
  gần đây `7998719b`, `7eb01d9a`) release GIL — tránh overhead spawn process của `loky`/`multiprocessing`
  vốn đắt trên Windows. Việc `Parallel(n_jobs=..., batch_size='auto')` trong `genetic_engine.py` không chỉ
  định `backend=` tường minh nên kế thừa đúng context `parallel_backend(...)` — đã verify bằng code trace,
  wiring chính xác.

## 6. 🟡 `__liquidity_mask__` — boundary bleed giữa các ticker (lặp lại 3 nơi)

`run_weekly_evolution.py` (trong `run_evolution()`, `evaluate_and_promote()`, và phần validation ở `main()`):
```python
avg_vol = pd.Series(train_df["volume"].values).rolling(avg_volume_window).mean().fillna(0.0).values
```
- `train_df`/`test_df`/`val_df` là dữ liệu **đa ticker đã nối** (theo cùng cấu trúc `prepare_features()` trả
  về, sort theo `["ticker","date"]`). `.rolling(20)` áp dụng trực tiếp lên toàn bộ Series **không có
  `.groupby("ticker")`**, nên với mỗi ticker mới bắt đầu (trừ ticker đầu tiên), 19 dòng đầu tiên sẽ tính
  trung bình volume **lẫn với dữ liệu của ticker liền trước** trong danh sách sort — đúng loại lỗi "boundary
  bleed" mà chính codebase này đã cẩn thận phòng tránh ở `prepare_features()`
  (comment: "Compute derived features grouped by ticker to prevent boundary bleed").
- Hậu quả: `__liquidity_mask__` có thể sai (true/false lệch) cho khoảng `19 × (số ticker - 1)` dòng — quy mô
  nhỏ so với tổng dữ liệu nhưng là lỗi thật, và đúng loại lỗi mà audit yêu cầu kiểm tra.
- **Khuyến nghị sửa** (áp dụng cho cả 3 vị trí lặp lại):
  ```python
  avg_vol = train_df.groupby("ticker")["volume"].transform(
      lambda x: x.rolling(avg_volume_window, min_periods=1).mean()
  ).fillna(0.0).values
  ```

## 7. 🟡 Dead CLI flags

`--min-avg-volume` (mặc định 500000.0) và `--avg-volume-window` (mặc định 20) được khai báo ở `argparse`
nhưng **không có bất kỳ tham chiếu `args.min_avg_volume` / `args.avg_volume_window` nào** trong toàn bộ file
— đã verify bằng grep. Giá trị `20` và `500000.0` bị hard-code trực tiếp ở 3 nơi tính `__liquidity_mask__`.
Người vận hành truyền các flag này qua CLI sẽ không có tác dụng gì mà không có cảnh báo. Khuyến nghị: wire
`args.min_avg_volume`/`args.avg_volume_window` xuyên suốt `run_evolution()`/`evaluate_and_promote()`, hoặc
xoá 2 flag nếu chưa cần dùng.

---

## KIỂM CHỨNG (Verification Log)

| Kiểm tra | Kết quả |
|---|---|
| `pytest tests/test_focal_point_detector.py` | 5 passed (bao gồm 2 regression test PIT-equivalence & vectorized-mapping-equivalence mới) |
| `pytest tests/test_vn_features_targeted.py` | 4 passed (bao gồm `test_prepare_features_pit_safety` chạy full pipeline qua direct-assignment mới) |
| `pytest tests/test_genetic_alpha_evolution_v4.py tests/quant_test_genetic_engine_optimizations.py tests/test_gp_numba_jit_vm.py` | 44 passed |
| Repro `UnifiedFeatureAdapter(use_arsenal=True).generate_all(panel)` sau reorder | Xác nhận cột `date`/`ticker` bị hoán đổi, 152 alpha cột tính sai âm thầm, không exception/warning |
| Grep toàn repo caller của `AlternativeDataFetcher().generate_all` | 7+ call site ngoài phạm vi audit, gồm `paper_trading_daily.py` (live) |
| Grep `args.min_avg_volume`/`args.avg_volume_window` | 0 kết quả — dead flags xác nhận |

## KHUYẾN NGHỊ ƯU TIÊN

1. **[P0 — sửa ngay]** Khôi phục thứ tự index `['date','symbol']` khi return trong
   `AlternativeDataFetcher.generate_all()` — 1 dòng, chặn corrupt dữ liệu ở paper trading & backtest.
2. **[P1]** Sửa `.rolling()` cho `__liquidity_mask__` dùng `.groupby("ticker")` ở cả 3 vị trí trong
   `run_weekly_evolution.py`.
3. **[P2]** Thêm assert chống trùng lặp `(ticker, date)` trước khi gán trực tiếp giá trị VN alphas.
4. **[P2]** Wire hoặc xoá `--min-avg-volume`/`--avg-volume-window`.
5. **[P3 — thông tin]** Làm rõ với team rằng thay đổi worker/backend là **thêm cap Windows mới**, không
   phải gỡ bỏ giới hạn cũ — cập nhật lại changelog/PR description nếu cần cho khớp thực tế.
