from datetime import UTC, datetime, timedelta

from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderCapability, ProviderCapacityEvent


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
