from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models.etf_holdings import ETFHoldingsAdapterState, ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import Instrument
from app.services.etf_holdings import list_etfs_with_holdings, profile_to_out
from tests.unit.conftest import AsyncSessionAdapter

NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)


def _profile_snapshot(
    *,
    profile_id: int,
    composition_date: date,
    known_at: datetime,
    provider: str,
    provenance: str,
    snapshot_hash: str,
    count: int,
) -> ETFHoldingsSnapshot:
    return ETFHoldingsSnapshot(
        etf_profile_id=profile_id,
        composition_date=composition_date,
        known_at=known_at,
        published_at=known_at,
        provenance=provenance,
        source_provider=provider,
        source_quality="issuer",
        completeness_status="complete",
        row_count=count,
        resolved_count=count - 1,
        unresolved_count=1,
        snapshot_hash=snapshot_hash,
        extra_data={
            "legal_metadata": {"source_tier": "issuer_native", "expected_cadence": "weekly"},
            "artifact_identity_validation": {"status": "matched"},
        },
    )


def _legacy_list_statement(q: str | None):
    statement = (
        select(ETFProfile)
        .join(Instrument, Instrument.id == ETFProfile.instrument_id)
        .options(selectinload(ETFProfile.instrument), selectinload(ETFProfile.snapshots))
    )
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(Instrument.symbol.ilike(pattern), Instrument.name.ilike(pattern))
        )
    return statement.order_by(Instrument.symbol.asc()).limit(100)


async def _legacy_list_etfs_with_holdings(db, q: str | None):
    rows = (await db.execute(_legacy_list_statement(q))).scalars().all()
    return [await profile_to_out(db, row) for row in rows]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "seed_mode", [False, True], ids=["normal-source-visibility", "e2e-fixture-visibility"]
)
async def test_catalogue_batch_matches_legacy_output_and_bounds_profile_queries(
    db,
    instrument,
    monkeypatch,
    seed_mode: bool,
):
    monkeypatch.setattr(settings, "E2E_SEED_MARKET_DATA", seed_mode)
    expected_latest: dict[tuple[str, bool], int | None] = {}
    latest_checked = NOW - timedelta(minutes=1)

    for index in range(12):
        ticker = f"TST{index:02d}"
        current_instrument = Instrument(
            symbol=ticker,
            name=f"Measured Fund {index:02d}",
            currency="USD",
            instrument_type_id=instrument.instrument_type_id,
            is_active=True,
        )
        db.add(current_instrument)
        db.flush()
        profile = ETFProfile(
            instrument_id=current_instrument.id,
            issuer="Measured Issuer",
            adapter_key="spdr",
            adapter_confidence=Decimal("0.9500"),
            adapter_status="success",
            legal_metadata={"source_tier": "issuer_native", "expected_cadence": "weekly"},
        )
        db.add(profile)
        db.flush()

        if index == 0:
            db.add_all(
                [
                    _profile_snapshot(
                        profile_id=profile.id,
                        composition_date=date(2026, 11, 7),
                        known_at=NOW - timedelta(days=1),
                        provider="native-test",
                        provenance="issuer_current_holdings",
                        snapshot_hash="native-latest",
                        count=101,
                    ),
                    _profile_snapshot(
                        profile_id=profile.id,
                        composition_date=date(2026, 11, 6),
                        known_at=NOW - timedelta(hours=3),
                        provider="e2e_reference",
                        provenance="controlled_fixture",
                        snapshot_hash="fixture-earlier-known",
                        count=201,
                    ),
                    _profile_snapshot(
                        profile_id=profile.id,
                        composition_date=date(2026, 11, 6),
                        known_at=NOW - timedelta(hours=2),
                        provider="e2e_reference",
                        provenance="controlled_fixture",
                        snapshot_hash="fixture-later-known",
                        count=202,
                    ),
                ]
            )
        elif index == 1:
            # A profile with no stored composition exercises the missing-snapshot path.
            pass
        elif index == 11:
            # Canonical source snapshots remain hidden when the E2E fixture filter is active.
            db.add(
                _profile_snapshot(
                    profile_id=profile.id,
                    composition_date=date(2026, 11, 7),
                    known_at=NOW - timedelta(days=1),
                    provider="native-test",
                    provenance="issuer_current_holdings",
                    snapshot_hash="native-only",
                    count=111,
                )
            )
        else:
            db.add_all(
                [
                    _profile_snapshot(
                        profile_id=profile.id,
                        composition_date=date(2026, 11, 5),
                        known_at=NOW - timedelta(days=3),
                        provider="native-test",
                        provenance="issuer_current_holdings",
                        snapshot_hash=f"native-{index}",
                        count=100 + index,
                    ),
                    _profile_snapshot(
                        profile_id=profile.id,
                        composition_date=date(2026, 11, 4),
                        known_at=NOW - timedelta(days=4),
                        provider="e2e_reference",
                        provenance="controlled_fixture",
                        snapshot_hash=f"fixture-{index}",
                        count=200 + index,
                    ),
                ]
            )

        if index == 0:
            db.add_all(
                [
                    ETFHoldingsAdapterState(
                        etf_profile_id=profile.id,
                        adapter_key="prior-route",
                        status="failure",
                        last_checked_at=latest_checked,
                        last_failure_at=latest_checked,
                        failure_reason="older adapter state",
                    ),
                    ETFHoldingsAdapterState(
                        etf_profile_id=profile.id,
                        adapter_key="current-route",
                        status="success",
                        last_checked_at=latest_checked,
                        last_success_at=latest_checked,
                        row_count=300,
                        resolved_count=299,
                        unresolved_count=1,
                        completeness_status="complete",
                    ),
                    ETFHoldingsAdapterState(
                        etf_profile_id=profile.id,
                        adapter_key="unchecked-route",
                        status="failure",
                        last_checked_at=None,
                        last_failure_at=NOW,
                        failure_reason="unchecked state must sort last",
                    ),
                ]
            )
        elif index != 10:
            db.add(
                ETFHoldingsAdapterState(
                    etf_profile_id=profile.id,
                    adapter_key="current-route",
                    status="success",
                    last_checked_at=NOW - timedelta(minutes=index),
                    last_success_at=NOW - timedelta(minutes=index),
                    row_count=200 + index,
                    resolved_count=199 + index,
                    unresolved_count=1,
                    completeness_status="complete",
                )
            )
        db.flush()

        if index == 0:
            expected_latest[(ticker, False)] = next(
                snapshot.id
                for snapshot in profile.snapshots
                if snapshot.snapshot_hash == "native-latest"
            )
            expected_latest[(ticker, True)] = next(
                snapshot.id
                for snapshot in profile.snapshots
                if snapshot.snapshot_hash == "fixture-later-known"
            )

    outside_instrument = Instrument(
        symbol="OUT",
        name="Outside the measured catalogue",
        currency="USD",
        instrument_type_id=instrument.instrument_type_id,
        is_active=True,
    )
    db.add(outside_instrument)
    db.flush()
    db.add(ETFProfile(instrument_id=outside_instrument.id, adapter_status="unresolved"))
    db.flush()

    bind = db.get_bind()
    legacy_session = Session(bind=bind)
    batched_session = Session(bind=bind)
    async_legacy = AsyncSessionAdapter(legacy_session)
    async_batched = AsyncSessionAdapter(batched_session)
    statements: list[str] = []

    def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(bind, "before_cursor_execute", count_selects)
    try:
        legacy = await _legacy_list_etfs_with_holdings(async_legacy, "Measured Fund")
        legacy_query_count = len(statements)
        statements.clear()
        batched = await list_etfs_with_holdings(async_batched, "Measured Fund")
        batched_query_count = len(statements)
    finally:
        event.remove(bind, "before_cursor_execute", count_selects)
        legacy_session.close()
        batched_session.close()

    print(
        f"ETF profile catalogue SELECTs for {len(legacy)} profiles: "
        f"legacy={legacy_query_count}, batched={batched_query_count}"
    )
    assert legacy_query_count >= 2 * len(legacy) + 2
    assert batched_query_count <= 3
    assert batched_query_count < legacy_query_count
    assert [item.model_dump(mode="json") for item in batched] == [
        item.model_dump(mode="json") for item in legacy
    ]
    assert [item.symbol for item in batched] == [f"TST{index:02d}" for index in range(12)]
    expected_snapshot_id = expected_latest[("TST00", seed_mode)]
    assert batched[0].latest_snapshot_id == expected_snapshot_id
    assert batched[0].resolved_count == (201 if seed_mode else 100)
    if seed_mode:
        assert batched[-1].latest_snapshot_id is None
    assert batched[0].holdings_capability is not None
    assert batched[0].holdings_capability.last_checked_at == latest_checked.replace(tzinfo=None)
    assert batched[0].holdings_capability.failure_reason is None
    assert batched[10].holdings_capability is not None
    assert batched[10].holdings_capability.last_checked_at is None
