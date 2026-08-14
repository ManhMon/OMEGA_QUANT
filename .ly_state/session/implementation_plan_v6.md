# Kế hoạch thiết kế v6: Pipeline Dữ liệu Vĩ mô & Tối ưu hóa Alpha Cảm xúc (Phase 26)

**Remediation v6**: Sửa 1 blocking finding từ Codex plan audit v5.

---

## Resolved Findings (v2 → v3)

> [!IMPORTANT]
> **Finding v2-1 (CRITICAL): Synthetic CPI publication date.**
> GSO `published_at = day 29` là inferred, không phải actual release timestamp.
> **Fix v3**: **Loại bỏ CPI hoàn toàn** khỏi macro pipeline. Chỉ giữ 3 nguồn có source-provided timestamps:
> - **SBV Interest Rates** (API trả `announcement_date` thực tế)
> - **SBV Interbank Rates** (API trả `date` thực tế)
> - **Yahoo Finance USD/VND** (Unix timestamp thực tế từ market close)
>
> CPI sẽ chỉ được thêm lại khi có nguồn API cung cấp machine-readable `published_at` thực tế.

> [!IMPORTANT]
> **Finding v2-2 (HIGH): Append-only persistence unspecified.**
> `run()` ghi đè Parquet file, không bảo toàn vintages giữa các lần chạy.
> **Fix v3**: Triển khai persistence protocol rõ ràng:
> ```python
> def run(self, output_path):
>     new_records = self.fetch()
>     # Within-fetch dedup: raise on conflicting rows (same revision_id, different value)
>     if new_records["revision_id"].duplicated().any():
>         dupes = new_records[new_records["revision_id"].duplicated(keep=False)]
>         conflicts = dupes.groupby("revision_id")["value"].nunique()
>         if (conflicts > 1).any():
>             raise ValueError(f"Conflicting revision_ids within fetch: {conflicts[conflicts>1].index.tolist()}")
>         new_records = new_records.drop_duplicates(subset=["revision_id"], keep="first")
>     if output_path.exists():
>         existing = pd.read_parquet(output_path)
>         # Chỉ append records có revision_id chưa tồn tại
>         seen_ids = set(existing["revision_id"])
>         unseen = new_records[~new_records["revision_id"].isin(seen_ids)]
>         combined = pd.concat([existing, unseen], ignore_index=True)
>     else:
>         combined = new_records
>     # Atomic write: write to tmp → rename
>     tmp_path = output_path.with_suffix(".tmp.parquet")
>     combined.to_parquet(tmp_path, index=False)
>     tmp_path.replace(output_path)
>     return combined
> ```
> **As-of selection API**:
> ```python
> @staticmethod
> def query_as_of(parquet_path, as_of_date):
>     """Return only vintages ingested on or before as_of_date."""
>     df = pd.read_parquet(parquet_path)
>     # Timezone-safe: localize naive, convert aware
>     ts = pd.Timestamp(as_of_date)
>     if ts.tzinfo is None:
>         ts = ts.tz_localize("Asia/Ho_Chi_Minh")
>     else:
>         ts = ts.tz_convert("Asia/Ho_Chi_Minh")
>     return df[df["ingested_at"] <= ts]
> ```

> [!IMPORTANT]
> **Finding v2-3 (HIGH): revision_id contract contradicts itself.**
> Python `hash()` is process-randomized, non-monotonic, collision-prone.
> **Fix v3**: Dùng **SHA-256 deterministic digest** thay vì `hash()`:
> ```python
> import hashlib
> def _revision_id(indicator, observation_date, value, source):
>     key = f"{indicator}|{observation_date}|{value}|{source}"
>     return hashlib.sha256(key.encode()).hexdigest()[:16]
> ```
> `revision_id` là content-addressable identifier (giống git blob hash), **không phải** monotonically increasing sequence. Schema contract sửa lại: `revision_id` là deterministic hex digest, unique per content tuple.

> [!WARNING]
> **Finding v2-4 (HIGH): Holiday calendar fails open after 2027.**
> Hard-coded 2015-2027 silently classifies unknown future holidays as tradable.
> **Fix v3**: `next_tradable_session()` **raise `ValueError`** nếu ngày nằm ngoài khoảng supported `[2015-01-01, 2027-12-31]`:
> ```python
> SUPPORTED_RANGE = (pd.Timestamp("2015-01-01"), pd.Timestamp("2027-12-31"))
>
> def next_tradable_session(date, holidays):
>     if date < SUPPORTED_RANGE[0] or date > SUPPORTED_RANGE[1]:
>         raise ValueError(f"Date {date} outside supported calendar range {SUPPORTED_RANGE}")
>     candidate = date
>     while candidate.weekday() >= 5 or candidate in holidays:
>         candidate += timedelta(days=1)
>         if candidate > SUPPORTED_RANGE[1]:
>             raise ValueError(f"No tradable session found within supported range")
>     return candidate
> ```
> Test case bổ sung: ngày `2028-01-01` → `ValueError`.

> [!WARNING]
> **Finding v2-5 (MEDIUM): Decay ceiling ambiguous.**
> "Cap age at 90" vs "age > 90 → contribution 0" là behavior khác nhau.
> **Fix v3**: Spec chính xác bằng vectorized masking:
> ```python
> MAX_AGE_DAYS = 90
> # Step 1: Validate ORIGINAL input values before any reindex/fillna
> if isinstance(sentiment_age_days, pd.Series):
>     # Reject explicit NaN — do NOT allow dropna to hide them
>     if sentiment_age_days.isna().any():
>         raise ValueError("sentiment_age_days contains NaN values")
>     if (sentiment_age_days < 0).any() or not np.all(np.isfinite(sentiment_age_days)):
>         raise ValueError("sentiment_age_days must be finite and non-negative")
>     if sentiment_age_days.index.has_duplicates:
>         raise ValueError("sentiment_age_days must have unique index")
> else:  # scalar
>     if not math.isfinite(sentiment_age_days) or sentiment_age_days < 0:
>         raise ValueError("sentiment_age_days must be finite and non-negative")
>     sentiment_age_days = pd.Series(sentiment_age_days, index=all_symbols)
> # Step 2: Reindex to all_symbols, fill ONLY newly missing symbols
> age = sentiment_age_days.reindex(all_symbols).fillna(MAX_AGE_DAYS)
> decay_factor = np.exp(-self.sentiment_decay * age.to_numpy(dtype=float))
> # Hard mask: age >= MAX_AGE_DAYS → contribution = 0.0 (not decayed)
> decay_factor = np.where(age.to_numpy() >= MAX_AGE_DAYS, 0.0, decay_factor)
> ```
> - `age = 89` → `decay_factor = exp(-λ*89)` (normal decay)
> - `age = 90` → `decay_factor = 0.0` (hard cutoff)
> - Missing symbol → `age = MAX_AGE_DAYS` → `decay_factor = 0.0` → uses `default_score`
> - Duplicate index → raise `ValueError("sentiment_age_days must have unique index")`

> [!NOTE]
> **Finding v2-6 (MEDIUM): sentiment_decay non-finite accepted.**
> `>= 0` doesn't reject `NaN`; `+inf` yields invalid behavior.
> **Fix v3**: Validate in `__init__`:
> ```python
> import math
> if not math.isfinite(sentiment_decay) or sentiment_decay < 0:
>     raise ValueError("sentiment_decay must be finite and non-negative")
> if not math.isfinite(sentiment_scale):
>     raise ValueError("sentiment_scale must be finite")
> ```
> Test cases: `NaN` → `ValueError`, `+inf` → `ValueError`, `-inf` → `ValueError`, `-0.1` → `ValueError`.

---

## Final Scope (v3)

### [Component: Macro Data Pipeline]

#### [MODIFY] [macro_pipeline.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/data/macro_pipeline.py)

**Schema** (8 columns):
```python
SCHEMA = [
    "indicator", "value", "observation_date", "published_at",
    "available_at", "ingested_at", "revision_id", "source",
]
```

**Data sources** (3 only — all provide source timestamps):
```python
DEFAULT_URLS = {
    "sbv_rate": "https://www.sbv.gov.vn/api/interest-rates",
    "interbank_rate": "https://www.sbv.gov.vn/api/interbank-rates",
    "usd_vnd": "https://query1.finance.yahoo.com/v8/finance/chart/USDVND=X",
}
# NO World Bank. NO GSO CPI (no machine-readable published_at).
```

**Key changes**:
1. Remove World Bank CPI URL. Remove GSO CPI.
2. Add `observation_date` (the period the data covers) separate from `published_at` (when source published it).
3. `available_at = next_tradable_session(published_at + 1 day, hose_holidays)`.
4. `next_tradable_session()` raises `ValueError` outside `[2015-01-01, 2027-12-31]`.
5. `ingested_at = pd.Timestamp.now(tz='Asia/Ho_Chi_Minh')`.
6. `revision_id = hashlib.sha256(content_key).hexdigest()[:16]`.
7. Append-only persistence: read existing → append unseen → atomic replace.
8. `query_as_of(path, date)` selection API.
9. Validate: `observation_date <= published_at < available_at`.
10. No `drop_duplicates`. All vintages preserved.

#### [MODIFY] [test_macro_pipeline.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/test_macro_pipeline.py)

Adversarial test cases:
- `published_at` on Saturday → `available_at` jumps to Monday.
- `published_at` on 2024-04-29 (before 30/4 holiday) → `available_at` jumps past holiday.
- Same indicator+observation_date, different value → both kept with different `revision_id`.
- Vintage isolation: `query_as_of(cutoff)` returns only records with `ingested_at <= cutoff`.
- Year-only date payload (World Bank style) → `ValueError`.
- Date outside `[2015, 2027]` → `ValueError`.
- Append-only: second `run()` call doesn't duplicate existing records.

---

### [Component: Sentiment Alpha Optimization]

#### [MODIFY] [sentiment_alpha.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/signal/sentiment_alpha.py)

**Key changes**:
1. `__init__`: `math.isfinite(sentiment_decay) and sentiment_decay >= 0`. `math.isfinite(sentiment_scale)`. Raise `ValueError` on NaN/inf/-inf/negative.
2. `_validate_pit`: Add `as_of <= available_at`. Full ordering: `as_of <= available_at < timestamp`.
3. `sentiment_age_days`: Accept **both scalar `float` and `pd.Series`** (backward compatible). If scalar → broadcast to all symbols via `pd.Series(scalar, index=all_symbols)`. If Series → validate unique index, reindex to `all_symbols`, `fillna(MAX_AGE_DAYS)`. Both paths: validate finite, non-negative.
4. Hard mask: `age >= 90` → `decay_factor = 0.0` via `np.where`.
5. `article_counts`: Validate finite (`np.isfinite`), non-negative.
6. Sector neutralization on `adjustment` only:
   ```python
   adjustment = clamped * scale * decay_factor * volume_scale
   if sectors:
       sector_series = pd.Series(sectors).reindex(all_symbols).fillna("Unclassified")
       adjustment = adjustment - adjustment.groupby(sector_series).transform("mean")
   combined = base_signals + adjustment
   ```
7. Sort result by index for deterministic output.

#### [MODIFY] [test_sentiment_alpha_opt.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/test_sentiment_alpha_opt.py)

Adversarial test cases:
- `sentiment_decay = NaN` → `ValueError`.
- `sentiment_decay = +inf` → `ValueError`.
- `sentiment_decay = -inf` → `ValueError`.
- `sentiment_decay = -0.1` → `ValueError`.
- `sentiment_decay = 0` → no decay applied.
- `sentiment_age_days` as `pd.Series` with per-symbol ages.
- `sentiment_age_days` with `age = 89` → nonzero decay. `age = 90` → contribution 0.
- `sentiment_age_days` with NaN → `ValueError`.
- `sentiment_age_days` with duplicate index → `ValueError`.
- `article_counts` with NaN → `ValueError`.
- `article_counts` with `-1` → `ValueError`.
- `as_of > available_at` → `ValueError`.
- Sector neutralization: verify `base_signal` values unchanged (only adjustment is demeaned).

---

## Verification Plan

### Automated Tests
```powershell
python -m pytest tests/test_macro_pipeline.py tests/test_sentiment_alpha_opt.py -v
```

### SoD Enforcer
```powershell
python scripts/sod_gate_enforcer.py
```

---

## Dispatch Identity Evidence

- **L2 Role**: 15 `data-engineer` (role_id=15, tier=2, platform=OpenCode)
- **L3 Role**: 20 `compliance-officer` (role_id=20, tier=3, platform=Codex)
- **Writer ≠ Auditor**: 15 ≠ 20 ✅
- **Gate**: `macro_and_sentiment_alpha_v3_20260808`

## Lessons Learned Applied

1. **[macro_and_sentiment_alpha_v1_20260808]**: Store immutable vintage snapshots; enforce `as_of <= available_at` and non-negative decay.
2. **[VCI_KBS_WARNING_ONLY_RECONCILIATION_20260802]**: Filter future rows before validation.
3. **[news_collection_remediation_v10_fix4]**: Implement atomic write-and-replace.
