from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.data_source import DataSource
from app.models.market_data_foundation import (
    Issuer,
    MarketEventScanState,
    MarketRefreshJob,
    SecIssuerDirectoryCandidate,
)
from app.models.provider_observation import LatestPriceSnapshot
from app.models.provider_runtime import ProviderCapability, ProviderCapacityEvent
from app.models.tokenized_asset import TokenizedAssetDetail


def test_capacity_events_are_admin_only_and_expose_reset_evidence(client, admin_headers, db):
    assert client.get("/api/v1/market-data/capacity-events").status_code == 401

    source = DataSource(name="capacity-test", is_active=True)
    db.add(source)
    db.flush()
    event = ProviderCapacityEvent(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:AAPL:D1",
        scope="api_key",
        status_code=429,
        message="429 Too Many Requests",
        retry_at=datetime.now(UTC) + timedelta(seconds=30),
        response_headers={"retry-after": "30", "x-ratelimit-limit": "10"},
        observed_at=datetime.now(UTC),
        error_type="ProviderRateLimitError",
    )
    db.add(event)
    db.commit()

    response = client.get("/api/v1/market-data/capacity-events", headers=admin_headers)
    assert response.status_code == 200
    row = next(item for item in response.json() if item["data_source_id"] == source.id)
    assert row["capability"] == "price_history"
    assert row["status_code"] == 429
    assert row["scope"] == "api_key"
    assert row["response_headers"]["retry-after"] == "30"


def test_refresh_queue_status_is_admin_only_and_hides_lease_tokens(
    client, admin_headers, db, instrument
):
    assert client.get("/api/v1/market-data/refresh/queue").status_code == 401

    db.add(
        MarketRefreshJob(
            request_key=f"admin-refresh:{instrument.id}",
            capability="price_history",
            instrument_id=instrument.id,
            timeframe="D1",
            next_attempt_at=datetime.now(UTC),
            metadata_payload={"source": "integration"},
        )
    )
    db.commit()

    response = client.get("/api/v1/market-data/refresh/queue", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"]["queued"] == 1
    row = next(item for item in payload["jobs"] if item["instrument_id"] == instrument.id)
    assert row["status"] == "queued"
    assert row["started_at"] is None
    assert row["finished_at"] is None
    assert row["result_summary"] is None
    assert "lease_token" not in row


def test_sec_issuer_report_materialization_uses_persisted_clean_rows_only(
    client, admin_headers, db
):
    fingerprint = "d" * 64
    db.add(
        MarketEventScanState(
            scan_key="edgar:ipo_pipeline:sec_directory",
            provider="edgar",
            operation="discover_issuer_ciks_page",
            cycle_count=1,
            status="complete",
            provenance={
                "last_completed_cycle_number": 1,
                "last_completed_report_cycle_number": 1,
                "last_completed_cycle_clean": True,
                "last_completed_materialization_mode": "disabled",
                "last_completed_source_fingerprint": fingerprint,
                "last_completed_directory_total": 1,
            },
        )
    )
    db.add(
        SecIssuerDirectoryCandidate(
            cycle_number=1,
            directory_offset=0,
            directory_total=1,
            source_fingerprint=fingerprint,
            materialization_mode="disabled",
            cik="0000000091",
            conformed_name="Persisted SEC Issuer",
            name_candidates=["Persisted SEC Issuer"],
            tickers=["PSI"],
            source_payload={"cik": "0000000091", "name": "Persisted SEC Issuer"},
            admission_decision="would_create",
            decision_reason="No issuer matches this CIK.",
            cycle_status="complete",
            cycle_complete=True,
            cycle_clean=True,
            cycle_failure_count=0,
            observed_at=datetime.now(UTC),
        )
    )
    db.commit()

    assert (
        client.post(
            "/api/v1/market-data/sec-directory-candidates/materialize",
            json={"reviewed_cycle_count": 1},
        ).status_code
        == 401
    )
    response = client.post(
        "/api/v1/market-data/sec-directory-candidates/materialize",
        json={"reviewed_cycle_count": 1, "max_candidates": 1},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1
    assert response.json()["provider_http_requests"] == 0
    issuer = db.query(Issuer).filter_by(cik="0000000091").one()
    assert issuer.domain_key == "cik:0000000091"
    assert issuer.provenance["source_fingerprint"] == fingerprint


def test_short_interest_refresh_is_admin_only_and_accepts_resumable_page_budget(
    client, admin_headers, instrument, monkeypatch
):
    from datetime import date

    from app.services import short_interest

    calls = []

    async def fake_refresh(db, instrument_id, **kwargs):
        calls.append((instrument_id, kwargs))
        return {"status": "pending", "next_page_pending": True}

    monkeypatch.setattr(short_interest, "refresh_short_interest_for_instrument", fake_refresh)
    path = (
        f"/api/v1/market-data/short-interest/{instrument.id}/refresh"
        "?start=2026-08-01&end=2026-08-31&max_pages=3"
    )

    assert client.post(path).status_code == 401
    response = client.post(path, headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == {"status": "pending", "next_page_pending": True}
    assert calls == [
        (
            instrument.id,
            {
                "start": date(2026, 8, 1),
                "end": date(2026, 8, 31),
                "max_pages": 3,
                "retry_blocked": False,
            },
        )
    ]


def test_market_event_history_refresh_is_admin_only_and_page_bounded(
    client, admin_headers, monkeypatch
):
    from datetime import date

    from app.services import market_events

    calls = []

    async def fake_refresh(db, **kwargs):
        calls.append(kwargs)
        return {
            "status": "refreshed",
            "window": {"start": kwargs["start"], "end": kwargs["end"]},
            "max_pages_per_provider": kwargs["max_pages"],
        }

    monkeypatch.setattr(market_events, "refresh_market_events", fake_refresh)
    path = (
        "/api/v1/market-data/events/refresh?provider=massive"
        "&start=2026-01-01&end=2026-01-31&max_pages=2&retry_blocked=true"
    )

    assert client.post(path).status_code == 401
    response = client.post(path, headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == {
        "status": "refreshed",
        "window": {"start": "2026-01-01", "end": "2026-01-31"},
        "max_pages_per_provider": 2,
    }
    assert calls == [
        {
            "start": date(2026, 1, 1),
            "end": date(2026, 1, 31),
            "provider_names": ["massive"],
            "max_pages": 2,
            "force_refresh": False,
            "retry_blocked": True,
        }
    ]

    reversed_window = client.post(
        "/api/v1/market-data/events/refresh?provider=massive" "&start=2026-02-01&end=2026-01-31",
        headers=admin_headers,
    )
    assert reversed_window.status_code == 422
    assert len(calls) == 1


def test_tokenized_assets_are_admin_only_and_preserve_provider_identity(
    client, admin_headers, db, instrument
):
    db.add(
        TokenizedAssetDetail(
            instrument_id=instrument.id,
            provider_asset_id="x:AAPL",
            provider_name="xstocks",
            token_symbol="xAAPL",
            underlying_symbol="AAPL",
            underlying_figi="BBG000B9XRY4",
            underlying_composite_figi="BBG000B9XRY4",
            underlying_isin="US0378331005",
            underlying_cusip="037833100",
            underlying_cik="0000320193",
            backing_type="fully_backed",
            deployments=[{"network": "solana", "address": "So111"}],
            provenance={"provider": "xstocks"},
        )
    )
    source = DataSource(name="xstocks-admin-test", is_active=True)
    db.add(source)
    db.flush()
    db.add(
        LatestPriceSnapshot(
            instrument_id=instrument.id,
            data_source_id=source.id,
            provider_symbol="xAAPL",
            observed_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
            price=Decimal("123.45"),
        )
    )
    db.commit()

    assert client.get("/api/v1/market-data/tokenized-assets").status_code == 401
    response = client.get(
        "/api/v1/market-data/tokenized-assets?provider=xstocks", headers=admin_headers
    )
    assert response.status_code == 200
    row = response.json()[0]
    assert row["provider"] == "xstocks"
    assert row["provider_asset_id"] == "x:AAPL"
    assert row["token_symbol"] == "xAAPL"
    assert row["underlying_figi"] == "BBG000B9XRY4"
    assert row["underlying_composite_figi"] == "BBG000B9XRY4"
    assert row["underlying_isin"] == "US0378331005"
    assert row["underlying_cusip"] == "037833100"
    assert row["underlying_cik"] == "0000320193"
    assert row["underlying_issuer_id"] is None
    assert row["deployments"][0]["address"] == "So111"
    assert row["latest_price"] == 123.45
    assert row["latest_price_provider_symbol"] == "xAAPL"
