from datetime import UTC, datetime, timedelta
from decimal import Decimal


def test_user_can_create_update_and_delete_manual_basket(
    client,
    auth_headers,
    instrument,
    instrument_b,
):
    created = client.post(
        "/api/v1/baskets",
        headers=auth_headers,
        json={
            "name": "Mega-cap pair",
            "description": "Two-stock research basket",
            "weighting_scheme": "custom",
            "members": [
                {"instrument_id": instrument.id, "weight": "0.60"},
                {"symbol": instrument_b.symbol, "weight": "0.40"},
            ],
        },
    )

    assert created.status_code == 200
    basket = created.json()
    assert basket["name"] == "Mega-cap pair"
    assert basket["source_type"] == "manual"
    assert basket["is_read_only"] is False
    assert basket["snapshot_count"] == 1
    assert basket["latest_snapshot_date"] is not None
    assert [member["symbol"] for member in basket["members"]] == ["AAPL", "MSFT"]
    assert basket["members"][0]["weight"] == "0.60000000"

    listed = client.get("/api/v1/baskets", headers=auth_headers)
    assert listed.status_code == 200
    assert any(row["id"] == basket["id"] for row in listed.json())

    updated = client.patch(
        f"/api/v1/baskets/{basket['id']}",
        headers=auth_headers,
        json={
            "name": "Equal-weight pair",
            "weighting_scheme": "equal",
            "members": [
                {"instrument_id": instrument_b.id},
                {"instrument_id": instrument.id},
            ],
        },
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["weighting_scheme"] == "equal"
    assert updated_body["snapshot_count"] == 2
    assert [member["symbol"] for member in updated_body["members"]] == ["MSFT", "AAPL"]
    assert updated_body["members"][0]["weight"] is None

    snapshots = client.get(f"/api/v1/baskets/{basket['id']}/snapshots", headers=auth_headers)
    assert snapshots.status_code == 200
    snapshot_body = snapshots.json()
    assert len(snapshot_body) == 2
    assert [row["member_count"] for row in snapshot_body] == [2, 2]
    assert {row["source_type"] for row in snapshot_body} == {"manual"}

    deleted = client.delete(f"/api/v1/baskets/{basket['id']}", headers=auth_headers)
    assert deleted.status_code == 204
    missing = client.get(f"/api/v1/baskets/{basket['id']}", headers=auth_headers)
    assert missing.status_code == 404


def test_custom_basket_rejects_unknown_duplicate_and_unbalanced_members(
    client,
    auth_headers,
    instrument,
):
    unknown = client.post(
        "/api/v1/baskets",
        headers=auth_headers,
        json={
            "name": "Unknown member",
            "members": [{"symbol": "NOTREAL"}],
        },
    )
    assert unknown.status_code == 400
    assert "unknown instruments" in unknown.text

    duplicate = client.post(
        "/api/v1/baskets",
        headers=auth_headers,
        json={
            "name": "Duplicate member",
            "members": [
                {"instrument_id": instrument.id},
                {"symbol": instrument.symbol},
            ],
        },
    )
    assert duplicate.status_code == 400
    assert "duplicate instrument" in duplicate.text

    unbalanced = client.post(
        "/api/v1/baskets",
        headers=auth_headers,
        json={
            "name": "Bad weights",
            "weighting_scheme": "custom",
            "members": [{"instrument_id": instrument.id, "weight": "0.75"}],
        },
    )
    assert unbalanced.status_code == 400
    assert "sum to 1.0" in unbalanced.text


def test_basket_auto_classification_uses_shared_equity_metadata(
    client,
    auth_headers,
    db,
    instrument,
    instrument_b,
):
    from app.models.instrument import EquityDetail

    db.add(
        EquityDetail(
            instrument_id=instrument.id,
            sector="Technology",
            industry="Consumer Electronics",
        )
    )
    db.add(
        EquityDetail(
            instrument_id=instrument_b.id,
            sector="Technology",
            industry="Software",
        )
    )
    db.commit()

    response = client.post(
        "/api/v1/baskets",
        headers=auth_headers,
        json={
            "name": "Tech basket",
            "classification_mode": "auto",
            "members": [
                {"instrument_id": instrument.id},
                {"instrument_id": instrument_b.id},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sector"] == "Technology"
    assert body["industry"] is None


def test_basket_ohlcv_returns_rebased_weighted_series(
    client,
    auth_headers,
    db,
    instrument,
    instrument_b,
):
    from app.models.ohlcv import OHLCVBar, Timeframe

    base = datetime(2026, 1, 1, tzinfo=UTC)
    for offset, (aapl_close, msft_close) in enumerate([(100, 200), (110, 220), (121, 198)]):
        ts = base + timedelta(days=offset)
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=Timeframe.D1,
                ts=ts,
                open=Decimal(str(aapl_close)),
                high=Decimal(str(aapl_close)),
                low=Decimal(str(aapl_close)),
                close=Decimal(str(aapl_close)),
                volume=Decimal("1000"),
                is_adjusted=True,
            )
        )
        db.add(
            OHLCVBar(
                instrument_id=instrument_b.id,
                timeframe=Timeframe.D1,
                ts=ts,
                open=Decimal(str(msft_close)),
                high=Decimal(str(msft_close)),
                low=Decimal(str(msft_close)),
                close=Decimal(str(msft_close)),
                volume=Decimal("2000"),
                is_adjusted=True,
            )
        )
    db.flush()

    created = client.post(
        "/api/v1/baskets",
        headers=auth_headers,
        json={
            "name": "Equal pair",
            "members": [
                {"instrument_id": instrument.id},
                {"instrument_id": instrument_b.id},
            ],
        },
    )
    assert created.status_code == 200
    basket_id = created.json()["id"]

    response = client.get(f"/api/v1/baskets/{basket_id}/ohlcv/D1", headers=auth_headers)

    assert response.status_code == 200
    bars = response.json()
    assert len(bars) == 3
    assert bars[0]["close"] == 100
    assert bars[1]["close"] == 110
    # AAPL +21% and MSFT -1%, equal weighted from the first aligned bar.
    assert bars[2]["close"] == 110
    assert bars[2]["volume"] == 3000
