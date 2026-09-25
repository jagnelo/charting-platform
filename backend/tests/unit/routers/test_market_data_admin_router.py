from datetime import UTC, datetime, timedelta

from app.config import provider_rate_limit_seed
from app.models.market_data_foundation import (
    Issuer,
    MarketEventConsensus,
    MarketEventPrelistingCandidate,
    MarketEventScanState,
    MarketRefreshJob,
    SecIssuerDirectoryCandidate,
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


def test_quota_baseline_reconciliation_is_admin_only_and_contract_derived(
    client, auth_headers, admin_headers
):
    body = {
        "provider": "marketdata_app",
        "capability": "price_history",
        "dimension": "credits_per_day",
        "used_units": 25,
        "observed_at": datetime.now(UTC).isoformat(),
        "evidence_reference": "dashboard:marketdata-app:2026-09-16",
    }
    path = "/api/v1/market-data/quota-coordinator/baselines"

    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers=auth_headers).status_code == 403

    response = client.post(path, json=body, headers=admin_headers)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["provider"] == "marketdata_app"
    assert payload["dimension"] == "credits_per_day"
    assert payload["unit"] == "credits"
    assert payload["quota_group"] == "account"
    assert payload["used_units"] == 25
    assert payload["limit_units"] == provider_rate_limit_seed("marketdata_app")["quota_contract"]["dimensions"][0]["limit"]
    assert payload["source"] == "operator_dashboard_attestation"
    assert payload["actor_user_id"] is not None
    assert "API key" not in response.text

    status = client.get(
        "/api/v1/market-data/quota-coordinator/baselines",
        params={
            "provider": "marketdata_app",
            "capability": "price_history",
            "dimension": "credits_per_day",
        },
        headers=admin_headers,
    )
    assert status.status_code == 200, status.text
    dimension = status.json()["dimensions"][0]
    assert dimension["status"] == "verified"
    assert dimension["effective_used_units"] == 25
    assert dimension["remaining_units"] == (
        provider_rate_limit_seed("marketdata_app")["quota_contract"]["dimensions"][0]["limit"]
        - 25
    )

    summary = client.get(
        "/api/v1/market-data/quota-coordinator?provider=marketdata_app",
        headers=admin_headers,
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["baselines"][0]["effective_used_units"] == 25
    assert summary.json()["baselines"][0]["remaining_units"] == (
        provider_rate_limit_seed("marketdata_app")["quota_contract"]["dimensions"][0]["limit"]
        - 25
    )

    bad_dimension = {**body, "dimension": "requests_per_second"}
    rejected = client.post(path, json=bad_dimension, headers=admin_headers)
    assert rejected.status_code == 422
    secret_reference = {**body, "evidence_reference": "dashboard token=secret-value"}
    assert client.post(path, json=secret_reference, headers=admin_headers).status_code == 422
    standalone_key = {**body, "evidence_reference": "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"}
    assert client.post(path, json=standalone_key, headers=admin_headers).status_code == 422
    bearer_value = {**body, "evidence_reference": "Bearer example-key-value"}
    assert client.post(path, json=bearer_value, headers=admin_headers).status_code == 422
    namespaced_key = {
        **body,
        "evidence_reference": "dashboard:alpaca:AbCdEf0123456789",
    }
    assert client.post(path, json=namespaced_key, headers=admin_headers).status_code == 422
    secret_labeled = {
        **body,
        "evidence_reference": "dashboard:alpaca:access-token-example",
    }
    assert client.post(path, json=secret_labeled, headers=admin_headers).status_code == 422


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


def test_event_scan_state_requires_admin_and_exposes_cursor_progress(client, admin_headers, db):
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


def test_sec_directory_candidate_report_is_admin_only_and_paginated(client, admin_headers, db):
    issuer = Issuer(
        domain_key="cik:0000000042",
        legal_name="Existing Issuer",
        cik="0000000042",
    )
    db.add(issuer)
    db.flush()
    fingerprint = "a" * 64
    db.add(
        MarketEventScanState(
            scan_key="edgar:ipo_pipeline:sec_directory",
            provider="edgar",
            operation="discover_issuer_ciks_page",
            cycle_count=1,
            scanned_count=2,
            status="complete",
            provenance={
                "active_cycle_number": 1,
                "active_materialization_mode": "disabled",
                "active_directory_total": 2,
                "active_source_fingerprint": fingerprint,
                "last_completed_report_cycle_number": 1,
                "last_completed_cycle_clean": True,
                "last_completed_directory_total": 2,
                "last_completed_materialization_mode": "disabled",
                "last_completed_source_fingerprint": fingerprint,
            },
        )
    )
    db.add_all(
        [
            SecIssuerDirectoryCandidate(
                cycle_number=1,
                directory_offset=0,
                directory_total=2,
                source_fingerprint=fingerprint,
                materialization_mode="disabled",
                cik="0000000041",
                conformed_name="New Issuer",
                name_candidates=["New Issuer"],
                tickers=["NEW"],
                source_payload={"cik": "0000000041", "name": "New Issuer", "tickers": ["NEW"]},
                admission_decision="would_create",
                decision_reason="No issuer currently matches this CIK.",
                cycle_status="complete",
                cycle_complete=True,
                cycle_clean=True,
                cycle_failure_count=0,
                observed_at=datetime.now(UTC),
            ),
            SecIssuerDirectoryCandidate(
                cycle_number=1,
                directory_offset=1,
                directory_total=2,
                source_fingerprint=fingerprint,
                materialization_mode="disabled",
                cik="0000000042",
                conformed_name="SEC Alias",
                name_candidates=["SEC Alias"],
                tickers=["OLD"],
                source_payload={"cik": "0000000042", "name": "SEC Alias", "tickers": ["OLD"]},
                admission_decision="already_exists",
                decision_reason="CIK already matches an issuer; its legal name is unchanged.",
                cycle_status="complete",
                cycle_complete=True,
                cycle_clean=True,
                cycle_failure_count=0,
                matched_issuer_id=issuer.id,
                matched_issuer_domain_key=issuer.domain_key,
                matched_issuer_legal_name=issuer.legal_name,
                observed_at=datetime.now(UTC),
            ),
        ]
    )
    db.flush()

    path = "/api/v1/market-data/sec-directory-candidates"
    assert client.get(path).status_code == 401
    first_page = client.get(path, params={"limit": 1}, headers=admin_headers)
    assert first_page.status_code == 200, first_page.text
    first_body = first_page.json()
    assert first_body["cycle_number"] == 1
    assert first_body["cycle_status"] == "complete"
    assert first_body["cycle_clean"] is True
    assert first_body["directory_total"] == 2
    assert first_body["candidate_count"] == 2
    assert first_body["next_offset"] == 1
    assert first_body["candidates"][0]["admission_decision"] == "would_create"
    assert first_body["candidates"][0]["cik"] == "0000000041"

    second_page = client.get(
        path,
        params={"cycle_number": 1, "offset": 1, "limit": 1},
        headers=admin_headers,
    )
    assert second_page.status_code == 200, second_page.text
    second_candidate = second_page.json()["candidates"][0]
    assert second_candidate["admission_decision"] == "already_exists"
    assert second_candidate["matched_issuer"] == {
        "id": issuer.id,
        "domain_key": issuer.domain_key,
        "legal_name": issuer.legal_name,
    }
