"""S6: Safe evaluation utility (PRD v5.7 §31.6).

One API issue: `model/ratio.go` uses eval to parse ratio expressions.
Fix: Provide safe expression evaluator with restricted environment.

This module provides a secure alternative to Python's eval()/exec()
for evaluating simple mathematical expressions (like ratio calculations)
without allowing arbitrary code execution.
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Any, Dict

# Safe operators for mathematical expressions
_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval_ratio(expression: str, variables: Dict[str, float] | None = None) -> float:
    """Safely evaluate a mathematical expression for ratio/rate calculations.

    Only allows basic arithmetic operations (+, -, *, /, **, %) and
    numeric literals. No function calls, no attribute access, no imports.

    Args:
        expression: Mathematical expression string (e.g., "1.5 * tokens / 1000")
        variables: Optional dict of allowed variable names → numeric values

    Returns:
        The evaluated numeric result.

    Raises:
        ValueError: If the expression contains unsafe constructs.
        ZeroDivisionError: If division by zero occurs.
    """
    if not expression or not expression.strip():
        raise ValueError("Expression cannot be empty")

    # Strip whitespace
    expr = expression.strip()

    # Quick reject: no function calls allowed
    if re.search(r'\w+\s*\(', expr):
        raise ValueError(f"Function calls not allowed in expression: {expr}")

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {e}")

    return _eval_node(tree.body, variables or {})


def _eval_node(node: ast.AST, variables: Dict[str, float]) -> float:
    """Recursively evaluate an AST node."""
    # Number literal
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)

    # Variable reference
    if isinstance(node, ast.Name):
        if node.id in variables:
            return float(variables[node.id])
        raise ValueError(f"Unknown variable: {node.id}")

    # Binary operation
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        return float(_SAFE_OPERATORS[op_type](left, right))

    # Unary operation
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = _eval_node(node.operand, variables)
        return float(_SAFE_OPERATORS[op_type](operand))

    raise ValueError(f"Unsupported expression construct: {type(node).__name__}")


# ---------------------------------------------------------------------------
# Sanitize dynamic import (PRD v5.7 §31.6 — replace __import__ with safe pattern)
# ---------------------------------------------------------------------------

def safe_import_module(module_path: str, attribute: str = "") -> Any:
    """Safely import a module and optionally an attribute.

    Replaces __import__(...) patterns with a validated import.
    Only allows whitelisted module prefixes.

    Args:
        module_path: Dot-separated module path (e.g., "core.events.event_bus")
        attribute: Optional attribute name to get from the module.

    Returns:
        The imported module or attribute.

    Raises:
        ImportError: If the module is not in the whitelist.
    """
    # Whitelist of allowed module prefixes
    ALLOWED_PREFIXES = ("core.", "plugins.", "sdk.", "cli.")

    if not any(module_path.startswith(p) for p in ALLOWED_PREFIXES):
        raise ImportError(
            f"Module '{module_path}' is not in the allowed import whitelist. "
            f"Allowed prefixes: {ALLOWED_PREFIXES}"
        )

    import importlib

    module = importlib.import_module(module_path)

    if attribute:
        if not hasattr(module, attribute):
            raise ImportError(
                f"Attribute '{attribute}' not found in module '{module_path}'"
            )
        return getattr(module, attribute)

    return module
