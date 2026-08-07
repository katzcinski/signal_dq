# [ENGINE-FROZEN] — regex-based parser, no eval()
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Canonical grammar patterns
# ---------------------------------------------------------------------------
_NUM = r"-?\d+(?:\.\d+)?"
_OP = r"[><!]?=|[><]"

_PAT_CMP = re.compile(rf"^({_OP})\s*({_NUM})$", re.IGNORECASE)
_PAT_BETWEEN = re.compile(
    rf"^BETWEEN\s+({_NUM})\s+AND\s+({_NUM})$", re.IGNORECASE
)
_PAT_DELTA = re.compile(
    rf"^DELTA\s+({_OP})\s*({_NUM})\s*%$", re.IGNORECASE
)
_PAT_IS_NULL = re.compile(r"^IS\s+NULL$", re.IGNORECASE)
_PAT_IS_NOT_NULL = re.compile(r"^IS\s+NOT\s+NULL$", re.IGNORECASE)
_PAT_IN = re.compile(r"^(?:NOT\s+)?IN\s*\(.+\)$", re.IGNORECASE)
_PAT_MATCHES = re.compile(r"^MATCHES\s+/.+/$", re.IGNORECASE)
_PAT_APPROX = re.compile(
    rf"^=\s*({_NUM})\s*[+-]\s*({_NUM})$", re.IGNORECASE
)

_ALL_PATTERNS = [
    _PAT_CMP,
    _PAT_BETWEEN,
    _PAT_DELTA,
    _PAT_IS_NULL,
    _PAT_IS_NOT_NULL,
    _PAT_IN,
    _PAT_MATCHES,
    _PAT_APPROX,
]

_OPS_MAP = {
    "=": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
}


def validate_expectation(expr: str) -> None:
    """Raise ValueError if *expr* does not match any supported grammar form."""
    expr = (expr or "").strip()
    if not expr:
        raise ValueError("Expectation expression must not be empty.")
    for pat in _ALL_PATTERNS:
        if pat.match(expr):
            return
    raise ValueError(
        f"Unsupported expectation expression: {expr!r}. "
        "Supported: '= N', '!= N', '> N', '>= N', '< N', '<= N', "
        "'BETWEEN X AND Y', 'DELTA <op> N%', 'IS NULL', 'IS NOT NULL', "
        "'IN(...)', 'NOT IN(...)', 'MATCHES /regex/', '= N ±T'."
    )


def evaluate(actual: Any, expr: str, previous_value: Any = None) -> bool:
    """Evaluate *actual* against *expr*; return True if the check passes."""
    expr = (expr or "").strip()

    # IS NULL / IS NOT NULL
    if _PAT_IS_NULL.match(expr):
        return actual is None
    if _PAT_IS_NOT_NULL.match(expr):
        return actual is not None

    # MATCHES /regex/
    m = _PAT_MATCHES.match(expr)
    if m:
        pattern = re.search(r"/(.+)/$", expr)
        if pattern:
            return bool(re.search(pattern.group(1), str(actual)))
        return False

    # DELTA <op> N%
    m = _PAT_DELTA.match(expr)
    if m:
        op, pct = m.group(1), float(m.group(2))
        if previous_value is None or float(previous_value) == 0:
            return True  # no baseline → pass (warm-up)
        delta = abs(float(actual) - float(previous_value)) / abs(float(previous_value)) * 100
        fn = _OPS_MAP.get(op)
        return fn(delta, pct) if fn else False

    # BETWEEN X AND Y
    m = _PAT_BETWEEN.match(expr)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return lo <= float(actual) <= hi

    # = N ±T  (approximate equality)
    m = _PAT_APPROX.match(expr)
    if m:
        center, tol = float(m.group(1)), float(m.group(2))
        return abs(float(actual) - center) <= tol

    # IN(...) / NOT IN(...)
    if _PAT_IN.match(expr):
        negated = expr.upper().startswith("NOT")
        inner = re.search(r"\((.+)\)", expr, re.DOTALL)
        if inner:
            values = [v.strip().strip("'\"") for v in inner.group(1).split(",")]
            contained = str(actual) in values
            return not contained if negated else contained
        return False

    # Simple comparison: <op> N
    m = _PAT_CMP.match(expr)
    if m:
        op, val = m.group(1), float(m.group(2))
        fn = _OPS_MAP.get(op)
        if fn:
            return fn(float(actual), val)

    raise ValueError(f"Could not evaluate expression: {expr!r}")
