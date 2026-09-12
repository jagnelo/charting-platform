from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.models.instrument_sync_run import InstrumentSyncRun
from app.services import instrument_sync
from app.services.instrument_sync import _listing_evidence
from tests.unit.conftest import AsyncSessionAdapter


def test_listing_evidence_preserves_provider_dates_and_provenance():
    observed_at = datetime(2026, 8, 11, 12, 30, tzinfo=UTC)

    evidence = _listing_evidence(
        {
            "status": "delisted",
            "ipo_date": "2010-01-04",
            "delisting_date": "2026-07-31",
        },
        provider_name="alpha_vantage",
        observed_at=observed_at,
    )

    assert evidence == {
        "status": "delisted",
        "ipo_date": "2010-01-04",
        "delisting_date": "2026-07-31",
        "source": "alpha_vantage",
        "observed_at": "2026-08-11T12:30:00+00:00",
        "evidence_role": "provider_listing_observation",
    }


def test_listing_evidence_does_not_create_empty_lifecycle_claims():
    assert (
        _listing_evidence(
            {"status": "", "ipo_date": None, "delisting_date": None},
            provider_name="alpha_vantage",
            observed_at=datetime(2026, 8, 11, tzinfo=UTC),
        )
        is None
    )


@pytest.mark.asyncio
async def test_tracked_sync_redacts_failure_error(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(instrument_sync, "_provider_chain_label", AsyncMock(return_value="fixture"))

    async def failing_seed(*_args, **_kwargs):
        raise RuntimeError("GET https://provider.test/data?api_key=sync-secret")

    monkeypatch.setattr(instrument_sync, "seed_universe", failing_seed)

    with pytest.raises(RuntimeError, match="sync-secret"):
        await instrument_sync.run_tracked_sync(async_db, "seed-universe")

    run = db.query(InstrumentSyncRun).one()
    assert "sync-secret" not in (run.error or "")
    assert "<redacted>" in (run.error or "")
