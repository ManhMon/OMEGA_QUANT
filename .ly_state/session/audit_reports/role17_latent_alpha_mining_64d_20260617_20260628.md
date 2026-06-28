# QA Audit Report

**Role**: QA Engineer (Role 17) — Tier 3 Independent Audit
**Date**: 2026-06-28
**Gate**: LATENT_ALPHA_MINING_64D_20260617
**L2 Session**: l2_role14_reconstruct_latent_alphas_2015_now_20260628
**L2 Role**: 14 data-scientist
**L3 Session**: l3_role17_reconstruct_latent_alphas_2015_now_20260628
**Scope under audit**: `scripts/reconstruct_latent_components_all.py`, `tests/phase35/test_reconstruct_latent_components_all.py`, `data/latent_alphas_components.parquet`

---

## Repo-Local Skill Source Evidence

- Role file read: `.agents/agent/qa-engineer.md`
- Skill files read:
  - `.agents/skills/verify-changes/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`
  - `.agents/skills/audit-cycle/SKILL.md`
  - (`webapp-testing` not applicable — no web/UI surface in this gate)

## Forbidden Path Scan

- No authoritative reliance on forbidden paths.
- Non-authoritative only (not used as source of authority): `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, `.codex\memories`.

---

## Audit Evidence Checklist

### 1. Writer != Auditor (SOD separation)
- L2 `l2_role_id = 14` (data-scientist); L3 `l3_role_id = 17` (qa-engineer). **14 ≠ 17 — verified.**
- Distinct from the sibling code-reviewer L3 (`role_id = 21`). Independent QA perspective maintained.
- **PASS.**

### 2. Code changes vs approved scope
- The task checklist references `implementation_plan.md`. That document describes the **Hybrid GMM-BOCPD** feature set (`bocpd.py`, `latent_gmm.py`, `drawdown_control.py`, `risk_sizing.py`, `test_pipeline_v2.py`) and **does not govern** the reconstruction script under audit. The authoritative scope for this gate is the L2 report (`.ly_state/session/l2_role14_reconstruct_latent_alphas_2015_now_20260628.md`).
- Against that L2-declared scope, `scripts/reconstruct_latent_components_all.py` does exactly what it claims: loads `data/market_2015_now.parquet`, selects top-104 by cumulative windowed volume, builds a full-range feature parquet, and reuses `run_latent_alpha_mining(method="autoencoder", n_components=16)` to overwrite `data/latent_alphas_components.parquet`. Behavior matches the docstring and L2 narrative.
- **Caveat (non-blocking for QA mandate):** the mining call additionally rewrites `data/latent_alphas_model.pkl`, `data/latent_alphas_metrics.json`, `data/features_advanced_top104_2015_2026.parquet`, and `.ly_state/session/latent_alphas_report_20260617.md`. These are intrinsic, expected by-products of a latent-alpha-mining run and were transparently declared in the L2 "Files Touched" list. The sibling L3 (role 21) treats this as a **blocking scope violation** under a stricter code-review interpretation. From the QA functional mandate this is a process/scope-definition concern, not a functional or PIT defect. See "Relationship to Role 21" below.
- **PASS (functional scope) with documented scope caveat.**

### 3. Focused tests — `tests/phase35/test_reconstruct_latent_components_all.py`
- **Execution limitation (disclosed):** `python`/`pytest` invocations are gated in this audit session and were auto-denied; only `git` is ungated. I could **not** execute the suite myself. Evidence below is from static verification + prior independent execution.
- **Static trace of `test_select_top_liquid_tickers_uses_requested_window_and_ranking`:**
  - Fixture rows: `OLD@2014-12-31 vol 10000` (outside window), `AAA@2015-01-05=100`, `BBB@2015-01-05=500`, `AAA@2016-01-05=200`, `BBB@2016-01-05=300`.
  - Window `[2015-01-01, 2016-12-31]` excludes `OLD`. Grouped sums: `BBB = 800`, `AAA = 300`. Descending sort → `['BBB','AAA']`; `head(2)` → `['BBB','AAA']`. Matches asserted `['BBB','AAA']`.
  - Function logic (`date.between` → `groupby("ticker")["volume"].sum()` → `sort_values(ascending=False)` → `head(top_n)`) corresponds exactly to the assertion. **Trace passes.**
- **Corroborating execution evidence:** the prior independent L3 (role 21) recorded `pytest -q tests/phase35/test_reconstruct_latent_components_all.py -> PASS`, and the L2 report records `1 passed`.
- **PASS** (static trace + two independent prior execution records; not self-executed this session).

### 4. PIT safety
- Universe ranking (`select_top_liquid_tickers`) operates only on rows inside the requested date window.
- Per-symbol `returns` via `pct_change()` (trailing) and `adv_vnd` via `rolling(20, min_periods=5).mean()` (trailing) — no forward leakage.
- Latent mining reuses the train-only fit / frozen OOS projection path in `mine_latent_alphas.py` (chronological split; forward returns not used in projection). Confirmed consistent with the L2 report PIT section and the role-21 PIT review (which found no look-ahead in the new path).
- **Caveats (non-blocking, research-grade notes):**
  - *Universe-selection look-ahead:* `select_top_liquid_tickers` sums volume across the **entire** 2015–2026 window to choose the top-104, so the universe is defined using end-of-window liquidity. This is a standard "top-liquid-names" reconstruction convention but is a mild selection look-ahead; it does not affect the PIT-critical mining fit/projection. Worth noting for any downstream backtest that consumes this universe.
  - *Metadata loss:* generated parquets drop `as_of`/`available_at`; downstream applies T-1 lag separately (same caveat role 21 raised — a design limitation, not a new defect).
- **PASS** with documented research caveats.

### 5. `latent_ae_11` — research-justified selection vs typo
- `latent_ae_11` is a **real** component (Component Index 11) present in the rebuilt 16-column AE output, and is consumed by `latent_gmm.py` alongside `latent_ae_00` and `latent_ae_01`.
- Per `.ly_state/session/latent_alphas_report_20260617.md`, `latent_ae_11`: OOS IC −0.2445, **OOS IR −1.3532**, Turnover 0.1441, **IC/IR/TO gates all PASS**, OOS/IS decay 0.9456 (stable). It ranks **#5 of 16** by `|OOS IR|` and is among the 13 components passing all gates.
- **Correction to the task framing:** the checklist describes `latent_ae_11` as "top component by IR." That is inaccurate — the top component by `|OOS IR|` is `latent_ae_10` (IR −2.3282); `latent_ae_11` is rank 5. However, it **is** a strong, gate-passing, top-tier component and is clearly **not a typo**.
- **PASS** — selection is research-justified (real, gate-passing component); the "top component" wording is corrected above.

---

## Test Results Summary

- [x] Functional requirements met (script reconstructs full-range latent components; selection function behaves per spec)
- [x] Edge cases handled (out-of-window rows excluded; `min_periods` guards rolling ADV)
- [x] Focused regression test passes (static trace + 2 prior execution records)
- [x] PIT safety verified for the mining path (train-only fit, frozen projection, trailing features)
- [x] `latent_ae_11` confirmed a real, gate-passing component (not a typo)

## Defects / Findings

1. **(Non-blocking, scope)** Reconstruction run rewrites four artifacts beyond the named 3-file scope (`*_model.pkl`, `*_metrics.json`, `features_advanced_top104_2015_2026.parquet`, `latent_alphas_report_20260617.md`). Intrinsic mining outputs, declared in L2. Recommend the operator reconcile the gate's scope definition to explicitly include these mining by-products (or have L2 suppress the auxiliary writes) to remove ambiguity. This is the same observation role 21 graded as blocking under a stricter mandate.
2. **(Non-blocking, research caveat)** Universe selection uses full-window cumulative volume (mild selection look-ahead). Acceptable for a reconstruction artifact; flag for downstream backtest consumers.
3. **(Documentation)** Task framing's "top component by IR" for `latent_ae_11` is inaccurate (it is rank 5/16); selection remains valid.

## Limitations of This Audit

- Focused test was **not self-executed** (pytest gated this session). Verdict relies on static trace + prior independent execution evidence (role 21 + L2). Recommend a fresh `pytest tests/phase35/test_reconstruct_latent_components_all.py` run in an ungated environment to close this gap.

## Relationship to Role 21 (sibling L3)

- Role 21 (code-reviewer) recorded `[NEEDS_FIX]` in `phase_gates.json`, driven by (a) the extra-artifact scope interpretation and (b) the full `pytest -q` suite having 7 pre-existing/unrelated failures (missing baseline/hybrid-regime artifacts, an `AttributeError` in `scripts/backtest_hybrid_regime.py`) — failures unrelated to the code under audit and outside this QA checklist (which mandates **focused** tests).
- This QA audit operates on a narrower, functional mandate (focused tests, PIT, `latent_ae_11` justification, writer/auditor separation) and reaches an independent conclusion on that mandate.
- **`phase_gates.json` is intentionally left unmodified** per the task directive (avoid conflicting with the Codex/role-21 record). This report is advisory and stands alongside role 21's gate entry; the operator/L1 should reconcile the two mandates before final gate disposition.

---

## Verdict

**[APPROVED]** — for the QA functional mandate: the reconstruction script and its focused test are functionally correct, the mining path is PIT-safe, and `latent_ae_11` is a verified, gate-passing, research-justified component (not a typo).

This approval is **scoped and conditional**, with these explicit caveats: (1) the focused test was verified statically + via prior independent execution, not self-executed this session; (2) the extra-artifact scope concern raised by role 21 is real and should be reconciled at the gate-definition level; (3) `phase_gates.json` remains untouched and role 21's `[NEEDS_FIX]` stands of record. The operator should reconcile the differing L3 mandates before final gate sign-off.
