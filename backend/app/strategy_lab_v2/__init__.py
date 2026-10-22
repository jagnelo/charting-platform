"""Engine-neutral contracts for the Strategy Lab v2 backend.

This package deliberately has no import path to Nautilus, providers, persistence,
network clients, or the application router. Those integrations live behind
separately reviewed adapters.
"""

from app.strategy_lab_v2.canonical import canonical_json, content_digest

__all__ = ["canonical_json", "content_digest"]
