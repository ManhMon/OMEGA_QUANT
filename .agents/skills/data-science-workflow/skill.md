---
name: data-science-workflow
description: Data science workflow for OMEGA_QUANT. EDA, data quality assessment, experiment tracking, statistical tests, reproducibility protocols, and reporting standards for Vietnam equity quant research.
when_to_use: "When performing exploratory data analysis, validating data quality, running statistical tests, tracking experiments, or ensuring reproducibility in any OMEGA_QUANT data science task."
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

# Data Science Workflow — OMEGA_QUANT Research Standards

> Domain skill for rigorous, reproducible data science in quant research.
> **Every analysis must be reproducible, PIT-aware, and documented. Ad-hoc notebooks are not evidence.**

---

## 1. EDA (Exploratory Data Analysis) Protocol

### Before Any Modeling: Understand the Data

| Step | Action | Purpose |
|------|--------|---------|
| **1. Shape** | `df.shape`, `df.dtypes`, `df.info()` | Size, types, memory |
| **2. Missing** | `df.isnull().sum()`, `df.isnull().mean()` | Completeness assessment |
| **3. Distribution** | Histograms, KDE, box plots per column | Outlier detection |
| **4. Time coverage** | Date range, gaps, trading day alignment | Calendar validation |
| **5. Scale check** | Price magnitude (VND_FULL > 1000?) | VCI scale verification |
| **6. Correlations** | Cross-correlation matrix, rolling correlations | Feature relationships |
| **7. Stationarity** | ADF test, KPSS test on returns | Time-series properties |
| **8. Regime** | Visualize bull/bear/sideways periods | Regime-aware analysis |

### Vietnam-Specific EDA Checks

| Check | Expected | Flag If |
|-------|----------|---------|
| **Price scale** | close.max() > 1000 | VND_FULL not applied |
| **Trading days** | ~245-250 per year | Missing or extra days |
| **Volume profile** | Higher at open/close (ATO/ATC) | Unusual volume patterns |
| **Price limits** | Daily return within ±7% | Data errors or limit stocks |
| **Sector distribution** | All ICB L2 sectors represented | Missing sector assignments |
| **Exchange mix** | HOSE + HNX + UPCOM present | Single-exchange dataset |

### EDA Documentation Template

```markdown
## EDA Report: [Dataset Name]
- **Date range**: YYYY-MM-DD to YYYY-MM-DD
- **Universe**: N stocks (HOSE: X, HNX: Y, UPCOM: Z)
- **Missing data**: <column>: <% missing>
- **Scale**: VND_FULL verified (max close = XXXXX)
- **Trading days**: NNN (expected: ~NNN)
- **Key findings**: [bullet points]
- **Data quality issues**: [list or "none"]
```

---

## 2. Data Quality Assessment

### Quality Dimensions

| Dimension | Metric | Threshold |
|-----------|--------|-----------|
| **Completeness** | % non-null per column | > 95% for price/volume |
| **Accuracy** | OHLCV consistency checks | 100% pass rate |
| **Timeliness** | Data freshness (T+2 max) | < 3 days old |
| **Consistency** | No duplicate (date, symbol) | Zero duplicates |
| **Validity** | Price > 0, volume >= 0 | 100% valid |
| **Uniqueness** | Unique index on (date, symbol) | Enforced |

### Automated Quality Checks

| Check | Implementation |
|-------|---------------|
| **OHLCV invariant** | `high >= max(open, close)` AND `low <= min(open, close)` |
| **VND scale** | `ensure_vnd_scale()` verification |
| **Calendar alignment** | Trading days match `config/vn_holidays.json` |
| **PIT timestamp** | `as_of <= available_at` for all rows |
| **Volume sanity** | No negative volumes, no zero-volume trading days (unless suspended) |
| **Return bounds** | Daily return within ±7% (±10% for no-reference) |

### Data Quality Report

```markdown
## Data Quality Report: [Dataset]
- **Completeness**: X% (target: >95%)
- **OHLCV consistency**: N violations (target: 0)
- **VND scale**: Verified / NOT verified
- **PIT timestamps**: All valid / N violations
- **Calendar**: Aligned / N missing days
- **Duplicates**: 0 / N found
- **Action**: [PASS / NEEDS_FIX / REJECT]
```

---

## 3. Statistical Tests

### Tests for Quant Research

| Test | Purpose | OMEGA_QUANT Usage |
|------|---------|-------------------|
| **Spearman rank correlation** | IC computation (signal vs. forward return) | Primary alpha metric |
| **Pearson correlation** | Linear relationship strength | Secondary, outlier-sensitive |
| **t-test** | Mean IC != 0 | Statistical significance of alpha |
| **ADF test** | Stationarity of returns | Feature engineering input |
| **KPSS test** | Trend stationarity | Complement to ADF |
| **Kolmogorov-Smirnov** | Distribution comparison | Train vs. test distribution shift |
| **Mann-Whitney U** | Non-parametric group comparison | Regime-conditional IC comparison |
| **Bootstrap CI** | Confidence intervals for Sharpe/IC | Robust inference without normality |

### Multiple Testing Correction

| Method | When to Use |
|--------|-------------|
| **Bonferroni** | Small number of tests, conservative |
| **Benjamini-Hochberg (FDR)** | Many tests (e.g., screening 1000 features) |
| **Deflated Sharpe Ratio** | Adjusting for number of strategies tested |

### Test Reporting Standards

| Required Field | Example |
|---------------|---------|
| **Test name** | Spearman rank correlation |
| **Statistic** | rho = 0.035 |
| **p-value** | p = 0.002 |
| **Effect size** | IC = 0.035, IR = 0.62 |
| **Sample size** | N = 2500 trading days |
| **Multiple testing** | BH-FDR adjusted p = 0.008 |
| **Conclusion** | Statistically significant at alpha = 0.05 |

---

## 4. Experiment Tracking

### MLflow Integration

| Entity | What to Track |
|--------|--------------|
| **Run** | Single model training execution |
| **Parameters** | Hyperparameters, data config, universe, date range |
| **Metrics** | IC, IR, Sharpe, Sortino, max_drawdown, turnover |
| **Artifacts** | Model checkpoint, feature importance, equity curve |
| **Tags** | Regime, model type, experiment purpose |

### Experiment Naming Convention

```
{date}_{model}_{universe}_{purpose}
Example: 20260613_xgb_ranker_vn50_alpha_v33
```

### Experiment Log Requirements

- [ ] Every model training run logged in MLflow
- [ ] Parameters include: model type, hyperparameters, data range, universe
- [ ] Metrics include: train IC, val IC, OOS IC, Sharpe, max_drawdown
- [ ] Artifacts saved: model file, feature importance, config
- [ ] Tags include: regime, experiment type, researcher/role

### Reproducibility Checklist

- [ ] **Seeds**: `torch.manual_seed(42)`, `numpy.random.seed(42)`, `random.seed(42)`
- [ ] **Deterministic**: `torch.use_deterministic_algorithms(True)`
- [ ] **Environment**: Python version, package versions logged
- [ ] **Data version**: Parquet file hash or date-stamped filename
- [ ] **Config**: Full config YAML saved with run
- [ ] **Code version**: Git commit hash logged

---

## 5. Reproducibility Protocol

### The Reproducibility Standard

> **If another agent (or human) cannot reproduce your result from your saved artifacts, config, and code, the result does not exist.**

### Required for Every Analysis

| Artifact | Location | Content |
|----------|----------|---------|
| **Code** | `src/` or `scripts/` | Version-controlled Python |
| **Config** | `config/` | YAML configuration |
| **Data** | `data/*.parquet` | Versioned parquet files |
| **Results** | `.ly_state/session/` | Metrics, logs, outputs |
| **MLflow run** | MLflow tracking server | Full experiment record |

### Reproducibility Verification

| Check | Method |
|-------|--------|
| **Code reproduces** | Re-run script, compare output hash |
| **Data matches** | Parquet file hash matches recorded hash |
| **Seeds set** | Grep for `manual_seed`, `random.seed`, `np.random.seed` |
| **Deterministic** | `torch.use_deterministic_algorithms` present |
| **Config complete** | All parameters in config, no hardcoded magic numbers |
| **Environment** | `pip freeze` or conda environment.yml saved |

---

## 6. Analysis Reporting Standards

### Report Structure

```markdown
# Analysis Report: [Title]

## 1. Objective
What question are we answering?

## 2. Data
- Source: [VCI/local parquet]
- Universe: [N stocks, exchanges]
- Date range: [start to end]
- Quality: [pass/fail from quality report]

## 3. Methodology
- Features: [list with PIT safety notes]
- Model: [type, hyperparameters]
- Validation: [walk-forward/CPCV, embargo]
- Metrics: [IC, Sharpe, etc.]

## 4. Results
- IC: [mean ± std]
- Sharpe: [net of costs]
- Max drawdown: [%]
- Turnover: [%]

## 5. Statistical Significance
- Test: [name]
- Statistic: [value]
- p-value: [value]
- Multiple testing: [correction method]

## 6. Conclusion
[Actionable recommendation]

## 7. Reproducibility
- MLflow run: [run_id]
- Git commit: [hash]
- Data file: [parquet filename + hash]
```

---

## 7. Common Statistical Pitfalls

| Pitfall | Description | Prevention |
|---------|-------------|------------|
| **p-hacking** | Testing many hypotheses until one is significant | Pre-register hypotheses, apply FDR correction |
| **Data snooping** | Reusing same test set for multiple models | Fresh OOS period for final evaluation |
| **Survivorship bias** | Analyzing only surviving stocks | PIT universe with delistings |
| **Non-stationarity** | Assuming stable relationships over time | Regime-conditional analysis, rolling windows |
| **Small sample** | Drawing conclusions from < 100 observations | Minimum sample size requirements |
| **Correlation != causation** | Interpreting correlation as alpha | Economic rationale required for alpha hypothesis |
| **Overfitting** | Model memorizes training data | Walk-forward OOS, regularization, simplicity |

---

## 8. Verification Checklist

Before submitting any data science analysis:

- [ ] **EDA complete**: Shape, missing, distribution, scale, calendar documented
- [ ] **Data quality**: OHLCV consistency, VND scale, PIT timestamps verified
- [ ] **PIT-safe**: All features T-1 shifted, no look-ahead
- [ ] **Statistical tests**: Appropriate tests used, p-values reported with corrections
- [ ] **Experiment tracked**: MLflow run with parameters, metrics, artifacts
- [ ] **Reproducible**: Seeds set, config saved, code version-controlled
- [ ] **Report written**: Structured report with methodology, results, conclusion
- [ ] **Peer-reviewable**: Another role can independently verify results

---

## 9. Anti-Patterns

| Don't | Do |
|-------|-----|
| Skip EDA and go straight to modeling | EDA first — understand the data |
| Report only the best result | Report all results including failures |
| Ignore data quality issues | Document and address every quality flag |
| Use p < 0.05 without multiple testing correction | Apply BH-FDR or Bonferroni |
| Ad-hoc notebook without version control | Scripts in `src/` or `scripts/`, version-controlled |
| Hardcode parameters | Config YAML with all parameters |
| Forget to set seeds | Set all seeds at the top of every script |
| Analyze full sample then split | Split FIRST, analyze only train set |
| Assume stationarity | Test for stationarity, use rolling windows |
| Report gross metrics only | Always report net-of-cost metrics |

---

## 10. SOD/PIT Guardrails

| Guardrail | Rule |
|-----------|------|
| **PIT: in every analysis** | All time-series analysis respects `as_of <= available_at` |
| **PIT: EDA includes PIT check** | EDA protocol includes PIT timestamp verification |
| **SOD: analyst != approver** | Data scientist (L2) cannot approve own analysis for production |
| **SOD: Tier 3 audit** | Analysis submitted to Code Reviewer (role 21) + QA Engineer (role 17) |
| **SOD: evidence persisted** | All reports, metrics, logs in `.ly_state/session/` |
| **Reproducibility**: mandatory | Every result must be reproducible from saved artifacts |

---

> **Remember:** Good data science is reproducible data science. If you can't reproduce it, you can't trust it.
