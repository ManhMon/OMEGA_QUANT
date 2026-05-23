# TEAM ARCHITECTURE - OMEGA_QUANT (Per Institutional Engineering Spec v1.0)

**Version**: 2.3
**Status**: R8 (Backend Engineer Role 9 - Audit Findings Fix)
**Last Updated**: 2026-05-10
**Reference**: omega_quant_ai_institutional_engineering_spec_full.md Section 17

---

## EXECUTIVE SUMMARY

OMEGA_QUANT operates as a **25-role agent system** organized into L1 (Orchestrator), L2 (Build/Code), and L3 (Audit/Review) tiers. 

**Core Principle**: Specialization with clear ownership. Every decision is traceable to a role, a task, and an audit log. SOD is strictly enforced.

---

## TIER 1: L1 (Ly) - Orchestrator & Management (5 Roles)

### 1.1 Project Manager (Role 1)
**Platform**: Ly (L1)
**Responsibilities**:
- Strategic orchestration of all roles
- Resource allocation and prioritization
- Final gate decision for deployment
- Human interface for critical decisions
**Constraints**:
- ❌ Cannot write code
- ✅ Can read all files, make decisions, spawn tasks

### 1.2 Product Owner (Role 2)
**Platform**: Ly (L1)
**Responsibilities**:
- Feature prioritization
- Stakeholder alignment
- Requirements gathering
**Constraints**:
- ❌ Cannot make architectural decisions
- ✅ Can define product scope

### 1.3 Scrum Master (Role 3)
**Platform**: Ly (L1)
**Responsibilities**:
- Agile process management
- Blocker removal
- Sprint planning
**Constraints**:
- ❌ Cannot implement code
- ✅ Can manage team workflow

### 1.4 Release Manager (Role 4)
**Platform**: Ly (L1)
**Responsibilities**:
- Release coordination
- Deployment gates
- Versioning strategy
**Constraints**:
- ❌ Cannot approve final code review
- ✅ Can gate releases

### 1.5 Delivery Manager (Role 5)
**Platform**: Ly (L1)
**Responsibilities**:
- Timeline tracking
- Resource management
- Risk mitigation at project level
**Constraints**:
- ❌ Cannot write quant logic
- ✅ Can adjust delivery schedules

---

## TIER 2: L2 (OpenCode) - Build, Code, Design (11 Roles)

### 2.1 System Architect (Role 6)
**Platform**: OpenCode (L2)
**Responsibilities**:
- System design
- Interface definition
- Review module boundaries

### 2.2 Tech Lead (Role 7)
**Platform**: OpenCode (L2)
**Responsibilities**:
- Technical leadership
- Code standards enforcement
- Coordinate implementation

### 2.3 Frontend Engineer (Role 8)
**Platform**: OpenCode (L2)
**Responsibilities**:
- UI/UX implementation
- Component building

### 2.4 Backend Engineer (Role 9)
**Platform**: OpenCode (L2)
**Responsibilities**:
- API implementation
- Core business logic

### 2.5 Database Admin (Role 10)
**Platform**: OpenCode (L2)
**Responsibilities**:
- Schema design
- DB performance tuning

### 2.6 DevOps Engineer (Role 11)
**Platform**: OpenCode (L2)
**Responsibilities**:
- CI/CD pipelines
- Automation

### 2.7 Cloud Infra Engineer (Role 12)
**Platform**: OpenCode (L2)
**Responsibilities**:
- Infrastructure as Code (IaC)
- Cloud resource provisioning

### 2.8 UI/UX Integrator (Role 13)
**Platform**: OpenCode (L2)
**Responsibilities**:
- Styling and layout
- User experience consistency

### 2.9 Data Scientist (Role 14)
**Platform**: OpenCode (L2)
**Responsibilities**:
- Alpha discovery
- Signal research

### 2.10 Data Engineer (Role 15)
**Platform**: OpenCode (L2)
**Responsibilities**:
- Data pipeline construction
- ETL processes

### 2.11 Machine Learning Eng (Role 16)
**Platform**: OpenCode (L2)
**Responsibilities**:
- Model training pipelines
- Feature engineering

---

## TIER 3: L3 (Codex) - Audit, Review, Security (9 Roles)

### 3.1 QA Engineer (Role 17)
**Platform**: Codex (L3)
**Responsibilities**:
- Functional testing execution and validation (AUDIT ONLY)
- Acceptance testing validation (AUDIT ONLY)
**Constraints**:
- ❌ NO test writing or implementation
- ✅ Execute and validate tests only

### 3.2 SDET (Role 18)
**Platform**: Codex (L3)
**Responsibilities**:
- Test automation execution and validation (AUDIT ONLY)
- Test framework audit and review (AUDIT ONLY)
- ❌ NO test writing or test framework development (moved to Role 11 DevOps Engineer or Role 9 Backend Engineer)

### 3.3 Security Auditor (Role 19)
**Platform**: Codex (L3)
**Responsibilities**:
- Security scanning and audit (AUDIT ONLY)
- Secrets management check (AUDIT ONLY)
**Constraints**:
- ❌ NO security fixes or implementation
- ✅ Audit and report only

### 3.4 Compliance Officer (Role 20)
**Platform**: Codex (L3)
**Responsibilities**:
- PIT safety checks (AUDIT ONLY)
- Institutional standards compliance validation (AUDIT ONLY)
**Constraints**:
- ❌ NO compliance fixes or implementation
- ✅ Validate and report only

### 3.5 Code Reviewer (Role 21)
**Platform**: Codex (L3)
**Responsibilities**:
- Peer reviews (AUDIT ONLY)
- Final audit reports (AUDIT ONLY)
**Constraints**:
- ❌ NO code fixes or implementation
- ✅ Review and report only

### 3.6 Penetration Tester (Role 22)
**Platform**: Codex (L3)
**Responsibilities**:
- Adversarial security testing (AUDIT ONLY)
**Constraints**:
- ❌ NO security fixes or implementation
- ✅ Test and report only

### 3.7 Performance Tester (Role 23)
**Platform**: Codex (L3)
**Responsibilities**:
- Load and stress testing (AUDIT ONLY)
- Bottleneck identification (AUDIT ONLY)
**Constraints**:
- ❌ NO performance fixes or implementation
- ✅ Test and report only

### 3.8 UAT Validator (Role 24)
**Platform**: Codex (L3)
**Responsibilities**:
- User acceptance criteria validation (AUDIT ONLY)
**Constraints**:
- ❌ NO feature implementation or fixes
- ✅ Validate and report only

### 3.9 IT Systems Auditor (Role 25)
**Platform**: Codex (L3)
**Responsibilities**:
- Comprehensive system audit (AUDIT ONLY)
- Governance reporting (AUDIT ONLY)
**Constraints**:
- ❌ NO system fixes or implementation
- ✅ Audit and report only

---

## WORKFLOW MODEL (L1 -> L2 -> L3)

1. **Ly (L1)**: Receives request, categorizes task, and dispatches to a specialist role.
2. **OpenCode (L2)**: Receives implementation, refactor, and code tasks. Outputs normative artifacts.
3. **Codex (L3)**: Receives production audit and review tasks. Outputs audit reports.
4. **Audit Cycle**: Every change to normative artifacts must be audited by a Review/Critic Agent on Codex (L3).

---

## STATE PERSISTENCE

All agents must store state in `.ly_state/session/`:
- `active_tasks.json`
- `agent_locks.json`
- `context_cache.json`
- `.ly_state/session/audit_log.jsonl`

---

## SUCCESS CRITERIA

1. **Strict Isolation**: Agents must not see context outside their assigned task.
2. **Segregation of Duties (SOD)**: Implementation agent cannot audit their own work.
3. **Verification-First**: Tests must be implemented alongside or before production code.
4. **Point-In-Time (PIT) Safety**: All quant features must enforce T-1 lag.

**Version**: 2.3
**Last Updated**: 2026-05-10
**Status**: Pending Independent Codex R7 Audit
