from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.data_source import DataSource
from app.models.market_data_foundation import MarketRefreshJob
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
    assert row["deployments"][0]["address"] == "So111"
    assert row["latest_price"] == 123.45
    assert row["latest_price_provider_symbol"] == "xAAPL"
