# IMPLEMENTATION CONTRACT CHECKLIST (Spec v1.0)

**Purpose**: Enforce `omega_quant_ai_line_by_line_implementation_contracts_v1.md` during implementation/audit.
**Owner**: Ly (L1) + Codex Review/Test roles (L3)
**Status**: Active
**Version**: SemVer (Matches governing spec version)

---

## 0) Usage Rule (Mandatory)
- Impl session must fill checklist before requesting audit.
- Audit session must verify checklist evidence, not trust declarations.
- Missing P0/P1 item => verdict `[NEEDS_FIX]`.

---

## 1) Global Principles Gate

### P0 (Hard Fail)
- [ ] Verification-first: tests executed and passed for changed scope.
- [ ] Contract-first: contract exists before implementation.
- [ ] No leakage: no look-ahead, no data leakage, PIT/T-1 enforced where applicable.
- [ ] Recovery by design: retry/rollback/checkpoint behavior documented.

### P1
- [ ] Resource-aware: complexity/memory/runtime budget documented.
- [ ] Observability by default: logs/metrics/trace fields present.
- [ ] Version constraint: aligns with governing specification semantic version.

Evidence:
- Test run artifact:
- Contract artifact:
- PIT proof artifact:
- Checkpoint/Rollback artifact:

---

## 2) File-Level Contract Gate (One file, one responsibility)

For each changed file:
- [ ] File has single primary responsibility.
- [ ] File header contract present with fields:
  - [ ] Purpose
  - [ ] Spec reference
  - [ ] Owner agent
  - [ ] Inputs
  - [ ] Outputs
  - [ ] Dependencies
  - [ ] Side effects
  - [ ] Failure modes
  - [ ] Tests
- [ ] If file is re-export only, explicitly marked.
- [ ] If file has IO/network/DB, side effects explicitly declared.
- [ ] No circular dependency introduced.

Evidence (file paths + lines):

---

## 3) Class-Level Contract Gate (One class, one contract)

For each changed class:
- [ ] Responsibilities / Non-responsibilities defined.
- [ ] State and invariants explicit.
- [ ] Constructor only initializes dependencies/invariants.
- [ ] Lifecycle explicit.
- [ ] Failure modes documented.
- [ ] Tests mapped to class contract.

Evidence (class names + tests):

---

## 4) Function-Level Contract Gate (One function, one behavior)

For each changed function:
- [ ] Signature explicit.
- [ ] Inputs/Outputs explicit.
- [ ] Preconditions/Postconditions documented.
- [ ] Exceptions documented.
- [ ] Side effects documented.
- [ ] Complexity/Idempotency/Retryability documented (when relevant).
- [ ] No hidden IO/global mutable state.

Evidence (function names + docstrings/tests):

---

## 5) Event/Schema Boundary Gate

- [ ] Module boundaries explicit via schema/interface.
- [ ] Event/schema has proper semantic versioning according to governing specs.
- [ ] Event correlation/trace fields present where required.
- [ ] Backward-compatibility impact assessed.

Evidence:

---

## 6) Test Contract Gate

- [ ] Unit tests for changed behavior.
- [ ] Integration tests for boundary behavior.
- [ ] PIT/leakage tests for quant path.
- [ ] Negative/error-path tests.
- [ ] Coverage for changed lines/functions acceptable.
- [ ] Test results attached.

Evidence:
- pytest command:
- result summary:
- coverage summary:

---

## 7) Side-Effect & Safety Gate

- [ ] All side effects listed in contract.
- [ ] Security-sensitive operations sandboxed/policy-compliant.
- [ ] Rollback path verified.
- [ ] Checkpoint path verified.

Evidence:

---

## 8) SOD + Isolation Gate

- [ ] Impl session label valid: `[L2-Impl:*]` or `[L3-Impl:*]`.
- [ ] Audit session label valid: `[L3-Audit:*]`.
- [ ] Writer != Auditor session.
- [ ] Audit role is read-only on code/docs.
- [ ] Spawn prompt contained Hard Blindness Rule.

Evidence:
- impl session id:
- audit session id:
- spawn command excerpt:

---

## 9) 6-Gate Progress Record

Update `.ly_state/session/phase_gates.json`:
- [ ] Architecture
- [ ] Review
- [ ] Test
- [ ] Risk
- [ ] Security
- [ ] Deployment

Final:
- [ ] `final_verdict` set
- [ ] `final_decision_by` set
- [ ] `final_decision_timestamp` set

---

## 10) Audit Verdict Template

```text
[Role]: <Role 16 Review | Role 20 Critic>
[Verdict]: [APPROVED] | [NEEDS_FIX]
[PIT Safety]: PASS | FAIL
[Role Compliance]: PASS | FAIL
[Findings]:
- P0:
- P1:
- P2:
[Required Fixes]:
- ...
[Evidence]:
- file:line
- test output ref
```

---

## 11) Quick Reject Rules

Immediate `[NEEDS_FIX]` if any:
- No contract for changed file/class/function.
- Test missing or failing.
- Hidden side effect detected.
- Invalid semantic versioning or version mismatch with specs.
- SOD violation (self-approval or shared impl/audit session).
- Missing Hard Blindness Rule in spawn payload.

---

## 12) Change Log
- v1.0.0: Initial checklist aligned to both specs and current orchestration rules.


