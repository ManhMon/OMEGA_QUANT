I now have an accurate, grounded picture. Key finding from the audit: **most of what the current plan frames as "new to build" already exists in the codebase** — and two of its formulas (square-root market impact, ceiling/floor price limits) are already implemented. The genuinely novel pieces are narrower than the plan implies. Here is my evaluation followed by the complete rewritten plan.

---

## Đánh giá nhanh bản kế hoạch hiện tại

**Điểm mạnh:** Tư duy 4 tầng lọc đúng hướng; ý thức PIT/slippage/price-limit tốt; 4 ý tưởng nghiên cứu (fracdiff, Hawkes, conformal động, survival) đều có giá trị.

**Vấn đề nghiêm trọng nhất — trùng lặp với code đã có (nguy cơ reinvent):**

| Hạng mục trong plan | Đã tồn tại trong repo | Kết luận |
|---|---|---|
| `SectorRotationEngine` (mới) | `portfolio/sector_classifier.py::SectorClassifier` (đã có `compute_relative_strength`, `detect_sector_rotation`, `compute_sector_flow`) | **Mở rộng**, không viết mới |
| Slippage square-root (§2) | `execution/transaction_cost.py::TransactionCostModel` — đã có market-impact `√(V/ADV)` | **Hiệu chuẩn lại**, không viết mới |
| Chặn Trần/Sàn | `core/vn_market_rules.py::VnMarketRules.calculate_price_limits` (đã có tick-round, 7%) | **Gọi lại**, không tự dò trần |
| Regime/HMM (ý tưởng C) | `strategy/regime_detector.py` (HMM), `strategy/latent_gmm.py` (GMM), `math/bocpd.py` (BOCPD) | **Tái dùng** |
| Triple-barrier | `backtest/label_engine.py`, `backtest/multi_horizon_labels.py` (đã có `settlement_gap`) | **Tái dùng** |
| PIT-safety | `risk/pit_guardian.py::PITGuardian.check_target_leakage` | **Tái dùng** |
| CPCV + DSR | `validation/cpcv.py`, `validation/dsr.py` | **Tái dùng** |

**Thực sự MỚI (không có sẵn):** Conformal/Mondrian predictor · Hawkes · Fractional differentiation · Survival model · Meta-labeling (đề xuất thêm).

**Lỗi kỹ thuật cần sửa trong spec cũ:**
1. CQR gọi là "Mondrian" nhưng code chỉ tính **một** `np.quantile` toàn cục → không phải Mondrian. Mondrian đòi hỏi score theo *nhóm* (regime × liquidity bucket).
2. RS ex-Top3 dùng `groupby('ticker')['market_cap'].shift(1)` — sai trục: xếp hạng vốn hóa phải trên **lát cắt ngang theo ngày**, không phải shift theo mã.
3. `Publish_Lag=45` cố định là *giả định*, không phải sự thật: nên dùng `publish_date` thực khi có, fallback 45.
4. Đề xuất Hawkes cho dữ liệu EOD là rủi ro — Hawkes cần timestamp sự kiện nội phiên; với EOD, **BOCPD (đã có) là thay thế rẻ và vững hơn**. Giữ Hawkes như nhánh nâng cao có điều kiện.

**Ý tưởng đột phá tôi bổ sung:** Meta-labeling (López de Prado) để lọc false-positive & định cỡ lệnh; Conformal-width điều biến bằng **BOCPD run-length** (thay Hawkes ở EOD); Ceiling-unlock reversal alpha khai thác T+2.5; Regime-conditional alpha weighting qua Thompson sampling (đã có `thompson_sampling.py`).

Dưới đây là bản kế hoạch mới hoàn chỉnh. Tôi in trực tiếp ra màn hình để bạn lưu.

---

# Kế Hoạch & Đặc Tả Kỹ Thuật Định Lượng v2 — Ma Trận Quyết Định 4 Chiều, Dự Báo Cực Trị Conformal & Vi Cấu Trúc Thị Trường VN

> **Phiên bản:** 2.0 · **Trạng thái:** Draft để phê duyệt · **Nguyên tắc chủ đạo:** *Reuse-first* — mọi hạng mục phải tra soát module đã có trước khi viết mới. Chỉ 5 thành phần được phép tạo mới (đánh dấu 🆕). Mọi thứ khác là **EXTEND** (mở rộng) hoặc **WIRE** (đấu nối).

---

## 0. Bối Cảnh & Phạm Vi

Repo OMEGA_QUANT đã có hạ tầng quant trưởng thành (alpha arsenal, CPCV, DSR, HMM/GMM/BOCPD regime, PIT guardian, VN market rules, transaction-cost model). Bản kế hoạch này **không** dựng lại các thành phần đó; nó **đấu nối chúng thành một ma trận quyết định 4 chiều mạch lạc** và bổ sung đúng 5 năng lực còn thiếu.

**Mục tiêu định lượng (Definition of Done):**
- Deflated Sharpe Ratio (DSR, tái dùng `validation/dsr.py`) $> 0.95$ trên OOS của CPCV.
- Max Drawdown giảm $\ge 15\%$ so với cấu hình C3 hiện hành.
- Tỷ lệ "mua trúng đỉnh" (chạm biên stop trước biên target của triple-barrier) giảm $\ge 20\%$.
- **Không** có vi phạm PIT nào từ `PITGuardian.check_target_leakage` trên toàn feature panel.

**Ngoài phạm vi (Non-goals):** thay đổi execution live, thay đổi nguồn dữ liệu, tối ưu hạ tầng DB.

---

## 1. Kiến Trúc Ma Trận Quyết Định 4 Chiều

Bốn tầng lọc tuần tự; mỗi tầng chỉ *thu hẹp* tập ứng viên và *điều biến* cỡ vị thế — không tầng nào được nhìn tương lai.

```
                 [Panel dữ liệu PIT-safe: giá / khối lượng / BCTC / dòng vốn ngoại]
                                          │
        ┌─────────────────────────────────┴──────────────────────────────────┐
        ▼                                                                      │
┌────────────────────────────────────────┐   nguồn tái dùng                    │
│ Chiều 1 — Regime Vĩ Mô & Hàng Hóa       │   strategy/regime_detector.py (HMM) │
│  → Risk-On / Neutral / Risk-Off         │   strategy/latent_gmm.py (GMM)      │
│  → đặt Cash_Cap & exposure_scale        │   math/bocpd.py (changepoint)       │
└──────────────────┬─────────────────────┘                                     │
                   ▼                                                            │
┌────────────────────────────────────────┐                                     │
│ Chiều 2 — Cơ Bản Vi Mô (Quality Gate)   │   risk/pit_guardian.py             │
│  → loại mã rác; PIT publish-lag BCTC     │   (publish_date thực, fallback 45d) │
└──────────────────┬─────────────────────┘                                     │
                   ▼                                                            │
┌────────────────────────────────────────┐                                     │
│ Chiều 3 — Dòng Tiền & RS Ngành (Breadth) │   portfolio/sector_classifier.py  │
│  → Sector Breadth + RS ex-Top3 (t-1)    │   data/vn_market.py (foreign flow) │
└──────────────────┬─────────────────────┘                                     │
                   ▼                                                            │
┌────────────────────────────────────────┐                                     │
│ Chiều 4 — Điểm Vào & Dải Giá Conformal   │   🆕 models/conformal_predictor.py │
│  → CQR + Mondrian(regime×liquidity)      │   backtest/label_engine.py (nhãn)  │
│  → dải nở/co theo BOCPD run-length        │   core/vn_market_rules.py (limits) │
└──────────────────┬─────────────────────┘                                     │
                   ▼                                                            │
        [Meta-label filter 🆕] → [Position sizing] → [Execution với price-limit + √-slippage]
```

### Chiều 1 — Regime Vĩ Mô & Hàng Hóa *(WIRE, không code mới)*
- **Đầu vào:** GDP/CPI (World Bank), USD/VND, vàng, Brent qua `FreeMacroClient`; cộng đặc trưng nội thị (VNINDEX vol, breadth).
- **Bộ phân loại:** dùng `RegimeDetectorHMM` (nhãn theo return) **hoặc** `LatentGMMRegime` (posterior mượt). Lấy `get_dampening_factor()` / `get_exposure_scale()` làm `exposure_scale ∈ [0,1]`.
- **Changepoint guard:** `BOCPDDetector.is_regime_change()` trên chuỗi return VNINDEX → khi phát hiện đổi pha, ép `exposure_scale ← min(exposure_scale, 0.5)` cho tới khi run-length hồi phục.
- **Đầu ra:** `regime_state ∈ {RiskOn, Neutral, RiskOff}`, `exposure_scale`, `bocpd_run_length`.

### Chiều 2 — Cơ Bản Vi Mô (Quality Gate) *(EXTEND)*
- **PIT BCTC:** dùng `publish_date` **thực** khi có trong bảng fundamentals; chỉ khi thiếu mới fallback lag công bố nhân tạo `PUBLISH_LAG_DAYS = 45` (quý) / `90` (kiểm toán năm). Ghi cột `fundamental_asof` và verify bằng `PITGuardian.verify_feature_lag`.
- **Luật loại cứng** (mọi giá trị lấy tại `fundamental_asof ≤ t`):
$$\text{Filter Out} \iff (D/E_t > 1.5)\ \lor\ (\text{ROE}_t < 8\%)\ \lor\ (\text{NetProfit lỗ}\ \ge 2\ \text{quý liên tiếp})$$
- **Đầu ra:** `quality_pass ∈ {0,1}` cho từng mã theo ngày.

### Chiều 3 — Dòng Tiền & RS Ngành *(EXTEND `SectorClassifier`)*
- **Sector PIT:** phân ngành lịch sử qua ánh xạ as-of (mở rộng `SectorClassifier.fetch_sector_mapping` → thêm `get_sector_mapping_pit(date)`).
- **Sector Breadth:** % mã trong ngành đóng cửa trên MA50 cá thể (MA đã `shift(1)`).
- **RS ex-Top3 (sửa lỗi trục):** xếp hạng vốn hóa trên **lát cắt ngang theo ngày $t-1$**, loại 3 mã lớn nhất mỗi ngành, rồi tính:
$$RS_{i,t} = w_1\cdot \text{Perf\_vs\_Index}_{i,t} + w_2\cdot \text{Perf\_vs\_Sector\_ExTop3}_{i,t}$$
- **Dòng vốn ngoại:** dùng `VNMarketFlowDataSource.fetch_foreign_flow` + `fetch_prop_flow` làm đặc trưng smart-money (z-score 20 ngày).
- **Đầu ra:** `sector_breadth`, `rs_score`, `foreign_flow_z`.

### Chiều 4 — Điểm Vào & Dải Giá Conformal *(🆕 + WIRE)*
- **Nhãn:** dùng `backtest/label_engine.py` + `MultiHorizonLabels` (triple-barrier co giãn theo EWMA-vol, `settlement_gap` đã có). Nhãn $-1$ nếu chạm stop trước target.
- **CQR + Mondrian thật:** `ConformalTrendPredictor` 🆕 — LightGBM quantile, hiệu chuẩn conformal **theo nhóm** `(regime_state × liquidity_bucket)`.
- **Dải động:** bề rộng nở theo posterior đổi pha & run-length BOCPD (thay cho Hawkes ở dữ liệu EOD).
- **Đầu ra:** `(lower_band, upper_band, point_forecast)` tại $T+20$ đã hiệu chuẩn phủ.

---

## 2. Mô Hình Hóa Vi Cấu Trúc Thị Trường VN *(EXTEND, không code mới)*

Triệt tiêu Sharpe ảo bằng ràng buộc khớp lệnh thực tế — **tất cả dựng trên module có sẵn**:

- **Price Limits — gọi `VnMarketRules.calculate_price_limits(ref_price)`** (đã có tick-round, biên ±7% HOSE / ±10% phiên chào sàn):
  - Chiều **Mua**: `fill = 0` nếu `close ≥ ceiling_price` (bám trần → không mua đuổi).
  - Chiều **Bán**: `fill = 0` nếu `close ≤ floor_price` (kẹt sàn → không cắt được lỗ, giữ nguyên vị thế & cảnh báo).
- **ADV Cap:** khối lượng lệnh $\le 5\%\cdot ADV_{20d}$.
- **Slippage — hiệu chuẩn lại `TransactionCostModel`** (đã có nhánh market-impact `√`): thay slippage tuyến tính hiện tại bằng luật căn bậc hai có nền spread:
$$\text{Slippage(bps)} = \text{BaseSpread}_{\text{regime}} + \gamma\cdot\sqrt{\tfrac{V_{\text{order}}}{ADV_{20d}}}$$
  với `BaseSpread` phụ thuộc `liquidity_bucket` và `regime_state` (Risk-Off nới rộng). $\gamma$ hiệu chuẩn từ dữ liệu impact lịch sử.

---

## 3. Ý Tưởng Nghiên Cứu Đột Phá (đã lọc theo tính khả thi VN-EOD)

> Ký hiệu: 🆕 = xây mới · ♻️ = dùng hạ tầng sẵn có.

### A. 🆕 Fractional Differentiation cho đặc trưng Trend
Sai phân bậc 1 giết ký ức dài hạn. Tìm $d\in(0,1)$ tối thiểu để chuỗi vừa **dừng** (ADF/KPSS) vừa giữ **tự tương quan** cao nhất với gốc:
$$(1-B)^d = \sum_{k=0}^{\infty}(-1)^k\binom{d}{k}B^k$$
Dùng **fixed-width window** (cắt trọng số $|w_k|<\tau$) để tránh rò rỉ & giữ độ dài ổn định. Áp cho log-price, log-volume, RS. Module: `quant/features/frac_diff.py`.

### B. ♻️→🆕 Chuỗi sự kiện Trần/Sàn — BOCPD trước, Hawkes sau
Kẹt sàn/trần hàng loạt mang tính tự kích hoạt. **Ở EOD, ưu tiên `BOCPDDetector` (đã có)** trên chuỗi "tần suất chạm trần/sàn theo ngành" để phát hiện leo thang — rẻ, không cần timestamp nội phiên. **Chỉ khi có dữ liệu tick** mới nâng cấp lên Hawkes:
$$\lambda_i(t)=\mu_i+\sum_j \alpha_{ij}e^{-\beta_{ij}(t-t_j)}$$
Cường độ tăng → thu hẹp vị thế & nới stop. Module Hawkes (điều kiện): `quant/math/hawkes.py`.

### C. ♻️ Conformal Scaling thích ứng theo Regime & Run-length
Thay dải tĩnh bằng dải động, điều biến bởi **posterior HMM/GMM và run-length BOCPD** (đều đã có):
$$\text{BandWidth}_t = \text{BaseWidth}_t \times g\big(\text{RegimePosterior}_t,\ \ell_{\text{BOCPD},t}\big)$$
Đổi pha Bear hoặc run-length rơi mạnh → dải nở tự động, bảo vệ tài khoản trước cú sụt bất ngờ.

### D. 🆕 Liquidity-Trap Survival Model
Ước lượng số ngày tối thiểu thoát vị thế mục tiêu mà không tạo impact lớn, bằng Cox PH / Random Survival Forest:
$$h(t\mid X)=h_0(t)\exp(\beta^{\top}X)$$
Đồng biến $X$: tần suất kẹt sàn gần đây, tỷ lệ nắm giữ cổ đông lớn, z-score thanh khoản, `foreign_flow_z`. Đầu ra `expected_exit_days` → chặn mở vị thế nếu vượt ngưỡng. Module: `quant/models/liquidity_survival.py`.

### E. 🆕 Meta-Labeling (đề xuất mới — López de Prado)
Trên tín hiệu sơ cấp của ma trận 4 chiều, huấn luyện bộ phân loại nhị phân "nên đặt cược hay không" để **cắt false-positive và định cỡ** (bet-sizing theo xác suất). Đây là đòn bẩy precision rẻ nhất, ăn khớp trực tiếp với `strategy/` hiện có. Module: `quant/strategy/meta_labeler.py`.

### F. ♻️ Regime-Conditional Alpha Weighting qua Thompson Sampling
Dùng `quant/thompson_sampling.py` + `portfolio/thompson_sampling_overlay.py` để phân bổ trọng số alpha theo hiệu năng có điều kiện regime — khai thác trực tiếp `regime_state` từ Chiều 1.

---

## 4. Đặc Tả Kiến Trúc Triển Khai (Implementation Spec)

### 4.1 🆕 `ConformalTrendPredictor` — `src/omega/quant/models/conformal_predictor.py`

> Sửa lỗi Mondrian của spec cũ: conformal score tính **theo nhóm** `(regime × liquidity_bucket)`, không phải một quantile toàn cục.

```python
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor


class ConformalTrendPredictor:
    """CQR có Mondrian conformalization theo (regime × liquidity_bucket).

    Đảm bảo phủ ~ (1 - alpha) *có điều kiện* trong từng nhóm, thay vì chỉ
    phủ biên tế trung bình. Chống quantile-crossing và cho phép dải động.
    """

    def __init__(self, alpha: float = 0.20, min_group: int = 50):
        self.alpha = alpha
        self.min_group = min_group  # nhóm ít mẫu hơn -> gộp vào 'global'
        self.model_low = LGBMRegressor(objective="quantile", alpha=alpha / 2)
        self.model_high = LGBMRegressor(objective="quantile", alpha=1 - alpha / 2)
        self.cal_q_: dict = {}      # group_key -> conformal quantile
        self.global_q_: float = 0.0

    def fit(self, X_train, y_train, X_cal, y_cal, cal_groups: pd.Series):
        """cal_groups: Series khóa nhóm '<regime>|<liq_bucket>' căn theo X_cal."""
        self.model_low.fit(X_train, y_train)
        self.model_high.fit(X_train, y_train)

        p_low = self.model_low.predict(X_cal)
        p_high = self.model_high.predict(X_cal)
        # Nonconformity score CQR: độ lệch lớn nhất ra ngoài dải phân vị.
        scores = np.maximum(p_low - y_cal, y_cal - p_high)

        s = pd.Series(scores, index=cal_groups.index)
        self.global_q_ = float(np.quantile(scores, 1 - self.alpha))
        for g, idx in s.groupby(cal_groups).groups.items():
            grp = s.loc[idx].to_numpy()
            self.cal_q_[g] = (
                float(np.quantile(grp, 1 - self.alpha))
                if len(grp) >= self.min_group else self.global_q_
            )
        return self

    def predict_interval(self, X_test, test_groups: pd.Series):
        p_low = self.model_low.predict(X_test)
        p_high = self.model_high.predict(X_test)
        # Chống quantile-crossing.
        lo = np.minimum(p_low, p_high)
        hi = np.maximum(p_low, p_high)
        q = test_groups.map(self.cal_q_).fillna(self.global_q_).to_numpy()
        return lo - q, hi + q, 0.5 * (lo + hi)
```

### 4.2 EXTEND `SectorClassifier` — `src/omega/quant/portfolio/sector_classifier.py`

> Thêm 2 method vào lớp **đã có**. **Không** tạo `SectorRotationEngine` mới.

```python
def get_sector_mapping_pit(self, as_of: str) -> pd.DataFrame:
    """Ánh xạ ngành hiệu lực tại thời điểm as_of (chống look-ahead)."""
    query = """
        SELECT ticker, sector, effective_date
        FROM ticker_sectors
        WHERE effective_date <= ?
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY ticker ORDER BY effective_date DESC
        ) = 1
    """
    return pd.read_sql(query, self._conn, params=[as_of])

def compute_rs_ex_top3(self, panel: pd.DataFrame, as_of: str) -> pd.Series:
    """RS hiệu chỉnh loại 3 mã vốn hóa lớn nhất NGÀNH — xếp hạng trên
    lát cắt ngang tại t-1 (sửa lỗi shift theo mã của spec cũ)."""
    sectors = self.get_sector_mapping_pit(as_of)
    df = panel.merge(sectors, on="ticker", how="inner")

    # Breadth: MA50 đã shift(1) để không dùng giá hôm nay.
    df["ma50"] = df.groupby("ticker")["close"].transform(
        lambda x: x.rolling(50).mean().shift(1))
    df["above_ma50"] = (df["close"] > df["ma50"]).astype(int)

    # Xếp hạng vốn hóa trên CROSS-SECTION của ngày t-1 trong từng ngành.
    prev = df[df["date"] == df["date"].max()].copy()  # lát cắt as_of
    prev["mcap_rank"] = prev.groupby("sector")["market_cap"].rank(ascending=False)
    keep = prev.loc[prev["mcap_rank"] > 3, "ticker"]

    ex = df[df["ticker"].isin(keep)]
    perf_sector = ex.groupby("sector")["ret"].transform("mean")
    perf_index = df["ret_index"]
    return self._w1 * (df["ret"] - perf_index) + self._w2 * (df["ret"] - perf_sector)
```

### 4.3 EXTEND `TransactionCostModel` — `src/omega/quant/execution/transaction_cost.py`

> Thay **1 dòng** slippage tuyến tính bằng luật căn bậc hai + nền spread theo regime. Nhánh market-impact `√` đã có sẵn — giữ nguyên.

```python
# Trong estimate_cost(), thay khối "2. Slippage":
participation_rate = order_value / (adv_value + 1e-10)
base_spread_bps = self._base_spread_for(regime_state, liquidity_bucket)  # mới
slippage_bps = base_spread_bps + self.gamma * np.sqrt(participation_rate)
slippage = order_value * (slippage_bps / 10000)
```

### 4.4 WIRE Price-Limit Fill Guard — trong backtest engine

```python
from omega.core.vn_market_rules import VnMarketRules

def can_fill(side: str, close: float, ref_price: float) -> bool:
    floor, ceiling = VnMarketRules.calculate_price_limits(ref_price)
    if side == "BUY" and close >= ceiling:
        return False          # bám trần: không mua đuổi
    if side == "SELL" and close <= floor:
        return False          # kẹt sàn: không cắt được lỗ
    return True
```

### 4.5 🆕 Danh mục module mới (chỉ 5 file được phép tạo)
| File | Nội dung |
|---|---|
| `quant/models/conformal_predictor.py` | §4.1 CQR + Mondrian |
| `quant/features/frac_diff.py` | Ý tưởng A |
| `quant/models/liquidity_survival.py` | Ý tưởng D |
| `quant/strategy/meta_labeler.py` | Ý tưởng E |
| `quant/math/hawkes.py` *(điều kiện: chỉ khi có tick data)* | Ý tưởng B nâng cao |

---

## 5. Kế Hoạch Xác Minh Thống Kê (Verification Plan)

### 5.1 Bộ kiểm thử an toàn — `tests/test_decision_matrix_v2.py`
| # | Test | Khẳng định |
|---|---|---|
| 1 | `test_future_shuffle_invariance` | Xáo trộn tương lai VNINDEX → RS/z-score ngày $T$ bất biến (PIT-safe) |
| 2 | `test_sector_mapping_no_lookahead` | Đổi phân ngành lịch sử trong DB → `get_sector_mapping_pit` trả đúng ánh xạ as-of |
| 3 | `test_rs_ex_top3_cross_section` | RS loại đúng 3 mã vốn hóa lớn nhất *theo lát cắt ngang t-1* (chặn lỗi trục cũ) |
| 4 | `test_price_limit_buy_block` | Mua tại phiên bám trần → fill rate = 0% (dùng `VnMarketRules`) |
| 5 | `test_price_limit_sell_block` | Bán tại phiên sàn → fill rate = 0%, vị thế giữ nguyên + cảnh báo |
| 6 | `test_mondrian_conditional_coverage` | Phủ thực **trong từng nhóm** `(regime×liq)` ∈ $[78\%,86\%]$ (không chỉ biên tế) |
| 7 | `test_cqr_no_quantile_crossing` | `lower_band ≤ upper_band` trên toàn tập test |
| 8 | `test_embargo_isolation` | CPCV purge/embargo ≥ 200 ngày với nhãn $T+60$ (tái dùng `validation/cpcv.py`) |
| 9 | `test_fracdiff_stationarity_memory` | Chuỗi fracdiff qua ADF@5% và giữ corr với gốc $> 0.9$ |
| 10 | `test_pit_guardian_zero_violation` | `PITGuardian.check_target_leakage` = 0 vi phạm trên panel đầy đủ |

### 5.2 Chỉ số nghiệm thu (Success Gates) — bắt buộc đồng thời
- **DSR** (`validation/dsr.py`, OOS/CPCV) $> 0.95$.
- **MDD** giảm $\ge 15\%$ so với C3.
- **Tỷ lệ mua trúng đỉnh** giảm $\ge 20\%$ (tần suất chạm stop trước target của triple-barrier).
- **0 vi phạm PIT**; **0 fill** vi phạm price-limit trong backtest.
- **Coverage có điều kiện** đạt trong mọi nhóm Mondrian (test #6).

### 5.3 Lệnh kiểm chứng
```bash
pytest tests/test_decision_matrix_v2.py -q
python scripts/backtest_hybrid_regime.py --config decision_matrix_v2   # DSR/MDD/top-buy
python scripts/sod_gate_enforcer.py --check-before-push
```

---

## 6. Lộ Trình Thực Thi Theo Pha (mỗi bước có tiêu chí verify)

1. **P0 — Đấu nối tái dùng (không code mới):** WIRE Chiều 1 (HMM/GMM/BOCPD) + price-limit guard §4.4 → *verify:* test #4, #5 xanh; backtest chạy end-to-end.
2. **P1 — Sửa lỗi trục & PIT:** EXTEND SectorClassifier §4.2, publish-lag thực Chiều 2 → *verify:* test #1,#2,#3,#10.
3. **P2 — Conformal Chiều 4:** 🆕 `conformal_predictor.py` + WIRE nhãn triple-barrier → *verify:* test #6,#7,#8.
4. **P3 — Cost thực tế:** EXTEND `TransactionCostModel` §4.3 → *verify:* so sánh cost-curve vs baseline; Sharpe sụt hợp lý.
5. **P4 — Đột phá:** fracdiff (A) → meta-labeling (E) → survival (D) → *verify:* test #9; DSR/MDD gate §5.2.
6. **P5 — Điều kiện:** Hawkes (B) chỉ khi có tick data; Thompson weighting (F) → *verify:* ablation cải thiện dương.

**Thứ tự ưu tiên giá trị/chi phí:** P0→P1 (sửa rủi ro rò rỉ, chi phí thấp) trước P2→P4 (alpha mới). Không mở P4 nếu P1 chưa đạt 0 vi phạm PIT.

---

## 7. Rủi Ro & Giảm Thiểu
| Rủi ro | Giảm thiểu |
|---|---|
| Reinvent module đã có | Nguyên tắc reuse-first §0; chỉ 5 file 🆕 được duyệt |
| Hawkes thiếu dữ liệu tick | Mặc định BOCPD (đã có) ở EOD; Hawkes là nhánh điều kiện |
| Overfit khi thêm nhiều alpha | DSR phạt số phép thử; CPCV purge/embargo; meta-label lọc |
| Mondrian nhóm quá nhỏ | Fallback `global_q_` khi $n<$ `min_group` (§4.1) |
| Publish-lag sai lệch | Ưu tiên `publish_date` thực; fallback 45/90 ngày có ghi cột `fundamental_asof` |

---

*Hết kế hoạch v2.*

---

Bạn muốn tôi **ghi bản này ra file** (`implementation_plan_v2.md`) để bạn khỏi copy tay không? Nếu có, tôi sẽ tạo file ngay. Tôi giữ nguyên `implementation_plan.md` cũ để bạn đối chiếu.
