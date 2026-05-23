# OMEGA_QUANT Deployment Standard Operating Procedure (SOP)
# ===========================================================

**Version:** 1.0.0  
**Last Updated:** 2026-05-11  
**Owner:** OMEGA_QUANT DevOps Team  
**Classification:** Internal Use Only

---

## Table of Contents

1. [Overview](#overview)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Deployment Procedures](#deployment-procedures)
4. [Post-Deployment Validation](#post-deployment-validation)
5. [Rollback Procedures](#rollback-procedures)
6. [Monitoring & Alerts](#monitoring--alerts)
7. [Troubleshooting](#troubleshooting)
8. [Emergency Contacts](#emergency-contacts)

---

## Overview

This document outlines the standard operating procedures for deploying OMEGA_QUANT to production environments. All deployments must follow these procedures to ensure system reliability, data integrity, and regulatory compliance.

### Deployment Principles

1. **PIT Safety First**: All deployments must maintain point-in-time data integrity
2. **Zero Downtime**: Use blue-green or canary deployment strategies
3. **Rollback Ready**: Every deployment must have a tested rollback plan
4. **Audit Trail**: All deployment actions must be logged and auditable
5. **Segregation of Duties**: Separate implementation and validation teams

### Deployment Types

- **Hotfix**: Critical bug fixes (< 2 hours)
- **Standard**: Regular feature releases (planned maintenance window)
- **Major**: Architecture changes (extended maintenance window)

---

## Pre-Deployment Checklist

### 1. Code Quality Gates

- [ ] All unit tests passing (`pytest tests/`)
- [ ] Integration tests passing (`pytest tests/integration/`)
- [ ] Code coverage ≥ 80% (`pytest --cov`)
- [ ] Linting passed (`flake8`, `black`, `mypy`)
- [ ] Security scan completed (no critical vulnerabilities)
- [ ] Performance benchmarks within acceptable range

### 2. Configuration Validation

- [ ] `config/production.yaml` reviewed and validated
- [ ] `.env` file configured with production secrets
- [ ] Environment variables verified (`python scripts/health_check.py --config config/production.yaml`)
- [ ] Database migrations tested (if applicable)
- [ ] API keys and credentials rotated (if needed)

### 3. Data Integrity

- [ ] PIT safety checks passed
- [ ] Data pipeline tested with production-like data
- [ ] Backfill completed (if required)
- [ ] Data quality metrics within thresholds

### 4. Risk Management

- [ ] Risk limits configured correctly
- [ ] Stop-loss mechanisms tested
- [ ] Position sizing validated
- [ ] Compliance checks passed

### 5. Documentation

- [ ] CHANGELOG.md updated
- [ ] API documentation current
- [ ] Runbook updated
- [ ] Deployment notes prepared

### 6. Approvals

- [ ] Code review completed (minimum 2 reviewers)
- [ ] QA sign-off obtained
- [ ] Risk management approval
- [ ] Compliance approval (for regulatory changes)
- [ ] Business owner approval

---

## Deployment Procedures

### Standard Deployment Process

#### Phase 1: Preparation (T-24 hours)

1. **Create Deployment Branch**
   ```bash
   git checkout -b deploy/production-YYYYMMDD
   git push origin deploy/production-YYYYMMDD
   ```

2. **Run Pre-Deployment Tests**
   ```bash
   # Full test suite
   pytest tests/ -v --cov --cov-report=html
   
   # Performance benchmarks
   python scripts/profile_performance.py --config config/production.yaml
   
   # Health check
   python scripts/health_check.py --config config/production.yaml
   ```

3. **Backup Current State**
   ```bash
   # Backup database (if applicable)
   pg_dump omega_quant > backups/omega_quant_$(date +%Y%m%d_%H%M%S).sql
   
   # Backup configuration
   cp -r config backups/config_$(date +%Y%m%d_%H%M%S)
   
   # Backup current holdings
   cp data/holdings/current.csv backups/holdings_$(date +%Y%m%d_%H%M%S).csv
   ```

4. **Notify Stakeholders**
   - Send deployment notification email
   - Update status page
   - Post in Slack #deployments channel

#### Phase 2: Deployment (T-0)

1. **Enable Maintenance Mode** (if required)
   ```bash
   # Stop daily cron jobs
   crontab -l > backups/crontab_backup.txt
   crontab -r
   ```

2. **Pull Latest Code**
   ```bash
   cd /opt/omega_quant
   git fetch origin
   git checkout deploy/production-YYYYMMDD
   ```

3. **Update Dependencies**
   ```bash
   # Activate virtual environment
   source venv/bin/activate
   
   # Update Python packages
   pip install -r requirements.txt --upgrade
   
   # Verify installation
   pip check
   ```

4. **Run Database Migrations** (if applicable)
   ```bash
   # Backup before migration
   python scripts/backup_database.py
   
   # Run migrations
   alembic upgrade head
   
   # Verify migration
   alembic current
   ```

5. **Update Configuration**
   ```bash
   # Copy production config
   cp config/production.yaml.new config/production.yaml
   
   # Validate configuration
   python -c "import yaml; yaml.safe_load(open('config/production.yaml'))"
   ```

6. **Restart Services**
   ```bash
   # Restart application
   systemctl restart omega-quant
   
   # Verify service status
   systemctl status omega-quant
   ```

7. **Re-enable Scheduled Jobs**
   ```bash
   # Restore crontab
   crontab backups/crontab_backup.txt
   
   # Verify cron jobs
   crontab -l
   ```

#### Phase 3: Validation (T+15 minutes)

1. **Health Check**
   ```bash
   python scripts/health_check.py --config config/production.yaml
   ```

2. **Smoke Tests**
   ```bash
   # Test data loading
   python -c "from omega.data.data_loader import DataLoader; dl = DataLoader({}); print('Data loader OK')"
   
   # Test portfolio manager
   python -c "from omega.core.portfolio_manager import PortfolioManager; pm = PortfolioManager({}); print('Portfolio manager OK')"
   
   # Test risk manager
   python -c "from omega.core.risk_manager import RiskManager; rm = RiskManager({}); print('Risk manager OK')"
   ```

3. **Verify Logs**
   ```bash
   # Check for errors
   tail -n 100 logs/omega_quant.log | grep -i error
   
   # Check application logs
   journalctl -u omega-quant -n 50 --no-pager
   ```

4. **Test Daily Run** (dry run with T-1 lag)
   ```bash
   # IMPORTANT: Use T-1 date (yesterday) to enforce PIT safety
   python scripts/run_daily.py --config config/production.yaml --date $(date -d "yesterday" +%Y-%m-%d)
   
   # Or let script default to T-1 automatically
   python scripts/run_daily.py --config config/production.yaml
   ```

---

## Post-Deployment Validation

### Immediate Validation (T+30 minutes)

- [ ] All services running
- [ ] No error logs
- [ ] Health check passing
- [ ] Metrics being collected
- [ ] Alerts configured

### Extended Validation (T+24 hours)

- [ ] Daily rebalance completed successfully
- [ ] Performance metrics within expected range
- [ ] No data quality issues
- [ ] Risk checks functioning
- [ ] Audit logs being written

### Weekly Review (T+7 days)

- [ ] System stability confirmed
- [ ] Performance benchmarks met
- [ ] No regression issues
- [ ] User feedback collected
- [ ] Lessons learned documented

---

## Rollback Procedures

### When to Rollback

Initiate rollback if:
- Critical bugs discovered in production
- Data integrity issues detected
- Performance degradation > 50%
- Risk management failures
- Compliance violations

### Rollback Steps

1. **Assess Situation**
   ```bash
   # Check system status
   python scripts/health_check.py --config config/production.yaml
   
   # Review recent logs
   tail -n 500 logs/omega_quant.log
   ```

2. **Verify Rollback Point**
   ```bash
   # List available rollback points
   python scripts/rollback.py --list
   
   # Verify target rollback point
   python scripts/rollback.py --date YYYY-MM-DD --verify-only
   ```

3. **Execute Rollback**
   ```bash
   # Stop services
   systemctl stop omega-quant
   
   # Execute rollback
   python scripts/rollback.py --date YYYY-MM-DD
   
   # Restore previous code version
   git checkout tags/v1.0.0  # or previous stable tag
   
   # Restore dependencies
   pip install -r requirements.txt
   
   # Restart services
   systemctl start omega-quant
   ```

4. **Validate Rollback**
   ```bash
   # Health check
   python scripts/health_check.py --config config/production.yaml
   
   # Verify portfolio state
   python -c "import pandas as pd; df = pd.read_csv('data/holdings/current.csv'); print(f'Positions: {len(df)}')"
   ```

5. **Notify Stakeholders**
   - Send rollback notification
   - Update incident report
   - Schedule post-mortem

---

## Monitoring & Alerts

### Key Metrics to Monitor

1. **System Health**
   - CPU usage < 80%
   - Memory usage < 80%
   - Disk space > 20% free
   - Service uptime > 99.9%

2. **Application Performance**
   - Daily rebalance completion time < 5 minutes
   - Data load time < 30 seconds
   - Signal generation time < 10 seconds
   - Portfolio construction time < 5 seconds

3. **Trading Metrics**
   - Number of positions (target: 30-50)
   - Portfolio volatility < 20%
   - Daily P&L within expected range
   - Order fill rate > 95%

4. **Data Quality**
   - Missing data < 5%
   - Data freshness < 24 hours
   - PIT safety violations = 0
   - Outliers < 1%

### Alert Thresholds

| Severity | Condition | Response Time |
|----------|-----------|---------------|
| **Critical** | System down, data corruption, PIT violation | Immediate (< 15 min) |
| **High** | Performance degradation > 50%, risk limit breach | < 1 hour |
| **Medium** | Data quality issues, minor bugs | < 4 hours |
| **Low** | Performance degradation < 25%, warnings | < 24 hours |

### Alert Channels

- **Critical**: PagerDuty + Phone + Email + Slack
- **High**: Email + Slack
- **Medium**: Email
- **Low**: Daily digest email

---

## Troubleshooting

### Common Issues

#### Issue: Daily Rebalance Fails

**Symptoms:**
- Script exits with error
- No portfolio.csv generated
- Error logs show exceptions

**Diagnosis:**
```bash
# Check logs
tail -n 200 logs/omega_quant.log | grep -i error

# Run with debug logging
OMEGA_LOG_LEVEL=DEBUG python scripts/run_daily.py --config config/production.yaml
```

**Resolution:**
1. Check data availability
2. Verify configuration
3. Check disk space
4. Review risk limits
5. Contact on-call engineer if unresolved

#### Issue: PIT Safety Violation

**Symptoms:**
- Health check fails on PIT safety
- Future data detected in dataset

**Diagnosis:**
```bash
# Run PIT safety check
python -c "from omega.data.data_loader import DataLoader; dl = DataLoader({}); dl.validate_pit_safety()"
```

**Resolution:**
1. **STOP ALL TRADING IMMEDIATELY**
2. Identify source of future data leak
3. Purge contaminated data
4. Restore from clean backup
5. Re-run validation
6. Document incident for compliance

**Note:** As of Phase 10, the `--skip-checks` flag has been REMOVED from `run_daily.py` to enforce mandatory PIT safety validation. All runs now default to T-1 lag (yesterday's date) unless explicitly overridden.

#### Issue: High Memory Usage

**Symptoms:**
- Memory usage > 90%
- System slowdown
- OOM errors

**Diagnosis:**
```bash
# Check memory usage
free -h
ps aux --sort=-%mem | head -n 10

# Profile memory
python scripts/profile_performance.py --memory-profile
```

**Resolution:**
1. Reduce chunk size in config
2. Clear cache: `rm -rf data/cache/*`
3. Restart services
4. Consider increasing system memory

---

## Emergency Contacts

### On-Call Rotation

| Role | Primary | Backup | Phone |
|------|---------|--------|-------|
| **DevOps Lead** | [Name] | [Name] | [Phone] |
| **Quant Lead** | [Name] | [Name] | [Phone] |
| **Risk Manager** | [Name] | [Name] | [Phone] |
| **Compliance Officer** | [Name] | [Name] | [Phone] |

### Escalation Path

1. **Level 1**: On-call engineer (0-30 min)
2. **Level 2**: Team lead (30-60 min)
3. **Level 3**: Director of Engineering (60+ min)
4. **Level 4**: CTO (critical incidents only)

### External Contacts

- **Broker Support**: [Phone/Email]
- **Data Provider Support**: [Phone/Email]
- **Cloud Provider Support**: [Phone/Email]
- **Legal Counsel**: [Phone/Email]

---

## Appendix

### A. Deployment Checklist Template

```
Deployment Date: _______________
Deployment Type: [ ] Hotfix [ ] Standard [ ] Major
Deployed By: _______________
Reviewed By: _______________

Pre-Deployment:
[ ] Tests passing
[ ] Config validated
[ ] Backups created
[ ] Approvals obtained

Deployment:
[ ] Code deployed
[ ] Services restarted
[ ] Health check passed

Post-Deployment:
[ ] Smoke tests passed
[ ] Monitoring active
[ ] Stakeholders notified

Sign-off:
Engineer: _______________ Date: _______________
QA: _______________ Date: _______________
Risk: _______________ Date: _______________
```

### B. Incident Report Template

```
Incident ID: _______________
Date/Time: _______________
Severity: [ ] Critical [ ] High [ ] Medium [ ] Low

Description:
_______________________________________________

Impact:
_______________________________________________

Root Cause:
_______________________________________________

Resolution:
_______________________________________________

Lessons Learned:
_______________________________________________

Action Items:
1. _______________________________________________
2. _______________________________________________
3. _______________________________________________
```

### C. Change Log Format

```
## [Version] - YYYY-MM-DD

### Added
- New features

### Changed
- Changes to existing functionality

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Fixed
- Bug fixes

### Security
- Security updates
```

---

**Document Control:**
- **Version History**: See git log
- **Review Frequency**: Quarterly
- **Next Review Date**: 2026-08-11
- **Document Owner**: DevOps Team

---

*End of Document*
