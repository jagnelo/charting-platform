from datetime import UTC, datetime, timedelta

from app.models.market_data_foundation import (
    Issuer,
    MarketEventConsensus,
    MarketEventPrelistingCandidate,
    MarketEventScanState,
    MarketRefreshJob,
)


def test_refresh_queue_status_requires_admin_and_hides_lease_token(
    client, admin_headers, db, instrument
):
    assert client.get("/api/v1/market-data/refresh/queue").status_code == 401

    job = MarketRefreshJob(
        request_key=f"unit-refresh:{instrument.id}",
        capability="price_history",
        instrument_id=instrument.id,
        timeframe="D1",
        status="leased",
        attempts=2,
        next_attempt_at=datetime.now(UTC),
        leased_until=datetime.now(UTC) - timedelta(seconds=1),
        lease_token="unit-secret-lease-token",
        last_error="GET https://provider.test/data?api_key=read-secret",
        metadata_payload={"source": "unit"},
    )
    db.add(job)
    db.flush()

    response = client.get(
        "/api/v1/market-data/refresh/queue?status=leased",
        headers=admin_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"] == {"leased": 1}
    row = payload["jobs"][0]
    assert row["id"] == job.id
    assert row["lease_expired"] is True
    assert row["attempts"] == 2
    assert "read-secret" not in row["last_error"]
    assert "<redacted>" in row["last_error"]
    assert row["metadata"] == {"source": "unit"}
    assert "lease_token" not in row


def test_event_consensus_status_requires_admin_and_exposes_conflicts(
    client, admin_headers, db, instrument
):
    consensus = MarketEventConsensus(
        consensus_key="market-event-consensus:v1:test",
        event_type="earnings",
        instrument_id=instrument.id,
        effective_date=datetime(2026, 9, 15).date(),
        status="conflicted",
        observation_count=2,
        source_count=2,
        agreement_fields=["event_type"],
        conflict_fields=[{"field": "eps_estimate"}],
        canonical_payload={"fields": {"event_type": "earnings"}},
        first_observed_at=datetime(2026, 9, 12, tzinfo=UTC),
        last_observed_at=datetime(2026, 9, 12, tzinfo=UTC),
        provenance={"algorithm": "market_event_consensus_v1"},
    )
    db.add(consensus)
    db.flush()

    assert client.get("/api/v1/market-data/event-consensus").status_code == 401
    response = client.get(
        "/api/v1/market-data/event-consensus",
        params={"status": "CONFLICTED", "instrument_id": instrument.id},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "conflicted"
    assert body[0]["source_count"] == 2
    assert body[0]["conflict_fields"] == [{"field": "eps_estimate"}]


def test_prelisting_candidates_require_admin_and_expose_provenance(
    client, admin_headers, db, instrument
):
    candidate = MarketEventPrelistingCandidate(
        candidate_key="event:admin-prelisting",
        instrument_id=instrument.id,
        proposed_symbol="NEWC",
        proposed_name="New Co",
        exchange_mic="XNAS",
        expected_listing_date=datetime(2026, 10, 1).date(),
        status="pending",
        stable_identifiers={"figi": "BBG000000001"},
        provider_sources=["edgar"],
        first_seen_at=datetime(2026, 9, 12, tzinfo=UTC),
        last_seen_at=datetime(2026, 9, 12, tzinfo=UTC),
        provenance={"algorithm": "market_event_prelisting_v1"},
    )
    db.add(candidate)
    db.flush()

    assert client.get("/api/v1/market-data/prelisting-candidates").status_code == 401
    response = client.get(
        "/api/v1/market-data/prelisting-candidates",
        params={"status": "PENDING", "instrument_id": instrument.id},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["proposed_symbol"] == "NEWC"
    assert body[0]["stable_identifiers"] == {"figi": "BBG000000001"}
    assert body[0]["provenance"]["algorithm"] == "market_event_prelisting_v1"


def test_event_scan_state_requires_admin_and_exposes_cursor_progress(
    client, admin_headers, db
):
    db.add(
        Issuer(
            id=42,
            domain_key="cik:0000000042",
            legal_name="Cursor Issuer",
            cik="0000000042",
            country_code="US",
        )
    )
    db.flush()
    state = MarketEventScanState(
        scan_key="edgar:ipo_pipeline:issuer_universe",
        provider="edgar",
        operation="fetch_ipo_pipeline_events",
        cursor_issuer_id=42,
        cycle_count=3,
        scanned_count=120,
        last_batch_count=40,
        last_event_count=5,
        last_failure_count=1,
        status="partial",
        last_error="one or more issuer pipeline reads failed",
        provenance={"bounded": True},
    )
    db.add(state)
    db.flush()

    assert client.get("/api/v1/market-data/event-scan-state").status_code == 401
    response = client.get(
        "/api/v1/market-data/event-scan-state",
        params={"scan_key": state.scan_key},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["cursor_issuer_id"] == 42
    assert body[0]["status"] == "partial"
    assert body[0]["provenance"] == {"bounded": True}
