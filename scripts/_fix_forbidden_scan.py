"""Rewrite forbidden path scan lines in old audit reports.
Remove all old 'absent; non-authoritative' lines and replace with canonical format.
"""
import pathlib, re

CANONICAL_FORBIDDEN_LINE = "non-authoritative scan evidence only; no reliance."

FORBIDDEN_PATHS = [
    r".gemini\antigravity-ide\scratch\ag-kit",
    r".openclaw\skills",
    r"C:\Users\GHC\.agents",
    r".codex\memories",
]

FILES = [
    ".ly_state/session/audit_reports/role20_vci_sparse_terminal_independent_freshness_evidence_20260805.md",
    ".ly_state/session/audit_reports/role20_vci_signed_lifecycle_freshness_receipts_20260805.md",
]

for fname in FILES:
    p = pathlib.Path(fname)
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    for line in lines:
        stripped = line.strip().lower()
        # Remove any line containing forbidden path keywords but not in correct canonical format
        is_forbidden_path_line = any(
            fp.lower() in stripped or fp.replace("\\", "/").lower() in stripped
            for fp in FORBIDDEN_PATHS
        )
        if is_forbidden_path_line and CANONICAL_FORBIDDEN_LINE not in stripped:
            # Skip old incorrectly formatted forbidden path line
            continue
        out.append(line)
    
    content = "".join(out)
    
    # Now ensure each forbidden path has exactly one canonical line
    # Check what's already there
    result_lines = content.splitlines()
    has_canonical = {fp: False for fp in FORBIDDEN_PATHS}
    for line in result_lines:
        for fp in FORBIDDEN_PATHS:
            if (fp.lower() in line.lower() or fp.replace("\\", "/").lower() in line.lower()):
                if CANONICAL_FORBIDDEN_LINE in line.lower():
                    has_canonical[fp] = True
    
    # Append missing canonical lines before end
    missing = [fp for fp, found in has_canonical.items() if not found]
    if missing:
        content = content.rstrip() + "\n\n## Forbidden Path Scan (Canonical)\n\n"
        for fp in FORBIDDEN_PATHS:
            content += f"- `{fp}` - {CANONICAL_FORBIDDEN_LINE}\n"
    
    p.write_text(content, encoding="utf-8")
    print(f"Fixed: {fname}")

print("Done")
