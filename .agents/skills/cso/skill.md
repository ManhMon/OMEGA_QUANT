---
name: cso
description: Security-audit guidance for signed receipts, secret handling, integrity controls, and fail-closed verification.
when_to_use: "When auditing security-sensitive workflows, signed receipts, secrets, integrity checks, or failure handling."
allowed-tools: Read, Glob, Grep, Bash
---

# CSO Security Audit

## Signed Receipts

- Verify receipt signatures against a trusted public key and expected algorithm.
- Bind signature verification to the complete canonical payload, issuer, subject, timestamp, nonce, and gate or artifact identifier.
- Reject missing, malformed, expired, replayed, unverifiable, or mismatched receipts.
- Record verification outcome and non-secret identifiers; never log signature material or private keys.

## Secret Handling

- Never hardcode, commit, echo, or include secrets in reports, logs, exceptions, fixtures, or receipts.
- Load secrets only from approved runtime secret stores with least-privilege access.
- Redact secrets before persistence and fail deployment or audit checks when secret exposure is detected.

## Integrity Controls

- Verify trusted source, expected path, digest, and signature before accepting artifacts or audit evidence.
- Treat absent, unreadable, altered, or ambiguous evidence as invalid.
- Pin trusted identities and algorithms; reject downgrade or substitution attempts.

## Fail-Closed Rules

- Deny approval, access, execution, or promotion when validation cannot complete.
- Do not replace failed verification with defaults, warnings, retries that bypass limits, or manual approval.
- Emit actionable non-secret errors and preserve evidence for independent review.

## Audit Checklist

- [ ] Receipt signature, identity, freshness, replay protection, and payload binding verified.
- [ ] Secrets absent from source, logs, reports, and artifacts.
- [ ] Artifact and evidence integrity verified from trusted inputs.
- [ ] Invalid or unavailable validation fails closed.
