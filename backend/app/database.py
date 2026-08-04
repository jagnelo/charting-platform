import asyncio
import logging
from inspect import isawaitable

import anyio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


class _CancelledPoolTerminationFilter(logging.Filter):
    """Keep expected client-disconnect disposal out of backend error logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not record.exc_info:
            return True
        exception = record.exc_info[1]
        return not isinstance(exception, asyncio.CancelledError)


_pool_logger = logging.getLogger("sqlalchemy.pool.impl.AsyncAdaptedQueuePool")
if not any(isinstance(f, _CancelledPoolTerminationFilter) for f in _pool_logger.filters):
    _pool_logger.addFilter(_CancelledPoolTerminationFilter())

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.LOG_LEVEL.upper() == "DEBUG"),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_stream_session_factory():
    """Return the factory used by long-lived streaming request bodies."""
    return AsyncSessionLocal


def get_auth_session_factory():
    """Return a factory for short-lived authentication lookups.

    Authentication for a streaming response must not borrow FastAPI's
    request-scoped ``get_db`` generator: that generator is finalized only
    after the response body, while the stream may outlive the dependency
    resolution.  A factory keeps the identity lookup's session lifetime
    explicit and independently testable.
    """
    return AsyncSessionLocal


class Base(DeclarativeBase):
    pass


async def _finish_cleanup(operation, description: str) -> None:
    """Run an async cleanup operation outside the cancelled request task."""
    # Some compatibility/test session adapters expose synchronous cleanup
    # methods.  They have already completed by the time they return, so there
    # is no child task to shield in that case.
    if not isawaitable(operation):
        return
    cleanup_task = asyncio.create_task(operation)
    try:
        await asyncio.shield(cleanup_task)
    except BaseException:
        # A request cancellation can still interrupt the await on the parent
        # task even though ``cleanup_task`` is shielded.  Wait for that child
        # to finish so asyncpg sees a normal task rather than a cancelled one.
        try:
            await asyncio.shield(cleanup_task)
        except BaseException:
            logger.debug("%s failed during cancellation cleanup", description, exc_info=True)


async def rollback_session_safely(session: AsyncSession) -> None:
    """Rollback without allowing ASGI cancellation to interrupt cleanup."""
    with anyio.CancelScope(shield=True):
        operation = session.rollback()
        await _finish_cleanup(
            operation,
            "Database rollback",
        )


async def close_session_safely(session: AsyncSession) -> None:
    """Close a session while shielding pool cleanup from cancellation."""
    with anyio.CancelScope(shield=True):
        operation = session.close()
        await _finish_cleanup(
            operation,
            "Database session close",
        )


async def get_db() -> AsyncSession:
    """Yield a request-scoped session with cancellation-safe cleanup.

    ASGI streaming responses can be cancelled when a browser closes the
    connection while a response body is still being produced.  ``CancelledError``
    is a ``BaseException`` (rather than an ``Exception``), so the old dependency
    skipped the rollback path and let SQLAlchemy close the connection while the
    task was still cancelled.  asyncpg then logged an ``Exception terminating
    connection`` even though the request was intentionally aborted.

    Keep transaction cleanup explicit and handle cancellation like every other
    failed request.  The session is always closed in ``finally`` after rollback,
    allowing the pool to receive a clean connection rather than a cancelled
    close operation.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except BaseException:
        await rollback_session_safely(session)
        raise
    finally:
        await close_session_safely(session)
