I'll provide a comprehensive set of PIT-safe features for the Vietnam stock market, organized into the two requested groups.
Here's a comprehensive feature design for Vietnam stock market PIT-safe features:

## GROUP 1: NEWS AND SENTIMENT FEATURES (Nhóm tin tức, tâm lý)

| Feature Name | Mathematical Formula | PIT Safety Mechanism | Vietnam Market Rationale |
|:-------------|:---------------------|:---------------------|:-------------------------|
| **ViBERT_Sentiment_1D** | $S_t = \frac{1}{N_t} \sum_{i=1}^{N_t} \text{ViBERT}(\text{news}_i)$ where news published before market open on day $t$ | Use only news with `published_at < market_open_t`, index at t-1 for prediction at t | Vietnamese news often released after market hours; ViBERT trained on Vietnamese financial corpus captures local idioms ("cổ phiếu nóng", "dòng tiền") |
| **ViBERT_Sentiment_5D_Decay** | $S_{5D,t} = \sum_{i=0}^{4} \lambda^i \cdot S_{t-i}$ where $\lambda = 0.7$ (exponential decay) | Each $S_{t-i}$ uses only news available at $t-i-1$ | Retail-dominated market shows sentiment persistence; 5-day captures weekly cycle (Mon-Fri trading) |
| **ViBERT_Sentiment_20D_MA** | $S_{20D,t} = \frac{1}{20}\sum_{i=1}^{20} S_{t-i}$ | Rolling average using only past sentiment scores | 20-day captures monthly sentiment trend; Vietnamese retail investors follow monthly salary cycles |
| **News_Volume_Shock** | $V_t = \frac{N_t - \mu_{20D}}{\sigma_{20D}}$ where $N_t$ = count of news articles, $\mu_{20D}$, $\sigma_{20D}$ = 20-day mean/std | Count news with `published_at < t`, compute stats from [t-21, t-1] | Abnormal news volume precedes major moves; Vietnamese media amplifies during scandals (bond defaults, corporate fraud) |
| **ATC_Volume_Ratio** | $\text{ATC}_t = \frac{V_{\text{ATC},t}}{V_{\text{total},t}}$ (ATC = continuous matching at close) | Use only trading data from session t-1 | Vietnamese market has ATC session (14:30-14:45); high ATC ratio indicates institutional/informed positioning before close |
| **Morning_Gap** | $\text{Gap}_t = \frac{P_{\text{open},t} - P_{\text{close},t-1}}{P_{\text{close},t-1}}$ | Use $P_{\text{close},t-1}$ from previous day, $P_{\text{open},t}$ from current day | Vietnamese retail traders react to overnight news; morning gaps reflect sentiment shift from previous close |
| **Volume_Trend_Shock** | $\text{VTS}_t = \frac{V_t - \text{MA}_{20}(V)_{t-1}}{\text{Std}_{20}(V)_{t-1}}$ | Compute MA and Std from [t-21, t-1], compare to $V_t$ | Sudden volume spikes indicate retail FOMO or institutional accumulation; common in Vietnamese penny stocks |
| **Intraday_Volatility_Morning** | $\sigma_{\text{morning},t} = \text{Std}(R_{\text{5min}})$ for 9:00-11:30 session | Use only intraday returns from morning session of day t-1 for prediction at t | Vietnamese market has AM (9:00-11:30) and PM (13:00-14:45) sessions; morning volatility reflects overnight sentiment |
| **Foreign_Net_Flow_5D** | $\text{FNF}_{5D,t} = \sum_{i=1}^{5} (\text{Foreign}_{\text{buy},t-i} - \text{Foreign}_{\text{sell},t-i})$ | Sum foreign flow from [t-5, t-1] | Foreign investors (20-25% free float) are informed; 5-day flow captures institutional positioning; HSX publishes daily foreign trading data |
| **Retail_Sentiment_Proxy** | $\text{RSP}_t = \frac{V_{\text{odd-lot},t-1}}{V_{\text{total},t-1}}$ (odd-lot = <100 shares) | Use trading data from t-1 | Vietnamese retail traders dominate odd-lot trading; high ratio indicates retail euphoria (contrarian signal) |

---

## GROUP 2: FUNDAMENTAL METRICS FEATURES (Nhóm chỉ số cơ bản doanh nghiệp)

| Feature Name | Mathematical Formula | PIT Safety Mechanism | Vietnam Market Rationale |
|:-------------|:---------------------|:---------------------|:-------------------------|
| **PE_Ratio_PIT** | $\text{PE}_t = \frac{P_t}{\text{EPS}_{\text{latest}}}$ where $\text{EPS}_{\text{latest}}$ = most recent published EPS | Use `as_of_date` from financial filings; only update on `available_at` date | Vietnamese firms report quarterly (within 30 days of quarter-end); PIT mapping prevents look-ahead; captures valuation vs. market |
| **PB_Ratio_PIT** | $\text{PB}_t = \frac{P_t}{\text{BVPS}_{\text{latest}}}$ where $\text{BVPS} = \frac{\text{Book Equity}}{\text{Shares Outstanding}}$ | Use book value from most recent available filing | Vietnamese banks/real estate trade at P/B premium; retail investors focus on "cheap" P/B stocks |
| **EV_EBITDA_PIT** | $\text{EV/EBITDA}_t = \frac{\text{Market Cap}_t + \text{Debt} - \text{Cash}}{\text{EBITDA}_{\text{TTM}}}$ | Debt/Cash from latest balance sheet; EBITDA trailing-twelve-months from latest 4 quarters | More robust than P/E for Vietnamese manufacturing/infrastructure firms with high leverage |
| **ROE_PIT** | $\text{ROE}_t = \frac{\text{Net Income}_{\text{TTM}}}{\text{Equity}_{\text{latest}}}$ | TTM net income from latest 4 available quarters | Vietnamese investors favor high-ROE stocks (>15%); banks/consumer stocks show persistent ROE |
| **Debt_to_Equity_PIT** | $\text{D/E}_t = \frac{\text{Total Debt}_{\text{latest}}}{\text{Total Equity}_{\text{latest}}}$ | Use most recent balance sheet with `as_of_date <= t` | Vietnamese firms (esp. real estate) often highly leveraged; D/E spike precedes distress |
| **Earnings_Growth_YoY** | $\text{EG}_t = \frac{\text{EPS}_{Q,t} - \text{EPS}_{Q,t-4}}{\|\text{EPS}_{Q,t-4}\|}$ (Q = quarter) | Use earnings from same quarter last year, only if both reports available by date t | Vietnamese market rewards growth stocks; YoY removes seasonality (Tet holiday effects in Q1) |
| **Earnings_Growth_QoQ** | $\text{EG}_{\text{QoQ},t} = \frac{\text{EPS}_{Q,t} - \text{EPS}_{Q-1,t}}{\|\text{EPS}_{Q-1,t}\|}$ | Use sequential quarters, both available by date t | Detects acceleration/deceleration; Vietnamese cyclical stocks (steel, construction) show strong QoQ trends |
| **Price_to_Sales_PIT** | $\text{P/S}_t = \frac{\text{Market Cap}_t}{\text{Revenue}_{\text{TTM}}}$ | Revenue TTM from latest 4 available quarters | Alternative to P/E for loss-making growth stocks (tech, biotech) in Vietnamese market |
| **Dividend_Yield_PIT** | $\text{DY}_t = \frac{\text{Div}_{\text{announced}}}{\text{P}_t}$ where Div = most recent dividend announcement | Use only dividends with `ex_date <= t` and `announced_date < t` | Vietnamese firms pay annual dividends (often in Q2); retail investors chase high-yield stocks (7-10%) |
| **Asset_Turnover_PIT** | $\text{AT}_t = \frac{\text{Revenue}_{\text{TTM}}}{\text{Total Assets}_{\text{latest}}}$ | Revenue TTM, assets from latest balance sheet | Measures efficiency; Vietnamese retail/manufacturing firms with high turnover outperform |
| **Current_Ratio_PIT** | $\text{CR}_t = \frac{\text{Current Assets}_{\text{latest}}}{\text{Current Liabilities}_{\text{latest}}}$ | Use most recent balance sheet | Liquidity indicator; Vietnamese firms with CR < 1 face refinancing risk (bond market stress 2022-2023) |
| **Market_to_Fundamental_Drift** | $\text{MTF}_t = \frac{P_t / P_{t-20}}{\text{EPS}_{\text{TTM},t} / \text{EPS}_{\text{TTM},t-1}}$ | Price change vs. earnings change; ensure both EPS reports available | Detects price momentum decoupled from fundamentals; Vietnamese retail speculation causes drift |
| **Accruals_Quality** | $\text{Accruals}_t = \frac{\text{Net Income}_{\text{TTM}} - \text{CFO}_{\text{TTM}}}{\text{Total Assets}_{\text{latest}}}$ | Net income and cash-from-operations from latest reports | High accruals = earnings quality risk; Vietnamese firms (real estate) inflate earnings via receivables |
| **Financial_Report_Lag** | $\text{Lag}_t = t - \text{available\_at}_{\text{latest}}$ (days since last report) | Direct calculation from filing metadata | Vietnamese firms with long lags (>45 days) often have accounting issues; stale data = higher uncertainty |
| **ROA_PIT** | $\text{ROA}_t = \frac{\text{Net Income}_{\text{TTM}}}{\text{Total Assets}_{\text{latest}}}$ | TTM net income, latest assets | Asset-heavy Vietnamese firms (utilities, infrastructure) judged on ROA vs. ROE |

---

## PIT SAFETY ENFORCEMENT RULES

1. **Temporal Alignment**: All features at time `t` use only data with `timestamp < t` or `available_at < t`
2. **As-of Mapping**: Fundamental data uses `as_of_date` (reporting period) but only accessible after `available_at` (publication date)
3. **T-1 Lag**: For prediction at day `t`, all features computed using data up to `t-1` close
4. **No Intraday Look-ahead**: Intraday features (morning gap, ATC ratio) computed only after session close
5. **Quarterly Staleness**: Vietnamese firms report within 30 days of quarter-end; features may be stale for up to 30 days
6. **News Indexing**: News sentiment indexed by `published_at`, not `crawled_at` or `scraped_at`

All features are designed for the OMEGA_QUANT V21 framework with strict PIT compliance under AGENTS.md Section 17 SOD enforcement.

[0m
> build · kr/claude-sonnet-4.5
[0m
[0m# [0mTodos
[•] Design News and Sentiment Group features with formulas
[ ] Design Fundamental Metrics Group features with formulas
[ ] Document PIT safety mechanisms for each feature
[0m
[0m# [0mTodos
[✓] Design News and Sentiment Group features with formulas
[•] Design Fundamental Metrics Group features with formulas
[ ] Document PIT safety mechanisms for each feature
[ ] Create comprehensive markdown table with all features
[0m
[0m# [0mTodos
[✓] Design News and Sentiment Group features with formulas
[✓] Design Fundamental Metrics Group features with formulas
[✓] Document PIT safety mechanisms for each feature
[✓] Create comprehensive markdown table with all features
[0m
