# Latent Alpha Mining Report — LATENT_ALPHA_MINING_64D_20260617

**Role**: 14 (data-scientist) L2 — implementation only, no self-approval
**Timestamp**: 2026-06-17T13:16:30.185814+00:00
**Seed**: 42
**Elapsed**: 31.9s

## 1. Configuration

| Parameter | Value |
|-----------|-------|
| Method | PCA |
| N Components | 64 |
| N Features (input) | 114 |
| Train Ratio | 0.6 |
| Train Dates | 363 |
| Test Dates (OOS) | 242 |
| Features Hash | `a80c73af5a08195c` |
| Features Path | `C:\Users\GHC\repos\OMEGA_QUANT\data\features_advanced_sim.parquet` |

## 2. Vietnam Market Parameters

| Parameter | Value |
|-----------|-------|
| Round-trip cost | 27.0 bps |
| Trading days/year | 248 |
| IC min threshold | 0.02 |
| IR min threshold | 0.3 |
| Turnover max | 0.3 |

## 3. PIT Safety Verification

- [x] Features are T-1 lagged in source parquet (pre-computed)
- [x] Cross-sectional standardization uses only same-date data
- [x] PCA/ICA fit on TRAINING window only (chronological split)
- [x] OOS projection uses frozen model (no re-fit on test)
- [x] Forward returns (labels) NOT used in projection
- [x] No look-ahead bias in any pipeline step

## 4. Summary

| Metric | Value |
|--------|-------|
| Components evaluated | 64 |
| Pass all gates | 7 |
| Pass IC gate (|net_IC| >= 0.02) | 41 |
| Pass IR gate (|IR| >= 0.3) | 7 |
| Best OOS IR | 2.4419 |
| Best OOS IC | 0.586766 |

## 5. Ranked Latent Alphas (by |OOS IR|)

| Rank | Component | Method | OOS IC | OOS IR | Net IC | Turnover | IC Gate | IR Gate | TO Gate | OOS/IS Decay |
|------|-----------|--------|--------|--------|--------|----------|---------|---------|---------|--------------|
| 1 | latent_pca_10 | PCA | 0.5868 | 2.4419 | 0.5860 | 0.2671 | PASS | PASS | PASS | 1.083 |
| 2 | latent_pca_08 | PCA | 0.4102 | 1.3371 | 0.4097 | 0.2057 | PASS | PASS | PASS | 1.0377 |
| 3 | latent_pca_09 | PCA | -0.3809 | -1.1489 | -0.3817 | 0.2832 | PASS | PASS | PASS | 1.1381 |
| 4 | latent_pca_13 | PCA | 0.2080 | 0.5936 | 0.2074 | 0.1998 | PASS | PASS | PASS | 0.9693 |
| 5 | latent_pca_18 | PCA | 0.1387 | 0.3947 | 0.1380 | 0.2390 | PASS | PASS | PASS | 3.6152 |
| 6 | latent_pca_14 | PCA | -0.1070 | -0.3364 | -0.1077 | 0.2548 | PASS | PASS | PASS | 1.6589 |
| 7 | latent_pca_28 | PCA | 0.1060 | 0.3257 | 0.1054 | 0.2361 | PASS | PASS | PASS | 1.1523 |
| 8 | latent_pca_21 | PCA | -0.1025 | -0.2867 | -0.1032 | 0.2572 | PASS | FAIL | PASS | 0.8566 |
| 9 | latent_pca_50 | PCA | -0.0916 | -0.2642 | -0.0923 | 0.2484 | PASS | FAIL | PASS | 1.5373 |
| 10 | latent_pca_11 | PCA | 0.0919 | 0.2588 | 0.0915 | 0.1297 | PASS | FAIL | PASS | 1.1417 |
| 11 | latent_pca_23 | PCA | -0.0829 | -0.2423 | -0.0835 | 0.2313 | PASS | FAIL | PASS | 1.6387 |
| 12 | latent_pca_05 | PCA | -0.0729 | -0.2103 | -0.0735 | 0.2264 | PASS | FAIL | PASS | 1.3642 |
| 13 | latent_pca_53 | PCA | 0.0746 | 0.2045 | 0.0739 | 0.2419 | PASS | FAIL | PASS | 632.1441 |
| 14 | latent_pca_63 | PCA | -0.0732 | -0.2038 | -0.0737 | 0.1749 | PASS | FAIL | PASS | 1.4861 |
| 15 | latent_pca_07 | PCA | 0.0721 | 0.1909 | 0.0713 | 0.3143 | PASS | FAIL | FAIL | 0.735 |
| 16 | latent_pca_44 | PCA | 0.0627 | 0.1841 | 0.0621 | 0.2524 | PASS | FAIL | PASS | 4.1138 |
| 17 | latent_pca_33 | PCA | -0.0579 | -0.1715 | -0.0587 | 0.2951 | PASS | FAIL | PASS | 7.1399 |
| 18 | latent_pca_52 | PCA | 0.0562 | 0.1564 | 0.0556 | 0.2415 | PASS | FAIL | PASS | 1.5021 |
| 19 | latent_pca_48 | PCA | -0.0552 | -0.1524 | -0.0559 | 0.2715 | PASS | FAIL | PASS | 0.5072 |
| 20 | latent_pca_40 | PCA | -0.0554 | -0.1492 | -0.0561 | 0.2741 | PASS | FAIL | PASS | 31.5464 |
| 21 | latent_pca_16 | PCA | 0.0501 | 0.1464 | 0.0494 | 0.2492 | PASS | FAIL | PASS | 0.6534 |
| 22 | latent_pca_41 | PCA | -0.0509 | -0.1459 | -0.0517 | 0.2879 | PASS | FAIL | PASS | 3.3943 |
| 23 | latent_pca_37 | PCA | -0.0506 | -0.1307 | -0.0512 | 0.2227 | PASS | FAIL | PASS | 4.6177 |
| 24 | latent_pca_36 | PCA | -0.0421 | -0.1191 | -0.0428 | 0.2425 | PASS | FAIL | PASS | 1.4668 |
| 25 | latent_pca_46 | PCA | 0.0404 | 0.1161 | 0.0396 | 0.2674 | PASS | FAIL | PASS | 2.2009 |
| 26 | latent_pca_27 | PCA | -0.0384 | -0.1144 | -0.0390 | 0.2344 | PASS | FAIL | PASS | 0.5692 |
| 27 | latent_pca_19 | PCA | 0.0402 | 0.1124 | 0.0398 | 0.1713 | PASS | FAIL | PASS | 1.2743 |
| 28 | latent_pca_04 | PCA | 0.0388 | 0.1122 | 0.0381 | 0.2385 | PASS | FAIL | PASS | 0.8236 |
| 29 | latent_pca_32 | PCA | -0.0373 | -0.1069 | -0.0379 | 0.2546 | PASS | FAIL | PASS | 3.0663 |
| 30 | latent_pca_12 | PCA | -0.0364 | -0.0987 | -0.0374 | 0.3378 | PASS | FAIL | FAIL | 7.0225 |
| 31 | latent_pca_29 | PCA | 0.0356 | 0.0969 | 0.0349 | 0.2446 | PASS | FAIL | PASS | 1.0808 |
| 32 | latent_pca_15 | PCA | -0.0348 | -0.0937 | -0.0356 | 0.2990 | PASS | FAIL | PASS | 1.9339 |
| 33 | latent_pca_17 | PCA | -0.0279 | -0.0786 | -0.0286 | 0.2579 | PASS | FAIL | PASS | 0.7627 |
| 34 | latent_pca_25 | PCA | 0.0275 | 0.0774 | 0.0269 | 0.2399 | PASS | FAIL | PASS | 1.0048 |
| 35 | latent_pca_20 | PCA | 0.0264 | 0.0755 | 0.0258 | 0.2106 | PASS | FAIL | PASS | 0.6627 |
| 36 | latent_pca_03 | PCA | 0.0276 | 0.0742 | 0.0270 | 0.2033 | PASS | FAIL | PASS | 2.109 |
| 37 | latent_pca_24 | PCA | 0.0241 | 0.0685 | 0.0236 | 0.1977 | PASS | FAIL | PASS | 0.6019 |
| 38 | latent_pca_56 | PCA | -0.0218 | -0.0637 | -0.0225 | 0.2789 | PASS | FAIL | PASS | 11.56 |
| 39 | latent_pca_30 | PCA | 0.0219 | 0.0634 | 0.0212 | 0.2812 | PASS | FAIL | PASS | 0.4118 |
| 40 | latent_pca_06 | PCA | 0.0219 | 0.0626 | 0.0217 | 0.0963 | PASS | FAIL | PASS | 4.0591 |
| 41 | latent_pca_55 | PCA | -0.0211 | -0.0564 | -0.0215 | 0.1405 | PASS | FAIL | PASS | 2.3252 |
| 42 | latent_pca_47 | PCA | -0.0189 | -0.0496 | -0.0195 | 0.2032 | FAIL | FAIL | PASS | 0.9461 |
| 43 | latent_pca_59 | PCA | 0.0165 | 0.0471 | 0.0161 | 0.1289 | FAIL | FAIL | PASS | 3.1121 |
| 44 | latent_pca_49 | PCA | -0.0169 | -0.0455 | -0.0175 | 0.2253 | FAIL | FAIL | PASS | 0.5567 |
| 45 | latent_pca_57 | PCA | -0.0173 | -0.0437 | -0.0177 | 0.1422 | FAIL | FAIL | PASS | 0.6966 |
| 46 | latent_pca_26 | PCA | 0.0155 | 0.0401 | 0.0149 | 0.2388 | FAIL | FAIL | PASS | 0.4594 |
| 47 | latent_pca_31 | PCA | 0.0124 | 0.0343 | 0.0118 | 0.2255 | FAIL | FAIL | PASS | 0.4 |
| 48 | latent_pca_62 | PCA | 0.0117 | 0.0324 | 0.0113 | 0.1496 | FAIL | FAIL | PASS | 1.2702 |
| 49 | latent_pca_39 | PCA | -0.0121 | -0.0323 | -0.0127 | 0.2354 | FAIL | FAIL | PASS | 0.6059 |
| 50 | latent_pca_60 | PCA | 0.0104 | 0.0295 | 0.0098 | 0.2008 | FAIL | FAIL | PASS | 0.1745 |
| 51 | latent_pca_43 | PCA | -0.0095 | -0.0279 | -0.0101 | 0.1941 | FAIL | FAIL | PASS | 0.7404 |
| 52 | latent_pca_02 | PCA | 0.0100 | 0.0265 | 0.0094 | 0.2205 | FAIL | FAIL | PASS | 0.5461 |
| 53 | latent_pca_54 | PCA | -0.0080 | -0.0232 | -0.0085 | 0.2074 | FAIL | FAIL | PASS | 0.3346 |
| 54 | latent_pca_00 | PCA | -0.0096 | -0.0221 | -0.0099 | 0.1095 | FAIL | FAIL | PASS | 0.3796 |
| 55 | latent_pca_58 | PCA | -0.0063 | -0.0169 | -0.0069 | 0.2320 | FAIL | FAIL | PASS | 0.0764 |
| 56 | latent_pca_22 | PCA | 0.0052 | 0.0150 | 0.0045 | 0.2428 | FAIL | FAIL | PASS | 0.368 |
| 57 | latent_pca_61 | PCA | -0.0050 | -0.0140 | -0.0056 | 0.1887 | FAIL | FAIL | PASS | 0.0909 |
| 58 | latent_pca_34 | PCA | -0.0044 | -0.0123 | -0.0051 | 0.2348 | FAIL | FAIL | PASS | 0.2153 |
| 59 | latent_pca_51 | PCA | 0.0040 | 0.0112 | 0.0033 | 0.2334 | FAIL | FAIL | PASS | 0.1514 |
| 60 | latent_pca_45 | PCA | 0.0033 | 0.0091 | 0.0026 | 0.2573 | FAIL | FAIL | PASS | 0.2457 |
| 61 | latent_pca_35 | PCA | 0.0028 | 0.0085 | 0.0022 | 0.2287 | FAIL | FAIL | PASS | 0.1336 |
| 62 | latent_pca_01 | PCA | -0.0020 | -0.0048 | -0.0022 | 0.0510 | FAIL | FAIL | PASS | 0.1189 |
| 63 | latent_pca_38 | PCA | 0.0015 | 0.0043 | 0.0009 | 0.2207 | FAIL | FAIL | PASS | 0.872 |
| 64 | latent_pca_42 | PCA | -0.0011 | -0.0030 | -0.0017 | 0.2196 | FAIL | FAIL | PASS | 0.0764 |

## 6. Detailed Metrics per Component

### latent_pca_10

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 10 |
| OOS IC Mean | 0.586766 |
| OOS IC Std | 0.240291 |
| OOS IR | 2.4419 |
| IC Positive Rate | 0.9752 |
| IC t-stat | 37.987 |
| N Dates (OOS) | 242 |
| Turnover | 0.2671 |
| Net IC (cost-adj) | 0.586045 |
| Train IC Mean | 0.541793 |
| Train IR | 2.2063 |
| OOS/IS Decay Ratio | 1.083 |

### latent_pca_08

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 8 |
| OOS IC Mean | 0.410245 |
| OOS IC Std | 0.306811 |
| OOS IR | 1.3371 |
| IC Positive Rate | 0.8884 |
| IC t-stat | 20.8008 |
| N Dates (OOS) | 242 |
| Turnover | 0.2057 |
| Net IC (cost-adj) | 0.40969 |
| Train IC Mean | 0.395358 |
| Train IR | 1.3517 |
| OOS/IS Decay Ratio | 1.0377 |

### latent_pca_09

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 9 |
| OOS IC Mean | -0.380942 |
| OOS IC Std | 0.33157 |
| OOS IR | -1.1489 |
| IC Positive Rate | 0.1322 |
| IC t-stat | -17.8728 |
| N Dates (OOS) | 242 |
| Turnover | 0.2832 |
| Net IC (cost-adj) | -0.381707 |
| Train IC Mean | -0.334719 |
| Train IR | -0.9956 |
| OOS/IS Decay Ratio | 1.1381 |

### latent_pca_13

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 13 |
| OOS IC Mean | 0.207954 |
| OOS IC Std | 0.350311 |
| OOS IR | 0.5936 |
| IC Positive Rate | 0.7231 |
| IC t-stat | 9.2347 |
| N Dates (OOS) | 242 |
| Turnover | 0.1998 |
| Net IC (cost-adj) | 0.207415 |
| Train IC Mean | 0.21454 |
| Train IR | 0.6475 |
| OOS/IS Decay Ratio | 0.9693 |

### latent_pca_18

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 18 |
| OOS IC Mean | 0.138666 |
| OOS IC Std | 0.351332 |
| OOS IR | 0.3947 |
| IC Positive Rate | 0.624 |
| IC t-stat | 6.1399 |
| N Dates (OOS) | 242 |
| Turnover | 0.239 |
| Net IC (cost-adj) | 0.138021 |
| Train IC Mean | 0.038356 |
| Train IR | 0.1168 |
| OOS/IS Decay Ratio | 3.6152 |

### latent_pca_14

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 14 |
| OOS IC Mean | -0.10699 |
| OOS IC Std | 0.318002 |
| OOS IR | -0.3364 |
| IC Positive Rate | 0.3719 |
| IC t-stat | -5.2339 |
| N Dates (OOS) | 242 |
| Turnover | 0.2548 |
| Net IC (cost-adj) | -0.107678 |
| Train IC Mean | -0.064496 |
| Train IR | -0.1969 |
| OOS/IS Decay Ratio | 1.6589 |

### latent_pca_28

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 28 |
| OOS IC Mean | 0.105996 |
| OOS IC Std | 0.325409 |
| OOS IR | 0.3257 |
| IC Positive Rate | 0.6529 |
| IC t-stat | 5.0672 |
| N Dates (OOS) | 242 |
| Turnover | 0.2361 |
| Net IC (cost-adj) | 0.105359 |
| Train IC Mean | 0.091985 |
| Train IR | 0.2721 |
| OOS/IS Decay Ratio | 1.1523 |

### latent_pca_21

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 21 |
| OOS IC Mean | -0.102526 |
| OOS IC Std | 0.35759 |
| OOS IR | -0.2867 |
| IC Positive Rate | 0.376 |
| IC t-stat | -4.4602 |
| N Dates (OOS) | 242 |
| Turnover | 0.2572 |
| Net IC (cost-adj) | -0.10322 |
| Train IC Mean | -0.119683 |
| Train IR | -0.3317 |
| OOS/IS Decay Ratio | 0.8566 |

### latent_pca_50

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 50 |
| OOS IC Mean | -0.091619 |
| OOS IC Std | 0.346842 |
| OOS IR | -0.2642 |
| IC Positive Rate | 0.3843 |
| IC t-stat | -4.1092 |
| N Dates (OOS) | 242 |
| Turnover | 0.2484 |
| Net IC (cost-adj) | -0.09229 |
| Train IC Mean | -0.059598 |
| Train IR | -0.1723 |
| OOS/IS Decay Ratio | 1.5373 |

### latent_pca_11

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 11 |
| OOS IC Mean | 0.091853 |
| OOS IC Std | 0.354861 |
| OOS IR | 0.2588 |
| IC Positive Rate | 0.595 |
| IC t-stat | 4.0266 |
| N Dates (OOS) | 242 |
| Turnover | 0.1297 |
| Net IC (cost-adj) | 0.091503 |
| Train IC Mean | 0.080452 |
| Train IR | 0.2267 |
| OOS/IS Decay Ratio | 1.1417 |

### latent_pca_23

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 23 |
| OOS IC Mean | -0.082906 |
| OOS IC Std | 0.342199 |
| OOS IR | -0.2423 |
| IC Positive Rate | 0.3967 |
| IC t-stat | -3.7689 |
| N Dates (OOS) | 242 |
| Turnover | 0.2313 |
| Net IC (cost-adj) | -0.08353 |
| Train IC Mean | -0.050593 |
| Train IR | -0.1473 |
| OOS/IS Decay Ratio | 1.6387 |

### latent_pca_05

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 5 |
| OOS IC Mean | -0.072852 |
| OOS IC Std | 0.346378 |
| OOS IR | -0.2103 |
| IC Positive Rate | 0.405 |
| IC t-stat | -3.2719 |
| N Dates (OOS) | 242 |
| Turnover | 0.2264 |
| Net IC (cost-adj) | -0.073463 |
| Train IC Mean | -0.053404 |
| Train IR | -0.1523 |
| OOS/IS Decay Ratio | 1.3642 |

### latent_pca_53

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 53 |
| OOS IC Mean | 0.074593 |
| OOS IC Std | 0.364695 |
| OOS IR | 0.2045 |
| IC Positive Rate | 0.5702 |
| IC t-stat | 3.1818 |
| N Dates (OOS) | 242 |
| Turnover | 0.2419 |
| Net IC (cost-adj) | 0.07394 |
| Train IC Mean | 0.000118 |
| Train IR | 0.0003 |
| OOS/IS Decay Ratio | 632.1441 |

### latent_pca_63

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 63 |
| OOS IC Mean | -0.073249 |
| OOS IC Std | 0.359347 |
| OOS IR | -0.2038 |
| IC Positive Rate | 0.3926 |
| IC t-stat | -3.171 |
| N Dates (OOS) | 242 |
| Turnover | 0.1749 |
| Net IC (cost-adj) | -0.073721 |
| Train IC Mean | -0.049288 |
| Train IR | -0.1381 |
| OOS/IS Decay Ratio | 1.4861 |

### latent_pca_07

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 7 |
| OOS IC Mean | 0.072113 |
| OOS IC Std | 0.37777 |
| OOS IR | 0.1909 |
| IC Positive Rate | 0.562 |
| IC t-stat | 2.9696 |
| N Dates (OOS) | 242 |
| Turnover | 0.3143 |
| Net IC (cost-adj) | 0.071264 |
| Train IC Mean | 0.098116 |
| Train IR | 0.2933 |
| OOS/IS Decay Ratio | 0.735 |

### latent_pca_44

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 44 |
| OOS IC Mean | 0.06274 |
| OOS IC Std | 0.340752 |
| OOS IR | 0.1841 |
| IC Positive Rate | 0.5744 |
| IC t-stat | 2.8643 |
| N Dates (OOS) | 242 |
| Turnover | 0.2524 |
| Net IC (cost-adj) | 0.062058 |
| Train IC Mean | -0.015251 |
| Train IR | -0.0459 |
| OOS/IS Decay Ratio | 4.1138 |

### latent_pca_33

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 33 |
| OOS IC Mean | -0.05789 |
| OOS IC Std | 0.337495 |
| OOS IR | -0.1715 |
| IC Positive Rate | 0.4256 |
| IC t-stat | -2.6684 |
| N Dates (OOS) | 242 |
| Turnover | 0.2951 |
| Net IC (cost-adj) | -0.058687 |
| Train IC Mean | -0.008108 |
| Train IR | -0.0245 |
| OOS/IS Decay Ratio | 7.1399 |

### latent_pca_52

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 52 |
| OOS IC Mean | 0.05622 |
| OOS IC Std | 0.359471 |
| OOS IR | 0.1564 |
| IC Positive Rate | 0.5537 |
| IC t-stat | 2.433 |
| N Dates (OOS) | 242 |
| Turnover | 0.2415 |
| Net IC (cost-adj) | 0.055568 |
| Train IC Mean | 0.037427 |
| Train IR | 0.1023 |
| OOS/IS Decay Ratio | 1.5021 |

### latent_pca_48

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 48 |
| OOS IC Mean | -0.055161 |
| OOS IC Std | 0.362045 |
| OOS IR | -0.1524 |
| IC Positive Rate | 0.438 |
| IC t-stat | -2.3701 |
| N Dates (OOS) | 242 |
| Turnover | 0.2715 |
| Net IC (cost-adj) | -0.055894 |
| Train IC Mean | -0.108751 |
| Train IR | -0.294 |
| OOS/IS Decay Ratio | 0.5072 |

### latent_pca_40

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 40 |
| OOS IC Mean | -0.055364 |
| OOS IC Std | 0.371151 |
| OOS IR | -0.1492 |
| IC Positive Rate | 0.4463 |
| IC t-stat | -2.3205 |
| N Dates (OOS) | 242 |
| Turnover | 0.2741 |
| Net IC (cost-adj) | -0.056104 |
| Train IC Mean | -0.001755 |
| Train IR | -0.0049 |
| OOS/IS Decay Ratio | 31.5464 |

### latent_pca_16

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 16 |
| OOS IC Mean | 0.050077 |
| OOS IC Std | 0.341979 |
| OOS IR | 0.1464 |
| IC Positive Rate | 0.5785 |
| IC t-stat | 2.2779 |
| N Dates (OOS) | 242 |
| Turnover | 0.2492 |
| Net IC (cost-adj) | 0.049404 |
| Train IC Mean | 0.076641 |
| Train IR | 0.2207 |
| OOS/IS Decay Ratio | 0.6534 |

### latent_pca_41

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 41 |
| OOS IC Mean | -0.050921 |
| OOS IC Std | 0.348924 |
| OOS IR | -0.1459 |
| IC Positive Rate | 0.405 |
| IC t-stat | -2.2702 |
| N Dates (OOS) | 242 |
| Turnover | 0.2879 |
| Net IC (cost-adj) | -0.051698 |
| Train IC Mean | -0.015002 |
| Train IR | -0.0427 |
| OOS/IS Decay Ratio | 3.3943 |

### latent_pca_37

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 37 |
| OOS IC Mean | -0.050633 |
| OOS IC Std | 0.387454 |
| OOS IR | -0.1307 |
| IC Positive Rate | 0.4504 |
| IC t-stat | -2.0329 |
| N Dates (OOS) | 242 |
| Turnover | 0.2227 |
| Net IC (cost-adj) | -0.051234 |
| Train IC Mean | -0.010965 |
| Train IR | -0.0315 |
| OOS/IS Decay Ratio | 4.6177 |

### latent_pca_36

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 36 |
| OOS IC Mean | -0.042132 |
| OOS IC Std | 0.353682 |
| OOS IR | -0.1191 |
| IC Positive Rate | 0.4628 |
| IC t-stat | -1.8532 |
| N Dates (OOS) | 242 |
| Turnover | 0.2425 |
| Net IC (cost-adj) | -0.042787 |
| Train IC Mean | -0.028724 |
| Train IR | -0.0848 |
| OOS/IS Decay Ratio | 1.4668 |

### latent_pca_46

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 46 |
| OOS IC Mean | 0.040354 |
| OOS IC Std | 0.347666 |
| OOS IR | 0.1161 |
| IC Positive Rate | 0.5413 |
| IC t-stat | 1.8056 |
| N Dates (OOS) | 242 |
| Turnover | 0.2674 |
| Net IC (cost-adj) | 0.039632 |
| Train IC Mean | 0.018335 |
| Train IR | 0.0499 |
| OOS/IS Decay Ratio | 2.2009 |

### latent_pca_27

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 27 |
| OOS IC Mean | -0.038357 |
| OOS IC Std | 0.33542 |
| OOS IR | -0.1144 |
| IC Positive Rate | 0.4587 |
| IC t-stat | -1.7789 |
| N Dates (OOS) | 242 |
| Turnover | 0.2344 |
| Net IC (cost-adj) | -0.03899 |
| Train IC Mean | -0.067388 |
| Train IR | -0.1973 |
| OOS/IS Decay Ratio | 0.5692 |

### latent_pca_19

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 19 |
| OOS IC Mean | 0.040243 |
| OOS IC Std | 0.358154 |
| OOS IR | 0.1124 |
| IC Positive Rate | 0.5207 |
| IC t-stat | 1.7479 |
| N Dates (OOS) | 242 |
| Turnover | 0.1713 |
| Net IC (cost-adj) | 0.039781 |
| Train IC Mean | 0.03158 |
| Train IR | 0.0854 |
| OOS/IS Decay Ratio | 1.2743 |

### latent_pca_04

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 4 |
| OOS IC Mean | 0.038767 |
| OOS IC Std | 0.34553 |
| OOS IR | 0.1122 |
| IC Positive Rate | 0.5207 |
| IC t-stat | 1.7454 |
| N Dates (OOS) | 242 |
| Turnover | 0.2385 |
| Net IC (cost-adj) | 0.038123 |
| Train IC Mean | 0.047068 |
| Train IR | 0.1281 |
| OOS/IS Decay Ratio | 0.8236 |

### latent_pca_32

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 32 |
| OOS IC Mean | -0.037259 |
| OOS IC Std | 0.348559 |
| OOS IR | -0.1069 |
| IC Positive Rate | 0.4421 |
| IC t-stat | -1.6629 |
| N Dates (OOS) | 242 |
| Turnover | 0.2546 |
| Net IC (cost-adj) | -0.037946 |
| Train IC Mean | 0.012151 |
| Train IR | 0.0355 |
| OOS/IS Decay Ratio | 3.0663 |

### latent_pca_12

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 12 |
| OOS IC Mean | -0.036447 |
| OOS IC Std | 0.369193 |
| OOS IR | -0.0987 |
| IC Positive Rate | 0.4711 |
| IC t-stat | -1.5357 |
| N Dates (OOS) | 242 |
| Turnover | 0.3378 |
| Net IC (cost-adj) | -0.037359 |
| Train IC Mean | -0.00519 |
| Train IR | -0.014 |
| OOS/IS Decay Ratio | 7.0225 |

### latent_pca_29

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 29 |
| OOS IC Mean | 0.035564 |
| OOS IC Std | 0.366953 |
| OOS IR | 0.0969 |
| IC Positive Rate | 0.562 |
| IC t-stat | 1.5077 |
| N Dates (OOS) | 242 |
| Turnover | 0.2446 |
| Net IC (cost-adj) | 0.034903 |
| Train IC Mean | 0.032906 |
| Train IR | 0.0944 |
| OOS/IS Decay Ratio | 1.0808 |

### latent_pca_15

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 15 |
| OOS IC Mean | -0.034756 |
| OOS IC Std | 0.370739 |
| OOS IR | -0.0937 |
| IC Positive Rate | 0.5 |
| IC t-stat | -1.4584 |
| N Dates (OOS) | 242 |
| Turnover | 0.299 |
| Net IC (cost-adj) | -0.035563 |
| Train IC Mean | -0.017972 |
| Train IR | -0.0542 |
| OOS/IS Decay Ratio | 1.9339 |

### latent_pca_17

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 17 |
| OOS IC Mean | -0.027875 |
| OOS IC Std | 0.354565 |
| OOS IR | -0.0786 |
| IC Positive Rate | 0.4917 |
| IC t-stat | -1.223 |
| N Dates (OOS) | 242 |
| Turnover | 0.2579 |
| Net IC (cost-adj) | -0.028571 |
| Train IC Mean | -0.036548 |
| Train IR | -0.1055 |
| OOS/IS Decay Ratio | 0.7627 |

### latent_pca_25

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 25 |
| OOS IC Mean | 0.027515 |
| OOS IC Std | 0.35558 |
| OOS IR | 0.0774 |
| IC Positive Rate | 0.5165 |
| IC t-stat | 1.2038 |
| N Dates (OOS) | 242 |
| Turnover | 0.2399 |
| Net IC (cost-adj) | 0.026867 |
| Train IC Mean | 0.027384 |
| Train IR | 0.0792 |
| OOS/IS Decay Ratio | 1.0048 |

### latent_pca_20

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 20 |
| OOS IC Mean | 0.026387 |
| OOS IC Std | 0.349367 |
| OOS IR | 0.0755 |
| IC Positive Rate | 0.5372 |
| IC t-stat | 1.1749 |
| N Dates (OOS) | 242 |
| Turnover | 0.2106 |
| Net IC (cost-adj) | 0.025818 |
| Train IC Mean | 0.039815 |
| Train IR | 0.1125 |
| OOS/IS Decay Ratio | 0.6627 |

### latent_pca_03

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 3 |
| OOS IC Mean | 0.027586 |
| OOS IC Std | 0.371638 |
| OOS IR | 0.0742 |
| IC Positive Rate | 0.5083 |
| IC t-stat | 1.1547 |
| N Dates (OOS) | 242 |
| Turnover | 0.2033 |
| Net IC (cost-adj) | 0.027037 |
| Train IC Mean | -0.01308 |
| Train IR | -0.0359 |
| OOS/IS Decay Ratio | 2.109 |

### latent_pca_24

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 24 |
| OOS IC Mean | 0.02409 |
| OOS IC Std | 0.351655 |
| OOS IR | 0.0685 |
| IC Positive Rate | 0.5248 |
| IC t-stat | 1.0657 |
| N Dates (OOS) | 242 |
| Turnover | 0.1977 |
| Net IC (cost-adj) | 0.023556 |
| Train IC Mean | 0.040025 |
| Train IR | 0.1146 |
| OOS/IS Decay Ratio | 0.6019 |

### latent_pca_56

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 56 |
| OOS IC Mean | -0.021779 |
| OOS IC Std | 0.342126 |
| OOS IR | -0.0637 |
| IC Positive Rate | 0.4628 |
| IC t-stat | -0.9903 |
| N Dates (OOS) | 242 |
| Turnover | 0.2789 |
| Net IC (cost-adj) | -0.022532 |
| Train IC Mean | 0.001884 |
| Train IR | 0.0056 |
| OOS/IS Decay Ratio | 11.56 |

### latent_pca_30

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 30 |
| OOS IC Mean | 0.021927 |
| OOS IC Std | 0.345991 |
| OOS IR | 0.0634 |
| IC Positive Rate | 0.5248 |
| IC t-stat | 0.9859 |
| N Dates (OOS) | 242 |
| Turnover | 0.2812 |
| Net IC (cost-adj) | 0.021168 |
| Train IC Mean | 0.053242 |
| Train IR | 0.154 |
| OOS/IS Decay Ratio | 0.4118 |

### latent_pca_06

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 6 |
| OOS IC Mean | 0.021923 |
| OOS IC Std | 0.350262 |
| OOS IR | 0.0626 |
| IC Positive Rate | 0.5124 |
| IC t-stat | 0.9737 |
| N Dates (OOS) | 242 |
| Turnover | 0.0963 |
| Net IC (cost-adj) | 0.021663 |
| Train IC Mean | -0.005401 |
| Train IR | -0.0149 |
| OOS/IS Decay Ratio | 4.0591 |

### latent_pca_55

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 55 |
| OOS IC Mean | -0.021143 |
| OOS IC Std | 0.374901 |
| OOS IR | -0.0564 |
| IC Positive Rate | 0.4504 |
| IC t-stat | -0.8773 |
| N Dates (OOS) | 242 |
| Turnover | 0.1405 |
| Net IC (cost-adj) | -0.021522 |
| Train IC Mean | 0.009093 |
| Train IR | 0.0252 |
| OOS/IS Decay Ratio | 2.3252 |

### latent_pca_47

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 47 |
| OOS IC Mean | -0.018941 |
| OOS IC Std | 0.381503 |
| OOS IR | -0.0496 |
| IC Positive Rate | 0.4711 |
| IC t-stat | -0.7724 |
| N Dates (OOS) | 242 |
| Turnover | 0.2032 |
| Net IC (cost-adj) | -0.01949 |
| Train IC Mean | -0.020021 |
| Train IR | -0.0573 |
| OOS/IS Decay Ratio | 0.9461 |

### latent_pca_59

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 59 |
| OOS IC Mean | 0.016497 |
| OOS IC Std | 0.350104 |
| OOS IR | 0.0471 |
| IC Positive Rate | 0.5372 |
| IC t-stat | 0.733 |
| N Dates (OOS) | 242 |
| Turnover | 0.1289 |
| Net IC (cost-adj) | 0.016149 |
| Train IC Mean | 0.005301 |
| Train IR | 0.0151 |
| OOS/IS Decay Ratio | 3.1121 |

### latent_pca_49

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 49 |
| OOS IC Mean | -0.01692 |
| OOS IC Std | 0.37199 |
| OOS IR | -0.0455 |
| IC Positive Rate | 0.4959 |
| IC t-stat | -0.7076 |
| N Dates (OOS) | 242 |
| Turnover | 0.2253 |
| Net IC (cost-adj) | -0.017528 |
| Train IC Mean | 0.030393 |
| Train IR | 0.0817 |
| OOS/IS Decay Ratio | 0.5567 |

### latent_pca_57

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 57 |
| OOS IC Mean | -0.017339 |
| OOS IC Std | 0.396875 |
| OOS IR | -0.0437 |
| IC Positive Rate | 0.4876 |
| IC t-stat | -0.6797 |
| N Dates (OOS) | 242 |
| Turnover | 0.1422 |
| Net IC (cost-adj) | -0.017723 |
| Train IC Mean | -0.024892 |
| Train IR | -0.0717 |
| OOS/IS Decay Ratio | 0.6966 |

### latent_pca_26

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 26 |
| OOS IC Mean | 0.015506 |
| OOS IC Std | 0.386312 |
| OOS IR | 0.0401 |
| IC Positive Rate | 0.5041 |
| IC t-stat | 0.6244 |
| N Dates (OOS) | 242 |
| Turnover | 0.2388 |
| Net IC (cost-adj) | 0.014861 |
| Train IC Mean | -0.033753 |
| Train IR | -0.0877 |
| OOS/IS Decay Ratio | 0.4594 |

### latent_pca_31

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 31 |
| OOS IC Mean | 0.012377 |
| OOS IC Std | 0.36037 |
| OOS IR | 0.0343 |
| IC Positive Rate | 0.5041 |
| IC t-stat | 0.5343 |
| N Dates (OOS) | 242 |
| Turnover | 0.2255 |
| Net IC (cost-adj) | 0.011768 |
| Train IC Mean | 0.030941 |
| Train IR | 0.0936 |
| OOS/IS Decay Ratio | 0.4 |

### latent_pca_62

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 62 |
| OOS IC Mean | 0.011691 |
| OOS IC Std | 0.361059 |
| OOS IR | 0.0324 |
| IC Positive Rate | 0.4917 |
| IC t-stat | 0.5037 |
| N Dates (OOS) | 242 |
| Turnover | 0.1496 |
| Net IC (cost-adj) | 0.011287 |
| Train IC Mean | -0.009204 |
| Train IR | -0.0262 |
| OOS/IS Decay Ratio | 1.2702 |

### latent_pca_39

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 39 |
| OOS IC Mean | -0.012106 |
| OOS IC Std | 0.374776 |
| OOS IR | -0.0323 |
| IC Positive Rate | 0.4711 |
| IC t-stat | -0.5025 |
| N Dates (OOS) | 242 |
| Turnover | 0.2354 |
| Net IC (cost-adj) | -0.012741 |
| Train IC Mean | 0.019981 |
| Train IR | 0.0556 |
| OOS/IS Decay Ratio | 0.6059 |

### latent_pca_60

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 60 |
| OOS IC Mean | 0.010374 |
| OOS IC Std | 0.351918 |
| OOS IR | 0.0295 |
| IC Positive Rate | 0.5041 |
| IC t-stat | 0.4586 |
| N Dates (OOS) | 242 |
| Turnover | 0.2008 |
| Net IC (cost-adj) | 0.009832 |
| Train IC Mean | -0.059446 |
| Train IR | -0.1705 |
| OOS/IS Decay Ratio | 0.1745 |

### latent_pca_43

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 43 |
| OOS IC Mean | -0.009545 |
| OOS IC Std | 0.34258 |
| OOS IR | -0.0279 |
| IC Positive Rate | 0.4959 |
| IC t-stat | -0.4334 |
| N Dates (OOS) | 242 |
| Turnover | 0.1941 |
| Net IC (cost-adj) | -0.010069 |
| Train IC Mean | 0.012891 |
| Train IR | 0.0382 |
| OOS/IS Decay Ratio | 0.7404 |

### latent_pca_02

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 2 |
| OOS IC Mean | 0.009954 |
| OOS IC Std | 0.375592 |
| OOS IR | 0.0265 |
| IC Positive Rate | 0.5248 |
| IC t-stat | 0.4123 |
| N Dates (OOS) | 242 |
| Turnover | 0.2205 |
| Net IC (cost-adj) | 0.009359 |
| Train IC Mean | -0.018228 |
| Train IR | -0.0497 |
| OOS/IS Decay Ratio | 0.5461 |

### latent_pca_54

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 54 |
| OOS IC Mean | -0.007986 |
| OOS IC Std | 0.344486 |
| OOS IR | -0.0232 |
| IC Positive Rate | 0.4711 |
| IC t-stat | -0.3606 |
| N Dates (OOS) | 242 |
| Turnover | 0.2074 |
| Net IC (cost-adj) | -0.008546 |
| Train IC Mean | -0.02387 |
| Train IR | -0.067 |
| OOS/IS Decay Ratio | 0.3346 |

### latent_pca_00

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 0 |
| OOS IC Mean | -0.009562 |
| OOS IC Std | 0.433069 |
| OOS IR | -0.0221 |
| IC Positive Rate | 0.5 |
| IC t-stat | -0.3435 |
| N Dates (OOS) | 242 |
| Turnover | 0.1095 |
| Net IC (cost-adj) | -0.009858 |
| Train IC Mean | 0.025188 |
| Train IR | 0.0658 |
| OOS/IS Decay Ratio | 0.3796 |

### latent_pca_58

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 58 |
| OOS IC Mean | -0.006262 |
| OOS IC Std | 0.369902 |
| OOS IR | -0.0169 |
| IC Positive Rate | 0.4835 |
| IC t-stat | -0.2634 |
| N Dates (OOS) | 242 |
| Turnover | 0.232 |
| Net IC (cost-adj) | -0.006888 |
| Train IC Mean | -0.081962 |
| Train IR | -0.2035 |
| OOS/IS Decay Ratio | 0.0764 |

### latent_pca_22

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 22 |
| OOS IC Mean | 0.005194 |
| OOS IC Std | 0.347184 |
| OOS IR | 0.015 |
| IC Positive Rate | 0.5083 |
| IC t-stat | 0.2327 |
| N Dates (OOS) | 242 |
| Turnover | 0.2428 |
| Net IC (cost-adj) | 0.004538 |
| Train IC Mean | -0.014115 |
| Train IR | -0.0382 |
| OOS/IS Decay Ratio | 0.368 |

### latent_pca_61

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 61 |
| OOS IC Mean | -0.005049 |
| OOS IC Std | 0.360518 |
| OOS IR | -0.014 |
| IC Positive Rate | 0.5248 |
| IC t-stat | -0.2179 |
| N Dates (OOS) | 242 |
| Turnover | 0.1887 |
| Net IC (cost-adj) | -0.005559 |
| Train IC Mean | -0.055547 |
| Train IR | -0.1584 |
| OOS/IS Decay Ratio | 0.0909 |

### latent_pca_34

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 34 |
| OOS IC Mean | -0.004423 |
| OOS IC Std | 0.360457 |
| OOS IR | -0.0123 |
| IC Positive Rate | 0.5041 |
| IC t-stat | -0.1909 |
| N Dates (OOS) | 242 |
| Turnover | 0.2348 |
| Net IC (cost-adj) | -0.005057 |
| Train IC Mean | -0.020541 |
| Train IR | -0.059 |
| OOS/IS Decay Ratio | 0.2153 |

### latent_pca_51

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 51 |
| OOS IC Mean | 0.003956 |
| OOS IC Std | 0.354165 |
| OOS IR | 0.0112 |
| IC Positive Rate | 0.5165 |
| IC t-stat | 0.1738 |
| N Dates (OOS) | 242 |
| Turnover | 0.2334 |
| Net IC (cost-adj) | 0.003326 |
| Train IC Mean | 0.026122 |
| Train IR | 0.0789 |
| OOS/IS Decay Ratio | 0.1514 |

### latent_pca_45

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 45 |
| OOS IC Mean | 0.003327 |
| OOS IC Std | 0.364537 |
| OOS IR | 0.0091 |
| IC Positive Rate | 0.4917 |
| IC t-stat | 0.142 |
| N Dates (OOS) | 242 |
| Turnover | 0.2573 |
| Net IC (cost-adj) | 0.002632 |
| Train IC Mean | -0.013543 |
| Train IR | -0.0377 |
| OOS/IS Decay Ratio | 0.2457 |

### latent_pca_35

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 35 |
| OOS IC Mean | 0.002801 |
| OOS IC Std | 0.331441 |
| OOS IR | 0.0085 |
| IC Positive Rate | 0.5 |
| IC t-stat | 0.1315 |
| N Dates (OOS) | 242 |
| Turnover | 0.2287 |
| Net IC (cost-adj) | 0.002183 |
| Train IC Mean | -0.02097 |
| Train IR | -0.0614 |
| OOS/IS Decay Ratio | 0.1336 |

### latent_pca_01

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 1 |
| OOS IC Mean | -0.00204 |
| OOS IC Std | 0.422808 |
| OOS IR | -0.0048 |
| IC Positive Rate | 0.5041 |
| IC t-stat | -0.0751 |
| N Dates (OOS) | 242 |
| Turnover | 0.051 |
| Net IC (cost-adj) | -0.002178 |
| Train IC Mean | -0.017151 |
| Train IR | -0.043 |
| OOS/IS Decay Ratio | 0.1189 |

### latent_pca_38

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 38 |
| OOS IC Mean | 0.001458 |
| OOS IC Std | 0.342033 |
| OOS IR | 0.0043 |
| IC Positive Rate | 0.5248 |
| IC t-stat | 0.0663 |
| N Dates (OOS) | 242 |
| Turnover | 0.2207 |
| Net IC (cost-adj) | 0.000862 |
| Train IC Mean | -0.001672 |
| Train IR | -0.0048 |
| OOS/IS Decay Ratio | 0.872 |

### latent_pca_42

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 42 |
| OOS IC Mean | -0.001081 |
| OOS IC Std | 0.354955 |
| OOS IR | -0.003 |
| IC Positive Rate | 0.4628 |
| IC t-stat | -0.0474 |
| N Dates (OOS) | 242 |
| Turnover | 0.2196 |
| Net IC (cost-adj) | -0.001674 |
| Train IC Mean | -0.014157 |
| Train IR | -0.0388 |
| OOS/IS Decay Ratio | 0.0764 |

## 7. Input Feature Columns

Total alpha features used: **114**

<details>
<summary>Click to expand full feature list</summary>

1. `alpha_absorption`
2. `alpha_acceleration_index`
3. `alpha_adv_20d`
4. `alpha_adv_60d`
5. `alpha_atr_14_norm`
6. `alpha_bb_dist_10`
7. `alpha_bb_dist_120`
8. `alpha_bb_dist_20`
9. `alpha_bb_dist_40`
10. `alpha_bb_dist_60`
11. `alpha_body_size`
12. `alpha_candle_range`
13. `alpha_consecutive_up_days`
14. `alpha_cross_sectional_zscore`
15. `alpha_daily_vpin_toxicity_20`
16. `alpha_dist_high_120`
17. `alpha_dist_high_252`
18. `alpha_dist_high_60`
19. `alpha_dist_low_120`
20. `alpha_dist_low_252`
21. `alpha_dist_low_60`
22. `alpha_dist_ma_10`
23. `alpha_dist_ma_100`
24. `alpha_dist_ma_20`
25. `alpha_dist_ma_200`
26. `alpha_dist_ma_5`
27. `alpha_dist_ma_50`
28. `alpha_dist_ma_60`
29. `alpha_gap_return`
30. `alpha_garman_klass_vol_20`
31. `alpha_hist_vol_10`
32. `alpha_hist_vol_20`
33. `alpha_hist_vol_60`
34. `alpha_inertia`
35. `alpha_limit_lock_streak`
36. `alpha_liquidity_drought_acceleration_20_60`
37. `alpha_liquidity_quality`
38. `alpha_market_correlation`
39. `alpha_mom_20_60`
40. `alpha_mom_5_20`
41. `alpha_mom_60_120`
42. `alpha_obv_change_20`
43. `alpha_order_imbalance`
44. `alpha_p34_kyle_lambda_20`
45. `alpha_p34_liquidity_provision_ratio_10`
46. `alpha_p34_micro_momentum_5_20`
47. `alpha_p34_tick_signed_volume_imbalance_5`
48. `alpha_p34_volatility_compression_5`
49. `alpha_p34_volume_clock_acceleration_10`
50. `alpha_pair_correlation`
51. `alpha_parkinson_vol_10`
52. `alpha_parkinson_vol_20`
53. `alpha_parkinson_vol_60`
54. `alpha_percentile_rank`
55. `alpha_price_acceleration`
56. `alpha_range_impact_stress_20`
57. `alpha_relative_strength`
58. `alpha_relative_strength_universe`
59. `alpha_ret_120d`
60. `alpha_ret_20d`
61. `alpha_ret_5d`
62. `alpha_ret_60d`
63. `alpha_roc_10`
64. `alpha_roc_120`
65. `alpha_roc_20`
66. `alpha_roc_252`
67. `alpha_roc_5`
68. `alpha_roc_60`
69. `alpha_roll_effective_spread_20`
70. `alpha_rsi_14`
71. `alpha_rsi_21`
72. `alpha_rsi_28`
73. `alpha_rsi_7`
74. `alpha_rsi_crossover_20_120`
75. `alpha_rsi_crossover_5_20`
76. `alpha_rsi_crossover_60_120`
77. `alpha_rsi_divergence`
78. `alpha_sector_rel_momentum_20`
79. `alpha_sector_rel_momentum_60`
80. `alpha_smart_money_lite`
81. `alpha_stock_sector_corr`
82. `alpha_t2_momentum_adj`
83. `alpha_turtle_traders`
84. `alpha_vn_001_post_settlement_momentum`
85. `alpha_vn_002_limit_band_reversion`
86. `alpha_vn_004_intraday_persistence`
87. `alpha_vn_005_liquidity_adjusted_reversal`
88. `alpha_vn_amihud_liq_reversal`
89. `alpha_vn_bollinger_snapback`
90. `alpha_vn_close_location_reversion`
91. `alpha_vn_illiq_regime_penalty`
92. `alpha_vn_limit_lock_continuation`
93. `alpha_vn_limit_unlock_exhaustion`
94. `alpha_vn_rsi_divergence_reversal`
95. `alpha_vn_sector_neutral_residual_reversion`
96. `alpha_vn_t2_cash_recycling_bounce`
97. `alpha_vn_t2_momentum_diff`
98. `alpha_vn_t2_settlement_supply_overhang`
99. `alpha_vn_turnover_exhaustion`
100. `alpha_vn_volume_shock_reversal`
101. `alpha_vol_ma_ratio_10_60`
102. `alpha_vol_ma_ratio_5_20`
103. `alpha_vol_momentum_10`
104. `alpha_vol_momentum_20`
105. `alpha_vol_momentum_5`
106. `alpha_vwap_deviation`
107. `alpha_wick_ratio`
108. `alpha_yang_zhang_vol_20`
109. `alpha_zscore`
110. `hl_range`
111. `oc_range`
112. `ret_1d`
113. `ret_5d`
114. `vol_ratio`

</details>

## 8. Artifacts

| Artifact | Path |
|----------|------|
| Projected components | `data\latent_alphas_components.parquet` |
| Fitted models | `data\latent_alphas_model.pkl` |
| Metrics JSON | `data\latent_alphas_metrics.json` |
| This report | `.ly_state\session\latent_alphas_report_20260617.md` |

## 9. Reproducibility

- **Seed**: 42 (random, numpy)
- **Features hash**: `a80c73af5a08195c`
- **Python packages**: numpy, pandas, scikit-learn, scipy
- **Deterministic**: Yes (all random_state=SEED, no stochastic splits)

## 10. SOD/PIT Guardrails

| Guardrail | Status |
|-----------|--------|
| PIT: No look-ahead | PASS — train-only fit, frozen OOS projection |
| PIT: T-1 lag verified | PASS — source features pre-lagged |
| SOD: No self-approval | COMPLIANT — L2 role, submit to Tier 3 |
| SOD: Tier 3 audit pending | PENDING — Code Reviewer (role 21) + QA Engineer (role 17) |
| Reproducibility | PASS — seeds set, hash recorded, deterministic |

> **Verdict**: RESEARCH_ONLY — latent alphas require walk-forward OOS validation
> via Phase 3.5 backtest before promotion consideration.