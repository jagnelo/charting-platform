"""Regression coverage for expected asyncpg cancellation disposal logging."""

import asyncio
import logging

import pytest

from app.database import (
    _CancelledPoolTerminationFilter,
    close_session_safely,
    rollback_session_safely,
)


def test_pool_filter_only_suppresses_cancelled_error_records():
    filter_ = _CancelledPoolTerminationFilter()
    cancelled = logging.LogRecord(
        "sqlalchemy.pool.impl.AsyncAdaptedQueuePool",
        logging.ERROR,
        __file__,
        1,
        "Exception terminating connection",
        (),
        (asyncio.CancelledError, asyncio.CancelledError(), None),
    )
    ordinary = logging.LogRecord(
        "sqlalchemy.pool.impl.AsyncAdaptedQueuePool",
        logging.ERROR,
        __file__,
        1,
        "Exception terminating connection",
        (),
        (RuntimeError, RuntimeError("broken connection"), None),
    )

    assert filter_.filter(cancelled) is False
    assert filter_.filter(ordinary) is True


@pytest.mark.asyncio
async def test_cleanup_helpers_accept_synchronous_compatibility_sessions():
    """Adapters used by legacy callers must not be treated as awaitables."""

    class Session:
        def __init__(self):
            self.rollback_calls = 0
            self.close_calls = 0

        def rollback(self):
            self.rollback_calls += 1

        def close(self):
            self.close_calls += 1

    session = Session()
    await rollback_session_safely(session)
    await close_session_safely(session)

    assert session.rollback_calls == 1
    assert session.close_calls == 1
