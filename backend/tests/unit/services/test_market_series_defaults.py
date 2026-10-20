import asyncio
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401 - register all foreign-key targets
from app.database import Base
from app.models.market_data_foundation import (
    AdjustmentBasis,
    MarketSeries,
    MarketSeriesDefault,
)
from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.market_data import _default_series_bar_condition
from app.services.market_series import SeriesScope, get_or_create_series


class _AsyncSessionAdapter:
    """Exercise the async service against an isolated synchronous SQLite DB."""

    def __init__(self, session: Session):
        self.session = session

    async def execute(self, *args, **kwargs):
        return self.session.execute(*args, **kwargs)

    async def flush(self, *args, **kwargs):
        self.session.flush(*args, **kwargs)

    async def get(self, *args, **kwargs):
        return self.session.get(*args, **kwargs)

    def add(self, *args, **kwargs):
        return self.session.add(*args, **kwargs)

    def begin_nested(self):
        return self.session.begin_nested()


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _bar(*, series_id: int | None, adjusted: bool = True) -> OHLCVBar:
    return OHLCVBar(
        instrument_id=1,
        market_series_id=series_id,
        timeframe=Timeframe.D1,
        ts=datetime(2026, 1, 2, tzinfo=UTC),
        open=10,
        high=11,
        low=9,
        close=10,
        is_adjusted=adjusted,
        adjustment_basis="provider_adjusted" if adjusted else "raw",
        adjustment_version="v1",
        session="regular",
        scope_key=(f"series:{series_id}:regular" if series_id else "legacy:regular"),
    )


def test_first_canonical_series_becomes_stable_default_without_replacement():
    engine, session = _db()
    try:
        db = _AsyncSessionAdapter(session)
        first = asyncio.run(
            get_or_create_series(
                db,
                SeriesScope(
                    instrument_id=1,
                    data_source_id=10,
                    feed_scope="provider_native",
                    session_code="regular",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.PROVIDER_ADJUSTED,
                    adjustment_version="v1",
                ),
                canonical=True,
            )
        )
        second = asyncio.run(
            get_or_create_series(
                db,
                SeriesScope(
                    instrument_id=1,
                    data_source_id=11,
                    feed_scope="provider_native",
                    session_code="regular",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.PROVIDER_ADJUSTED,
                    adjustment_version="v1",
                ),
                canonical=True,
            )
        )
        selected = session.execute(select(MarketSeriesDefault)).scalar_one()
        assert selected.market_series_id == first.id
        assert selected.market_series_id != second.id
    finally:
        session.close()
        engine.dispose()


def test_regular_series_replaces_an_extended_compatibility_default():
    engine, session = _db()
    try:
        db = _AsyncSessionAdapter(session)
        extended = asyncio.run(
            get_or_create_series(
                db,
                SeriesScope(
                    instrument_id=1,
                    data_source_id=10,
                    feed_scope="provider_native",
                    session_code="extended",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.PROVIDER_ADJUSTED,
                    adjustment_version="v1",
                ),
                canonical=True,
            )
        )
        regular = asyncio.run(
            get_or_create_series(
                db,
                SeriesScope(
                    instrument_id=1,
                    data_source_id=11,
                    feed_scope="provider_native",
                    session_code="regular",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.PROVIDER_ADJUSTED,
                    adjustment_version="v1",
                ),
                canonical=True,
            )
        )
        selected = session.execute(select(MarketSeriesDefault)).scalar_one()
        assert selected.market_series_id == regular.id
        assert selected.market_series_id != extended.id
        assert selected.selection_reason == "prefer_regular_session"
    finally:
        session.close()
        engine.dispose()


def test_default_condition_excludes_alternate_and_legacy_bars():
    engine, session = _db()
    try:
        session.add_all(
            [
                MarketSeries(
                    id=10,
                    instrument_id=1,
                    data_source_id=10,
                    feed_scope="provider_native",
                    session_code="regular",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.PROVIDER_ADJUSTED,
                    adjustment_version="v1",
                    is_canonical=True,
                    is_active=True,
                ),
                MarketSeries(
                    id=20,
                    instrument_id=1,
                    data_source_id=11,
                    feed_scope="provider_native",
                    session_code="regular",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.PROVIDER_ADJUSTED,
                    adjustment_version="v1",
                    is_canonical=True,
                    is_active=True,
                ),
                MarketSeriesDefault(
                    instrument_id=1,
                    timeframe="D1",
                    is_adjusted=True,
                    market_series_id=20,
                ),
            ]
        )
        session.add_all([_bar(series_id=10), _bar(series_id=20), _bar(series_id=None)])
        session.flush()
        statement = select(OHLCVBar).where(
            OHLCVBar.instrument_id == 1,
            OHLCVBar.timeframe == Timeframe.D1,
            OHLCVBar.is_adjusted.is_(True),
            _default_series_bar_condition(1, Timeframe.D1, True),
        )
        rows = session.execute(statement).scalars().all()
        assert [row.market_series_id for row in rows] == [20]
    finally:
        session.close()
        engine.dispose()


def test_default_condition_keeps_legacy_bars_when_canonical_series_is_empty():
    engine, session = _db()
    try:
        session.add(
            MarketSeries(
                id=10,
                instrument_id=1,
                data_source_id=10,
                feed_scope="provider_native",
                session_code="regular",
                timeframe="D1",
                adjustment_basis=AdjustmentBasis.PROVIDER_ADJUSTED,
                adjustment_version="v1",
                is_canonical=True,
                is_active=True,
            )
        )
        session.add(_bar(series_id=None))
        session.flush()
        statement = select(OHLCVBar).where(
            OHLCVBar.instrument_id == 1,
            OHLCVBar.timeframe == Timeframe.D1,
            OHLCVBar.is_adjusted.is_(True),
            _default_series_bar_condition(1, Timeframe.D1, True),
        )
        rows = session.execute(statement).scalars().all()
        assert [row.market_series_id for row in rows] == [None]
    finally:
        session.close()
        engine.dispose()
