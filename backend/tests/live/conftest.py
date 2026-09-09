from __future__ import annotations

from tests.live.live_usage import flush_observations


def pytest_sessionfinish(session, exitstatus):
    """Persist measured direct-adapter usage after every live pytest process."""

    flush_observations(int(exitstatus))
