"""Derive the minimum local validation profile from a branch workstream."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

PROFILES = ("none", "unit", "docker_integration", "full_stack_browser")


def _text(values: dict[str, Any]) -> str:
    paths: list[str] = []
    for key in ("scope", "owned_paths", "branch_tests"):
        value = values.get(key) or []
        if isinstance(value, list):
            paths.extend(str(item) for item in value)
    for key in ("live_test_impact", "migration_impact", "deployment_impact"):
        paths.append(str(values.get(key, "")))
    return " ".join(paths).lower()


def minimum_profile(values: dict[str, Any]) -> str:
    """Return the weakest profile that can exercise the declared change boundary."""
    text = _text(values)
    if not text.strip():
        return "unit"
    if any(
        marker in text
        for marker in (
            "frontend/",
            "tests/e2e",
            "playwright",
            "visual",
            "websocket",
            "authentication",
            "workstation",
            "browser",
            "compose",
        )
    ):
        return "full_stack_browser"
    if any(
        marker in text
        for marker in (
            "backend/app",
            "backend/tests/integration",
            "testcontainers",
            "postgres",
            "redis",
            "migration",
            "alembic",
            "worker",
            "provider",
            "docker",
        )
    ):
        return "docker_integration"
    if all(marker in text for marker in ("docs/",)) and not any(
        marker in text for marker in ("script", "makefile", "workflow")
    ):
        return "none"
    return "unit"


def profile_rank(profile: str) -> int:
    try:
        return PROFILES.index(profile)
    except ValueError:
        return -1


def profile_is_sufficient(selected: str, values: dict[str, Any]) -> bool:
    required = minimum_profile(values)
    if profile_rank(selected) >= profile_rank(required):
        return True
    exception = str(values.get("local_validation_exception", "")).lower()
    return "human-authorized" in exception and "remote-only" in exception


def classify_paths(paths: Iterable[str]) -> str:
    """Convenience classifier for changed-path tooling and diagnostics."""
    return minimum_profile({"owned_paths": list(paths), "scope": list(paths)})
