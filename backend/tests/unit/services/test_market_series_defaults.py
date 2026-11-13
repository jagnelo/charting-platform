import asyncio
from datetime import UTC, date, datetime, time

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401 - register all foreign-key targets
from app.database import Base
from app.models.exchange import Exchange
from app.models.instrument import Instrument
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import (
    AdjustmentBasis,
    MarketSeries,
    MarketSeriesDefault,
)
from app.models.ohlcv import OHLCVBar, Timeframe
from app.routers.research import _load_instrument_bars
from app.services.bulk_fetch import _existing_timestamps
from app.services.market_data import _default_series_bar_condition
from app.services.market_series import (
    SeriesScope,
    get_or_create_series,
    select_default_series_for_complete_range,
    select_default_series_for_latest_contiguous_suffix,
)
from app.services.ohlcv_coverage import _xnys_session_days


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


def _bar(
    *,
    series_id: int | None,
    adjusted: bool = True,
    ts: datetime = datetime(2026, 1, 2, tzinfo=UTC),
    data_source_id: int | None = None,
) -> OHLCVBar:
    return OHLCVBar(
        instrument_id=1,
        data_source_id=data_source_id,
        market_series_id=series_id,
        timeframe=Timeframe.D1,
        ts=ts,
        open=10,
        high=11,
        low=9,
        close=10,
        is_adjusted=adjusted,
        adjustment_basis="split_adjusted" if adjusted else "raw",
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
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
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
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
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
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
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
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
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
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
                    adjustment_version="massive-split-adjusted",
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
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
                    adjustment_version="alpaca-split",
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
                adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
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


def test_split_adjusted_default_excludes_alpaca_total_return_series():
    engine, session = _db()
    try:
        massive_split = MarketSeries(
            id=30,
            instrument_id=1,
            data_source_id=10,
            feed_scope="provider_native",
            session_code="regular",
            timeframe="D1",
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="massive-split-adjusted",
            is_canonical=True,
            is_active=True,
        )
        alpaca_all = MarketSeries(
            id=40,
            instrument_id=1,
            data_source_id=20,
            feed_scope="iex",
            session_code="regular",
            timeframe="D1",
            adjustment_basis=AdjustmentBasis.PROVIDER_ADJUSTED,
            adjustment_version="alpaca-all",
            is_canonical=True,
            is_active=True,
        )
        session.add_all(
            [
                massive_split,
                alpaca_all,
                MarketSeriesDefault(
                    instrument_id=1,
                    timeframe="D1",
                    is_adjusted=True,
                    market_series_id=40,
                    selection_reason="historical-alpaca-all-default",
                ),
            ]
        )
        split_bar = _bar(series_id=30, data_source_id=10)
        all_bar = _bar(series_id=40, data_source_id=20)
        all_bar.adjustment_basis = "provider_adjusted"
        all_bar.adjustment_version = "alpaca-all"
        session.add_all([split_bar, all_bar])
        session.flush()

        rows = (
            session.execute(
                select(OHLCVBar).where(
                    OHLCVBar.instrument_id == 1,
                    OHLCVBar.timeframe == Timeframe.D1,
                    OHLCVBar.is_adjusted.is_(True),
                    _default_series_bar_condition(1, Timeframe.D1, True),
                )
            )
            .scalars()
            .all()
        )
        assert [(row.market_series_id, row.adjustment_version) for row in rows] == [(30, "v1")]
        assert session.get(MarketSeriesDefault, 1).market_series_id == 40
    finally:
        session.close()
        engine.dispose()


def test_deeper_provider_default_switches_only_after_complete_coherent_range():
    engine, session = _db()
    try:
        massive = MarketSeries(
            id=10,
            instrument_id=1,
            data_source_id=10,
            feed_scope="provider_native",
            session_code="regular",
            timeframe="D1",
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="massive-split-adjusted",
            is_canonical=True,
            is_active=True,
            source_series_key="massive:TEST:D1:provider_native:regular:split_adjusted:massive-split-adjusted",
        )
        alpaca = MarketSeries(
            id=20,
            instrument_id=1,
            data_source_id=20,
            feed_scope="iex",
            session_code="regular",
            timeframe="D1",
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="alpaca-split",
            is_canonical=True,
            is_active=True,
            source_series_key="alpaca:TEST:D1:iex:regular:split_adjusted:alpaca-split",
        )
        session.add_all(
            [
                Instrument(
                    id=1,
                    instrument_type_id=1,
                    symbol="TEST",
                    name="Test instrument",
                    currency="USD",
                    is_active=True,
                    identity_status="resolved",
                ),
                Exchange(id=1, mic="XNYS", name="New York Stock Exchange", country_code="US"),
                InstrumentListing(
                    id=1,
                    instrument_id=1,
                    exchange_id=1,
                    ticker="TEST",
                    currency="USD",
                    is_primary=True,
                    is_active=True,
                ),
                massive,
                alpaca,
                MarketSeriesDefault(
                    instrument_id=1,
                    timeframe="D1",
                    is_adjusted=True,
                    market_series_id=10,
                    selection_reason="first_canonical",
                ),
            ]
        )
        sessions = sorted(_xnys_session_days(date(2016, 11, 7), date(2026, 11, 6)))
        recent_start = date(2024, 11, 6)
        full_stamps = [datetime.combine(day, time.min, tzinfo=UTC) for day in sessions]
        recent_stamps = [stamp for stamp in full_stamps if stamp.date() >= recent_start]
        full_start = full_stamps[0]
        full_end = datetime(2026, 11, 6, 23, 59, tzinfo=UTC)
        for stamp in recent_stamps:
            session.add(_bar(series_id=10, ts=stamp, data_source_id=10))
            session.add(_bar(series_id=20, ts=stamp, data_source_id=20))
        session.flush()

        def ordinary_read_series_ids():
            rows = session.execute(
                select(OHLCVBar)
                .where(
                    OHLCVBar.instrument_id == 1,
                    OHLCVBar.timeframe == Timeframe.D1,
                    OHLCVBar.is_adjusted.is_(True),
                    _default_series_bar_condition(1, Timeframe.D1, True),
                )
                .order_by(OHLCVBar.ts)
            ).scalars()
            return [row.market_series_id for row in rows]

        async def analysis_read_series_ids():
            rows = await _load_instrument_bars(
                _AsyncSessionAdapter(session),
                session.get(Instrument, 1),
                {
                    "timeframe": Timeframe.D1,
                    "is_adjusted": True,
                    "session": "all",
                    "start": full_start,
                    "end": full_end,
                },
                limit=10000,
            )
            return [row.market_series_id for row in rows]

        # The deeper alternate exists but is not selected while its complete
        # range has not yet been established by the caller.
        assert set(ordinary_read_series_ids()) == {10}
        initial_analysis_ids = asyncio.run(analysis_read_series_ids())
        assert len(initial_analysis_ids) == len(recent_stamps)
        assert set(initial_analysis_ids) == {10}
        # An incomplete alternate must not displace the still-useful recent
        # default, even when it already contains overlapping recent bars.
        narrow_complete = asyncio.run(
            select_default_series_for_complete_range(
                _AsyncSessionAdapter(session),
                instrument_id=1,
                timeframe="D1",
                adjusted=True,
                market_series_id=20,
                start=recent_stamps[0],
                end=full_end,
            )
        )
        assert narrow_complete is False
        switched_early = asyncio.run(
            select_default_series_for_complete_range(
                _AsyncSessionAdapter(session),
                instrument_id=1,
                timeframe="D1",
                adjusted=True,
                market_series_id=20,
                start=full_start,
                end=full_end,
            )
        )
        assert switched_early is False
        assert set(ordinary_read_series_ids()) == {10}
        assert set(asyncio.run(analysis_read_series_ids())) == {10}

        # The older chunk arrives later. Only now does the same ordinary read
        # select the one complete Alpaca feed for the whole requested range.
        for stamp in full_stamps:
            if stamp.date() < recent_start:
                session.add(_bar(series_id=20, ts=stamp, data_source_id=20))
        session.flush()
        switched = asyncio.run(
            select_default_series_for_complete_range(
                _AsyncSessionAdapter(session),
                instrument_id=1,
                timeframe="D1",
                adjusted=True,
                market_series_id=20,
                start=full_start,
                end=full_end,
            )
        )
        assert switched is True
        assert set(ordinary_read_series_ids()) == {20}
        full_analysis_ids = asyncio.run(analysis_read_series_ids())
        assert len(full_analysis_ids) == len(full_stamps)
        assert set(full_analysis_ids) == {20}
        # The overlapping observations remain intact in their own feeds; the
        # default switch changes reads, not stored provider/source lineage.
        stored = session.execute(
            select(OHLCVBar.market_series_id, OHLCVBar.data_source_id, OHLCVBar.ts).where(
                OHLCVBar.instrument_id == 1,
                OHLCVBar.timeframe == Timeframe.D1,
                OHLCVBar.is_adjusted.is_(True),
            )
        ).all()
        assert len(stored) == len(recent_stamps) + len(full_stamps)
        assert sum(
            series_id == 10 and source_id == 10 for series_id, source_id, _ in stored
        ) == len(recent_stamps)
        assert sum(
            series_id == 20 and source_id == 20 for series_id, source_id, _ in stored
        ) == len(full_stamps)
        selected_default = session.execute(select(MarketSeriesDefault)).scalar_one()
        assert selected_default.market_series_id == 20
        assert selected_default.selection_reason == "complete_admitted_range"
        assert session.get(MarketSeries, 20).data_source_id == 20
        assert session.get(MarketSeries, 20).adjustment_basis == AdjustmentBasis.SPLIT_ADJUSTED
    finally:
        session.close()
        engine.dispose()


def test_latest_contiguous_deeper_suffix_can_upgrade_default_without_hiding_older_gap():
    engine, session = _db()
    try:
        massive = MarketSeries(
            id=10,
            instrument_id=1,
            data_source_id=10,
            feed_scope="provider_native",
            session_code="regular",
            timeframe="D1",
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="massive-split-adjusted",
            is_canonical=True,
            is_active=True,
        )
        alpaca = MarketSeries(
            id=20,
            instrument_id=1,
            data_source_id=20,
            feed_scope="iex",
            session_code="regular",
            timeframe="D1",
            adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
            adjustment_version="alpaca-split",
            is_canonical=True,
            is_active=True,
        )
        session.add_all(
            [
                Instrument(
                    id=1,
                    instrument_type_id=1,
                    symbol="TEST",
                    name="Test instrument",
                    currency="USD",
                    is_active=True,
                    identity_status="resolved",
                ),
                Exchange(id=1, mic="XNYS", name="New York Stock Exchange", country_code="US"),
                InstrumentListing(
                    id=1,
                    instrument_id=1,
                    exchange_id=1,
                    ticker="TEST",
                    currency="USD",
                    is_primary=True,
                    is_active=True,
                ),
                massive,
                alpaca,
                MarketSeriesDefault(
                    instrument_id=1,
                    timeframe="D1",
                    is_adjusted=True,
                    market_series_id=10,
                    selection_reason="first_canonical",
                ),
            ]
        )
        sessions = sorted(_xnys_session_days(date(2020, 1, 2), date(2026, 11, 6)))
        suffix_start = date(2020, 7, 27)
        current_default_start = date(2024, 11, 11)
        end = datetime(2026, 11, 6, 23, 59, tzinfo=UTC)
        for stamp_date in sessions:
            stamp = datetime.combine(stamp_date, time.min, tzinfo=UTC)
            if stamp_date == date(2020, 1, 2):
                session.add(_bar(series_id=20, ts=stamp, data_source_id=20))
            if stamp_date >= suffix_start:
                session.add(_bar(series_id=20, ts=stamp, data_source_id=20))
            if stamp_date >= current_default_start:
                session.add(_bar(series_id=10, ts=stamp, data_source_id=10))
        session.flush()

        upgraded = asyncio.run(
            select_default_series_for_latest_contiguous_suffix(
                _AsyncSessionAdapter(session),
                instrument_id=1,
                timeframe="D1",
                adjusted=True,
                market_series_id=20,
                requested_start=datetime(2020, 1, 2, tzinfo=UTC),
                end=end,
            )
        )
        assert upgraded is True
        selected = session.execute(select(MarketSeriesDefault)).scalar_one()
        assert selected.market_series_id == 20
        assert selected.selection_reason == "complete_admitted_range"

        ordinary = (
            session.execute(
                select(OHLCVBar)
                .where(
                    OHLCVBar.instrument_id == 1,
                    OHLCVBar.timeframe == Timeframe.D1,
                    OHLCVBar.is_adjusted.is_(True),
                    _default_series_bar_condition(1, Timeframe.D1, True),
                )
                .order_by(OHLCVBar.ts)
            )
            .scalars()
            .all()
        )
        assert ordinary
        assert {bar.market_series_id for bar in ordinary} == {20}
        assert min(bar.ts.date() for bar in ordinary) == date(2020, 1, 2)
        assert (
            min(bar.ts.date() for bar in ordinary if bar.ts.date() >= suffix_start) == suffix_start
        )
        assert max(bar.ts.date() for bar in ordinary) == date(2026, 11, 6)

        all_rows = session.execute(select(OHLCVBar.market_series_id, OHLCVBar.data_source_id)).all()
        assert all_rows.count((10, 10)) == sum(
            stamp_date >= current_default_start for stamp_date in sessions
        )
        assert (
            all_rows.count((20, 20))
            == sum(stamp_date >= suffix_start for stamp_date in sessions) + 1
        )

        older_gap = asyncio.run(
            select_default_series_for_complete_range(
                _AsyncSessionAdapter(session),
                instrument_id=1,
                timeframe="D1",
                adjusted=True,
                market_series_id=20,
                start=datetime(2020, 1, 2, tzinfo=UTC),
                end=end,
            )
        )
        assert older_gap is False
    finally:
        session.close()
        engine.dispose()


def test_latest_contiguous_suffix_rejects_stale_narrow_and_basis_mismatch_candidates():
    engine, session = _db()
    try:
        session.add_all(
            [
                Instrument(
                    id=1,
                    instrument_type_id=1,
                    symbol="TEST",
                    name="Test instrument",
                    currency="USD",
                    is_active=True,
                    identity_status="resolved",
                ),
                MarketSeries(
                    id=10,
                    instrument_id=1,
                    data_source_id=10,
                    feed_scope="provider_native",
                    session_code="regular",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
                    adjustment_version="massive-split-adjusted",
                    is_canonical=True,
                    is_active=True,
                ),
                MarketSeries(
                    id=20,
                    instrument_id=1,
                    data_source_id=20,
                    feed_scope="iex",
                    session_code="regular",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
                    adjustment_version="alpaca-split",
                    is_canonical=True,
                    is_active=True,
                ),
                MarketSeries(
                    id=30,
                    instrument_id=1,
                    data_source_id=30,
                    feed_scope="raw",
                    session_code="regular",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.RAW,
                    adjustment_version="raw-v1",
                    is_canonical=True,
                    is_active=True,
                ),
                MarketSeries(
                    id=40,
                    instrument_id=1,
                    data_source_id=40,
                    feed_scope="iex",
                    session_code="extended",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
                    adjustment_version="alpaca-split-adjusted",
                    is_canonical=True,
                    is_active=True,
                ),
                MarketSeriesDefault(
                    instrument_id=1,
                    timeframe="D1",
                    is_adjusted=True,
                    market_series_id=10,
                    selection_reason="first_canonical",
                ),
            ]
        )
        start = datetime(2026, 1, 2, tzinfo=UTC)
        middle = datetime(2026, 1, 5, tzinfo=UTC)
        newest = datetime(2026, 1, 6, tzinfo=UTC)
        last = datetime(2026, 1, 7, tzinfo=UTC)
        end = last
        session.add_all(
            [
                _bar(series_id=10, ts=middle, data_source_id=10),
                _bar(series_id=10, ts=newest, data_source_id=10),
                _bar(series_id=10, ts=last, data_source_id=10),
                _bar(series_id=20, ts=middle, data_source_id=20),
                _bar(series_id=20, ts=newest, data_source_id=20),
                _bar(series_id=20, ts=last, data_source_id=20),
                _bar(series_id=30, ts=start, data_source_id=30),
                _bar(series_id=30, ts=middle, data_source_id=30),
                _bar(series_id=30, ts=newest, data_source_id=30),
                _bar(series_id=30, ts=last, data_source_id=30),
            ]
        )
        session.flush()

        async def try_candidate(series_id, candidate_start, adjusted=True, candidate_end=end):
            return await select_default_series_for_latest_contiguous_suffix(
                _AsyncSessionAdapter(session),
                instrument_id=1,
                timeframe="D1",
                adjusted=adjusted,
                market_series_id=series_id,
                requested_start=candidate_start,
                end=candidate_end,
            )

        assert (
            asyncio.run(try_candidate(20, start, candidate_end=datetime(2026, 1, 8, tzinfo=UTC)))
            is False
        )  # stale: the alternate does not reach the requested end
        assert asyncio.run(try_candidate(20, newest)) is False  # cannot narrow the current default
        assert asyncio.run(try_candidate(30, start)) is False  # raw is not adjusted-compatible
        assert asyncio.run(try_candidate(40, start)) is False  # session scope must stay stable
        assert session.execute(select(MarketSeriesDefault)).scalar_one().market_series_id == 10
    finally:
        session.close()
        engine.dispose()


def test_bulk_existing_timestamp_check_is_scoped_to_requested_provider_series():
    engine, session = _db()
    try:
        session.add_all(
            [
                MarketSeries(
                    id=10,
                    instrument_id=1,
                    data_source_id=10,
                    feed_scope="massive",
                    session_code="regular",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
                    adjustment_version="massive-split-adjusted",
                    is_canonical=True,
                    is_active=True,
                ),
                MarketSeries(
                    id=20,
                    instrument_id=1,
                    data_source_id=20,
                    feed_scope="alpaca_iex",
                    session_code="regular",
                    timeframe="D1",
                    adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
                    adjustment_version="alpaca-split",
                    is_canonical=True,
                    is_active=True,
                ),
                _bar(series_id=10, data_source_id=10),
                _bar(series_id=20, data_source_id=20),
            ]
        )
        session.flush()
        existing = asyncio.run(
            _existing_timestamps(
                _AsyncSessionAdapter(session),
                1,
                Timeframe.D1,
                True,
                market_series_ids={20},
            )
        )
        assert existing == {(datetime(2026, 1, 2, tzinfo=UTC), 20)}
    finally:
        session.close()
        engine.dispose()
