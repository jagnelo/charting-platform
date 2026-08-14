"""
Integration tests for /screeners endpoints + the screener engine
running against a real Postgres DB.

Condition tree format (new):
  {"operator": "AND|OR|NOT", "conditions": [
      {"type": "price_threshold",    "field": "close", "op": "gt|lt|eq|gte|lte", "value": N},
      {"type": "indicator_threshold","indicator": "rsi", "params": {...}, "op": "lt", "value": N},
      {"type": "indicator_cross",    "indicator_a": {...}, "indicator_b": {...}, "op": "crosses_above"},
  ]}
"""

import json
from datetime import UTC, datetime, timedelta

from app.models.screener import ScreenerResult


class TestScreenerCRUD:
    def test_screener_history_can_be_consumed_as_a_numeric_plot(
        self, client, auth_headers, screener, db
    ):
        base = datetime.now(UTC) - timedelta(days=1)
        db.add_all(
            [
                ScreenerResult(
                    screener_id=screener.id,
                    run_at=base,
                    matched_ids=[1, 2],
                    result_data={
                        "_coverage": {
                            "universe_count": 4,
                            "evaluated_count": 4,
                            "excluded": [],
                        }
                    },
                ),
                ScreenerResult(
                    screener_id=screener.id,
                    run_at=base + timedelta(days=1),
                    matched_ids=[1],
                    result_data={
                        "_coverage": {
                            "universe_count": 4,
                            "evaluated_count": 2,
                            "excluded": [{"instrument_id": 4}],
                        }
                    },
                ),
            ]
        )
        db.commit()

        percentage = client.get(
            f"/api/v1/screeners/{screener.id}/plot",
            headers=auth_headers,
            params={"metric": "percentage"},
        )
        assert percentage.status_code == 200
        payload = percentage.json()
        assert payload["history_count"] == 2
        assert [point["value"] for point in payload["points"]] == [50.0, 50.0]
        assert payload["points"][1]["coverage"] == 0.5
        assert payload["warning"] is None

        count = client.get(
            f"/api/v1/screeners/{screener.id}/plot",
            headers=auth_headers,
            params={"metric": "count"},
        )
        assert count.status_code == 200
        assert [point["value"] for point in count.json()["points"]] == [2.0, 1.0]

    def test_screener_history_plot_does_not_fabricate_empty_history(
        self, client, auth_headers, screener
    ):
        response = client.get(f"/api/v1/screeners/{screener.id}/plot", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["points"] == []
        assert "No retained scan history" in response.json()["warning"]

    def test_create_screener_from_saved_condition(self, client, auth_headers):
        condition = {
            "operator": "AND",
            "conditions": [{"type": "price_threshold", "field": "close", "op": "gt", "value": 100}],
        }
        saved = client.put(
            "/api/v1/workspaces/library/conditions/close-above-100",
            headers=auth_headers,
            json={"name": "Close above 100", "condition": condition},
        )
        assert saved.status_code == 200
        created = client.post(
            "/api/v1/screeners/from-condition/close-above-100",
            headers=auth_headers,
            json={"name": "Saved condition scan", "universe_type": "all", "timeframe": "D1"},
        )
        assert created.status_code == 201
        created_conditions = created.json()["conditions"]
        assert created_conditions["type"] == "python_condition"
        assert (
            created_conditions["code_version_id"]
            == saved.json()["payload"]["python_code_version_id"]
        )

    def test_python_condition_screener_queues_and_reconciles_batch_result(
        self, client, auth_headers, instrument, ohlcv_bars, tmp_path, monkeypatch
    ):
        """A Python EasyScan must stay isolated from FastAPI and reconcile typed cells."""
        monkeypatch.setattr(
            "app.services.research_jobs.settings.RESEARCH_JOB_DIR", str(tmp_path / "jobs")
        )
        monkeypatch.setattr(
            "app.services.research_jobs.settings.RESEARCH_RESULT_DIR", str(tmp_path / "results")
        )
        asset = client.post(
            "/api/v1/code/assets",
            headers=auth_headers,
            json={
                "stable_key": "python-qualifies",
                "name": "Python qualifies",
                "kind": "condition",
                "initial_version": {
                    "source": "output.boolean('qualifies', True)",
                    "output_contract": "boolean",
                },
            },
        )
        assert asset.status_code == 201
        version_id = asset.json()["versions"][0]["id"]

        created = client.post(
            f"/api/v1/screeners/from-python-condition/{version_id}",
            headers=auth_headers,
            json={
                "name": "Python qualifies scan",
                "universe_type": "custom",
                "universe_instrument_ids": [instrument.id],
                "timeframe": "D1",
            },
        )
        assert created.status_code == 201
        screener = created.json()
        assert screener["conditions"] == {"type": "python_condition", "code_version_id": version_id}
        alert = client.post(
            "/api/v1/alerts/screener",
            headers=auth_headers,
            json={"screener_id": screener["id"], "trigger_type": "entered", "repeat": True},
        )
        assert alert.status_code == 201

        queued = client.post(f"/api/v1/screeners/{screener['id']}/run", headers=auth_headers)
        assert queued.status_code == 200
        queued_result = queued.json()
        assert queued_result["result_data"]["_status"] == "queued"
        run_id = queued_result["result_data"]["_python_research_run_id"]
        assert (tmp_path / "jobs" / f"{run_id}.json").exists()

        result_dir = tmp_path / "results"
        result_dir.mkdir()
        (result_dir / f"{run_id}.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "artifacts": {
                        "batch_cells": {
                            "type": "batch",
                            "value": {
                                "cells": [
                                    {
                                        "instrument_id": instrument.id,
                                        "symbol": instrument.symbol,
                                        "status": "completed",
                                        "value": True,
                                    }
                                ]
                            },
                        }
                    },
                }
            )
        )
        results = client.get(
            f"/api/v1/screeners/{screener['id']}/results",
            headers=auth_headers,
            params={"limit": 1},
        )
        assert results.status_code == 200
        reconciled = results.json()[0]
        assert reconciled["matched_ids"] == [instrument.id]
        assert reconciled["result_data"]["_status"] == "completed"
        assert reconciled["result_data"]["_coverage"] == {
            "universe_count": 1,
            "evaluated_count": 1,
            "excluded": [],
        }
        alerts = client.get("/api/v1/alerts/screener", headers=auth_headers)
        assert alerts.status_code == 200
        assert alerts.json()[0]["last_checked_run_id"] == reconciled["id"]
        history = client.get(
            "/api/v1/alerts/history",
            headers=auth_headers,
            params={"alert_type": "screener", "instrument_id": instrument.id},
        )
        assert history.status_code == 200
        assert history.json()[0]["condition_snapshot"] == {
            "event": "entered",
            "screener_id": screener["id"],
            "screener_name": screener["name"],
            "trigger_type": "entered",
            "run_id": reconciled["id"],
        }

    def test_python_condition_can_reference_a_single_output_study_version(
        self, client, auth_headers, instrument
    ):
        asset = client.post(
            "/api/v1/code/assets",
            headers=auth_headers,
            json={
                "stable_key": "study-boolean-reuse",
                "name": "Reusable study boolean",
                "kind": "study",
                "initial_version": {
                    "source": "output.boolean('qualifies', True)",
                    "output_contract": "boolean",
                },
            },
        )
        assert asset.status_code == 201
        version_id = asset.json()["versions"][0]["id"]
        created = client.post(
            f"/api/v1/screeners/from-python-condition/{version_id}",
            headers=auth_headers,
            json={
                "name": "Reusable study scan",
                "universe_type": "custom",
                "universe_instrument_ids": [instrument.id],
                "timeframe": "D1",
            },
        )
        assert created.status_code == 201
        assert created.json()["conditions"] == {
            "type": "python_condition",
            "code_version_id": version_id,
        }

    def test_create_screener(self, client, auth_headers):
        res = client.post(
            "/api/v1/screeners",
            headers=auth_headers,
            json={
                "name": "Oversold RSI",
                "conditions": {
                    "operator": "AND",
                    "conditions": [
                        {
                            "type": "indicator_threshold",
                            "indicator": "rsi",
                            "params": {"period": 14},
                            "op": "lt",
                            "value": 30,
                        }
                    ],
                },
                "universe_type": "all",
                "timeframe": "D1",
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "Oversold RSI"
        assert data["conditions"]["operator"] == "AND"
        assert len(data["conditions"]["conditions"]) == 1

    def test_list_screeners(self, client, auth_headers, screener):
        res = client.get("/api/v1/screeners", headers=auth_headers)
        assert res.status_code == 200
        ids = [s["id"] for s in res.json()]
        assert screener.id in ids

    def test_get_screener(self, client, auth_headers, screener):
        res = client.get(f"/api/v1/screeners/{screener.id}", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["id"] == screener.id

    def test_get_screener_not_found(self, client, auth_headers):
        res = client.get("/api/v1/screeners/99999", headers=auth_headers)
        assert res.status_code == 404

    def test_screener_user_isolation(self, client, db, screener):
        from app.models.user import User
        from app.services.auth import create_access_token, hash_password

        other = User(
            username="screener_other",
            email="screener_other@test.com",
            hashed_password=hash_password("x"),
            is_active=True,
        )
        db.add(other)
        db.flush()
        headers = {"Authorization": f"Bearer {create_access_token(other.id, 'screener_other')}"}
        res = client.get(f"/api/v1/screeners/{screener.id}", headers=headers)
        assert res.status_code == 404

    def test_delete_screener(self, client, auth_headers, screener):
        res = client.delete(f"/api/v1/screeners/{screener.id}", headers=auth_headers)
        assert res.status_code == 204

    def test_screener_requires_auth(self, client):
        res = client.get("/api/v1/screeners")
        assert res.status_code == 401

    def test_duplicate_name_rejected(self, client, auth_headers):
        payload = {
            "name": "Dupe Screener",
            "conditions": {"operator": "AND", "conditions": []},
            "universe_type": "all",
            "timeframe": "D1",
        }
        assert (
            client.post("/api/v1/screeners", headers=auth_headers, json=payload).status_code == 201
        )
        assert (
            client.post("/api/v1/screeners", headers=auth_headers, json=payload).status_code == 409
        )


class TestScreenerAlertCRUD:
    def test_alert_lifecycle_and_user_isolation(self, client, db, auth_headers, screener):
        created = client.post(
            "/api/v1/alerts/screener",
            headers=auth_headers,
            json={"screener_id": screener.id, "trigger_type": "entered", "repeat": True},
        )
        assert created.status_code == 201
        alert = created.json()
        assert alert["screener_id"] == screener.id
        assert alert["screener_name"] == screener.name
        assert alert["status"] == "active"
        assert alert["repeat"] is True

        listed = client.get("/api/v1/alerts/screener", headers=auth_headers)
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()] == [alert["id"]]

        paused = client.patch(
            f"/api/v1/alerts/screener/{alert['id']}",
            headers=auth_headers,
            json={"status": "paused", "repeat": False},
        )
        assert paused.status_code == 200
        assert paused.json()["status"] == "paused"
        assert paused.json()["repeat"] is False

        rearmed = client.post(
            f"/api/v1/alerts/screener/{alert['id']}/rearm", headers=auth_headers, json={}
        )
        assert rearmed.status_code == 200
        assert rearmed.json()["status"] == "active"

        from app.models.user import User
        from app.services.auth import create_access_token, hash_password

        other = User(
            username="screener_alert_other",
            email="screener_alert_other@test.com",
            hashed_password=hash_password("x"),
            is_active=True,
        )
        db.add(other)
        db.flush()
        other_headers = {
            "Authorization": f"Bearer {create_access_token(other.id, 'screener_alert_other')}"
        }
        assert client.get("/api/v1/alerts/screener", headers=other_headers).json() == []
        assert (
            client.patch(
                f"/api/v1/alerts/screener/{alert['id']}",
                headers=other_headers,
                json={"status": "disabled"},
            ).status_code
            == 404
        )
        assert (
            client.delete(
                f"/api/v1/alerts/screener/{alert['id']}", headers=auth_headers
            ).status_code
            == 200
        )
        assert client.get("/api/v1/alerts/screener", headers=auth_headers).json() == []


class TestScreenerRun:
    def test_run_screener_empty_conditions_returns_result(self, client, auth_headers, screener):
        res = client.post(f"/api/v1/screeners/{screener.id}/run", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "matched_ids" in data
        assert "duration_ms" in data
        assert "result_data" in data

    def test_run_screener_price_condition_matches(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        """Screener with close > 0 should match our AAPL instrument."""
        create_res = client.post(
            "/api/v1/screeners",
            headers=auth_headers,
            json={
                "name": "Any Price",
                "conditions": {
                    "operator": "AND",
                    "conditions": [
                        {"type": "price_threshold", "field": "close", "op": "gt", "value": 0}
                    ],
                },
                "universe_type": "all",
                "timeframe": "D1",
            },
        )
        assert create_res.status_code == 201
        screener_id = create_res.json()["id"]
        run_res = client.post(f"/api/v1/screeners/{screener_id}/run", headers=auth_headers)
        assert run_res.status_code == 200
        assert instrument.id in run_res.json()["matched_ids"]

    def test_run_screener_can_use_basket_universe(
        self, client, auth_headers, instrument, ohlcv_bars
    ):
        basket = client.post(
            "/api/v1/baskets",
            headers=auth_headers,
            json={
                "name": "Screener basket",
                "members": [{"instrument_id": instrument.id}],
            },
        )
        assert basket.status_code == 200

        create_res = client.post(
            "/api/v1/screeners",
            headers=auth_headers,
            json={
                "name": "Basket Price",
                "conditions": {
                    "operator": "AND",
                    "conditions": [
                        {"type": "price_threshold", "field": "close", "op": "gt", "value": 0}
                    ],
                },
                "universe_type": "basket",
                "universe_basket_id": basket.json()["id"],
                "timeframe": "D1",
            },
        )
        assert create_res.status_code == 201
        assert create_res.json()["universe_basket_id"] == basket.json()["id"]

        run_res = client.post(
            f"/api/v1/screeners/{create_res.json()['id']}/run",
            headers=auth_headers,
        )
        assert run_res.status_code == 200
        assert run_res.json()["matched_ids"] == [instrument.id]

    def test_run_screener_impossible_condition_no_matches(
        self, client, auth_headers, db, instrument, ohlcv_bars
    ):
        """Price > 999999 should match nothing."""
        create_res = client.post(
            "/api/v1/screeners",
            headers=auth_headers,
            json={
                "name": "Impossible",
                "conditions": {
                    "operator": "AND",
                    "conditions": [
                        {
                            "type": "price_threshold",
                            "field": "close",
                            "op": "gt",
                            "value": 999999,
                        }
                    ],
                },
                "universe_type": "all",
                "timeframe": "D1",
            },
        )
        screener_id = create_res.json()["id"]
        run_res = client.post(f"/api/v1/screeners/{screener_id}/run", headers=auth_headers)
        assert run_res.status_code == 200
        assert run_res.json()["matched_ids"] == []

    def test_run_saves_result(self, client, auth_headers, screener):
        client.post(f"/api/v1/screeners/{screener.id}/run", headers=auth_headers)
        results_res = client.get(
            f"/api/v1/screeners/{screener.id}/results", headers=auth_headers, params={"limit": 5}
        )
        assert results_res.status_code == 200
        assert len(results_res.json()) >= 1

    def test_result_history_limit_is_bounded(self, client, auth_headers, screener):
        for value in (0, 101):
            response = client.get(
                f"/api/v1/screeners/{screener.id}/results",
                headers=auth_headers,
                params={"limit": value},
            )
            assert response.status_code == 422

    def test_market_gauge_uses_the_latest_saved_scan_with_coverage(
        self, client, auth_headers, screener
    ):
        client.post(f"/api/v1/screeners/{screener.id}/run", headers=auth_headers)
        gauge = client.get(f"/api/v1/analysis/gauges/{screener.id}", headers=auth_headers)
        assert gauge.status_code == 200
        payload = gauge.json()
        assert payload["screener_id"] == screener.id
        assert payload["run_at"] is not None
        assert payload["universe_count"] >= payload["evaluated_count"]

    def test_market_gauge_is_honest_before_a_scan_is_run(self, client, auth_headers, screener):
        gauge = client.get(f"/api/v1/analysis/gauges/{screener.id}", headers=auth_headers)
        assert gauge.status_code == 200
        assert gauge.json()["percentage"] is None
        assert gauge.json()["exclusions"][0]["code"] == "scan_not_run"

    def test_streaming_scan_reports_missing_local_history_without_provider_fetch(
        self, client, auth_headers, instrument_b
    ):
        """Cold scan members are coverage exclusions, not interactive provider calls."""
        created = client.post(
            "/api/v1/screeners",
            headers=auth_headers,
            json={
                "name": "Local history only",
                "conditions": {"operator": "AND", "conditions": []},
                "universe_type": "custom",
                "universe_instrument_ids": [instrument_b.id],
                "timeframe": "D1",
            },
        )
        assert created.status_code == 201

        response = client.post(
            f"/api/v1/screeners/{created.json()['id']}/run/stream", headers=auth_headers
        )
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
        assert {
            "type": "error",
            "instrument_id": instrument_b.id,
            "code": "coverage_missing_ohlcv",
            "message": "Fewer than two canonical local bars are available for this timeframe.",
        } in events
        done = events[-1]
        assert done["type"] == "done"
        assert (
            done["coverage"]["excluded"][str(instrument_b.id)]["code"] == "coverage_missing_ohlcv"
        )

    def test_or_logic_screener(self, client, auth_headers, instrument, ohlcv_bars):
        """OR screener: either impossible OR definitely-true → should match."""
        create_res = client.post(
            "/api/v1/screeners",
            headers=auth_headers,
            json={
                "name": "OR Test",
                "conditions": {
                    "operator": "OR",
                    "conditions": [
                        {
                            "type": "price_threshold",
                            "field": "close",
                            "op": "gt",
                            "value": 999999,
                        },
                        {
                            "type": "price_threshold",
                            "field": "close",
                            "op": "gt",
                            "value": 0,
                        },
                    ],
                },
                "universe_type": "all",
                "timeframe": "D1",
            },
        )
        screener_id = create_res.json()["id"]
        run_res = client.post(f"/api/v1/screeners/{screener_id}/run", headers=auth_headers)
        assert instrument.id in run_res.json()["matched_ids"]

    def test_and_logic_requires_all_conditions(self, client, auth_headers, instrument, ohlcv_bars):
        """AND screener with one impossible condition → no matches."""
        create_res = client.post(
            "/api/v1/screeners",
            headers=auth_headers,
            json={
                "name": "AND Test",
                "conditions": {
                    "operator": "AND",
                    "conditions": [
                        {
                            "type": "price_threshold",
                            "field": "close",
                            "op": "gt",
                            "value": 0,
                        },
                        {
                            "type": "price_threshold",
                            "field": "close",
                            "op": "gt",
                            "value": 999999,
                        },
                    ],
                },
                "universe_type": "all",
                "timeframe": "D1",
            },
        )
        screener_id = create_res.json()["id"]
        run_res = client.post(f"/api/v1/screeners/{screener_id}/run", headers=auth_headers)
        assert run_res.json()["matched_ids"] == []
