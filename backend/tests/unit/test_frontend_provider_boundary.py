"""Keep the authenticated workstation independent of provider implementation details."""

import re
from pathlib import Path

PRIMARY_FRONTEND = Path(__file__).resolve().parents[3] / "frontend" / "src"
FORBIDDEN_PROVIDER_TERMS = re.compile(
    r"yfinance|alpaca|polygon|massive|alpha\s*vantage|openfigi|fred|"
    r"api[_-]?key|provider[_ -]?fallback|fallback[_ -]?provider",
    re.IGNORECASE,
)


def test_primary_frontend_does_not_embed_provider_identifiers_or_fallback_order():
    """Provider selection belongs behind canonical APIs and capability metadata."""
    violations: list[str] = []
    for path in sorted(PRIMARY_FRONTEND.rglob("*")):
        if not path.is_file() or path.suffix not in {".ts", ".tsx", ".vue", ".css", ".scss"}:
            continue
        text = path.read_text(encoding="utf-8")
        if FORBIDDEN_PROVIDER_TERMS.search(text):
            violations.append(str(path.relative_to(PRIMARY_FRONTEND)))
    assert violations == []
