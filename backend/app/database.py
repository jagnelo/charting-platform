from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

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


class Base(DeclarativeBase):
    pass


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
        await session.rollback()
        raise
    finally:
        await session.close()
