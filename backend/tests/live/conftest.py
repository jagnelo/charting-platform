from __future__ import annotations

import os

import pytest

from tests.live.live_usage import (
    activate_case,
    deactivate_case,
    ensure_ledger_writable,
    ensure_usage_scope_configured,
    flush_observations,
    install_httpx_quota_admission_guard,
)


def pytest_sessionstart(session):
    """Fail before provider calls when the external usage ledger is unwritable."""

    del session
    if os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1":
        return
    if os.getenv("PROVIDER_LIVE_MATRIX_RUN") != "1":
        pytest.exit(
            "direct live pytest execution is blocked; use "
            "scripts/run-live-provider-probes.py so provider selection, "
            "approved deferrals, routing safety, and durable quota evidence "
            "are enforced",
            returncode=2,
        )
    try:
        install_httpx_quota_admission_guard()
        ensure_usage_scope_configured()
        ensure_ledger_writable()
        from app.services.provider_quota_coordinator import ensure_provider_quota_coordinator

        ensure_provider_quota_coordinator()
    except RuntimeError as exc:
        pytest.exit(str(exc), returncode=2)


def pytest_sessionfinish(session, exitstatus):
    """Persist measured direct-adapter usage after every live pytest process."""

    flush_observations(int(exitstatus))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """Tag every measured provider call with the exact pytest node ID."""

    token = activate_case(item.nodeid)
    try:
        yield
    finally:
        deactivate_case(token)
