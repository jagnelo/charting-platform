from datetime import UTC, datetime, timedelta

from app.models.market_data_foundation import MarketEventConsensus, MarketRefreshJob


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
