"""Stable event-loop policy for Strategy Lab's async test suite."""

from __future__ import annotations

import asyncio

import pytest
import uvloop


def pytest_sessionstart(session: pytest.Session) -> None:
    del session
    uvloop.install()


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """Use uvloop to avoid the host interpreter's broken default executor shutdown."""

    return uvloop.EventLoopPolicy()
