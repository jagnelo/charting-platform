"""
Root conftest — shared fixtures for the entire test suite.

Container strategy
──────────────────
Unit tests      No containers; all I/O is mocked.
Integration     One Postgres container + one Redis container started *once* per
                pytest session (scope="session").  Speed win: containers take ~3s
                to start; spinning them up per-test would be unusable.
                DB isolation is achieved with per-test *transaction rollback*:
                each test runs inside a savepoint that is rolled back on teardown,
                leaving zero state for the next test.
"""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class AsyncSessionAdapter:
    """Small async facade so FastAPI async dependencies can use the sync test session."""

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

    async def delete(self, *args, **kwargs):
        self._session.delete(*args, **kwargs)

    def add(self, *args, **kwargs):
        return self._session.add(*args, **kwargs)

    def add_all(self, *args, **kwargs):
        return self._session.add_all(*args, **kwargs)

    def __getattr__(self, item):
        return getattr(self._session, item)


# ── Containers (session-scoped) ────────────────────────────────────────────────


@pytest.fixture(scope="session")
def pg_container():
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container():
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest.fixture(scope="session")
def redis_url(redis_container):
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


# ── Engine (session-scoped) ────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def db_engine(pg_container):
    """One engine per test session.  All tables created once."""
    raw_url = pg_container.get_connection_url()
    url = raw_url.replace("postgresql://", "postgresql+psycopg2://")

    # Import models so they register with Base.metadata
    import app.models  # noqa
    from app.database import Base

    engine = create_engine(url, echo=False, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ── Per-test session with savepoint rollback ──────────────────────────────────


@pytest.fixture()
def db(db_engine) -> Generator[Session, None, None]:
    """
    Wraps every test in a nested transaction (SAVEPOINT).
    On teardown the savepoint is rolled back — DB is clean for the next test.
    This is ~10x faster than truncating tables between tests.
    """
    conn = db_engine.connect()
    conn.begin()  # outer transaction
    Session = sessionmaker(bind=conn)
    session = Session()
    session.begin_nested()  # SAVEPOINT

    yield session

    session.close()
    conn.rollback()  # rolls back the outer transaction
    conn.close()


# ── FastAPI app with overridden DB dependency ─────────────────────────────────


@pytest.fixture()
def app(db, redis_url, monkeypatch):
    from app.config import settings
    from app.database import get_db
    from app.main import app as _app

    monkeypatch.setattr(settings, "REDIS_URL", redis_url)

    async_db = AsyncSessionAdapter(db)

    def _override():
        yield async_db

    _app.dependency_overrides[get_db] = _override
    yield _app
    _app.dependency_overrides.clear()


@pytest.fixture()
def client(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


# ── Auth helpers ───────────────────────────────────────────────────────────────


@pytest.fixture()
def user(db):
    from app.models.user import User
    from app.services.auth import hash_password

    u = User(
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("Password123!"),
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture()
def admin_user(db):
    from app.models.user import User
    from app.services.auth import hash_password

    u = User(
        username="admin",
        email="admin@example.com",
        hashed_password=hash_password("Admin123!"),
        is_active=True,
        is_admin=True,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture()
def auth_headers(user):
    from app.services.auth import create_access_token

    token = create_access_token(user.id, user.username)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(admin_user):
    from app.services.auth import create_access_token

    token = create_access_token(admin_user.id, admin_user.username)
    return {"Authorization": f"Bearer {token}"}


# ── Domain fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def asset_class(db):
    from app.models.asset_class import AssetClass

    ac = AssetClass(name="Equity", description="Equity instruments")
    db.add(ac)
    db.flush()
    return ac


@pytest.fixture()
def instrument_type(db, asset_class):
    from app.models.asset_class import InstrumentType

    it = InstrumentType(name="Stock", asset_class_id=asset_class.id)
    db.add(it)
    db.flush()
    return it


@pytest.fixture()
def instrument(db, instrument_type):
    from app.models.instrument import Instrument

    inst = Instrument(
        symbol="AAPL",
        name="Apple Inc.",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(inst)
    db.flush()
    return inst


@pytest.fixture()
def instrument_b(db, instrument_type):
    """Second instrument for multi-instrument tests."""
    from app.models.instrument import Instrument

    inst = Instrument(
        symbol="MSFT",
        name="Microsoft Corporation",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(inst)
    db.flush()
    return inst


@pytest.fixture()
def ohlcv_bars(db, instrument):
    """150 daily bars for AAPL with a seeded random walk — deterministic."""
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

    wl = Watchlist(user_id=user.id, name="Default", is_default=True)
    db.add(wl)
    db.flush()
    return wl


@pytest.fixture()
def price_alert(db, user, instrument):
    from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert

    a = PriceAlert(
        user_id=user.id,
        instrument_id=instrument.id,
        condition=AlertCondition.CROSSES_ABOVE,
        threshold_price=Decimal("200.00"),
        status=AlertStatus.ACTIVE,
        repeat=False,
    )
    db.add(a)
    db.flush()
    return a


@pytest.fixture()
def screener(db, user):
    from app.models.screener import ScreenerDefinition

    s = ScreenerDefinition(
        user_id=user.id,
        name="Test Screener",
        conditions={"operator": "AND", "conditions": []},
        universe_type="all",
        timeframe="D1",
    )
    db.add(s)
    db.flush()
    return s
