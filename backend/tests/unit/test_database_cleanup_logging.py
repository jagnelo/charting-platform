"""Regression coverage for expected asyncpg cancellation disposal logging."""

import asyncio
import logging

from app.database import _CancelledPoolTerminationFilter


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
