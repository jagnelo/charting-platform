from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config import settings
from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import MarketRefreshJob, MarketSeries, MarketSeriesDefault
from app.models.ohlcv import OHLCVBar, Timeframe
from app.services import market_data
from app.services.derived_timeframes import derived_timeframe_needs_refresh
from app.services.market_data import _default_series_bar_condition
from app.services.ohlcv_coverage import _xnys_session_days
from app.tasks import data_tasks
from tests.unit.conftest import AsyncSessionAdapter


class _WorkerAdapter(AsyncSessionAdapter):
    def add(self, value):
        self._session.add(value)


class _WorkerSessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_args):
        return None


@pytest.mark.parametrize(
    ("retained_alternate", "older_chunk", "held_chunk"),
    [
        (False, False, False),
        (True, False, False),
        (True, True, False),
        (True, True, True),
    ],
)
@pytest.mark.asyncio
async def test_worker_persists_first_alternate_series_returns_bars_and_queues_older_chunk(
    db, instrument, monkeypatch, retained_alternate, older_chunk, held_chunk
):
    """The actual worker keeps useful deeper bars visible and queues older work."""
    massive = DataSource(name="massive")
    alpaca = DataSource(name="alpaca")
    db.add_all([massive, alpaca])
    db.flush()
    exchange = Exchange(mic="XNYS", name="New York Stock Exchange", country_code="US")
    db.add(exchange)
    db.flush()
    db.add(
        InstrumentListing(
            instrument_id=instrument.id,
            exchange_id=exchange.id,
            ticker=instrument.symbol,
            currency="USD",
            is_primary=True,
            is_active=True,
        )
    )
    db.flush()
    massive_series = MarketSeries(
        instrument_id=instrument.id,
        data_source_id=massive.id,
        feed_scope="provider_native",
        session_code="regular",
        timeframe=Timeframe.D1.value,
        adjustment_basis="split_adjusted",
        adjustment_version="massive-split-adjusted",
        is_canonical=True,
        is_active=True,
    )
    db.add(massive_series)
    db.flush()
    current_days = sorted(_xnys_session_days(date(2024, 11, 11), date(2026, 10, 30)))
    for session_day in current_days:
        stamp = datetime.combine(session_day, time.min, tzinfo=UTC)
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=massive.id,
                market_series_id=massive_series.id,
                timeframe=Timeframe.D1,
                ts=stamp,
                open=100,
                high=102,
                low=99,
                close=101,
                volume=1000,
                is_adjusted=True,
                adjustment_basis="split_adjusted",
                adjustment_version="massive-split-adjusted",
                session="regular",
                scope_key=f"series:{massive_series.id}:regular",
            )
        )
    default = MarketSeriesDefault(
        instrument_id=instrument.id,
        timeframe=Timeframe.D1.value,
        is_adjusted=True,
        market_series_id=massive_series.id,
        selection_reason="first_canonical",
    )
    db.add(default)

    coarse_provider_rows = {}
    for coarse_timeframe, row_count, anchor in (
        (Timeframe.W1, 104, date(2024, 10, 28)),
        (Timeframe.MN, 25, date(2024, 10, 1)),
    ):
        coarse_series = MarketSeries(
            instrument_id=instrument.id,
            data_source_id=massive.id,
            feed_scope="provider_native",
            session_code="regular",
            timeframe=coarse_timeframe.value,
            adjustment_basis="split_adjusted",
            adjustment_version="massive-split-adjusted",
            is_canonical=True,
            is_active=True,
        )
        db.add(coarse_series)
        db.flush()
        db.add(
            MarketSeriesDefault(
                instrument_id=instrument.id,
                timeframe=coarse_timeframe.value,
                is_adjusted=True,
                market_series_id=coarse_series.id,
                selection_reason="first_canonical",
            )
        )
        provider_rows = []
        for offset in range(row_count):
            period_date = anchor + timedelta(
                days=offset * (7 if coarse_timeframe is Timeframe.W1 else 30)
            )
            row = OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=massive.id,
                market_series_id=coarse_series.id,
                timeframe=coarse_timeframe,
                ts=datetime.combine(period_date, time.min, tzinfo=UTC),
                open=100,
                high=102,
                low=99,
                close=101,
                volume=1000,
                is_adjusted=True,
                adjustment_basis="split_adjusted",
                adjustment_version="massive-split-adjusted",
                session="regular",
                scope_key=f"series:{coarse_series.id}:regular",
            )
            provider_rows.append(row)
        db.add_all(provider_rows)
        coarse_provider_rows[coarse_timeframe] = (coarse_series, provider_rows)

    retained_alpaca_series = None
    if retained_alternate:
        retained_alpaca_series = MarketSeries(
            instrument_id=instrument.id,
            data_source_id=alpaca.id,
            feed_scope="iex",
            session_code="regular",
            timeframe=Timeframe.D1.value,
            adjustment_basis="split_adjusted",
            adjustment_version="alpaca-split-adjusted",
            is_canonical=True,
            is_active=True,
        )
        db.add(retained_alpaca_series)
        db.flush()
        for session_day in [
            date(2018, 11, 1),
            *_xnys_session_days(date(2020, 7, 27), date(2026, 10, 30)),
        ]:
            stamp = datetime.combine(session_day, time.min, tzinfo=UTC)
            db.add(
                OHLCVBar(
                    instrument_id=instrument.id,
                    data_source_id=alpaca.id,
                    market_series_id=retained_alpaca_series.id,
                    timeframe=Timeframe.D1,
                    ts=stamp,
                    open=200,
                    high=202,
                    low=199,
                    close=201,
                    volume=2000,
                    is_adjusted=True,
                    adjustment_basis="split_adjusted",
                    adjustment_version="alpaca-split-adjusted",
                    session="regular",
                    scope_key=f"series:{retained_alpaca_series.id}:regular",
                )
            )
        if held_chunk:
            # This is the retained upgrade state: current D1 is already the
            # deeper Alpaca series while W1/MN still select old Massive rows.
            default.market_series_id = retained_alpaca_series.id

    requested_start = datetime(2016, 1, 1, tzinfo=UTC)
    planned_start = datetime(2021, 5, 17, tzinfo=UTC)
    end = datetime(2026, 10, 30, 23, 59, tzinfo=UTC)
    preparation = {
        "range_mode": "deepest_admitted",
        "range_start": requested_start.isoformat(),
        "range_end": end.isoformat(),
        "selection_start": planned_start.isoformat(),
        "adjusted": True,
        "derive_coarse_timeframes": False,
    }
    chunk_start = requested_start if older_chunk else planned_start
    chunk_end = planned_start if older_chunk else end
    job = MarketRefreshJob(
        request_key=f"worker-deeper-default-{chunk_start.date()}",
        instrument_id=instrument.id,
        capability="price_history",
        timeframe=Timeframe.D1.value,
        start_at=chunk_start,
        end_at=chunk_end,
        priority=10,
        status="queued",
        attempts=0,
        next_attempt_at=datetime(2026, 11, 7, tzinfo=UTC),
        metadata_payload={"data_preparation_child": preparation},
    )
    db.add(job)
    db.commit()

    if retained_alternate:
        from app.services.ohlcv_coverage import assess_ohlcv_coverage

        retained_recent = (
            db.execute(
                select(OHLCVBar).where(
                    OHLCVBar.market_series_id == retained_alpaca_series.id,
                    OHLCVBar.ts >= planned_start,
                    OHLCVBar.ts <= end,
                )
            )
            .scalars()
            .all()
        )
        coverage_before_worker = assess_ohlcv_coverage(
            retained_recent,
            Timeframe.D1,
            planned_start,
            end,
            calendar="XNYS",
        )
        assert coverage_before_worker.status.value == "ready", coverage_before_worker

    adapter = _WorkerAdapter(db)

    class _Context:
        def __call__(self):
            return _WorkerSessionContext(adapter)

    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", _Context())
    monkeypatch.setattr(market_data, "pg_insert", sqlite_insert)
    monkeypatch.setattr(settings, "E2E_SEED_MARKET_DATA", False)

    created_provider_bars = []

    async def fetch_from_alpaca(
        _db, requested_instrument, timeframe, start, finish, adjusted, *, provider_name
    ):
        assert (
            not retained_alternate
        ), "the retained coherent alternate should cover the recent chunk"
        assert provider_name == "alpaca"
        assert requested_instrument.id == instrument.id
        assert adjusted is True
        series = MarketSeries(
            instrument_id=instrument.id,
            data_source_id=alpaca.id,
            feed_scope="iex",
            session_code="regular",
            timeframe=Timeframe.D1.value,
            adjustment_basis="split_adjusted",
            adjustment_version="alpaca-split-adjusted",
            is_canonical=True,
            is_active=True,
        )
        db.add(series)
        db.flush()
        for session_day in sorted(_xnys_session_days(start.date(), finish.date())):
            stamp = datetime.combine(session_day, time.min, tzinfo=UTC)
            bar = OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=alpaca.id,
                market_series_id=series.id,
                timeframe=timeframe,
                ts=stamp,
                open=200,
                high=202,
                low=199,
                close=201,
                volume=2000,
                is_adjusted=True,
                adjustment_basis="split_adjusted",
                adjustment_version="alpaca-split-adjusted",
                session="regular",
                scope_key=f"series:{series.id}:regular",
            )
            created_provider_bars.append(bar)
        return created_provider_bars

    monkeypatch.setattr(market_data, "_fetch_provider", fetch_from_alpaca)
    monkeypatch.setattr(data_tasks, "fetch_ohlcv", market_data.fetch_ohlcv)

    if retained_alternate:
        retained_read = await market_data._fetch_ohlcv_impl(
            adapter,
            instrument,
            Timeframe.D1,
            planned_start,
            end=end,
            adjusted=True,
            allow_provider_fetch=False,
            source_provider="alpaca",
        )
        assert retained_read

    async def plan_and_fetch(
        worker_db, *, job, instrument, timeframe, preparation, priority, redis
    ):
        preparation["source_provider"] = "alpaca"
        request_start = requested_start if older_chunk else planned_start
        request_end = planned_start if older_chunk else end
        if held_chunk:
            return (
                (request_start, request_end, requested_start, end, "alpaca", None),
                preparation,
                None,
                None,
                "native_usage_bootstrap_not_admitted",
                None,
            )
        fetched = await market_data.fetch_ohlcv(
            worker_db,
            instrument,
            timeframe,
            request_start,
            end=request_end,
            adjusted=True,
            source_provider="alpaca",
            allow_provider_fetch=not older_chunk,
        )
        return (
            (request_start, request_end, requested_start, end, "alpaca", None),
            preparation,
            None,
            None,
            None,
            fetched,
        )

    monkeypatch.setattr(data_tasks, "_plan_and_fetch_history_chunk", plan_and_fetch)

    claim_calls = 0

    async def claim(worker_db, *, limit):
        nonlocal claim_calls
        claim_calls += 1
        assert limit == 1
        if claim_calls > 1:
            return []
        job.status = "leased"
        job.lease_token = "initial-worker-lease"
        job.leased_until = datetime(2026, 11, 8, tzinfo=UTC)
        return [job]

    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", claim)
    completed_summaries = []

    async def complete(_db, completed_job, *, result_summary, **_kwargs):
        completed_job.status = "completed"
        completed_job.result_summary = {"outcome": "completed", **result_summary}
        completed_summaries.append(completed_job.result_summary)

    monkeypatch.setattr(data_tasks, "complete_refresh_job", complete)

    result = await data_tasks.process_refresh_jobs({})

    assert result["claimed"] == 1
    assert result["completed"] == 1, result
    summary = completed_summaries[0]
    if held_chunk:
        assert summary["preparation_status"] == "held"
        assert summary["reason_code"] == "native_usage_bootstrap_not_admitted"
        assert summary["retry_at"] is None
    else:
        assert summary["bars_observed"] > 0
    if retained_alternate:
        assert created_provider_bars == []
        assert retained_alpaca_series is not None
    if not held_chunk:
        assert summary["data_status"] == "partial"
        assert summary["range_coverage_status"] == "partial"
        assert summary["default_series_selected"] is True

    stored_default = db.execute(
        select(MarketSeriesDefault).where(
            MarketSeriesDefault.instrument_id == instrument.id,
            MarketSeriesDefault.timeframe == Timeframe.D1.value,
            MarketSeriesDefault.is_adjusted.is_(True),
        )
    ).scalar_one()
    assert stored_default.market_series_id != massive_series.id
    alpaca_series = (
        retained_alpaca_series
        or db.execute(
            select(MarketSeries).where(
                MarketSeries.data_source_id == alpaca.id,
                MarketSeries.timeframe == Timeframe.D1.value,
            )
        ).scalar_one()
    )
    assert stored_default.market_series_id == alpaca_series.id
    default_read = (
        db.execute(
            select(OHLCVBar)
            .where(
                OHLCVBar.instrument_id == instrument.id,
                OHLCVBar.timeframe == Timeframe.D1,
                OHLCVBar.is_adjusted.is_(True),
                _default_series_bar_condition(instrument.id, Timeframe.D1, True),
            )
            .order_by(OHLCVBar.ts)
        )
        .scalars()
        .all()
    )
    assert default_read
    assert {bar.market_series_id for bar in default_read} == {alpaca_series.id}
    if older_chunk:
        assert job.end_at < max(bar.ts for bar in default_read)
    if retained_alternate:
        assert min(bar.ts.date() for bar in default_read) == date(2018, 11, 1)
    else:
        expected_first_bar = min(_xnys_session_days(planned_start.date(), end.date()))
        assert min(bar.ts.date() for bar in default_read) == expected_first_bar
    assert max(bar.ts.date() for bar in default_read) == date(2026, 10, 30)

    # A D1 source switch also refreshes the derived defaults in the same worker
    # pass, without replacing the older provider-supplied coarse observations.
    for coarse_timeframe, (old_series, original_rows) in coarse_provider_rows.items():
        coarse_default = db.execute(
            select(MarketSeriesDefault).where(
                MarketSeriesDefault.instrument_id == instrument.id,
                MarketSeriesDefault.timeframe == coarse_timeframe.value,
                MarketSeriesDefault.is_adjusted.is_(True),
            )
        ).scalar_one()
        derived_series = db.get(MarketSeries, coarse_default.market_series_id)
        assert derived_series is not None
        assert derived_series.id != old_series.id
        assert derived_series.is_canonical is True
        assert derived_series.data_source_id == alpaca.id
        assert derived_series.adjustment_basis == "split_adjusted"
        assert derived_series.adjustment_version == "alpaca-split-adjusted"
        visible_coarse_rows = (
            db.execute(
                select(OHLCVBar).where(
                    OHLCVBar.instrument_id == instrument.id,
                    OHLCVBar.timeframe == coarse_timeframe,
                    OHLCVBar.is_adjusted.is_(True),
                    _default_series_bar_condition(instrument.id, coarse_timeframe, True),
                )
            )
            .scalars()
            .all()
        )
        assert visible_coarse_rows
        assert all(row.is_derived is True for row in visible_coarse_rows)
        assert {row.market_series_id for row in visible_coarse_rows} == {derived_series.id}
        assert {row.data_source_id for row in visible_coarse_rows} == {alpaca.id}
        retained_provider_rows = (
            db.execute(select(OHLCVBar).where(OHLCVBar.market_series_id == old_series.id))
            .scalars()
            .all()
        )
        assert len(retained_provider_rows) == len(original_rows)
        assert all(row.data_source_id == massive.id for row in retained_provider_rows)
        assert all(
            row.adjustment_version == "massive-split-adjusted" for row in retained_provider_rows
        )
        if retained_alternate:
            from app.services.ohlcv_coverage import assess_ohlcv_coverage

            coarse_coverage = assess_ohlcv_coverage(
                visible_coarse_rows,
                coarse_timeframe,
                min(row.ts for row in visible_coarse_rows),
                max(row.ts for row in visible_coarse_rows),
                calendar="XNYS",
            )
            assert coarse_coverage.status.value == "partial"
        else:
            from app.services.ohlcv_coverage import assess_ohlcv_coverage

            coarse_coverage = assess_ohlcv_coverage(
                visible_coarse_rows,
                coarse_timeframe,
                min(row.ts for row in visible_coarse_rows),
                max(row.ts for row in visible_coarse_rows),
                calendar="XNYS",
            )
            assert coarse_coverage.status.value == "ready"
        assert not await derived_timeframe_needs_refresh(
            AsyncSessionAdapter(db),
            instrument.id,
            coarse_timeframe,
            adjusted=True,
        )

    # Original Massive observations remain stored and keep their source lineage.
    retained_massive = (
        db.execute(select(OHLCVBar).where(OHLCVBar.market_series_id == massive_series.id))
        .scalars()
        .all()
    )
    assert len(retained_massive) == len(current_days)
    assert all(bar.data_source_id == massive.id for bar in retained_massive)
    if retained_alternate:
        from app.services.ohlcv_coverage import assess_ohlcv_coverage

        coverage = assess_ohlcv_coverage(
            default_read,
            Timeframe.D1,
            requested_start,
            end,
            calendar="XNYS",
        )
        assert coverage.status.value == "partial"
        assert coverage.missing_slices

    continuations = (
        db.execute(
            select(MarketRefreshJob).where(
                MarketRefreshJob.id != job.id,
                MarketRefreshJob.capability == "price_history",
            )
        )
        .scalars()
        .all()
    )
    if held_chunk or older_chunk:
        assert continuations == []
    else:
        continuation = continuations[0]
        continuation_prep = continuation.metadata_payload["data_preparation_child"]
        assert continuation.status == "queued"
        assert continuation_prep["chunk"] is True
        assert continuation_prep["source_provider"] == "alpaca"
        assert continuation_prep["range_start"] == requested_start.isoformat()
        assert continuation.start_at.replace(tzinfo=UTC) < planned_start
        assert continuation.end_at.replace(tzinfo=UTC) < planned_start
