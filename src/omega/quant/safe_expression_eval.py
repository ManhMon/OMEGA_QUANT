"""
OMEGA_QUANT Safe Expression Evaluator
======================================
EXEC-01 FIX: Replace eval() with AST-validated expression evaluation.

Parses expressions into AST and validates against a strict allowlist of
safe node types before evaluation. This prevents code injection and
sandbox escape in alpha expression evaluation.

Author: System Architect (Role 06)
Date: 2026-06-13
Gate: REMAINING_PHASES_AND_ORPHAN_CODE_DEEP_AUDIT_FIX1_20260613
"""

from __future__ import annotations

import ast
from typing import Any, Dict, Set


# ---------------------------------------------------------------------------
# AST Node Allowlist
# ---------------------------------------------------------------------------

# Node types considered safe for expression evaluation.
# This list is intentionally restrictive — any node type not listed is
# rejected before eval.
#
# Python 3.14 compatibility: ast.Num, ast.Str, and ast.NameConstant were
# removed (deprecated since 3.8, all merged into ast.Constant).  We guard
# with getattr so the allowlist is valid on every supported Python version.
_ALLOWED_NODE_TYPES: Set[type] = set()

def _build_allowlist() -> Set[type]:
    """Build the AST node allowlist, compatible with the running Python version."""
    types: Set[type] = {
        # Top-level
        ast.Expression,
        ast.Module,
        # Expressions
        ast.BinOp,
        ast.UnaryOp,
        ast.BoolOp,
        ast.Compare,
        ast.Call,
        ast.IfExp,  # ternary
        ast.Attribute,
        ast.Subscript,
        ast.Slice,
        ast.Name,
        ast.Constant,    # Python 3.8+ (sole literal node in 3.14)
        ast.Tuple,
        ast.List,
        # Operators
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.Not,
        ast.And,
        ast.Or,
        # Comparisons
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.Is,
        ast.IsNot,
        ast.In,
        ast.NotIn,
        # Context nodes (implicit in Name, Subscript, Attribute, etc.)
        ast.Load,
        ast.Store,
        ast.Del,
    }
    # Legacy node types removed in Python 3.14 (deprecated since 3.8).
    # Only add them if the running interpreter still exposes them.
    _legacy = ("Num", "Str", "NameConstant", "Index")
    for _name in _legacy:
        _cls = getattr(ast, _name, None)
        if _cls is not None:
            types.add(_cls)
    return types

_ALLOWED_NODE_TYPES = _build_allowlist()


class ExpressionRejected(Exception):
    """Raised when an expression contains disallowed AST nodes."""
    pass


def _validate_ast(node: ast.AST, depth: int = 0) -> None:
    """
    Recursively validate that every AST node is in the allowlist.

    Args:
        node: The AST node to validate.
        depth: Current recursion depth (guard against pathological input).

    Raises:
        ExpressionRejected: If any node is not in the allowlist.
    """
    if depth > 200:
        raise ExpressionRejected("Expression too deeply nested (max 200 levels)")

    if type(node) not in _ALLOWED_NODE_TYPES:
        raise ExpressionRejected(
            f"Disallowed expression element: {type(node).__name__}"
        )

    for child in ast.iter_child_nodes(node):
        _validate_ast(child, depth=depth + 1)


def safe_eval_expression(
    expression: str,
    globals_dict: Dict[str, Any],
    locals_dict: Dict[str, Any],
) -> Any:
    """
    Safely evaluate a mathematical/data expression using AST validation.

    The expression is parsed into an AST, validated against a strict
    allowlist of node types, and only then evaluated with the provided
    globals and locals dictionaries.

    Args:
        expression: The expression string to evaluate.
        globals_dict: Global namespace (should have __builtins__ = {}).
        locals_dict: Local namespace with safe functions and data variables.

    Returns:
        The result of evaluating the expression.

    Raises:
        ExpressionRejected: If the expression contains disallowed constructs.
        ValueError: If the expression cannot be evaluated.
    """
    # Strip leading/trailing whitespace
    expression = expression.strip()

    if not expression:
        raise ExpressionRejected("Empty expression")

    # Block common injection patterns before AST parse
    _block_dangerous_patterns(expression)

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ExpressionRejected(f"Invalid expression syntax: {e}") from e

    _validate_ast(tree)

    try:
        return eval(compile(tree, "<alpha_expr>", "eval"), globals_dict, locals_dict)
    except Exception as e:
        raise ValueError(f"Expression evaluation failed: {expression!r}: {e}") from e


def _block_dangerous_patterns(expression: str) -> None:
    """
    Pre-AST block for known dangerous string patterns.

    This is a defense-in-depth layer — even if AST validation were somehow
    bypassed, these string patterns would still be caught.
    """
    lowered = expression.lower()
    dangerous = [
        "import", "__import__", "exec(", "exec ",
        "compile(", "compile ", "eval(", "eval ",
        "open(", "open ", "getattr", "setattr", "delattr",
        "globals", "locals", "vars", "dir(",
        "__builtins__", "__subclasses__", "__bases__", "__mro__",
        "__class__", "__init__", "__new__",
        "lambda ", "lambda:",
    ]
    for pattern in dangerous:
        if pattern in lowered:
            raise ExpressionRejected(
                f"Expression contains disallowed pattern: {pattern!r}"
            )
