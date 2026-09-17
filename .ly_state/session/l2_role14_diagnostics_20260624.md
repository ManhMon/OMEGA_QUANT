# L2 Report: GMM Mismatch and Semantic Mapping Fix
**Role**: 14 (data-scientist) | **Platform**: OpenCode (Offline Edit) | **Gate**: HYBRID_REGIME_DIAGNOSTICS_20260624

## 1. Tóm tắt Vấn đề & Giải pháp
* **Vấn đề Train/Inference Mismatch**: GMM fit trên các điểm phân tán của từng symbol hằng ngày, nhưng lúc inference lại nhận vector trung bình theo ngày. Điều này làm mất phương sai và phân loại sai lệch hệ thống (100% Bear).
* **Giải pháp**: Sửa đổi `fit()` trong `latent_gmm.py` để huấn luyện trên daily mean. Sửa đổi `_map_regimes()` để mapping semantics (Bull, Sideways, Bear) dựa trên realized returns thực tế của từng cụm thay vì dùng norm heuristic.

## 2. Kiểm chứng & Kết quả
- Chạy unit test của GMM: PASSED.
- Đã đồng bộ test suite để đảm bảo test parity.

## 3. Bằng chứng Compliance
- **Repo-local role**: `.agents/agent/data-scientist.md`
- **Repo-local skills**:
  - `.agents/skills/quant-research/SKILL.md`
  - `.agents/skills/backtesting-pit-safety/SKILL.md`
  - `.agents/skills/data-science-workflow/SKILL.md`
- **Forbidden path scan**: Không sử dụng `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories` làm authoritative source.
