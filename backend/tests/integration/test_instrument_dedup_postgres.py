"""Duplicate-instrument detection and merge against real PostgreSQL.

The merge introspects ``pg_constraint``/``pg_index``, uses ``ctid`` set deletes,
``jsonb_set`` on JSON columns and ``FOR UPDATE`` locks; SQLite cannot run any
of that.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.instrument_dedup import (
    MergePlan,
    merge_duplicate_instruments,
    merge_instrument_pair,
    plan_duplicate_merges,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

DAY0 = datetime(2026, 1, 5, tzinfo=UTC)


def _async_database_url(raw_url: str) -> str:
    return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
        "postgresql+psycopg2://", "postgresql+asyncpg://", 1
    )


@pytest_asyncio.fixture
async def sessions(request, test_database_url):
    raw_url = test_database_url or request.getfixturevalue("pg_container").get_connection_url()
    schema = f"instrument_dedup_{uuid4().hex}"
    import app.models  # noqa: F401
    from app.database import Base

    bootstrap = create_async_engine(_async_database_url(raw_url))
    scoped = None
    created = False
    try:
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection.execution_options(schema_translate_map={None: schema})
                )
            )
        scoped = create_async_engine(
            _async_database_url(raw_url),
            connect_args={"server_settings": {"search_path": schema}},
        )
        yield async_sessionmaker(scoped, expire_on_commit=False)
    finally:
        if scoped is not None:
            await scoped.dispose()
        if created:
            async with bootstrap.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap.dispose()


async def _scalar(session, sql, **params):
    return (await session.execute(text(sql), params)).scalar_one()


async def _base(session):
    await session.execute(text("INSERT INTO asset_class (name) VALUES ('Equity')"))
    ac = await _scalar(session, "SELECT id FROM asset_class")
    await session.execute(
        text("INSERT INTO instrument_type (name, asset_class_id) VALUES ('Stock', :a)"), {"a": ac}
    )
    await session.execute(text("INSERT INTO exchange (mic, name) VALUES ('XNYS', 'NYSE')"))
    await session.execute(text("INSERT INTO data_source (name, is_active) VALUES ('alpaca', true)"))
    await session.execute(
        text(
            'INSERT INTO "user" (username, email, hashed_password, is_active, is_admin, settings) '
            "VALUES ('u','u@example.test','x', true, false, '{}')"
        )
    )
    return {
        "type": await _scalar(session, "SELECT id FROM instrument_type"),
        "exchange": await _scalar(session, "SELECT id FROM exchange"),
        "source": await _scalar(session, "SELECT id FROM data_source"),
        "user": await _scalar(session, 'SELECT id FROM "user"'),
    }


async def _instrument(
    session, ctx, symbol, name, *, domain_key=None, status="resolved", identifiers=(), listing=True
):
    iid = await _scalar(
        session,
        "INSERT INTO instrument (instrument_type_id, symbol, name, is_active, is_synthetic, "
        "domain_key, identity_status) VALUES (:t, :s, :n, true, false, :d, :st) RETURNING id",
        t=ctx["type"],
        s=symbol,
        n=name,
        d=domain_key,
        st=status,
    )
    for kind, value in identifiers:
        await session.execute(
            text(
                "INSERT INTO instrument_identifier (instrument_id, identifier_type, "
                "identifier_value, is_primary, is_active) "
                "VALUES (:i, CAST(:k AS instrumentidentifiertype), :v, :p, true)"
            ),
            {"i": iid, "k": kind, "v": value, "p": kind != "INTERNAL"},
        )
    if listing:
        await session.execute(
            text(
                "INSERT INTO instrument_listing (instrument_id, exchange_id, ticker, "
                "is_primary, is_active) VALUES (:i, :e, :t, true, true)"
            ),
            {"i": iid, "e": ctx["exchange"], "t": symbol},
        )
    return iid


async def _series_and_bars(session, ctx, iid, days, *, close=100.0):
    d1 = await _scalar(
        session,
        "INSERT INTO market_series (instrument_id, exchange_id, data_source_id, feed_scope, "
        "session_code, timeframe, adjustment_basis, adjustment_version, is_canonical, is_active, provenance)"
        " VALUES (:i, :e, :s, 'iex', 'regular', 'D1', 'RAW', 'v1', true, true, '{}') RETURNING id",
        i=iid,
        e=ctx["exchange"],
        s=ctx["source"],
    )
    w1 = await _scalar(
        session,
        "INSERT INTO market_series (instrument_id, exchange_id, data_source_id, feed_scope, "
        "session_code, timeframe, adjustment_basis, adjustment_version, is_canonical, is_active, provenance)"
        " VALUES (:i, :e, :s, :fs, 'regular', 'W1', 'RAW', 'v1', true, true, '{}') RETURNING id",
        i=iid,
        e=ctx["exchange"],
        s=ctx["source"],
        fs=f"derived-d1-{d1}",
    )
    for day in days:
        await session.execute(
            text(
                "INSERT INTO ohlcv_bar (instrument_id, data_source_id, timeframe, ts, open, high, "
                "low, close, volume, is_adjusted, session, market_series_id, scope_key, adjustment_basis, adjustment_version) "
                "VALUES (:i, :s, 'D1', :ts, :c, :c, :c, :c, 10, false, 'regular', :m, :k, 'raw', 'legacy')"
            ),
            {
                "i": iid,
                "s": ctx["source"],
                "ts": DAY0 + timedelta(days=day),
                "c": close + day,
                "m": d1,
                "k": f"series:{d1}:regular",
            },
        )
    return d1, w1


async def _seed_pair(session, ctx):
    canonical = await _instrument(
        session,
        ctx,
        "ABBV",
        "AbbVie Inc.",
        domain_key="composite-figi:BBG0025Y4RY4",
        identifiers=[("COMPOSITE_FIGI", "BBG0025Y4RY4"), ("INTERNAL", "instrument:c")],
    )
    duplicate = await _instrument(
        session,
        ctx,
        "ABBV",
        "ABBVIE INC.",
        domain_key="cusip:00287Y109",
        identifiers=[("CUSIP", "00287Y109"), ("INTERNAL", "instrument:d")],
    )
    c_d1, _ = await _series_and_bars(session, ctx, canonical, [0, 1, 2])
    d_d1, d_w1 = await _series_and_bars(session, ctx, duplicate, [1, 2, 3, 4])
    await session.execute(
        text(
            "INSERT INTO favorite_instrument (user_id, instrument_id, position, added_at) "
            "VALUES (:u, :i, 0, now())"
        ),
        {"u": ctx["user"], "i": duplicate},
    )
    return canonical, duplicate, c_d1, d_d1, d_w1


async def test_plan_and_merge_unions_bars_and_repoints_children(sessions):
    async with sessions() as session:
        ctx = await _base(session)
        canonical, duplicate, c_d1, d_d1, d_w1 = await _seed_pair(session, ctx)
        await session.commit()

    async with sessions() as session:
        report = await plan_duplicate_merges(session)
    assert [(p.canonical_id, p.duplicate_id, p.reason) for p in report.plans] == [
        (canonical, duplicate, "legacy_key_vs_figi")
    ]
    assert report.plans[0].detail["evidence"] == "same_listing"

    summary = await merge_duplicate_instruments(sessions, max_pairs=10)
    assert summary["merged"] == 1 and summary["failed"] == 0

    async with sessions() as session:
        assert await _scalar(session, "SELECT count(*) FROM instrument") == 1
        # Union of {0,1,2} and {1,2,3,4}: five distinct days, canonical's rows win.
        assert await _scalar(session, "SELECT count(*) FROM ohlcv_bar") == 5
        assert (await _scalar(session, "SELECT count(DISTINCT instrument_id) FROM ohlcv_bar")) == 1
        assert (
            await _scalar(
                session, "SELECT count(*) FROM ohlcv_bar WHERE instrument_id <> :c", c=canonical
            )
            == 0
        )
        # Series merged (D1 and derived W1 twins), bars point at canonical series only.
        assert await _scalar(session, "SELECT count(*) FROM market_series") == 2
        assert (
            await _scalar(
                session, "SELECT count(*) FROM ohlcv_bar WHERE market_series_id <> :s", s=c_d1
            )
            == 0
        )
        assert (
            await _scalar(
                session,
                "SELECT count(*) FROM ohlcv_bar WHERE scope_key <> :k",
                k=f"series:{c_d1}:regular",
            )
            == 0
        )
        assert (
            await _scalar(
                session, "SELECT count(*) FROM market_series WHERE id IN (:a, :b)", a=d_d1, b=d_w1
            )
            == 0
        )
        # Favorite repointed; the legacy CUSIP now identifies the survivor.
        assert await _scalar(session, "SELECT instrument_id FROM favorite_instrument") == canonical
        assert (
            await _scalar(
                session,
                "SELECT instrument_id FROM instrument_identifier "
                "WHERE identifier_type::text = 'CUSIP'",
            )
            == canonical
        )
        assert (
            await _scalar(
                session,
                "SELECT count(*) FROM instrument_identifier WHERE is_primary AND instrument_id=:c",
                c=canonical,
            )
            == 1
        )
        assert await _scalar(session, "SELECT count(*) FROM instrument_listing") == 1
        log = (
            await session.execute(
                text(
                    "SELECT duplicate_instrument_id, canonical_instrument_id, reason "
                    "FROM instrument_merge_log"
                )
            )
        ).one()
        assert tuple(log) == (duplicate, canonical, "legacy_key_vs_figi")

    # Idempotent: nothing left to plan or merge.
    again = await merge_duplicate_instruments(sessions, max_pairs=10)
    assert again["planned"] == 0 and again["merged"] == 0

    # Replaying the same pair directly reports it as already merged.
    async with sessions() as session:
        result = await merge_instrument_pair(
            session, MergePlan(canonical, duplicate, "legacy_key_vs_figi")
        )
        assert result.status == "already_merged"


async def test_every_foreign_key_to_instrument_is_covered(sessions):
    from app.database import Base
    from app.services.instrument_dedup import _foreign_key_columns

    async with sessions() as session:
        columns = {
            (fk.table.strip('"'), fk.column)
            for fk in await _foreign_key_columns(session, "instrument")
        }
    expected = {
        (table.name, column.name)
        for table in Base.metadata.tables.values()
        for column in table.columns
        for fk in column.foreign_keys
        if fk.column.table.name == "instrument"
    }
    assert expected <= columns


async def test_share_classes_with_different_cusips_are_never_merged(sessions):
    async with sessions() as session:
        ctx = await _base(session)
        await _instrument(
            session,
            ctx,
            "RUSH",
            "Rush Enterprises Class A",
            domain_key="cusip:781846209",
            identifiers=[("CUSIP", "781846209")],
        )
        await _instrument(
            session,
            ctx,
            "RUSH",
            "Rush Enterprises Class B",
            domain_key="cusip:781846308",
            identifiers=[("CUSIP", "781846308")],
        )
        await session.commit()
    async with sessions() as session:
        report = await plan_duplicate_merges(session)
    assert report.plans == []
    assert report.skipped["domain_key_conflict"] == 1


async def test_keyless_row_needs_evidence_and_separator_variant_merges(sessions):
    async with sessions() as session:
        ctx = await _base(session)
        stable = await _instrument(
            session,
            ctx,
            "BRK.B",
            "Berkshire Hathaway Inc.",
            domain_key="composite-figi:BBG000DWG505",
            identifiers=[("COMPOSITE_FIGI", "BBG000DWG505")],
            listing=False,
        )
        variant = await _instrument(
            session, ctx, "BRK-B", "BERKSHIRE HATHAWAY INC", status="quarantined", listing=False
        )
        # Same ticker, no listing overlap and no bars: no evidence, not merged.
        await _instrument(
            session,
            ctx,
            "ZZZ",
            "Zed Corp",
            domain_key="composite-figi:BBG1",
            identifiers=[("COMPOSITE_FIGI", "BBG1")],
            listing=False,
        )
        await _instrument(session, ctx, "ZZZ", "Zed Corp", status="quarantined", listing=False)
        await session.commit()
    async with sessions() as session:
        report = await plan_duplicate_merges(session)
    assert [(p.canonical_id, p.duplicate_id, p.reason) for p in report.plans] == [
        (stable, variant, "separator_variant")
    ]
    assert report.skipped["insufficient_evidence"] == 1


async def test_agreeing_bars_are_evidence_and_disagreeing_bars_are_not(sessions):
    async with sessions() as session:
        ctx = await _base(session)
        a = await _instrument(
            session,
            ctx,
            "AGR",
            "Agree Corp",
            domain_key="composite-figi:A",
            identifiers=[("COMPOSITE_FIGI", "A")],
            listing=False,
        )
        b = await _instrument(
            session, ctx, "AGR", "Agree Corp", status="quarantined", listing=False
        )
        c = await _instrument(
            session,
            ctx,
            "DIS",
            "Dis Corp",
            domain_key="composite-figi:C",
            identifiers=[("COMPOSITE_FIGI", "C")],
            listing=False,
        )
        d = await _instrument(session, ctx, "DIS", "Dis Corp", status="quarantined", listing=False)
        days = list(range(25))
        await _series_and_bars(session, ctx, a, days)
        await _series_and_bars(session, ctx, b, days)
        await _series_and_bars(session, ctx, c, days, close=100.0)
        await _series_and_bars(session, ctx, d, days, close=500.0)
        await session.commit()
    async with sessions() as session:
        report = await plan_duplicate_merges(session)
    assert [(p.canonical_id, p.duplicate_id) for p in report.plans] == [(a, b)]
    assert report.plans[0].detail["evidence"] == "bar_agreement"
    assert report.skipped["insufficient_evidence"] == 1
    _ = (c, d)


async def test_leased_refresh_job_defers_and_job_payload_is_rewritten(sessions):
    async with sessions() as session:
        ctx = await _base(session)
        canonical, duplicate, *_ = await _seed_pair(session, ctx)
        await session.execute(
            text(
                "INSERT INTO market_refresh_job (request_key, instrument_id, capability, status, priority, attempts, "
                "next_attempt_at, metadata_payload) VALUES ('k1', :i, 'history', 'leased', 100, 0, now(), "
                "CAST(:p AS json))"
            ),
            {
                "i": duplicate,
                "p": f'{{"data_preparation_child": {{"instrument_id": {duplicate}}}}}',
            },
        )
        await session.commit()
    plan = MergePlan(canonical, duplicate, "legacy_key_vs_figi")
    async with sessions() as session:
        assert (await merge_instrument_pair(session, plan)).status == "skipped_open_lease"
        await session.rollback()
    async with sessions() as session:
        await session.execute(text("UPDATE market_refresh_job SET status='queued'"))
        await session.commit()
    async with sessions() as session:
        assert (await merge_instrument_pair(session, plan)).status == "merged"
        await session.commit()
    async with sessions() as session:
        row = (
            await session.execute(
                text(
                    "SELECT instrument_id, metadata_payload::jsonb #>> "
                    "'{data_preparation_child,instrument_id}' FROM market_refresh_job"
                )
            )
        ).one()
        assert tuple(row) == (canonical, str(canonical))


async def test_failed_merge_rolls_back_completely(sessions):
    async with sessions() as session:
        ctx = await _base(session)
        canonical, duplicate, *_ = await _seed_pair(session, ctx)
        await session.commit()
    async with sessions() as session:
        await session.execute(text("DROP TABLE instrument_merge_log"))
        await session.commit()
    async with sessions() as session:
        with pytest.raises(Exception):
            await merge_instrument_pair(
                session, MergePlan(canonical, duplicate, "legacy_key_vs_figi")
            )
        await session.rollback()
    async with sessions() as session:
        assert await _scalar(session, "SELECT count(*) FROM instrument") == 2
        assert await _scalar(session, "SELECT count(*) FROM ohlcv_bar") == 7


async def test_empty_database_is_a_noop(sessions):
    summary = await merge_duplicate_instruments(sessions)
    assert summary["planned"] == 0 and summary["merged"] == 0
