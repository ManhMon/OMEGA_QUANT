"""Gate verdict utilities for walk-forward validation."""
from __future__ import annotations


def _is_gate_verdict_pass(verdict) -> bool:
    """Check if a gate verdict represents a pass.

    Parameters
    ----------
    verdict : any
        Gate verdict value from validate_research_gate() result dict.

    Returns
    -------
    bool
        True if verdict is a pass, False otherwise.

    Notes
    -----
    Pass conditions:
    - Boolean True
    - String exactly matching "PASS" or "APPROVED" (case-insensitive)

    Fail conditions:
    - Boolean False
    - String starting with "FAIL", "REJECT", "NEEDS_FIX" (case-insensitive)
    - None, empty string, or missing value
    - Any other string not explicitly recognized as pass

    This prevents truthiness bugs where non-empty fail strings like
    "FAIL: insufficient samples" are incorrectly treated as pass.
    """
    # Boolean True is pass
    if verdict is True:
        return True

    # Boolean False, None, or missing is fail
    if verdict is False or verdict is None:
        return False

    # String verdict: check for explicit pass/fail markers
    if isinstance(verdict, str):
        verdict_upper = verdict.strip().upper()

        # Empty string is fail
        if not verdict_upper:
            return False

        # Explicit pass markers
        if verdict_upper in ("PASS", "APPROVED"):
            return True

        # Explicit fail markers
        if verdict_upper.startswith(("FAIL", "REJECT", "NEEDS_FIX")):
            return False

        # Any other string is treated as fail (conservative)
        return False

    # Any other type is treated as fail
    return False
