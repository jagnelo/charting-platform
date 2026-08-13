from datetime import UTC, date, datetime

import pytest

from app.models.etf_holdings import ETFHoldingsSnapshot, ETFProfile
from app.services.etf_holdings import get_latest_snapshot
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_normal_bootstrap_can_exclude_controlled_fixture_snapshot(db, instrument):
    profile = ETFProfile(
        instrument_id=instrument.id,
        issuer="Test issuer",
        adapter_status="success",
    )
    db.add(profile)
    db.flush()
    db.add_all(
        [
            ETFHoldingsSnapshot(
                etf_profile_id=profile.id,
                composition_date=date(2026, 1, 1),
                known_at=datetime(2026, 1, 2, tzinfo=UTC),
                provenance="issuer_self_snapshotted_holdings",
                source_provider="test-provider",
                source_quality="self_snapshotted_holdings",
                completeness_status="unknown",
                snapshot_hash="canonical-snapshot",
            ),
            ETFHoldingsSnapshot(
                etf_profile_id=profile.id,
                composition_date=date(2026, 2, 1),
                known_at=datetime(2026, 2, 2, tzinfo=UTC),
                provenance="controlled_fixture",
                source_provider="e2e_reference",
                source_quality="fixture",
                completeness_status="complete",
                snapshot_hash="fixture-snapshot",
            ),
        ]
    )
    db.flush()

    async_db = AsyncSessionAdapter(db)
    latest = await get_latest_snapshot(async_db, instrument.id, include_holdings=False)
    canonical = await get_latest_snapshot(
        async_db,
        instrument.id,
        include_holdings=False,
        include_controlled_fixture=False,
    )

    assert latest is not None
    assert latest.provenance == "controlled_fixture"
    assert canonical is not None
    assert canonical.provenance == "issuer_self_snapshotted_holdings"
