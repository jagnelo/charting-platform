"""
Expression engine for synthetic/ratio instruments.

Parses a simple arithmetic expression like 'SPY/GLD' or '(SPY*0.5)/GLD',
extracts the ticker tokens, and evaluates it bar-by-bar against constituent
OHLCV series to produce a synthetic OHLCV series.

Design constraints:
  - Only the AST nodes in _SAFE_NODES are permitted (no function calls, no
    attribute access, no imports — just arithmetic on names and numbers).
  - Ticker tokens must be valid Python identifiers (letters, digits, underscore),
    which covers all normal ticker symbols.  Slashes are treated as division
    operators, not as part of a symbol name.
  - The engine is purely synchronous; callers that need async should run it in
    an executor.
"""

import ast
import re

import numpy as np

# AST node types we allow in an expression tree.
_SAFE_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Num,  # Python ≤3.7 literal
    ast.Constant,  # Python ≥3.8 literal
    ast.Name,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.USub,
    ast.UAdd,
    # Context nodes automatically attached to every ast.Name by the parser
    ast.Load,
    ast.Store,
    ast.Del,
)

# Symbols that are Python keywords and therefore cannot be identifiers in an
# expression (e.g. 'and', 'or', 'not').  These will produce a parse error before
# we even reach our safety check, but listed here for documentation.
_KEYWORDS = frozenset({"and", "or", "not", "in", "is", "if", "else", "True", "False", "None"})


class ExpressionError(ValueError):
    """Raised when the expression cannot be parsed or contains unsafe nodes."""


def normalize_expression(raw: str) -> str:
    """
    Normalise an expression to a canonical form suitable for use as an
    instrument symbol.

    Strips whitespace, upper-cases all ticker tokens (names), and collapses
    redundant spaces around operators.  The result is deterministic so that two
    users typing 'spy/gld' and 'SPY / GLD' resolve to the same synthetic row.

    Raises ExpressionError if the expression is invalid.
    """
    # Parse first to validate
    tickers = extract_tickers(raw)
    # Upper-case all tickers in the raw string (case-insensitive replacement)
    result = raw.strip()
    for t in tickers:
        result = re.sub(r"\b" + re.escape(t) + r"\b", t.upper(), result, flags=re.IGNORECASE)
    # Remove all spaces for a compact canonical form
    result = re.sub(r"\s+", "", result)
    return result


def extract_tickers(expression: str) -> list[str]:
    """
    Return deduplicated list of ticker tokens in the expression (preserving order
    of first occurrence).

    Raises ExpressionError on any parse or safety error.
    """
    tree = _parse(expression)
    seen: dict[str, None] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            name = node.id.upper()
            if name not in seen:
                seen[name] = None
    return list(seen)


def _parse(expression: str) -> ast.Expression:
    """Parse the expression and validate that it only uses safe AST nodes."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        raise ExpressionError(f"Syntax error in expression '{expression}': {e}") from e

    for node in ast.walk(tree):
        if not isinstance(node, _SAFE_NODES):
            raise ExpressionError(
                f"Unsupported operation in expression '{expression}': {type(node).__name__}"
            )
    return tree


def evaluate_expression(
    expression: str,
    constituent_closes: dict[str, np.ndarray],
) -> np.ndarray:
    """
    Evaluate the arithmetic expression bar-by-bar using the provided close
    price arrays, returning a synthetic close array aligned to the shortest
    constituent series.

    constituent_closes: mapping of UPPER-CASE ticker → numpy float64 array of
                        close prices, all same length (caller must align first).

    Raises ExpressionError on any eval error.
    """
    tree = _parse(expression)
    # Build eval namespace with upper-cased ticker arrays
    namespace = {k.upper(): v for k, v in constituent_closes.items()}
    try:
        result = eval(  # noqa: S307
            compile(tree, "<expression>", "eval"),
            {"__builtins__": {}},
            namespace,
        )
    except Exception as e:
        raise ExpressionError(f"Evaluation error in expression '{expression}': {e}") from e

    if isinstance(result, np.ndarray):
        return result.astype(np.float64)
    # Scalar — broadcast to the length of the first series
    if namespace:
        first = next(iter(namespace.values()))
        return np.full(len(first), float(result), dtype=np.float64)
    return np.array([float(result)], dtype=np.float64)


def compute_synthetic_ohlcv(
    expression: str,
    constituent_ohlcv: dict[str, dict[str, np.ndarray]],
) -> dict[str, np.ndarray]:
    """
    Compute synthetic OHLCV by applying the expression to each OHLCV field
    independently using the constituent series.

    constituent_ohlcv: mapping of UPPER-CASE ticker →
        {'open': np.ndarray, 'high': np.ndarray, 'low': np.ndarray,
         'close': np.ndarray, 'volume': np.ndarray}

    All arrays must be pre-aligned to the same timestamps (caller is responsible).
    Volume is set to None (a ratio of volumes is meaningless).

    Returns dict with keys 'open', 'high', 'low', 'close', 'volume'.
    'volume' is an array of np.nan.
    """
    fields = ["open", "high", "low", "close"]
    result: dict[str, np.ndarray] = {}
    for field in fields:
        field_map = {ticker: series[field] for ticker, series in constituent_ohlcv.items()}
        result[field] = evaluate_expression(expression, field_map)

    # Volume has no meaningful interpretation for a ratio/expression chart
    length = len(next(iter(result.values())))
    result["volume"] = np.full(length, np.nan, dtype=np.float64)
    return result


def is_expression(text: str) -> bool:
    """
    Heuristic check: does this string look like an arithmetic expression rather
    than a plain ticker symbol?

    Returns True if the string contains an arithmetic operator (+, -, *, /)
    surrounded by ticker-like tokens.
    """
    # A plain symbol is only letters, digits, dots, hyphens, underscores, equals
    if re.fullmatch(r"[A-Za-z0-9.\-_=^]+", text.strip()):
        return False
    # Contains an arithmetic operator between identifier-like tokens
    return bool(re.search(r"[A-Za-z0-9_]\s*[+\-*/]\s*[A-Za-z0-9_(]", text))
