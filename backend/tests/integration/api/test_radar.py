from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select


def _seed_radar_bars(
    db,
    instrument,
    prices: list[float],
    *,
    start_at: datetime | None = None,
    timeframe=None,
):
    from app.models.ohlcv import OHLCVBar, Timeframe

    base = start_at or (datetime.now(UTC) - timedelta(days=len(prices)))
    tf = timeframe or Timeframe.D1
    for index, price in enumerate(prices):
        db.add(
            OHLCVBar(
                instrument_id=instrument.id,
                timeframe=tf,
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
        assert detections[0]["state"] in {"developing", "confirmed"}
        assert "entry_price" in detections[0]
        assert "target_price" in detections[0]

        filtered = client.get(
            "/api/v1/radar/detections",
            headers=auth_headers,
            params={"setup_type": "approaching_support", "min_score": 0.1},
        )
        assert filtered.status_code == 200
        assert all(row["setup_type"] == "approaching_support" for row in filtered.json())

        state_filtered = client.get(
            "/api/v1/radar/detections",
            headers=auth_headers,
            params={"state": "developing"},
        )
        assert state_filtered.status_code == 200
        assert all(row["state"] == "developing" for row in state_filtered.json())
        assert "outcome_status" in detections[0]
        assert "bars_since_signal" in detections[0]

    def test_run_can_use_basket_universe(self, client, auth_headers, db, instrument, instrument_b):
        _seed_radar_bars(db, instrument, [95, 100, 95, 100, 95, 100] * 20 + [98, 97, 96, 97, 98])
        _seed_radar_bars(
            db,
            instrument_b,
            [100, 104, 108, 111, 108, 104] * 18 + [108, 110.5, 107.5, 106.5, 105.5],
        )
        basket = client.post(
            "/api/v1/baskets",
            headers=auth_headers,
            json={"name": "Radar basket", "members": [{"instrument_id": instrument.id}]},
        )
        assert basket.status_code == 200

        run_res = client.post(
            "/api/v1/radar/run",
            headers=auth_headers,
            json={
                "timeframe": "D1",
                "universe_type": "basket",
                "universe_filter": {"basket_id": basket.json()["id"]},
            },
        )
        assert run_res.status_code == 200
        run_data = run_res.json()
        assert run_data["universe_type"] == "basket"
        assert run_data["universe_filter"]["basket_id"] == basket.json()["id"]
        assert run_data["evaluated_count"] == 1

    def test_run_and_filter_by_custom_timeframe(self, client, auth_headers, db, instrument):
        from app.models.ohlcv import Timeframe

        _seed_radar_bars(
            db,
            instrument,
            [95, 100, 95, 100, 95, 100] * 20 + [98, 97, 96, 97, 98],
            timeframe=Timeframe.H4,
        )

        run_res = client.post(
            "/api/v1/radar/run",
            headers=auth_headers,
            json={"timeframe": "H4"},
        )
        assert run_res.status_code == 200
        assert run_res.json()["timeframe"] == "H4"

        list_res = client.get(
            "/api/v1/radar/detections",
            headers=auth_headers,
            params={"timeframe": "H4"},
        )
        assert list_res.status_code == 200
        rows = list_res.json()
        assert rows
        assert all(row["timeframe"] == "H4" for row in rows)

    def test_detail_and_overlay_endpoints(self, client, auth_headers, db, instrument):
        _seed_radar_bars(db, instrument, [95, 100, 95, 100, 95, 100] * 20 + [98, 97, 96, 97, 98])
        client.post("/api/v1/radar/run", headers=auth_headers)

        detections = client.get("/api/v1/radar/detections", headers=auth_headers).json()
        detection_id = detections[0]["id"]

        detail_res = client.get(f"/api/v1/radar/detections/{detection_id}", headers=auth_headers)
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["evidence"]["indicator_visuals"] or detail["evidence"]["drawing_visuals"]
        assert "metrics" in detail["evidence"]
        assert detail["thread"] is not None
        assert detail["thread_history"]
        assert detail["state"] in {"developing", "confirmed"}
        assert "invalidation_price" in detail["evidence"]["metrics"]
        assert "entry_price" in detail["evidence"]["metrics"]
        assert "target_price" in detail["evidence"]["metrics"]
        assert isinstance(detail["evidence"]["metrics"]["invalidation_price"], float)
        inv_drawings = [
            drawing
            for drawing in detail["evidence"]["drawing_visuals"]
            if drawing.get("source_role") == "invalidation"
        ]
        assert inv_drawings, "Expected an invalidation drawing in evidence"
        assert inv_drawings[0]["drawing_type"] == "horizontal_line"
        assert [
            drawing
            for drawing in detail["evidence"]["drawing_visuals"]
            if drawing.get("source_role") == "entry"
        ]
        assert [
            drawing
            for drawing in detail["evidence"]["drawing_visuals"]
            if drawing.get("source_role") == "target"
        ]
        assert (
            inv_drawings[0]["data"]["points"][0]["price"]
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
        assert "outcome_status" in overlays[0]

    def test_history_and_outcome_summary_endpoints(self, client, auth_headers, db, instrument):
        _seed_radar_bars(db, instrument, [95, 100, 95, 100, 95, 100] * 20 + [98, 97, 96, 97, 98])
        run_res = client.post("/api/v1/radar/run", headers=auth_headers)
        assert run_res.status_code == 200

        detections = client.get("/api/v1/radar/detections", headers=auth_headers).json()
        assert detections

        history_res = client.get(
            f"/api/v1/radar/instruments/{instrument.id}/history",
            headers=auth_headers,
            params={"timeframe": "D1"},
        )
        assert history_res.status_code == 200
        history = history_res.json()
        assert history
        assert all(row["instrument_id"] == instrument.id for row in history)
        assert all(row["timeframe"] == "D1" for row in history)
        assert all("created_at" in row for row in history)

        outcome_res = client.get(
            "/api/v1/radar/outcomes/summary",
            headers=auth_headers,
            params={"timeframe": "D1"},
        )
        assert outcome_res.status_code == 200
        summaries = outcome_res.json()
        assert summaries
        assert all(row["timeframe"] == "D1" for row in summaries)
        assert all("target_hit_rate" in row for row in summaries)

    def test_watchlist_and_alert_actions(self, client, auth_headers, db, instrument):
        _seed_radar_bars(db, instrument, [95, 100, 95, 100, 95, 100] * 20 + [98, 97, 96, 97, 98])
        client.post("/api/v1/radar/run", headers=auth_headers)
        detections = client.get("/api/v1/radar/detections", headers=auth_headers).json()
        detection_id = detections[0]["id"]

        watchlist_res = client.post(
            f"/api/v1/radar/detections/{detection_id}/actions/add-to-watchlist",
            headers=auth_headers,
            json={},
        )
        assert watchlist_res.status_code == 200
        watchlist_payload = watchlist_res.json()
        assert watchlist_payload["watchlist_id"] > 0
        assert watchlist_payload["item_id"] > 0

        alert_res = client.post(
            f"/api/v1/radar/detections/{detection_id}/actions/create-price-alert",
            headers=auth_headers,
            json={},
        )
        assert alert_res.status_code == 200
        alert_payload = alert_res.json()
        assert alert_payload["instrument_id"] == instrument.id
        assert alert_payload["status"] == "active"
        assert alert_payload["condition"] in {
            "crosses_above",
            "crosses_below",
            "touches",
        }

    def test_repeat_runs_continue_thread_history(self, client, auth_headers, db, instrument):
        from app.models.radar import RadarDetection

        _seed_radar_bars(db, instrument, [95, 100, 95, 100, 95, 100] * 20 + [98, 97, 96, 97, 98])

        first_run = client.post("/api/v1/radar/run", headers=auth_headers)
        assert first_run.status_code == 200
        detection_count_after_first = len(db.execute(select(RadarDetection)).scalars().all())
        second_run = client.post("/api/v1/radar/run", headers=auth_headers)
        assert second_run.status_code == 200
        detection_count_after_second = len(db.execute(select(RadarDetection)).scalars().all())

        detections = client.get("/api/v1/radar/detections", headers=auth_headers).json()
        assert detections
        detail = client.get(
            f"/api/v1/radar/detections/{detections[0]['id']}",
            headers=auth_headers,
        ).json()
        history = client.get(
            f"/api/v1/radar/instruments/{instrument.id}/history",
            headers=auth_headers,
            params={"timeframe": "D1"},
        ).json()

        assert detail["thread"] is not None
        assert detail["thread"]["detection_count"] == 1
        assert detail["thread_event_index"] is not None
        assert len(detail["thread_history"]) == detail["thread"]["detection_count"]
        assert detection_count_after_second == detection_count_after_first
        identity_rows = {
            (
                row.get("thread_id"),
                row.get("thread_event_index"),
                row.get("setup_type"),
                row.get("state"),
                row.get("signal_at"),
                row.get("context_at"),
            )
            for row in history
        }
        assert len(identity_rows) == len(history)

    def test_repeat_runs_can_transition_thread_to_invalidated(
        self, client, auth_headers, db, instrument
    ):
        prices = [95, 100, 95, 100, 95, 100] * 20 + [98, 97, 96, 97, 98]
        _seed_radar_bars(db, instrument, prices)

        first_run = client.post("/api/v1/radar/run", headers=auth_headers)
        assert first_run.status_code == 200

        _seed_radar_bars(
            db,
            instrument,
            [94, 92, 90],
            start_at=datetime.now(UTC),
        )
        second_run = client.post("/api/v1/radar/run", headers=auth_headers)
        assert second_run.status_code == 200

        invalidated = client.get(
            "/api/v1/radar/detections",
            headers=auth_headers,
            params={"state": "invalidated", "active_only": False},
        )
        assert invalidated.status_code == 200
        rows = invalidated.json()
        assert rows
        assert any(row["instrument_symbol"] == "AAPL" for row in rows)

    def test_repeat_runs_can_transition_thread_to_resolved(
        self, client, auth_headers, db, instrument
    ):
        prices = [95, 100, 95, 100, 95, 100] * 20 + [98, 97, 96, 97, 98]
        _seed_radar_bars(db, instrument, prices)

        first_run = client.post("/api/v1/radar/run", headers=auth_headers)
        assert first_run.status_code == 200

        _seed_radar_bars(
            db,
            instrument,
            [101, 104, 107, 110],
            start_at=datetime.now(UTC),
        )
        second_run = client.post("/api/v1/radar/run", headers=auth_headers)
        assert second_run.status_code == 200

        resolved = client.get(
            "/api/v1/radar/detections",
            headers=auth_headers,
            params={"state": "resolved", "active_only": False},
        )
        assert resolved.status_code == 200
        rows = resolved.json()
        assert rows
        assert any(row["instrument_symbol"] == "AAPL" for row in rows)

    def test_detection_not_found_returns_404(self, client, auth_headers):
        res = client.get("/api/v1/radar/detections/999999", headers=auth_headers)
        assert res.status_code == 404
