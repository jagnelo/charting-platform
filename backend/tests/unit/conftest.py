from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture(scope="session")
def db_engine():
    import app.models  # noqa: F401
    from app.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db(db_engine) -> Generator[Session, None, None]:
    conn = db_engine.connect()
    tx = conn.begin()
    SessionLocal = sessionmaker(bind=conn)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        if tx.is_active:
            tx.rollback()
        conn.close()


@pytest.fixture()
def user(db):
    from app.models.user import User
    from app.services.auth import hash_password

    instance = User(
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db.add(instance)
    db.flush()
    return instance


@pytest.fixture()
def asset_class(db):
    from app.models.asset_class import AssetClass

    instance = AssetClass(name="Equity", description="Equity instruments")
    db.add(instance)
    db.flush()
    return instance


@pytest.fixture()
def instrument_type(db, asset_class):
    from app.models.asset_class import InstrumentType

    instance = InstrumentType(name="Stock", asset_class_id=asset_class.id)
    db.add(instance)
    db.flush()
    return instance


@pytest.fixture()
def instrument(db, instrument_type):
    from app.models.instrument import Instrument

    instance = Instrument(
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(instance)
    db.flush()
    return instance


@pytest.fixture()
def ohlcv_bars(db, instrument):
    import random

    from app.models.ohlcv import OHLCVBar, Timeframe

    rng = random.Random(42)
    bars = []
    price = 180.0
    base = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(150):
        price = max(10.0, price + rng.uniform(-3.5, 3.5))
        bar = OHLCVBar(
            instrument_id=instrument.id,
            timeframe=Timeframe.D1,
            ts=base + timedelta(days=i),
            open=Decimal(str(round(price - 1, 4))),
            high=Decimal(str(round(price + 2, 4))),
            low=Decimal(str(round(price - 2, 4))),
            close=Decimal(str(round(price, 4))),
            volume=Decimal(str(rng.randint(40_000_000, 160_000_000))),
            is_adjusted=True,
        )
        bars.append(bar)
        db.add(bar)
    db.flush()
    return bars


@pytest.fixture()
def watchlist(db, user):
    from app.models.watchlist import Watchlist

    instance = Watchlist(user_id=user.id, name="Default", is_default=True)
    db.add(instance)
    db.flush()
    return instance


@pytest.fixture()
def screener(db, user):
    from app.models.screener import ScreenerDefinition

    instance = ScreenerDefinition(
        user_id=user.id,
        name="Test Screener",
        conditions={"operator": "AND", "conditions": []},
        universe_type="all",
        timeframe="D1",
    )
    db.add(instance)
    db.flush()
    return instance


class AsyncSessionAdapter:
    """Async facade around the sync sqlite session used by unit router tests."""

    def __init__(self, session: Session):
        self._session = session

    async def execute(self, *args, **kwargs):
        return self._session.execute(*args, **kwargs)

    async def get(self, *args, **kwargs):
        return self._session.get(*args, **kwargs)

    async def commit(self):
        self._session.commit()

    async def rollback(self):
        self._session.rollback()

    async def flush(self, *args, **kwargs):
        self._session.flush(*args, **kwargs)

    async def refresh(self, *args, **kwargs):
        self._session.refresh(*args, **kwargs)

    async def close(self):
        """Keep the shared sync fixture session available to later requests."""
        return None

    async def delete(self, *args, **kwargs):
        self._session.delete(*args, **kwargs)

    def add(self, *args, **kwargs):
        return self._session.add(*args, **kwargs)

    def add_all(self, *args, **kwargs):
        return self._session.add_all(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._session, item)


@pytest.fixture(autouse=True)
def inline_provider_runtime_executor(monkeypatch):
    """Keep provider-runtime unit calls deterministic in this sandbox.

    The production runtime deliberately invokes synchronous adapters through
    the event loop's default executor.  The unit environment's worker-thread
    wakeup is unreliable, so execute those already-isolated calls inline;
    Docker integration tests retain the production executor path.
    """
    from app.services import provider_quota_coordinator, provider_runtime

    real_asyncio = provider_runtime.asyncio

    class _InlineLoop:
        async def run_in_executor(self, _executor, func, *args):
            return func(*args)

    class _ProviderRuntimeAsyncio:
        def __getattr__(self, item):
            return getattr(real_asyncio, item)

        @staticmethod
        def get_event_loop():
            return _InlineLoop()

    monkeypatch.setattr(provider_runtime, "asyncio", _ProviderRuntimeAsyncio())

    class _InlineCoordinatorAsyncio:
        def __getattr__(self, item):
            return getattr(real_asyncio, item)

        @staticmethod
        async def to_thread(func, /, *args, **kwargs):
            return func(*args, **kwargs)

    monkeypatch.setattr(
        provider_quota_coordinator, "asyncio", _InlineCoordinatorAsyncio()
    )


@pytest.fixture()
def app(db, monkeypatch):
    from app.config import settings
    from app.database import get_auth_session_factory, get_db, get_stream_session_factory
    from app.main import app as _app
    from app.routers import market_data_admin

    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")

    class _InlineAsyncio:
        gather = staticmethod(asyncio.gather)

        @staticmethod
        async def to_thread(func, /, *args, **kwargs):
            return func(*args, **kwargs)

    # The unit app uses a synchronous SQLite quota ledger.  Run those tiny
    # coordinator calls inline so the sandbox's worker-thread shutdown issue
    # cannot mask the endpoint assertions; integration tests retain the real
    # asyncio.to_thread behavior.
    monkeypatch.setattr(market_data_admin, "asyncio", _InlineAsyncio)

    async_db = AsyncSessionAdapter(db)

    async def _override():
        yield async_db

    _app.dependency_overrides[get_db] = _override
    _app.dependency_overrides[get_stream_session_factory] = lambda: lambda: async_db
    _app.dependency_overrides[get_auth_session_factory] = lambda: lambda: async_db
    yield _app
    _app.dependency_overrides.clear()


class _SyncASGIClient:
    """Synchronous request facade that avoids Starlette's thread portal."""

    def __init__(self, app):
        self._app = app

    def request(self, method: str, url: str, **kwargs):
        async def _send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_send())

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs):
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)


@pytest.fixture()
def client(app) -> _SyncASGIClient:
    return _SyncASGIClient(app)


@pytest.fixture()
def auth_headers(user):
    from app.services.auth import create_access_token

    token = create_access_token(user.id, user.username)
    return {"Authorization": f"Bearer {token}"}
