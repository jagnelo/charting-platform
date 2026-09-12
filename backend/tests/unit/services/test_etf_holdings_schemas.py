from datetime import UTC, datetime

from app.schemas.etf_holdings import (
    ETFConstituentTimelinePoint,
    ETFHoldingsAdapterStateOut,
    ETFHoldingsBackfillFilingOut,
    ETFHoldingsBackfillJobOut,
    ETFHoldingsDateOut,
    ETFHoldingsSnapshotOut,
    ETFHoldingsWeightEvolutionPointOut,
)


def test_etf_holdings_response_schemas_serialize_timestamps_as_canonical_utc_z():
    naive = datetime(2026, 9, 12, 14, 30)
    aware = datetime(2026, 9, 12, 16, 30, tzinfo=UTC)

    adapter = ETFHoldingsAdapterStateOut(
        id=1,
        etf_profile_id=2,
        adapter_key="sec_nport",
        status="ready",
        last_success_at=naive,
        last_failure_at=aware,
        last_checked_at=naive,
        published_at=aware,
    )
    snapshot = ETFHoldingsSnapshotOut(
        id=3,
        etf_profile_id=2,
        etf_instrument_id=4,
        etf_symbol="XLK",
        etf_name="Technology Select Sector SPDR Fund",
        composition_date="2026-09-01",
        known_at=naive,
        published_at=aware,
        provenance="sec",
        source_provider="sec",
        source_quality="issuer_filing",
        completeness_status="complete",
        row_count=10,
        resolved_count=10,
        unresolved_count=0,
        parser_version="sec-v1",
    )
    date_row = ETFHoldingsDateOut(
        snapshot_id=3,
        composition_date="2026-09-01",
        known_at=naive,
        published_at=aware,
        row_count=10,
        resolved_count=10,
        unresolved_count=0,
        provenance="sec",
        source_provider="sec",
        source_quality="issuer_filing",
    )
    timeline = ETFConstituentTimelinePoint(
        snapshot_id=3,
        composition_date="2026-09-01",
        known_at=naive,
        published_at=aware,
        weight=0.25,
        source_provider="sec",
        provenance="sec",
    )
    evolution = ETFHoldingsWeightEvolutionPointOut(
        snapshot_id=3,
        composition_date="2026-09-01",
        known_at=naive,
        published_at=aware,
        weight=0.25,
        source_provider="sec",
        provenance="sec",
    )
    filing = ETFHoldingsBackfillFilingOut(
        id=5,
        etf_profile_id=2,
        accession_number="0000000000-26-000001",
        form="NPORT-P",
        acceptance_datetime=naive,
        ingested_at=aware,
        status="ingested",
    )
    job = ETFHoldingsBackfillJobOut(
        id=6,
        etf_profile_id=2,
        source_provider="sec",
        job_type="backfill",
        status="completed",
        discovered_count=1,
        ingested_count=1,
        skipped_count=0,
        failed_count=0,
        started_at=naive,
        completed_at=aware,
        filings=[filing],
    )

    assert adapter.model_dump(mode="json")["last_success_at"] == "2026-09-12T14:30:00Z"
    assert adapter.model_dump(mode="json")["published_at"] == "2026-09-12T16:30:00Z"
    assert snapshot.model_dump(mode="json")["known_at"] == "2026-09-12T14:30:00Z"
    assert date_row.model_dump(mode="json")["published_at"] == "2026-09-12T16:30:00Z"
    assert timeline.model_dump(mode="json")["known_at"] == "2026-09-12T14:30:00Z"
    assert evolution.model_dump(mode="json")["published_at"] == "2026-09-12T16:30:00Z"
    assert filing.model_dump(mode="json")["acceptance_datetime"] == "2026-09-12T14:30:00Z"
    assert job.model_dump(mode="json")["started_at"] == "2026-09-12T14:30:00Z"
    assert job.model_dump(mode="json")["completed_at"] == "2026-09-12T16:30:00Z"
    assert job.model_dump(mode="json")["filings"][0]["ingested_at"] == "2026-09-12T16:30:00Z"
