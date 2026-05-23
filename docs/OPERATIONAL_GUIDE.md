# OMEGA_QUANT - Hướng Dẫn Vận Hành Hệ Thống
**Version**: 1.0.0
**Last Updated**: 2026-05-14
**Status**: Production Ready

---

## Mục Lục
1. [Tổng Quan Hệ Thống](#1-tổng-quan-hệ-thống)
2. [Cấu Trúc Thư Mục](#2-cấu-trúc-thư-mục)
3. [Cài Đặt & Khởi Tạo](#3-cài-đặt--khởi-tạo)
4. [Chạy Hệ Thống Hàng Ngày](#4-chạy-hệ-thống-hàng-ngày)
5. [Giám Sát & Alerting](#5-giám-sát--alerting)
6. [Xử Lý Sự Cố](#6-xử-lý-sự-cố)
7. [Bảo Trì Định Kỳ](#7-bảo-trì-định-kỳ)
8. [Backup & Recovery](#8-backup--recovery)
9. [Security Checklist](#9-security-checklist)

---

## 1. Tổng Quan Hệ Thống

### 1.1 Mô Tả Kiến Trúc

OMEGA_QUANT là hệ thống **Institutional Grade Quant AI** được thiết kế để:
- **Alpha Generation**: Tạo tín hiệu giao dịch từ dữ liệu thị trường
- **Risk Management**: Quản lý rủi ro theo chuẩn Institutional
- **Execution Engine**: Thực thi lệnh qua broker (SSI, VNDirect, VietStock)
- **Self-Evolution**: Tự học và cải thiện chiến lược theo thời gian

### 1.2 Các Phase Chính

| Phase | Mô Tả | Status |
|:---|:---|:---|
| **Phase 1** | Foundation (Worker, Checkpoint, Database, Event Bus) | ✅ Production |
| **Phase 2** | Data & Storage Layer (VCI Ingestion, Feature Engineering) | ✅ Production |
| **Phase 3** | Quant Math Engine (Alpha Discovery, PIT Safety, Expression Generator) | ✅ Production |
| **Phase 4** | Execution Engine (VWAP/TWAP, Slippage Estimation) | ✅ Production |
| **Phase 5** | Risk Management (Circuit Breaker, Individual RiskGuard) | ✅ Production |
| **Phase 6** | Memory & Evolution (Neural Memory, Evolution Engine) | ✅ Production |
| **Phase 7** | Observability & SRE (Structured Logging, Metrics) | ✅ Production |
| **Phase 8** | Security & Governance (Vault, RBAC, Audit Trail) | ✅ Production |
| **Phase 9** | E2E Pipeline & PIT Safety Boundaries | ✅ Production |
| **Phase 10** | Production Deployment & CLI Scripts | ✅ Production |
| **Phase 11** | Task State Machine | ✅ Production |
| **Phase 12** | Model Registry & Context Assembly | ✅ Production |
| **Phase 13** | ML Engine (XGBoost, LSTM, PIT-safe training) | ✅ Production |

### 1.3 Yêu Cầu Hệ Thống

| Component | Minimum | Recommended |
|:---|:---|:---|
| **RAM** | 8GB | 16GB |
| **CPU** | 4 cores | 8+ cores |
| **Disk** | 50GB | 100GB SSD |
| **Python** | 3.11+ | 3.14+ |
| **OS** | Windows 10/11, Linux | Windows 11, Ubuntu 22.04 |

---

## 2. Cấu Trúc Thư Mục

```
OMEGA_QUANT/
├── config/                    # Configuration files
│   ├── production.yaml         # Production config
│   ├── development.yaml        # Development config
│   └── vn_holidays.json       # Vietnam stock holidays
├── packages/                   # Core packages
│   ├── core/                   # Core utilities
│   ├── data/                   # Data ingestion & processing
│   ├── quant/                  # Quant math engine
│   ├── observability/          # Monitoring & logging
│   └── security/               # Security & governance
├── scripts/                    # Operational scripts
│   ├── deploy_omega.py         # Deployment script
│   ├── run_daily.py           # Daily run script
│   ├── health_check.py         # Health check script
│   ├── rollback.py             # Rollback script
│   └── sod_gate_enforcer.py   # SOD verification
├── tests/                      # Test suites (706 tests)
│   ├── phase1/ ... phase13/   # Phase-specific tests
│   └── conftest.py            # Test fixtures
├── data/                       # Data directory
│   └── market/                # Market data (CSV files)
├── logs/                       # Application logs
├── artifacts/                  # Model artifacts & outputs
├── .ly_state/                 # State persistence
│   ├── session/               # Current session state
│   ├── memory/                # Memory snapshots
│   ├── checkpoints/            # Checkpoint files
│   └── gates/                 # Phase gates (APPROVED/REJECTED)
└── docs/                       # Documentation
    ├── OPERATIONAL_GUIDE.md    # This file
    └── PHASE*_*.md            # Phase-specific docs
```

---

## 3. Cài Đặt & Khởi Tạo

### 3.1 Cài Đặt Môi Trường

```bash
# Clone repository
git clone https://github.com/ManhMon/V21_QUANT.git
cd V21_QUANT

# Tạo virtual environment (khuyến nghị)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# hoặc
venv\Scripts\activate     # Windows

# Cài đặt dependencies
pip install -e packages/core
pip install -e packages/data
pip install -e packages/quant
pip install -e packages/observability
pip install -e packages/security

# Cài đặt dependencies chung
pip install pandas numpy pyyaml pytest pytest-cov
```

### 3.2 Khởi Tạo Cấu Hình

```bash
# Copy file cấu hình mẫu
cp config/production.yaml config/local.yaml

# Chỉnh sửa cấu hình theo nhu cầu
# Đặc biệt chú ý:
# - data.data_dir: Đường dẫn dữ liệu
# - portfolio.initial_capital: Vốn ban đầu
# - execution.broker: Broker sử dụng (ssi/vndirect/vietsol)
```

### 3.3 Verify Installation

```bash
# Chạy health check
python scripts/health_check.py --quick

# Kết quả mong đợi:
# ============================================================
# SYSTEM HEALTH CHECK RESULTS
# ============================================================
# [PASS] Memory: X.XX GB available (XX% used)
# [PASS] CPU: XX% usage
# [PASS] Disk: XX.X GB free
# [PASS] Data Availability: XX symbols available
# ============================================================
# Status: HEALTHY
# ============================================================
```

---

## 4. Chạy Hệ Thống Hàng Ngày

### 4.1 Daily Pipeline Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    DAILY WORKFLOW                          │
├─────────────────────────────────────────────────────────────┤
│  1. Pre-flight Checks (T-0:00)                             │
│     └── Verify data, check market hours                    │
│  2. Data Ingestion (T-0:05)                                │
│     └── Load market data from vnstock/API                  │
│  3. Feature Engineering (T-0:15)                           │
│     └── Compute indicators, alpha signals                  │
│  4. Alpha Generation (T-0:30)                               │
│     └── Generate candidate alphas                          │
│  5. Risk Management (T-0:45)                               │
│     └── Apply risk controls, circuit breakers             │
│  6. Portfolio Optimization (T-1:00)                         │
│     └── Compute optimal weights                            │
│  7. Execution Planning (T-1:15)                           │
│     └── Generate order list                               │
│  8. Post-trade Analysis (T+1:00)                          │
│     └── Update metrics, log performance                    │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Chạy Daily Pipeline

```bash
# Chạy với cấu hình mặc định
python scripts/run_daily.py

# Chạy với cấu hình tùy chỉnh
python scripts/run_daily.py --config config/local.yaml

# Chạy cho ngày cụ thể (backtest)
python scripts/run_daily.py --date 2026-05-13

# Bỏ qua pre-flight checks (không khuyến nghị)
python scripts/run_daily.py --skip-checks
```

### 4.3 Output Mẫu

```bash
============================================================
DAILY REBALANCE SUMMARY - 2026-05-13
============================================================
Status: SUCCESS
Execution Time: 45.23 seconds

Portfolio Summary:
  - Total Positions: 15
  - Total Exposure: 87.3%
  - Daily P&L: +1.23%
  - YTD Return: +12.45%

Top Holdings:
  1. VCB: 12.5% (Long)
  2. FPT: 10.2% (Long)
  3. HPG: 8.7% (Long)

Risk Metrics:
  - Portfolio Volatility: 18.5%
  - Max Drawdown: -2.1%
  - Sharpe Ratio: 1.45
============================================================
```

---

## 5. Giám Sát & Alerting

### 5.1 Monitoring Endpoints

```bash
# Kiểm tra trạng thái hệ thống
python scripts/health_check.py --quick

# Kiểm tra chi tiết (bao gồm data freshness)
python scripts/health_check.py --full

# Xem logs gần đây
tail -n 100 logs/omega_prod.log
```

### 5.2 Alert Thresholds

| Metric | Warning | Critical | Action |
|:---|:---|:---|:---|
| **Portfolio Drawdown** | -5% | -10% | Pause trading |
| **Volatility** | 25% | 40% | Reduce exposure |
| **Data Freshness** | >30 min | >60 min | Alert ops team |
| **Execution Error Rate** | >5% | >10% | Stop execution |
| **Memory Usage** | >80% | >90% | Restart services |

### 5.3 Structured Logging Format

```json
{
  "timestamp": "2026-05-14T09:15:30.123456+07:00",
  "level": "INFO",
  "logger": "alpha_discovery",
  "message": "Alpha generated successfully",
  "context": {
    "phase": "alpha_discovery",
    "alpha_id": "alpha_001",
    "ic": 0.12,
    "sharpe": 1.45,
    "turnover": 0.15
  },
  "trace_id": "abc123",
  "span_id": "def456"
}
```

---

## 6. Xử Lý Sự Cố

### 6.1 Common Issues & Solutions

| Issue | Cause | Solution |
|:---|:---|:---|
| **Data Load Failed** | API rate limit | Retry after 5 min, check API key |
| **Memory Error** | Large dataset | Reduce history days in config |
| **Model Not Found** | Wrong version | Check model registry |
| **Execution Failed** | Broker offline | Switch to backup broker |
| **PIT Safety Error** | Future data leak | Check data timestamps |

### 6.2 Rollback Procedure

```bash
# Xem danh sách checkpoints
python scripts/rollback.py --list

# Rollback về checkpoint cụ thể
python scripts/rollback.py --checkpoint 2026-05-13_09-00

# Rollback về phiên bản model
python scripts/rollback.py --model momentum_v1
```

### 6.3 Emergency Procedures

```bash
# Dừng giao dịch ngay lập tức
python scripts/emergency_stop.py

# Kiểm tra positions hiện tại
python scripts/emergency_stop.py --status

# Cancel tất cả orders đang chờ
python scripts/emergency_stop.py --cancel-all
```

---

## 7. Bảo Trì Định Kỳ

### 7.1 Daily Tasks

- [ ] Chạy `health_check.py --quick` mỗi sáng
- [ ] Kiểm tra logs cho errors/warnings
- [ ] Verify data freshness (< 30 phút)

### 7.2 Weekly Tasks

- [ ] Chạy full test suite: `pytest -q`
- [ ] Review P&L performance
- [ ] Kiểm tra disk space
- [ ] Backup state files

### 7.3 Monthly Tasks

- [ ] Chạy L3 audit: `codex exec --dangerously-bypass-approvals-and-sandbox '[L3-Audit:Role21-Review] Full audit'`
- [ ] Review security logs
- [ ] Update dependencies (pip update)
- [ ] Performance profiling

### 7.4 Test Suite

```bash
# Chạy full test suite
pytest -q

# Chạy với coverage
pytest --cov=packages --cov-report=html

# Chạy PIT safety tests
pytest -k pit -q

# Chạy specific phase tests
pytest tests/phase3/ -q
```

**Test Results**: 706/706 PASSED (100%)

---

## 8. Backup & Recovery

### 8.1 Backup Strategy

```bash
# Backup state files (tự động chạy mỗi ngày)
python scripts/backup.py --type state

# Backup models
python scripts/backup.py --type models

# Backup full system
python scripts/backup.py --type full

# Backup location: .ly_state/backups/
```

### 8.2 Recovery Procedure

```bash
# Liệt kê backups có sẵn
python scripts/backup.py --list

# Khôi phục từ backup
python scripts/backup.py --restore backup_2026-05-13.tar.gz

# Verify restore
python scripts/health_check.py --quick
```

### 8.3 State Persistence

Hệ thống sử dụng `.ly_state/` để lưu trữ state:

```
.ly_state/
├── session/
│   ├── active_tasks.json      # Tasks đang chạy
│   ├── active_config.yaml     # Config hiện tại
│   └── deployment_metadata.json # Deployment info
├── memory/
│   └── session_*.json         # Memory snapshots
├── checkpoints/
│   └── checkpoint_*.json      # Checkpoint files
├── gates/
│   └── phase*_gate.json       # Phase approval gates
└── logs/
    └── *.jsonl                # Audit logs
```

---

## 9. Security Checklist

### 9.1 Pre-Deployment

- [ ] Verify git status: `git status`
- [ ] Chạy SOD gate enforcer: `python scripts/sod_gate_enforcer.py --check-before-push`
- [ ] Review code changes
- [ ] Update version tags

### 9.2 Production Security

- [ ] Không commit secrets vào git
- [ ] Sử dụng environment variables cho API keys
- [ ] Enable RBAC: `security.rbac_enabled: true`
- [ ] Enable audit trail: `security.audit_trail_enabled: true`
- [ ] Review access logs định kỳ

### 9.3 Secrets Management

```bash
# Sử dụng vault cho secrets
python scripts/vault.py --set broker_api_key=<key>
python scripts/vault.py --get broker_api_key

# Hoặc sử dụng .env file
echo "BROKER_API_KEY=xxx" > .env
```

---

## 10. Liên Hệ & Hỗ Trợ

### 10.1 Tài Liệu Liên Quan

| Document | Mục đích |
|:---|:---|
| `docs/OMEGA_SUPER_MASTER_PLAN.md` | Lộ trình phát triển |
| `docs/SYSTEM_MASTER_LOG.md` | Log tất cả thay đổi |
| `docs/PHASE*_FINAL_AUDIT_*.md` | Audit reports |
| `docs/TEAM_ARCHITECTURE.md` | 25 Agent Roles |

### 10.2 Scripts Reference

| Script | Chức năng |
|:---|:---|
| `deploy_omega.py` | Deployment |
| `run_daily.py` | Daily pipeline |
| `health_check.py` | System health |
| `rollback.py` | Rollback |
| `sod_gate_enforcer.py` | SOD verification |
| `backup.py` | Backup & restore |
| `emergency_stop.py` | Emergency stop |

---

## Quick Reference

```bash
# 1. Khởi tạo
python scripts/deploy_omega.py --env production --deploy

# 2. Health check
python scripts/health_check.py --quick

# 3. Chạy hàng ngày
python scripts/run_daily.py --config config/production.yaml

# 4. Kiểm tra tests
python -m pytest -q

# 5. Xem logs
tail -n 100 logs/omega_prod.log
