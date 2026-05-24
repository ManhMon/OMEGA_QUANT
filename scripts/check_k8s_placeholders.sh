#!/usr/bin/env bash
# check_k8s_placeholders.sh
# ─────────────────────────────────────────────────────────────────────────────
# SOD-01 remediation (L3 audit role21_phase24_mlops_audit_20260524)
#
# Scans infra/kubernetes/ for unreplaced template placeholders of the form
# <UPPER_CASE_OR_MIXED> and fails the pipeline if any are found.
#
# Usage:
#   bash scripts/check_k8s_placeholders.sh
#
# Exit codes:
#   0 — no placeholders found (safe to deploy)
#   1 — placeholders found (block deploy)
#
# Add to CI (GitHub Actions example):
#   - name: Check K8s placeholders
#     run: bash scripts/check_k8s_placeholders.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SEARCH_DIR="${1:-infra/kubernetes}"
# Matches <WORD> and <WORD_WORD> — strict uppercase placeholder pattern (no colon variant)
PLACEHOLDER_PATTERN='<[A-Z][A-Z0-9_]+>'

echo "[check_k8s_placeholders] Scanning: ${SEARCH_DIR}"
echo "[check_k8s_placeholders] Pattern:  ${PLACEHOLDER_PATTERN}"
echo ""

# grep -rn: recursive, print line numbers
# --include: only yaml files
# || true: don't exit on grep finding nothing (exit 1 from grep means no match)
# grep -v '<SEALED:': exclude sealed secret placeholders (already encrypted)
# grep -vE ':[0-9]+:\s*#': exclude YAML comment lines (anchored to grep -rn output format "file:line:content")
MATCHES=$(grep -rn \
    --include="*.yaml" \
    --include="*.yml" \
    -E "${PLACEHOLDER_PATTERN}" \
    "${SEARCH_DIR}" \
    | grep -v '<SEALED:' \
    | grep -vE ':[0-9]+:\s*#' \
    || true)

if [[ -z "${MATCHES}" ]]; then
    echo "[check_k8s_placeholders] PASS — no unreplaced placeholders found."
    exit 0
fi

echo "[check_k8s_placeholders] FAIL — unreplaced placeholders detected:"
echo ""
echo "${MATCHES}"
echo ""
echo "[check_k8s_placeholders] ACTION REQUIRED:"
echo "  Replace all <PLACEHOLDER> values before deploying."
echo "  For Seldon manifests: build the model image, then substitute"
echo "  <MODEL_IMAGE>, <MODEL_VERSION>, <RUN_ID>, <MODEL_NAME> via"
echo "  envsubst or your CI pipeline's secret injection step."
echo ""
echo "  For SealedSecret templates: run kubeseal to generate encrypted"
echo "  values and replace <SEALED:*> placeholders."
exit 1
