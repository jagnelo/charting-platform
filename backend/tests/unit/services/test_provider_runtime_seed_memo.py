from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderPolicy
from app.services import provider_runtime
from app.services.provider_runtime import seed_provider_runtime
from tests.unit.conftest import AsyncSessionAdapter


def _make_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


class _Counter:
    def __init__(self, engine):
        self.count = 0
        event.listen(engine, "before_cursor_execute", self._hit)

    def _hit(self, *_args):
        self.count += 1


@pytest.fixture()
def engine():
    eng = _make_engine()
    yield eng
    eng.dispose()


def _seed(session, *, commit: bool) -> None:
    adapter = AsyncSessionAdapter(session)
    asyncio.run(seed_provider_runtime(adapter))
    if commit:
        session.commit()


def _statements_for(session, counter) -> int:
    before = counter.count
    _seed(session, commit=True)
    return counter.count - before


def test_second_seed_after_commit_is_skipped(engine) -> None:
    counter = _Counter(engine)
    with sessionmaker(bind=engine)() as session:
        first = _statements_for(session, counter)
        second = _statements_for(session, counter)
        assert first > 500
        assert second < 20
        assert session.scalar(select(func.count()).select_from(ProviderPolicy)) > 0


def test_rollback_does_not_arm_memo(engine) -> None:
    counter = _Counter(engine)
    with sessionmaker(bind=engine)() as session:
        _seed(session, commit=False)
        session.rollback()
        assert session.scalar(select(func.count()).select_from(DataSource)) == 0
        assert _statements_for(session, counter) > 500


def test_savepoint_rollback_does_not_arm_memo(engine) -> None:
    counter = _Counter(engine)
    with sessionmaker(bind=engine)() as session:
        nested = session.begin_nested()
        _seed(session, commit=False)
        nested.rollback()
        session.commit()
        assert _statements_for(session, counter) > 500


def test_savepoint_release_before_outer_rollback_does_not_arm_memo(engine) -> None:
    counter = _Counter(engine)
    with sessionmaker(bind=engine)() as session:
        _seed(session, commit=False)
        nested = session.begin_nested()
        nested.commit()
        session.rollback()
        assert session.scalar(select(func.count()).select_from(DataSource)) == 0
        assert _statements_for(session, counter) > 500


def test_seed_inside_released_savepoint_arms_memo_on_root_commit(engine) -> None:
    counter = _Counter(engine)
    with sessionmaker(bind=engine)() as session:
        nested = session.begin_nested()
        _seed(session, commit=False)
        nested.commit()
        session.commit()
        assert _statements_for(session, counter) < 20


def test_uncommitted_seed_does_not_arm_memo(engine) -> None:
    counter = _Counter(engine)
    with sessionmaker(bind=engine)() as session:
        _seed(session, commit=False)
        session.flush()
        assert _statements_for(session, counter) > 500


def test_ttl_expiry_reseeds(engine, monkeypatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(provider_runtime, "_seed_memo_clock", lambda: now[0])
    counter = _Counter(engine)
    with sessionmaker(bind=engine)() as session:
        _statements_for(session, counter)
        now[0] += provider_runtime._SEED_MEMO_TTL_SECONDS - 1
        assert _statements_for(session, counter) < 20
        now[0] += 2
        assert _statements_for(session, counter) > 500


def test_fingerprint_change_reseeds(engine, monkeypatch) -> None:
    counter = _Counter(engine)
    with sessionmaker(bind=engine)() as session:
        _statements_for(session, counter)
        assert _statements_for(session, counter) < 20
        seeds = dict(settings.PROVIDER_FRESHNESS_SEEDS)
        seeds["price_history"] = 12345
        monkeypatch.setattr(settings, "PROVIDER_FRESHNESS_SEEDS", seeds)
        assert _statements_for(session, counter) > 500


def test_separate_binds_do_not_share_memo() -> None:
    first, second = _make_engine(), _make_engine()
    try:
        counter_first, counter_second = _Counter(first), _Counter(second)
        with sessionmaker(bind=first)() as one, sessionmaker(bind=second)() as two:
            _statements_for(one, counter_first)
            assert _statements_for(one, counter_first) < 20
            assert _statements_for(two, counter_second) > 500
    finally:
        first.dispose()
        second.dispose()


def test_reset_helper_forces_reseed(engine) -> None:
    counter = _Counter(engine)
    with sessionmaker(bind=engine)() as session:
        _statements_for(session, counter)
        provider_runtime.reset_provider_runtime_seed_memo()
        assert _statements_for(session, counter) > 500
