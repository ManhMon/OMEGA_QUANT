# VCI canonical / KBS reconciliation

VCI từ vnstock là nguồn OHLCV canonical duy nhất. KBS từ vnstock chỉ đối chiếu; không thể chặn, sửa, hoặc ghi đè dữ liệu VCI. Thay thế thiết kế verifier dựa trên HSX/HNX official bundle.

## Policy đã chốt

- Giá `open/high/low/close`: mismatch khi `abs(vci-kbs) > max(1 VND, 0.001 * abs(vci))`; equality là match.
- Volume: chỉ khi `vci_volume > 0`; mismatch khi `abs(vci-kbs) / vci > 0.01`; equality là match. VCI volume bằng 0: provider warning, không chia 0.
- Chỉ compare daily raw/unadjusted rows đã chuẩn hoá `VND_FULL`. Không compare adjusted series.
- KBS fetch error, empty, missing ticker/date, duplicate ticker/date, schema-invalid: warning finding; VCI vẫn publish. Tất cả exception từ KBS fetch, reconciliation, state/artifact write bị catch tại boundary; không thay VCI eligibility, terminal status, exit code, hoặc publication.
- State key `(ticker, field)`. KBS warning không reset/tăng streak; chỉ một valid exact ticker/date comparison mới cập nhật state. Mismatch tại session VCI kế tiếp tăng streak; match reset streak về 0. `critical` tại streak 3; valid match ở session VCI kế tiếp hạ thành `warning`. KBS failure sau critical giữ critical cũ nhưng xuất warning availability; không auto-recover.
- Session kế tiếp lấy từ thứ tự trading dates có trong canonical VCI của ticker, không theo calendar. Nếu canonical VCI có gap, reset streak, không suy đoán continuity.
- KBS rows có `trading_date > as_of_date` bị loại trước compare/state; exact ticker/date only. Không backfill, không dùng future KBS rows.
- Dashboard aggregate theo exchange + ticker/field drill-down. Reconciliation alert không là circuit breaker.

## Proposed changes

### Provider client + pure reconciliation

#### [MODIFY] [vnstock_client.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/src/omega/data/vnstock_client.py)

- Dùng client hiện hữu với `source="VCI"` và `source="KBS"`; không tạo alias KBS giả.
- Chuẩn hoá history cho hai nguồn về date/OHLCV `VND_FULL`; validate one row/ticker/date trước compare.

#### [NEW] `src/omega/data/provider_reconciliation.py`

- Pure functions/dataclasses nhận VCI/KBS frames và prior state; trả summary/findings/next state.
- Payload exact: `schema_version`, `as_of_date`, `provider_primary="vnstock_vci"`, `provider_reference="vnstock_kbs"`, `status`, `aggregate_by_exchange`, `findings`.
- Finding: ticker, exchange, trading_date, field, VCI/KBS value nullable, absolute/relative diff nullable, tolerance, severity, `consecutive_mismatch_sessions`, reason.
- Deterministic finding order. Không I/O, không network.

---

### Canonical updater + dashboard artifact

#### [MODIFY] [update_market_data.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/update_market_data.py)

- Sau VCI fetch/validation, fetch KBS best-effort cùng ticker/date. KBS boundary fail-open độc lập với VCI release/publish.
- Persist reconciliation state/latest JSON atomically vào `.ly_state/session/`; nếu write fail log warning, retain VCI result. Output paths injectable cho tests.
- Đính kèm best-effort summary vào updater projection; không đổi 14-column canonical schema hoặc `source="vnstock_vci"`.

#### [MODIFY] [update_dashboard_portfolio.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/update_dashboard_portfolio.py)

- Merge `market_data_reconciliation` latest artifact vào `risk_status.json`; preserve current signal/monitoring merge contract.

#### [MODIFY] [2_🛡️_Risk.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/apps/dashboard/pages/2_%F0%9F%9B%A1%EF%B8%8F_Risk.py)

- Thêm Market Data Health card, exchange aggregate, ticker/field findings table. Critical/warning rõ ràng. Không set `breached` hay sửa circuit-breaker section.

---

### Tests

#### [NEW] `tests/test_provider_reconciliation.py`

- Exact price/volume boundaries; invalid/missing/duplicate schema; VND_FULL.
- Three consecutive observed VCI sessions escalate; valid matching next VCI session recovers; KBS failures hold state; canonical VCI gap resets streak.
- PIT: KBS future row bị drop; mutation/addition KBS future không đổi output/state earlier.

#### [MODIFY] [test_vci_updater_validation_write_blocker.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/test_vci_updater_validation_write_blocker.py) and [test_dashboard_portfolio_sync.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/tests/test_dashboard_portfolio_sync.py)

- Mock KBS mismatch, outage, reconciliation/state write exceptions; prove VCI publication eligibility/status/exit path unchanged and canonical schema/source unchanged.
- Prove risk payload keeps aggregate + drill-down, without altering existing monitoring merge semantics.

## Verification

- `python -m pytest tests/test_provider_reconciliation.py tests/test_vci_updater_validation_write_blocker.py tests/test_dashboard_portfolio_sync.py -q`
- Mocked dry-run: KBS mismatch/outage and artifact-write failure yield warnings; VCI remains publish-eligible.
- Streamlit Risk page loads `risk_status.json` with aggregate and drill-down; circuit breaker stays unchanged.

> [!IMPORTANT]
> Implementation only after Codex `cx/gpt-5.6-sol` approves this plan, then L2 Role 15 implements and L3 Role 20 independently audits.
