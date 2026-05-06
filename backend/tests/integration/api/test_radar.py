from datetime import UTC, datetime, timedelta
from decimal import Decimal


def _seed_radar_bars(db, instrument, prices: list[float]):
    from app.models.ohlcv import OHLCVBar, Timeframe

    base = datetime.now(UTC) - timedelta(days=len(prices))
    for index, price in enumerate(prices):
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=Timeframe.D1,
                ts=base + timedelta(days=index),
                open=Decimal(str(round(price - 0.5, 4))),
                high=Decimal(str(round(price + 1.3, 4))),
                low=Decimal(str(round(price - 1.3, 4))),
                close=Decimal(str(round(price, 4))),
                volume=Decimal("1000000"),
                is_adjusted=True,
            )
        )
    db.flush()


class TestRadarAPI:
    def test_run_and_list_detections(self, client, auth_headers, db, instrument, instrument_b):
        _seed_radar_bars(db, instrument, [95, 100, 95, 100, 95, 100] * 20 + [98, 97, 96, 97, 98])
        _seed_radar_bars(
            db,
            instrument_b,
            [100, 104, 108, 111, 108, 104] * 18 + [108, 110.5, 107.5, 106.5, 105.5],
        )

        run_res = client.post("/api/v1/radar/run", headers=auth_headers)
        assert run_res.status_code == 200
        run_data = run_res.json()
        assert run_data["status"] == "completed"
        assert run_data["detection_count"] >= 1

        list_res = client.get("/api/v1/radar/detections", headers=auth_headers)
        assert list_res.status_code == 200
        detections = list_res.json()
        assert detections
        assert detections[0]["instrument_symbol"] in {"AAPL", "MSFT"}
        assert "signal_at" in detections[0]
        assert "thread_id" in detections[0]

        filtered = client.get(
            "/api/v1/radar/detections",
            headers=auth_headers,
            params={"setup_type": "approaching_support", "min_score": 0.1},
        )
        assert filtered.status_code == 200
        assert all(row["setup_type"] == "approaching_support" for row in filtered.json())

    def test_detail_and_overlay_endpoints(self, client, auth_headers, db, instrument):
        _seed_radar_bars(db, instrument, [95, 100, 95, 100, 95, 100] * 20 + [98, 97, 96, 97, 98])
        client.post("/api/v1/radar/run", headers=auth_headers)

        detections = client.get("/api/v1/radar/detections", headers=auth_headers).json()
        detection_id = detections[0]["id"]

        detail_res = client.get(f"/api/v1/radar/detections/{detection_id}", headers=auth_headers)
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["evidence"]["overlays"]
        assert "metrics" in detail["evidence"]
        assert detail["thread"] is not None
        assert detail["thread_history"]
        assert "invalidation_price" in detail["evidence"]["metrics"]
        assert isinstance(detail["evidence"]["metrics"]["invalidation_price"], float)
        inv_overlays = [
            o for o in detail["evidence"]["overlays"] if o.get("role") == "invalidation"
        ]
        assert inv_overlays, "Expected an invalidation overlay in evidence"
        assert inv_overlays[0]["kind"] == "line"
        assert (
            inv_overlays[0]["points"][0]["price"]
            == detail["evidence"]["metrics"]["invalidation_price"]
        )

        overlay_res = client.get(
            f"/api/v1/radar/instruments/{instrument.id}/overlays",
            headers=auth_headers,
            params={"detection_id": detection_id},
        )
        assert overlay_res.status_code == 200
        overlays = overlay_res.json()
        assert len(overlays) == 1
        assert overlays[0]["id"] == detection_id
        assert overlays[0]["thread_history"]

    def test_repeat_runs_continue_thread_history(self, client, auth_headers, db, instrument):
        _seed_radar_bars(db, instrument, [95, 100, 95, 100, 95, 100] * 20 + [98, 97, 96, 97, 98])

        first_run = client.post("/api/v1/radar/run", headers=auth_headers)
        assert first_run.status_code == 200
        second_run = client.post("/api/v1/radar/run", headers=auth_headers)
        assert second_run.status_code == 200

        detections = client.get("/api/v1/radar/detections", headers=auth_headers).json()
        assert detections
        detail = client.get(
            f"/api/v1/radar/detections/{detections[0]['id']}",
            headers=auth_headers,
        ).json()

        assert detail["thread"] is not None
        assert detail["thread"]["detection_count"] == 1
        assert detail["thread_event_index"] is not None
        assert len(detail["thread_history"]) == detail["thread"]["detection_count"]

    def test_detection_not_found_returns_404(self, client, auth_headers):
        res = client.get("/api/v1/radar/detections/999999", headers=auth_headers)
        assert res.status_code == 404
