"""Deprecated compatibility shim. Use :mod:`omega.data.sanitizer`."""
from .sanitizer import DataValidator, ValidationIssue

__all__ = ["DataValidator", "ValidationIssue"]
