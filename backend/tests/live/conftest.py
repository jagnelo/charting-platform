from __future__ import annotations

import os

import pytest

from tests.live.live_usage import ensure_ledger_writable, flush_observations


def pytest_sessionstart(session):
    """Fail before provider calls when the external usage ledger is unwritable."""

    del session
    if os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1":
        return
    try:
        ensure_ledger_writable()
    except RuntimeError as exc:
        pytest.exit(str(exc), returncode=2)


def pytest_sessionfinish(session, exitstatus):
    """Persist measured direct-adapter usage after every live pytest process."""

    flush_observations(int(exitstatus))
